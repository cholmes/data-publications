#!/usr/bin/env python3
"""One lossless quad as JPEG, WebP and JPEG XL COGs, each level compared with a lossless COG.

For the pass marks in VALIDATION.md ("JPEG XL against JPEG and WebP"). Needs a GDAL whose
GeoTIFF driver has JXL (conda-forge's does; Homebrew's 3.13.1 does not).

    python3 jxl_test.py <source.mrf or .tif> <work dir> <name> [--also <existing.tif> <label>]

Writes <work dir>/<name>-<build>.tif for every build and prints the result as JSON. --also
measures an existing file (the full-colour JPEG from the colour resolution test) the same way.
One thread throughout, so encode and decode times compare.
"""
import json
import os
import sys
import time

import numpy as np
from osgeo import gdal

gdal.UseExceptions()
gdal.SetConfigOption("GDAL_NUM_THREADS", "1")
COMMON = ["BLOCKSIZE=512", "OVERVIEW_RESAMPLING=AVERAGE", "OVERVIEWS=IGNORE_EXISTING", "NUM_THREADS=1", "BIGTIFF=IF_SAFER"]
BUILDS = [("jpeg-65-75", ["COMPRESS=JPEG", "QUALITY=65", "OVERVIEW_QUALITY=75"]),
          ("webp-50", ["COMPRESS=WEBP", "QUALITY=50", "OVERVIEW_QUALITY=50"]),
          ("webp-65", ["COMPRESS=WEBP", "QUALITY=65", "OVERVIEW_QUALITY=65"])] + \
         [(f"jxl-d{d}", ["COMPRESS=JXL", "JXL_LOSSLESS=NO", f"JXL_DISTANCE={d}", "JXL_EFFORT=5"])
          for d in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0)] + \
         [(f"jxl-d2.0-e{e}", ["COMPRESS=JXL", "JXL_LOSSLESS=NO", "JXL_DISTANCE=2.0", f"JXL_EFFORT={e}"]) for e in (3, 7)]


def levels(path):
    ds = gdal.Open(path)
    band = ds.GetRasterBand(1)
    return [ds.ReadAsArray()[:3]] + [np.stack([ds.GetRasterBand(i).GetOverview(k).ReadAsArray() for i in (1, 2, 3)])
                                     for k in range(band.GetOverviewCount())]


def cbcr(a):
    r, g, b = a.astype(np.float32)
    return np.stack([-0.168736 * r - 0.331264 * g + 0.5 * b, 0.5 * r - 0.418688 * g - 0.081312 * b])


def psnr(a, b):
    mse = ((a.astype(np.float32) - b.astype(np.float32)) ** 2).reshape(a.shape[0], -1).mean(axis=1, dtype=np.float64)
    return [round(float(10 * np.log10(255 ** 2 / m)), 2) for m in mse]


def measure(path, truth):
    t0 = time.process_time()
    got = levels(path)
    decode = time.process_time() - t0
    ds = gdal.Open(path)
    colour = psnr(cbcr(truth[0]), cbcr(got[0]))
    return {"file_bytes": os.path.getsize(path), "psnr_db_by_level": [psnr(t, g) for t, g in zip(truth, got)],
            "colour_psnr_db": round(float(10 * np.log10(255 ** 2 / np.mean([255 ** 2 / 10 ** (c / 10) for c in colour]))), 2),
            "decode_all_levels_cpu_s": round(decode, 2), "layout": ds.GetMetadataItem("LAYOUT", "IMAGE_STRUCTURE"),
            "compression": ds.GetMetadataItem("COMPRESSION", "IMAGE_STRUCTURE"),
            "block": ds.GetRasterBand(1).GetBlockSize(), "overviews": ds.GetRasterBand(1).GetOverviewCount()}


def main():
    source, work, name = sys.argv[1:4]
    os.makedirs(work, exist_ok=True)
    src = gdal.Translate("", source, format="MEM", bandList=[1, 2, 3])
    truth_path = f"{work}/{name}-lossless.tif"
    gdal.Translate(truth_path, src, format="COG", creationOptions=["COMPRESS=ZSTD"] + COMMON)
    truth = levels(truth_path)
    result = {"gdal": gdal.__version__, "source": os.path.basename(source),
              "megapixels": round(src.RasterXSize * src.RasterYSize / 1e6, 1), "builds": {}}
    for build, options in BUILDS:
        path = f"{work}/{name}-{build}.tif"
        cpu, wall = time.process_time(), time.monotonic()
        gdal.Translate(path, src, format="COG", creationOptions=options + COMMON)
        cpu, wall = time.process_time() - cpu, time.monotonic() - wall
        result["builds"][build] = {"options": options, "encode_cpu_s": round(cpu, 1), "encode_wall_s": round(wall, 1),
                                   **measure(path, truth)}
        print(build, result["builds"][build]["file_bytes"], result["builds"][build]["psnr_db_by_level"][0],
              result["builds"][build]["colour_psnr_db"], round(cpu, 1), file=sys.stderr, flush=True)
    if "--also" in sys.argv:
        path, label = sys.argv[sys.argv.index("--also") + 1:][:2]
        result["builds"][label] = {"options": "existing file", **measure(path, truth)}
    os.remove(truth_path)
    json.dump(result, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
