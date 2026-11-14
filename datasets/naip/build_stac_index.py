#!/usr/bin/env python3
"""Build a STAC-GeoParquet index of converted quads from one or more runs' receipts.

One row per file, as a STAC item: footprint in longitude and latitude, the date flown, the
file's own CRS and extent (projection extension), one asset, `image`, with the file's URL,
size and checksum, and one link, `derived_from`, to the source file. The collection is kept in
the file's `stac-geoparquet` metadata (specification 1.1.0). Rows are sorted by year and then along a Hilbert curve through the
footprint centres, so that each row group covers one compact area and a reader can skip
almost all of the file from the row-group bbox statistics.

    uv run --no-project --with pyarrow==21.0.0 --with pyproj==3.7.2 \
        python build_stac_index.py <out.parquet> <receipts dir> [<receipts dir> ...] \
        [--base-url https://data.source.coop/nthh/naip/] [--row-group 512] [--sort hilbert|name]
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


def hilbert(lon, lat, order=16):
    """Distance along a Hilbert curve of 2**order cells per side over the whole lon/lat plane."""
    n = 1 << order
    x = min(n - 1, max(0, int((lon + 180.0) / 360.0 * n)))
    y = min(n - 1, max(0, int((lat + 90.0) / 180.0 * n)))
    d, s = 0, n >> 1
    while s:
        rx, ry = int(bool(x & s)), int(bool(y & s))
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x, y = n - 1 - x, n - 1 - y
            x, y = y, x
        s >>= 1
    return d


def sort_rows(rows, how):
    if how == "name":
        rows.sort(key=lambda r: (r["naip:state"], r["naip:year"], r["id"]))
    else:
        rows.sort(key=lambda r: (r["naip:year"], hilbert((r["bbox"]["xmin"] + r["bbox"]["xmax"]) / 2,
                                                         (r["bbox"]["ymin"] + r["bbox"]["ymax"]) / 2), r["id"]))


def collection(rows):
    """The STAC Collection these items belong to, kept in the file's own metadata."""
    days = [r["datetime"] for r in rows]
    return {
        "type": "Collection", "stac_version": "1.1.0", "stac_extensions": [], "id": "naip",
        "title": "NAIP display copies, 2024 onward",
        "description": "RGB JPEG Cloud-Optimized GeoTIFFs of USDA National Agriculture Imagery Program quarter "
                       "quads, one item per file, converted from the four-band files in s3://naip-analytic. "
                       "NAIP imagery is in the public domain and USDA asks for credit; these files are a format "
                       "conversion, not a USDA product.",
        "license": "other",
        "providers": [{"name": "USDA Farm Production and Conservation Business Center", "roles": ["producer", "licensor"],
                       "url": "https://naip-usdaonline.hub.arcgis.com/"}],
        "extent": {"spatial": {"bbox": [[min(r["bbox"]["xmin"] for r in rows), min(r["bbox"]["ymin"] for r in rows),
                                         max(r["bbox"]["xmax"] for r in rows), max(r["bbox"]["ymax"] for r in rows)]]},
                   "temporal": {"interval": [[min(days).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                              max(days).strftime("%Y-%m-%dT%H:%M:%SZ")]]}},
        "summaries": {"gsd": sorted({r["gsd"] for r in rows}), "naip:state": sorted({r["naip:state"] for r in rows}),
                      "naip:year": sorted({r["naip:year"] for r in rows}),
                      "proj:code": sorted({r["proj:code"] for r in rows})},
        "item_assets": {"image": {"type": "image/tiff; application=geotiff; profile=cloud-optimized",
                                  "roles": ["data", "visual"], "title": "RGB JPEG Cloud-Optimized GeoTIFF"}},
        "links": [],
    }


def write(rows, out, row_group):
    table = pa.Table.from_pylist(rows)
    # GeoParquet's bbox covering wants the struct's fields in this order; inferred structs come out
    # alphabetical.
    order = ("xmin", "ymin", "xmax", "ymax")
    bbox = pa.StructArray.from_arrays([pa.array([r["bbox"][k] for r in rows], pa.float64()) for k in order], names=order)
    table = table.set_column(table.schema.get_field_index("bbox"), "bbox", bbox)
    geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {"geometry": {
        "encoding": "WKB", "geometry_types": ["Polygon"],
        "bbox": [min(r["bbox"]["xmin"] for r in rows), min(r["bbox"]["ymin"] for r in rows),
                 max(r["bbox"]["xmax"] for r in rows), max(r["bbox"]["ymax"] for r in rows)],
        "covering": {"bbox": {k: ["bbox", k] for k in ("xmin", "ymin", "xmax", "ymax")}}}}}
    stac = {"version": "1.1.0", "collections": {"naip": collection(rows)}}
    table = table.replace_schema_metadata({"geo": json.dumps(geo), "stac-geoparquet": json.dumps(stac)})
    # Statistics only on the columns a reader filters by: on every column they are most of
    # the footer, which a reader fetches whole before anything else.
    pq.write_table(table, out, row_group_size=row_group, compression="zstd",
                   write_statistics=["bbox.xmin", "bbox.ymin", "bbox.xmax", "bbox.ymax", "datetime", "naip:year"])


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
        "links": [{"rel": "derived_from", "title": "Source four-band MRF (requester pays)",
                   "href": f"s3://naip-analytic/{state}/{year}/{resolution}/rgbir/{key.split('/')[-2]}/{filename[:-4]}.mrf"}],
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
    p.add_argument("--sort", choices=["hilbert", "name"], default="hilbert")
    a = p.parse_args()

    rows, transformers = [], {}
    for d in a.receipts_dirs:
        for name in sorted(os.listdir(d)):
            if name.endswith(".json"):
                with open(os.path.join(d, name)) as f:
                    rows.append(item(json.load(f), a.base_url, transformers))
    sort_rows(rows, a.sort)
    write(rows, a.out, a.row_group)
    print(json.dumps({"rows": len(rows), "bytes": os.path.getsize(a.out),
                      "row_groups": pq.ParquetFile(a.out).num_row_groups,
                      "epsg": sorted({r["proj:epsg"] for r in rows})}))


if __name__ == "__main__":
    main()
