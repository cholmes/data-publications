#!/usr/bin/env python3
"""Checks of an index release (index-package-plan.md), separate from the builders.

    python check_index_release.py list --out NEW_FILE
    python check_index_release.py check --release DIR --hosted DIR --artifacts ROOT \
        --listing FILE --out NEW_FILE [--changes FILE]

`list` makes an anonymous listing of the hosted product through data.source.coop (key and
size of every file under nthh/naip/). `check` runs checks 1b, 1c and 3 to 9 on the two files
in DIR (`naip.parquet`, `naip-overviews.parquet`), comparing with the hosted files in --hosted
(read anonymously beforehand) and with the receipts and overview build results under ROOT.

--changes names the differences from the hosted files a release is meant to have, written down
before the build: columns added (`added_columns`) and collection fields given new values
(`collection_fields`, by collection id). Checks 1b and 1c compare with the hosted files with
those changes made, and nothing else may differ. Check 11 tests the `naip:gti_location` column and
the two .gti files in DIR, when the release has them.

This program imports neither build_stac_index.py nor build_overview_index.py nor
partial_years.py. It decodes footprints from WKB and tests outlines with its own code; the only
geometry library it uses is pyproj, to take a file's corners from its CRS to degrees.
"""
import argparse
import collections
import copy
import glob
import hashlib
import json
import math
import os
import re
import struct
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import Transformer

HERE = os.path.dirname(os.path.abspath(__file__))
LIST_URL = "https://data.source.coop/nthh"
PREFIX = "naip/"
FILES = "https://data.source.coop/nthh/naip/"
OUT_URI = "s3://us-west-2.opendata.source.coop/nthh/naip/"
FULL = 0.9
TOL_BBOX = 1e-9
TOL_CORNER = 1e-6
TOL_COVER = 1e-9
OVERVIEW_RESULTS = "overviews/national/results/*-result.json"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------- listing ----------

def make_listing(out):
    files, token, pages = {}, None, 0
    while True:
        query = {"list-type": "2", "prefix": PREFIX, "max-keys": "1000"}
        if token:
            query["continuation-token"] = token
        with urllib.request.urlopen(f"{LIST_URL}?{urllib.parse.urlencode(query)}", timeout=60) as response:
            root = ET.fromstring(response.read())
        pages += 1
        ns = {"s": root.tag.split("}")[0].strip("{")}
        for item in root.findall("s:Contents", ns):
            files[item.find("s:Key", ns).text[len(PREFIX):]] = int(item.find("s:Size", ns).text)
        if root.findtext("s:IsTruncated", namespaces=ns) != "true":
            break
        token = root.findtext("s:NextContinuationToken", namespaces=ns)
    with open(out, "w") as f:
        json.dump({"listed_from": f"{LIST_URL}?list-type=2&prefix={PREFIX}", "pages": pages, "files": files}, f)
    print(f"{len(files)} files in {pages} pages")


# ---------- WKB ----------

def wkb_polygons(data):
    """A list of polygons, each a list of rings, each an (n, 2) array, from WKB (Polygon or MultiPolygon)."""
    def polygon(at, order):
        (rings,) = struct.unpack_from(order + "I", data, at)
        at += 4
        out = []
        for _ in range(rings):
            (n,) = struct.unpack_from(order + "I", data, at)
            at += 4
            out.append(np.frombuffer(data, dtype=np.dtype(order + "f8"), count=2 * n, offset=at).reshape(n, 2))
            at += 16 * n
        return out, at

    order = "<" if data[0] == 1 else ">"
    (kind,) = struct.unpack_from(order + "I", data, 1)
    if kind == 3:
        return [polygon(5, order)[0]]
    if kind == 6:
        (count,) = struct.unpack_from(order + "I", data, 5)
        at, out = 9, []
        for _ in range(count):
            inner = "<" if data[at] == 1 else ">"
            (sub,) = struct.unpack_from(inner + "I", data, at + 1)
            if sub != 3:
                raise ValueError(f"MultiPolygon part of type {sub}")
            rings, at = polygon(at + 5, inner)
            out.append(rings)
        return out
    raise ValueError(f"geometry type {kind}")


