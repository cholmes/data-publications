#!/usr/bin/env python3
"""Build one overview file for a state-year from the reduced levels of its hosted quads.

A wide view of the product opens one file per quad. This writes a single file that holds the
whole state at reduced resolution: every quad's reduced level is read from the hosted file,
its black border (where it has one) is marked as holding no picture, the quads are warped
onto one grid and mosaicked, and the result is written as a JPEG COG with a mask.

    WORK_BUCKET=<bucket> REQUEST_KEY=_overviews/<name>-request.json python3 overview.py
    REQUEST_FILE=request.json OUT_DIR=<dir> python3 overview.py        # local, nothing uploaded

Request:
    {"bucket": "<product bucket>", "name": "nv-2024-utm-9.6",
     "target_epsg": 26911, "res": 9.6, "read_m": 9.6,
     "out_key": "<key in the work bucket>", "result_key": "<key in the work bucket>",
     "quads": [[id, key, epsg, gsd], ...], "collar_ids": [ids of the black-edged quads]}

`res` is the pixel size of the finest level in the target grid's own units; `read_m` is the
quad level to read. The file's bounds are snapped outward to 512 pixels, so every reduced
level is an exact halving of the one before.

Needs GDAL's Python bindings, numpy and (for S3) boto3, all in the converter image.
"""
import concurrent.futures
import json
import math
import os
import random
import resource
import shutil
import tempfile
import time

import numpy as np
from osgeo import gdal, osr

gdal.UseExceptions()
BLOCK = 512
NEAR = 6            # grey levels a border pixel may be from black
WIDEN = 2           # pixels the border is widened by, to take the JPEG fringe with it
DARK = 8            # a pixel at most this in all bands counts as black in the checks
WINDOWS = 200
QUALITY = int(os.environ.get("QUALITY", "75"))
THREADS = int(os.environ.get("THREADS", "16"))


def stage(bucket, quad, read_m, folder):
    """One quad's reduced level as a local file: 0 in all bands where there is no picture."""
    name, key, epsg, gsd = quad
    level = round(math.log2(read_m / gsd)) - 1
    src = gdal.OpenEx(f"/vsis3/{bucket}/{key}", gdal.OF_RASTER, open_options=[f"OVERVIEW_LEVEL={level}"])
    marked = gdal.Nearblack("", gdal.Translate("", src, format="MEM"), format="MEM", nearDist=NEAR, setAlpha=True)
    pixels = marked.ReadAsArray()
    valid = pixels[3] > 0
    border = not valid.all()
    for _ in range(WIDEN if border else 0):
        grown = valid.copy()
        grown[1:] &= valid[:-1]
        grown[:-1] &= valid[1:]
        grown[:, 1:] &= valid[:, :-1]
        grown[:, :-1] &= valid[:, 1:]
        valid = grown
    rgb = np.maximum(pixels[:3], 1)          # a real pixel is never 0, so 0 can mean "no picture"
    rgb[:, ~valid] = 0
    path = os.path.join(folder, name + ".tif")
    out = gdal.GetDriverByName("GTiff").Create(path, src.RasterXSize, src.RasterYSize, 3, gdal.GDT_Byte,
                                               ["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES"])
    out.SetGeoTransform(src.GetGeoTransform())
    out.SetProjection(src.GetProjection())
    out.WriteArray(rgb)
    for band in (1, 2, 3):
        out.GetRasterBand(band).SetNoDataValue(0)
    out = None
    gt = src.GetGeoTransform()
    corners = [(gt[0] + gt[1] * x, gt[3] + gt[5] * y)
               for x, y in ((0, 0), (src.RasterXSize, 0), (src.RasterXSize, src.RasterYSize), (0, src.RasterYSize))]
    return {"id": name, "path": path, "epsg": int(epsg), "corners": corners, "border": bool(border)}


def to_target(staged, target_epsg):
    """Each staged quad's corners in the target grid."""
    target = osr.SpatialReference()
    target.ImportFromEPSG(target_epsg)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transforms = {}
    for quad in staged:
        if quad["epsg"] not in transforms:
            source = osr.SpatialReference()
            source.ImportFromEPSG(quad["epsg"])
            source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            transforms[quad["epsg"]] = osr.CoordinateTransformation(source, target)
        quad["target"] = [transforms[quad["epsg"]].TransformPoint(x, y)[:2] for x, y in quad["corners"]]


