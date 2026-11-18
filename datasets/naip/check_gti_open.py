#!/usr/bin/env python3
"""Check 12 of the NAIP index (index-package-plan.md): stac/naip.gti.fgb opens in GDAL as QGIS would.

    python check_gti_open.py --release DIR --out NEW_FILE [--host https://data.source.coop]

DIR holds the local naip.gti.fgb and naip-overviews.gti.fgb whose checksums the report records. Run with
the Python inside QGIS 4.2.1 (GDAL 3.12.4), the GDAL a QGIS user opens the file with. On macOS:

    Q=/Applications/QGIS-final-4_2_1.app/Contents; R=$Q/Resources/python3.12
    PROJ_DATA=$Q/Resources/qgis/proj GDAL_DATA=$Q/Resources/qgis/gdal \
        PYTHONPATH="$R:$R/lib-dynload:$R/site-packages" $Q/MacOS/python3.12 check_gti_open.py ...

The script opens GTI:/vsicurl/<host>/nthh/naip/stac/naip.gti.fgb, the hosted file, as a user does. Every
address inside it (tiles and the overview index) is absolute, so there is no loopback copy: the hosted
pair is what is checked. It reads the Alta window at full resolution and the whole of Utah at about
600 m, and records every index and imagery request GDAL made (from its debug log). The check passes when
both reads give a picture (band 1 mean between 60 and 200, alpha not all zero), every imagery request is
a byte range, no index file is read whole, and neither read takes more than 8 MiB of the index files. A
third step does what QGIS does when the layer is added, approximate statistics of band 1 and a
1,000-pixel draw of the whole extent, and must fetch no more than 8 MiB in all.

Until 2026-11-18 this check opened stac/naip.gti (the GeoParquet tile index) through a loopback server;
its reports under releases/ are kept as they were.
"""
import argparse
import hashlib
import json
import os
import re
import sys

from osgeo import gdal

gdal.UseExceptions()

FILES = ("naip.gti.fgb", "naip-overviews.gti.fgb")
STAC = "/nthh/naip/stac/"
ALTA = (-111.632, 40.596, -111.618, 40.585)       # ulx, uly, lrx, lry, as -projwin takes them
UTAH = (-114.1, 42.1, -109.0, 36.9)
UTAH_RES = 0.0054                                  # degrees, about 600 m
INDEX_BYTES_PER_READ = 8 << 20                     # GET bytes of the index files one read may take
WHOLE_WIDTH = 1000                                 # pixels across of the whole-extent draw
WHOLE_BYTES = 8 << 20                              # all bytes the add-layer step may fetch


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read(url, window, res, out_png):
    if window is None:
        # What QGIS does when the layer is added: approximate statistics of a band, then a draw of
        # the whole extent at about the width of a map window.
        source = gdal.Open(url)
        source.GetRasterBand(1).ComputeStatistics(True)
        options = ["-outsize", str(WHOLE_WIDTH), "0", "-of", "PNG"]
    else:
        options = ["-projwin", *map(str, window), "-of", "PNG"]
    if res:
        options += ["-tr", str(res), str(res)]
    gdal.Translate(out_png, url, options=options)
    ds = gdal.Open(out_png)
    stats = [ds.GetRasterBand(b).ComputeStatistics(False) for b in (1, 4)]
    return {"size": [ds.RasterXSize, ds.RasterYSize], "band1_mean": round(stats[0][2], 3), "alpha_max": stats[1][1]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True, help="folder with the local naip.gti.fgb and naip-overviews.gti.fgb")
    parser.add_argument("--out", required=True)
    parser.add_argument("--host", default="https://data.source.coop")
    args = parser.parse_args()
    if os.path.exists(args.out):
        sys.exit("Use a new output path; earlier results are kept.")
    release = os.path.abspath(args.release)
    sizes = {n: os.path.getsize(os.path.join(release, n)) for n in FILES}
    work = args.out + ".work"
    os.makedirs(work)
    url = f"GTI:/vsicurl/{args.host}{STAC}naip.gti.fgb"
    log = os.path.join(work, "gdal-debug.txt")
    gdal.SetConfigOption("CPL_DEBUG", "ON")
    gdal.SetConfigOption("CPL_LOG", log)
    reads, errors, index_ranges = {}, [], []
    for name, window, res in (("alta_full_resolution", ALTA, None), ("utah_600m", UTAH, UTAH_RES), ("add_layer_whole_extent", None, None)):
        log_at = os.path.getsize(log) if os.path.exists(log) else 0
        try:
            reads[name] = read(url, window, res, os.path.join(work, name + ".png"))
        except RuntimeError as e:
            errors.append(f"{name}: {e}")
            reads[name] = None
        if reads[name] is not None:
            # GDAL's own record of the ranges it fetched: "VSICURL: Downloading <start>-<end> (<url>)".
            with open(log, errors="replace") as f:
                f.seek(log_at)
                fetched = re.findall(r"Downloading (\d+)-(\d+) \((\S+?)\)", f.read())
            index = [(u.rsplit("/", 1)[1], int(a), int(b)) for a, b, u in fetched if u.endswith(tuple(STAC + n for n in FILES))]
            index_ranges += index
            reads[name]["all_bytes"] = sum(int(b) - int(a) + 1 for a, b, _ in fetched)
            reads[name]["index_requests"] = len(index)
            reads[name]["index_bytes"] = sum(b - a + 1 for _, a, b in index)
    gdal.SetConfigOption("CPL_LOG", None)
    with open(log, errors="replace") as f:
        text = f.read()
    # GDAL's own record of each imagery request: the effective URL and the range it asked for.
    imagery = sorted(set(re.findall(r"https://data\.source\.coop/nthh/naip/(?!stac/)[^\s?)&]+\.tif", text)))
    whole = [{"file": n, "start": a, "end": b} for n, a, b in index_ranges if a == 0 and b + 1 >= sizes[n] and sizes[n] > 1 << 20]
    downloads = re.findall(r"HTTP: Fetch\(https?://[^)]*\.tif", text)
    picture = lambda r: r is not None and 60 <= r["band1_mean"] <= 200 and r["alpha_max"] > 0
    small = (all(r is not None and r["index_bytes"] <= INDEX_BYTES_PER_READ for r in reads.values())
             and reads["add_layer_whole_extent"] is not None and reads["add_layer_whole_extent"]["all_bytes"] <= WHOLE_BYTES)
    passed = not errors and all(picture(r) for r in reads.values()) and small and bool(imagery) and not whole and not downloads
    report = {
        "schema_version": 1,
        "plan": "datasets/naip/index-package-plan.md, check 12 (addendum of 2026-11-18)",
        "gdal": gdal.__version__,
        "release_files": {n: {"sha256": sha256(os.path.join(release, n)), "size_bytes": sizes[n]} for n in FILES},
        "opened": url,
        "reads": reads,
        "errors": errors,
        "imagery_files_read": imagery,
        "index_files_read_whole": whole,
        "imagery_downloaded_whole": downloads,
        "index_requests": [{"file": n, "start": a, "bytes": b - a + 1} for n, a, b in index_ranges],
        "status": "passed" if passed else "failed",
    }
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1)
        f.write("\n")
    print(json.dumps({k: report[k] for k in ("reads", "errors", "status")}, indent=1), len(imagery), "imagery files")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
