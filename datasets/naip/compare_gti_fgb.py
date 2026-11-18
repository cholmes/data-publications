#!/usr/bin/env python3
"""Compare the pixels of the FlatGeobuf tile index with those of the r7 tile index, window by window.

    python compare_gti_fgb.py <r7 address> <fgb address> <release dir with naip.parquet> <out.json> [--seed 8] [--samples 6]

Run it in a Python whose GDAL reads Parquet (QGIS's own), for the r7 side. The r7 side is the XML tile
index over naip.parquet that releases r6 and r7 held (no longer hosted; give a local copy next to the
parquet files). Addresses as GDAL opens them, for example a local path for r7 and
`GTI:/vsicurl/https://data.source.coop/nthh/naip/stac/naip.gti.fgb`.

Each window is 1600 x 1000 pixels, read the way QGIS draws a view (one ReadRaster at the view's
resolution) but with nearest-neighbour resampling, so a difference is a different source pixel and not
a blend. The windows: Alta, Utah, at about 1 m, 4 m and 7 m; the whole country; and, chosen at random
from the quad index with a fixed seed, places flown in more than one year, places on a state border
(flown by two states) and places flown once, at about 1 m, and places flown in more than one year at 4 m.

For each window: pixels equal in all four bands; pixels drawn (alpha above 0) by r7 but empty in the
FlatGeobuf mosaic, the reverse, and pixels both draw but differently. The two indexes choose files
differently: r7 draws every listed file, newest on top; the FlatGeobuf draws only the newest file of
each 3.75-minute cell, in full, so where neighbouring files overlap either may be on top, and an older
flight no longer shows where the newest file of a cell is empty. So the report also gives, for pixels
that differ, the greatest distance from a cell boundary (quarter quads overlap their neighbours by a few
hundred metres, about 0.003 degrees), and how many differ farther than 0.005 degrees from one.
"""
import argparse
import json
import math
import random
import time

import numpy as np
import pyarrow.compute as pc
import pyarrow.parquet as pq
from osgeo import gdal

gdal.UseExceptions()
for key, value in {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_MAX_RETRY": "4",
                   "GDAL_HTTP_RETRY_DELAY": "1", "GDAL_PAM_ENABLED": "NO"}.items():
    gdal.SetConfigOption(key, value)

W, H = 1600, 1000
CELL = 0.0625
M1, M4, M7 = 0.00001, 0.00004, 0.00008     # degrees a pixel: about 1 m, 4 m and 7 m on screen


def sample_places(release_dir, seed, n):
    with open(release_dir / "naip.parquet", "rb") as f:
        t = pq.ParquetFile(f).read(columns=["bbox", "naip:state", "naip:year"])
    bbox = t["bbox"]
    cx = pc.divide(pc.add(pc.struct_field(bbox, "xmin"), pc.struct_field(bbox, "xmax")), 2).to_pylist()
    cy = pc.divide(pc.add(pc.struct_field(bbox, "ymin"), pc.struct_field(bbox, "ymax")), 2).to_pylist()
    cells = {}
    for x, y, state, year in zip(cx, cy, t["naip:state"].to_pylist(), t["naip:year"].to_pylist()):
        cells.setdefault((math.floor(x / CELL), math.floor(y / CELL)), set()).add((state, year))
    groups = {"several_years": [], "two_states": [], "one_flight": []}
    for cell, flights in sorted(cells.items()):
        if len({s for s, _ in flights}) > 1:
            groups["two_states"].append(cell)
        elif len(flights) > 1:
            groups["several_years"].append(cell)
        else:
            groups["one_flight"].append(cell)
    rng = random.Random(seed)
    picked = {k: rng.sample(v, min(n, len(v))) for k, v in groups.items()}
    # A cell's corner, so the window spans four cells and their overlapping edges.
    return {k: [((i + 1) * CELL, (j + 1) * CELL) for i, j in v] for k, v in picked.items()}, \
        {k: len(v) for k, v in groups.items()}