def edges_of(polygons):
    """(m, 4) array of x0, y0, x1, y1 for every ring edge."""
    parts = [np.hstack([ring[:-1], ring[1:]]) for rings in polygons for ring in rings]
    return np.vstack(parts)


def point_segment_distance(points, edges):
    """For each point, the least distance to any edge. points (k, 2), edges (m, 4)."""
    p = points[:, None, :]
    a, b = edges[None, :, 0:2], edges[None, :, 2:4]
    ab = b - a
    t = np.clip(((p - a) * ab).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-300), 0, 1)
    nearest = a + t[..., None] * ab
    return np.sqrt(((p - nearest) ** 2).sum(-1)).min(1)


def inside(points, edges):
    """Even-odd rule over all ring edges (outer rings and holes alike)."""
    x, y = points[:, 0:1], points[:, 1:2]
    x0, y0, x1, y1 = (edges[None, :, i] for i in range(4))
    crosses = ((y0 > y) != (y1 > y)) & (x < (x1 - x0) * (y - y0) / np.where(y1 == y0, 1e-300, y1 - y0) + x0)
    return crosses.sum(1) % 2 == 1


def proper_crossings(a, b, tol):
    """True where a segment of a (k, 4) properly crosses a segment of b (m, 4), beyond tol."""
    def orient(p, q, r):
        return (q[..., 0] - p[..., 0]) * (r[..., 1] - p[..., 1]) - (q[..., 1] - p[..., 1]) * (r[..., 0] - p[..., 0])
    p1, p2 = a[:, None, 0:2], a[:, None, 2:4]
    q1, q2 = b[None, :, 0:2], b[None, :, 2:4]
    scale_a = np.sqrt(((p2 - p1) ** 2).sum(-1))
    scale_b = np.sqrt(((q2 - q1) ** 2).sum(-1))
    d1, d2 = orient(p1, p2, q1) / np.maximum(scale_a, 1e-300), orient(p1, p2, q2) / np.maximum(scale_a, 1e-300)
    d3, d4 = orient(q1, q2, p1) / np.maximum(scale_b, 1e-300), orient(q1, q2, p2) / np.maximum(scale_b, 1e-300)
    return (((d1 > tol) & (d2 < -tol)) | ((d1 < -tol) & (d2 > tol))) & (((d3 > tol) & (d4 < -tol)) | ((d3 < -tol) & (d4 > tol)))


def covers(outline_edges, quad_ring, tol):
    """Whether an outline (its edges) covers a simple convex quad footprint, to tol degrees."""
    vertices = quad_ring[:-1]
    near = point_segment_distance(vertices, outline_edges) <= tol
    if not (inside(vertices, outline_edges) | near).all():
        return False
    lo, hi = quad_ring.min(0) - tol, quad_ring.max(0) + tol
    keep = ~((np.maximum(outline_edges[:, 0], outline_edges[:, 2]) < lo[0]) | (np.minimum(outline_edges[:, 0], outline_edges[:, 2]) > hi[0])
             | (np.maximum(outline_edges[:, 1], outline_edges[:, 3]) < lo[1]) | (np.minimum(outline_edges[:, 1], outline_edges[:, 3]) > hi[1]))
    local = outline_edges[keep]
    if not len(local):
        return True
    quad_edges = np.hstack([quad_ring[:-1], quad_ring[1:]])
    if proper_crossings(quad_edges, local, tol).any():
        return False
    ends = np.vstack([local[:, 0:2], local[:, 2:4]])
    strictly = inside(ends, quad_edges) & (point_segment_distance(ends, quad_edges) > tol)
    return not strictly.any()


# ---------- expected state ----------

def receipts(root):
    with open(os.path.join(HERE, "evidence", "receipt-dirs-62.json")) as f:
        dirs = json.load(f)
    out = []
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(root, d, "*.json"))):
            with open(path) as f:
                r = json.load(f)
            rel = r["out_uri"][len(OUT_URI):]
            state, year = rel.split("/")[0], int(rel.split("/")[1])
            out.append({"href": FILES + rel, "state": state, "year": year, "size": r["output_bytes"], "sha256": r["output_sha256"]})
    return out


