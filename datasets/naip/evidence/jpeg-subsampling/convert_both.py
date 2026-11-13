#!/usr/bin/env python3
"""Convert one lossless NAIP quad to RGB JPEG COGs with halved and with full colour resolution,
using the patched GDAL (JPEG_YCBCR_SUBSAMPLING), and record size, time and error.

    python3 convert_both.py <source.mrf> <out dir> <name>

Writes <out dir>/<name>-420.tif, <name>-444.tif and <name>.json. PSNR is against the lossless
source at full resolution, overall and for colour only (Cb, Cr).
"""
import json, os, sys, time
import numpy as np
from osgeo import gdal
gdal.UseExceptions()
src_path, out, name = sys.argv[1:4]
src = gdal.Open(src_path)
ref = src.ReadAsArray()[:3].astype(np.float32)
def cbcr(a):
    r, g, b = a
    return np.stack([-0.168736 * r - 0.331264 * g + 0.5 * b, 0.5 * r - 0.418688 * g - 0.081312 * b])
def psnr(a, b):
    return round(float(10 * np.log10(255 ** 2 / ((a - b) ** 2).mean())), 2)
result = {"gdal": gdal.__version__, "source": os.path.basename(src_path), "megapixels": round(src.RasterXSize * src.RasterYSize / 1e6, 1)}
for code, sub in (("420", "4:2:0"), ("444", "4:4:4")):
    path = f"{out}/{name}-{code}.tif"
    wall, cpu = time.monotonic(), time.process_time()
    gdal.Translate(path, src, format="COG", bandList=[1, 2, 3], creationOptions=[
        "COMPRESS=JPEG", "QUALITY=65", "OVERVIEW_QUALITY=75", "BLOCKSIZE=512", "OVERVIEW_RESAMPLING=AVERAGE",
        "OVERVIEWS=IGNORE_EXISTING", "NUM_THREADS=1", f"JPEG_YCBCR_SUBSAMPLING={sub}"])
    wall, cpu = time.monotonic() - wall, time.process_time() - cpu
    ds = gdal.Open(path)
    got = ds.ReadAsArray().astype(np.float32)
    result[code] = {"bytes": os.path.getsize(path), "convert_wall_s": round(wall, 1), "convert_cpu_s": round(cpu, 1),
                    "megapixels_per_cpu_s": round(result["megapixels"] / cpu, 1),
                    "psnr_db": psnr(ref, got), "colour_psnr_db": psnr(cbcr(ref), cbcr(got)),
                    "overviews": ds.GetRasterBand(1).GetOverviewCount(), "layout": ds.GetMetadataItem("LAYOUT", "IMAGE_STRUCTURE")}
result["444_over_420_bytes"] = round(result["444"]["bytes"] / result["420"]["bytes"], 3)
json.dump(result, open(f"{out}/{name}.json", "w"), indent=1)
print(json.dumps(result, indent=1))
