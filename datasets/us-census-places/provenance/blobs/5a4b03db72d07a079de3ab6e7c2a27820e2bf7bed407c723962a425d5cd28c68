"""Check a display package against the released GeoParquet, by reading the archive itself.

    uv run --locked --project scripts/display_tools python datasets/us-census-places/validate_display.py \
        --display DIR --package PACKAGED_RELEASE --report NEW_FILE [--same-as OTHER_DISPLAY_DIR]

Separate from build_display.py: it derives what each layer should hold with its own code and decodes
the tiles with mapbox-vector-tile. Checks 1 to 8 of display-plan.md; check 9 (browser) is separate.
Every check is run and recorded even after one fails. Exits 1 unless all pass.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import mapbox_vector_tile
import pyarrow.parquet as pq
import shapely
from pmtiles.reader import MmapSource, Reader, all_tiles
from shapely.geometry import box, shape
from shapely.ops import transform, unary_union

MAX_ZOOM, EXTENT = 11, 4096
HALF = 20037508.342789244
LAYERS = {"census_counties": "counties", "census_places": "places", "census_towns": "county-subdivisions"}
KINDS = ["county", "incorporated", "unincorporated", "township"]
STATES = ["CO", "TX", "OH", "CA", "GA", "PA"]
COUNTIES = {"08013": "Boulder CO", "48453": "Travis TX", "39049": "Franklin OH", "06037": "Los Angeles CA",
            "13121": "Fulton GA", "42003": "Allegheny PA", "19153": "Polk IA", "31031": "Cherry NE"}
WIDTH, HEIGHT, PADDING = 1440, 900, 24
STATE_LIMIT, COUNTY_LIMIT, DISTANCE_LIMIT, AREA_LIMIT, SAMPLE, SAMPLE_TILES = 600_000, 400_000, 30.0, 0.01, 32, 16


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def merc_y(lat: float) -> float:
    return math.log(math.tan(math.pi / 4 + lat * math.pi / 360))


def to_mercator(geometry):
    return transform(lambda x, y: (tuple(v * HALF / 180 for v in x), tuple(merc_y(v) * HALF / math.pi for v in y)), geometry)


def tile_xy(lng: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2 ** zoom
    return int((lng + 180) / 360 * n), int((1 - merc_y(lat) / math.pi) / 2 * n)


def expected(package: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """layer -> GEOID -> the properties and source geometry the tiles should carry."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for layer, asset in LAYERS.items():
        table = pq.read_table(package / "assets" / f"{asset}.parquet")
        rows = {}
        for i in range(table.num_rows):
            status = table["gaz_funcstat"][i].as_py()
            if layer == "census_towns" and status != "A":
                continue
            kind = {"census_counties": "county", "census_towns": "township"}.get(layer) or (
                "incorporated" if status == "A" else "unincorporated")
            bounds = table["bbox"][i].as_py()
            geoid = table["GEOID"][i].as_py()
            if geoid in rows:
                raise ValueError(f"{layer}: GEOID {geoid} occurs twice in the release")
            rows[geoid] = {"name": table["NAME"][i].as_py(), "state": table["STUSPS"][i].as_py(), "kind": kind,
                           "population": table["popest_2023"][i].as_py(),
                           "area": round(table["ALAND"][i].as_py() / 1e6, 2),
                           "bounds": [bounds[k] for k in ("xmin", "ymin", "xmax", "ymax")],
                           "wkb": table["geometry"][i].as_py()}
        out[layer] = rows
    return out


