#!/usr/bin/env python3
"""Requests an anonymous reader makes to draw two wide views from an overview file.

    python3 check_overview.py <https url of the file> <latitude of the state> [--other <url>]

Reads through GDAL with range requests and counts them: a 1,280 by 800 pixel view 37 km
across at the file's centre, and a view of the whole file. With --other, also compares the
file's finest level with the second level of the other file on the same grid (PSNR on 200
windows of 512 pixels), for the question of reading a quad level against averaging a finer one.
"""
import argparse
import json
import math
import random

import numpy as np
from osgeo import gdal

gdal.UseExceptions()
VIEW = (1280, 800)


def counted(url, read):
    gdal.VSICurlClearCache()
    gdal.NetworkStatsReset()
    ds = gdal.Open("/vsicurl/" + url)
    read(ds)
    stats = json.loads(gdal.NetworkStatsGetAsSerializedJSON()).get("methods", {})
    return {"requests": sum(m.get("count", 0) for m in stats.values()),
            "bytes": stats.get("GET", {}).get("downloaded_bytes", 0)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("latitude", type=float)
    p.add_argument("--other")
    a = p.parse_args()
    for key, value in {"CPL_VSIL_NETWORK_STATS_ENABLED": "YES", "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
                       "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES"}.items():
        gdal.SetConfigOption(key, value)
    ds = gdal.Open("/vsicurl/" + a.url)
    width, height, res = ds.RasterXSize, ds.RasterYSize, ds.GetGeoTransform()[1]
    web = "3857" in (ds.GetSpatialRef().GetAuthorityCode(None) or "")
    ground = res * math.cos(math.radians(a.latitude)) if web else res
    across = min(width, round(37000 / ground))
    down = min(height, round(across * VIEW[1] / VIEW[0]))
    x0, y0 = (width - across) // 2, (height - down) // 2
    scale = min(VIEW[0] / width, VIEW[1] / height)
    out = {
        "url": a.url, "size": [width, height], "ground_m": round(ground, 2),
        "view_37km": counted(a.url, lambda d: d.ReadRaster(x0, y0, across, down, buf_xsize=VIEW[0], buf_ysize=VIEW[1])),
        "whole_file": counted(a.url, lambda d: d.ReadRaster(0, 0, width, height, buf_xsize=max(1, round(width * scale)),
                                                             buf_ysize=max(1, round(height * scale)))),
    }
    if a.other:
        other = gdal.Open("/vsicurl/" + a.other)
        coarse = [other.GetRasterBand(b).GetOverview(0) for b in (1, 2, 3)]
        # The two files snap their bounds to different multiples (512 pixels of their own
        # size), so the other file's second level sits at a whole-pixel offset inside this one.
        ours_gt, theirs_gt = ds.GetGeoTransform(), other.GetGeoTransform()
        dx, dy = (theirs_gt[0] - ours_gt[0]) / res, (ours_gt[3] - theirs_gt[3]) / res
        assert abs(dx - round(dx)) < 1e-6 and abs(dy - round(dy)) < 1e-6 and abs(theirs_gt[1] * 2 - res) < 1e-9, \
            "the two files are not on the same grid"
        dx, dy, cw, ch = round(dx), round(dy), coarse[0].XSize, coarse[0].YSize
        assert dx >= 0 and dy >= 0 and dx + cw <= width and dy + ch <= height, "the other file is not inside this one"
        mask = ds.GetRasterBand(1).GetMaskBand()
        rng, found = random.Random(20261114), []
        for _ in range(8000):
            if len(found) == 200:
                break
            cx, cy = rng.randrange(cw // 512) * 512, rng.randrange(ch // 512) * 512
            x, y = cx + dx, cy + dy
            valid = mask.ReadAsArray(x, y, 512, 512) > 0
            if valid.mean() < 0.5:
                continue
            ours = ds.ReadAsArray(x, y, 512, 512).astype(np.float64)
            theirs = np.stack([c.ReadAsArray(cx, cy, 512, 512) for c in coarse]).astype(np.float64)
            mse = [float(((ours[b] - theirs[b])[valid] ** 2).mean()) for b in range(3)]
            found.append([99.0 if m == 0 else round(10 * math.log10(255 ** 2 / m), 2) for m in mse])
        out["against_averaged"] = {"windows": len(found),
                                   "median_db": [sorted(f[b] for f in found)[len(found) // 2] for b in range(3)],
                                   "lowest_db": [min(f[b] for f in found) for b in range(3)]}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
