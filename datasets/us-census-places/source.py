"""Pinned US Census Bureau inputs for the 2023 counties, places and county subdivisions release."""
from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = "us-census-places-build/1"
BOUNDARY_BASE = "https://www2.census.gov/geo/tiger/GENZ2023/shp/"
GAZETTEER_BASE = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/"
ESTIMATES_BASE = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/cities/totals/"

FILES: dict[str, dict[str, Any]] = {
    "cb_2023_us_county_500k.zip": {
        "url": BOUNDARY_BASE + "cb_2023_us_county_500k.zip", "size_bytes": 11_630_077,
        "sha256": "99d6597b1fc7767deef62e01d28d8b5dcbd578e151855f7dc0d173cbf5bf0868"},
    "cb_2023_us_place_500k.zip": {
        "url": BOUNDARY_BASE + "cb_2023_us_place_500k.zip", "size_bytes": 22_856_787,
        "sha256": "27562072c8e7890cafa6b3ac7a44e5e394b34da210501b48500052bc56b8a18d"},
    "cb_2023_us_cousub_500k.zip": {
        "url": BOUNDARY_BASE + "cb_2023_us_cousub_500k.zip", "size_bytes": 40_339_825,
        "sha256": "c5d57d7f71af1f40f738e8dccc23bf62efd0331491a5ff0e24cfdcf026e6bc03"},
    "2023_Gaz_place_national.zip": {
        "url": GAZETTEER_BASE + "2023_Gaz_place_national.zip", "size_bytes": 1_220_953,
        "sha256": "3c8b23c0dcdb15c0ebd16fee7373e032466e6b585650aa219bc1bee5ac8bd58f"},
    "2023_Gaz_cousubs_national.zip": {
        "url": GAZETTEER_BASE + "2023_Gaz_cousubs_national.zip", "size_bytes": 1_491_622,
        "sha256": "22f4892eadaa4236add3b3dd015dff401e74e1aef32a7717a15e44c23dbdc1f3"},
    "sub-est2023.csv": {
        "url": ESTIMATES_BASE + "sub-est2023.csv", "size_bytes": 6_714_548,
        "sha256": "493161c5f342e587b10fcbfbfca6768f8b828c80ff9ac2283ef16225ccd653e9"},
}

COMMON = ["GEOIDFQ", "GEOID", "NAME", "NAMELSAD", "STUSPS"]
TAIL = ["STATE_NAME", "LSAD", "ALAND", "AWATER"]
# asset id -> boundary file, expected rows, source fields in order, gazetteer file, estimates summary level
LAYERS: dict[str, dict[str, Any]] = {
    "counties": {
        "file": "cb_2023_us_county_500k.zip", "rows": 3235,
        "fields": ["STATEFP", "COUNTYFP", "COUNTYNS", *COMMON, *TAIL],
        "gazetteer": None, "sumlev": "050"},
    "places": {
        "file": "cb_2023_us_place_500k.zip", "rows": 32608,
        "fields": ["STATEFP", "PLACEFP", "PLACENS", *COMMON, *TAIL],
        "gazetteer": "2023_Gaz_place_national.zip", "sumlev": "162"},
    "county-subdivisions": {
        "file": "cb_2023_us_cousub_500k.zip", "rows": 36367,
        "fields": ["STATEFP", "COUNTYFP", "COUSUBFP", "COUSUBNS", *COMMON, "NAMELSADCO", *TAIL],
        "gazetteer": "2023_Gaz_cousubs_national.zip", "sumlev": "061"},
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def verified_file(path: Path) -> dict[str, Any]:
    """The pin of a cached input, after checking its size and SHA-256."""
    pin = FILES[path.name]
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing; run `build.py acquire` first")
    size, sha = path.stat().st_size, digest(path)
    if size != pin["size_bytes"] or sha != pin["sha256"]:
        raise ValueError(f"{path.name}: {size} bytes, sha256 {sha}; differs from the pinned input")
    return {"name": path.name, **pin}


def acquire(cache: Path) -> dict[str, Any]:
    """Download any input not yet in the cache, then verify all of them."""
    cache.mkdir(parents=True, exist_ok=True)
    for name, pin in FILES.items():
        path = cache / name
        if not path.is_file():
            partial = path.with_name(name + ".part")
            request = urllib.request.Request(pin["url"], headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request) as response, partial.open("wb") as out:
                shutil.copyfileobj(response, out, 4 * 1024 * 1024)
            os.replace(partial, path)
    return {name: verified_file(cache / name) for name in FILES}
