#!/usr/bin/env python3
"""One picture of the same ground drawn from several files, side by side, for choosing between them.

    python3 overview_pictures.py <out.png> <lon> <lat> <metres per screen pixel> <label>=<file or url> ...

Each file is read through GDAL at the screen's pixel size (so a file whose finest level is
coarser is enlarged, as a map would) onto one 512 pixel panel in the first file's projection.
A label ending in "@quads" names a STAC index instead: the hosted quads that cover the panel
are mosaicked, which is what a viewer reading the quads would show.
"""
import sys

import numpy as np
import pyarrow.parquet as pq
from osgeo import gdal, osr
from PIL import Image, ImageDraw

gdal.UseExceptions()
gdal.SetConfigOption("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
PANEL = 512


def path(p):
    return ("/vsicurl/" if p.startswith("http") else "") + p


def main():
    out, lon, lat, size = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
    sources = [arg.split("=", 1) for arg in sys.argv[5:]]
    first = gdal.Open(path(next(p for label, p in sources if not label.endswith("@quads"))))
    srs = osr.SpatialReference(wkt=first.GetProjection())
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    x, y, _ = osr.CoordinateTransformation(wgs, srs).TransformPoint(lon, lat)
    half = PANEL * size / 2
    bounds = (x - half, y - half, x + half, y + half)
    panels = []
    for label, p in sources:
        if label.endswith("@quads"):
            with open(p, "rb") as f:
                rows = pq.ParquetFile(f).read(columns=["bbox", "assets"]).to_pylist()
            d = half * 1.5 / 111000
            files = [path(r["assets"]["image"]["href"]) for r in rows
                     if r["bbox"]["xmin"] < lon + d * 1.4 and r["bbox"]["xmax"] > lon - d * 1.4
                     and r["bbox"]["ymin"] < lat + d and r["bbox"]["ymax"] > lat - d]
            source, label = gdal.BuildVRT("", files), f"{label[:-6]} ({len(files)} quads)"
        else:
            source = gdal.Open(path(p))
        pixels = gdal.Warp("", source, format="MEM", dstSRS=srs.ExportToWkt(), outputBounds=bounds, width=PANEL, height=PANEL,
                           resampleAlg="bilinear").ReadAsArray()[:3]
        panel = Image.fromarray(np.moveaxis(pixels, 0, 2))
        draw = ImageDraw.Draw(panel)
        draw.rectangle((0, 0, 8 + 7 * len(label), 18), fill=(0, 0, 0))
        draw.text((4, 3), label, fill=(255, 255, 255))
        panels.append(panel)
    sheet = Image.new("RGB", (PANEL * len(panels) + 4 * (len(panels) - 1), PANEL), (255, 255, 255))
    for i, panel in enumerate(panels):
        sheet.paste(panel, (i * (PANEL + 4), 0))
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
