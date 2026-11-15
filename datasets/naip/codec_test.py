#!/usr/bin/env python3
"""JPEG 2000, HTJ2K and AVIF files of one lossless quad, and JPEG XL COGs with finer overviews.

For the pass marks in VALIDATION.md ("JPEG 2000, HTJ2K and AVIF against the same two quads").
Measured like jxl_test.py, plus the HTTP requests two map views take through GDAL from a local
server that counts them. Needs a GDAL with JP2OpenJPEG, AVIF and JXL in GeoTIFF, and
ojph_compress beside the Python that runs this (conda-forge: gdal libgdal-jp2openjpeg openjph).

    python3 codec_test.py <source.mrf or .tif> <work dir> <name> [--requests-for <file in work dir> ...]

Writes <work dir>/<name>-<build>.<ext> for every build and prints the result as JSON.
--requests-for measures the two views for files already in the work dir (the COGs jxl_test.py
made). One thread throughout.
"""
import http.server
import json
import os
import resource
import socket
import subprocess
import sys
import time

import numpy as np
from osgeo import gdal

from jxl_test import COMMON, cbcr, levels, psnr

gdal.UseExceptions()
gdal.SetConfigOption("GDAL_NUM_THREADS", "1")
gdal.SetConfigOption("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
PORT = 8791
LAYOUT = ["RESOLUTIONS=6", "BLOCKXSIZE=1024", "BLOCKYSIZE=1024", "PROGRESSION=RPCL", "TLM=YES", "PLT=YES", "YCC=YES",
          "GMLJP2=NO"]
JP2_QUALITIES = (4, 6, 8, 10, 12, 15)
HTJ2K_STEPS = (0.02, 0.03, 0.05, 0.08)
AVIF = [("avif-q50-444", ["QUALITY=50", "YUV_SUBSAMPLING=444"]), ("avif-q60-444", ["QUALITY=60", "YUV_SUBSAMPLING=444"]),
        ("avif-q70-444", ["QUALITY=70", "YUV_SUBSAMPLING=444"]), ("avif-q60-420", ["QUALITY=60", "YUV_SUBSAMPLING=420"])]
JXL_FINER = ((2.5, 1.5), (3.0, 2.0))             # full-resolution distance, overview distance
STREET = (4096, 6144, 1024, 1024)                # a window on both the 512 and the 1024 px grid


class Counting(http.server.BaseHTTPRequestHandler):
    """Serves one folder with byte ranges and writes a line per request to the log."""
    protocol_version = "HTTP/1.1"

    def do_HEAD(self):
        self.answer(False)

    def do_GET(self):
        self.answer(True)

    def answer(self, body):
        path = os.path.join(self.server.root, os.path.basename(self.path))
        if not os.path.isfile(path):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            self.server.log.write(f"{self.command} {self.path} 404 0\n")
            return
        size = os.path.getsize(path)
        start, end, status = 0, size - 1, 200
        asked = self.headers.get("Range")
        if asked:
            first, last = asked.split("=")[1].split("-")
            start, end, status = int(first), min(int(last) if last else size - 1, size - 1), 206
        self.send_response(status)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if body:
            with open(path, "rb") as f:
                f.seek(start)
                self.wfile.write(f.read(end - start + 1))
        self.server.log.write(f"{self.command} {self.path} {status} {end - start + 1 if body else 0}\n")

    def log_message(self, *args):
        pass


def serve(root, log_path):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Counting)
    server.root, server.log = root, open(log_path, "w", buffering=1)
    server.serve_forever()


def cpu():
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    return time.process_time() + child.ru_utime + child.ru_stime


def measure(path, truth):
    t0 = time.process_time()
    got = levels(path)
    decode = time.process_time() - t0
    by_level, same = [], True
    for t, g in zip(truth, got):
        h, w = min(t.shape[1], g.shape[1]), min(t.shape[2], g.shape[2])
        same = same and t.shape == g.shape
        by_level.append(psnr(t[:, :h, :w], g[:, :h, :w]))
    colour = psnr(cbcr(truth[0]), cbcr(got[0]))
    return {"file_bytes": os.path.getsize(path), "psnr_db_by_level": by_level, "level_sizes_match_the_cog": same,
            "colour_psnr_db": round(float(10 * np.log10(255 ** 2 / np.mean([255 ** 2 / 10 ** (c / 10) for c in colour]))), 2),
            "decode_all_levels_cpu_s": round(decode, 2), "reduced_levels": len(got) - 1}


