# US Census counties, places and county subdivisions, 2023

The Census Bureau's 2023 cartographic boundary files (1:500,000) for counties, places and county
subdivisions, converted from zipped shapefiles to one GeoParquet file per layer.

**Status (2026-11-16):** candidate. The build and its checks are written; no release has been
built from committed code, nothing is hosted and nothing is in the public catalogue.

| File | Rows | What a row is |
| --- | ---: | --- |
| `counties.parquet` | 3,235 | A county or its equivalent |
| `places.parquet` | 32,608 | An incorporated place (city, town, village) or a census designated place |
| `county-subdivisions.parquet` | 36,367 | A township, town or other division of a county |

Every source row and field is kept, with the geometry GDAL decodes, in NAD83 (EPSG:4269). Four
columns are added after the source fields:

- `source_row`: the row's 1-based position in the shapefile.
- `gaz_funcstat`: the functional status code of the same `GEOID` in the 2023 gazetteer file. `A`
  is an active government, which is how a city is told from a census designated place and a
  governing township from a statistical one. Null for counties.
- `popest_2023`: the Census estimate of population on 1 July 2023. Null for census designated
  places and for Puerto Rico and the island areas, which the estimates file does not cover.
- `bbox`: the bounds of the row's geometry.

Rows are written along a Hilbert curve, so the rows of one area sit together and a reader can
skip the rest by the `bbox` statistics.

These are generalised boundaries for mapping, not legal boundaries. Boundaries are as of
1 January 2023.

## Build and check

```sh
cd datasets/us-census-places
uv sync --locked
uv run --locked python build.py acquire
uv run --locked python build.py build --output ../../.local/us-census-places/cb2023-r1
uv run --locked python validate.py --release ../../.local/us-census-places/cb2023-r1 --report ../../.local/us-census-places/cb2023-r1-source-fidelity.json
uv run --locked python -m unittest test_faults -v
```

The inputs are pinned by size and SHA-256 in `source.py`. What the checks must show was written
before the first build, in [validation-plan.md](validation-plan.md).

## Source and licence

US Census Bureau: cartographic boundary files, gazetteer files and population estimates. These
are US Government works in the public domain; cite the Census Bureau as the source. The scripts
here are Apache-2.0.
