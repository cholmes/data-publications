"""Fault tests: the validator must reject each damaged copy of a built layer, for the stated reason.

    US_CENSUS_PLACES_RELEASE=<built release> uv run --locked python -m unittest test_faults -v

Uses the counties layer of a real build (the smallest) and the pinned inputs in the source cache.
Skipped when no build is named.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from common import ROW_GROUP_SIZE
from validate import CACHE_DEFAULT, Failed, check_layer

RELEASE = os.environ.get("US_CENSUS_PLACES_RELEASE")
CACHE = Path(os.environ.get("US_CENSUS_PLACES_SOURCE", CACHE_DEFAULT))
ASSET = "counties"


def replace(table: pa.Table, name: str, values: list) -> pa.Table:
    at = table.schema.get_field_index(name)
    return table.set_column(at, table.schema.field(name), pa.array(values, type=table.schema.field(name).type))


def swapped(table: pa.Table) -> pa.Table:
    order = np.arange(table.num_rows)
    order[[10, 2000]] = order[[2000, 10]]
    return table.take(pa.array(order))


def bbox_changed(table: pa.Table) -> pa.Table:
    box = table["bbox"].combine_chunks()
    children = [box.field(i).to_pylist() for i in range(4)]
    children[0][5] -= 0.25
    names = [box.type.field(i).name for i in range(4)]
    at = table.schema.get_field_index("bbox")
    return table.set_column(at, table.schema.field("bbox"),
                            pa.StructArray.from_arrays([pa.array(c, type=pa.float64()) for c in children], names=names))


def wkb_changed(table: pa.Table) -> pa.Table:
    values = table["geometry"].to_pylist()
    damaged = bytearray(values[7])
    damaged[-1] ^= 1
    values[7] = bytes(damaged)
    return replace(table, "geometry", values)


def edit(name: str, row: int, value):
    def apply(table: pa.Table) -> pa.Table:
        values = table[name].to_pylist()
        values[row] = value(values[row]) if callable(value) else value
        return replace(table, name, values)
    return apply


FAULTS = {
    "removed row": (lambda t: t.slice(1), "rows"),
    "duplicated row": (lambda t: pa.concat_tables([t, t.slice(3, 1)]), "rows"),
    "changed value": (edit("NAME", 4, lambda v: v + "x"), "NAME: values differ"),
    "value turned null": (edit("NAME", 4, None), "NAME: nulls differ"),
    "changed source_row": (edit("source_row", 4, lambda v: v + 100000), "source_row is not"),
    "changed WKB byte": (wkb_changed, "WKB of source_row"),
    "changed bbox child": (bbox_changed, "bbox.xmin differs"),
    "changed gaz_funcstat": (edit("gaz_funcstat", 4, "A"), "gaz_funcstat differs"),
    "changed popest_2023": (edit("popest_2023", 4, lambda v: (v or 0) + 1), "popest_2023 differs"),
    "rows out of order": (swapped, "not in Hilbert order"),
}


@unittest.skipUnless(RELEASE, "set US_CENSUS_PLACES_RELEASE to a built release")
class Faults(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = Path(RELEASE) / "data" / f"{ASSET}.parquet"
        cls.table = pq.read_table(cls.path)

    def test_unchanged_passes(self) -> None:
        check_layer(CACHE, ASSET, self.path)

    def test_faults_are_rejected(self) -> None:
        for label, (damage, reason) in FAULTS.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / f"{ASSET}.parquet"
                pq.write_table(damage(self.table), path, row_group_size=ROW_GROUP_SIZE, compression="zstd")
                with self.assertRaises(Failed) as caught:
                    check_layer(CACHE, ASSET, path)
                self.assertIn(reason, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
