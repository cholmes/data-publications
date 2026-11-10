# NAIP display copies, 2024 onward

RGB JPEG Cloud-Optimized GeoTIFFs of USDA NAIP aerial imagery for the state-years that the AWS
`naip-visualization` bucket does not hold. That bucket stops at 2023; the 2024 and 2025 flights are
on AWS only as requester-pays MRF in `naip-analytic`. These files are converted from that MRF with
the same settings, file names and key layout as `naip-visualization`, so a path here is the path
the file would have there.

**Draft.** Only Utah 2024 is converted so far and it is not uploaded here yet.

## Files

```
<state>/<year>/<resolution>/rgb/<block>/m_<quad>_<quarter>_<utm zone>_<resolution>_<date flown>.tif
ut/2024/60cm/rgb/40112/m_4011233_ne_12_060_20240712.tif
index/<state>-<year>-<resolution>.parquet
```

- One file per quarter quad, in its own UTM zone, at the source's resolution (30 or 60 cm).
- Red, green and blue, 8 bits each, JPEG at quality 85 in 512 px blocks, with overviews.
- Adjacent quads overlap. The date at the end of a file name is the day it was flown.
- `index/*.parquet` is a GeoParquet table with one row per file: path, footprint, date flown,
  size, SHA-256 and how the file was made.

## What this is not

- Not the four-band data. Near infrared and the lossless pixels are in `s3://naip-analytic`.
- Not a USDA product. It is a format conversion of USDA's imagery.
- Not a mosaic. Nothing is reprojected, colour balanced or merged.

## How it was made and checked

Stock GDAL 3.13.1, COG driver, `COMPRESS=JPEG QUALITY=85 BLOCKSIZE=512`. Every file is checked
against its source for size, georeferencing and layout before upload. On a control of 20 Utah 2021
quads, the result decodes to the same full-resolution pixels as the published `naip-visualization`
file. Code, receipts summary and validation notes:
https://github.com/nthh/data-publications/tree/main/datasets/naip

## Source and license

Imagery: USDA Farm Production and Conservation Business Center, National Agriculture Imagery
Program. Public domain; credit USDA. Source files: NAIP on AWS (https://registry.opendata.aws/naip/).