def mosaic(staged, target_epsg, res, folder):
    """A lazy mosaic of the staged quads on the target grid, with an alpha band. Returns its path and bounds."""
    step = BLOCK * res
    xs = [x for q in staged for x, _ in q["target"]]
    ys = [y for q in staged for _, y in q["target"]]
    bounds = (math.floor(min(xs) / step) * step, math.floor(min(ys) / step) * step,
              math.ceil(max(xs) / step) * step, math.ceil(max(ys) / step) * step)
    zones = {}
    for quad in staged:
        zones.setdefault(quad["epsg"], []).append(quad["path"])
    main = max(zones, key=lambda e: len(zones[e]))
    warped = []
    for epsg in sorted(zones, key=lambda e: (e == main, e)):      # the main zone last, so it lies on top
        together = os.path.join(folder, f"zone-{epsg}.vrt")
        gdal.BuildVRT(together, zones[epsg], srcNodata=0, VRTNodata=0)
        path = os.path.join(folder, f"zone-{epsg}-warped.vrt")
        gdal.Warp(path, together, format="VRT", dstSRS=f"EPSG:{target_epsg}", xRes=res, yRes=res,
                  outputBounds=bounds, resampleAlg="bilinear", srcNodata=0, dstNodata=0,
                  multithread=True, warpOptions=["NUM_THREADS=ALL_CPUS"])
        warped.append(path)
    joined = os.path.join(folder, "joined.vrt")
    gdal.BuildVRT(joined, warped, srcNodata=0, VRTNodata=0)
    final = os.path.join(folder, "mosaic.vrt")
    gdal.Warp(final, joined, format="VRT", xRes=res, yRes=res, outputBounds=bounds, resampleAlg="near",
              srcNodata=0, dstAlpha=True)
    return final, bounds, {str(e): len(v) for e, v in zones.items()}


def psnr(a, b, valid):
    """Per band, over the pixels both have a picture for."""
    out = []
    for band in range(3):
        diff = a[band].astype(np.float64)[valid] - b[band].astype(np.float64)[valid]
        mse = float((diff ** 2).mean())
        out.append(99.0 if mse == 0 else round(10 * math.log10(255 ** 2 / mse), 2))
    return out


