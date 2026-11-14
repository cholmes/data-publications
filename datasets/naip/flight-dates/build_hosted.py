#!/usr/bin/env python3
"""List the hosted quads for the viewer: where each file is and where its corners are.

Reads the per-state index files made by ../build_index.py and writes hosted.json.gz:

    {"base": "<url prefix>", "quads": [[path, width, height, nw_lon, nw_lat, ne_lon, ne_lat,
                                         se_lon, se_lat, sw_lon, sw_lat], ...]}

    uv run --no-project --with pyarrow==21.0.0 python build_hosted.py hosted.json <index.parquet>...

The corners are the file's own corners in its UTM zone, turned to longitude and latitude by
the index builder. The viewer stretches each file between them.
"""
import gzip
import json
import struct
import sys

import pyarrow.parquet as pq

BASE = "https://s3.us-west-2.amazonaws.com/us-west-2.opendata.source.coop/nthh/naip/"


def main(out, indexes):
    quads = []
    for index in indexes:
        for row in pq.read_table(index, columns=["path", "width", "height", "geometry"]).to_pylist():
            # WKB polygon, one ring: south-west, south-east, north-east, north-west, south-west.
            sw, se, ne, nw = (struct.unpack_from("<dd", row["geometry"], 13 + 16 * i) for i in range(4))
            quads.append([row["path"], row["width"], row["height"],
                          *(round(v, 6) for corner in (nw, ne, se, sw) for v in corner)])
    quads.sort()
    with gzip.open(out + ".gz", "wt", compresslevel=6) as f:
        json.dump({"base": BASE, "quads": quads}, f, separators=(",", ":"))
    print(len(quads), "quads from", len(indexes), "index files")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
