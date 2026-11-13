#!/usr/bin/env python3
"""Build the flight-date table the viewer in this folder reads.

One record per quarter quad per survey: which 3.75 minute cell it is, the date in its name,
the survey year, the state and the resolution. Two inputs, both already on disk:

- the Microsoft Planetary Computer STAC-GeoParquet of its `naip` collection (2010 to 2023),
  one part per year;
- the manifests of 2024 and 2025 made from a listing of `s3://naip-analytic`.

    uv run --no-project --with pyarrow==21.0.0 --with numpy==2.2.6 python build_dates.py \
        <dir of MPC parts> <dir of 2024-2025 manifests> dates.bin [--hosted ut-2024,nh-2025,...]

The cell of a quad comes from its name (latitude and longitude of the one degree block, the
quad number 1 to 64 counted from the north-west, and the quarter). For the Planetary Computer
rows the same cell is also taken from the item's bounding box, and the two are compared; the
count that disagree is printed and written into the file's header.

The date is the one in the file name. It is the date most of the quad was flown, not a date
for every pixel (see "Flight dates" in ../README.md).
"""
import argparse
import datetime
import glob
import gzip
import json
import os
import re
import struct

import numpy as np
import pyarrow.parquet as pq

WEST, NORTH, CELL = -125.0, 50.0, 0.0625           # conterminous United States
COLS, ROWS = 944, 416                              # to 66 W and 24 N
EPOCH = datetime.date(2000, 1, 1)
NAME = re.compile(r"^([a-z]{2})_m_(\d{2})(\d{3})(\d{2})_(nw|ne|sw|se)_(\d{2})_([\w.]+?)_(\d{8})(?:_\d+)?$", re.IGNORECASE)
RESOLUTION_CM = {"1": 100, "h": 50, ".5": 50, ".6": 60, "060": 60, "030": 30, "100": 100, "050": 50, "30": 30,
                 "60": 60, "2": 200}


def cell_from_name(match):
    """(row, col) of the grid, or None when the quad is outside it."""
    lat, lon, quad, quarter = int(match[2]), int(match[3]), int(match[4]), match[5].lower()
    row_in_block, col_in_block = divmod(quad - 1, 8)
    north = lat + 1 - row_in_block * 0.125 - (0.0625 if quarter[0] == "s" else 0)
    west = -(lon + 1) + col_in_block * 0.125 + (0.0625 if quarter[1] == "e" else 0)
    row, col = round((NORTH - north) / CELL), round((west - WEST) / CELL)
    return (row, col) if 0 <= row < ROWS and 0 <= col < COLS else None


def cell_from_bbox(bbox):
    lon, lat = (bbox["xmin"] + bbox["xmax"]) / 2, (bbox["ymin"] + bbox["ymax"]) / 2
    row, col = int((NORTH - lat) // CELL), int((lon - WEST) // CELL)
    return (row, col) if 0 <= row < ROWS and 0 <= col < COLS else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mpc_parts")
    p.add_argument("manifests")
    p.add_argument("out")
    p.add_argument("--hosted", default="", help="state-years hosted in the product, e.g. ut-2024,nh-2025")
    a = p.parse_args()

    records, states = [], {}
    stats = {"unparsed_names": 0, "outside_grid": 0, "name_and_bbox_disagree": 0, "resolution_unknown": 0}

    def add(match, survey_year, cell):
        flown = datetime.datetime.strptime(match[8], "%Y%m%d").date()
        cm = RESOLUTION_CM.get(match[7], 0)
        stats["resolution_unknown"] += cm == 0
        records.append((cell[0] * COLS + cell[1], (flown - EPOCH).days, survey_year - 2000,
                        states.setdefault(match[1].lower(), len(states)), cm))

    for part in sorted(glob.glob(os.path.join(a.mpc_parts, "*.parquet"))):
        table = pq.read_table(part, columns=["id", "bbox", "naip:year"]).to_pylist()
        for item in table:
            match = NAME.match(item["id"])
            if not match:
                stats["unparsed_names"] += 1
                continue
            by_name, by_bbox = cell_from_name(match), cell_from_bbox(item["bbox"])
            if by_name is None:
                stats["outside_grid"] += 1
                continue
            stats["name_and_bbox_disagree"] += by_name != by_bbox
            add(match, int(item["naip:year"]), by_name)
        print(os.path.basename(part)[:8], len(table), stats, flush=True)

    for manifest in sorted(glob.glob(os.path.join(a.manifests, "*.jsonl"))):
        survey_year = int(os.path.basename(manifest).split("-")[1])
        with open(manifest) as f:
            for line in f:
                match = NAME.match(json.loads(line)["id"])
                if not match:
                    stats["unparsed_names"] += 1
                    continue
                cell = cell_from_name(match)
                if cell is None:
                    stats["outside_grid"] += 1
                    continue
                add(match, survey_year, cell)

    records.sort()
    cell, day, year, state, cm = (np.array(column, dtype=kind) for column, kind in
                                  zip(zip(*records), ("<u4", "<u2", "u1", "u1", "u1")))
    header = {
        "schema": "naip-flight-dates@1", "west": WEST, "north": NORTH, "cell_degrees": CELL,
        "cols": COLS, "rows": ROWS, "epoch": EPOCH.isoformat(), "records": len(records),
        "cells_with_imagery": int(len(np.unique(cell))), "states": list(states),
        "hosted": [s for s in a.hosted.split(",") if s],
        "sources": "Microsoft Planetary Computer naip STAC-GeoParquet (2010 to 2023); "
                   "s3://naip-analytic listing of 2026-11-10 (2024 and 2025)",
        "arrays": [["cell", "u4"], ["day", "u2"], ["survey_year", "u1"], ["state", "u1"], ["resolution_cm", "u1"]],
        **stats,
    }
    head = json.dumps(header).encode()
    head += b" " * (-(4 + len(head)) % 4)
    body = struct.pack("<I", len(head)) + head + b"".join(x.tobytes() for x in (cell, day, year, state, cm))
    with gzip.open(a.out + ".gz", "wb", compresslevel=6) as f:
        f.write(body)
    print(json.dumps(header | {"states": len(states), "bytes": len(body),
                               "gz_bytes": os.path.getsize(a.out + ".gz")}, indent=1))


if __name__ == "__main__":
    main()
