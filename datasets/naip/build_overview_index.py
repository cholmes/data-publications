#!/usr/bin/env python3
"""A STAC GeoParquet index of overview files, one item per file, from their build results.

    python3 build_overview_index.py <quad index.parquet> <base url of the files> <out.parquet> <result.json> ...

Each result is what overview.py wrote for one state file, or what national.py wrote for the
national file. The item has the columns of the quad index, so a reader of that index reads
this one unchanged: `gsd` is the file's finest level and `datetime` is the latest flight
date among the quads of the same state, year and zone, with the first in `start_datetime`.

The footprint of a state file is an outline of its quads, not the file's rectangle, which
for most states is a third empty: the union of the quad footprints, widened a little and
simplified by less than it was widened, so it still covers every quad. A hole the size of a
missing quad or more is kept and smaller ones are dropped. A reader that asks which files are
in view is then not sent to a file with no picture there, and where a newer flight lacks
quads it goes on to the older file that has them.
A state with islands has an outline of several parts (a MultiPolygon).
The file's rectangle is in `proj:bbox`. The national file's footprint is its rectangle.

The national file is in Web Mercator, where a pixel covers less ground the further north it
is. Its `gsd` is the ground size at the middle latitude of the file; `proj:transform` has
the exact pixel. It has no state or year, and its dates and quad count are those of all the
state files given.

The collection is kept in the file's `stac-geoparquet` metadata, with a link to the quad
index the files were made from (QUAD_INDEX_URL).
"""
import json
import math
import os
import struct
import sys

import pyarrow as pa
import pyarrow.parquet as pq
from osgeo import ogr, osr

ogr.UseExceptions()

EDGE_POINTS = 16
GROW = 0.002        # degrees an outline is widened by before it is simplified, about 200 m
HOLE = 0.001        # square degrees: the smallest hole kept in an outline. A quarter quad is 0.0625 degrees a side (0.0039)
QUAD_INDEX_URL = os.environ.get("QUAD_INDEX_URL", "https://data.source.coop/nthh/naip/stac/naip.parquet")
TYPE = "image/tiff; application=geotiff; profile=cloud-optimized"
EXTENSIONS = ["https://stac-extensions.github.io/projection/v2.0.0/schema.json",
              "https://stac-extensions.github.io/file/v2.1.0/schema.json"]


def collection(rows):
    days = lambda key, pick: pick(r[key] for r in rows).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "type": "Collection", "stac_version": "1.1.0", "stac_extensions": [], "id": "naip-overviews",
        "title": "NAIP display copies, overview files",
        "description": "Reduced pictures made from the NAIP display copies, for drawing a map before the quarter quads "
                       "are worth reading: one file per state, year and UTM zone at 9.6 m, and one file of the "
                       "country with the latest flight of each state on top. RGB JPEG Cloud-Optimized GeoTIFFs "
                       "with a mask where there is no picture. NAIP imagery is in the public domain and USDA asks "
                       "for credit; these files are not a USDA product.",
        "license": "other",
        "providers": [{"name": "USDA Farm Production and Conservation Business Center", "roles": ["producer", "licensor"],
                       "url": "https://naip-usdaonline.hub.arcgis.com/"}],
        "extent": {"spatial": {"bbox": [[min(r["bbox"]["xmin"] for r in rows), min(r["bbox"]["ymin"] for r in rows),
                                         max(r["bbox"]["xmax"] for r in rows), max(r["bbox"]["ymax"] for r in rows)]]},
                   "temporal": {"interval": [[days("start_datetime", min), days("end_datetime", max)]]}},
        "summaries": {"gsd": sorted({r["gsd"] for r in rows}),
                      "naip:state": sorted({r["naip:state"] for r in rows if r["naip:state"]}),
                      "naip:year": sorted({r["naip:year"] for r in rows if r["naip:year"]}),
                      "proj:code": sorted({r["proj:code"] for r in rows})},
        "item_assets": {"image": {"type": TYPE, "roles": ["overview", "visual"],
                                  "title": "RGB JPEG Cloud-Optimized GeoTIFF with a mask"}},
        "links": [{"rel": "derived_from", "href": QUAD_INDEX_URL, "type": "application/vnd.apache.parquet",
                   "title": "The quarter quads these files were made from, one item per file (STAC GeoParquet)"}],
    }


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


