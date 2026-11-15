# NAIP display copies

RGB JPEG Cloud-Optimized GeoTIFFs of USDA NAIP quarter quads, converted from the naip-analytic MRF files with the settings, file names and key layout of the AWS naip-visualization bucket. Every 2024 and 2025 state-year, which that bucket does not hold, and the latest flight of the four states last flown in 2023, with reduced pictures of each state and of the country for drawing a map.

**Planned product:** no converted release is currently available.

This page describes the intended dataset and its planned metadata. No release files are linked yet.

## Scope and formats

Formats will be listed when a converted release is prepared.

## Producer, source, and license

- Producer attribution: USDA Farm Production and Conservation Business Center, Geospatial Enterprise Operations (NAIP). Source files from the NAIP on AWS open data buckets maintained by Esri.
- License: NAIP imagery is produced by the USDA Farm Production and Conservation Business Center and is in the public domain. USDA asks for credit; these files are a format conversion, not a USDA product.
- Temporal scope: One file per quarter quad per state-year. Each file name ends in the date it was flown. Utah 2024 was flown from 2024-06-23 to 2024-08-31.

## Release files

No release files are available.

## Display package

No versioned display package is recorded.

## Limitations

- Display copy only. The files hold red, green and blue as lossy JPEG at quality 65, with overviews at quality 75 and colour at half resolution. The near-infrared band and the lossless pixels stay in s3://naip-analytic.
- Four Pennsylvania 2024 files carry a 2010 flight date in their names, as they do in the source.
- Pennsylvania 2024 and West Virginia 2024 are partial flights, the 2024 folders of the source lack every quad numbered xx12023 (California and Oregon at 120 W), and Florida 2025 lacks a strip of south Florida. Those places are filled from the flight before, with Pennsylvania 2022 and West Virginia 2022 whole and only the missing quads from California 2022, Oregon 2022 and Florida 2023. They differ from their neighbours in year, season and tone.
- The overview files are for drawing a map, not for measurement. A state file holds one flight year of one state in one UTM zone at 9.6 m; the national file holds the latest flight of each state, so neighbouring states can differ in year and in tone.
- Adjacent quarter quads overlap, as they do in the source.

Public hosting and scientific validation status must be checked independently.
