#!/usr/bin/env python3
"""Which years of a state were flown again only in part, and so are left out of the indexes.

    python3 partial_years.py <quad index.parquet>

A year is partial when it holds under FULL of the quads an older year of the same state holds.
Most states are flown whole each time. Where a later year covers part of a state, listing it
puts two flights with different light and season side by side inside one state, in every map
that draws the newest file over a place. The files of a partial year stay where they are; the
indexes do not list them (build_stac_index.py, build_overview_index.py), and the national
file is made without them (make_national_request.py).

Prints the partial years with their counts and changes nothing.
"""
import collections
import sys

import pyarrow.parquet as pq

FULL = 0.9


def partial(counts):
    """Of {(state, year): quads}: the (state, year) holding under FULL of an older year's quads."""
    return {(state, year) for (state, year), n in counts.items()
            if any(s == state and y < year and n < FULL * m for (s, y), m in counts.items())}


def counts_of(states, years):
    return collections.Counter(zip(states, years))


def main():
    with open(sys.argv[1], "rb") as f:
        table = pq.ParquetFile(f).read(columns=["naip:state", "naip:year"])
    counts = counts_of(table["naip:state"].to_pylist(), table["naip:year"].to_pylist())
    for state, year in sorted(partial(counts)):
        older = {y: n for (s, y), n in sorted(counts.items()) if s == state and y < year}
        print(f"{state} {year}: {counts[state, year]} quads; older years {older}")


if __name__ == "__main__":
    main()
