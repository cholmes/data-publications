# NAIP display copies

The National Agriculture Imagery Program (NAIP) flies the United States at 30 or 60 cm. On AWS it
is published twice: `s3://naip-analytic` holds the four-band data, and `s3://naip-visualization`
holds an RGB JPEG copy that is about a tenth of the size and is what most maps draw. The display
copy stops at 2023. The 2024 and 2025 flights are in `naip-analytic` only, as requester-pays MRF
files that few tools read.

Microsoft Planetary Computer also publishes NAIP, as four-band Cloud-Optimized GeoTIFFs on Azure.
On 2026-11-14 its catalogue had at least one item for 34 of the 51 state-years of 2024 and 2025 hosted here and
none for the other 17 (`evidence/planetary-computer-presence.json`, made by
`check_planetary_computer.py`; the check tests presence, not completeness). Maine 2025 is there
at 60 cm and here at 30 cm.

This workspace makes the missing display copy: one RGB JPEG Cloud-Optimized GeoTIFF per quarter
quad, with the same settings, file names and key layout as `naip-visualization`.

**Status (2026-11-15):** every 2024 and 2025 state-year is converted and hosted in the Source
Cooperative product `nthh/naip`, which is unlisted, with ten earlier ones. Colorado, Delaware,
Maryland and Washington 2023 are the latest flight of those states, and Utah 2021 is there for
its late-season flights. Pennsylvania 2022 and West Virginia 2022 are whole, because the 2024
flights of both states are partial. California 2022, Oregon 2022 and Florida 2023 hold only
the quads the newer flight lacks (32, 16 and 150). All ten are also in `naip-visualization`;
they are here so one product and one index cover the country. In all 61 state-years in 48
states: 246,773 files, 12.60 TB, about 6% of the size of the source. Each state-year passed
the hosted checks in [PUBLISHING.md](PUBLISHING.md); [VALIDATION.md](VALIDATION.md) has the
results of each. The index at `stac/naip.parquet` lists every file except those of the two
partial years.

**Partial years are hosted but not listed.** Pennsylvania 2024 (1,118 quads) and West Virginia
2024 (101 quads) cover only part of each state. Listed beside the whole 2022 flights, they put
two flights of different season and tone side by side inside one state in any map that draws
the newest file over a place. So neither index lists them, and the national file is made
without them; the files stay under `pa/2024/`, `wv/2024/` and in `overviews/`. The rule is a
count, in [partial_years.py](partial_years.py): a year holding under 90% of the quads of an
older year of the same state is not listed. `build_stac_index.py --keep-partial-years` lists
them again.

The country is whole where the source has a flight since 2021. What is still empty is water
and a range in Nevada that the source leaves black. Where an older flight fills a gap it
differs from its neighbours in year, season and tone. VALIDATION.md has the detail.

**Overview files** are in `overviews/`: 116 reduced pictures of one state, year and UTM zone at
9.6 m, and one of the country in Web Mercator at about 240 m with the latest flight of each
state on top (117 files, 21.4 GB). `stac/naip-overviews.parquet` lists 115 of them (not the two
state files of the partial years), one item per file,
with the pixel size in `gsd` and an outline of where the file has a picture; the collection
record of `stac/naip.parquet` links to it with rel `overviews`. A map draws the coarsest
files whose `gsd` is no larger than a screen pixel and the quads when none is that fine.
[flight-dates/](flight-dates/) holds a viewer of when every quad was flown.

## Layout

```
<state>/<year>/<resolution>/rgb/<block>/m_<quad>_<quarter>_<utm zone>_<resolution>_<date flown>.tif
ut/2024/60cm/rgb/40112/m_4011233_ne_12_060_20240712.tif
overviews/<state>-<year>-utm<zone>.tif          overviews/ut-2024-utm12.tif
overviews/national-latest.tif
stac/naip.parquet                               one item per quad file
stac/naip-overviews.parquet                     one item per overview file
```

A 2023 file name carries two dates: the day flown, then the day the file was made.

A file here has the same path it would have in `naip-visualization`. Each file is in its own UTM
zone, 512 px JPEG blocks at quality 65, with overviews at quality 75. Adjacent quads overlap.

## Flight dates

