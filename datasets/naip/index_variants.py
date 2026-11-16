#!/usr/bin/env python3
"""Write the quad index in several layouts, to measure which is cheapest for a map to open.

    python3 index_variants.py <naip stac index.parquet> <out dir>

A reader fetches the footer before any row, and the footer grows with row groups times leaf
columns. Rows, order and values are the same in every variant; only the layout differs:

    groups-512     as published: every column, 512 rows a group
    groups-2048    every column, 2,048 rows a group
    groups-8192    every column, 8,192 rows a group
    lean-512       only what a map draws from (LEAN), 512 rows a group
    lean-2048      the same, 2,048 rows a group
    lean-8192      the same, 8,192 rows a group

Prints one line per variant: bytes, footer bytes, row groups, leaf columns.
"""
import os
import sys

import pyarrow as pa
import pyarrow.parquet as pq

STATISTICS = ["bbox.xmin", "bbox.ymin", "bbox.xmax", "bbox.ymax", "datetime", "naip:year"]
LEAN = ["id", "geometry", "bbox", "datetime", "gsd", "naip:state", "naip:year", "proj:code", "assets"]


def main():
    source, out = sys.argv[1:3]
    os.makedirs(out, exist_ok=True)
    with open(source, "rb") as f:
        table = pq.ParquetFile(f).read()
    # The lean copy keeps one thing from each asset: where the file is.
    image = table["assets"].combine_chunks().field("image")
    href = pa.StructArray.from_arrays([pa.StructArray.from_arrays([image.field("href")], names=["href"])], names=["image"])
    lean = table.select(LEAN).set_column(LEAN.index("assets"), "assets", href)
    for name, rows, group in (("groups-512", table, 512), ("groups-2048", table, 2048), ("groups-8192", table, 8192),
                              ("lean-512", lean, 512), ("lean-2048", lean, 2048), ("lean-8192", lean, 8192)):
        path = os.path.join(out, name + ".parquet")
        pq.write_table(rows, path, row_group_size=group, compression="zstd", write_statistics=STATISTICS)
        meta = pq.ParquetFile(path).metadata
        with open(path, "rb") as f:
            f.seek(-8, os.SEEK_END)
            footer = int.from_bytes(f.read(4), "little")
        print(name, os.path.getsize(path), "bytes", footer, "footer bytes", meta.num_row_groups, "row groups", meta.num_columns, "leaf columns", flush=True)


if __name__ == "__main__":
    main()
