# US Census counties, places and county subdivisions, 2023 cartographic boundaries

Shore-clipped outlines of US counties, cities and other places, and county subdivisions, from the Census Bureau's 2023 cartographic boundary files, as GeoParquet with government status and 2023 population estimates added, and a display package of outline tiles and a names index for choosing places on a map.

**Selected release:** `cb2023-r1`. This link structure describes the prepared package; public hosting and validation have not been checked by this generator.

## Scope and formats

The 2023 Census cartographic boundary files for counties, places and county subdivisions as three GeoParquet files. Every source row and field and the geometry GDAL decodes are kept, in NAD83 (EPSG:4269). Added columns: source_row, gaz_funcstat (functional status from the 2023 gazetteer), popest_2023 (1 July 2023 estimate) and bbox. Rows follow a Hilbert curve. These are boundaries generalised for mapping at 1:500,000, as of 1 January 2023, not legal boundaries.

Formats: `application/json`, `application/vnd.apache.parquet`, `application/vnd.pmtiles`, `image/png`, `text/markdown`.

## Producer, source, and license

- Producer attribution: Source: US Census Bureau, 2023 cartographic boundary files, gazetteer files and vintage 2023 population estimates.
- License: US Government work in the public domain. The Census Bureau asks to be cited as the source. These files are a format conversion, not a Census Bureau product.
- Temporal scope: Boundaries as of 1 January 2023. Population estimates are for 1 July 2023.

- [Host: nthh](https://github.com/nthh/data-publications)
- [Producer: US Census Bureau](https://www.census.gov/)
- [License terms](https://www.census.gov/about/policies/citation.html)
- [Original download](https://www2.census.gov/geo/tiger/GENZ2023/shp/)

## Release files

- [counties.parquet](releases/cb2023-r1/assets/counties.parquet) (asset)
- [county-subdivisions.parquet](releases/cb2023-r1/assets/county-subdivisions.parquet) (asset)
- [places.parquet](releases/cb2023-r1/assets/places.parquet) (asset)
- [thumbnail.png](releases/cb2023-r1/display/thumbnail.png) (display_derivatives)
- [data-license.json](releases/cb2023-r1/licenses/data-license.json) (data_license)
- [source-license.json](releases/cb2023-r1/licenses/source-license.json) (source_license)
- [counties-field-dictionary.json](releases/cb2023-r1/metadata/counties-field-dictionary.json) (field_dictionary)
- [county-subdivisions-field-dictionary.json](releases/cb2023-r1/metadata/county-subdivisions-field-dictionary.json) (field_dictionary)
- [places-field-dictionary.json](releases/cb2023-r1/metadata/places-field-dictionary.json) (field_dictionary)
- [build-manifest.json](releases/cb2023-r1/provenance/build-manifest.json) (supporting_files)
- [source-manifest.json](releases/cb2023-r1/provenance/source-manifest.json) (supporting_files)
- [validation-plan.md](releases/cb2023-r1/provenance/validation-plan.md) (supporting_files)
- [attribution.json](releases/cb2023-r1/source/attribution.json) (source_attribution)

## Display package

Display release: `cb2023-display-r2`. The manifest is pinned at SHA-256 `2c3828c9aa555375993ccbc1a37fef0d19e40c9608a6e37d020a6205a55497c6`.
Display assets are separate immutable derivatives bound to this analytical release.
- [Display manifest](display/cb2023-display-r2/manifest.json)
- [Counties PMTiles](display/cb2023-display-r2/assets/census_counties.pmtiles) (23766772 bytes; SHA-256 `23e2e5abf8a7cc3c94e81c5d345adbf5d2a893c21e7c0467a885a1070b925ac2`)
  - [Map style](display/cb2023-display-r2/styles/census_counties.json)
- [Cities, towns and census designated places PMTiles](display/cb2023-display-r2/assets/census_places.pmtiles) (37275676 bytes; SHA-256 `79520f8f8bb67d09b6e443539865494bf80d02049dcd9a2a8869544db987cadf`)
  - [Map style](display/cb2023-display-r2/styles/census_places.json)
- [Governing townships and towns PMTiles](display/cb2023-display-r2/assets/census_towns.pmtiles) (20349807 bytes; SHA-256 `a56dc97780b3e0d71393f211a1025e8e2fffbbdc95432164bf344f6c3e3a2be5`)
  - [Map style](display/cb2023-display-r2/styles/census_towns.json)

## Limitations

- Generalised boundaries for mapping at 1:500,000, not legal boundaries. The TIGER/Line files are the fuller source.
- Census designated places, Puerto Rico and the island areas carry no population estimate.
- Coordinates are NAD83 (EPSG:4269) and are not transformed.
- The display tiles draw only county subdivisions that are active governments; all of them are in the GeoParquet.

## Related datasets

- [Census TIGER/Line 2024 counties and places (cboettig/census)](https://source.coop/cboettig/census)
- [HIFLD archive with Census TIGER 2024 counties, places and county subdivisions (seerai/hifld)](https://source.coop/seerai/hifld)

Public hosting and scientific validation status must be checked independently.
