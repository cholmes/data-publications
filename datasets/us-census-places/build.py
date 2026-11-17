"""Build the 2023 Census counties, places and county subdivisions as GeoParquet.

    build.py acquire [--cache DIR]                  download and verify the six pinned inputs
    build.py inspect [--source-cache DIR]           verify the inputs and print each layer's facts
    build.py build --output NEW_DIR [--source-cache DIR] [--allow-uncommitted]

One file per layer, every source row and field, geometry as GDAL decodes it, in EPSG:4269. Four
columns are appended (source_row, gaz_funcstat, popest_2023, bbox) and rows are written along a
Hilbert curve. validation-plan.md states the rules; validate.py checks the result against the
sources with its own readers.
"""
from __future__ import annotations

import argparse
import csv
import importlib.metadata
import io
import json
import resource
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
import pyproj
import shapely

from common import BBOX_FIELDS, ROW_GROUP_SIZE, hilbert_keys
from source import FILES, LAYERS, acquire, digest, verified_file

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CACHE_DEFAULT = REPO / ".local/us-census-places/source"
RELEASE_NAME = "cb2023-r1"
WORKFLOW = ["build.py", "common.py", "source.py", "validate.py", "test_faults.py", "pyproject.toml", "uv.lock",
            "dataset.yaml", "validation-plan.md", "README.md"]


def json_write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def peak_rss_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)


def gazetteer_funcstat(path: Path) -> dict[str, str]:
    """GEOID -> FUNCSTAT from a gazetteer file (tab separated, one member in the zip)."""
    with zipfile.ZipFile(path) as z:
        (member,) = [n for n in z.namelist() if n.endswith(".txt")]
        text = z.read(member).decode("utf-8")
    lines = text.splitlines()
    header = [h.strip() for h in lines[0].split("\t")]
    geoid, funcstat = header.index("GEOID"), header.index("FUNCSTAT")
    out: dict[str, str] = {}
    for line in lines[1:]:
        cells = line.split("\t")
        key, value = cells[geoid].strip(), cells[funcstat].strip()
        if out.setdefault(key, value) != value:
            raise ValueError(f"{path.name}: GEOID {key} has two FUNCSTAT values")
    return out


def estimates(path: Path, sumlev: str) -> dict[str, int]:
    """GEOID -> POPESTIMATE2023 for one summary level of sub-est2023.csv."""
    table = io.StringIO(path.read_bytes().decode("latin-1"))
    header = table.readline().rstrip("\r\n").split(",")
    at = {name: header.index(name) for name in ("SUMLEV", "STATE", "COUNTY", "PLACE", "COUSUB", "POPESTIMATE2023")}
    parts = {"050": ("STATE", "COUNTY"), "162": ("STATE", "PLACE"), "061": ("STATE", "COUNTY", "COUSUB")}[sumlev]
    out: dict[str, int] = {}
    for cells in csv.reader(table):
        if cells[at["SUMLEV"]] != sumlev:
            continue
        key, value = "".join(cells[at[p]] for p in parts), int(cells[at["POPESTIMATE2023"]])
        if out.setdefault(key, value) != value:
            raise ValueError(f"{path.name}: {sumlev} {key} has two estimates")
    return out


def read_layer(cache: Path, asset: str) -> tuple[pa.Table, str]:
    spec = LAYERS[asset]
    uri = "/vsizip/" + str((cache / spec["file"]).resolve())
    info = pyogrio.read_info(uri)
    if info["features"] != spec["rows"] or list(info["fields"]) != spec["fields"]:
        raise ValueError(f"{asset}: {info['features']} rows, fields {list(info['fields'])}; differs from the pinned layer")
    if not pyproj.CRS.from_user_input(info["crs"]).equals(pyproj.CRS.from_epsg(4269), ignore_axis_order=True):
        raise ValueError(f"{asset}: unexpected CRS {info['crs']}")
    meta, table = pyogrio.read_arrow(uri)
    return table, meta["geometry_name"]


