#!/usr/bin/env python3
"""The GDAL tile index pair for QGIS and GDAL: stac/naip.gti.fgb and stac/naip-overviews.gti.fgb.

    python build_gti_fgb.py <dir with naip.parquet and naip-overviews.parquet> <out dir>
        [--host https://data.source.coop] [--prefix nthh/naip]

Two FlatGeobuf files, each a GDAL tile index (GTI) on its own: the raster settings are written into the
layer metadata, so a reader opens `GTI:/vsicurl/https://data.source.coop/nthh/naip/stac/naip.gti.fgb`
with no XML file and no Parquet driver. The mosaic is in NAD83 longitude and latitude (the quads' datum)
at 0.000005 degrees, about 0.5 m, with red, green, blue and alpha bands. Zoomed out it reads the 9.6 m
state overview files (0.00008 to 0.00128 degrees) and then the national file (0.00256 to 0.04096
degrees); the coarsest levels keep a whole-country read, such as the statistics QGIS takes when the layer
is added, to a few hundred kilobytes of the national file's own overviews.

naip.gti.fgb has one row per 3.75-minute cell of the quarter-quad grid (0.0625 degrees a side), holding
the newest file of the quad index whose footprint centre lies in that cell (the latest `datetime`, then
the greatest `id`). Its footprint is the cell itself, not the file's extent, so no two rows overlap:
neighbouring cells only touch. GDAL reads the sources of a view in parallel only when they do not
overlap; with the quad index, where years and the edges of neighbouring quads overlap, it reads them one
at a time. Each file still covers a little more than its cell, as quarter quads do, and GDAL draws all of
it, so where two neighbours overlap either may be on top.

naip-overviews.gti.fgb has one row per overview file, with its bbox as the footprint.

The tile addresses are absolute (`/vsicurl?empty_dir=yes&url=https://...`), and so is the overview
reference in naip.gti.fgb: the `GTI:` prefix a reader uses to open a FlatGeobuf as a tile index stops
GDAL resolving relative paths. `empty_dir=yes` keeps GDAL from looking for side files next to each file.

Columns: `datetime` (the flight date) and `naip:gti_location` (the GTI location field); the overview
index also has `id`, which naip.gti.fgb's overview levels filter on. The file name in each address is the
quad index's `id` without its state prefix.
`--host` and `--prefix` change the address of every file, and `--index-dir` the folder of the pair, for a
copy on another server.
"""
import argparse
import json
import math
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from osgeo import gdal, ogr, osr

gdal.UseExceptions()

CELL = 0.0625            # degrees: a quarter quad is 3.75 minutes a side
PUBLISHED = "https://data.source.coop/nthh/naip/"   # the hrefs in the index release
QUADS_DESCRIPTION = ("NAIP visualization COGs as one mosaic for GDAL and QGIS: the newest quarter quad of each "
                     "3.75-minute cell, the cell as its footprint. GDAL tile index; open as GTI:/vsicurl/<this address>.")
OVERVIEWS_DESCRIPTION = ("Overview files of the NAIP visualization COGs (9.6 m state files and the national file), "
                         "opened by naip.gti.fgb for zoomed-out views. GDAL tile index.")


def vsicurl(url):
    return f"/vsicurl?empty_dir=yes&url={url}"


def gti_settings(res):
    """GTI layer-metadata keys of one index at `res` degrees: CRS EPSG:4269 (the layer's), the lower 48."""
    return {
        "LOCATION_FIELD": "naip:gti_location", "SORT_FIELD": "datetime", "SORT_FIELD_ASC": "YES",
        "RESX": res, "RESY": res, "MINX": "-125.2", "MINY": "23.2", "MAXX": "-66.0", "MAXY": "49.92",
        "BAND_COUNT": "4", "DATA_TYPE": "Byte", "COLOR_INTERPRETATION": "red,green,blue,alpha",
    }


QUAD_RES = "0.000005"
OVERVIEW_RES = "0.00008"
FACTORS = ("2", "4", "8")                                               # from the quads themselves
STATE_LEVELS = ("0.00008", "0.00016", "0.00032", "0.00064", "0.00128")  # the 9.6 m state files
NATIONAL_LEVELS = ("0.00256", "0.00512", "0.01024", "0.02048", "0.04096")  # the national file


def overview_settings(overview_dataset):
    """naip.gti.fgb's overview levels: three factors, then naip-overviews.gti.fgb filtered and resampled."""
    meta = {f"OVERVIEW_{i}_FACTOR": factor for i, factor in enumerate(FACTORS)}
    levels = [("id <> 'national-latest'", r) for r in STATE_LEVELS] + [("id = 'national-latest'", r) for r in NATIONAL_LEVELS]
    for i, (where, res) in enumerate(levels, start=len(FACTORS)):
        meta[f"OVERVIEW_{i}_DATASET"] = overview_dataset
        meta[f"OVERVIEW_{i}_OPEN_OPTIONS"] = f"FILTER={where},RESX={res},RESY={res}"   # GDAL splits on commas
    return meta


