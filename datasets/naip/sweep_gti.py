#!/usr/bin/env python3
"""How much the hosted naip.gti reads at each zoom level: one fresh GDAL process per level.

    python sweep_gti.py --out NEW_FILE [--url /vsicurl/https://data.source.coop/nthh/naip/stac/naip.gti]
        [--center -111.625,40.59] [--pixels 800x600]

Run with the Python inside QGIS 4.2.1 (see check_gti_open.py for the command). Each level reads a
view of the same pixel size around the same centre, at one resolution in degrees, in its own
process so nothing is cached between levels. GDAL's debug log gives every range it fetched; the
report gives, per level, the seconds taken, the bytes and requests of the index files and of the
imagery, which imagery files were read (quarter quads, state overviews, the national file), any
file read whole, and band statistics of the picture.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

LEVELS = [0.000005, 0.00001, 0.00002, 0.00004, 0.00008, 0.00016, 0.00032, 0.00064, 0.00128, 0.00256, 0.00512, 0.01]
INDEX = ("/stac/naip.parquet", "/stac/naip-overviews.parquet")

CHILD = r'''
import sys
from osgeo import gdal
gdal.UseExceptions()
url, out, res, ulx, uly, lrx, lry = sys.argv[1], sys.argv[2], float(sys.argv[3]), *map(float, sys.argv[4:8])
gdal.Translate(out, url, options=["-projwin", str(ulx), str(uly), str(lrx), str(lry), "-tr", str(res), str(res), "-of", "GTiff"])
ds = gdal.Open(out)
s = [ds.GetRasterBand(b).ComputeStatistics(False) for b in (1, 4)]
print("STATS", ds.RasterXSize, ds.RasterYSize, round(s[0][2], 2), s[1][1], round(s[1][2], 2))
'''


def kind(url):
    if "/overviews/national" in url:
        return "national"
    if "/overviews/" in url:
        return "state_overview"
    if url.endswith(".tif"):
        return "quad"
    return "other"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--url", default="/vsicurl/https://data.source.coop/nthh/naip/stac/naip.gti")
    p.add_argument("--center", default="-111.625,40.59")
    p.add_argument("--pixels", default="800x600")
    a = p.parse_args()
    if os.path.exists(a.out):
        sys.exit("Use a new output path; earlier results are kept.")
    cx, cy = map(float, a.center.split(","))
    w, h = map(int, a.pixels.split("x"))
    work = tempfile.mkdtemp()
    levels = []
    for res in LEVELS:
        ulx, uly, lrx, lry = cx - w * res / 2, cy + h * res / 2, cx + w * res / 2, cy - h * res / 2
        log = os.path.join(work, f"{res}.log")
        env = {**os.environ, "CPL_DEBUG": "ON", "CPL_LOG": log, "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR"}
        start = time.time()
        run = subprocess.run([sys.executable, "-c", CHILD, a.url, os.path.join(work, f"{res}.tif"), str(res),
                              str(ulx), str(uly), str(lrx), str(lry)], env=env, capture_output=True, text=True, timeout=900)
        seconds = round(time.time() - start, 1)
        text = open(log, errors="replace").read() if os.path.exists(log) else ""
        fetched = [(int(x), int(y), u) for x, y, u in re.findall(r"Downloading (\d+)-(\d+) \((\S+?)\)", text)]
        index = [f for f in fetched if f[2].endswith(INDEX)]
        imagery = [f for f in fetched if f[2].endswith(".tif")]
        files = {}
        for x, y, u in imagery:
            files.setdefault(u, 0)
            files[u] += y - x + 1
        stats = re.search(r"STATS (\d+) (\d+) (\S+) (\S+) (\S+)", run.stdout)
        level = {
            "res_degrees": res, "approx_metres": round(res * 111320 * 0.7577), "view_degrees": [round(w * res, 4), round(h * res, 4)],
            "seconds": seconds, "ok": run.returncode == 0 and bool(stats),
            "index_requests": len(index), "index_bytes": sum(y - x + 1 for x, y, _ in index),
            "imagery_requests": len(imagery), "imagery_bytes": sum(files.values()),
            "imagery_files": {k: sum(1 for u in files if kind(u) == k) for k in ("quad", "state_overview", "national")},
            "largest_file_bytes": max(files.values(), default=0),
            "whole_downloads": len(re.findall(r"HTTP: Fetch\(https?://[^)]*\.tif", text)),
            "picture": None if not stats else {"size": [int(stats[1]), int(stats[2])], "band1_mean": float(stats[3]),
                                               "alpha_max": float(stats[4]), "alpha_mean": float(stats[5])},
            "error": None if run.returncode == 0 else run.stderr.strip()[-400:],
        }
        levels.append(level)
        print(json.dumps({k: level[k] for k in ("res_degrees", "approx_metres", "seconds", "ok", "index_bytes", "imagery_requests",
                                                "imagery_bytes", "imagery_files", "whole_downloads")}), flush=True)
    import osgeo
    report = {"schema_version": 1, "url": a.url, "center": [cx, cy], "pixels": [w, h], "gdal": osgeo.__version__, "levels": levels}
    with open(a.out, "w") as f:
        json.dump(report, f, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