def build_layer(cache: Path, asset: str, path: Path) -> dict[str, Any]:
    spec = LAYERS[asset]
    table, geometry_name = read_layer(cache, asset)
    table = table.combine_chunks()
    wkb = table[geometry_name].chunk(0).cast(pa.binary())
    geometry = shapely.from_wkb(wkb.to_numpy(zero_copy_only=False))
    if shapely.is_missing(geometry).any() or shapely.is_empty(geometry).any():
        raise ValueError(f"{asset}: a row has no geometry")
    bounds = shapely.bounds(geometry)
    rows = table.num_rows
    source_row = np.arange(1, rows + 1, dtype=np.int64)
    geoid = table["GEOID"].to_pylist()
    funcstat = gazetteer_funcstat(cache / spec["gazetteer"]) if spec["gazetteer"] else {}
    population = estimates(cache / "sub-est2023.csv", spec["sumlev"])
    columns = {name: table[name].chunk(0) for name in spec["fields"]}
    columns["geometry"] = wkb
    columns["source_row"] = pa.array(source_row)
    columns["gaz_funcstat"] = pa.array([funcstat.get(g) for g in geoid], type=pa.string())
    columns["popest_2023"] = pa.array([population.get(g) for g in geoid], type=pa.int64())
    columns["bbox"] = pa.StructArray.from_arrays([pa.array(bounds[:, i], type=pa.float64()) for i in range(4)],
                                                names=BBOX_FIELDS)
    order = np.lexsort((source_row, hilbert_keys(bounds)))
    extent = [float(bounds[:, 0].min()), float(bounds[:, 1].min()), float(bounds[:, 2].max()), float(bounds[:, 3].max())]
    types = sorted({shapely.get_type_id(g) for g in geometry})
    names = {3: "Polygon", 6: "MultiPolygon"}
    geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {"geometry": {
        "encoding": "WKB", "geometry_types": [names[int(t)] for t in types],
        "crs": pyproj.CRS.from_epsg(4269).to_json_dict(), "bbox": extent,
        "covering": {"bbox": {name: ["bbox", name] for name in BBOX_FIELDS}}}}}
    metadata = {b"geo": json.dumps(geo, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
                b"source:producer": b"US Census Bureau", b"source:file": spec["file"].encode(),
                b"source:sha256": FILES[spec["file"]]["sha256"].encode()}
    out = pa.table(columns).take(pa.array(order)).replace_schema_metadata(metadata)
    pq.write_table(out, path, row_group_size=ROW_GROUP_SIZE, compression="zstd", compression_level=9,
                   use_dictionary=True, write_statistics=True, version="2.6")
    written = pq.ParquetFile(path)
    return {"name": path.name, "path": f"data/{path.name}", "size_bytes": path.stat().st_size,
            "sha256": digest(path), "feature_count": rows, "bbox": extent, "crs": "EPSG:4269",
            "geometry_types": geo["columns"]["geometry"]["geometry_types"],
            "schema_fields": [f.name for f in written.schema_arrow],
            "row_groups": written.metadata.num_row_groups, "row_group_size": ROW_GROUP_SIZE,
            "gaz_funcstat_counts": dict(sorted(Counter(
                v if v is not None else "null" for v in out["gaz_funcstat"].to_pylist()).items())),
            "popest_2023_present": rows - out["popest_2023"].null_count}


def committed(allow_uncommitted: bool) -> str:
    status = subprocess.check_output(["git", "status", "--porcelain", "--", "datasets/us-census-places"],
                                     cwd=REPO, text=True).strip()
    if status and not allow_uncommitted:
        raise SystemExit("Commit the workflow before building a release (or pass --allow-uncommitted for a trial).")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    return head + ("+uncommitted" if status else "")


def build(cache: Path, output: Path, allow_uncommitted: bool) -> dict[str, Any]:
    pa.set_cpu_count(2)
    pa.set_io_thread_count(2)
    if output.exists():
        raise SystemExit("Use a new output directory; earlier builds are never overwritten.")
    commit = committed(allow_uncommitted)
    pins = {name: verified_file(cache / name) for name in FILES}
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < 40_000_000_000:
        raise RuntimeError("Less than 40 GB free on the shared machine; stop before writing output.")
    (output / "data").mkdir(parents=True)
    for name in ("dataset.yaml", "validation-plan.md", "README.md"):
        shutil.copyfile(HERE / name, output / name)
    json_write(output / "source-manifest.json", {"producer": "US Census Bureau", "license": "public domain",
                                                 "files": pins})
    assets = {asset: build_layer(cache, asset, output / "data" / f"{asset}.parquet") for asset in LAYERS}
    peak = peak_rss_bytes()
    if peak >= 1_000_000_000:
        raise RuntimeError(f"Peak process memory exceeded the 1 GB limit: {peak:,} bytes")
    report = {"release": RELEASE_NAME, "created_from_commit": commit, "peak_process_memory_bytes": peak,
              "workflow_files": {name: digest(HERE / name) for name in WORKFLOW},
              "tool_versions": {"python": sys.version.split()[0],
                                **{p: importlib.metadata.version(p) for p in ("pyarrow", "pyogrio", "shapely", "pyproj", "numpy")},
                                "gdal": ".".join(map(str, pyogrio.__gdal_version__))},
              "layers": assets}
    json_write(output / "build-manifest.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("acquire").add_argument("--cache", type=Path, default=CACHE_DEFAULT)
    sub.add_parser("inspect").add_argument("--source-cache", type=Path, default=CACHE_DEFAULT)
    p = sub.add_parser("build")
    p.add_argument("--source-cache", type=Path, default=CACHE_DEFAULT)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--allow-uncommitted", action="store_true")
    args = parser.parse_args()
    if args.command == "acquire":
        print(json.dumps(acquire(args.cache), indent=2))
    elif args.command == "inspect":
        for name in FILES:
            verified_file(args.source_cache / name)
        for asset in LAYERS:
            table, _ = read_layer(args.source_cache, asset)
            print(asset, table.num_rows, [f"{f.name}:{f.type}" for f in table.schema])
    else:
        report = build(args.source_cache, args.output, args.allow_uncommitted)
        print(json.dumps({a: {k: v[k] for k in ("size_bytes", "feature_count", "row_groups", "gaz_funcstat_counts",
                                                "popest_2023_present")} for a, v in report["layers"].items()}, indent=2))


if __name__ == "__main__":
    main()