def views(path, log_path):
    """Requests and bytes for a street view and the whole quad at one sixteenth, each from a cold open."""
    out = {}
    for view in ("street_1024_px_window", "whole_quad_at_one_sixteenth"):
        gdal.VSICurlClearCache()
        with open(log_path) as f:
            before = len(f.readlines())
        t0 = time.process_time()
        ds = gdal.Open(f"/vsicurl/http://127.0.0.1:{PORT}/{os.path.basename(path)}")
        if view.startswith("street"):
            ds.ReadAsArray(*STREET)
        else:
            ds.ReadAsArray(buf_xsize=ds.RasterXSize // 16, buf_ysize=ds.RasterYSize // 16)
        ds = None
        time.sleep(0.2)
        with open(log_path) as f:
            lines = [line.split() for line in f.readlines()[before:]]
        out[view] = {"requests": len(lines), "bytes": sum(int(line[3]) for line in lines),
                     "cpu_s": round(time.process_time() - t0, 2)}
    return out


def main():
    source, work, name = sys.argv[1:4]
    also = sys.argv[sys.argv.index("--requests-for") + 1:] if "--requests-for" in sys.argv else []
    if "--serve" in sys.argv:
        return serve(work, name)
    log_path = f"{work}/{name}-requests.log"
    server = subprocess.Popen([sys.executable, os.path.abspath(__file__), source, work, log_path, "--serve"])
    try:
        for _ in range(50):
            if socket.socket().connect_ex(("127.0.0.1", PORT)) == 0:
                break
            time.sleep(0.2)
        else:
            raise SystemExit("the counting server did not start")
        src = gdal.Translate("", source, format="MEM", bandList=[1, 2, 3])
        truth_path = f"{work}/{name}-lossless.tif"
        gdal.Translate(truth_path, src, format="COG", creationOptions=["COMPRESS=ZSTD"] + COMMON)
        truth = levels(truth_path)
        result = {"gdal": gdal.__version__, "source": os.path.basename(source), "street_window": STREET, "builds": {},
                  "megapixels": round(src.RasterXSize * src.RasterYSize / 1e6, 1), "views_of_existing_files": {}}

        def record(build, path, options, start):
            entry = {"options": options, "encode_cpu_s": round(cpu() - start, 1)}
            try:
                entry.update(measure(path, truth))
                entry["views"] = views(path, log_path)
            except Exception as error:
                entry["failed"] = str(error)[:300]
            result["builds"][build] = entry
            print(build, entry.get("file_bytes"), (entry.get("psnr_db_by_level") or [None])[0], entry.get("colour_psnr_db"),
                  entry["encode_cpu_s"], entry.get("views"), entry.get("failed"), file=sys.stderr, flush=True)

        for q in JP2_QUALITIES:
            path, options, start = f"{work}/{name}-jp2-q{q}.jp2", [f"QUALITY={q}"] + LAYOUT, cpu()
            gdal.Translate(path, src, format="JP2OpenJPEG", creationOptions=options)
            record(f"jp2-q{q}", path, options, start)

        ppm = f"{work}/{name}.ppm"
        gdal.Translate(ppm, src, format="PNM")
        for step in HTJ2K_STEPS:
            path = f"{work}/{name}-htj2k-s{step}.j2c"
            options = ["-qstep", str(step), "-num_decomps", "5", "-tile_size", "{1024,1024}", "-prog_order", "RPCL",
                       "-tlm_marker", "true", "-colour_trans", "true"]
            start = cpu()
            subprocess.run([os.path.join(os.path.dirname(sys.executable), "ojph_compress"), "-i", ppm, "-o", path] + options,
                           check=True, stdout=subprocess.DEVNULL)
            record(f"htj2k-s{step}", path, options, start)
        for extra in (ppm, ppm + ".aux.xml"):
            if os.path.exists(extra):
                os.remove(extra)

        for build, options in AVIF:
            path, options, start = f"{work}/{name}-{build}.avif", options + ["CODEC=AOM", "SPEED=6", "NUM_THREADS=1"], cpu()
            try:
                gdal.Translate(path, src, format="AVIF", creationOptions=options)
            except RuntimeError as error:
                result["builds"][build] = {"options": options, "failed": str(error)[:300]}
                print(build, "failed", str(error)[:200], file=sys.stderr, flush=True)
                continue
            record(build, path, options, start)

        for distance, overview in JXL_FINER:
            build = f"jxl-d{distance}-ovr-d{overview}"
            path, start = f"{work}/{name}-{build}.tif", cpu()
            options = ["COMPRESS=JXL", "JXL_LOSSLESS=NO", f"JXL_DISTANCE={distance}", "JXL_EFFORT=5"]
            gdal.SetConfigOption("JXL_DISTANCE_OVERVIEW", str(overview))
            gdal.Translate(path, src, format="COG", creationOptions=options + COMMON)
            gdal.SetConfigOption("JXL_DISTANCE_OVERVIEW", None)
            record(build, path, options + [f"config JXL_DISTANCE_OVERVIEW={overview}"], start)

        for existing in also:
            result["views_of_existing_files"][existing] = views(f"{work}/{existing}", log_path)
            print(existing, result["views_of_existing_files"][existing], file=sys.stderr, flush=True)
        os.remove(truth_path)
        json.dump(result, sys.stdout, indent=1)
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
