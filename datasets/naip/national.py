#!/usr/bin/env python3
"""Build the national overview file from the state overview files.

One Web Mercator picture on the standard zoom grid, written as a JPEG COG with a mask. Each
state file is read at a reduced level, reprojected on one thread with a coverage band beside
the colour, and pasted onto one canvas, a later source over an earlier one.

    WORK_BUCKET=<bucket> REQUEST_KEY=<key of the request> python3 national.py
    REQUEST_FILE=request.json OUT_DIR=<dir> python3 national.py        # local, nothing uploaded

Request (make_national_request.py writes it):
    {"bucket": "<bucket of the state files>", "name": "national-latest", "res": 305.748, "read_m": 153.6,
     "out_key": "...", "result_key": "...", "quads": [[name, key, epsg, pixel size], ...]}   oldest first

Why a coverage band: reprojecting with a no-data value darkens every pixel that a source
only partly covers, which drew a dark line along each zone's edge (Vermont, 2026-11-14).
With a coverage band the colour is the average of the pixels that have a picture, and a
pixel less than COVERED covered is left to the source beneath.

Needs GDAL's Python bindings, numpy and (for S3) boto3, all in the converter image.
"""
import concurrent.futures
import json
import math
import os
import random
import resource
import tempfile
import time

import numpy as np
from osgeo import gdal

gdal.UseExceptions()
BLOCK = 512
COVERED = 128        # of 255: a pixel at least half covered by a source takes that source's colour
WINDOWS = 200
QUALITY = int(os.environ.get("QUALITY", "75"))
THREADS = int(os.environ.get("THREADS", "8"))


def read(bucket, source, read_m):
    """One state file's reduced level in memory, with its mask as a fourth band."""
    name, key, epsg, pixel = source
    path = f"/vsis3/{bucket}/{key}"
    whole = gdal.Open(path)
    level = min(round(math.log2(read_m / pixel)) - 1, whole.GetRasterBand(1).GetOverviewCount() - 1)
    src = gdal.OpenEx(path, gdal.OF_RASTER, open_options=[f"OVERVIEW_LEVEL={level}"]) if level >= 0 else whole
    mem = gdal.GetDriverByName("MEM").Create("", src.RasterXSize, src.RasterYSize, 4, gdal.GDT_Byte)
    mem.SetGeoTransform(src.GetGeoTransform())
    mem.SetProjection(src.GetProjection())
    mem.WriteArray(np.concatenate([src.ReadAsArray()[:3], src.GetRasterBand(1).GetMaskBand().ReadAsArray()[None]]))
    mem.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
    return name, mem


def placed(mem, res):
    """The source on the national grid: colour, coverage (0 to 255), and its pixel offset from the grid's origin."""
    probe = gdal.Warp("", mem, format="VRT", dstSRS="EPSG:3857")
    gt = probe.GetGeoTransform()
    x0, y1 = math.floor(gt[0] / res), math.ceil(gt[3] / res)
    x1 = math.ceil((gt[0] + gt[1] * probe.RasterXSize) / res)
    y0 = math.floor((gt[3] + gt[5] * probe.RasterYSize) / res)
    out = gdal.Warp("", mem, format="MEM", dstSRS="EPSG:3857", xRes=res, yRes=res,
                    outputBounds=(x0 * res, y0 * res, x1 * res, y1 * res), resampleAlg="average",
                    srcAlpha=True, dstAlpha=True, warpOptions=["NUM_THREADS=1"]).ReadAsArray()
    return out[:3], out[3], x0, y1


def psnr(a, b, valid):
    out = []
    for band in range(3):
        diff = a[band].astype(np.float64)[valid] - b[band].astype(np.float64)[valid]
        mse = float((diff ** 2).mean())
        out.append(99.0 if mse == 0 else round(10 * math.log10(255 ** 2 / mse), 2))
    return out