def read(ds, cx, cy, res):
    gt = ds.GetGeoTransform()
    if res is None:                       # the whole mosaic, as a national view
        x0, y0, w, h = 0, 0, ds.RasterXSize, ds.RasterYSize
        bw, bh = W, int(W * h / w)
    else:
        x0 = int(round((cx - W * res / 2 - gt[0]) / gt[1]))
        y0 = int(round((cy + H * res / 2 - gt[3]) / gt[5]))
        w, h, bw, bh = int(round(W * res / gt[1])), int(round(H * res / -gt[5])), W, H
    t = time.time()
    data = ds.ReadRaster(x0, y0, w, h, buf_xsize=bw, buf_ysize=bh, resample_alg=gdal.GRIORA_NearestNeighbour)
    return np.frombuffer(data, np.uint8).reshape(4, bh, bw), time.time() - t, edge_distance(gt, x0, y0, w, h, bw, bh)


def edge_distance(gt, x0, y0, w, h, bw, bh):
    """Degrees from each pixel centre of the buffer to the nearest cell boundary."""
    xs = gt[0] + (x0 + (np.arange(bw) + 0.5) * w / bw) * gt[1]
    ys = gt[3] + (y0 + (np.arange(bh) + 0.5) * h / bh) * gt[5]
    dx = np.abs(xs / CELL - np.round(xs / CELL)) * CELL
    dy = np.abs(ys / CELL - np.round(ys / CELL)) * CELL
    return np.minimum(dx[None, :], dy[:, None])


def compare(a, b, dist):
    drawn_a, drawn_b = a[3] > 0, b[3] > 0
    same = (a == b).all(axis=0)
    differ = ~same & (drawn_a | drawn_b)
    far = float(dist[differ].max()) if differ.any() else None
    return {"differing_max_deg_from_cell_edge": far,
            "differing_beyond_0.005_deg_from_cell_edge": int((differ & (dist > 0.005)).sum()),
            "pixels": int(same.size), "equal": int(same.sum()), "equal_share": round(float(same.mean()), 6),
            "r7_drawn": int(drawn_a.sum()), "fgb_drawn": int(drawn_b.sum()),
            "r7_only": int((drawn_a & ~drawn_b).sum()), "fgb_only": int((drawn_b & ~drawn_a).sum()),
            "both_drawn_different": int((drawn_a & drawn_b & ~same).sum())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("r7")
    parser.add_argument("fgb")
    parser.add_argument("release_dir")
    parser.add_argument("out")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--samples", type=int, default=6)
    args = parser.parse_args()
    from pathlib import Path
    places, group_sizes = sample_places(Path(args.release_dir), args.seed, args.samples)

    r7, fgb = gdal.Open(args.r7), gdal.Open(args.fgb)
    grid = {"r7": [r7.RasterXSize, r7.RasterYSize, list(r7.GetGeoTransform()), r7.RasterCount],
            "fgb": [fgb.RasterXSize, fgb.RasterYSize, list(fgb.GetGeoTransform()), fgb.RasterCount]}
    assert grid["r7"] == grid["fgb"], grid
    assert [fgb.GetRasterBand(i).GetOverviewCount() for i in (1,)] == [r7.GetRasterBand(1).GetOverviewCount()]

    windows = [("alta_1m", -111.625, 40.59, M1), ("alta_4m", -111.625, 40.59, M4), ("alta_7m", -111.625, 40.59, M7),
               ("national", None, None, None)]
    for group, centres in places.items():
        windows += [(f"{group}_{n}_1m", x, y, M1) for n, (x, y) in enumerate(centres)]
    windows += [(f"several_years_{n}_4m", x, y, M4) for n, (x, y) in enumerate(places["several_years"][:3])]

    rows = []
    for name, cx, cy, res in windows:
        a, ta, dist = read(r7, cx, cy, res)
        b, tb, _ = read(fgb, cx, cy, res)
        row = {"window": name, "centre": [cx, cy], "deg_per_px": res, "r7_seconds": round(ta, 2), "fgb_seconds": round(tb, 2),
               **compare(a, b, dist)}
        rows.append(row)
        print(json.dumps(row), flush=True)
    report = {"r7": args.r7, "fgb": args.fgb, "grid": grid["fgb"][:3], "overview_levels": r7.GetRasterBand(1).GetOverviewCount(),
              "gdal": gdal.__version__, "seed": args.seed, "cell_groups": group_sizes, "windows": rows}
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
