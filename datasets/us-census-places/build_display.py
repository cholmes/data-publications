"""Build the display package of a release: outline tiles and a names index. display-plan.md has the rules.

    build_display.py --package PACKAGED_RELEASE --output NEW_DIR [--allow-uncommitted]

Reads only the three GeoParquet files of the packaged release (checked against its manifest).
Writes assets/<layer>.pmtiles (an outline layer and its label layer), assets/place-names.json, one MapLibre style per layer and a
manifest with status "provisional". finalize_display.py marks it prepared after the checks pass.
Needs tippecanoe v2.79.0 and tile-join on PATH.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import shapely

from source import digest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATASET, ANALYTIC_RELEASE, DISPLAY_RELEASE = "us-census-places", "cb2023-r1", "cb2023-display-r3"
TIPPECANOE_LOCK = REPO / "datasets/grwl/tippecanoe.lock.json"
MAX_ZOOM = 11
KINDS = ["county", "incorporated", "unincorporated", "township"]
# layer, release asset, first zoom, title, line colour and width
LAYERS = [("census_counties", "counties", 3, "Counties", 0.6),
          ("census_places", "places", 7, "Cities, towns and census designated places", 0.9),
          ("census_towns", "county-subdivisions", 7, "Governing townships and towns", 0.45)]
OUTLINE_ARGS = ["--no-feature-limit", "--no-tile-size-limit", "--no-tiny-polygon-reduction",
                "--detect-shared-borders", "--simplification=15", "--simplify-only-low-zooms"]
LABEL_ARGS = ["--drop-rate=1", "--no-feature-limit", "--no-tile-size-limit"]
ATTRIBUTION = "Source: US Census Bureau, 2023 cartographic boundary files, gazetteer files and population estimates"
SOURCE = ("US Census Bureau: 2023 cartographic boundary files (1:500,000) for counties, places and county "
          "subdivisions; population is the 1 July 2023 estimate, absent for census designated places.")
LINE = "#f3d27a"


def json_write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def kind_of(layer: str, funcstat: str | None) -> str:
    if layer == "census_counties":
        return "county"
    if layer == "census_towns":
        return "township"
    return "incorporated" if funcstat == "A" else "unincorporated"


def rows_of(layer: str, path: Path) -> list[dict[str, Any]]:
    """The drawn rows of one layer, in the file's order, with the properties the tiles carry."""
    table = pq.read_table(path, columns=["GEOID", "NAME", "STUSPS", "ALAND", "gaz_funcstat", "popest_2023", "bbox",
                                         "geometry"]).to_pylist()
    out = []
    for row in table:
        if layer == "census_towns" and row["gaz_funcstat"] != "A":
            continue
        box = row["bbox"]
        out.append({"id": row["GEOID"], "name": row["NAME"], "state": row["STUSPS"],
                    "kind": kind_of(layer, row["gaz_funcstat"]), "population": row["popest_2023"],
                    "area": round(row["ALAND"] / 1e6, 2), "bounds": [box["xmin"], box["ymin"], box["xmax"], box["ymax"]],
                    "wkb": row["geometry"]})
    return out


def features(rows: list[dict[str, Any]], outline_path: Path, label_path: Path) -> None:
    with outline_path.open("w", encoding="utf-8") as outlines, label_path.open("w", encoding="utf-8") as labels:
        for row in rows:
            geometry = shapely.from_wkb(row["wkb"])
            shared = {"id": row["id"], "name": row["name"], "kind": row["kind"]}
            if row["population"] is not None:
                shared["population"] = row["population"]
            west, south, east, north = row["bounds"]
            outline = {**shared, "state": row["state"], "xmin": west, "ymin": south, "xmax": east, "ymax": north}
            point = shapely.point_on_surface(shapely.make_valid(geometry))
            for stream, properties, shape in ((outlines, outline, geometry), (labels, {**shared, "area": row["area"]}, point)):
                stream.write('{"type":"Feature","properties":' + json.dumps(properties, ensure_ascii=False)
                             + ',"geometry":' + shapely.to_geojson(shape) + "}\n")


