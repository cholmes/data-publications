#!/usr/bin/env python3
"""How often each 3.75 minute cell is snow covered, by calendar month.

Source: the daily snow and ice analysis of the US National Ice Center (IMS, 4 km, NSIDC
data set G02156), read anonymously. Every fifth day of ten years is sampled. For each cell
and calendar month the result is the share of sampled days on which the analysis marks the
ground snow covered, as a whole percent (255 where the analysis has no land).

    python3 build_snow.py <download cache dir> snow.bin [--first 2015 --last 2024 --every 5]

Needs numpy and GDAL's Python bindings. Each cell is sampled at four points.
"""
import argparse
import concurrent.futures
import datetime
import gzip
import json
import os
import re
import struct
import time
import urllib.error
import urllib.request

import numpy as np
from osgeo import gdal, osr

WEST, NORTH, CELL, COLS, ROWS = -125.0, 50.0, 0.0625, 944, 416
BASE = "https://noaadata.apps.nsidc.org/NOAA/G02156/GIS/4km/{year}/"
LAND, SNOW = 2, 4


def get(url, tries=6):
    """The archive answers 500 now and then; wait and ask again."""
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))


def names(year):
    return sorted(set(re.findall(r'href="(ims\d{7}_4km_GIS_v[\d.]+\.tif\.gz)"', get(BASE.format(year=year)).decode())))


def fetch(cache, year, name):
    path = os.path.join(cache, name)
    if not os.path.exists(path):
        data = get(BASE.format(year=year) + name)
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.rename(path + ".part", path)
    return path


def sample_points(path):
    """Pixel row and column in the analysis grid for four points inside every cell."""
    ds = gdal.Open("/vsigzip/" + path)
    geographic = osr.SpatialReference()
    geographic.ImportFromEPSG(4326)
    geographic.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_grid = osr.CoordinateTransformation(geographic, osr.SpatialReference(wkt=ds.GetProjection()))
    gt = ds.GetGeoTransform()
    rows, cols = [], []
    for dy in (0.25, 0.75):
        for dx in (0.25, 0.75):
            lon = WEST + (np.arange(COLS) + dx) * CELL
            lat = NORTH - (np.arange(ROWS) + dy) * CELL
            points = [(float(x), float(y)) for y in lat for x in lon]
            xy = np.array(to_grid.TransformPoints(points))[:, :2]
            cols.append(((xy[:, 0] - gt[0]) / gt[1]).astype(int))
            rows.append(((xy[:, 1] - gt[3]) / gt[5]).astype(int))
    return np.array(rows), np.array(cols)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cache")
    p.add_argument("out")
    p.add_argument("--first", type=int, default=2015)
    p.add_argument("--last", type=int, default=2024)
    p.add_argument("--every", type=int, default=5)
    a = p.parse_args()
    gdal.UseExceptions()
    os.makedirs(a.cache, exist_ok=True)

    jobs = []
    for year in range(a.first, a.last + 1):
        # Some days are held in two versions; names sort by version, so the later one wins.
        for name in {n[:10]: n for n in names(year)}.values():
            day = int(name[7:10])
            if day % a.every == 3 % a.every:
                jobs.append((year, name, (datetime.date(year, 1, 1) + datetime.timedelta(day - 1)).month))
    print(len(jobs), "days to read", flush=True)

    cells = COLS * ROWS
    snow, land = np.zeros((12, cells), np.int32), np.zeros((12, cells), np.int32)
    days_in_month, points, failed = [0] * 12, None, []
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        paths = pool.map(lambda j: fetch(a.cache, j[0], j[1]), jobs)
        for done, ((year, name, month), path) in enumerate(zip(jobs, paths), 1):
            try:
                dataset = gdal.Open("/vsigzip/" + path)      # keep it alive while the band is read
                grid = dataset.GetRasterBand(1).ReadAsArray()
            except RuntimeError as error:
                failed.append(f"{name}: {error}")
                continue
            if points is None:
                points = sample_points(path)
            values = grid[points[0], points[1]]
            snow[month - 1] += (values == SNOW).sum(axis=0)
            land[month - 1] += ((values == SNOW) | (values == LAND)).sum(axis=0)
            days_in_month[month - 1] += 1
            if done % 50 == 0:
                print(done, "of", len(jobs), flush=True)

    percent = np.where(land > 0, np.rint(100 * snow / np.maximum(land, 1)), 255).astype("u1")
    header = {"schema": "naip-flight-dates-snow@1", "cols": COLS, "rows": ROWS,
              "source": "US National Ice Center IMS daily snow and ice analysis, 4 km (NSIDC G02156)",
              "years": [a.first, a.last], "every_days": a.every, "days_by_month": days_in_month,
              "days_failed": failed, "arrays": [["percent_snow_covered", "u1", 12]]}
    head = json.dumps(header).encode()
    head += b" " * (-(4 + len(head)) % 4)
    with gzip.open(a.out + ".gz", "wb", compresslevel=6) as f:
        f.write(struct.pack("<I", len(head)) + head + percent.tobytes())
    print(json.dumps(header | {"gz_bytes": os.path.getsize(a.out + ".gz")}))


if __name__ == "__main__":
    main()
