#!/usr/bin/env python3
"""Several overview files of one state-year against a reference none of them was built from.

    python3 check_overview_against_full_resolution.py <naip stac index.parquet> <state> <year> \
        [--sample N] [--zone EPSG] <label>=<overview file or https url> ...

The reference: each sampled quad read at full resolution from the hosted file and averaged
onto the first file's grid on one thread. Every file must share that grid. Blocks of 128
pixels whose centre is at least INSET metres inside the quad are compared (the quad's edge
overlaps its neighbours, and which quad a file took there is not this check's question).
Reports median and lowest PSNR per band for each label, on the same blocks.
"""
import argparse
import json
import math
import random

import numpy as np
import pyarrow.parquet as pq
from osgeo import gdal, osr

gdal.UseExceptions()
gdal.SetConfigOption("GDAL_NUM_THREADS", "1")
gdal.SetConfigOption("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
BLOCK = 128
INSET = 480.0


def opened(path):
    return gdal.Open(("/vsicurl/" if path.startswith("http") else "") + path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("index")
    p.add_argument("state")
    p.add_argument("year", type=int)
    p.add_argument("files", nargs="+", metavar="label=file")
    p.add_argument("--sample", type=int, default=12)
    p.add_argument("--zone", type=int)
    a = p.parse_args()
    files = [(label, opened(path)) for label, path in (f.split("=", 1) for f in a.files)]
    first = files[0][1]
    fgt, res = first.GetGeoTransform(), first.GetGeoTransform()[1]
    for label, ds in files:
        if ds.GetGeoTransform() != fgt or (ds.RasterXSize, ds.RasterYSize) != (first.RasterXSize, first.RasterYSize):
            raise SystemExit(f"{label} is not on the grid of {files[0][0]}")
    srs = osr.SpatialReference(wkt=first.GetProjection())
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    with open(a.index, "rb") as f:
        rows = pq.ParquetFile(f).read(columns=["id", "naip:state", "naip:year", "proj:epsg", "assets"]).to_pylist()
    quads = sorted((r["id"], r["assets"]["image"]["href"]) for r in rows
                   if r["naip:state"] == a.state and r["naip:year"] == a.year and a.zone in (None, r["proj:epsg"]))
    chosen = random.Random(20261114).sample(quads, min(a.sample, len(quads)))
    scores = {label: [] for label, _ in files}
    used = []
    for quad_id, href in chosen:
        quad = opened(href)
        qgt, qsrs = quad.GetGeoTransform(), osr.SpatialReference(wkt=quad.GetProjection())
        qsrs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        x0, y1 = qgt[0] + INSET, qgt[3] - INSET
        x1, y0 = qgt[0] + qgt[1] * quad.RasterXSize - INSET, qgt[3] + qgt[5] * quad.RasterYSize + INSET
        xs, ys, _ = zip(*osr.CoordinateTransformation(qsrs, srs).TransformPoints([(x, y) for x in (x0, x1) for y in (y0, y1)]))
        # The largest window of whole blocks inside the inset quad, on the file's grid.
        c0, c1 = math.ceil((max(xs[:2]) - fgt[0]) / res), math.floor((min(xs[2:]) - fgt[0]) / res)
        r0, r1 = math.ceil((fgt[3] - min(ys[1], ys[3])) / res), math.floor((fgt[3] - max(ys[0], ys[2])) / res)
        nx, ny = (c1 - c0) // BLOCK, (r1 - r0) // BLOCK
        if nx < 1 or ny < 1:
            continue
        w, h = nx * BLOCK, ny * BLOCK
        bounds = (fgt[0] + c0 * res, fgt[3] - (r0 + h) * res, fgt[0] + (c0 + w) * res, fgt[3] - r0 * res)
        reference = gdal.Warp("", quad, format="MEM", dstSRS=first.GetProjection(), outputBounds=bounds, width=w, height=h,
                              resampleAlg="average", overviewLevel="NONE",      # or GDAL reads a reduced level
                              warpOptions=["NUM_THREADS=1"]).ReadAsArray()[:3].astype(np.float32)
        used.append({"id": quad_id, "blocks": nx * ny})
        for label, ds in files:
            got = ds.ReadAsArray(c0, r0, w, h)[:3].astype(np.float32)
            mse = ((got - reference) ** 2).reshape(3, ny, BLOCK, nx, BLOCK).mean(axis=(2, 4)).reshape(3, -1)
            scores[label].append(10 * np.log10(255 ** 2 / np.maximum(mse, 1e-9)))
    result = {"reference": "hosted quads at full resolution, averaged onto the file grid", "pixel_m": res,
              "quads": used, "blocks": sum(q["blocks"] for q in used), "files": {}}
    for label, _ in files:
        s = np.concatenate(scores[label], axis=1)
        result["files"][label] = {"median_db": [round(float(v), 2) for v in np.median(s, axis=1)],
                                  "lowest_db": [round(float(v), 2) for v in s.min(axis=1)]}
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