def tippecanoe(lock: dict[str, Any]) -> str:
    path = shutil.which("tippecanoe")
    if not path or digest(Path(path).resolve()) != lock["binary_sha256"]:
        raise SystemExit("tippecanoe is missing or is not the binary pinned in datasets/grwl/tippecanoe.lock.json")
    return path


def style(layer: str, width: float) -> dict[str, Any]:  # one archive per layer
    return {"version": 8, "name": layer, "glyphs": "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
            "sources": {"data": {"type": "vector", "url": f"../assets/{layer}.pmtiles", "promoteId": "id"}},
            "layers": [
                {"id": f"{layer}-fill", "type": "fill", "source": "data", "source-layer": layer,
                 "paint": {"fill-color": LINE, "fill-opacity": ["case", ["boolean", ["feature-state", "lit"], False], 0.16, 0.03]}},
                {"id": f"{layer}-line", "type": "line", "source": "data", "source-layer": layer,
                 "paint": {"line-color": LINE, "line-opacity": 0.75, "line-width": width}},
                {"id": f"{layer}-label", "type": "symbol", "source": "data", "source-layer": f"{layer}_label",
                 "layout": {"text-field": ["get", "name"], "text-font": ["Noto Sans Regular"], "text-size": 11,
                            "text-padding": 6, "text-max-width": 7,
                            "symbol-sort-key": ["-", 0, ["coalesce", ["get", "population"],
                                                         ["*", 20, ["coalesce", ["get", "area"], 0]]]]},
                 "paint": {"text-color": LINE, "text-halo-color": "rgba(10,14,12,0.85)", "text-halo-width": 1.4}}]}


