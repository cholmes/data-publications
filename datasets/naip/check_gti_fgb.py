#!/usr/bin/env python3
"""Check the FlatGeobuf tile index pair against the index release it was built from.

    python check_gti_fgb.py <release dir: naip.parquet, naip-overviews.parquet> <dir with the two .gti.fgb>
        [--base https://data.source.coop/nthh/naip/] [--index-dir stac]

Reads the FlatGeobuf files back with GDAL and recomputes the expected rows a second way (an Arrow sort
and group, not the builder's loop):

1. naip.gti.fgb has one row per 0.0625-degree cell that holds the centre of any quad footprint, and no
   other rows; each footprint is exactly its cell, so no two rows overlap.
2. Each row's file is the newest of its cell: latest `datetime`, then greatest `id`; its `datetime`
   equals that file's.
3. Every address is absolute, `/vsicurl?empty_dir=yes&url=<base><path>`, and names the file the
   release's `href` names.
4. naip-overviews.gti.fgb has every overview file once, its bbox as the footprint, and the same address
   rule; its `id` values are those the overview levels filter on.
5. The GTI settings in the layer metadata: location and sort fields, resolution, extent, four Byte bands,
   and in naip.gti.fgb the 13 overview levels listed in LEVELS below (three factors, five levels of the
   state files and five of the national file), each dataset an absolute `GTI:` address of the overview
   index.

Prints a JSON report; exits 1 if any check fails.
"""
import argparse
import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from osgeo import gdal, ogr

gdal.UseExceptions()
CELL = 0.0625
PUBLISHED = "https://data.source.coop/nthh/naip/"
STATES, NATIONAL = "id <> 'national-latest'", "id = 'national-latest'"
# naip.gti.fgb's overview levels in order: (factor, overview filter, resolution in degrees).
LEVELS = [("2", None, None), ("4", None, None), ("8", None, None),
          (None, STATES, "0.00008"), (None, STATES, "0.00016"), (None, STATES, "0.00032"),
          (None, STATES, "0.00064"), (None, STATES, "0.00128"),
          (None, NATIONAL, "0.00256"), (None, NATIONAL, "0.00512"), (None, NATIONAL, "0.01024"),
          (None, NATIONAL, "0.02048"), (None, NATIONAL, "0.04096")]


def fgb_rows(path):
    ds = gdal.OpenEx(str(path), gdal.OF_VECTOR)
    layer = ds.GetLayer(0)
    meta = layer.GetMetadata()
    names = [layer.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(layer.GetLayerDefn().GetFieldCount())]
    rows = []
    for feature in layer:
        geometry = feature.GetGeometryRef()
        rows.append({**{n: feature.GetFieldAsString(n) for n in names},
                     "envelope": geometry.GetEnvelope(), "points": geometry.GetGeometryRef(0).GetPointCount(),
                     "area": geometry.GetArea()})
    return meta, names, rows


