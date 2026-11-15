#!/usr/bin/env python3
"""An overview file against the hosted quads it was made from, read independently of how it was built.

    python3 check_overview_against_quads.py <overview file or https url> <naip stac index.parquet> \
        <state> <year> [--sample N] [--zone EPSG]

For a seeded sample of the state-year's quads: read the quad's own reduced level at the file's
pixel size, put it on the file's grid with one thread, and compare it with the same window of
the file in 128 pixel blocks. Reports PSNR per block and whether a block agrees better when
moved by one pixel, which is how a reprojection that returned shifted pixels shows up. The
build's own check cannot see that: it compares the file with the mosaic the file was read from.
"""
import argparse
import json
import math
import random

import numpy as np
import pyarrow.parquet as pq
from osgeo import gdal, osr

gdal.UseExceptions()
gdal.SetConfigOption("GDAL_NUM_THREADS", "1")
gdal.SetConfigOption("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
BLOCK = 128
FLAT = 1.0          # a block that agrees within one grey level as it lies is not out of place


def opened(path):
    return gdal.Open(("/vsicurl/" if path.startswith("http") else "") + path)


def quad_level(href, res):
    """The quad's reduced level nearest the file's pixel size, as a dataset in memory."""
    ds = opened(href)
    gt, band = ds.GetGeoTransform(), ds.GetRasterBand(1)
    sizes = [(band.GetOverview(i).XSize, band.GetOverview(i).YSize) for i in range(band.GetOverviewCount())]
    k = min(range(len(sizes)), key=lambda i: abs(math.log(gt[1] * ds.RasterXSize / sizes[i][0] / res)))
    w, h = sizes[k]
    mem = gdal.GetDriverByName("MEM").Create("", w, h, 3, gdal.GDT_Byte)
    mem.SetProjection(ds.GetProjection())
    mem.SetGeoTransform((gt[0], gt[1] * ds.RasterXSize / w, 0, gt[3], 0, gt[5] * ds.RasterYSize / h))
    mem.WriteArray(np.stack([ds.GetRasterBand(b).GetOverview(k).ReadAsArray() for b in (1, 2, 3)]))
    return mem, gt[1] * ds.RasterXSize / w


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("index")
    p.add_argument("state")
    p.add_argument("year", type=int)
    p.add_argument("--sample", type=int, default=40)
    p.add_argument("--zone", type=int)
    a = p.parse_args()
    with open(a.index, "rb") as f:
        rows = pq.ParquetFile(f).read(columns=["id", "naip:state", "naip:year", "proj:epsg", "assets"]).to_pylist()
    quads = sorted((r["id"], r["assets"]["image"]["href"]) for r in rows
                   if r["naip:state"] == a.state and r["naip:year"] == a.year and a.zone in (None, r["proj:epsg"]))
    chosen = random.Random(20261114).sample(quads, min(a.sample, len(quads)))
    ds = opened(a.file)
    fgt, mask = ds.GetGeoTransform(), ds.GetRasterBand(1).GetMaskBand()
    res, srs = fgt[1], osr.SpatialReference(wkt=ds.GetProjection())
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    blocks, per_quad = [], []
    for quad_id, href in chosen:
        level, level_res = quad_level(href, res)
        qgt, qsrs = level.GetGeoTransform(), osr.SpatialReference(wkt=level.GetProjection())
        qsrs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        corners = [(qgt[0] + i * qgt[1] * level.RasterXSize, qgt[3] + j * qgt[5] * level.RasterYSize) for i in (0, 1) for j in (0, 1)]
        xs, ys, _ = zip(*osr.CoordinateTransformation(qsrs, srs).TransformPoints(corners))
        c0, c1 = max(0, math.ceil((min(xs) - fgt[0]) / res)), min(ds.RasterXSize, math.floor((max(xs) - fgt[0]) / res))
        r0, r1 = max(0, math.ceil((fgt[3] - max(ys)) / res)), min(ds.RasterYSize, math.floor((fgt[3] - min(ys)) / res))
        if c1 - c0 < BLOCK or r1 - r0 < BLOCK:
            continue
        want = gdal.Warp("", level, format="MEM", dstSRS=srs.ExportToWkt(), width=c1 - c0, height=r1 - r0, dstAlpha=True,
                         outputBounds=(fgt[0] + c0 * res, fgt[3] - r1 * res, fgt[0] + c1 * res, fgt[3] - r0 * res),
                         resampleAlg="bilinear", srcNodata=0, warpOptions=["NUM_THREADS=1"]).ReadAsArray().astype(np.float32)
        got = ds.ReadAsArray(c0, r0, c1 - c0, r1 - r0)[:3].astype(np.float32)
        valid = (want[3] > 0) & (mask.ReadAsArray(c0, r0, c1 - c0, r1 - r0) > 0)
        found = []
        for y in range(1, r1 - r0 - BLOCK, BLOCK):
            for x in range(1, c1 - c0 - BLOCK, BLOCK):
                if valid[y - 1:y + BLOCK + 1, x - 1:x + BLOCK + 1].mean() < 1:
                    continue
                w = want[:3, y:y + BLOCK, x:x + BLOCK]
                moved = {(dx, dy): float(np.abs(got[:, y + dy:y + dy + BLOCK, x + dx:x + dx + BLOCK] - w).mean())
                         for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
                best = min(moved, key=moved.get)
                mse = float(((got[:, y:y + BLOCK, x:x + BLOCK] - w) ** 2).mean())
                found.append({"psnr_db": round(10 * math.log10(255 ** 2 / max(mse, 1e-9)), 2),
                              "better_moved": list(best) if best != (0, 0) and moved[(0, 0)] >= FLAT
                              and moved[best] < 0.7 * moved[(0, 0)] else None})
        if found:
            per_quad.append({"id": quad_id, "level_m": round(level_res, 3), "blocks": len(found),
                             "blocks_better_moved": sum(1 for b in found if b["better_moved"]),
                             "lowest_psnr_db": min(b["psnr_db"] for b in found)})
            blocks += found
    psnrs = sorted(b["psnr_db"] for b in blocks)
    print(json.dumps({"file": a.file, "pixel_m": res, "quads_sampled": len(per_quad), "blocks": len(blocks),
                      "blocks_better_moved_by_one_pixel": sum(1 for b in blocks if b["better_moved"]),
                      "quads_with_a_moved_block": sum(1 for q in per_quad if q["blocks_better_moved"]),
                      "psnr_db": {"lowest": psnrs[0], "median": psnrs[len(psnrs) // 2]} if psnrs else None,
                      "quads": per_quad}, indent=1))


if __name__ == "__main__":
    main()
