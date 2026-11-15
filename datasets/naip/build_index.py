#!/usr/bin/env python3
"""Build the quad index for one converted state-year from its receipts.

One row per file: where it is, what it covers, when it was flown, its size and checksum,
and how it was made. Written as GeoParquet 1.1 with footprints in longitude and latitude.

    uv run --no-project --with pyarrow==21.0.0 --with pyproj==3.7.2 \
        python build_index.py <receipts dir> <out.parquet>
"""

import hashlib
import json
import os
import struct
import sys

import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import Transformer


def footprint(receipt, transformers):
    """Corner ring in lon/lat (closed, counter-clockwise) and the bounds in the file's own CRS."""
    x0, dx, _, y0, _, dy = receipt["output"]["geotransform"]
    x1, y1 = x0 + dx * receipt["output"]["width"], y0 + dy * receipt["output"]["height"]
    epsg = int(receipt["output"]["epsg"])
    if epsg not in transformers:
        transformers[epsg] = Transformer.from_crs(epsg, 4326, always_xy=True)
    corners = [(x0, y1), (x1, y1), (x1, y0), (x0, y0), (x0, y1)]
    ring = [transformers[epsg].transform(x, y) for x, y in corners]
    return ring, [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def wkb_polygon(ring):
    return struct.pack("<BII", 1, 3, 1) + struct.pack("<I", len(ring)) + b"".join(
        struct.pack("<dd", x, y) for x, y in ring)


def main(receipts_dir, out_path):
    rows, transformers = [], {}
    for name in sorted(os.listdir(receipts_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(receipts_dir, name)) as f:
            r = json.load(f)
        key = r["out_uri"].split("/", 3)[3] if "out_uri" in r else r["out_key"]
        # <state>/<year>/<res>/rgb/<block>/m_<quad>_<quarter>_<zone>_<res>_<yyyymmdd flown>[_<yyyymmdd made>].tif
        state, year, resolution, _, _, filename = key.split("/")[-6:]
        flown = filename[:-4].split("_")[5]      # a 2023 name carries a second date after it, the day the file was made
        ring, native = footprint(r, transformers)
        psnr = r.get("psnr_db")
        rows.append({
            "id": r["id"],
            "state": state,
            "year": int(year),
            "resolution_cm": int(resolution[:-2]),
            "flown": f"{flown[:4]}-{flown[4:6]}-{flown[6:]}",
            "path": "/".join(key.split("/")[-6:]),
            "bytes": r["output_bytes"],
            "sha256": r.get("output_sha256"),
            "width": r["output"]["width"],
            "height": r["output"]["height"],
            "epsg": int(r["output"]["epsg"]),
            "native_bounds": native,
            "source_bytes": sum(r["source_bytes"].values()),
            "psnr_db": None if not psnr else round(sum(psnr) / len(psnr), 3),
            "jpeg_quality": r["quality"],
            "gdal": r["gdal"],
            "run": r["run_id"],
            "geometry": wkb_polygon(ring),
            "bbox": {"xmin": min(p[0] for p in ring), "ymin": min(p[1] for p in ring),
                     "xmax": max(p[0] for p in ring), "ymax": max(p[1] for p in ring)},
        })
    table = pa.Table.from_pylist(rows)
    bounds = [min(r["bbox"]["xmin"] for r in rows), min(r["bbox"]["ymin"] for r in rows),
              max(r["bbox"]["xmax"] for r in rows), max(r["bbox"]["ymax"] for r in rows)]
    geo = {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {"geometry": {
            "encoding": "WKB", "geometry_types": ["Polygon"], "bbox": bounds,
            "covering": {"bbox": {"xmin": ["bbox", "xmin"], "ymin": ["bbox", "ymin"],
                                  "xmax": ["bbox", "xmax"], "ymax": ["bbox", "ymax"]}},
        }},
    }
    table = table.replace_schema_metadata({"geo": json.dumps(geo)})
    pq.write_table(table, out_path, compression="zstd")
    with open(out_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    print(json.dumps({
        "file": os.path.basename(out_path), "rows": len(rows), "bytes": os.path.getsize(out_path),
        "sha256": digest, "data_bytes": sum(r["bytes"] for r in rows), "bounds": [round(b, 5) for b in bounds],
        "flown_first": min(r["flown"] for r in rows), "flown_last": max(r["flown"] for r in rows),
        "rows_with_sha256": sum(1 for r in rows if r["sha256"]),
        "rows_with_psnr": sum(1 for r in rows if r["psnr_db"] is not None),
    }, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