def read_index(path):
    with open(path, "rb") as f:
        table = pq.ParquetFile(f).read(columns=["id", "datetime", "bbox", "assets", "naip:gti_location"])
    hrefs = pc.struct_field(pc.struct_field(table["assets"], "image"), "href").to_pylist()
    locations = table["naip:gti_location"].to_pylist()
    for href, location in zip(hrefs, locations):   # the release's two addresses name the same file
        assert location.startswith("../") and href == PUBLISHED + location[3:], (href, location)
    bbox = table["bbox"].combine_chunks()
    boxes = list(zip(*(bbox.field(k).to_pylist() for k in ("xmin", "ymin", "xmax", "ymax"))))
    return table["id"].to_pylist(), table["datetime"], hrefs, boxes


def newest_per_cell(ids, when, boxes):
    newest = {}
    for row, (xmin, ymin, xmax, ymax) in enumerate(boxes):
        cell = (math.floor((xmin + xmax) / 2 / CELL), math.floor((ymin + ymax) / 2 / CELL))
        best = newest.get(cell)
        if best is None or (when[row], ids[row]) > (when[best], ids[best]):
            newest[cell] = row
    return newest


def polygon(x0, y0, x1, y1):
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)):
        ring.AddPoint_2D(x, y)
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ring)
    return poly


def write(out, layer_name, description, meta, rows, with_id):
    """rows: (id, datetime string, location, (x0, y0, x1, y1)). Metadata is set before the first feature:
    the FlatGeobuf driver writes the header then, and drops metadata set later."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4269)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ds = ogr.GetDriverByName("FlatGeobuf").CreateDataSource(str(out))
    layer = ds.CreateLayer(layer_name, srs, ogr.wkbPolygon,
                           options=["SPATIAL_INDEX=YES", f"TITLE={layer_name}", f"DESCRIPTION={description}"])
    fields = [("datetime", ogr.OFTDateTime), (meta["LOCATION_FIELD"], ogr.OFTString)]
    for name, kind in ([("id", ogr.OFTString)] if with_id else []) + fields:
        layer.CreateField(ogr.FieldDefn(name, kind))
    layer.SetMetadata(meta)
    definition = layer.GetLayerDefn()
    for fid, stamp, location, box in rows:
        feature = ogr.Feature(definition)
        if with_id:
            feature.SetField("id", fid)
        feature.SetField("datetime", stamp)
        feature.SetField(meta["LOCATION_FIELD"], location)
        feature.SetGeometry(polygon(*box))
        layer.CreateFeature(feature)
    ds = None
    reopened = gdal.OpenEx(str(out), gdal.OF_VECTOR)
    back = reopened.GetLayer(0)
    assert meta.items() <= back.GetMetadata().items(), "layer metadata survived the write"
    return back.GetFeatureCount()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--host", default="https://data.source.coop")
    parser.add_argument("--prefix", default="nthh/naip")
    parser.add_argument("--index-dir", default="stac", help="folder of the pair under the prefix, for a test copy")
    args = parser.parse_args()
    base = f"{args.host.rstrip('/')}/{args.prefix.strip('/')}/"
    args.out_dir.mkdir(parents=True, exist_ok=True)

    quad_meta = gti_settings(QUAD_RES)
    overview_meta = gti_settings(OVERVIEW_RES)
    quad_meta.update(overview_settings("GTI:" + vsicurl(f"{base}{args.index_dir.strip('/')}/naip-overviews.gti.fgb")))

    def address(href):
        return vsicurl(base + href[len(PUBLISHED):])

    ids, when, hrefs, boxes = read_index(args.release_dir / "naip.parquet")
    stamps = pc.strftime(when, "%Y-%m-%dT%H:%M:%SZ").to_pylist()
    newest = newest_per_cell(ids, when.cast(pa.int64()).to_pylist(), boxes)
    quads = [(ids[r], stamps[r], address(hrefs[r]), (i * CELL, j * CELL, (i + 1) * CELL, (j + 1) * CELL))
             for (i, j), r in sorted(newest.items(), key=lambda item: item[1])]
    quad_rows = write(args.out_dir / "naip.gti.fgb", "naip", QUADS_DESCRIPTION, quad_meta, quads, with_id=False)

    o_ids, o_when, o_hrefs, o_boxes = read_index(args.release_dir / "naip-overviews.parquet")
    o_stamps = pc.strftime(o_when, "%Y-%m-%dT%H:%M:%SZ").to_pylist()
    overview_rows = write(args.out_dir / "naip-overviews.gti.fgb", "naip_overviews", OVERVIEWS_DESCRIPTION, overview_meta,
                          [(i, s, address(h), b) for i, s, h, b in zip(o_ids, o_stamps, o_hrefs, o_boxes)],
                          with_id=True)

    print(json.dumps({"quad_rows_in": len(ids), "cells": quad_rows, "older_rows_left_out": len(ids) - quad_rows,
                      "overview_rows_in": len(o_ids), "overview_rows": overview_rows, "base": base,
                      "files": {p.name: p.stat().st_size for p in sorted(args.out_dir.glob("*.gti.fgb"))}}, indent=1))


if __name__ == "__main__":
    main()
