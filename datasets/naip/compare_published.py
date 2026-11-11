#!/usr/bin/env python3
"""Compare control outputs with the files naip-visualization publishes for the same quads.

For every receipt of a control run: overview sizes, overview edge brightness, pixel error
between the two files at every overview level and on a centre window at full resolution,
and every difference in what GDAL reports about the two files.

    AWS_REQUEST_PAYER=requester python3 compare_published.py <receipts dir> <out.json> \
        [--window 4096] [--workers 6]

Reads both files in place over /vsis3/ with the caller's credentials (naip-visualization is
requester pays). Full resolution is compared on a centre window, not the whole file, to keep
the transfer small; the converter's own receipt holds the whole-file error against the source.
"""

import argparse
import json
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from osgeo import gdal

gdal.UseExceptions()

IGNORED_INFO_KEYS = {"description", "files", "size", "stac"}


def psnr(a, b):
    """PSNR in dB per band between two (bands, rows, cols) arrays; None where identical."""
    d = a.astype(np.int32) - b.astype(np.int32)
    mse = (d * d).reshape(d.shape[0], -1).mean(axis=1)
    return [None if m == 0 else round(float(10 * np.log10(255.0 * 255.0 / m)), 3) for m in mse]


def edge_ratios(array):
    """Last row over the row before it and last column over the column before, band 1."""
    band = array[0].astype(np.float64)
    rows, cols = band[-2:].mean(axis=1), band[:, -2:].mean(axis=0)
    return [round(float(rows[1] / max(rows[0], 1.0)), 3), round(float(cols[1] / max(cols[0], 1.0)), 3)]


def flatten(value, prefix=""):
    if isinstance(value, dict):
        for k, v in value.items():
            if not (prefix == "" and k in IGNORED_INFO_KEYS):
                yield from flatten(v, f"{prefix}/{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from flatten(v, f"{prefix}[{i}]")
    else:
        yield prefix, value


def info_differences(ours, published):
    a = dict(flatten(gdal.Info(ours, format="json")))
    b = dict(flatten(gdal.Info(published, format="json")))
    return {k: [a.get(k), b.get(k)] for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}


def compare(receipt, window):
    ours = gdal.Open("/vsis3/" + receipt["out_uri"][5:])
    published = gdal.Open(f"/vsis3/naip-visualization/{receipt['published']['key']}")
    out = {"id": receipt["id"], "info_differences": info_differences(ours, published), "levels": []}
    w, h = min(window, ours.RasterXSize), min(window, ours.RasterYSize)
    x, y = (ours.RasterXSize - w) // 2, (ours.RasterYSize - h) // 2
    out["full_resolution_window_psnr_db"] = psnr(
        ours.ReadAsArray(x, y, w, h, band_list=[1, 2, 3]), published.ReadAsArray(x, y, w, h, band_list=[1, 2, 3]))
    count = max(ours.GetRasterBand(1).GetOverviewCount(), published.GetRasterBand(1).GetOverviewCount())
    for level in range(count):
        def read(ds):
            band = ds.GetRasterBand(1)
            if level >= band.GetOverviewCount():
                return None
            return np.stack([ds.GetRasterBand(i).GetOverview(level).ReadAsArray() for i in (1, 2, 3)])
        a, b = read(ours), read(published)
        row = {"level": level + 1,
               "size": None if a is None else [a.shape[2], a.shape[1]],
               "published_size": None if b is None else [b.shape[2], b.shape[1]],
               "edges": None if a is None else edge_ratios(a),
               "published_edges": None if b is None else edge_ratios(b)}
        row["psnr_db"] = psnr(a, b) if a is not None and b is not None and a.shape == b.shape else None
        out["levels"].append(row)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("receipts_dir")
    p.add_argument("out")
    p.add_argument("--window", type=int, default=4096)
    p.add_argument("--workers", type=int, default=6)
    a = p.parse_args()

    receipts = []
    for name in sorted(os.listdir(a.receipts_dir)):
        if name.endswith(".json"):
            with open(os.path.join(a.receipts_dir, name)) as f:
                receipts.append(json.load(f))
    with ThreadPoolExecutor(a.workers) as pool:
        quads = list(pool.map(lambda r: compare(r, a.window), receipts))

    lowest = lambda values: min(v for v in values if v is not None) if any(v is not None for v in values) else None
    levels = sorted({l["level"] for q in quads for l in q["levels"]})
    summary = {
        "quads": len(quads),
        "sizes_equal": all(l["size"] == l["published_size"] for q in quads for l in q["levels"]),
        "lowest_edge_ratio": min(min(l["edges"]) for q in quads for l in q["levels"] if l["edges"]),
        "lowest_published_edge_ratio": min(min(l["published_edges"]) for q in quads for l in q["levels"] if l["published_edges"]),
        "full_resolution_window_median_psnr_db": statistics.median(lowest(q["full_resolution_window_psnr_db"]) or 99 for q in quads),
        "by_level": {},
        "info_differences": {},
    }
    for level in levels:
        values = [lowest(l["psnr_db"]) for q in quads for l in q["levels"] if l["level"] == level and l["psnr_db"]]
        values = [v if v is not None else 99 for v in values]
        summary["by_level"][level] = {"compared": len(values),
                                      "median_psnr_db": statistics.median(values) if values else None,
                                      "lowest_psnr_db": min(values) if values else None}
    for q in quads:
        for key, pair in q["info_differences"].items():
            entry = summary["info_differences"].setdefault(key, {"quads": 0, "example": pair})
            entry["quads"] += 1
    with open(a.out, "w") as f:
        json.dump({"summary": summary, "quads": quads}, f, indent=1)
        f.write("\n")
    json.dump(summary, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