def listed_years(all_receipts):
    counts = collections.Counter((r["state"], r["year"]) for r in all_receipts)
    left = {(s, y) for (s, y), n in counts.items() if any(s2 == s and y2 < y and n < FULL * m for (s2, y2), m in counts.items())}
    return set(counts) - left, left, counts


# ---------- checks ----------

def failure_list(items, limit=20):
    items = sorted(items)
    return {"count": len(items), "first": items[:limit]}


def check_accounting(table, expected, left_hrefs):
    hrefs = [a["image"]["href"] for a in table.column("assets").to_pylist()]
    counted = collections.Counter(hrefs)
    have, want = set(hrefs), set(expected)
    missing, extra = want - have, have - want
    twice = [h for h, n in counted.items() if n > 1]
    return {"passed": not (missing or extra or twice), "rows": len(hrefs), "expected": len(want),
            "missing": failure_list(missing), "extra": failure_list(extra),
            "extra_from_left_out_years": len(extra & left_hrefs), "twice": failure_list(twice)}


def check_size_checksum(table, expected):
    wrong = []
    for a in table.column("assets").to_pylist():
        image, r = a["image"], expected.get(a["image"]["href"])
        if r is None:
            continue
        if image["file:size"] != r["size"] or image["file:checksum"] != "1220" + r["sha256"]:
            wrong.append(image["href"])
    return {"passed": not wrong, "wrong": failure_list(wrong)}


def check_listing(table, listing, label):
    absent, wrong = [], []
    for a in table.column("assets").to_pylist():
        href, size = a["image"]["href"], a["image"]["file:size"]
        key = href[len(FILES):]
        if key not in listing:
            absent.append(key)
        elif listing[key] != size:
            wrong.append(key)
    return {"passed": not absent and not wrong, "rows": table.num_rows, "absent": failure_list(absent),
            "size_differs": failure_list(wrong), "table": label}


def check_footprints(table, corners):
    bad_bbox, bad_corner, open_ring, worst_corner = [], [], [], 0.0
    ids, geoms, boxes = table.column("id").to_pylist(), table.column("geometry").to_pylist(), table.column("bbox").to_pylist()
    lonlat = None
    if corners:
        epsgs = np.array(table.column("proj:epsg").to_pylist())
        pb = np.array(table.column("proj:bbox").to_pylist())
        xs = np.stack([pb[:, 0], pb[:, 2], pb[:, 2], pb[:, 0]], 1)
        ys = np.stack([pb[:, 1], pb[:, 1], pb[:, 3], pb[:, 3]], 1)
        lonlat = np.zeros(xs.shape + (2,))
        for epsg in np.unique(epsgs):
            rows = epsgs == epsg
            lon, lat = Transformer.from_crs(int(epsg), 4326, always_xy=True).transform(xs[rows], ys[rows])
            lonlat[rows, :, 0], lonlat[rows, :, 1] = lon, lat
    for i, (item, wkb, box) in enumerate(zip(ids, geoms, boxes)):
        polygons = wkb_polygons(wkb)
        if any(not np.array_equal(ring[0], ring[-1]) for rings in polygons for ring in rings):
            open_ring.append(item)
        allpts = np.vstack([ring for rings in polygons for ring in rings])
        lo, hi = allpts.min(0), allpts.max(0)
        if max(abs(box["xmin"] - lo[0]), abs(box["ymin"] - lo[1]), abs(box["xmax"] - hi[0]), abs(box["ymax"] - hi[1])) > TOL_BBOX:
            bad_bbox.append(item)
        if corners:
            d = float(point_segment_distance(lonlat[i], edges_of(polygons)).max())
            worst_corner = max(worst_corner, d)
            if d > TOL_CORNER:
                bad_corner.append(item)
    out = {"passed": not bad_bbox and not bad_corner and not open_ring, "bbox_not_bounds": failure_list(bad_bbox),
           "ring_not_closed": failure_list(open_ring)}
    if corners:
        out.update({"corner_off_outline": failure_list(bad_corner), "worst_corner_degrees": worst_corner})
    return out


