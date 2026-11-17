#!/usr/bin/env python3
"""Check 12 of an index release (index-package-plan.md): its naip.gti opens in GDAL as QGIS would.

    python check_gti_open.py --release DIR --out NEW_FILE [--host https://data.source.coop]

Run with the Python inside QGIS 4.2.1 (GDAL 3.12.4 with its Parquet and GTI drivers); the
naip-index environment has GDAL 3.12.4 without the Parquet driver. On macOS:

    Q=/Applications/QGIS-final-4_2_1.app/Contents; R=$Q/Resources/python3.12
    PROJ_DATA=$Q/Resources/qgis/proj GDAL_DATA=$Q/Resources/qgis/gdal \
        PYTHONPATH="$R:$R/lib-dynload:$R/site-packages" $Q/MacOS/python3.12 check_gti_open.py ...

A loopback
server answers /nthh/naip/stac/<name> from the release's four files, with byte ranges, and sends
every other path to the host with a 302, so a relative tile address in the index reaches the
hosted imagery as it will once the files are at stac/. The script opens
/vsicurl/http://127.0.0.1:<port>/nthh/naip/stac/naip.gti, reads the Alta window at full
resolution and the whole of Utah at about 600 m, and records every request the server saw and
every imagery request GDAL made (from its debug log). The check passes when both reads give a
picture (band 1 mean between 60 and 200, alpha not all zero), every imagery request is a byte
range, and no index file is read whole.
"""
import argparse
import hashlib
import http.server
import json
import os
import re
import sys
import threading

from osgeo import gdal

gdal.UseExceptions()

FILES = ("naip.gti", "naip-overviews.gti", "naip.parquet", "naip-overviews.parquet")
STAC = "/nthh/naip/stac/"
ALTA = (-111.632, 40.596, -111.618, 40.585)       # ulx, uly, lrx, lry, as -projwin takes them
UTAH = (-114.1, 42.1, -109.0, 36.9)
UTAH_RES = 0.0054                                  # degrees, about 600 m


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def serve(release, host, seen):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def answer(self, body):
            path = self.path.split("?")[0]
            name = path[len(STAC):] if path.startswith(STAC) else None
            if name not in FILES:
                seen.append({"method": self.command, "path": path, "status": 302})
                self.send_response(302)
                self.send_header("Location", host + path)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            data_path = os.path.join(release, name)
            size = os.path.getsize(data_path)
            want = re.match(r"bytes=(\d+)-(\d*)$", self.headers.get("Range") or "")
            start, end = (int(want[1]), min(int(want[2] or size - 1), size - 1)) if want else (0, size - 1)
            seen.append({"method": self.command, "path": path, "status": 206 if want else 200, "bytes": end - start + 1, "size": size})
            self.send_response(206 if want else 200)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if want:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if body:
                with open(data_path, "rb") as f:
                    f.seek(start)
                    self.wfile.write(f.read(end - start + 1))

        def do_HEAD(self):
            self.answer(False)

        def do_GET(self):
            self.answer(True)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def read(url, window, res, out_png):
    options = ["-projwin", *map(str, window), "-of", "PNG"]
    if res:
        options += ["-tr", str(res), str(res)]
    gdal.Translate(out_png, url, options=options)
    ds = gdal.Open(out_png)
    stats = [ds.GetRasterBand(b).ComputeStatistics(False) for b in (1, 4)]
    return {"size": [ds.RasterXSize, ds.RasterYSize], "band1_mean": round(stats[0][2], 3), "alpha_max": stats[1][1]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--host", default="https://data.source.coop")
    args = parser.parse_args()
    if os.path.exists(args.out):
        sys.exit("Use a new output path; earlier results are kept.")
    release = os.path.abspath(args.release)
    work = args.out + ".work"
    os.makedirs(work)
    seen = []
    server = serve(release, args.host, seen)
    url = f"/vsicurl/http://127.0.0.1:{server.server_address[1]}{STAC}naip.gti"
    log = os.path.join(work, "gdal-debug.txt")
    gdal.SetConfigOption("CPL_DEBUG", "ON")
    gdal.SetConfigOption("CPL_LOG", log)
    gdal.SetConfigOption("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    reads, errors = {}, []
    for name, window, res in (("alta_full_resolution", ALTA, None), ("utah_600m", UTAH, UTAH_RES)):
        before = len(seen)
        try:
            reads[name] = read(url, window, res, os.path.join(work, name + ".png"))
        except RuntimeError as e:
            errors.append(f"{name}: {e}")
            reads[name] = None
        reads.setdefault(name, None)
        if reads[name] is not None:
            index = [s for s in seen[before:] if s.get("size")]
            reads[name]["index_requests"] = len(index)
            reads[name]["index_bytes"] = sum(s["bytes"] for s in index)
    server.shutdown()
    gdal.SetConfigOption("CPL_LOG", None)
    with open(log, errors="replace") as f:
        text = f.read()
    # GDAL's own record of each imagery request: the effective URL and the range it asked for.
    imagery = sorted(set(re.findall(r"https://data\.source\.coop/nthh/naip/(?!stac/)[^\s?]+\.tif", text)))
    whole = [s for s in seen if s.get("size") and s["status"] == 200 and s["method"] == "GET" and s["size"] > 1 << 20]
    downloads = re.findall(r"HTTP: Fetch\(https?://[^)]*\.tif", text)
    picture = lambda r: r is not None and 60 <= r["band1_mean"] <= 200 and r["alpha_max"] > 0
    passed = not errors and all(picture(r) for r in reads.values()) and imagery and not whole and not downloads
    report = {
        "schema_version": 1,
        "plan": "datasets/naip/index-package-plan.md, addendum for r6, check 12",
        "gdal": gdal.__version__,
        "release_files": {n: {"sha256": sha256(os.path.join(release, n)), "size_bytes": os.path.getsize(os.path.join(release, n))} for n in FILES},
        "opened": url.replace(f":{server.server_address[1]}", ":<port>"),
        "reads": reads,
        "errors": errors,
        "imagery_files_read": imagery,
        "index_files_read_whole": whole,
        "imagery_downloaded_whole": downloads,
        "server_requests": len(seen),
        "redirects": sum(1 for s in seen if s["status"] == 302),
        "status": "passed" if passed else "failed",
    }
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1)
        f.write("\n")
    print(json.dumps({k: report[k] for k in ("reads", "errors", "status")}, indent=1), len(imagery), "imagery files")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
