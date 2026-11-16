#!/usr/bin/env python3
"""Write a STAC GeoParquet index in several layouts, to measure which is cheapest for a map to open.

    python3 index_variants.py <stac index.parquet> <out dir> <variant> [<variant> ...]

Rows and values are the same in every variant; only the columns kept, the row order and the
grouping differ. A variant is named <columns>-<order>-<grouping>:

    columns    all     every column
               lean    only what a map draws from (LEAN), and of each asset only its address

    order      yearhilbert   by year, then along a Hilbert curve (as published)
               hilbert       along the Hilbert curve alone, newest first where rows share a place
               morton        along a Z-order curve, newest first where rows share a place
               strips        in half-degree bands of latitude, west to east within a band
               newesthilbert the newest row of each place along the Hilbert curve, then the
                             second newest of each place, and so on

    grouping   g512          512 rows a row group, one page per column in each
               g8192p64      8,192 rows a row group, written as pages of 64 rows with Parquet's
                             page index (per-page bounds and addresses), so a reader can take
                             single pages. Any two numbers work.

A reader fetches the footer before any row, and the footer grows with row groups times leaf
columns. With pages, the footer is small and the per-page bounds are read only for the row
groups in view. In a paged variant only the columns with few distinct values keep a dictionary:
a dictionary is one block per row group, and a reader taking one page would have to take all of it.

Prints one line per variant: bytes, footer bytes, row groups, leaf columns.
"""
import os
import re
import sys

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from build_stac_index import hilbert

STATISTICS = ["bbox.xmin", "bbox.ymin", "bbox.xmax", "bbox.ymax", "datetime"]
LEAN = ["id", "geometry", "bbox", "datetime", "gsd", "naip:state", "naip:year", "proj:code", "assets"]
FEW_VALUES = ["gsd", "naip:state", "naip:year", "proj:code"]


def morton(lon, lat, order=16):
    x = int((lon + 180) / 360 * (1 << order))
    y = int((lat + 90) / 180 * (1 << order))
    d = 0
    for bit in range(order):
        d |= ((x >> bit) & 1) << (2 * bit) | ((y >> bit) & 1) << (2 * bit + 1)
    return d


def order_of(table, how):
    """The row numbers of the table in the wanted order."""
    if how == "yearhilbert":
        return list(range(table.num_rows))
    bbox = table["bbox"].combine_chunks()
    lon = pc.divide(pc.add(bbox.field("xmin"), bbox.field("xmax")), 2).to_pylist()
    lat = pc.divide(pc.add(bbox.field("ymin"), bbox.field("ymax")), 2).to_pylist()
    when = table["datetime"].cast(pa.int64()).to_pylist()
    rows = range(table.num_rows)
    if how == "strips":
        return sorted(rows, key=lambda i: (int(lat[i] // 0.5), lon[i], -when[i]))
    curve = morton if how == "morton" else hilbert
    place = [curve(lon[i], lat[i]) for i in rows]
    if how in ("hilbert", "morton"):
        return sorted(rows, key=lambda i: (place[i], -when[i]))
    if how == "newesthilbert":
        rank, seen = [0] * table.num_rows, {}
        for i in sorted(rows, key=lambda i: (place[i], -when[i])):
            rank[i] = seen.get(place[i], 0)
            seen[place[i]] = rank[i] + 1
        return sorted(rows, key=lambda i: (rank[i], place[i]))
    raise SystemExit(f"unknown order {how}")


def main():
    source, out, variants = sys.argv[1], sys.argv[2], sys.argv[3:]
    os.makedirs(out, exist_ok=True)
    with open(source, "rb") as f:
        table = pq.ParquetFile(f).read()
    # The lean copy keeps one thing from each asset: where the file is.
    image = table["assets"].combine_chunks().field("image")
    href = pa.StructArray.from_arrays([pa.StructArray.from_arrays([image.field("href")], names=["href"])], names=["image"])
    lean = table.select(LEAN).set_column(LEAN.index("assets"), "assets", href)
    orders = {}
    for name in variants:
        columns, how, grouping = name.split("-")
        group, page = re.fullmatch(r"g(\d+)(?:p(\d+))?", grouping).groups()
        if how not in orders:
            orders[how] = pa.array(order_of(table, how))
        rows = (lean if columns == "lean" else table).take(orders[how])
        path = os.path.join(out, name + ".parquet")
        paged = {} if page is None else {"write_page_index": True, "data_page_size": 1, "write_batch_size": int(page),
                                          "use_dictionary": FEW_VALUES}
        pq.write_table(rows, path, row_group_size=int(group), compression="zstd", write_statistics=STATISTICS, **paged)
        meta = pq.ParquetFile(path).metadata
        with open(path, "rb") as f:
            f.seek(-8, os.SEEK_END)
            footer = int.from_bytes(f.read(4), "little")
        print(name, os.path.getsize(path), "bytes", footer, "footer bytes", meta.num_row_groups, "row groups", meta.num_columns, "leaf columns", flush=True)


if __name__ == "__main__":
    main()
