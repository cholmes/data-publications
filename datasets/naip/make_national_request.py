#!/usr/bin/env python3
"""The request overview.py takes for the national file, from the state overview files' results.

    python3 make_national_request.py <folder of state *-result.json> <bucket> <key prefix of the state files> \
        <out request.json> --out-key KEY --result-key KEY [--zoom 9] [--quad-index naip.parquet]

The national file is one Web Mercator picture on the standard zoom grid (256 pixel tiles),
finest level --zoom. Its sources are the state files, each read at the level one step finer
than the national pixel and averaged. A later source lies over an earlier one, so the
sources are listed oldest flight year first: where a state has two years the later shows.

With --quad-index, a state file whose state and year that index does not list is left out. The
index leaves out the years in which only part of a state was flown again (partial_years.py),
so the country shows one flight per state.
"""
import argparse
import glob
import json
import math
import os

WEB_ZOOM_0 = 156543.03392804097          # metres per pixel at zoom 0, 256-pixel tiles


def main():
    p = argparse.ArgumentParser()
    p.add_argument("results")
    p.add_argument("bucket")
    p.add_argument("prefix")
    p.add_argument("out")
    p.add_argument("--out-key", required=True)
    p.add_argument("--result-key", required=True)
    p.add_argument("--zoom", type=int, default=9)
    p.add_argument("--name", default="national-latest")
    p.add_argument("--quad-index", help="leave out the state files whose state and year this index does not list")
    a = p.parse_args()
    listed = None
    if a.quad_index:
        import pyarrow.parquet as pq
        with open(a.quad_index, "rb") as f:
            table = pq.ParquetFile(f).read(columns=["naip:state", "naip:year"])
        listed = set(zip(table["naip:state"].to_pylist(), table["naip:year"].to_pylist()))
    res = WEB_ZOOM_0 / 2 ** a.zoom
    sources = []
    for path in glob.glob(os.path.join(a.results, "*-result.json")):
        with open(path) as f:
            r = json.load(f)
        state, year = r["name"].split("-")[:2]
        if listed is not None and (state, int(year)) not in listed:
            print("left out, not in the quad index:", r["name"])
            continue
        sources.append((int(year), r["name"], r["target_epsg"], r["res"]))
    finest = min(s[3] for s in sources)
    # The level of the state files to read: the coarsest that is still finer than the national pixel
    # on the ground at 49 degrees north, the top of the country, where a Web Mercator metre is shortest.
    read_m = finest * 2 ** math.floor(math.log2(res * math.cos(math.radians(49)) / finest))
    with open(a.out, "w") as f:
        json.dump({"bucket": a.bucket, "name": a.name, "target_epsg": 3857, "res": res, "read_m": read_m,
                   "out_key": a.out_key, "result_key": a.result_key, "collar_ids": [],
                   "quads": [[name, f"{a.prefix}{name}.tif", epsg, gsd] for _, name, epsg, gsd in sorted(sources)]}, f)
    print(a.name, len(sources), "state files, pixel", round(res, 3), "m, reading their", read_m, "m level")


if __name__ == "__main__":
    main()
