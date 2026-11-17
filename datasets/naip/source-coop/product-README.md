# NAIP display copies

RGB JPEG Cloud-Optimized GeoTIFFs of USDA NAIP quarter quads, converted from the naip-analytic MRF files with the settings, file names and key layout of the AWS naip-visualization bucket. Every 2024 and 2025 state-year, which that bucket does not hold, and the latest flight of the four states last flown in 2023, with reduced pictures of each state and of the country for drawing a map.

**Selected release:** `index-20261116-r5`. This link structure describes the prepared package; public hosting and validation have not been checked by this generator.

## Scope and formats

The two STAC GeoParquet index files of the NAIP display copies: one item per hosted RGB JPEG Cloud-Optimized GeoTIFF quarter quad, and one per overview file. Each item gives the file's address, size, SHA-256, footprint, CRS and flight date. The imagery is not in this package; the indexes point to it at data.source.coop/nthh/naip/.

Formats: `application/json`, `application/vnd.apache.parquet`, `image/png`, `text/markdown`, `text/plain`.

## Producer, source, and license

- Producer attribution: USDA Farm Production and Conservation Business Center, Geospatial Enterprise Operations (NAIP). Source files from the NAIP on AWS open data buckets maintained by Esri.
- License: NAIP imagery is produced by the USDA Farm Production and Conservation Business Center and is in the public domain. USDA asks for credit; these files are a format conversion, not a USDA product.
- Temporal scope: One file per quarter quad per state-year, from flights of 2021 to 2025. Each file name holds the date it was flown; a 2023 name then holds a second date, the day the file was made. The quad index gives the flight date of every file.

- [Host: nthh](https://github.com/nthh/data-publications)
- [Dataset release](https://registry.opendata.aws/naip/)
- [Producer: USDA Farm Production and Conservation Business Center](https://www.fpacbc.usda.gov/)

## Release files

- [overviews.parquet](releases/index-20261116-r5/assets/overviews.parquet) (asset)
- [quads.parquet](releases/index-20261116-r5/assets/quads.parquet) (asset)
- [thumbnail.png](releases/index-20261116-r5/display/thumbnail.png) (display_derivatives)
- [data-license.json](releases/index-20261116-r5/licenses/data-license.json) (data_license)
- [source-license.json](releases/index-20261116-r5/licenses/source-license.json) (source_license)
- [overviews-field-dictionary.json](releases/index-20261116-r5/metadata/overviews-field-dictionary.json) (field_dictionary)
- [quads-field-dictionary.json](releases/index-20261116-r5/metadata/quads-field-dictionary.json) (field_dictionary)
- [build-manifest.json](releases/index-20261116-r5/provenance/build-manifest.json) (supporting_files)
- [check.json](releases/index-20261116-r5/provenance/check.json) (supporting_files)
- [index-env.lock.txt](releases/index-20261116-r5/provenance/index-env.lock.txt) (supporting_files)
- [index-package-plan.md](releases/index-20261116-r5/provenance/index-package-plan.md) (supporting_files)
- [attribution.json](releases/index-20261116-r5/source/attribution.json) (source_attribution)

## Display package

No versioned display package is recorded.

## Limitations

- Display copy only. The files hold red, green and blue as lossy JPEG at quality 65, with overviews at quality 75 and colour at half resolution. The near-infrared band and the lossless pixels stay in s3://naip-analytic.
- Four Pennsylvania 2024 files carry a 2010 flight date in their names, as they do in the source.
- Pennsylvania 2024 (1,118 quads) and West Virginia 2024 (101 quads) cover only part of each state. Their files are hosted, under pa/2024/ and wv/2024/ and as overviews/pa-2024-utm18.tif and overviews/wv-2024-utm17.tif, but the two indexes do not list them and the national file is made without them. Both states are listed whole from 2022, so a map that draws the newest file over a place shows one flight per state. The rule is a count. A year holding under 90% of the quads of an older year of the same state is not listed.
- The 2024 folders of the source lack every quad numbered xx12023 (California and Oregon at 120 W), and Florida 2025 lacks a strip of south Florida. Those places are filled with only the missing quads from California 2022, Oregon 2022 and Florida 2023. They differ from their neighbours in year, season and tone.
- The overview files are for drawing a map, not for measurement. A state file holds one flight year of one state in one UTM zone at 9.6 m; the national file holds the latest flight of each state, so neighbouring states can differ in year and in tone.
- Adjacent quarter quads overlap, as they do in the source.

Public hosting and scientific validation status must be checked independently.
