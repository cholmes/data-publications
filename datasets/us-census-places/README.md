# US Census counties, places and county subdivisions, 2023

The Census Bureau's 2023 cartographic boundary files (1:500,000) for counties, places and county
subdivisions, converted from zipped shapefiles to one GeoParquet file per layer.

**Status (2026-11-17):** published, unlisted, at [source.coop/nthh/us-census-places](https://source.coop/nthh/us-census-places).
Release `cb2023-r1` was built from committed code, passed the checks of the validation plan and the
shared packager, and rebuilt byte-identically in a clean checkout. The display package
`cb2023-display-r3` (three outline tile files and a names index) passed the checks of
[display-plan.md](display-plan.md); its first build failed three and is kept in
`display/cb2023-display-r1-failed/`. The 68 hosted files passed the hosted checks
([report](../../research/us-census-places-20261116/hosted-validation.json)).

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

<!-- related-datasets:start -->

## Related datasets

Generated from `related_datasets` in [dataset.yaml](dataset.yaml). These references describe alternatives and complementary uses; they do not add datasets to the processing queue. The comparisons are based on the cited documentation, not an equivalence or accuracy benchmark.

### [Census TIGER/Line 2024 counties and places (cboettig/census)](<https://source.coop/cboettig/census>)

- **Relationship:** Alternative. National counties and places as GeoParquet and PMTiles, from the full-resolution TIGER/Line files.
- **Coverage:** 50 states, DC, Puerto Rico and the island areas
- **Formats:** GeoParquet, PMTiles
- **Access:** Tile headers, layer fields and six map views were read anonymously on 2026-11-16. The GeoParquet files were listed, not opened.
- **Comparison:** Counties and places only, no county subdivisions. TIGER/Line 2024 geometry, which runs out into coastal water, where the cartographic boundary files used here are clipped to the shore and generalised. Its tiles carry NAME, GEOID and FUNCSTAT but no bounds, state abbreviation, population or label points. On 2026-11-16 its tiles read 89 to 359 KB for three whole-state views and 36 to 91 KB for three whole-county views, within the limits of display-plan.md.
- **Reviewed:** 2026-11-16. **Sources:** [Product page](<https://source.coop/cboettig/census>).

### [HIFLD archive with Census TIGER 2024 counties, places and county subdivisions (seerai/hifld)](<https://source.coop/seerai/hifld>)

- **Relationship:** Alternative. The same three layers, with tracts and block groups, as GeoParquet.
- **Formats:** GeoParquet
- **Access:** Listed anonymously and READMEs read on 2026-11-16; data files not opened.
- **Comparison:** Holds all three layers, with incorporated places and census designated places as two datasets, from the TIGER 2024 geodatabase. GeoParquet only, as directories of part files; no tiles. Its READMEs were read; no data file was opened, so schema and row counts are unchecked.
- **Reviewed:** 2026-11-16. **Sources:** [Product page](<https://source.coop/seerai/hifld>).

<!-- related-datasets:end -->
