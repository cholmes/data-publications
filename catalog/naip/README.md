# NAIP visualization COGs

RGB JPEG Cloud-Optimized GeoTIFFs of USDA NAIP quarter quads, converted from the naip-analytic MRF files with the settings, file names and key layout of the AWS naip-visualization bucket. Every 2024 and 2025 state-year, which that bucket does not hold, and the latest flight of the four states last flown in 2023, with reduced pictures of each state and of the country for drawing a map.

One file per quarter quad per state-year, from flights of 2021 to 2025. Each file name holds the date it was flown; a 2023 name then holds a second date, the day the file was made. The quad index gives the flight date of every file.

## Layout

- Quarter quads: `<state>/<year>/<resolution>/rgb/<block>/<name>.tif`, as in the AWS naip-visualization bucket, for example `ut/2024/60cm/rgb/40111/m_4011127_ne_12_060_20240816.tif`.
- Overview files: `overviews/<state>-<year>-utm<zone>.tif` (one flight year of one state in one UTM zone, 9.6 m) and `overviews/national-latest.tif` (the latest flight of each state, EPSG:3857, about 306 m).
- Indexes: `stac/naip.parquet` lists every quarter quad and `stac/naip-overviews.parquet` every overview file, as STAC GeoParquet: address, size, SHA-256, footprint, CRS and flight date. A reader finds the files for a place by querying the index on its `bbox` columns.

## Files

Use GeoParquet for analysis. Field dictionaries describe columns and units.

| File | Size |
| --- | ---: |
| [stac/naip.parquet](https://data.source.coop/nthh/naip/stac/naip.parquet) | 44.29 MB |
| [stac/naip-overviews.parquet](https://data.source.coop/nthh/naip/stac/naip-overviews.parquet) | 516.2 kB |
| [stac/naip.fields.json](https://data.source.coop/nthh/naip/stac/naip.fields.json) | 1.5 kB |
| [stac/naip-overviews.fields.json](https://data.source.coop/nthh/naip/stac/naip-overviews.fields.json) | 1.7 kB |

## Schema

[Column definitions in the catalog](https://nthh.github.io/data-publications/naip/collection.json) include names, storage types and descriptions. Use the field dictionaries and producer documentation above for units, coded values and limitations.


## Read with DuckDB

Query the remote GeoParquet directly:

```sql
SELECT count(*) AS feature_count FROM read_parquet('https://data.source.coop/nthh/naip/stac/naip.parquet');
SELECT * FROM read_parquet('https://data.source.coop/nthh/naip/stac/naip.parquet') LIMIT 5;
```

## Attribution and license

USDA Farm Production and Conservation Business Center, Geospatial Enterprise Operations (NAIP). Source files from the NAIP on AWS open data buckets maintained by Esri.

NAIP imagery is produced by the USDA Farm Production and Conservation Business Center and is in the public domain. USDA asks for credit; these files are a format conversion, not a USDA product.

Independently maintained by [nthh](https://source.coop/nthh).

- [Dataset release](https://registry.opendata.aws/naip/)
- [Processor: nthh](https://source.coop/nthh/naip)
- [Producer: USDA Farm Production and Conservation Business Center](https://www.fpacbc.usda.gov/)

## Limitations

- Display copy only. The files hold red, green and blue as lossy JPEG at quality 65, with overviews at quality 75 and colour at half resolution. The near-infrared band and the lossless pixels stay in s3://naip-analytic.
- Four Pennsylvania 2024 files carry a 2010 flight date in their names, as they do in the source.
- Pennsylvania 2024 (1,118 quads) and West Virginia 2024 (101 quads) cover only part of each state. Their files are hosted, under pa/2024/ and wv/2024/ and as overviews/pa-2024-utm18.tif and overviews/wv-2024-utm17.tif, but the two indexes do not list them and the national file is made without them. Both states are listed whole from 2022, so a map that draws the newest file over a place shows one flight per state. The rule is a count. A year holding under 90% of the quads of an older year of the same state is not listed.
- The 2024 folders of the source lack every quad numbered xx12023 (California and Oregon at 120 W), and Florida 2025 lacks a strip of south Florida. Those places are filled with only the missing quads from California 2022, Oregon 2022 and Florida 2023. They differ from their neighbours in year, season and tone.
- The overview files are for drawing a map, not for measurement. A state file holds one flight year of one state in one UTM zone at 9.6 m; the national file holds the latest flight of each state, so neighbouring states can differ in year and in tone.
- Adjacent quarter quads overlap, as they do in the source.

[Conversion scripts and validation](https://github.com/nthh/data-publications/tree/main/datasets/naip) · [Portolan map](https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/naip/collection.json)


## Query stac/naip-overviews.parquet

```sql
SELECT count(*) AS feature_count FROM read_parquet('https://data.source.coop/nthh/naip/stac/naip-overviews.parquet');
SELECT * FROM read_parquet('https://data.source.coop/nthh/naip/stac/naip-overviews.parquet') LIMIT 5;
```

[Dataset query guidance](AGENTS.md).