def check(path, mosaic_path, staged, bounds, res, collar_ids):
    """The checks that need the mosaic or the staged quads: marks 1 to 4 of the test."""
    ds, before = gdal.Open(path), gdal.Open(mosaic_path)
    width, height = ds.RasterXSize, ds.RasterYSize
    band = ds.GetRasterBand(1)
    structure = ds.GetMetadata("IMAGE_STRUCTURE")
    levels = [[band.GetOverview(i).XSize, band.GetOverview(i).YSize] for i in range(band.GetOverviewCount())]
    smallest = band.GetOverview(band.GetOverviewCount() - 1)
    found = {
        "size": [width, height], "levels": levels, "layout": structure.get("LAYOUT"),
        "compression": structure.get("COMPRESSION"), "block": list(band.GetBlockSize()),
        "bands": ds.RasterCount, "mask_per_dataset": bool(band.GetMaskFlags() & gdal.GMF_PER_DATASET),
        "reads": band.ReadRaster(width // 2, height // 2, BLOCK, BLOCK) is not None
                 and smallest.ReadRaster(0, 0, smallest.XSize, smallest.YSize) is not None,
    }

    # Mark 2: windows of the file against the mosaic before encoding.
    rng, windows = random.Random(20261114), []
    for _ in range(40 * WINDOWS):
        if len(windows) == WINDOWS:
            break
        x, y = rng.randrange(width // BLOCK) * BLOCK, rng.randrange(height // BLOCK) * BLOCK
        want = before.ReadAsArray(x, y, BLOCK, BLOCK)
        valid = want[3] > 0
        if valid.mean() < 0.5:
            continue
        windows.append(psnr(ds.ReadAsArray(x, y, BLOCK, BLOCK), want, valid))
    found["windows"] = {"count": len(windows),
                        "lowest_db": [min(w[b] for w in windows) for b in range(3)] if windows else None,
                        "median_db": [sorted(w[b] for w in windows)[len(windows) // 2] for b in range(3)] if windows else None}

    # Marks 3 and 4: every quad's centre, and black inside every quad's bounding window, at about 10 m.
    mask = band.GetMaskBand()
    shrink = max(1, round(9.6 / res)) if res < 30 else 1
    centres_masked, quads = [], []
    for quad in staged:
        xs = [(x - bounds[0]) / res for x, _ in quad["target"]]
        ys = [(bounds[3] - y) / res for _, y in quad["target"]]
        cx, cy = int(sum(xs) / 4), int(sum(ys) / 4)
        if mask.ReadAsArray(cx, cy, 1, 1)[0, 0] == 0:
            centres_masked.append(quad["id"])
        x0, y0 = max(0, int(min(xs))), max(0, int(min(ys)))
        w, h = min(width, int(max(xs)) + 1) - x0, min(height, int(max(ys)) + 1) - y0
        bw, bh = max(1, w // shrink), max(1, h // shrink)
        rgb = ds.ReadAsArray(x0, y0, w, h, buf_xsize=bw, buf_ysize=bh)
        seen = mask.ReadAsArray(x0, y0, w, h, buf_xsize=bw, buf_ysize=bh) > 0
        quads.append({"id": quad["id"], "border": quad["border"],
                      "black_share": round(float((seen & (rgb.max(0) <= DARK)).mean()), 5),
                      "masked_share": round(float((~seen).mean()), 5)})
    collar = [q for q in quads if q["id"] in collar_ids]
    found["centres_masked"] = centres_masked
    found["black"] = {
        "collar_quads": len(collar),
        "collar_highest_share": max((q["black_share"] for q in collar), default=None),
        "other_highest_share": max((q["black_share"] for q in quads if q["id"] not in collar_ids), default=None),
        "quads_with_a_border_found": sum(q["border"] for q in quads),
        "masked_share_mean": round(sum(q["masked_share"] for q in quads) / len(quads), 5),
        "worst": sorted(quads, key=lambda q: -q["black_share"])[:10],
    }
    return found


def main():
    local = os.environ.get("REQUEST_FILE")
    if local:
        with open(local) as f:
            request = json.load(f)
    else:
        import boto3
        s3, work = boto3.client("s3"), os.environ["WORK_BUCKET"]
        request = json.loads(s3.get_object(Bucket=work, Key=os.environ["REQUEST_KEY"])["Body"].read())
    for key, value in {"AWS_NO_SIGN_REQUEST": "YES", "AWS_REGION": "us-west-2", "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
                       "CPL_VSIL_NETWORK_STATS_ENABLED": "YES", "GDAL_MAX_DATASET_POOL_SIZE": "400",
                       "GDAL_CACHEMAX": os.environ.get("GDAL_CACHEMAX", "2048"), "GDAL_NUM_THREADS": "ALL_CPUS"}.items():
        gdal.SetConfigOption(key, value)
    folder = tempfile.mkdtemp(prefix="overview-", dir=os.environ.get("OUT_DIR"))
    clock, seconds = time.monotonic(), {}

    def lap(name):
        nonlocal clock
        seconds[name], clock = round(time.monotonic() - clock, 1), time.monotonic()
        print(name, seconds[name], "s", flush=True)

    quads = sorted(request["quads"])
    print(request["name"], len(quads), "quads", flush=True)
    os.makedirs(f"{folder}/quads")
    with concurrent.futures.ThreadPoolExecutor(THREADS) as pool:
        staged = list(pool.map(lambda q: stage(request["bucket"], q, request["read_m"], f"{folder}/quads"), quads))
    network = json.loads(gdal.NetworkStatsGetAsSerializedJSON()).get("methods", {}).get("GET", {})
    staged_bytes = sum(os.path.getsize(q["path"]) for q in staged)
    lap("read_quads")

    to_target(staged, request["target_epsg"])
    mosaic_path, bounds, zones = mosaic(staged, request["target_epsg"], request["res"], folder)
    out = os.path.join(folder, request["name"] + ".tif")
    options = ["COMPRESS=JPEG", f"QUALITY={QUALITY}", f"OVERVIEW_QUALITY={QUALITY}", f"BLOCKSIZE={BLOCK}",
               "OVERVIEW_RESAMPLING=AVERAGE", "BIGTIFF=YES"]
    retried = None
    try:
        gdal.Translate(out, mosaic_path, format="COG", creationOptions=options + ["NUM_THREADS=ALL_CPUS"])
    except RuntimeError as error:
        # GDAL 3.13.1 with GDAL_NUM_THREADS=ALL_CPUS fails every time on a narrow mosaic (seen on
        # 2,048 by 28,160 pixels: "ZSTDDecode ... Unknown frame descriptor" from its temporary
        # overview file). One thread writes the same file correctly, and such files are small.
        retried = str(error)[:200]
        print("write failed with all threads, writing again with one:", retried, flush=True)
        for name in os.listdir(folder):
            if name.startswith(request["name"] + ".tif"):
                os.remove(os.path.join(folder, name))
        gdal.SetConfigOption("GDAL_NUM_THREADS", "1")
        gdal.Translate(out, mosaic_path, format="COG", creationOptions=options)
        gdal.SetConfigOption("GDAL_NUM_THREADS", "ALL_CPUS")
    lap("write_file")

    found = check(out, mosaic_path, staged, bounds, request["res"], set(request.get("collar_ids", [])))
    lap("check")
    result = {
        "name": request["name"], "gdal": gdal.__version__, "target_epsg": request["target_epsg"],
        "res": request["res"], "read_m": request["read_m"], "quads": len(quads), "zones": zones,
        "bounds": bounds, "bytes": os.path.getsize(out), "file": found, "seconds": seconds,
        "quad_requests": network.get("count"), "quad_bytes_read": network.get("downloaded_bytes"),
        "staged_bytes": staged_bytes, "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "write_retried_with_one_thread": retried,
    }
    if local:
        with open(os.path.join(folder, "result.json"), "w") as f:
            json.dump(result, f, indent=1)
        print(json.dumps({k: v for k, v in result.items() if k != "file"}), folder, flush=True)
        return
    s3.upload_file(out, work, request["out_key"], ExtraArgs={"ContentType": "image/tiff; application=geotiff; profile=cloud-optimized"})
    s3.put_object(Bucket=work, Key=request["result_key"], Body=json.dumps(result).encode())
    shutil.rmtree(folder)
    print("written", request["out_key"], result["bytes"], "bytes", flush=True)


if __name__ == "__main__":
    main()
