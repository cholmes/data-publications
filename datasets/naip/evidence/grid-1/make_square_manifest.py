#!/usr/bin/env python3
"""Tile manifest and square description for one 100 km square of the shared-grid test.

    uv run --no-project --with pyarrow==21.0.0 python make_square_manifest.py \
        <utah index.parquet> <utah source manifest.jsonl> <out dir> <bucket> <prefix>
"""
import json, os, sys
import pyarrow.parquet as pq

RES, BLOCK, TILE_BLOCKS, EPSG = 0.6, 512, 32, 26912
EAST, NORTH, SIDE = 400_000, 4_400_000, 100_000
index, manifest, out, bucket, prefix = sys.argv[1:6]
import math
col0 = math.ceil(EAST / RES - 0.5 - 1e-9)                    # first column whose centre is inside
col1 = math.ceil((EAST + SIDE) / RES - 0.5 - 1e-9)           # first column whose centre is past it
row0 = math.floor((NORTH + SIDE) / RES + 0.5 + 1e-9)         # top edge, in pixels north of the origin
row1 = math.floor(NORTH / RES + 0.5 + 1e-9)
width, height, span = col1 - col0, row0 - row1, BLOCK * TILE_BLOCKS
bounds = {r["id"]: (list(r["native_bounds"].values()) if isinstance(r["native_bounds"], dict) else list(r["native_bounds"]))
          for r in pq.read_table(index, columns=["id", "epsg", "native_bounds"]).to_pylist() if r["epsg"] == EPSG}
quads = [q for q in map(json.loads, open(manifest)) if q["id"] in bounds]
name = f"utm12_e{EAST // 1000}_n{NORTH // 1000}"
tiles, described = [], []
for row in range(math.ceil(height / span)):
    for col in range(math.ceil(width / span)):
        c, r = col0 + col * span, row0 - row * span
        w, h = min(span, width - col * span), min(span, height - row * span)
        x0, x1, y1, y0 = c * RES, (c + w) * RES, r * RES, (r - h) * RES
        sources = [{k: q[k] for k in ("src_bucket", "mrf", "idx", "lrc")} for q in quads
                   if bounds[q["id"]][0] < x1 and bounds[q["id"]][2] > x0 and bounds[q["id"]][1] < y1 and bounds[q["id"]][3] > y0]
        key = f"tiles/{name}/r{row:02d}_c{col:02d}.tif"
        tiles.append({"id": f"{name}-r{row:02d}-c{col:02d}", "out_key": key, "epsg": EPSG, "res": RES,
                      "col0": c, "row0": r, "width": w, "height": h, "sources": sources})
        described.append({"row": row, "col": col, "bucket": bucket, "key": prefix + key})
os.makedirs(out, exist_ok=True)
with open(f"{out}/{name}-tiles.jsonl", "w") as f:
    for t in tiles:
        f.write(json.dumps(t) + "\n")
json.dump({"id": name, "epsg": EPSG, "res": RES, "col0": col0, "row0": row0, "width": width, "height": height,
           "tile_blocks": TILE_BLOCKS, "out_key": f"square/{name}.tif", "tiles": described},
          open(f"{out}/{name}-square.json", "w"), indent=1)
used = {s["mrf"] for t in tiles for s in t["sources"]}
print(json.dumps({"square": name, "width": width, "height": height, "origin": [col0 * RES, row0 * RES], "tiles": len(tiles),
                  "source_quads": len(used), "sources_per_tile": [min(len(t["sources"]) for t in tiles), max(len(t["sources"]) for t in tiles)],
                  "source_gb": round(sum(q["lrc_bytes"] for q in quads if q["mrf"] in used) / 1e9, 1)}))
