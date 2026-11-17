"""Check a built release against the pinned Census inputs. Separate from build.py on purpose: it
rereads the shapefiles, the gazetteer files and the estimates file with its own code.

    validate.py --release DIR [--source-cache DIR] [--report NEW_FILE]

Exits 1 and writes status "failed" when any check of validation-plan.md fails. The report has the
shape the shared packager expects of a source-fidelity report.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import struct
import sys
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
import shapely

from common import ADDED, BBOX_FIELDS, hilbert_keys
from source import FILES, LAYERS, digest, verified_file

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CACHE_DEFAULT = REPO / ".local/us-census-places/source"
WINDOWS = {"Front Range": [-105.6, 39.5, -104.6, 40.3], "central Ohio": [-83.4, 39.7, -82.6, 40.3],
           "Los Angeles basin": [-118.7, 33.7, -117.6, 34.4], "Atlanta": [-84.7, 33.5, -84.1, 34.1]}


class Failed(Exception):
    pass


def need(condition: bool, message: str) -> None:
    if not condition:
        raise Failed(message)


def wkb_bounds(value: bytes) -> tuple[float, float, float, float]:
    """Bounds of a 2D Polygon or MultiPolygon read straight from its WKB, without a geometry library."""
    xs: list[float] = []
    ys: list[float] = []

    def polygon(at: int, order: str) -> int:
        (rings,) = struct.unpack_from(order + "I", value, at)
        at += 4
        for _ in range(rings):
            (points,) = struct.unpack_from(order + "I", value, at)
            at += 4
            flat = np.frombuffer(value, dtype=order + "f8", count=points * 2, offset=at)
            xs.extend((float(flat[0::2].min()), float(flat[0::2].max())))
            ys.extend((float(flat[1::2].min()), float(flat[1::2].max())))
            at += points * 16
        return at

    def geometry(at: int) -> int:
        order = "<" if value[at] == 1 else ">"
        (kind,) = struct.unpack_from(order + "I", value, at + 1)
        at += 5
        if kind == 3:
            return polygon(at, order)
        need(kind == 6, f"unexpected WKB geometry type {kind}")
        (parts,) = struct.unpack_from(order + "I", value, at)
        at += 4
        for _ in range(parts):
            at = geometry(at)
        return at

    need(geometry(0) == len(value), "WKB has trailing bytes")
    return min(xs), min(ys), max(xs), max(ys)


def funcstat_of(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as z:
        (member,) = [n for n in z.namelist() if n.endswith(".txt")]
        rows = csv.reader(io.StringIO(z.read(member).decode("utf-8")), delimiter="\t")
        header = [h.strip() for h in next(rows)]
        out: dict[str, str] = {}
        for row in rows:
            record = dict(zip(header, (cell.strip() for cell in row)))
            need(out.setdefault(record["GEOID"], record["FUNCSTAT"]) == record["FUNCSTAT"],
                 f"{path.name}: GEOID {record['GEOID']} has two FUNCSTAT values")
    return out


def population_of(path: Path, sumlev: str) -> dict[str, int]:
    parts = {"050": ("STATE", "COUNTY"), "162": ("STATE", "PLACE"), "061": ("STATE", "COUNTY", "COUSUB")}[sumlev]
    out: dict[str, int] = {}
    with path.open(encoding="latin-1", newline="") as stream:
        for record in csv.DictReader(stream):
            if record["SUMLEV"] != sumlev:
                continue
            key, value = "".join(record[p] for p in parts), int(record["POPESTIMATE2023"])
            need(out.setdefault(key, value) == value, f"{path.name}: {sumlev} {key} has two estimates")
    return out


def check_layer(cache: Path, asset: str, path: Path) -> dict[str, Any]:
    spec = LAYERS[asset]
    meta, source = pyogrio.read_arrow("/vsizip/" + str((cache / spec["file"]).resolve()))
    source = source.combine_chunks()
    file = pq.ParquetFile(path)
    out = file.read()
    rows = source.num_rows
    need(rows == spec["rows"], f"{asset}: source has {rows} rows, expected {spec['rows']}")
    need(out.num_rows == rows, f"{asset}: output has {out.num_rows} rows, source {rows}")
    need(out.schema.names == [*spec["fields"], "geometry", *ADDED],
         f"{asset}: output columns {out.schema.names}")
    order = out["source_row"].to_numpy()
    need(np.array_equal(np.sort(order), np.arange(1, rows + 1)), f"{asset}: source_row is not 1..{rows} exactly once")
    back = pa.array(np.argsort(order, kind="stable"))
    restored = out.take(back)
    for name in spec["fields"]:
        a, b = source[name], restored[name]
        need(a.type == b.type, f"{asset}.{name}: type {b.type}, source {a.type}")
        need(a.null_count == b.null_count and a.is_null().equals(b.is_null()), f"{asset}.{name}: nulls differ")
        need(a.equals(b), f"{asset}.{name}: values differ")
    source_wkb = source[meta["geometry_name"] or "wkb_geometry"].cast(pa.binary()).to_pylist()
    output_wkb = restored["geometry"].to_pylist()
    need(out.schema.field("geometry").type == pa.binary(), f"{asset}: geometry is not WKB binary")
    for row, (a, b) in enumerate(zip(source_wkb, output_wkb), start=1):
        need(b is not None and len(a) == len(b) and hashlib.sha256(a).digest() == hashlib.sha256(b).digest(),
             f"{asset}: WKB of source_row {row} differs")
    bounds = np.array([wkb_bounds(value) for value in output_wkb])
    box = restored["bbox"].combine_chunks()
    for i, name in enumerate(BBOX_FIELDS):
        child = box.field(name)
        need(child.null_count == 0 and np.array_equal(child.to_numpy(), bounds[:, i]), f"{asset}: bbox.{name} differs")
    extent = [float(bounds[:, 0].min()), float(bounds[:, 1].min()), float(bounds[:, 2].max()), float(bounds[:, 3].max())]
    geo = json.loads(file.schema_arrow.metadata[b"geo"])["columns"]["geometry"]
    need(geo["bbox"] == extent, f"{asset}: GeoParquet bounds {geo['bbox']}, recomputed {extent}")
    need(geo["encoding"] == "WKB" and geo["crs"]["id"] == {"authority": "EPSG", "code": 4269},
         f"{asset}: GeoParquet metadata does not declare WKB in EPSG:4269")
    need(set(geo["geometry_types"]) == {["", "", "", "Polygon", "", "", "MultiPolygon"][shapely.get_type_id(g)]
                                        for g in shapely.from_wkb(output_wkb)}, f"{asset}: geometry types differ")
    geoid = restored["GEOID"].to_pylist()
    funcstat = funcstat_of(cache / spec["gazetteer"]) if spec["gazetteer"] else {}
    population = population_of(cache / "sub-est2023.csv", spec["sumlev"])
    need(restored["gaz_funcstat"].to_pylist() == [funcstat.get(g) for g in geoid], f"{asset}: gaz_funcstat differs")
    need(restored["popest_2023"].to_pylist() == [population.get(g) for g in geoid], f"{asset}: popest_2023 differs")
    written = np.array([wkb_bounds(value) for value in out["geometry"].to_pylist()])
    keys = hilbert_keys(written)
    pairs = list(zip(keys.tolist(), order.tolist()))
    need(all(a <= b for a, b in zip(pairs, pairs[1:])), f"{asset}: rows are not in Hilbert order")
    pruning = {}
    groups = file.metadata.num_row_groups
    paths = {file.metadata.row_group(0).column(i).path_in_schema: i for i in range(file.metadata.num_columns)}
    for label, (west, south, east, north) in WINDOWS.items():
        matching = int(((written[:, 0] <= east) & (written[:, 2] >= west) & (written[:, 1] <= north) & (written[:, 3] >= south)).sum())
        read = 0
        for g in range(groups):
            stats = {name: file.metadata.row_group(g).column(paths[f"bbox.{name}"]).statistics for name in BBOX_FIELDS}
            if stats["xmin"].min <= east and stats["xmax"].max >= west and stats["ymin"].min <= north and stats["ymax"].max >= south:
                read += 1
        exempt = groups < 4
        pruning[label] = {"rows_matching": matching, "row_groups": groups, "row_groups_read": read, "exempt": exempt}
        if matching and not exempt:
            need(read * 2 <= groups, f"{asset}: {label} reads {read} of {groups} row groups")
    counts: dict[str, int] = {}
    for value in out["gaz_funcstat"].to_pylist():
        counts[value or "null"] = counts.get(value or "null", 0) + 1
    return {"asset_id": asset, "sha256": digest(path), "size_bytes": path.stat().st_size, "rows": rows,
            "source_fields_compared": len(spec["fields"]), "wkb_values_compared": rows, "bbox_values_recomputed": rows * 4,
            "gaz_funcstat_counts": dict(sorted(counts.items())),
            "popest_2023_present": rows - out["popest_2023"].null_count, "pruning": pruning}


def validate(release: Path, cache: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"status": "failed", "release": release.name, "assets": [], "evidence": {}}
    try:
        report["evidence"]["inputs"] = {name: verified_file(cache / name)["sha256"] for name in FILES}
        for asset in LAYERS:
            report["assets"].append(check_layer(cache, asset, release / "data" / f"{asset}.parquet"))
        report["status"] = "passed"
    except Failed as failure:
        report["evidence"]["failure"] = str(failure)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--source-cache", type=Path, default=CACHE_DEFAULT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.report and args.report.exists():
        raise SystemExit("Use a new report path; earlier reports are kept.")
    report = validate(args.release, args.source_cache)
    text = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.write_text(text, encoding="utf-8")
    print(text)
    sys.exit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
