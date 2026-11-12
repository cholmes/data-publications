#!/usr/bin/env python3
"""One quad built three ways from the lossless source: quality 65 with overviews at 85,
65 throughout, 85 throughout. Reports bytes and PSNR per level, for the pass marks in
VALIDATION.md ("Quality 65 at full resolution, 85 for overviews").

    AWS_REGION=us-west-2 python3 check.py <state/year/res/rgbir/block/name.mrf> <work dir> > result.json
"""
import json, os, struct, sys
import numpy as np
from osgeo import gdal
gdal.UseExceptions()
gdal.SetPathSpecificOption("/vsis3/naip-analytic", "AWS_REQUEST_PAYER", "requester")
key, work = sys.argv[1], sys.argv[2]
src = f"{work}/source.tif"
if not os.path.exists(src):
    gdal.Translate(src, "/vsis3/naip-analytic/" + key, bandList=[1, 2, 3], creationOptions=["TILED=YES", "COMPRESS=ZSTD", "BIGTIFF=YES"])
BUILDS = {"q65-ov85": (65, 85), "q65": (65, 65), "q85": (85, 85)}
for name, (q, oq) in BUILDS.items():
    gdal.Translate(f"{work}/{name}.tif", src, format="COG", creationOptions=["COMPRESS=JPEG", f"QUALITY={q}", f"OVERVIEW_QUALITY={oq}",
                   "BLOCKSIZE=512", "OVERVIEW_RESAMPLING=AVERAGE", "OVERVIEWS=IGNORE_EXISTING", "NUM_THREADS=4"])

def level_bytes(path):
    """Compressed bytes per image directory (full resolution first), from the block counts."""
    out, ds = [], gdal.Open(path)
    band = ds.GetRasterBand(1)
    for k in range(band.GetOverviewCount() + 1):
        b = band if k == 0 else band.GetOverview(k - 1)
        bx, by = b.GetBlockSize()
        n = 0
        for y in range(-(-b.YSize // by)):
            for x in range(-(-b.XSize // bx)):
                n += int(b.GetMetadataItem(f"BLOCK_SIZE_{x}_{y}", "TIFF") or 0)
        out.append(n)
    return out

def levels(path):
    ds = gdal.Open(path); band = ds.GetRasterBand(1)
    out = [ds.ReadAsArray().astype(np.float64)]
    for k in range(band.GetOverviewCount()):
        out.append(np.stack([ds.GetRasterBand(i).GetOverview(k).ReadAsArray() for i in (1, 2, 3)]).astype(np.float64))
    return out

def psnr(a, b):
    mse = ((a - b) ** 2).reshape(3, -1).mean(axis=1)
    return [None if m == 0 else round(float(10 * np.log10(255 ** 2 / m)), 2) for m in mse]

source = gdal.Open(src).ReadAsArray().astype(np.float64)
decoded = {n: levels(f"{work}/{n}.tif") for n in BUILDS}
result = {"quad": key, "builds": {}}
for n in BUILDS:
    ds = gdal.Open(f"{work}/{n}.tif")
    result["builds"][n] = {"file_bytes": os.path.getsize(f"{work}/{n}.tif"), "level_bytes": level_bytes(f"{work}/{n}.tif"),
                           "layout": ds.GetMetadataItem("LAYOUT", "IMAGE_STRUCTURE"), "block": ds.GetRasterBand(1).GetBlockSize(),
                           "sizes": [[a.shape[2], a.shape[1]] for a in decoded[n]],
                           "psnr_full_vs_source": psnr(decoded[n][0], source)}
m = decoded["q65-ov85"]
result["full_vs_all65_psnr_difference_db"] = [round(a - b, 3) for a, b in zip(result["builds"]["q65-ov85"]["psnr_full_vs_source"], result["builds"]["q65"]["psnr_full_vs_source"])]
result["overviews_vs_all85_psnr_db"] = [psnr(m[k], decoded["q85"][k]) for k in range(1, len(m))]
result["overviews_vs_all65_psnr_db"] = [psnr(m[k], decoded["q65"][k]) for k in range(1, len(m))]
# overview quality against the truth: each level averaged from the source the way GDAL does is
# not reproduced here; the all-85 file's levels stand in as the reference for pass mark 2.
edges = []
for a in m[1:]:
    lum = a.mean(axis=0)
    edges.append([round(float(lum[-1].mean() / lum[-2].mean()), 3), round(float(lum[:, -1].mean() / lum[:, -2].mean()), 3)])
result["overview_edge_ratios"] = edges
result["size_share_of_all85"] = round(result["builds"]["q65-ov85"]["file_bytes"] / result["builds"]["q85"]["file_bytes"], 4)
result["size_over_all65"] = round(result["builds"]["q65-ov85"]["file_bytes"] / result["builds"]["q65"]["file_bytes"], 4)
json.dump(result, sys.stdout, indent=1)
