#!/usr/bin/env python3
"""For published files with a dark overview edge: is the edge dark at full resolution too?

The converter refuses a file when the last row or column of an overview level is below 0.7
of the one before it. That catches the fault of copied source overviews (a last row half as
bright as the pixels it stands for). It also trips on a file whose own edge is black, or
that has a bright feature just inside the edge. Those files are converted with the check
off, and this script settles each one from the hosted file: for every overview level, the
last row and the last column must be as bright as the full-resolution pixels they cover.

    python3 check_dark_edges.py <receipts dir> <out.json> [--thumbs <dir>]

Reads each file anonymously over /vsis3/: the bottom 512 rows, the right 512 columns, the
edges of every overview level, and the smallest overview for a thumbnail. Needs GDAL's
Python bindings, numpy and (for thumbnails) Pillow.
"""
import argparse
import json
import os

import numpy as np
from osgeo import gdal, osr

STRIP = 512
# An overview edge passes when it is no darker than this share of what full resolution
# gives for the same ground, less a little for JPEG noise near black.
SHARE, SLACK = 0.85, 3.0


def edges(ds):
    """Per overview level: stored and expected brightness of the last row and last column."""
    width, height = ds.RasterXSize, ds.RasterYSize
    bottom = ds.ReadAsArray(0, height - STRIP, width, STRIP).astype(np.float32)   # bands, rows, cols
    right = ds.ReadAsArray(width - STRIP, 0, STRIP, height).astype(np.float32)
    out = []
    band = ds.GetRasterBand(1)
    for level in range(band.GetOverviewCount()):
        ov = band.GetOverview(level)
        ow, oh = ov.XSize, ov.YSize
        stored = np.stack([ds.GetRasterBand(b).GetOverview(level).ReadAsArray(0, oh - 1, ow, 1)
                           for b in (1, 2, 3)]).mean()
        first = int((oh - 1) * height / oh) - (height - STRIP)
        row = {"stored": round(float(stored), 2), "full_resolution": round(float(bottom[:, first:, :].mean()), 2)}
        stored = np.stack([ds.GetRasterBand(b).GetOverview(level).ReadAsArray(ow - 1, 0, 1, oh)
                           for b in (1, 2, 3)]).mean()
        first = int((ow - 1) * width / ow) - (width - STRIP)
        col = {"stored": round(float(stored), 2), "full_resolution": round(float(right[:, :, first:].mean()), 2)}
        for edge in (row, col):
            edge["pass"] = edge["stored"] >= SHARE * edge["full_resolution"] - SLACK
        out.append({"level": level + 1, "last_row": row, "last_column": col})
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("receipts_dir")
    p.add_argument("out")
    p.add_argument("--thumbs")
    a = p.parse_args()
    gdal.UseExceptions()
    gdal.SetConfigOption("AWS_NO_SIGN_REQUEST", "YES")
    gdal.SetConfigOption("AWS_REGION", "us-west-2")
    geographic = osr.SpatialReference()
    geographic.ImportFromEPSG(4326)
    geographic.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    if a.thumbs:
        from PIL import Image
        os.makedirs(a.thumbs, exist_ok=True)

    results = []
    for name in sorted(os.listdir(a.receipts_dir)):
        with open(os.path.join(a.receipts_dir, name)) as f:
            receipt = json.load(f)
        bucket, key = receipt["out_uri"].split("/", 3)[2:]
        ds = gdal.Open(f"/vsis3/{bucket}/{key}")
        levels = edges(ds)
        gt = ds.GetGeoTransform()
        projected = osr.SpatialReference(wkt=ds.GetProjection())
        lon, lat, _ = osr.CoordinateTransformation(projected, geographic).TransformPoint(
            gt[0] + gt[1] * ds.RasterXSize / 2, gt[3] + gt[5] * ds.RasterYSize / 2)
        smallest = np.stack([ds.GetRasterBand(b).GetOverview(len(levels) - 1).ReadAsArray() for b in (1, 2, 3)], -1)
        full = np.stack([ds.GetRasterBand(b).GetOverview(2).ReadAsArray() for b in (1, 2, 3)], -1)
        result = {
            "id": receipt["id"], "key": key, "lon": round(lon, 4), "lat": round(lat, 4),
            "receipt_edge_ratios": receipt["output"]["overview_edges"],
            "black_share": round(float((full.sum(-1) == 0).mean()), 4),
            "levels": levels,
            "pass": all(l[e]["pass"] for l in levels for e in ("last_row", "last_column")),
        }
        results.append(result)
        if a.thumbs:
            Image.fromarray(smallest).save(os.path.join(a.thumbs, receipt["id"] + ".jpg"), quality=80)
        print(receipt["id"], "pass" if result["pass"] else "FAIL", "black", result["black_share"], flush=True)
    with open(a.out, "w") as f:
        json.dump({"share": SHARE, "slack": SLACK, "files": len(results),
                   "passed": sum(r["pass"] for r in results), "results": results}, f, indent=1)
        f.write("\n")
    print(sum(r["pass"] for r in results), "of", len(results), "pass")


if __name__ == "__main__":
    main()