def release_table(path):
    with open(path, "rb") as f:
        table = pq.ParquetFile(f).read(columns=["id", "datetime", "bbox", "assets"])
    bbox = table["bbox"]
    return pa.table({
        "id": table["id"],
        "datetime": table["datetime"],
        "stamp": pc.strftime(pc.cast(table["datetime"], pa.timestamp("s", "UTC")), "%Y/%m/%d %H:%M:%S+00"),
        "href": pc.struct_field(pc.struct_field(table["assets"], "image"), "href"),
        "cx": pc.floor(pc.divide(pc.divide(pc.add(pc.struct_field(bbox, "xmin"), pc.struct_field(bbox, "xmax")), 2), CELL)),
        "cy": pc.floor(pc.divide(pc.divide(pc.add(pc.struct_field(bbox, "ymin"), pc.struct_field(bbox, "ymax")), 2), CELL)),
        "xmin": pc.struct_field(bbox, "xmin"), "ymin": pc.struct_field(bbox, "ymin"),
        "xmax": pc.struct_field(bbox, "xmax"), "ymax": pc.struct_field(bbox, "ymax"),
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("fgb_dir", type=Path)
    parser.add_argument("--base", default=PUBLISHED)
    parser.add_argument("--index-dir", default="stac")
    args = parser.parse_args()
    prefix = "/vsicurl?empty_dir=yes&url=" + args.base

    def expected_location(href):
        assert href.startswith(PUBLISHED), href
        return prefix + href[len(PUBLISHED):]

    failures, report = [], {}

    def check(name, ok, detail=None):
        report[name] = {"ok": bool(ok), **({"detail": detail} if detail is not None else {})}
        if not ok:
            failures.append(name)

    # 1-3: quads
    quads = release_table(args.release_dir / "naip.parquet")
    order = pc.sort_indices(quads, [("cx", "ascending"), ("cy", "ascending"), ("datetime", "descending"), ("id", "descending")])
    ranked = quads.take(order)
    cx, cy = ranked["cx"].to_pylist(), ranked["cy"].to_pylist()
    first = [i for i in range(len(cx)) if i == 0 or (cx[i], cy[i]) != (cx[i - 1], cy[i - 1])]
    newest = ranked.take(pa.array(first))
    expected = {(int(x), int(y)): (s, expected_location(h)) for x, y, s, h in
                zip(newest["cx"].to_pylist(), newest["cy"].to_pylist(), newest["stamp"].to_pylist(), newest["href"].to_pylist())}

    meta, names, rows = fgb_rows(args.fgb_dir / "naip.gti.fgb")
    location_field = meta.get("LOCATION_FIELD")
    got = {}
    bad_footprints = 0
    for row in rows:
        x0, x1, y0, y1 = row["envelope"]
        i, j = round(x0 / CELL), round(y0 / CELL)
        exact = (row["points"] == 5 and abs(x0 - i * CELL) < 1e-9 and abs(y0 - j * CELL) < 1e-9
                 and abs(x1 - (i + 1) * CELL) < 1e-9 and abs(y1 - (j + 1) * CELL) < 1e-9
                 and abs(row["area"] - CELL * CELL) < 1e-12)
        bad_footprints += not exact
        got.setdefault((i, j), []).append((row["datetime"], row[location_field]))
    report["quad_rows_in_release"] = quads.num_rows
    report["cells_expected"] = len(expected)
    report["rows"] = len(rows)
    check("one_row_per_cell", len(rows) == len(expected) and set(got) == set(expected) and all(len(v) == 1 for v in got.values()),
          {"rows": len(rows), "cells": len(expected), "missing": len(set(expected) - set(got)), "extra": len(set(got) - set(expected)),
           "duplicated": sum(len(v) > 1 for v in got.values())})
    check("footprint_is_the_cell", bad_footprints == 0, {"not_a_cell": bad_footprints})
    wrong = [(k, got[k][0], expected[k]) for k in expected if k in got and got[k][0] != expected[k]]
    check("newest_file_of_each_cell", not wrong, {"wrong": len(wrong), "examples": [str(w) for w in wrong[:3]]})
    check("addresses_absolute", all(r[location_field].startswith(prefix) and r[location_field].endswith(".tif") for r in rows))
    report["quad_fields"] = names
    report["quad_rows_left_out"] = quads.num_rows - len(rows)

    # 4: overviews
    overviews = release_table(args.release_dir / "naip-overviews.parquet")
    o_meta, o_names, o_rows = fgb_rows(args.fgb_dir / "naip-overviews.gti.fgb")
    want = {i: (s, expected_location(h), (x0, x1, y0, y1)) for i, s, h, x0, x1, y0, y1 in zip(
        *(overviews[c].to_pylist() for c in ("id", "stamp", "href", "xmin", "xmax", "ymin", "ymax")))}
    have = {r["id"]: (r["datetime"], r[o_meta.get("LOCATION_FIELD")], r["envelope"]) for r in o_rows}
    check("overviews_every_file_once", len(o_rows) == len(want) and set(have) == set(want),
          {"rows": len(o_rows), "release": len(want)})
    check("overviews_newest_and_address",
          all(have[k][:2] == want[k][:2] for k in want if k in have))
    check("overviews_footprint_is_bbox",
          all(max(abs(a - b) for a, b in zip(have[k][2], want[k][2])) < 1e-9 for k in want if k in have))
    check("overview_ids_used_by_filters", "national-latest" in have and "id" in o_names)

    # 5: settings
    base_keys = {"LOCATION_FIELD": "naip:gti_location", "SORT_FIELD": "datetime", "SORT_FIELD_ASC": "YES",
                 "BAND_COUNT": "4", "DATA_TYPE": "Byte", "COLOR_INTERPRETATION": "red,green,blue,alpha",
                 "MINX": "-125.2", "MINY": "23.2", "MAXX": "-66.0", "MAXY": "49.92"}
    check("quad_settings", all(meta.get(k) == v for k, v in base_keys.items())
          and meta.get("RESX") == "0.000005" == meta.get("RESY"), {k: meta.get(k) for k in base_keys})
    check("overview_settings", all(o_meta.get(k) == v for k, v in base_keys.items())
          and o_meta.get("RESX") == "0.00008" == o_meta.get("RESY"))
    dataset = "GTI:" + prefix + args.index_dir.strip("/") + "/naip-overviews.gti.fgb"
    levels = LEVELS
    level_ok = []
    for n, (factor, where, res) in enumerate(levels):
        if factor:
            level_ok.append(meta.get(f"OVERVIEW_{n}_FACTOR") == factor)
        else:
            options = f"FILTER={where},RESX={res},RESY={res}"
            level_ok.append(meta.get(f"OVERVIEW_{n}_DATASET") == dataset and meta.get(f"OVERVIEW_{n}_OPEN_OPTIONS") == options)
    check("overview_levels", all(level_ok) and f"OVERVIEW_{len(levels)}_DATASET" not in meta
          and f"OVERVIEW_{len(levels)}_FACTOR" not in meta, {"levels": len(levels), "matching": sum(level_ok)})

    report["files"] = {p.name: p.stat().st_size for p in sorted(args.fgb_dir.glob("*.gti.fgb"))}
    report["failures"] = failures
    print(json.dumps(report, indent=1))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
