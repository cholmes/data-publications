# NAIP display copies, 2024 onward

The National Agriculture Imagery Program (NAIP) flies the United States at 30 or 60 cm. On AWS it
is published twice: `s3://naip-analytic` holds the four-band data, and `s3://naip-visualization`
holds an RGB JPEG copy that is about a tenth of the size and is what most maps draw. The display
copy stops at 2023. The 2024 and 2025 flights are in `naip-analytic` only, as requester-pays MRF
files that few tools read.

This workspace makes the missing display copy: one RGB JPEG Cloud-Optimized GeoTIFF per quarter
quad, with the same settings, file names and key layout as `naip-visualization`.

**Status (2026-11-10):** Utah 2024 is converted (6,032 files, 249.6 GB) and sits in a private
bucket. Nothing is published. The Source Cooperative product `nthh/naip` exists and is empty.

## Layout

```
<state>/<year>/<resolution>/rgb/<block>/m_<quad>_<quarter>_<utm zone>_<resolution>_<date flown>.tif
ut/2024/60cm/rgb/40112/m_4011233_ne_12_060_20240712.tif
```

A file here has the same path it would have in `naip-visualization`. Each file is in its own UTM
zone, 512 px JPEG blocks at quality 85, with overviews. Adjacent quads overlap.

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
(`COMPRESS=JPEG QUALITY=85 BLOCKSIZE=512 OVERVIEW_RESAMPLING=AVERAGE`), checks the result against
the source, uploads it and writes a receipt with sizes, timings, request counts and the file's
SHA-256. [VALIDATION.md](VALIDATION.md) has the checks and what they found.

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
- At the same rate per byte, all 52 state-years are about $37, plus more memory for 30 cm quads.

## Source and license

NAIP is produced by the USDA Farm Production and Conservation Business Center and is in the public
domain; credit USDA when you use it. The source files are in the NAIP on AWS buckets. These files
are a format conversion and are not a USDA product. The code in this directory is Apache-2.0.

The canonical record is [dataset.yaml](dataset.yaml).
