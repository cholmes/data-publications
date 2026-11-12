#!/usr/bin/env python3
"""STAC-GeoParquet indexes for the grid test files, in the same shape as the published quad
index, so the browser demo can draw the tiles or the 100 km file from an index the same way.

    uv run --no-project --with pyarrow==21.0.0 --with pyproj==3.7.2 python make_test_indexes.py \
        <datasets/naip dir> <tile receipts dir> <square receipts dir> <public base url> <out dir>
"""
import copy, glob, json, sys
sys.path.insert(0, sys.argv[1])
import build_stac_index as b

tiles_dir, square_dir, base, out = sys.argv[2:6]
def rows(receipts_dir):
    result, transformers = [], {}
    for f in sorted(glob.glob(receipts_dir + "/*.json")):
        r = json.load(open(f))
        key = r["out_uri"].split("/", 3)[3]
        fake = copy.deepcopy(r)   # item() reads state, year and date from a quad path
        fake["out_uri"] = "s3://x/ut/2024/60cm/rgb/grid/m_0_xx_12_060_20240701.tif"
        row = b.item(fake, "", transformers)
        row["assets"]["image"]["href"] = base + key.split("_proto/grid-1/", 1)[1]
        result.append(row)
    return result
tiles = rows(tiles_dir)
b.sort_rows(tiles, "hilbert")
b.write(tiles, out + "/tiles-stac.parquet", 512)
b.write(rows(square_dir), out + "/square-stac.parquet", 512)
