#!/usr/bin/env python3
"""Look for a line along quad edges when adjacent quads are drawn together at overview scales.

Each quad in turn is drawn on top of its neighbours, on its own UTM grid, at each overview
scale (2, 4, 8, 16 and 32 times the pixel size), with nearest-neighbour sampling so a
one-pixel line survives. Along the top quad's south and east edges (the last row and last
column of its overviews), the mean of the two mosaic rows or columns at the edge is divided
by the mean of the ten on either side. A ratio near 1 is no line.

    python3 seam_check.py <out.json> <file> <file> [<file> ...]

Files are GDAL paths (for example /vsis3/bucket/key.tif) of adjacent quads; they may be in
different UTM zones.
"""

import json
import sys

import numpy as np
from osgeo import gdal

gdal.UseExceptions()
SCALES = (2, 4, 8, 16, 32)


def edge_ratio(profile, at):
    """Mean of the two values at `at` over the mean of the ten on either side of them."""
    near = profile[at - 1:at + 1]
    around = np.concatenate([profile[at - 11:at - 1], profile[at + 1:at + 11]])
    return round(float(near.mean() / max(around.mean(), 1.0)), 3)


def main(out_path, files):
    results = []
    for top in files:
        ds = gdal.Open(top)
        x0, dx, _, y1, _, dy = ds.GetGeoTransform()
        x1, y0 = x0 + dx * ds.RasterXSize, y1 + dy * ds.RasterYSize
        srs = ds.GetSpatialRef().ExportToWkt()
        others = [f for f in files if f != top]
        for scale in SCALES:
            res = abs(dx) * scale
            margin = 40 * res
            bounds = (x0 - margin, y0 - margin, x1 + margin, y1 + margin)
            mosaic = gdal.Warp("", others + [top], format="MEM", dstSRS=srs, outputBounds=bounds,
                               xRes=res, yRes=res, resampleAlg="near")
            a = mosaic.GetRasterBand(1).ReadAsArray().astype(np.float64)
            # rows and columns of the mosaic that fall inside the top quad
            c0, c1 = int(round(margin / res)), a.shape[1] - int(round(margin / res))
            r0, r1 = int(round(margin / res)), a.shape[0] - int(round(margin / res))
            south = edge_ratio(a[:, c0 + 5:c1 - 5].mean(axis=1), r1 - 1)
            east = edge_ratio(a[r0 + 5:r1 - 5, :].mean(axis=0), c1 - 1)
            covered = float((a[r1:r1 + 20, c0:c1] > 0).mean()), float((a[r0:r1, c1:c1 + 20] > 0).mean())
            results.append({"top": top.rsplit("/", 1)[-1], "scale": scale, "south": south, "east": east,
                            "neighbour_cover_south": round(covered[0], 2),
                            "neighbour_cover_east": round(covered[1], 2)})
    judged = [r[k] for r in results for k, c in (("south", "neighbour_cover_south"), ("east", "neighbour_cover_east")) if r[c] > 0.9]
    summary = {"files": len(files), "edges_judged": len(judged),
               "lowest_ratio": min(judged) if judged else None, "highest_ratio": max(judged) if judged else None}
    with open(out_path, "w") as f:
        json.dump({"summary": summary, "edges": results}, f, indent=1)
        f.write("\n")
    for r in results:
        print(r)
    print(json.dumps(summary))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