def build(package: Path, output: Path, allow_uncommitted: bool) -> dict[str, Any]:
    if output.exists():
        raise SystemExit("Use a new output directory; earlier display builds are never overwritten.")
    status = subprocess.check_output(["git", "status", "--porcelain", "--", f"datasets/{DATASET}"], cwd=REPO, text=True).strip()
    if status and not allow_uncommitted:
        raise SystemExit("Commit the workflow before building (or pass --allow-uncommitted for a trial).")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip() + ("+uncommitted" if status else "")
    manifest = json.loads((package / "manifest.json").read_text())
    if manifest.get("dataset_id") != DATASET or manifest.get("release_id") != ANALYTIC_RELEASE:
        raise SystemExit("The package is not the analytic release this display build is made from.")
    lock = json.loads(TIPPECANOE_LOCK.read_text())
    binary = tippecanoe(lock)
    if shutil.disk_usage(output.parent).free < 40_000_000_000:
        raise RuntimeError("Less than 40 GB free on the shared machine; stop before writing output.")
    for folder in ("assets", "styles", "reports"):
        (output / folder).mkdir(parents=True)
    environment = {**os.environ, "TIPPECANOE_MAX_THREADS": "2"}
    names, assets, sources = [], [], {}
    join = shutil.which("tile-join")
    with tempfile.TemporaryDirectory(dir=output) as scratch:
        for layer, asset, first, title, width in LAYERS:
            source = package / "assets" / f"{asset}.parquet"
            sha = digest(source)
            bound = [a for a in manifest["assets"] if a["asset_id"] == asset]
            sources[asset] = {"path": f"assets/{asset}.parquet", "sha256": sha, "size_bytes": source.stat().st_size,
                              "bound_in_release_manifest": bool(bound) and bound[0].get("sha256") == sha}
            rows = rows_of(layer, source)
            outline_json, label_json = Path(scratch) / f"{layer}.geojsonl", Path(scratch) / f"{layer}_label.geojsonl"
            features(rows, outline_json, label_json)
            # Relative names inside the scratch folder, so no temporary path is recorded in the archive.
            for name, flags in ((layer, OUTLINE_ARGS), (f"{layer}_label", LABEL_ARGS)):
                subprocess.run([binary, "-q", "-f", "-o", f"{name}.pmtiles", "-l", name, "-n", name, "-N", ATTRIBUTION,
                                f"-Z{first}", f"-z{MAX_ZOOM}", *flags, f"{name}.geojsonl"], check=True, env=environment, cwd=scratch)
            archive = output / "assets" / f"{layer}.pmtiles"
            subprocess.run([join, "-q", "-f", "--no-tile-size-limit", "-n", layer, "-N", ATTRIBUTION, "-o", "joined.pmtiles",
                            f"{layer}.pmtiles", f"{layer}_label.pmtiles"], check=True, env=environment, cwd=scratch,
                           stderr=subprocess.DEVNULL)
            shutil.move(str(Path(scratch) / "joined.pmtiles"), archive)
            names.extend(rows)
            json_write(output / "styles" / f"{layer}.json", style(layer, width))
            assets.append({"id": layer.replace("_", "-"), "title": title, "path": f"assets/{layer}.pmtiles",
                           "sha256": digest(archive), "size_bytes": archive.stat().st_size,
                           "style_path": f"styles/{layer}.json", "source_layer": layer,
                           "labels": {"source_layer": f"{layer}_label", "geometry_type": "point"},
                           "geometry_type": "polygon", "id_field": "id", "id_encoding": "property",
                           "attribute_fields": ["name", "state", "kind", "population", "xmin", "ymin", "xmax", "ymax"],
                           "min_zoom": first, "max_zoom": MAX_ZOOM, "source_rows": len(rows), "source_asset": sources[asset]})
    if not all(s["bound_in_release_manifest"] for s in sources.values()):
        raise SystemExit(f"A GeoParquet file does not match the release manifest: {sources}")
    names.sort(key=lambda r: (r["population"] is None, -(r["population"] or 0), -r["area"]))
    index = {"version": 1, "source": SOURCE, "kinds": KINDS,
             "columns": ["name", "state", "kind", "population", "xmin", "ymin", "xmax", "ymax"],
             "rows": [[r["name"], r["state"], KINDS.index(r["kind"]), r["population"], *(round(v, 3) for v in r["bounds"])]
                      for r in names]}
    (output / "assets" / "place-names.json").write_text(json.dumps(index, separators=(",", ":"), ensure_ascii=False),
                                                        encoding="utf-8")
    json_write(output / "reports" / "build-report.json", {
        "created_from_commit": commit, "tippecanoe": {"version": lock["version"], "binary_sha256": lock["binary_sha256"]},
        "outline_arguments": OUTLINE_ARGS, "label_arguments": LABEL_ARGS, "max_threads": 2, "sources": sources,
        "workflow_files": {name: digest(HERE / name) for name in ("build_display.py", "validate_display.py",
                                                                  "finalize_display.py", "display-plan.md", "source.py")},
        "rows_drawn": {item["source_layer"]: item["source_rows"] for item in assets}, "names_rows": len(index["rows"])})
    (output / "README.md").write_text(
        f"# {DATASET} display package {DISPLAY_RELEASE}\n\nOutline tiles and a names index made from the GeoParquet of "
        f"`{ANALYTIC_RELEASE}`, for drawing and choosing places on a map. The GeoParquet is the data; these are not.\n"
        f"The rules and checks are in `display-plan.md` of the dataset workspace.\n\n{ATTRIBUTION}.\n", encoding="utf-8")
    files = {str(p.relative_to(output)): {"sha256": digest(p), "size_bytes": p.stat().st_size}
             for p in sorted(output.rglob("*")) if p.is_file()}
    result = {"schema_version": 1, "dataset_id": DATASET, "display_release": DISPLAY_RELEASE,
              "analytic_release": ANALYTIC_RELEASE, "status": "provisional", "attribution": ATTRIBUTION,
              "source_license": {"identifier": "other", "url": "https://www.census.gov/about/policies/citation.html"},
              "names_index": {"path": "assets/place-names.json", "rows": len(index["rows"])},
              "assets": assets, "files": files}
    json_write(output / "manifest.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-uncommitted", action="store_true")
    args = parser.parse_args()
    result = build(args.package.resolve(), args.output.resolve(), args.allow_uncommitted)
    print(json.dumps({"archive_bytes": {a["source_layer"]: a["size_bytes"] for a in result["assets"]}, "names_rows": result["names_index"]["rows"],
                      "rows_drawn": {a["source_layer"]: a["source_rows"] for a in result["assets"]}}, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
