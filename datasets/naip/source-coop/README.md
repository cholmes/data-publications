# NAIP visualization COGs

**Locally generated metadata:** product creation, object uploads, and hosting checks have separate execution receipts.

- Dataset: `naip` (NAIP visualization COGs)
- Product ID: `naip`
- Local publication status: `published`
- Local readiness: `prepared`
- Owner: `nthh` (confirmed)
- Canonical publication review stage: `not recorded`
- Creation readiness: `true`
- Hosted: `true`

## Summary

RGB JPEG Cloud-Optimized GeoTIFFs of USDA NAIP quarter quads, converted from the naip-analytic MRF files with the settings, file names and key layout of the AWS naip-visualization bucket. Every 2024 and 2025 state-year, which that bucket does not hold, and the latest flight of the four states last flown in 2023, with reduced pictures of each state and of the country for drawing a map.

The proposed Source Cooperative maintainer is separate from the immutable release package metadata; this draft does not change existing producer or converter credits.

## Credits and license

- Producer attribution: USDA Farm Production and Conservation Business Center, Geospatial Enterprise Operations (NAIP). Source files from the NAIP on AWS open data buckets maintained by Esri.
- License note: NAIP imagery is produced by the USDA Farm Production and Conservation Business Center and is in the public domain. USDA asks for credit; these files are a format conversion, not a USDA product.
- Temporal scope: One file per quarter quad per state-year, from flights of 2021 to 2025. Each file name holds the date it was flown; a 2023 name then holds a second date, the day the file was made. The quad index gives the flight date of every file.

## Sources and DOI references

- [Dataset release](https://registry.opendata.aws/naip/)
- [Processor: nthh](https://source.coop/nthh/naip)
- [Producer: USDA Farm Production and Conservation Business Center](https://www.fpacbc.usda.gov/)

## Related datasets

No related dataset links are recorded.

## Versioned metadata supplements

No separate metadata supplements are recorded.

## Snapshot assets

- `overviews`: Overview file index (STAC GeoParquet) (application/vnd.apache.parquet)
- `overviews_fields`: overviews field dictionary (application/json)
- `quads`: Quarter-quad index (STAC GeoParquet) (application/vnd.apache.parquet)
- `quads_fields`: quads field dictionary (application/json)
- `support-1`: Build commit, environment, input checksums and output facts (release r7, whose bytes this package holds) (application/json)
- `support-2`: Validator report of release r7, whose bytes this package holds: accounting against receipts, hosted listing, footprints, dates, gti locations, fault tests (application/json)
- `support-3`: Locked build environment (conda explicit list and one pip wheel) (text/plain)
- `support-4`: Checks written before the first build, with addenda (text/markdown)
- `support-5`: Checks 1 and 13: the index files are r7's bytes and the hosted stac/naip.gti.fgb pair matches them (application/json)
- `support-6`: Check 12: stac/naip.gti.fgb opened with GDAL 3.12.4 (QGIS 4.2.1) through /vsicurl/: Alta, Utah, and what QGIS reads when the layer is added (application/json)
- `support-7`: Differences from the hosted r7 files this release is meant to have (none in the index files), written before the package (application/json)
- `thumbnail`: Sampled display-only overview; not an analytic asset (image/png)

## Versioned display package

No versioned display package is recorded.

## Limitations

- Display copy only. The files hold red, green and blue as lossy JPEG at quality 65, with overviews at quality 75 and colour at half resolution. The near-infrared band and the lossless pixels stay in s3://naip-analytic.
- Four Pennsylvania 2024 files carry a 2010 flight date in their names, as they do in the source.
- Pennsylvania 2024 (1,118 quads) and West Virginia 2024 (101 quads) cover only part of each state. Their files are hosted, under pa/2024/ and wv/2024/ and as overviews/pa-2024-utm18.tif and overviews/wv-2024-utm17.tif, but the two indexes do not list them and the national file is made without them. Both states are listed whole from 2022, so a map that draws the newest file over a place shows one flight per state. The rule is a count. A year holding under 90% of the quads of an older year of the same state is not listed.
- The 2024 folders of the source lack every quad numbered xx12023 (California and Oregon at 120 W), and Florida 2025 lacks a strip of south Florida. Those places are filled with only the missing quads from California 2022, Oregon 2022 and Florida 2023. They differ from their neighbours in year, season and tone.
- The overview files are for drawing a map, not for measurement. A state file holds one flight year of one state in one UTM zone at 9.6 m; the national file holds the latest flight of each state, so neighbouring states can differ in year and in tone.
- Adjacent quarter quads overlap, as they do in the source.

## Source Cooperative route

Hosted product: `s3://nthh/naip`. The published release is bound to a checksum-verified hosting report.