def check_dates(table):
    wrong = []
    for item, when in zip(table.column("id").to_pylist(), table.column("datetime").to_pylist()):
        # <state>_m_<block><quad>_<quarter>_<zone>_<res>_<flown>[_<made>]: the first date is the day flown
        m = re.match(r"^[a-z]{2}_m_\d{7}_[nsNS][ewEW]_\d{2}_\d{2,3}_(\d{8})(_\d{8})?$", item)
        if not m or when.strftime("%Y%m%d") != m.group(1):
            wrong.append(item)
    return {"passed": not wrong, "wrong": failure_list(wrong)}


def geo_without_crs(table):
    """The release's geo metadata less its crs, which r5 writes out and the hosted files leave implicit."""
    geo = json.loads(table.schema.metadata[b"geo"])
    geo["columns"]["geometry"].pop("crs", None)
    return geo


GTI_LOCATION = "naip:gti_location"
NO_CHANGES = {"added_columns": [], "collection_fields": {}}


def stac_meta(table):
    return json.loads(table.schema.metadata[b"stac-geoparquet"])


def compare_meta(release, hosted, collection, first_date, changes=NO_CHANGES):
    """Collection records equal except the temporal extent, whose first date must be first_date,
    and the fields the changes give new values."""
    a, b = stac_meta(release), stac_meta(hosted)
    b["collections"][collection].update(changes["collection_fields"].get(collection, {}))
    ta = a["collections"][collection]["extent"]["temporal"]["interval"]
    tb = b["collections"][collection]["extent"]["temporal"]["interval"]
    a2, b2 = copy.deepcopy(a), copy.deepcopy(b)
    for m in (a2, b2):
        m["collections"][collection]["extent"]["temporal"] = None
    return {"rest_equal": a2 == b2, "release_interval": ta, "hosted_interval": tb,
            "first_date_is_earliest_row": ta[0][0][:10] == first_date,
            "geo_equal": geo_without_crs(release) == json.loads(hosted.schema.metadata[b"geo"]),
            "crs_is_crs84": json.loads(release.schema.metadata[b"geo"])["columns"]["geometry"].get("crs", {}).get("id") == {"authority": "OGC", "code": "CRS84"}}


def without_added(table, changes):
    keep = [n for n in table.column_names if n not in changes["added_columns"]]
    return table.select(keep)


def check_quad_values(release, hosted, changes=NO_CHANGES):
    meta = compare_meta(release, hosted, "naip", min(release.column("datetime").to_pylist()).strftime("%Y-%m-%d"), changes)
    added_present = all(n in release.column_names and n not in hosted.column_names for n in changes["added_columns"])
    release = without_added(release, changes)
    schema_equal = added_present and release.schema.remove_metadata() == hosted.schema.remove_metadata()
    differing = [n for n in release.column_names if n not in hosted.column_names or not release.column(n).equals(hosted.column(n))]
    passed = schema_equal and release.num_rows == hosted.num_rows and not differing and meta["rest_equal"] and meta["first_date_is_earliest_row"] and meta["geo_equal"] and meta["crs_is_crs84"]
    return {"passed": passed, "rows": [release.num_rows, hosted.num_rows], "schema_equal": schema_equal, "columns_differing": differing, "metadata": meta}


