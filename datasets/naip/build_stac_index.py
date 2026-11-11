#!/usr/bin/env python3
"""Build a STAC-GeoParquet index of converted quads from one or more runs' receipts.

One row per file, as a STAC item: footprint in longitude and latitude, the date flown, the
file's own CRS and extent (projection extension), and one asset, `image`, with the file's
URL, size and checksum. Rows are sorted by state, year and quad so that a row group covers a
compact area and a reader can skip most of the file from the bbox statistics.

    uv run --no-project --with pyarrow==21.0.0 --with pyproj==3.7.2 \
        python build_stac_index.py <out.parquet> <receipts dir> [<receipts dir> ...] \
        [--base-url https://data.source.coop/nthh/naip/] [--row-group 512]
"""

import argparse
import datetime
import json
import os

import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import Transformer

from build_index import footprint, wkb_polygon

EXTENSIONS = [
    "https://stac-extensions.github.io/projection/v2.0.0/schema.json",
    "https://stac-extensions.github.io/file/v2.1.0/schema.json",
]


def item(receipt, base_url, transformers):
    key = receipt["out_uri"].split("/", 3)[3]
    # <state>/<year>/<res>/rgb/<block>/m_<quad>_<quarter>_<zone>_<res>_<yyyymmdd>.tif
    path = "/".join(key.split("/")[-6:])
    state, year, resolution, _, _, filename = path.split("/")
    flown = filename[:-4].rsplit("_", 1)[-1]
    ring, native = footprint(receipt, transformers)
    out = receipt["output"]
    sha = receipt.get("output_sha256")
    return {
        "type": "Feature",
        "stac_version": "1.1.0",
        "stac_extensions": EXTENSIONS,
        "id": receipt["id"],
        "collection": "naip",
        "geometry": wkb_polygon(ring),
        "bbox": {"xmin": min(p[0] for p in ring), "ymin": min(p[1] for p in ring),
                 "xmax": max(p[0] for p in ring), "ymax": max(p[1] for p in ring)},
        "datetime": datetime.datetime(int(flown[:4]), int(flown[4:6]), int(flown[6:]),
                                      tzinfo=datetime.timezone.utc),
        "gsd": int(resolution[:-2]) / 100,
        "naip:state": state,
        "naip:year": int(year),
        "proj:code": f"EPSG:{out['epsg']}",
        "proj:epsg": int(out["epsg"]),
        "proj:bbox": native,
        "proj:shape": [out["height"], out["width"]],
        "proj:transform": [out["geotransform"][i] for i in (1, 2, 0, 4, 5, 3)],
        "assets": {"image": {
            "href": base_url + path,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "roles": ["data", "visual"],
            "title": "RGB JPEG Cloud-Optimized GeoTIFF",
            "file:size": receipt["output_bytes"],
            "file:checksum": None if not sha else "1220" + sha,
        }},
        "naip:run": receipt["run_id"],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("receipts_dirs", nargs="+")
    p.add_argument("--base-url", default="https://data.source.coop/nthh/naip/")
    p.add_argument("--row-group", type=int, default=512)
    a = p.parse_args()

    rows, transformers = [], {}
    for d in a.receipts_dirs:
        for name in sorted(os.listdir(d)):
            if name.endswith(".json"):
                with open(os.path.join(d, name)) as f:
                    rows.append(item(json.load(f), a.base_url, transformers))
    rows.sort(key=lambda r: (r["naip:state"], r["naip:year"], r["id"]))

    table = pa.Table.from_pylist(rows)
    geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {"geometry": {
        "encoding": "WKB", "geometry_types": ["Polygon"],
        "bbox": [min(r["bbox"]["xmin"] for r in rows), min(r["bbox"]["ymin"] for r in rows),
                 max(r["bbox"]["xmax"] for r in rows), max(r["bbox"]["ymax"] for r in rows)],
        "covering": {"bbox": {k: ["bbox", k] for k in ("xmin", "ymin", "xmax", "ymax")}}}}}
    table = table.replace_schema_metadata({"geo": json.dumps(geo)})
    pq.write_table(table, a.out, row_group_size=a.row_group, compression="zstd",
                   write_statistics=True)
    print(json.dumps({"rows": len(rows), "bytes": os.path.getsize(a.out),
                      "row_groups": pq.ParquetFile(a.out).num_row_groups,
                      "epsg": sorted({r["proj:epsg"] for r in rows})}))


if __name__ == "__main__":
    main()