def close(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(b, str) or isinstance(a, str):
        return a == b
    return abs(float(a) - float(b)) <= 1e-6


def view_of(bounds: list[float]) -> tuple[float, tuple[float, float, float, float]]:
    west, south, east, north = bounds
    zoom = math.log2(min((WIDTH - 2 * PADDING) / (512 * (east - west) / 360),
                         (HEIGHT - 2 * PADDING) / (512 * (merc_y(north) - merc_y(south)) / (2 * math.pi))))
    lng, y = (west + east) / 2, (merc_y(north) + merc_y(south)) / 2
    half_lng, half_y = WIDTH / 2 / (512 * 2 ** zoom) * 360, HEIGHT / 2 / (512 * 2 ** zoom) * 2 * math.pi
    lat = lambda v: (2 * math.atan(math.exp(v)) - math.pi / 2) * 180 / math.pi
    return zoom, (lng - half_lng, lat(y - half_y), lng + half_lng, lat(y + half_y))


def validate(display: Path, package: Path, same_as: Path | None) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    manifest = json.loads((display / "manifest.json").read_text())
    release = {a["asset_id"]: a["sha256"] for a in json.loads((package / "manifest.json").read_text())["assets"]}
    actual = {asset: sha256(package / "assets" / f"{asset}.parquet") for asset in LAYERS.values()}
    checks["1_inputs"] = {"passed": all(release.get(a) == h for a, h in actual.items()), "sha256": actual}
    want = expected(package)
    archives = {layer: display / "assets" / f"{layer}.pmtiles" for layer in LAYERS}
    archive_sha = {layer: sha256(path) for layer, path in archives.items()}

    samples: dict[str, list[str]] = {}
    for layer, rows in want.items():
        chosen = []
        for geoid in sorted(rows):
            west, south, east, north = rows[geoid]["bounds"]
            x0, y0 = tile_xy(west, north, MAX_ZOOM)
            x1, y1 = tile_xy(east, south, MAX_ZOOM)
            if (x1 - x0 + 1) * (y1 - y0 + 1) <= SAMPLE_TILES:
                chosen.append(geoid)
            if len(chosen) == SAMPLE:
                break
        samples[layer] = chosen
    wanted = {layer: set(ids) for layer, ids in samples.items()}

    seen: dict[str, set[str]] = {layer: set() for layer in want}
    label_points: dict[str, dict[str, list[tuple[float, float]]]] = {layer: {} for layer in want}
    pieces: dict[str, dict[str, list[Any]]] = {layer: {} for layer in want}
    wrong: list[str] = []
    unknown: dict[str, set[str]] = {layer: set() for layer in want}
    sizes: dict[str, dict[tuple[int, int, int], int]] = {layer: {} for layer in want}
    inside_labels: dict[str, dict[str, int]] = {layer: {} for layer in want}
    for archive_layer, archive in archives.items():
      with archive.open("rb") as stream:
        source = MmapSource(stream)
        for (z, x, y), data in all_tiles(source):
            sizes[archive_layer][(z, x, y)] = len(data)
            if z != MAX_ZOOM:
                continue
            tile = mapbox_vector_tile.decode(gzip.decompress(data))
            size = 2 * HALF / 2 ** z
            left, bottom = -HALF + x * size, HALF - (y + 1) * size
            place = lambda px, py: (left + px / EXTENT * size, bottom + py / EXTENT * size)
            core = box(left, bottom, left + size, bottom + size)
            for layer, rows in ((archive_layer, want[archive_layer]),):
                for feature in tile.get(layer, {}).get("features", []):
                    p = feature["properties"]
                    geoid = p.get("id")
                    row = rows.get(geoid)
                    if row is None:
                        unknown[layer].add(str(geoid))
                        continue
                    seen[layer].add(geoid)
                    got = [p.get("name"), p.get("state"), p.get("kind"), p.get("population"),
                           p.get("xmin"), p.get("ymin"), p.get("xmax"), p.get("ymax")]
                    if not all(close(a, b) for a, b in zip(got, [row["name"], row["state"], row["kind"], row["population"], *row["bounds"]])):
                        if len(wrong) < 20:
                            wrong.append(f"{layer} {geoid}: {got}")
                    if geoid in wanted[layer]:
                        fragment = transform(lambda px, py: tuple(zip(*[place(a, b) for a, b in zip(px, py)])), shape(feature["geometry"]))
                        pieces[layer].setdefault(geoid, []).append(shapely.make_valid(fragment).intersection(core))
                for feature in tile.get(f"{layer}_label", {}).get("features", []):
                    p = feature["properties"]
                    geoid = p.get("id")
                    row = rows.get(geoid)
                    if row is None:
                        unknown[layer].add(f"label {geoid}")
                        continue
                    got = [p.get("name"), p.get("kind"), p.get("population"), p.get("area")]
                    if not all(close(a, b) for a, b in zip(got, [row["name"], row["kind"], row["population"], row["area"]])):
                        if len(wrong) < 20:
                            wrong.append(f"{layer}_label {geoid}: {got}")
                    px, py = feature["geometry"]["coordinates"]
                    label_points[layer].setdefault(geoid, []).append(place(px, py))
                    if 0 <= px < EXTENT and 0 <= py < EXTENT:
                        inside_labels[layer][geoid] = inside_labels[layer].get(geoid, 0) + 1

    accounting = {layer: {"expected": len(rows), "found": len(seen[layer]), "missing": sorted(set(rows) - seen[layer])[:20],
                          "missing_count": len(set(rows) - seen[layer]), "unexpected": sorted(unknown[layer])[:20],
                          "labels_expected": len(rows), "labels_found": len(label_points[layer]),
                          "labels_with_copies_in_tile_margins": sum(1 for g in rows if len(label_points[layer].get(g, [])) > 1),
                          "labels_not_exactly_one": sum(1 for g in rows if inside_labels[layer].get(g, 0) != 1)}
                  for layer, rows in want.items()}
    checks["2_accounting"] = {"passed": all(a["missing_count"] == 0 and not a["unexpected"] and a["labels_not_exactly_one"] == 0
                                             for a in accounting.values()), "layers": accounting}
    checks["3_attributes"] = {"passed": not wrong, "first_differences": wrong}

    far, worst = [], 0.0
    for layer, rows in want.items():
        for geoid, points in label_points[layer].items():
            outline = to_mercator(shapely.from_wkb(rows[geoid]["wkb"]))
            distance = max(outline.distance(shapely.Point(pt)) for pt in points)
            worst = max(worst, distance)
            if distance > DISTANCE_LIMIT and len(far) < 20:
                far.append(f"{layer} {geoid}: {distance:.1f} m")
    checks["4_label_position"] = {"passed": not far, "limit_m": DISTANCE_LIMIT, "worst_m": round(worst, 2), "first_over": far}

    geometry = {}
    for layer, ids in samples.items():
        drawn, differs, both = {}, {}, {}
        for geoid in ids:
            rebuilt = unary_union(pieces[layer].get(geoid, [])).buffer(1).buffer(-1)
            outline = shapely.make_valid(to_mercator(shapely.from_wkb(want[layer][geoid]["wkb"])))
            if rebuilt.is_empty:
                drawn[geoid] = differs[geoid] = both[geoid] = float("inf")
                continue
            points = shapely.points(shapely.get_coordinates(shapely.segmentize(rebuilt.boundary, 25)))
            drawn[geoid] = round(float(shapely.distance(points, outline.boundary).max()), 2)
            differs[geoid] = round(outline.symmetric_difference(rebuilt).area / outline.area, 5)
            both[geoid] = round(shapely.hausdorff_distance(outline.boundary, rebuilt.boundary, densify=0.25), 2)
        geometry[layer] = {"sampled": len(ids), "worst_drawn_line_to_source_m": max(drawn.values()),
                           "worst_area_difference": max(differs.values()),
                           "failed": sorted(g for g in ids if drawn[g] > DISTANCE_LIMIT or differs[g] > AREA_LIMIT),
                           "two_sided_over_limit_reported_only": {g: d for g, d in both.items() if d > DISTANCE_LIMIT}}
    checks["5_geometry_sample"] = {"passed": all(g["sampled"] == SAMPLE and not g["failed"] for g in geometry.values()),
                                   "limit_m": DISTANCE_LIMIT, "area_limit": AREA_LIMIT,
                                   "note": "Pieces are clipped to their tile, joined, and closed by 1 m to remove tile seams.",
                                   "layers": geometry}

    def read(bounds: list[float], layers: list[str]) -> dict[str, Any]:
        zoom, view = view_of(bounds)
        tiles = total = 0
        for layer in layers:
            z = max(min(k[0] for k in sizes[layer]), min(MAX_ZOOM, math.floor(zoom)))
            x0, y0 = tile_xy(view[0], view[3], z)
            x1, y1 = tile_xy(view[2], view[1], z)
            found = [sizes[layer][(z, x, y)] for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) if (z, x, y) in sizes[layer]]
            tiles, total = tiles + len(found), total + sum(found)
        return {"zoom": round(zoom, 2), "archives": layers, "tiles": tiles, "bytes": total}

    county_bounds = {g: r["bounds"] for g, r in want["census_counties"].items()}
    state_bounds: dict[str, list[float]] = {}
    for row in want["census_counties"].values():
        b = state_bounds.setdefault(row["state"], list(row["bounds"]))
        b[0], b[1], b[2], b[3] = min(b[0], row["bounds"][0]), min(b[1], row["bounds"][1]), max(b[2], row["bounds"][2]), max(b[3], row["bounds"][3])
    state_views = {s: read(state_bounds[s], ["census_counties"]) for s in STATES}
    county_views = {name: read(county_bounds[g], ["census_places", "census_towns"]) for g, name in COUNTIES.items()}
    checks["6_read_cost"] = {"passed": all(v["bytes"] <= STATE_LIMIT for v in state_views.values())
                             and all(v["bytes"] <= COUNTY_LIMIT for v in county_views.values()),
                             "state_limit_bytes": STATE_LIMIT, "county_limit_bytes": COUNTY_LIMIT,
                             "state_views": state_views, "county_views": county_views}

    index = json.loads((display / "assets" / "place-names.json").read_text())
    rows = [[r["name"], r["state"], KINDS.index(r["kind"]), r["population"], *(round(v, 3) for v in r["bounds"])]
            for layer in want for r in want[layer].values()]
    canonical = lambda items: sorted(json.dumps(item, ensure_ascii=False) for item in items)
    keys = [(r[3] is None, -(r[3] or 0)) for r in index["rows"]]
    checks["7_names_index"] = {"passed": canonical(index["rows"]) == canonical(rows) and keys == sorted(keys)
                               and index["kinds"] == KINDS, "rows": len(index["rows"]), "expected_rows": len(rows)}

    if same_as is None:
        checks["8_repeat_build"] = {"passed": False, "note": "No second build was given."}
    else:
        names_same = sha256(display / "assets" / "place-names.json") == sha256(same_as / "assets" / "place-names.json")
        checks["8_repeat_build"] = {"passed": names_same, "names_index_identical": names_same,
                                    "archives_identical": {layer: sha == sha256(same_as / "assets" / f"{layer}.pmtiles")
                                                           for layer, sha in archive_sha.items()},
                                    "note": "If the archive differs, the second archive needs its own passing report."}

    return {"schema_version": 1, "dataset_id": manifest["dataset_id"], "display_release": manifest["display_release"],
            "archives_sha256": archive_sha, "archive_bytes": {layer: path.stat().st_size for layer, path in archives.items()},
            "status": "passed" if all(c["passed"] for c in checks.values()) else "failed", "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--display", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--same-as", type=Path)
    args = parser.parse_args()
    if args.report.exists():
        raise SystemExit("Use a new report path; earlier reports are kept.")
    report = validate(args.display, args.package, args.same_as)
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({name: check["passed"] for name, check in report["checks"].items()}, indent=2))
    sys.exit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
