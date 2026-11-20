# NAIP visualization COGs

RGB JPEG Cloud-Optimized GeoTIFFs of USDA NAIP quarter quads, converted from the naip-analytic MRF files with the settings, file names and key layout of the AWS naip-visualization bucket. Every 2024 and 2025 state-year, which that bucket does not hold, and the latest flight of the four states last flown in 2023, with reduced pictures of each state and of the country for drawing a map.

One file per quarter quad per state-year, from flights of 2021 to 2025. Each file name holds the date it was flown; a 2023 name then holds a second date, the day the file was made. The quad index gives the flight date of every file.

## Layout

- Quarter quads: `<state>/<year>/<resolution>/rgb/<block>/<name>.tif`, as in the AWS naip-visualization bucket, for example `ut/2024/60cm/rgb/40111/m_4011127_ne_12_060_20240816.tif`.
- Overview files: `overviews/<state>-<year>-utm<zone>.tif` (one flight year of one state in one UTM zone, 9.6 m) and `overviews/national-latest.tif` (the latest flight of each state, EPSG:3857, about 306 m).
- Indexes: `stac/naip.parquet` lists every quarter quad and `stac/naip-overviews.parquet` every overview file, as STAC GeoParquet: address, size, SHA-256, footprint, CRS and flight date. A reader finds the files for a place by querying the index on its `bbox` columns. `stac/naip.gti.fgb` opens the newest flight of every place in QGIS or GDAL as one mosaic (GDAL tile index in FlatGeobuf), with `stac/naip-overviews.gti.fgb` for zoomed-out views.

## How the two indexes are organized

Each index is a single GeoParquet file in the STAC GeoParquet layout: one row per STAC Item, with
the file's address in the `image` asset. There are no Item JSON files and no partitions. The
STAC Collection is stored in the file's own metadata under the `stac-geoparquet` key, and the
GeoParquet metadata under `geo`.

`stac/naip.parquet` has 245,554 rows, one per quarter quad file, covering 213,436 places; a place
flown in more than one listed year has a row for each. Its columns:

- `id`: state and file name, for example `ut_m_4011127_ne_12_060_20240816`.
- `geometry`: the footprint polygon, WKB in longitude and latitude; `bbox`: its extent as
  `xmin`, `ymin`, `xmax`, `ymax`.
- `datetime`: the flight date, at 00:00 UTC.
- `gsd` (0.3 or 0.6 m), `naip:state`, `naip:year`.
- `proj:code`, `proj:epsg`, `proj:bbox`, `proj:shape`, `proj:transform`: the file's UTM grid.
- `assets.image`: `href` (the file's address), `file:size`, `file:checksum` (SHA-256 as a
  multihash), `type` and `roles`.
- `naip:run`: the conversion run that made the file.
- `naip:gti_location`: the file's address relative to `stac/`, for example
  `../ut/2024/60cm/rgb/40111/m_4011127_ne_12_060_20240816.tif`, left from an earlier tile index
  that has been removed. It is not a STAC field; use `href` instead.

`stac/naip-overviews.parquet` has 115 rows, one per overview file, with the same columns except
`naip:run`, plus `start_datetime` and `end_datetime` (the flights drawn into the file) and
`naip:quads` (how many quarter quads it was made from). The national file's row has no state
or year.

Rows of the quad index are ordered along a Hilbert curve through the centre of each footprint,
newest flight first at the same place, with states and years mixed. They are written in 30
row groups of about 8,192 rows, with statistics and a page index, so a query for a small area
reads a few row groups instead of the whole 45 MB file. For the newest picture of a place, keep
the row with the latest `datetime`.

The quarter quads around Alta, Utah, newest first:

```sql
SELECT id, datetime, assets.image.href AS href
FROM read_parquet('https://data.source.coop/nthh/naip/stac/naip.parquet')
WHERE bbox.xmin < -111.60 AND bbox.xmax > -111.65
  AND bbox.ymin < 40.60 AND bbox.ymax > 40.58
ORDER BY datetime DESC;
```

## Open in QGIS or GDAL

The whole collection opens as one map layer, showing the newest flight of every place. Use
this address:

```
GTI:/vsicurl/https://data.source.coop/nthh/naip/stac/naip.gti.fgb
```

- QGIS: Layer > Add Layer > Add Raster Layer, leave Source type as File, paste the address
  into the source box and click Add. QGIS needs GDAL 3.9 or later (Help > About shows it).
- GDAL 3.9 or later: for example, to save the picture around Alta, Utah:

  ```
  gdal_translate -projwin -111.66 40.60 -111.60 40.57 \
    GTI:/vsicurl/https://data.source.coop/nthh/naip/stac/naip.gti.fgb alta.tif
  ```

The `GTI:` prefix selects GDAL's tile index driver.

What you get: RGB in NAD83 longitude and latitude at about 0.5 m, with an alpha band so the
masked edge of each quad stays clear. Zoomed out, the layer draws the 9.6 m state files and then
the national file, listed in `stac/naip-overviews.gti.fgb`.

How it works: `naip.gti.fgb` is a GDAL tile index (GTI) stored as FlatGeobuf. It has one row
per 3.75-minute cell of the quarter-quad grid, pointing at the newest quarter quad in that cell,
with the cell as its footprint. GDAL reads only the rows in view, not the whole 70 MB file, and
because no two footprints overlap it fetches a view's files in parallel. Measured with GDAL
3.12.4 from a home connection on 2026-11-19, median of three fresh sessions: opening takes
0.6 s, a 1.2 km view at Alta at full resolution 4.8 s (31 reads), a 6 by 4.5 km view at 1 m
17 s (94 reads), and all of Utah at 600 m 3.2 s (17 reads).

Each quarter quad covers a little more than its cell, and GDAL draws all of it, so where two
neighbours overlap either may be on top. Where the newest file of a cell has no picture, the
mosaic is empty rather than showing an older flight.

## Files

Use GeoParquet for analysis. Field dictionaries describe columns and units.

| File | Size |
| --- | ---: |
| [stac/naip.parquet](https://data.source.coop/nthh/naip/stac/naip.parquet) | 45.45 MB |
| [stac/naip-overviews.parquet](https://data.source.coop/nthh/naip/stac/naip-overviews.parquet) | 519.9 kB |
| [stac/naip.fields.json](https://data.source.coop/nthh/naip/stac/naip.fields.json) | 1.6 kB |
| [stac/naip-overviews.fields.json](https://data.source.coop/nthh/naip/stac/naip-overviews.fields.json) | 1.8 kB |

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
