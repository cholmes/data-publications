#!/usr/bin/env python3
"""Downsample the pinned national overview to a PNG for the catalogue card (mark 5 of
research/catalog-presentation-20261117/criteria.md).

    python thumbnail_image.py --national LOCAL.tif --sha256 PINNED --out NEW.png

LOCAL.tif must hold the pinned bytes (checked). Writes an RGBA PNG 2048 pixels wide, averaged from the
file's own overviews with its mask as alpha, and prints the corner coordinates (longitude, latitude)
that the card renderer needs to place it. The file is EPSG:3857, so the corners place it exactly.
"""
import argparse
import hashlib
import json
import math
import os
import subprocess

WIDTH = 2048
R = 6378137.0


def lonlat(x, y):
    return [round(math.degrees(x / R), 9), round(math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2), 9)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--national", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--gdal-bin", required=True, help="directory holding gdal_translate and gdalinfo")
    args = parser.parse_args()
    if os.path.exists(args.out):
        raise SystemExit("Use a new output path; earlier results are kept.")
    with open(args.national, "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != args.sha256:
            raise SystemExit("National file differs from the pinned SHA-256")
    info = json.loads(subprocess.run([os.path.join(args.gdal_bin, "gdalinfo"), "-json", args.national],
                                     check=True, capture_output=True, text=True).stdout)
    if "Pseudo-Mercator" not in info["coordinateSystem"]["wkt"]:
        raise SystemExit("Expected EPSG:3857")
    x0, dx, _, y0, _, dy = info["geoTransform"]
    width, height = info["size"]
    x1, y1 = x0 + dx * width, y0 + dy * height
    subprocess.run([os.path.join(args.gdal_bin, "gdal_translate"), "-q", "-of", "PNG", "-r", "average",
                    "-outsize", str(WIDTH), "0", "-b", "1", "-b", "2", "-b", "3", "-b", "mask",
                    "-co", "ZLEVEL=9", args.national, args.out], check=True)
    aux = args.out + ".aux.xml"
    if os.path.exists(aux):
        os.remove(aux)
    with open(args.out, "rb") as f:
        png = f.read()
    print(json.dumps({"path": args.out, "sha256": hashlib.sha256(png).hexdigest(), "size_bytes": len(png),
                      "source_sha256": args.sha256,
                      "coordinates": [lonlat(x0, y0), lonlat(x1, y0), lonlat(x1, y1), lonlat(x0, y1)]}))


if __name__ == "__main__":
    main()
