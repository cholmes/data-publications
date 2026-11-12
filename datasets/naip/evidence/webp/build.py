#!/usr/bin/env python3
"""One quad as JPEG and WebP COGs at several qualities, each level compared with a lossless
COG of the same quad. For the pass marks in VALIDATION.md ("WebP against JPEG").

    AWS_REGION=us-west-2 python3 build.py <state/year/res/rgbir/block/name.mrf> <work dir> > result.json
Keeps <work dir>/jpeg-65-85.tif, jpeg-65-65.tif and every webp file for the reader tests.
"""
import json, os, resource, sys, time
import numpy as np
from osgeo import gdal
gdal.UseExceptions()
gdal.SetPathSpecificOption("/vsis3/naip-analytic", "AWS_REQUEST_PAYER", "requester")
key, work = sys.argv[1], sys.argv[2]
COMMON = ["BLOCKSIZE=512", "OVERVIEW_RESAMPLING=AVERAGE", "OVERVIEWS=IGNORE_EXISTING", "NUM_THREADS=1"]
src = f"{work}/source.tif"
if not os.path.exists(src):
    gdal.Translate(src, "/vsis3/naip-analytic/" + key, bandList=[1, 2, 3], creationOptions=["TILED=YES", "COMPRESS=ZSTD", "BIGTIFF=YES"])
truth_path = f"{work}/lossless.tif"
gdal.Translate(truth_path, src, format="COG", creationOptions=["COMPRESS=ZSTD"] + COMMON)

def levels(path):
    ds = gdal.Open(path); band = ds.GetRasterBand(1)
    return [ds.ReadAsArray()] + [np.stack([ds.GetRasterBand(i).GetOverview(k).ReadAsArray() for i in (1, 2, 3)]) for k in range(band.GetOverviewCount())]

def level_bytes(path):
    out, ds = [], gdal.Open(path)
    band = ds.GetRasterBand(1)
    for k in range(band.GetOverviewCount() + 1):
        b = band if k == 0 else band.GetOverview(k - 1)
        bx, by = b.GetBlockSize()
        out.append(sum(int(b.GetMetadataItem(f"BLOCK_SIZE_{x}_{y}", "TIFF") or 0) for y in range(-(-b.YSize // by)) for x in range(-(-b.XSize // bx))))
    return out

def psnr(a, b):
    mse = ((a.astype(np.float64) - b) ** 2).reshape(3, -1).mean(axis=1)
    return [round(float(10 * np.log10(255 ** 2 / m)), 2) for m in mse]

truth = levels(truth_path)
BUILDS = [("jpeg-65-65", "JPEG", 65, 65), ("jpeg-65-75", "JPEG", 65, 75), ("jpeg-65-85", "JPEG", 65, 85)] + \
         [(f"webp-{q}", "WEBP", q, q) for q in (50, 60, 70, 75, 80, 85)]
result = {"quad": key, "megapixels": round(truth[0].shape[1] * truth[0].shape[2] / 1e6, 1), "builds": {}}
for name, codec, q, oq in BUILDS:
    path = f"{work}/{name}.tif"
    t0 = time.process_time(); w0 = time.monotonic()
    gdal.Translate(path, src, format="COG", creationOptions=[f"COMPRESS={codec}", f"QUALITY={q}", f"OVERVIEW_QUALITY={oq}"] + COMMON)
    encode_cpu, encode_wall = time.process_time() - t0, time.monotonic() - w0
    t0 = time.process_time()
    got = levels(path)
    decode_cpu = time.process_time() - t0
    ds = gdal.Open(path)
    result["builds"][name] = {"codec": codec, "quality": q, "overview_quality": oq, "file_bytes": os.path.getsize(path),
        "level_bytes": level_bytes(path), "psnr_db_by_level": [psnr(t, g) for t, g in zip(truth, got)],
        "encode_cpu_s": round(encode_cpu, 1), "encode_wall_s": round(encode_wall, 1), "decode_all_levels_cpu_s": round(decode_cpu, 2),
        "layout": ds.GetMetadataItem("LAYOUT", "IMAGE_STRUCTURE"), "block": ds.GetRasterBand(1).GetBlockSize(),
        "overviews": ds.GetRasterBand(1).GetOverviewCount()}
    print(name, result["builds"][name]["file_bytes"], result["builds"][name]["psnr_db_by_level"][0], file=sys.stderr, flush=True)
    if name == "jpeg-65-75":
        os.remove(path)
os.remove(truth_path); os.remove(src)
json.dump(result, sys.stdout, indent=1)