def check_overview_values(release, hosted, quads, results, changes=NO_CHANGES):
    first = min(release.column("start_datetime").to_pylist()[i] or release.column("datetime").to_pylist()[i] for i in range(release.num_rows))
    meta = compare_meta(release, hosted, "naip-overviews", first.strftime("%Y-%m-%d"), changes)
    added_present = all(n in release.column_names and n not in hosted.column_names for n in changes["added_columns"])
    release = without_added(release, changes)
    same_ids = added_present and release.column("id").to_pylist() == hosted.column("id").to_pylist()
    differing = [n for n in release.column_names if n != "geometry" and (n not in hosted.column_names or not release.column(n).equals(hosted.column(n)))]
    # outline covers its quads
    by_group = collections.defaultdict(list)
    for state, year, epsg, wkb in zip(*(quads.column(n).to_pylist() for n in ("naip:state", "naip:year", "proj:epsg", "geometry"))):
        by_group[(state, year, epsg)].append(wkb)
    uncovered, distances = {}, {}
    hosted_geom = dict(zip(hosted.column("id").to_pylist(), hosted.column("geometry").to_pylist()))
    for item, wkb in zip(release.column("id").to_pylist(), release.column("geometry").to_pylist()):
        result = results.get(item)
        if not result or "zones" not in result:
            continue
        state, year = item.split("-")[0], int(item.split("-")[1])
        outline = edges_of(wkb_polygons(wkb))
        bad = 0
        for zone in result["zones"]:
            for q in by_group.get((state, year, int(zone)), []):
                if not covers(outline, wkb_polygons(q)[0][0], TOL_COVER):
                    bad += 1
        if bad:
            uncovered[item] = bad
        if item in hosted_geom:
            other = edges_of(wkb_polygons(hosted_geom[item]))
            pts_a = np.vstack([outline[:, 0:2]])
            pts_b = np.vstack([other[:, 0:2]])
            step_a, step_b = max(1, len(pts_a) // 2000), max(1, len(pts_b) // 2000)
            d = max(point_segment_distance(pts_a[::step_a], other).max(), point_segment_distance(pts_b[::step_b], outline).max())
            distances[item] = round(float(d), 9)
    passed = same_ids and not differing and meta["rest_equal"] and meta["first_date_is_earliest_row"] and meta["geo_equal"] and meta["crs_is_crs84"] and not uncovered
    return {"passed": passed, "same_ids_same_order": same_ids, "columns_differing_except_geometry": differing, "metadata": meta,
            "outlines_not_covering_quads": uncovered,
            "outline_distance_to_hosted_degrees_reported": {"max": max(distances.values(), default=0), "by_item": distances,
                                                            "note": "sampled vertices, both directions; not passed or failed"}}


def check_overview_rows(overviews, quads, results, listed):
    ids = overviews.column("id").to_pylist()
    want = {name for name, r in results.items() if "zones" in r and (name.split("-")[0], int(name.split("-")[1])) in listed}
    have = {i for i in ids if i != "national-latest"}
    unlisted_rows = [i for i in have if (i.split("-")[0], int(i.split("-")[1])) not in listed]
    national = [r for r in overviews.to_pylist() if r["id"] == "national-latest"]
    national_ok = len(national) == 1 and national[0]["naip:quads"] == quads.num_rows
    return {"passed": have == want and not unlisted_rows and national_ok, "state_rows": len(have), "expected_state_rows": len(want),
            "missing": failure_list(want - have), "extra": failure_list(have - want), "rows_of_unlisted_years": failure_list(unlisted_rows),
            "national_quads": national[0]["naip:quads"] if national else None, "quad_rows": quads.num_rows}


def check_gti_locations(table):
    """Each row's naip:gti_location, taken from stac/, is the file its href names."""
    if GTI_LOCATION not in table.column_names:
        return {"passed": False, "reason": f"no {GTI_LOCATION} column"}
    base = FILES + "stac/"
    wrong = []
    for a, location in zip(table.column("assets").to_pylist(), table.column(GTI_LOCATION).to_pylist()):
        href = a["image"]["href"]
        if not location or "://" in location or location.startswith("/") or urllib.parse.urljoin(base, location) != href:
            wrong.append(f"{href} <- {location}")
    return {"passed": not wrong, "rows": table.num_rows, "wrong": failure_list(wrong)}


def check_gti_files(release_dir):
    """naip.gti opens naip.parquet with the location column, and its overview levels open
    naip-overviews.gti, which opens naip-overviews.parquet the same way; all four sit side by side."""
    found, problems = {}, []
    for name, index in (("naip.gti", "naip.parquet"), ("naip-overviews.gti", "naip-overviews.parquet")):
        path = os.path.join(release_dir, name)
        if not os.path.exists(path):
            problems.append(f"{name} missing")
            continue
        root = ET.parse(path).getroot()
        found[name] = {"sha256": sha256(path), "index": root.findtext("IndexDataset"), "location_field": root.findtext("LocationField"),
                       "overviews": [o.findtext("Dataset") for o in root.findall("Overview") if o.findtext("Dataset")]}
        if root.tag != "GDALTileIndexDataset":
            problems.append(f"{name}: root is {root.tag}")
        if found[name]["index"] != index:
            problems.append(f"{name}: index {found[name]['index']}")
        if found[name]["location_field"] != GTI_LOCATION:
            problems.append(f"{name}: location field {found[name]['location_field']}")
        if [b.findtext("ColorInterp") for b in root.findall("Band")] != ["Red", "Green", "Blue", "Alpha"]:
            problems.append(f"{name}: bands are not red, green, blue and alpha")
    if "naip.gti" in found and (not found["naip.gti"]["overviews"] or set(found["naip.gti"]["overviews"]) != {"naip-overviews.gti"}):
        problems.append("naip.gti: overview levels do not all open naip-overviews.gti")
    return {"passed": not problems, "files": found, "problems": problems}


def quad_checks(table, hosted, expected, left_hrefs, changes=NO_CHANGES):
    """The checks a changed quad index must fail (used by the fault tests)."""
    out = {"1b": check_quad_values(table, hosted, changes)["passed"], "3": check_accounting(table, expected, left_hrefs)["passed"],
           "4": check_size_checksum(table, expected)["passed"], "6": check_footprints(table, corners=True)["passed"],
           "7": check_dates(table)["passed"]}
    if GTI_LOCATION in changes["added_columns"]:
        out["11"] = check_gti_locations(table)["passed"]
    return out


def fault_tests(table, hosted, expected, left_hrefs, left_receipt, changes=NO_CHANGES):
    rows = table.to_pylist()
    schema = table.schema

    def rebuilt(rs):
        return pa.Table.from_pylist(rs, schema=schema)

    def change(i, fn):
        rs = copy.deepcopy(rows[i:i + 1])
        fn(rs[0])
        return rebuilt(rows[:i] + rs + rows[i + 1:])

    i = len(rows) // 2

    def footprint_byte(r):
        g = bytearray(r["geometry"])
        g[-3] ^= 0x01
        r["geometry"] = bytes(g)

    def add_back(r):
        r["assets"]["image"]["href"] = left_receipt["href"]
        r["assets"]["image"]["file:size"] = left_receipt["size"]
        r["assets"]["image"]["file:checksum"] = "1220" + left_receipt["sha256"]

    cases = [
        ("a row removed", rebuilt(rows[:i] + rows[i + 1:]), "3"),
        ("a row duplicated", rebuilt(rows[:i + 1] + rows[i:]), "3"),
        ("a size changed", change(i, lambda r: r["assets"]["image"].__setitem__("file:size", r["assets"]["image"]["file:size"] + 1)), "4"),
        ("a checksum changed", change(i, lambda r: r["assets"]["image"].__setitem__("file:checksum", r["assets"]["image"]["file:checksum"][:-1] + ("0" if r["assets"]["image"]["file:checksum"][-1] != "0" else "1"))), "4"),
        ("an address changed", change(i, lambda r: r["assets"]["image"].__setitem__("href", r["assets"]["image"]["href"].replace(".tif", "_x.tif"))), "3"),
        ("a bbox value changed", change(i, lambda r: r["bbox"].__setitem__("xmin", r["bbox"]["xmin"] - 1e-6)), "6"),
        ("a footprint byte changed", change(i, footprint_byte), "6"),
        ("a datetime changed", change(i, lambda r: r.__setitem__("datetime", r["datetime"].replace(day=1 if r["datetime"].day != 1 else 2))), "7"),
        ("rows of a left-out year added back", rebuilt(rows + [add_back(r) or r for r in [copy.deepcopy(rows[i])]]), "3"),
    ]
    if GTI_LOCATION in changes["added_columns"]:
        cases += [
            ("a gti location pointing at another file", change(i, lambda r: r.__setitem__(GTI_LOCATION, rows[i + 1][GTI_LOCATION])), "11"),
            ("a gti location made absolute", change(i, lambda r: r.__setitem__(GTI_LOCATION, r["assets"]["image"]["href"])), "11"),
        ]
    out = []
    for name, changed, reason in cases:
        result = quad_checks(changed, hosted, expected, left_hrefs, changes)
        out.append({"change": name, "expected_failing_check": reason, "checks_passed": result,
                    "rejected_for_stated_reason": result[reason] is False})
    return {"passed": all(c["rejected_for_stated_reason"] for c in out), "cases": out}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    lister = sub.add_parser("list")
    lister.add_argument("--out", required=True)
    checker = sub.add_parser("check")
    for name in ("release", "hosted", "artifacts", "listing", "out"):
        checker.add_argument("--" + name, required=True)
    checker.add_argument("--changes", help="JSON of the differences from the hosted files this release is meant to have")
    args = parser.parse_args()
    if os.path.exists(args.out):
        sys.exit("Use a new output path; earlier results are kept.")
    if args.command == "list":
        make_listing(args.out)
        return

    changes = NO_CHANGES
    if args.changes:
        with open(args.changes) as f:
            changes = {**NO_CHANGES, **json.load(f)}
    paths = {name: os.path.join(args.release, name) for name in ("naip.parquet", "naip-overviews.parquet")}
    hosted_paths = {name: os.path.join(args.hosted, name) for name in paths}
    read = lambda p: pq.read_table(p)
    quads, overviews = read(paths["naip.parquet"]), read(paths["naip-overviews.parquet"])
    hosted_quads, hosted_overviews = read(hosted_paths["naip.parquet"]), read(hosted_paths["naip-overviews.parquet"])
    with open(args.listing) as f:
        listing_doc = json.load(f)
    listing = listing_doc["files"]

    all_receipts = receipts(args.artifacts)
    listed, left, counts = listed_years(all_receipts)
    expected = {r["href"]: r for r in all_receipts if (r["state"], r["year"]) in listed}
    left_receipts = [r for r in all_receipts if (r["state"], r["year"]) in left]
    left_hrefs = {r["href"] for r in left_receipts}
    results = {}
    for path in sorted(glob.glob(os.path.join(args.artifacts, OVERVIEW_RESULTS))):
        with open(path) as f:
            r = json.load(f)
        results[r["name"]] = r

    checks = {
        "1b_quad_values_equal_hosted": check_quad_values(quads, hosted_quads, changes),
        "1c_overview_values_equal_hosted": check_overview_values(overviews, hosted_overviews, quads, results, changes),
        "3_accounting_against_receipts": check_accounting(quads, expected, left_hrefs),
        "4_size_and_checksum": check_size_checksum(quads, expected),
        "5_hosted_listing": {"quads": check_listing(quads, listing, "quads"), "overviews": check_listing(overviews, listing, "overviews")},
        "6_footprint": {"quads": check_footprints(quads, corners=True), "overviews": check_footprints(overviews, corners=False)},
        "7_flight_date": check_dates(quads),
        "8_overview_index": check_overview_rows(overviews, quads, results, listed),
        "9_fault_tests": fault_tests(quads, hosted_quads, expected, left_hrefs, left_receipts[0], changes),
    }
    if GTI_LOCATION in changes["added_columns"]:
        checks["11_gti"] = {"quads": check_gti_locations(quads), "overviews": check_gti_locations(overviews),
                            "files": check_gti_files(args.release)}
    for key in ("5_hosted_listing", "6_footprint", "11_gti"):
        if key not in checks:
            continue
        checks[key]["passed"] = all(v["passed"] for v in checks[key].values() if isinstance(v, dict))
    report = {
        "schema_version": 1,
        "plan": "datasets/naip/index-package-plan.md",
        "changes": changes,
        "release_files": {name: {"sha256": sha256(p), "size_bytes": os.path.getsize(p)} for name, p in paths.items()},
        "hosted_files": {name: {"sha256": sha256(p), "size_bytes": os.path.getsize(p)} for name, p in hosted_paths.items()},
        "listing": {"sha256": sha256(args.listing), "files": len(listing), "pages": listing_doc["pages"], "listed_from": listing_doc["listed_from"]},
        "receipts": len(all_receipts),
        "listed_state_years": len(listed),
        "left_out_state_years": {f"{s}-{y}": counts[s, y] for s, y in sorted(left)},
        "checks": checks,
        "status": "passed" if all(c["passed"] for c in checks.values()) else "failed",
    }
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1, default=str)
        f.write("\n")
    print(json.dumps({k: v["passed"] for k, v in checks.items()}, indent=1), report["status"])
    sys.exit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