def outline(quads):
    """The union of these quad footprints (WKB), widened by GROW, holes under HOLE dropped, simplified by less than GROW; and its bbox."""
    parts = ogr.Geometry(ogr.wkbMultiPolygon)
    for wkb in quads:
        parts.AddGeometry(ogr.CreateGeometryFromWkb(bytes(wkb)))
    joined = parts.UnionCascaded().Buffer(GROW, 2)
    kept = ogr.Geometry(ogr.wkbMultiPolygon)
    for i in range(max(1, joined.GetGeometryCount() if joined.GetGeometryType() == ogr.wkbMultiPolygon else 1)):
        polygon = joined.GetGeometryRef(i) if joined.GetGeometryType() == ogr.wkbMultiPolygon else joined
        shell = ogr.Geometry(ogr.wkbPolygon)
        shell.AddGeometry(polygon.GetGeometryRef(0))
        for j in range(1, polygon.GetGeometryCount()):
            hole = ogr.Geometry(ogr.wkbPolygon)
            hole.AddGeometry(polygon.GetGeometryRef(j))
            if hole.GetArea() >= HOLE:
                shell.AddGeometry(polygon.GetGeometryRef(j))
        kept.AddGeometry(shell)
    shape = kept.UnionCascaded().SimplifyPreserveTopology(GROW / 2)
    xmin, xmax, ymin, ymax = shape.GetEnvelope()
    return bytes(shape.ExportToIsoWkb()), {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}


def main():
    quad_index, base, out = sys.argv[1:4]
    with open(quad_index, "rb") as f:      # an open file: pyarrow's own file systems clash with GDAL's when both are loaded
        index = pq.ParquetFile(f)
        schema = index.schema_arrow
        quads = index.read(columns=["naip:state", "naip:year", "proj:epsg", "datetime", "geometry"]).to_pylist()
    results = []
    for path in sys.argv[4:]:
        with open(path) as f:
            results.append(json.load(f))
    by_group = {}
    for q in quads:
        by_group.setdefault((q["naip:state"], q["naip:year"], str(q["proj:epsg"])), []).append(q)
    rows = []
    for r in sorted(results, key=lambda r: ("zones" in r, r["name"])):      # the national file first
        if "zones" in r:
            state, year = r["name"].split("-")[:2]
            year, gsd, count = int(year), r["res"], r["quads"]
            mine = [q for zone in r["zones"] for q in by_group[state, year, zone]]
            dates = sorted(q["datetime"] for q in mine)
            geometry, bbox = outline([q["geometry"] for q in mine])
        else:
            state, year = None, None
            geometry, bbox = footprint(r["bounds"], r["target_epsg"])
            gsd = round(r["res"] * math.cos(math.radians((bbox["ymin"] + bbox["ymax"]) / 2)), 1)
            states = [s for s in results if "zones" in s]
            count = sum(s["quads"] for s in states)
            dates = sorted(q["datetime"] for s in states for zone in s["zones"]
                           for q in by_group[s["name"].split("-")[0], int(s["name"].split("-")[1]), zone])
        href = base.rstrip("/") + f"/{r['name']}.tif"
        width, height = r["file"]["size"]
        rows.append({
            "stac_version": "1.1.0", "stac_extensions": EXTENSIONS,
            "id": r["name"], "collection": "naip-overviews", "geometry": geometry, "bbox": bbox,
            "datetime": dates[-1], "start_datetime": dates[0], "end_datetime": dates[-1], "gsd": gsd,
            "naip:state": state, "naip:year": year, "naip:quads": count,
            "proj:code": f"EPSG:{r['target_epsg']}", "proj:epsg": r["target_epsg"], "proj:bbox": r["bounds"],
            "proj:shape": [height, width],
            "proj:transform": [r["res"], 0.0, r["bounds"][0], 0.0, -r["res"], r["bounds"][3]],
            "links": [],
            "assets": {"image": {"file:checksum": None, "file:size": r["bytes"], "href": href,
                                 "roles": ["overview", "visual"], "title": "RGB JPEG Cloud-Optimized GeoTIFF with a mask", "type": TYPE}},
        })
    fields = [f for f in schema if f.name != "naip:run"]
    at = [f.name for f in fields].index("datetime") + 1
    fields[at:at] = [pa.field("start_datetime", schema.field("datetime").type), pa.field("end_datetime", schema.field("datetime").type)]
    fields.append(pa.field("naip:quads", pa.int64()))
    table = pa.Table.from_pylist(rows, schema=pa.schema(fields))
    boxes = [r["bbox"] for r in rows]
    kinds = {ogr.CreateGeometryFromWkb(r["geometry"]).GetGeometryName().title().replace("polygon", "Polygon") for r in rows}
    geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {"geometry": {
        "encoding": "WKB", "geometry_types": sorted(kinds),
        "bbox": [min(b["xmin"] for b in boxes), min(b["ymin"] for b in boxes), max(b["xmax"] for b in boxes), max(b["ymax"] for b in boxes)],
        "covering": {"bbox": {k: ["bbox", k] for k in ("xmin", "ymin", "xmax", "ymax")}}}}}
    with open(out, "wb") as f:
        stac = {"version": "1.1.0", "collections": {"naip-overviews": collection(rows)}}
        pq.write_table(table.replace_schema_metadata({"geo": json.dumps(geo), "stac-geoparquet": json.dumps(stac)}), f,
                       compression="zstd")
    print(os.path.basename(out), len(rows), "items")


if __name__ == "__main__":
    main()
