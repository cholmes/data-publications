#!/usr/bin/env python3
"""Mean elevation and relief of every 3.75 minute cell of the viewer's grid.

Reads the public Terrain Tiles on AWS (terrarium PNG, zoom 8, about 450 m per pixel at
40 N) anonymously and writes terrain.bin.gz: a JSON header, then per cell the mean
elevation (int16 metres) and the relief, highest minus lowest pixel (uint16 metres).
A cell with no pixel holds -32768 and 0.

    python3 build_terrain.py <tile cache dir> terrain.bin

Needs numpy and Pillow. Tiles are kept in the cache dir, so a second run reads no network.
"""
import concurrent.futures
import gzip
import io
import json
import math
import os
import struct
import sys
import urllib.request

import numpy as np
from PIL import Image

WEST, NORTH, CELL, COLS, ROWS = -125.0, 50.0, 0.0625, 944, 416
ZOOM, SIZE = 8, 256
TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"


def tile_xy(lon, lat):
    n = 2 ** ZOOM
    return (int((lon + 180) / 360 * n),
            int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n))


def fetch(cache, x, y):
    path = os.path.join(cache, f"{ZOOM}-{x}-{y}.png")
    if not os.path.exists(path):
        with urllib.request.urlopen(TILES.format(z=ZOOM, x=x, y=y), timeout=60) as r:
            data = r.read()
        with open(path, "wb") as f:
            f.write(data)
    with open(path, "rb") as f:
        rgb = np.asarray(Image.open(io.BytesIO(f.read())).convert("RGB"), dtype=np.float32)
    return x, y, rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768


def main(cache, out):
    os.makedirs(cache, exist_ok=True)
    x0, y0 = tile_xy(WEST, NORTH)
    x1, y1 = tile_xy(WEST + COLS * CELL - 1e-9, NORTH - ROWS * CELL + 1e-9)
    jobs = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    cells = COLS * ROWS
    total, count = np.zeros(cells), np.zeros(cells)
    low, high = np.full(cells, np.inf), np.full(cells, -np.inf)
    n = 2 ** ZOOM
    px = (np.arange(SIZE) + 0.5) / SIZE
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        for done, (x, y, elevation) in enumerate(pool.map(lambda j: fetch(cache, *j), jobs), 1):
            lon = (x + px) / n * 360 - 180
            lat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * (y + px) / n))))
            col = np.floor((lon - WEST) / CELL).astype(int)
            row = np.floor((NORTH - lat) / CELL).astype(int)
            ok = ((row >= 0) & (row < ROWS))[:, None] & ((col >= 0) & (col < COLS))[None, :]
            index = (row[:, None] * COLS + col[None, :])[ok]
            values = elevation[ok]
            total += np.bincount(index, values, cells)
            count += np.bincount(index, minlength=cells)
            np.minimum.at(low, index, values)
            np.maximum.at(high, index, values)
            if done % 100 == 0:
                print(done, "of", len(jobs), flush=True)
    seen = count > 0
    mean = np.where(seen, total / np.maximum(count, 1), -32768).round().astype("<i2")
    relief = np.where(seen, high - low, 0).round().clip(0, 65535).astype("<u2")
    header = {"schema": "naip-flight-dates-terrain@1", "cols": COLS, "rows": ROWS, "zoom": ZOOM,
              "source": "Terrain Tiles on AWS (terrarium), zoom 8", "tiles": len(jobs),
              "cells_with_pixels": int(seen.sum()), "arrays": [["mean_m", "i2"], ["relief_m", "u2"]]}
    head = json.dumps(header).encode()
    head += b" " * (-(4 + len(head)) % 4)
    with gzip.open(out + ".gz", "wb", compresslevel=6) as f:
        f.write(struct.pack("<I", len(head)) + head + mean.tobytes() + relief.tobytes())
    print(json.dumps(header | {"gz_bytes": os.path.getsize(out + ".gz"),
                               "highest_mean_m": int(mean.max()), "highest_relief_m": int(relief.max())}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
