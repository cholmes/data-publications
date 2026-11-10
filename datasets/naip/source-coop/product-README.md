# NAIP display copies, 2024 onward

RGB JPEG Cloud-Optimized GeoTIFFs of USDA NAIP quarter quads for the state-years that the AWS naip-visualization bucket does not hold, converted from the naip-analytic MRF files with the same settings, file names and key layout.

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

- Display copy only. The files hold red, green and blue as lossy JPEG at quality 85. The near-infrared band and the lossless pixels stay in s3://naip-analytic.
- Only Utah 2024 is converted so far, and it sits in a private bucket. It is not on Source Cooperative.
- Files converted in the Utah pilot have no recorded SHA-256; the converter records one from the next run on.
- Adjacent quarter quads overlap, as they do in the source.

Public hosting and scientific validation status must be checked independently.
