#!/usr/bin/env python3
"""List the enclosed gaps of the national file: areas with no picture that the picture surrounds.

    python3 national_holes.py <national file, path or URL> <out.json> [--least 20] [--before earlier.json]

Reads the file's mask at full size, labels the connected areas where the mask is empty, and
drops the ones that touch the edge of the file (the sea and the neighbouring countries).
What is left is written largest first, one row per gap:

    [pixels, [west, south], [east, north], width in pixels, height in pixels]

A gap is either water the flights did not cover (Lake Michigan) or quads the source lacks.
With --before, prints which gaps of an earlier record are gone or smaller now.

Needs GDAL's Python bindings, numpy and scipy. The file must be in EPSG:3857.
"""
import argparse
import json
import math

import numpy as np
from osgeo import gdal
from scipy import ndimage

EARTH_RADIUS = 6378137.0


def lonlat(x, y):
    return (round(math.degrees(x / EARTH_RADIUS), 3),
            round(math.degrees(2 * math.atan(math.exp(y / EARTH_RADIUS)) - math.pi / 2), 3))


def holes(path, least):
    source = path if not path.startswith("http") else "/vsicurl/" + path
    ds = gdal.Open(source)
    x0, dx, _, y0, _, dy = ds.GetGeoTransform()
    empty = ds.GetRasterBand(1).GetMaskBand().ReadAsArray() == 0
    labels, count = ndimage.label(empty)
    outside = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])))
    sizes = np.bincount(labels.ravel())
    rows = []
    for label, where in enumerate(ndimage.find_objects(labels), start=1):
        if label in outside or sizes[label] < least:
            continue
        ys, xs = where
        west, north = lonlat(x0 + xs.start * dx, y0 + ys.start * dy)
        east, south = lonlat(x0 + xs.stop * dx, y0 + ys.stop * dy)
        rows.append([int(sizes[label]), [west, south], [east, north], xs.stop - xs.start, ys.stop - ys.start])
    return sorted(rows, key=lambda r: -r[0])


def overlap(a, b):
    return a[1][0] < b[2][0] and b[1][0] < a[2][0] and a[1][1] < b[2][1] and b[1][1] < a[2][1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("out")
    p.add_argument("--least", type=int, default=20, help="smallest gap listed, in pixels")
    p.add_argument("--before")
    a = p.parse_args()
    rows = holes(a.file, a.least)
    with open(a.out, "w") as f:
        json.dump(rows, f)
    print(len(rows), "enclosed gaps,", sum(r[0] for r in rows), "pixels")
    if a.before:
        with open(a.before) as f:
            earlier = json.load(f)
        for old in earlier:
            left = sum(new[0] for new in rows if overlap(old, new))
            if left < old[0]:
                print("gone" if left == 0 else f"smaller ({left} pixels left)", old)
        print(len(earlier), "gaps before,", sum(r[0] for r in earlier), "pixels")


if __name__ == "__main__":
    main()