The date in a file name, and so `datetime` in the index, is the date most of that quad was
flown, not a date for every pixel. Quads are cut from one seamless mosaic: neighbouring Utah
2024 quads with labels five weeks apart hold identical pixels where they overlap. Against
UGRC's NAIP 2024 flight-date polygons, the label is the date covering most of the quad in
98.8% of Utah's 6,032 quads, and 26.6% of quads contain a second date over at least 5% of
their area. A state can change season along a flight line: Utah 2021 is 24 September east of
about -111.56 and 5 to 28 November west of it.

The true lines are in USDA's image-date (seamline) polygons. Checked 2026-11-12: there is no
national file for 2024 or 2025. The national acquisition-date services at
`imagery.geoplatform.gov/iipp/rest/services/NAIP` stop at 2023. Per-state "Image Dates"
layers are on `naip-image-dates-usdaonline.hub.arcgis.com`: all 21 of the 2024 states we
publish were listed, and at least 16 of the 30 for 2025, with more being added. They are not
part of this product.

## What exists to convert

`evidence/naip-analytic-2024-2025-sizes.json`, listed 2026-11-10: 52 state-years in 44 states,
221,255 quads, 180.1 TB of source.

| | State-years | Quads | Source |
|---|---|---|---|
| 2024, 60 cm | 19 | 93,252 | 38.3 TB |
| 2024, 30 cm | 3 | 13,884 | 20.8 TB |
| 2025, 60 cm | 14 | 42,908 | 16.7 TB |
| 2025, 30 cm | 16 | 71,211 | 104.3 TB |

Colorado, Delaware, Hawaii, Maryland, Puerto Rico, the Virgin Islands and Washington have nothing
after 2023 in `naip-analytic`.

## How a file is made

`worker/convert.py` runs in a stock GDAL 3.13.1 container (`worker/Dockerfile`). For each quad it
downloads the `.mrf`, `.idx` and `.lrc`, writes bands 1 to 3 with GDAL's COG driver
(`COMPRESS=JPEG QUALITY=65 OVERVIEW_QUALITY=75 BLOCKSIZE=512 OVERVIEW_RESAMPLING=AVERAGE`; the
qualities are passed to each run as `QUALITY` and `OVERVIEW_QUALITY`), checks the result against
the source, uploads it and writes a receipt with sizes, timings, request counts and the file's
SHA-256. The next quad downloads while the current one converts (`OVERLAP_DOWNLOADS=0` turns that
off). [VALIDATION.md](VALIDATION.md) has the checks and what they found.

Try it on one file without any cloud account:

```sh
docker build -t naip-convert worker
docker run --rm -v "$PWD/in":/src:ro -v "$PWD/out":/out naip-convert --local /src/quad.mrf /out/quad.tif
```

`dispatch.py` builds manifests from a bucket listing and runs the converter as shards on ECS
Fargate Spot in us-west-2, next to the source, where reading it costs requests but no transfer.
`build_index.py` turns a run's receipts into a GeoParquet index of the files.

## What Utah cost

`evidence/utah-2024-summary.json`, `evidence/utah-2024-billed.json`.

- 23.6 minutes on 48 one-vCPU tasks; about 9 seconds per quad.
- $0.51 billed for that day's Fargate Spot, addresses and S3 requests.
- Peak memory 837 MiB per task, so 60 cm runs fit `--memory-mib 2048`, the least Fargate allows
  for one vCPU. The pilot ran with 4 GiB; New Hampshire 2025 then ran on 2 GiB.
- Downloading the next quad during conversion took 21% off the time per quad in New Hampshire.
- Requests were 38% of that bill, so the converter now uploads each file in one request and
  downloads the data file in 128 MiB parts.
- With those changes all 52 state-years are estimated at about $20 (range $19 to $24):
  `evidence/national-cost-estimate.json`. 30 cm is measured on a 40-quad sample: it needs 4 GiB
  tasks and runs about 20% slower per byte. Storage of the output is not in that figure.

## Source and license

NAIP is produced by the USDA Farm Production and Conservation Business Center and is in the public
domain; credit USDA when you use it. The source files are in the NAIP on AWS buckets. These files
are a format conversion and are not a USDA product. The code in this directory is Apache-2.0.

The canonical record is [dataset.yaml](dataset.yaml).
