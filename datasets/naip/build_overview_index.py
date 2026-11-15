#!/usr/bin/env python3
"""A STAC GeoParquet index of overview files, one item per file, from their build results.

    python3 build_overview_index.py <quad index.parquet> <base url of the files> <out.parquet> <result.json> ...

Each result is what overview.py wrote for one file. The item has the columns of the quad
index, so a reader of that index reads this one unchanged: `gsd` is the file's finest
level, the footprint is the file's rectangle in its own projection (densified, in
longitude and latitude), and `datetime` is the latest flight date among the quads of the
same state, year and zone, with the first in `start_datetime`.
"""
import json
import os
import struct
import sys

import pyarrow as pa
import pyarrow.parquet as pq
from osgeo import osr

EDGE_POINTS = 16


def footprint(bounds, epsg):
    """The rectangle's edge in longitude and latitude, EDGE_POINTS to a side, and its bbox."""
    xmin, ymin, xmax, ymax = bounds
    source, target = osr.SpatialReference(), osr.SpatialReference()
    source.ImportFromEPSG(epsg)
    target.ImportFromEPSG(4326)
    for srs in (source, target):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_lonlat = osr.CoordinateTransformation(source, target)
    corners = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)]
    ring = []
    for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
        for i in range(EDGE_POINTS):
            t = i / EDGE_POINTS
            ring.append(to_lonlat.TransformPoint(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)[:2])
    ring.append(ring[0])
    wkb = struct.pack("<BIII", 1, 3, 1, len(ring)) + b"".join(struct.pack("<dd", *p) for p in ring)
    lons, lats = [p[0] for p in ring], [p[1] for p in ring]
    return wkb, {"xmin": min(lons), "ymin": min(lats), "xmax": max(lons), "ymax": max(lats)}


def main():
    quad_index, base, out = sys.argv[1:4]
    with open(quad_index, "rb") as f:      # an open file: pyarrow's own file systems clash with GDAL's when both are loaded
        index = pq.ParquetFile(f)
        schema = index.schema_arrow
        quads = index.read(columns=["naip:state", "naip:year", "proj:epsg", "datetime"]).to_pylist()
    rows = []
    for path in sys.argv[4:]:
        with open(path) as f:
            r = json.load(f)
        state, year = r["name"].split("-")[:2]
        dates = sorted(q["datetime"] for q in quads if q["naip:state"] == state and q["naip:year"] == int(year)
                       and str(q["proj:epsg"]) in r["zones"])
        geometry, bbox = footprint(r["bounds"], r["target_epsg"])
        # Files named <state>-<year>-utm<zone> sit under <state>/<year>/; the earlier test files sit at the base.
        parts = r["name"].split("-")
        folder = f"{state}/{year}/" if len(parts) == 3 and parts[2].startswith("utm") else ""
        href = base.rstrip("/") + f"/{folder}{r['name']}.tif"
        width, height = r["file"]["size"]
        rows.append({
            "stac_version": "1.1.0",
            "stac_extensions": ["https://stac-extensions.github.io/projection/v2.0.0/schema.json",
                                "https://stac-extensions.github.io/file/v2.1.0/schema.json"],
            "id": r["name"], "collection": "naip-overviews", "geometry": geometry, "bbox": bbox,
            "datetime": dates[-1], "start_datetime": dates[0], "end_datetime": dates[-1], "gsd": r["res"],
            "naip:state": state, "naip:year": int(year), "naip:quads": r["quads"],
            "proj:code": f"EPSG:{r['target_epsg']}", "proj:epsg": r["target_epsg"], "proj:bbox": r["bounds"],
            "proj:shape": [height, width],
            "proj:transform": [r["res"], 0.0, r["bounds"][0], 0.0, -r["res"], r["bounds"][3]],
            "links": [],
            "assets": {"image": {"file:checksum": None, "file:size": r["bytes"], "href": href,
                                 "roles": ["overview", "visual"], "title": "RGB JPEG Cloud-Optimized GeoTIFF with a mask",
                                 "type": "image/tiff; application=geotiff; profile=cloud-optimized"}},
        })
    fields = [f for f in schema if f.name != "naip:run"]
    at = [f.name for f in fields].index("datetime") + 1
    fields[at:at] = [pa.field("start_datetime", schema.field("datetime").type), pa.field("end_datetime", schema.field("datetime").type)]
    fields.append(pa.field("naip:quads", pa.int64()))
    table = pa.Table.from_pylist(rows, schema=pa.schema(fields))
    boxes = [r["bbox"] for r in rows]
    geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {"geometry": {
        "encoding": "WKB", "geometry_types": ["Polygon"],
        "bbox": [min(b["xmin"] for b in boxes), min(b["ymin"] for b in boxes), max(b["xmax"] for b in boxes), max(b["ymax"] for b in boxes)],
        "covering": {"bbox": {k: ["bbox", k] for k in ("xmin", "ymin", "xmax", "ymax")}}}}}
    with open(out, "wb") as f:
        pq.write_table(table.replace_schema_metadata({"geo": json.dumps(geo)}), f, compression="zstd")
    print(os.path.basename(out), len(rows), "items")


if __name__ == "__main__":
    main()