def main():
    local = os.environ.get("REQUEST_FILE")
    if local:
        with open(local) as f:
            request = json.load(f)
    else:
        import boto3
        s3 = boto3.client("s3")
        work = os.environ["WORK_BUCKET"]
        request = json.loads(s3.get_object(Bucket=work, Key=os.environ["REQUEST_KEY"])["Body"].read())
    res, started, seconds = request["res"], time.monotonic(), {}

    def lap(name):
        nonlocal started
        seconds[name] = round(time.monotonic() - started, 1)
        started = time.monotonic()
        print(name, seconds[name], "s", flush=True)

    print(request["name"], len(request["quads"]), "state files", flush=True)
    with concurrent.futures.ThreadPoolExecutor(THREADS) as pool:
        sources = list(pool.map(lambda s: read(request["bucket"], s, request["read_m"]), request["quads"]))
    lap("read_sources")

    pieces = [(name, *placed(mem, res)) for name, mem in sources]      # in the request's order, one thread each
    step = BLOCK
    left = math.floor(min(p[3] for p in pieces) / step) * step
    top = math.ceil(max(p[4] for p in pieces) / step) * step
    right = math.ceil(max(p[3] + p[1].shape[2] for p in pieces) / step) * step
    bottom = math.floor(min(p[4] - p[1].shape[1] for p in pieces) / step) * step
    width, height = right - left, top - bottom
    canvas = np.zeros((4, height, width), np.uint8)
    shown = {}
    for name, colour, coverage, x0, y1 in pieces:
        h, w = coverage.shape
        row, col = top - y1, x0 - left
        take = coverage >= COVERED
        window = canvas[:, row:row + h, col:col + w]
        window[:3][:, take] = colour[:, take]
        window[3][take] = 255
        shown[name] = int(take.sum())
    lap("place")

    folder = tempfile.mkdtemp(prefix="national-", dir=os.environ.get("OUT_DIR"))
    mem = gdal.GetDriverByName("MEM").Create("", width, height, 4, gdal.GDT_Byte)
    mem.SetGeoTransform((left * res, res, 0, top * res, 0, -res))
    mem.SetProjection(gdal.Warp("", sources[0][1], format="VRT", dstSRS="EPSG:3857").GetProjection())
    mem.WriteArray(canvas)
    mem.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
    out = os.path.join(folder, request["name"] + ".tif")
    gdal.Translate(out, mem, format="COG", creationOptions=[
        "COMPRESS=JPEG", f"QUALITY={QUALITY}", f"OVERVIEW_QUALITY={QUALITY}", f"BLOCKSIZE={BLOCK}",
        "OVERVIEW_RESAMPLING=AVERAGE", "BIGTIFF=IF_SAFER", "NUM_THREADS=ALL_CPUS"])
    lap("write_file")

    ds = gdal.Open(out)
    band = ds.GetRasterBand(1)
    structure = ds.GetMetadata("IMAGE_STRUCTURE")
    mask = band.GetMaskBand().ReadAsArray()
    rng, windows = random.Random(20261114), []
    for _ in range(40 * WINDOWS):
        if len(windows) == WINDOWS:
            break
        x, y = rng.randrange(width // BLOCK) * BLOCK, rng.randrange(height // BLOCK) * BLOCK
        valid = canvas[3, y:y + BLOCK, x:x + BLOCK] > 0
        if valid.mean() < 0.5:
            continue
        windows.append(psnr(ds.ReadAsArray(x, y, BLOCK, BLOCK), canvas[:3, y:y + BLOCK, x:x + BLOCK], valid))
    dark = (canvas[:3].max(0) <= 8) & (canvas[3] > 0)
    result = {
        "name": request["name"], "gdal": gdal.__version__, "target_epsg": 3857, "res": res, "read_m": request["read_m"],
        "sources": len(sources), "bytes": os.path.getsize(out),
        "bounds": [left * res, bottom * res, right * res, top * res], "seconds": seconds,
        "file": {
            "size": [width, height],
            "levels": [[band.GetOverview(i).XSize, band.GetOverview(i).YSize] for i in range(band.GetOverviewCount())],
            "layout": structure.get("LAYOUT"), "compression": structure.get("COMPRESSION"), "block": list(band.GetBlockSize()),
            "bands": ds.RasterCount, "mask_per_dataset": bool(band.GetMaskFlags() & gdal.GMF_PER_DATASET),
            "mask_matches_canvas": float(((mask > 0) == (canvas[3] > 0)).mean()),
            "windows": {"count": len(windows), "lowest_db": [min(w[b] for w in windows) for b in range(3)],
                        "median_db": [sorted(w[b] for w in windows)[len(windows) // 2] for b in range(3)]},
        },
        "covered_share": round(float((canvas[3] > 0).mean()), 4),
        "dark_share_of_covered": round(float(dark.sum() / max(1, (canvas[3] > 0).sum())), 6),
        "sources_showing_nothing": sorted(n for n, count in shown.items() if count == 0),
        "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    lap("check")
    result["seconds"] = seconds
    if local:
        with open(os.path.join(folder, "result.json"), "w") as f:
            json.dump(result, f, indent=1)
    else:
        s3.upload_file(out, work, request["out_key"], ExtraArgs={"ContentType": "image/tiff; application=geotiff; profile=cloud-optimized"})
        s3.put_object(Bucket=work, Key=request["result_key"], Body=json.dumps(result, indent=1).encode(), ContentType="application/json")
        print("written", request["out_key"], result["bytes"], "bytes", flush=True)
    print(json.dumps({k: v for k, v in result.items() if k != "file"}), folder if local else "", flush=True)


if __name__ == "__main__":
    main()
