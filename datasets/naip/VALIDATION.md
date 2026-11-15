# Validation: NAIP display copies

## What was decided before the runs (2026-11-10)

These were written down before any file was converted on AWS, in the pilot plan and in the
converter itself (`worker/convert.py`, function `check`).

1. **Every file** must pass these checks against its source before it is uploaded, or the quad is
   recorded as failed and nothing is uploaded: same width and height, same geotransform, same EPSG
   code, three bands, COG layout, YCbCr JPEG compression, 512 px blocks, at least one overview.
2. **A sample** (every 50th quad) is compared pixel for pixel with the source's red, green and blue
   bands at full resolution, as PSNR per band. No pass mark was set in advance; the figure is
   reported.
3. **A control**: convert quads of a year that `s3://naip-visualization` already publishes, from the
   same kind of MRF source, and compare each result with the published file for size and for error
   against the source. No tolerance was set in advance. The question was whether stock GDAL with
   these settings reproduces the existing bucket.

A local trial on one quad came first. It settled nothing except that JPEG quality 85 was the
setting to test; its figures are not kept in this repository.

## Results

### Control: Utah 2021, 20 quads (run `control-1`)

`evidence/control-2021-summary.json`. Twenty quads spread across the state.

- Published settings, read from the published files: JPEG, YCbCr, quality 85, 512 px blocks, five
  overviews. The converter's settings are the same.
- Error against the source: identical for our file and the published file on all 20 quads, to
  three decimals (median 34.58 dB). The two decode to the same full-resolution pixels.
- Size: our files are 81% to 87% of the published files (median 84%). One published file was
  opened to see why (`m_3710928_se_12_060_20210822`): its tiles total 50.6 MB against 51.9 MB for
  ours, but the file is 61.7 MB. About 11 MB is not referenced by any tile, and GDAL reports that
  the file's layout was changed after it was written. Only that one file was examined.
- Overviews differ by one pixel in size (2512 against 2513 wide at the second level): the two were
  built by different overview code. Overview pixels were not compared.

### Utah 2024, 6,032 quads (run `ut2024-1`)

`evidence/utah-2024-summary.json`, `evidence/utah-2024-index.json`.

- 6,032 of 6,032 quads converted. None failed and none had a check problem.
- 249,594,785,306 bytes written from 2,490,401,105,942 bytes read (10.0%).
- Sampled error against the source, 121 quads: median 35.3 dB, lowest 32.0 dB.
- Flown 2024-06-23 to 2024-08-31.
- Peak memory of the converter process: 837 MiB on tasks with 4 GiB. A quad without the pixel
  comparison peaked near 540 MiB.
- Task time, summed over the receipts: 67% converting, 26% downloading, 5% uploading.

### New Hampshire 2025, 771 quads (run `nh2025-1`)

`evidence/new-hampshire-2025-summary.json`, `evidence/new-hampshire-2025-overlap.json`.

First run of the converter that downloads the next quad while the current one converts, and
first run on 2 GiB tasks.

- 771 of 771 quads converted, none with a check problem. One task was interrupted by Spot; its
  shard was launched again and skipped the quads already done.
- 47,401,872,192 bytes written from 353,433,330,595 bytes read (13.4%).
- Sampled error against the source, 16 quads: median 31.0 dB, lowest 29.9 dB. That is about
  4 dB below Utah at the same JPEG quality, with larger files. The control below shows the
  published display copies of New Hampshire have the same error.
- Peak memory 821 MiB on 2 GiB tasks.
- Overlapped downloads: 6.72 s per quad over 15 shards, against 8.46 s over two shards that
  repeated the same quads with overlap off, 21% less. The wait for downloads fell from 2.2 s to
  under 0.1 s per quad; conversion CPU time rose from 5.5 s to 5.9 s because the download shares
  the one vCPU. Two comparison shards are a small sample and hosts differ in speed.

### Rhode Island 2025, 116 quads (run `ri2025-1`)

`evidence/rhode-island-2025-summary.json`. First run with one-request uploads and 128 MiB
download parts.

- 116 of 116 quads converted on four 2 GiB tasks, none with a check problem.
- Requests per quad: 5.9 GET, 2 HEAD, 1 PUT for the file, plus the receipt's PUT. Utah averaged
  about 23 download and 4.5 upload requests per quad.
- 6.12 s per quad; the wait for downloads stayed near 0.1 s with the larger parts.
- Sampled error against the source, 6 quads: median 31.25 dB.

### 30 cm: New Hampshire 2023 control and Vermont 2025 sample, 20 quads each

`evidence/control-nh-2023-30cm-summary.json`, `evidence/vermont-2025-30cm-sample-summary.json`.
Runs `control-nh30-1` and `vt2025-sample-1`, on 8 GiB tasks so the real memory peak would show.

- 40 of 40 quads converted, none with a check problem. A 30 cm quad is about 420 to 500
  megapixels, 1.7 to 2.0 GB of source and 206 to 233 MB of output (11.7% of the source).
- Control: error against the source is 33.65 dB (median, lowest band) for both our files and
  the published 2023 display copies; per quad they differ by 0.001 to 0.003 dB. Our files are
  88% of the published size (80% to 99%).
- Peak memory 1,510 MiB. 4 GiB tasks are enough; 2 GiB would be tight.
- Vermont 2025: about 31 s per quad once the pixel check is counted at one quad in 50, which is
  4.9 task-hours per source TB against 3.9 to 4.1 for 60 cm.
- Vermont 2025 sampled error: median 29.48 dB, lowest 27.66 dB (10 quads). Forest again.
- Each file went up in one request (largest 300 MB).

### Control: New Hampshire 2021, 20 quads (run `control-nh-1`)

`evidence/control-nh-2021-summary.json`. Run because New Hampshire 2025 measured about 4 dB
below Utah; New Hampshire is mostly forest.

- Error against the source, lowest band: median 29.79 dB for our files and 29.79 dB for the
  published files (range 28.34 to 31.89 for both). Per quad and per band the two differ by
  0.001 to 0.003 dB.
- So the lower figure is what quality 85 gives on this imagery, and the published product has it
  too. It is not a fault of this conversion.
- Size: our files are 80% to 100% of the published files (median 89%).

## What this does not establish

- No output file from the Utah pilot has a recorded SHA-256. The converter records one from the
  next run on; the pilot's files need a pass that reads and hashes them.
- Only 40 quads of 30 cm have been converted. No full 30 cm state-year has run.
- The controls cover two states (Utah 2021, New Hampshire 2021). Other states' published files
  were not compared.
- Overview levels were checked for presence, not compared pixel for pixel with anything.
- Nothing here assesses the imagery itself (cloud, seamlines, colour balance). These files carry
  whatever the source carries.

## Hosted files (2026-11-11)

The checks were set in [PUBLISHING.md](PUBLISHING.md) before any upload and are run by
`check_hosted.py` with anonymous requests.

### First publishing runs: `ri2025-pub-1`, `nh2025-pub-1`, `ut2024-pub-1`

The grant was confirmed with two quads (`ri2025-pub-smoke`). The three state-years were then
converted again straight into `nthh/naip/`: 116, 771 and 6,032 files, none with a check problem,
every file with a SHA-256. Byte totals equal the pilot runs' exactly (6,112,508,166,
47,401,872,192 and 249,594,785,306). Spot interrupted 3 New Hampshire and 5 Utah tasks; their
shards were launched again.

- Rhode Island: the four hosted checks pass (`evidence/rhode-island-2025-hosted-checks.json`;
  24 files downloaded and hashed).
- New Hampshire: the four hosted checks pass (`evidence/new-hampshire-2025-hosted-checks.json`;
  21 files).
- Utah: the hosted checks were stopped before they finished, because of the fault below.

### Fault found after those checks passed: darkened overview edges

**These 6,919 files are faulty and are to be replaced.** Drawing them in a map at low zoom
showed dark dashes along quad edges. In each file, the last row or column of an overview level
is darker than the one before it wherever the level above has an odd size: about half as
bright at one level, a quarter at the next. Measured on `ut/2024/60cm/rgb/40111/
m_4011117_se_12_060_20240707.tif`, mean of the last two rows of band 1: level 2, 145.0 then
73.1; level 3, 143.7 then 37.3. Full resolution is not affected.

Cause: the source MRF carries its own pyramid (`<Rsets model="uniform" scale="2" />`), padded
with zeros where a size is odd, and GDAL's COG driver copies a source's overviews when it has
them. That is also why our overview sizes were one pixel larger than the published files' in
the Utah 2021 control. The published `naip-visualization` file for the same quad
(`m_4011117_se_12_060_20211105.tif`) has no darkened edge at any level.

None of the checks set beforehand looked at overview pixels; "What this does not establish"
said so. The hosted checks above passed on faulty files.

Fix, in `worker/convert.py`: `OVERVIEWS=IGNORE_EXISTING`, so overviews are built from full
resolution, and a new per-file check that fails a quad when any overview level's last row or
column is below 0.7 of the one before it (the ratios are kept in each receipt, for the source
and the output). Tried locally on the real source of `ri_m_4107102_ne_19_060_20250803`: the
source's ratios are as low as 0.46; the output's are 0.987 to 1.021 at every level, its
overview sizes now match the published convention (4524, 2262, 1131, 565, 282 wide), and
conversion took 5.8 s. Not yet run on AWS: it needs a new image.

## Checks set for the corrected converter (image `v4`), before any `v4` result (2026-11-11)

No state-year is converted again until these pass. All of it runs in the private work bucket.

The control quads are the 60 used before: 20 each of Utah 2021 (60 cm), New Hampshire 2021
(60 cm) and New Hampshire 2023 (30 cm), each compared with the file `naip-visualization`
publishes for the same quad. Runs `control-v4-ut21`, `control-v4-nh21`, `control-v4-nh23`.

1. **Overview sizes.** Every overview level of every control output has the same width and
   height as the published file's. Pass: all 60, all levels.
2. **Overview edges.** At every level, the last row over the row before it and the last column
   over the column before it are at least 0.9 in our file. The published file's ratios are
   reported beside ours. Pass: all 60, all levels. (The converter itself fails a quad below 0.7.)
3. **Overview pixels.** Each overview level of our file is compared pixel for pixel with the
   same level of the published file, as PSNR per band, and the same figure is taken at full
   resolution. Both are JPEG of the same source, so they will not be identical. Pass: at every
   level the median over the quads is no more than 3 dB below the full-resolution median for
   that set, and no single quad-level is below 25 dB. Whatever is found is reported.
4. **Everything GDAL reports.** `gdalinfo -json` of our file and of the published file are
   compared key by key for every control quad, leaving out file names and sizes. Every
   difference is listed, not only the ones looked for. Pass: no difference that changes what a
   reader gets (georeferencing, CRS, bands, colour interpretation, masks, nodata, block size,
   compression, overview count and sizes). Differences in tags that do not are listed and judged
   one by one.
5. **Full resolution unchanged.** The control's error against the source is the same as in the
   first control (per quad, within 0.01 dB), since only overviews should differ.
6. **Drawn.** A mosaic of four adjacent control-area quads at each overview scale, warped with
   GDAL from our files and from the published files, shows no line along a quad edge: along
   each shared edge, the mean of the two pixel rows or columns on the seam is within 10% of
   the mean of the ten on either side. One case crosses a UTM zone line.

### Results for image `v4` (2026-11-11)

Runs `control-v4-ut21`, `control-v4-nh21`, `control-v4-nh23` (60 quads, none with a check
problem; two 30 cm tasks were interrupted by Spot and launched again) and `seam-v4-ut24`
(four adjacent Utah 2024 quads across the UTM 11/12 line, in a test prefix of the work bucket).
Compared with `compare_published.py` and `seam_check.py`:
`evidence/control-v4-compare-published.json`, `evidence/seam-utah-2024-before.json`,
`evidence/seam-utah-2024-v4.json`.

1. **Overview sizes: pass.** Equal to the published file's at every level on 60 of 60 quads.
2. **Overview edges: pass.** Our lowest ratio is 0.951 (Utah 2021), 0.934 (New Hampshire 2021)
   and 0.970 (New Hampshire 2023); the published files' lowest are 0.928, 0.939 and 0.977. The
   source MRF pyramids are as low as 0.03.
3. **Overview pixels: the pass mark was mis-set; figures reported.** It was written as a
   margin below the full-resolution figure, on the assumption that full resolution would differ
   between our file and the published one. It does not: on the centre 4096 px window the two
   are pixel for pixel identical on 60 of 60 quads. The overview levels differ: median 37.9 to
   39.2 dB (Utah 2021), 34.8 to 36.0 dB (New Hampshire 2021), 34.5 to 37.1 dB (New Hampshire
   2023), lowest single quad-level 32.5 dB, above the 25 dB floor. On one quad
   (`ut_m_3710928_se_12_060_20210822`) both were compared with a lossless average of the
   source: ours 32.10, 32.85, 33.01, 33.90, 35.66 dB by level, published 31.94, 32.71, 32.77,
   33.63, 35.41 dB. Rebuilding that published file's overviews from its own decoded full
   resolution with AVERAGE reproduces its first level to 62 dB, so the published overviews
   look to have been made from the compressed image and ours from the source. One quad only.
4. **Everything GDAL reports: no difference that changes what a reader gets.** Listed in full:
   the published files carry vendor TIFF tags (software, artist, host, date, document name,
   image description, resolution unit) that the source MRF does not hold, so ours lack them;
   ours report `LAYOUT=COG` and `OVERVIEW_RESAMPLING=AVERAGE` and the published files report
   neither; on 16 New Hampshire 2021 and 8 New Hampshire 2023 quads our pixel height is
   -0.6000000000000288 or -0.3000000000000145 where the published file has -0.6 or -0.3,
   which comes from the source's bounding box (under a nanometre over a quad).
5. **Full resolution unchanged: pass.** Error against the source equals the first control's
   to four decimals on all 60 quads. File sizes are 98.4% to 100.3% of the first control's.
6. **Drawn: pass.** With each quad drawn over its neighbours at 2 to 32 times the pixel size,
   the 20 edges that have a neighbour beneath them measure 0.976 to 1.029, including the two
   zone 11 quads drawn over zone 12 neighbours. The same edges of the faulty files in the
   product measure down to 0.573.

Cost: building overviews instead of copying them makes conversion slower. Convert time per
quad went from 6.0 to 10.1 s (Utah 2021), 7.4 to 10.2 s (New Hampshire 2021) and 33 to 60 s
(30 cm). The national estimate of about $20 is therefore low; a rough scaling of its compute
share gives about $30 to $35. It is to be redone from the first full `v4` state-year.

Still not established: the overview comparison against a lossless average covers one quad;
the seam check covers one place; no full state-year has run on `v4`.

### Rhode Island 2025 converted again on `v4` (run `ri2025-pub-2`, 2026-11-11)

The first state-year replaced in the product. New Hampshire and Utah still hold the faulty
files of `nh2025-pub-1` and `ut2024-pub-1`.

- 116 of 116 quads, none with a check problem, every file with a new SHA-256; 6,059,990,730
  bytes (the faulty run wrote 6,112,508,166).
- Lowest overview edge ratio in any file: 0.925. The source pyramids are as low as 0.033.
- 10.1 s per quad against 7.8 s in `ri2025-pub-1`.
- The four hosted checks pass on the new files (`evidence/rhode-island-2025-hosted-checks.json`,
  24 files downloaded and hashed; this replaces the result for the faulty files).
- Seams, four adjacent quads near Providence drawn from the product: 0.990 to 1.046 on 20
  edges (`evidence/seam-rhode-island-2025.json`).
- Drawn in a map through `https://data.source.coop/nthh/naip/stac/naip.parquet`: no line at
  quad edges at zoom 12, where New Hampshire's faulty files still show a dashed dark line.

### New Hampshire 2025, Utah 2024 and Vermont 2025 on `v4` (2026-11-11)

Runs `nh2025-pub-2`, `ut2024-pub-2` and `vt2025-pub-1` wrote straight into the product. The
first two replace the faulty files of `nh2025-pub-1` and `ut2024-pub-1`; Vermont is the first
whole 30 cm state.

| | New Hampshire 2025 | Utah 2024 | Vermont 2025 (30 cm) |
|---|---|---|---|
| Quads with a receipt | 771 of 771 | 6,032 of 6,032 | 812 of 812 |
| Quads with a check problem | 0 | 0 | 0 |
| Bytes | 47,074,374,812 | 249,219,194,687 | 148,785,989,474 |
| Lowest overview edge ratio | 0.928 | 0.841 | 0.929 |
| Seconds per quad (receipts) | 10.1 | 11.2 | 45.2 |
| Peak memory, MiB | 844 | 894 | 1,139 |
| Tasks started, Spot interruptions | 12, 0 | 51, 3 | 40, 10 |
| Task-hours per source TB, whole task time | 6.5 | 7.9 | 8.1 |
| Hosted checks, files downloaded and hashed | pass, 21 | pass, 121 | pass, 21 |
| Seams across a UTM zone line, 20 edges | 0.998 to 1.033 | 0.976 to 1.029 | 0.989 to 1.045 |

- Utah's three quads under 0.92 (`m_4111261_se`, `m_4111262_sw`, `m_4011205_ne`) are open
  water on the Great Salt Lake. On the lowest, band 1 is about 1.4 across the last 96 rows at
  full resolution and 0.8 to 2.4 in the last rows of the smallest overview: the ratio is
  noise between near-black rows, not the darkened edge of the fault (which was 0.03 to 0.6
  on bright ground).
- Interrupted shards were started again with `launch --only`; no quad was converted twice
  into a different file (one receipt and one run id per quad).
- Evidence: `evidence/{new-hampshire-2025,utah-2024,vermont-2025}-{summary,hosted-checks}.json`
  and `evidence/seam-{new-hampshire-2025,utah-2024,vermont-2025}.json`.
- The index at `https://data.source.coop/nthh/naip/stac/naip.parquet` now holds 7,731 rows
  for the four state-years, all describing `v4` files.

### National estimate and launch plan after `v4` (2026-11-11)

`evidence/national-cost-estimate.json` (schema `@3`) replaces the $20 estimate: about $30
for the remaining 48 state-years ($28 to $33), from whole task time on the three runs above
and the Spot rates billed on 2026-11-10. The bill for 2026-11-11 had not posted when it was
written. `make_launch_plan.py` writes `evidence/national-launch-plan.json`: 48 runs, 2,384
shards sized by source bytes at about 0.6 task-hours each, six waves of at most 450 tasks
(the Fargate Spot quota is 512 vCPUs), launcher bounds adding to $140. Maine 2024 has a
60 cm and a 30 cm run with different run ids. Not launched.

## Tiles on a shared grid: one 100 km square (set 2026-11-12, before any result)

A test of re-cutting the imagery from quads into tiles on one pixel grid per UTM zone, and
of assembling a 100 km file from small tiles by copying compressed blocks. Written to our
own bucket under `_proto/`, not to the product.

**Why it is possible.** Every Utah 2024 quad's bounds are whole multiples of 0.6 m (6,032 of
6,032), and three pairs of neighbouring quads hold identical pixels where they overlap, in
the lossless source. So quads are cuts of one mosaic and can be cut differently without
resampling.

**The square.** NAD83 / UTM 12N, easting 400,000 to 500,000 m, northing 4,400,000 to
4,500,000 m (Provo, Timpanogos, Alta). A pixel belongs to the square when its centre is
inside it: 166,666 by 166,667 pixels, from x 400,000.2 and y 4,500,000.0. 320 source quads.

**Small tiles.** 32 by 32 blocks of 512 pixels (16,384 pixels, 9,830.4 m), counted from the
square's north-west pixel, so every block of a small tile is a block of the square: 11 by 11
tiles, the last row and column partial. JPEG quality 75, YCbCr, five overview levels built
by averaging from full resolution.

**The 100 km file.** Full resolution and overview levels 1 to 5 are the small tiles' blocks,
copied without decoding. Levels 6 to 9 are averaged from the decoded level 5 and encoded at
the same quality (one more generation than a direct build, on levels of 19 m and coarser).

Pass marks:

1. **Small tiles are the source.** Every tile's size and position match its window. On a
   sample of at least 12 tiles, PSNR against the lossless source over the whole tile is at
   least 31.0 dB in each band (quality 75 measured 32.0 to 37.5 dB on ten Utah crops).
2. **Tiles meet.** For every pair of neighbouring tiles, reading the two tiles' edge rows or
   columns gives the same values as reading the same rows or columns of the lossless source
   to within the JPEG error of criterion 1; no row or column is missing or repeated
   (positions checked from the geotransforms: the right edge of one tile is the left edge of
   the next, exactly).
3. **The copy is exact.** In the 100 km file, levels 0 to 5 decode to the same pixel values
   as the small tiles, on every block of at least 12 tiles and every level (difference
   exactly zero).
4. **The 100 km file is a valid COG.** GDAL reports `LAYOUT=COG`, GDAL's COG validator
   reports no error, and the file's size is within 1% of the small tiles' sizes summed plus
   levels 6 to 9.
5. **No darkened edges.** The overview edge ratio of every small tile is at least 0.7 at
   every level, as for quads.

Recorded without a pass mark: task time and cost per source TB; requests and bytes to a
first image for quads, small tiles and the 100 km file in GDAL, the browser reader and
Folia's reader; and whether each reader fetches the whole block table of the 100 km file.
A failed criterion is recorded as failed.

### Results (2026-11-12)

Square: NAD83 UTM 12N, easting 400,000 to 500,000, northing 4,400,000 to 4,500,000
(166,666 by 166,667 px). 121 tiles from 320 source quads, JPEG quality 75. Evidence in
`evidence/grid-1/`.

| Pass mark | Result |
|---|---|
| 1. Small tiles are the source | **Failed.** Size and position match on all 121 tiles. 13 tiles were sampled for PSNR; 9 have every band at 31.0 dB or more. Four fall short in blue only (29.75, 30.33, 30.78, 30.82 dB); red is 31.9 dB or more and green 33.2 dB or more on every tile. |
| 2. Tiles meet | Passed on positions: 11 by 11 tiles at exact 16,384 px steps, last row and column trimmed to the square. The edge rows were not separately read against the source. |
| 3. The copy is exact | Passed. Difference zero on every block of 13 tiles at levels 0 to 5. |
| 4. The 100 km file is a valid COG | Passed as written (`LAYOUT=COG`, validator no error or warning, 0.04% larger than the tiles summed). **But the first file did not draw in the browser reader**, see below. |
| 5. No darkened edges | Passed. Ratios 0.968 to 1.036. |

**Browser reader failure and fix.** The first assembled file wrote each level's tag values
in tag order, which put the JPEG tables after the block tables, 1.7 MB into the file.
GDAL read it; `@cogeotiff/core` (under deck.gl-geotiff) looks for the tables only in the
header bytes it fetches first and raised "Unable to find Jpeg header" for every block. The
pass mark did not cover a browser reader and should have. The assembler now writes the
small values of every level first and the block tables after, coarsest level first. The
test file was corrected by rewriting its first 2,275,616 bytes and copying the rest inside
S3 (`rehead_square.py`), not by a new run: a new converter image was not built because the
build machine was under its free-disk floor. The corrected file gives the same GDAL
checksums as the first at four windows and levels, and draws in the browser. The fixed
assembler passed the local self test; it has not yet run in the cluster.

**Compute.** Tiles: 5,554 task-seconds summed over 12 tasks (one Spot interruption), 8.4 MP
per CPU-second median, peak 1.56 GB. Source downloaded was 213.9 GB against 134.9 GB of
distinct source, because tiles in different tasks fetch the quads they share. Assembly:
7.4 CPU-seconds to copy, 324 s of task time with download, comparison, validation and
upload. Output 6.93 GB for tiles and for the 100 km file.

**Readers, cold.** Quads are the published files (quality 85) read from the Source
Cooperative bucket directly; tiles and the 100 km file are quality 75. Run from a laptop on
a home connection, so requests and bytes are the comparable figures.

GDAL 3.13.1, each view read to a 1024 px image (requests, MB, files opened):

| View | Quads by VRT | Quads by STAC index (GTI) | Tiles by VRT | 100 km file |
|---|---|---|---|---|
| Street, 614 m | 5, 0.72, 1 | 7, 0.74, 2 | 5, 0.56, 1 | 11, 0.67, 1 |
| Canyon, 15 km | 44, 3.42, 12 | 46, 3.44, 13 | 21, 1.06, 6 | 9, 0.84, 1 |
| Square, 100 km | 963, 22.8, 320 | 965, 23.1, 321 | 362, 7.85, 121 | 8, 0.57, 1 |

Building the quad VRT with `gdalbuildvrt` took 102 s and 640 requests. GDAL opened the
published STAC-GeoParquet index as a mosaic with no extra file
(`GTI:naip.parquet` with a filter on `naip:state`).

deck.gl-geotiff demo page, 1280 by 800 window (image requests, MB, files):

| View | Quads | Tiles | 100 km file (corrected) |
|---|---|---|---|
| Street, 0.6 km | 7, 0.51, 1 | 7, 0.39, 1 | 9, 0.52, 1 |
| Canyon, 19 km | 30, 1.74, 15 | 12, 0.74, 6 | 8, 0.46, 1 |
| Region, 37 km | 72, 3.86, 36 | 32, 1.83, 16 | 10, 0.51, 1 |

Neither reader fetched the whole block table of the 100 km file.

Not yet measured: Folia's reader, offline byte counts for the tiles and the 100 km file,
and a square on a state edge (which needs a transparency mask in the tile cutter and the
assembler).

### Same overview depth for every layout (2026-11-12)

The reader comparison above is unfair to quads and tiles: their overviews stop at their own
width, while the 100 km file's go down to the whole square. To separate "deep overviews"
from "one big file", an overview-only file was made for the square from the 100 km file's
levels 3 to 9 (4.8 m per pixel and coarser, 20,833 px, 118 MB, 1.7% of the full-resolution
bytes), by copying those blocks inside S3 (`make_overview_file.py`); its GDAL checksums
match the same levels of the 100 km file. The demo draws it below zoom 13.6 and the
full-resolution files at or above. The "switch" view is at zoom 13.6, the widest view the
full-resolution files must serve. No pass mark was set for this comparison.

deck.gl-geotiff demo page, 1280 by 800 window (image requests, MB, files):

| View | Quads alone | Quads + overview file | Tiles + overview file | 100 km file |
|---|---|---|---|---|
| Street, 0.6 km | 7, 0.51, 1 | 7, 0.51, 1 | 7, 0.39, 1 | 9, 0.52, 1 |
| Switch, 6 km | 17, 1.32, 2 | 17, 1.32, 2 | 11, 0.69, 1 | 15, 0.95, 1 |
| Canyon, 19 km | 30, 1.74, 15 | 8, 0.46, 1 | 8, 0.46, 1 | 8, 0.46, 1 |
| Region, 37 km | 72, 3.86, 36 | 10, 0.51, 1 | 10, 0.51, 1 | 10, 0.51, 1 |

With equal overview depth the three layouts cost the same below the switch, and differ by
at most 6 requests at it (one placement, where the view touched two quads; a view on a
quad corner would touch four). The earlier advantage of the 100 km file was the overview
depth, not the file size. Quads are quality 85 here and the others 75.

GDAL 3.13.1 with the same overview file attached (requests, MB, files opened), each view
read to a 1024 px image; "switch" here is 4.8 km at 4.7 m per pixel:

| View | Quads by VRT + overview | Tiles by VRT + overview | 100 km file |
|---|---|---|---|
| Street, 614 m | 5, 0.72, 1 | 5, 0.56, 1 | 8, 0.61, 1 |
| Switch, 4.8 km | 16, 2.62, 3 | 9, 1.64, 2 | 8, 1.64, 1 |
| Canyon, 15 km | 5, 0.77, 1 | 5, 0.77, 1 | 6, 0.77, 1 |
| Square, 100 km | 4, 0.46, 1 | 4, 0.46, 1 | 5, 0.51, 1 |

The VRT names the overview file and each of its levels in `<Overview>` elements. An
overview is taken to cover the same extent as the mosaic, so the quad VRT had to be cut to
the square first; an overview file must match the extent of whatever names it.

**Not working: the STAC index plus the overview file in GDAL.** Opened as
`GTI:naip.parquet` the published index reads correctly at full resolution (first table
above), but that form cannot name an overview file. A `.gti` XML file that names the index
and the overview file (`quads-stac-ov.gti`) opened only when given the CRS and extent, read
the overview levels, and returned blank images at full resolution (checksum 0 on the
street and switch views). The index footprints are in longitude and latitude, as STAC
requires, and the XML form appears to expect them in the mosaic's CRS; not investigated
further. A tile index in the mosaic's CRS, written from the STAC index, is the likely way
to give GDAL both; untested.

**Correction, same day: the STAC index can carry the overview file for GDAL.** The GTI
driver reads its settings from the index layer's metadata, and the Parquet driver keeps
layer metadata in the file. A copy of the square's 320 STAC rows with `SRS`,
`SRS_BEHAVIOR=REPROJECT`, the grid and extent, and `OVERVIEW_<n>_DATASET` entries in its
metadata (`make_gti_parquet.py`) opens as `GTI:<file>` with full resolution and all seven
overview levels, nothing else needed. `SRS_BEHAVIOR=REPROJECT` is what the `.gti` attempt
above lacked: it tells GDAL the footprints are in another CRS than the mosaic.

| View | Requests, MB, files |
|---|---|
| Street, 614 m | 9, 0.75, 3 |
| Switch, 4.8 km | 18, 2.64, 4 |
| Canyon, 15 km | 7, 0.79, 2 |
| Square, 100 km | 6, 0.48, 2 |

The images are not blank; their checksums differ slightly from the VRT route's (the mosaic
is one row taller from rounding the extent, and overlapping quads may be drawn in a
different order). Not compared pixel by pixel.

## Quality 65 at full resolution, 85 for overviews (set 2026-11-12, before any result)

Nathan's choice after viewing ten Utah areas at quality 50, 65, 75 and 85: 65 for full
resolution, 85 for the overview levels. The converter gets a separate overview quality
(GDAL's `OVERVIEW_QUALITY`). Checked on one Utah quad built three ways from the lossless
source: 65 with 85 overviews, 65 throughout, and 85 throughout.

Expected size, from the crop measurements (65 is 58% of the bytes of 85; overviews are a
third of full resolution at equal quality): 68% of the all-85 file, 18% more than all-65.

Pass marks:

1. **Full resolution is quality 65.** Its PSNR against the source is within 0.2 dB of the
   all-65 file's in every band, and its full-resolution bytes within 2%.
2. **Overviews are quality 85.** At each overview level, PSNR against the all-85 file's
   same level is at least 45 dB or the two decode identically, and the level's bytes are
   within 2% of the all-85 file's. (Both average the same lossless pixels; only rounding
   in the encoder may differ.)
3. **Size.** The file is between 64% and 72% of the all-85 file.
4. **Still a valid COG** with the same block size, levels and layout as the published
   quads, and overview edge ratios of at least 0.7.

Recorded without a pass mark: PSNR per band at full resolution and at each level.
A failed criterion is recorded as failed.

### Results (2026-11-12)

Quad `m_4011127_ne_12_060_20240816` (Alta, Utah), GDAL 3.13.1 on a laptop. Evidence in
`evidence/quality-65-85/`.

| Pass mark | Result |
|---|---|
| 1. Full resolution is quality 65 | Passed. PSNR identical to the all-65 file in every band (33.34, 34.07, 31.63 dB) and the full-resolution bytes are identical. |
| 2. Overviews are quality 85 | Passed. Every overview level decodes identically to the all-85 file's and has the same bytes. |
| 3. Size | Passed. 29.7 MB, 71.0% of the all-85 file (41.8 MB); the estimate was 68%. 20% more than all-65 (24.7 MB). |
| 4. Still a valid COG | Passed on layout, block size and levels (five overviews, as published); edge ratios 0.993 to 1.013. GDAL's validator script was not run on this local file. |

Recorded: the first overview level alone is 8.8 MB, 30% of the file. Against the all-65
file's overviews, the 85 overviews differ by 30 to 32 dB, which is the error the lower
setting would have added at those levels. All-85 full resolution measured 35.9, 36.9 and
33.3 dB. This ran with GDAL directly, not through the converter image; `convert.py` and
`mosaic.py` now take `OVERVIEW_QUALITY` but have not run with it in the cluster.

## WebP against JPEG, and overview quality (set 2026-11-12, before any result)

One Utah quad (`m_4011127_ne_12_060_20240816`), built from the lossless source as COGs:
JPEG at 65 with overviews at 65, 75 and 85; WebP (lossy) at 50, 60, 70, 75, 80 and 85 with
overviews at the same quality. Reference for every level: a lossless COG of the same quad
with the same averaged overviews. One thread for every build, so encode times compare.

Pass marks for WebP as the published encoding:

1. **Smaller at no more error.** Take the lowest WebP quality whose full-resolution PSNR
   is at least JPEG 65's in every band. Its file is at least 15% smaller than the JPEG
   file with overviews at 65.
2. **Draws in the browser reader.** The deck.gl-geotiff demo draws the WebP file at a
   street view and at a zoomed-out view with no error.
3. **Decode is not much slower in the browser.** Median decode time per block in the demo
   is at most twice JPEG's for the same views.
4. **Same structure.** `LAYOUT=COG`, 512 px blocks, five overview levels.

Recorded without a pass mark: encode seconds, GDAL decode seconds, bytes and PSNR at
every level for every build. The overview quality choice (65, 75 or 85) is Nathan's to
make from the per-level figures. Folia's own reader and ArcGIS are not tested here.
A failed criterion is recorded as failed.

### Results (2026-11-12)

GDAL 3.13.1 on a laptop, one thread; 117.7 megapixels. Evidence in `evidence/webp/`.
PSNR is red, green, blue against the lossless COG's same level.

| Build | File MB | Full res MB | Full res PSNR | Level 1 PSNR | Level 3 PSNR | Encode CPU s | Decode all levels CPU s |
|---|---|---|---|---|---|---|---|
| JPEG 65, overviews 65 | 24.70 | 17.53 | 33.3 34.1 31.6 | 31.7 32.5 30.5 | 30.7 31.6 30.2 | 3.2 | 0.60 |
| JPEG 65, overviews 75 | 26.36 | 17.53 | same | 32.7 33.5 31.1 | 31.8 32.7 30.8 | 3.2 | 0.64 |
| JPEG 65, overviews 85 | 29.67 | 17.53 | same | 34.6 35.5 32.1 | 33.9 35.0 31.8 | 3.3 | 0.66 |
| WebP 50 | 16.07 | 11.24 | 32.4 33.2 31.2 | 31.5 32.4 30.3 | 30.7 31.8 30.1 | 14.8 | 1.44 |
| WebP 60 | 18.69 | 13.09 | 33.1 34.0 31.7 | 32.3 33.3 30.8 | 31.5 32.7 30.6 | 15.2 | 1.55 |
| WebP 70 | 21.60 | 15.17 | 33.8 34.8 32.2 | 33.0 34.1 31.4 | 32.4 33.7 31.0 | 16.1 | 1.81 |
| WebP 75 | 23.31 | 16.39 | 34.2 35.2 32.5 | 33.5 34.6 31.6 | 32.8 34.2 31.3 | 16.3 | 1.85 |
| WebP 80 | 29.09 | 20.55 | 35.5 36.8 33.5 | 34.9 36.3 32.6 | 34.3 35.9 32.3 | 17.2 | 2.10 |
| WebP 85 | 36.59 | 26.01 | 37.0 38.5 34.6 | 36.4 38.1 33.7 | 35.9 37.9 33.3 | 18.3 | 2.54 |

| Pass mark | Result |
|---|---|
| 1. Smaller at no more error | **Failed.** The lowest tested WebP quality at or above JPEG 65 in every band is 70, and its file is 12.6% smaller, short of 15%. WebP 60 is 24.3% smaller but 0.2 dB below JPEG 65 in red and 0.1 dB in green (0.1 dB above in blue). The crossing point lies between the two steps tested. |
| 2. Draws in the browser reader | Passed. WebP 60 and 70 drew at the street and whole-quad views with no error. |
| 3. Decode not much slower in the browser | Passed, on a thin sample. Median per block over two rounds of the street view (6 blocks each): JPEG 4.1 to 10.0 ms, WebP 8.8 to 11.6 ms. The run-to-run spread is as large as the difference. |
| 4. Same structure | Passed. |

Recorded: in GDAL, WebP took about 5 times the CPU to encode and 2.4 to 3 times to decode.
JPEG overviews at 65 are 1.6 dB worse than full resolution at level 1 (they hold finer
detail per pixel); at 75 they are 0.6 dB worse; at 85 they are 1.3 dB better. Overviews at
75 add 6.7% to the all-65 file and at 85 add 20.1%. WebP's overviews lose less against
its full resolution (0.7 to 0.8 dB at level 1).

### Decision (Nathan, 2026-11-12)

JPEG, quality 65 at full resolution and 75 for the overview levels. WebP is not adopted.
The four state-years published so far are at quality 85 throughout and stay described
that way in `README.md` until they are converted again; the converter's defaults are
unchanged, and runs at the new setting pass `QUALITY=65` and `OVERVIEW_QUALITY=75`.

### Layout decision (Nathan, 2026-11-12)

Quads as published, plus one overview file per state-year in the state's main UTM zone.
The 10 km tiles and the 100 km file stay as a recorded test, not a product.

## Utah sample at quality 65 with overviews at 75 (set 2026-11-12, before any result)

About 100 Utah 2024 quads (the first ten of each of ten shards of the state manifest),
converted with image v6 into the work bucket, `QUALITY=65 OVERVIEW_QUALITY=75`. Compared
with the same quads' receipts from the published run `ut2024-pub-2` (quality 85).

Pass marks:

1. **Complete and clean.** Every quad has a receipt with no problem recorded (structure,
   overview edge ratio of at least 0.7).
2. **Size.** The sample's output bytes are between 55% and 68% of the same quads'
   published bytes (the Alta quad measured 63%).
3. **Error.** On every quad with a pixel check in both runs, PSNR is at most 3.0 dB below
   the published run's value for that quad.
4. **Speed.** Median megapixels per CPU-second is at least 90% of the published run's.

A failed criterion is recorded as failed.

### Results (2026-11-12)

Run `ut2024-q6575-sample`, image v6, 100 quads, 10 tasks. Summary in
`evidence/utah-2024-q65-75-sample-summary.json`.

| Pass mark | Result |
|---|---|
| 1. Complete and clean | Passed. 100 receipts, no problem recorded; lowest overview edge ratio 0.968. |
| 2. Size | Passed. 2.77 GB, 61.9% of the same quads as published. |
| 3. Error | Passed on the two quads that had a pixel check in both runs (the published run checked one quad in 50): 1.0 to 2.9 dB below the published values. Two quads is a thin basis. |
| 4. Speed | Passed. 14.3 megapixels per CPU-second median, against 11.6 for the same quads in the published run. |

Recorded: PSNR on the 50 quads checked in this run, lowest per band 28.7, 31.7 and 29.2 dB, median 31.8, 33.6 and 31.3 dB.
This is the first cluster run of `OVERVIEW_QUALITY`; receipts carry `quality` 65 and
`overview_quality` 75.

## The four state-years converted again at quality 65 with overviews at 75 (2026-11-12)

Runs `ri2025-pub-3`, `nh2025-pub-3`, `ut2024-pub-3` and `vt2025-pub-2`, image v6, written
over the quality 85 files in the product. No pass marks were written for these runs before
they started, which is a lapse; the hosted checks and the seam check are the ones set
earlier, and the error figures below are held against mark 3 of the Utah sample above.

| | Rhode Island 2025 | New Hampshire 2025 | Utah 2024 | Vermont 2025 (30 cm) |
|---|---|---|---|---|
| Files, none with a problem recorded | 116 | 771 | 6,032 | 812 |
| Bytes | 3,761,529,880 | 30,471,141,998 | 154,217,029,232 | 98,710,651,996 |
| Share of the quality 85 bytes | 62.1% | 64.7% | 61.9% | 66.3% |
| Hosted checks (listing, sampled SHA-256, opened in place, index) | pass | pass | pass | pass |
| Seam check, same four files as before, lowest to highest ratio | 0.986 to 1.044 | 0.998 to 1.033 | 0.975 to 1.030 | 0.991 to 1.044 |
| Tasks, Spot interruptions | 4, 0 | 12, 0 | 55, 7 | 33, 3 |
| Task-hours (quality 85 run) | 0.37 (not recorded) | 2.21 (2.30) | 21.03 (19.56) | 10.67 (10.71) |
| Quads with a pixel check | 12 | 39 | 121 | 41 |
| PSNR median, red, green, blue (dB) | 29.0, 29.0, 27.1 | 28.2, 28.5, 25.3 | 32.6, 34.0, 32.3 | 31.9, 32.9, 28.9 |
| PSNR lowest, red, green, blue (dB) | 26.3, 26.8, 24.7 | 27.0, 27.4, 23.8 | 28.7, 30.8, 28.6 | 30.4, 31.4, 26.3 |
| Quads checked in both runs | 3 | 8 | 121 | 9 |
| Largest drop from quality 85, red, green, blue (dB) | 3.8, 4.8, 3.5 | 3.7, 5.0, 3.2 | 3.4, 3.4, 2.8 | 2.5, 3.5, 2.3 |

**Error against the Utah sample's mark of at most 3.0 dB below quality 85: not met.** Every
state has quads beyond it. The two forested, leaf-on states lose the most: the median drop
in green is 4.4 dB in Rhode Island and 4.6 dB in New Hampshire, against 2.8 dB in Utah and
3.2 dB in Vermont. The Utah sample that the quality decision rested on understated the loss
for forest. Whether this is visible at map scale has not been looked at.

Compute did not change with quality: task-hours are within a few percent of the quality 85
runs, and Utah's rise goes with seven interruptions against three.

The index at `https://data.source.coop/nthh/naip/stac/naip.parquet` was rebuilt from these
four runs' receipts (7,731 rows, 1,388,789 bytes) and the hosted copy has the same SHA-256
as the local one. Summaries, hosted checks and seam checks are in `evidence/*-q65-75-*.json`.

## Colour resolution: JPEG 4:2:0 against 4:4:4 (2026-11-12)

Nathan found the yellow centre line of a road in Zion Canyon faded at quality 65 and still
faded at 85. No pass marks were set before these measurements; they are recorded as found.

- **Cause.** GDAL writes YCbCr JPEG in TIFF with colour at half resolution in both
  directions (TIFF `YCbCrSubSampling` 2, 2) and has no option to change it. On the 21 crops
  of the wipe viewer, colour-only PSNR gains about 1.3 dB from quality 65 to 85, and about
  2.4 dB from keeping quality 65 and storing colour at full resolution, which costs about
  23% more bytes (the size of ordinary quality 75). `evidence/jpeg-subsampling/full-colour.json`,
  ranked spots in `colour-loss.json`.
- **Patch.** GDAL 3.13.1 with a `JPEG_YCBCR_SUBSAMPLING` creation option (GTiff and COG) and a
  `JPEG_YCBCR_SUBSAMPLING_OVERVIEW` configuration option: branch `jpeg-ycbcr-subsampling` of
  `github.com/nthh/gdal`, commit 633b514, built into the local image
  `folia-gdal:3.13.1-jpeg-subsampling`. The first build tagged files 1, 1 while still encoding
  tiles at 2, 2 (the tile compression job did not carry the tag), which GDAL then refused to
  read; the pushed commit fixes that. The image tested is one commit-amend older than the
  pushed commit: the only difference is the position of one entry in the list of known
  configuration options.
- **Two quads, quality 65 with overviews at 75, converted both ways** (`zion.json`,
  `nhkanc.json`; local arm64 container, so speeds are not comparable with the cluster's):

| | Zion `ut_m_3711241_sw` 4:2:0 | 4:4:4 | NH Kancamagus `nh_m_4307105_ne` 4:2:0 | 4:4:4 |
|---|---|---|---|---|
| Bytes | 31,805,053 | 37,852,540 (+19.0%) | 46,396,846 | 57,714,053 (+24.4%) |
| Convert CPU seconds | 5.4 | 9.9 | 4.2 | 8.7 |
| PSNR, all bands (dB) | 32.41 | 33.12 | 25.86 | 26.85 |
| PSNR, colour only (dB) | 39.35 | 41.65 | 33.02 | 36.50 |

- **Readers.** Every level of both 4:4:4 files is tagged 1, 1; both validate as COGs; stock
  GDAL 3.13.1 reads full resolution and all five overviews; the deck.gl demo page draws
  them at zoom 18 and 13 with no error (`browser-subsampling.jsonl`), and the screenshots
  show the expected colours.
- **Not established.** Conversion cost on the cluster (convert CPU roughly doubled here, and
  conversion is one part of task time); browser decode time; GDAL's own test suite has not
  been run on the patch and no test was added for the new option.

### Overview files wait for the national run (Nathan, 2026-11-13)

Asked again with the request counts above (72 requests and 36 files for a 37 km view from
quads alone, against 10 requests and one file with an overview file). Answer: no overview
files for now. They are added after all six waves are converted and verified. The layout
recorded on 2026-11-12 (one file per state-year) has not been built or measured at state
size, and nothing in the product depends on it until then.

## National run, wave one: Alabama 2025, Montana 2025, New Mexico 2024 (2026-11-13)

Runs `al2025-pub-1`, `mt2025-pub-1` and `nm2024-pub-1`, image v6, `QUALITY=65
OVERVIEW_QUALITY=75`, written straight into the product. All three are 30 cm. The marks are the
ones already set: the converter's own checks on every file, and the four hosted checks of
[PUBLISHING.md](PUBLISHING.md). No new mark was written for this wave.

| | Alabama 2025 | Montana 2025 | New Mexico 2024 |
|---|---|---|---|
| Quads with a receipt | 3,477 of 3,477 | 11,745 of 11,745 | 8,027 of 8,027 |
| Quads with a problem recorded | 0 | 0 | 0 |
| Bytes | 434,085,293,314 | 877,093,583,189 | 710,958,023,680 |
| Share of the source bytes | 6.8% | 5.9% | 5.9% |
| Flown | 2025-06-24 to 2025-09-28 | 2025-06-09 to 2025-10-07 | 2024-05-02 to 2024-07-10 |
| Lowest overview edge ratio | 0.886 | 0.756 | 0.921 |
| Quads with a pixel check | 70 | 235 | 161 |
| PSNR median, red, green, blue (dB) | 31.8, 32.2, 28.8 | 34.2, 35.7, 31.4 | 35.9, 38.1, 34.1 |
| PSNR lowest, red, green, blue (dB) | 30.1, 30.8, 25.8 | 27.5, 30.4, 26.4 | 33.0, 35.5, 30.3 |
| Peak memory, MiB | 1,585 | 1,520 | 1,644 |
| Tasks started | 90 | 210 | 172 |
| Task-hours summed over receipts | 47.8 | 123.2 | 107.7 |
| Hosted checks: files listed at their recorded size | 3,477 | 11,745 | 8,027 |
| Hosted checks: files downloaded, hashed and opened in place | 70, all match | 235, all match | 161, all match |
| Hosted checks: index rows equal to receipts | 3,477 | 11,745 | 8,027 |
| Hosted checks | pass | pass | pass |

- The first pass left 751 quads in 22 shards that stopped early; those shards were launched again
  with `--only` and finished. Whether Spot or the one-hour deadline stopped them was not
  established, and the end records were not read (`tasks.with_end_record` is 0 in the summaries).
- The hosted checks were first started at about 01:00 and lost when the machine restarted. The
  results here are from a second run on the same day, from a home connection: 466 files, about
  40 GB downloaded, 1 hour 47 minutes for the longest state.
- Montana's lowest edge ratio, 0.756 on `mt_m_4710610_se_13_030_20250701`, is at the smallest
  overview level only (0.965, 0.897, 0.756 over the last three levels). It is above the
  converter's 0.7 mark. The file was not opened to see what is at that edge. Four other quads
  are between 0.886 and 0.897; every other quad is at 0.9 or above.
- What was billed has not been read. The plan expected about $5.28 for the wave against a
  ceiling of $27.42.
- The index hosted at `stac/naip.parquet` still holds only the first four state-years. The
  per-state index files built from these receipts are local
  (`al-2025-30cm-q6575.parquet` 594,482 bytes, `mt-2025-30cm-q6575.parquet` 1,627,165 bytes,
  `nm-2024-30cm-q6575.parquet` 1,321,212 bytes); uploading them needs the Source Cooperative
  login or a task.
- No seam check was run on these three states.
- Evidence: `evidence/{alabama-2025,montana-2025,new-mexico-2024}-{summary,hosted-checks}.json`.

## Several quads per task: three tests on 32 Idaho 2025 quads (2026-11-13)

An address is billed per task-hour ($0.005), about $7.50 of a national run at one quad per
task. `dispatch.py launch --group 4` starts one task for four shards, and the task definition
`folia-naip-display-pilot-publish-grouped:1` (`task-definition-grouped.json`, the v6 image)
starts one converter per shard. Each test was one 4 vCPU task on shards 0 to 3 of 125 of
Idaho 2025, eight quads each, written to the work bucket under `_test/` and deleted after.
The same quads in `id2025-pub-1` took 1,495 s in all.

| Test | Memory | GDAL_CACHEMAX | Quads done | Same SHA-256 as published | Seconds on quads | Peak per converter |
|---|---|---|---|---|---|---|
| group4-test-1 | 8 GB | default | 27 of 32, one converter killed | 27 of 27 | about 3 times the original per quad | 2.15 GiB |
| group4-test-2 | 16 GB | 205 MB | 32 of 32 | 32 of 32 | 1,307 | 0.91 GiB |
| group4-test-3 | 8 GB | 205 MB | 32 of 32 | 32 of 32 | 3,260 | 0.93 GiB |

- Four converters in 16 GB with the cache held at 205 MB (what a 4 GB task gets by default)
  run at the speed of four separate tasks and write the same bytes. That is the tested
  setting: about $1.90 of addresses for a national run in place of $7.50.
- 8 GB is not enough even though the converters themselves use under 1 GiB each: quads take
  more than twice as long. CPU seconds per quad do not change; the converters wait. Each
  holds two source files of about 1.4 GB on disk, and with 8 GB little of that stays in
  memory. Not measured directly: this is read from the timings, not from disk counters.
- Without GDAL_CACHEMAX, GDAL sizes its cache from the larger task and one converter was
  killed in 8 GB.
- Not tested: more than one task at this size, 60 cm quads, eight converters per task
  (would need more than the default 20 GB of task disk), Spot interruption rates at 4 vCPUs.
- Receipts: `_receipts/group4-test-{1,2,3}/` in the work bucket.

## The 66 quads the edge check refused (2026-11-14)

In the national run the converter refused 66 of 213,524 quads for a darkened overview edge:
54 in Nevada 2024, 9 in California 2024, and one each in Florida 2025, Wyoming 2024 and
North Carolina 2024. In 64 of them the ratio is 0.0 at every level: the last row or column
is black. The check divides the last row by the one before it, so a black source edge reads
the same as the fault it was written for. The Nevada quads ring an area where the source
has no quads at all. Florida (0.665 at the smallest level) and Wyoming (0.628 at level 4,
open water on the bottom edge) are near misses like Ohio's `m_4108132_nw` (0.697, a road
beside the edge, converted at a floor of 0.65 on 2026-11-13).

Decision (Nathan, 2026-11-14): publish them, then verify each.

- Converted with `OVERVIEW_EDGE_FLOOR=0` for the slices that hold them only (45 tasks).
  All 66 have a receipt with no problem recorded.
- Verified from the hosted files with `check_dark_edges.py`: at every overview level the
  last row and the last column are no darker than 85% of the full-resolution pixels they
  cover, less 3 levels. 66 of 66 pass (`evidence/dark-edge-quads.json`). A file with the
  copied-overview fault would fail this, since its edge is half as bright as its pixels.
- Black share of the 64: 22% to 99.9% of the quad.
- Not checked: why each area is black. The source carries it.
- The 0.7 check stays as it is for everything else. It cannot pass a file whose own edge
  is black; such files need this second check.

## National run, all six waves (2026-11-14)

The 45 runs of waves two to six, image v6, `QUALITY=65 OVERVIEW_QUALITY=75`, written straight
into the product, with the three runs of wave one beside them for one view of the whole run.
The marks are the ones already set: the converter's own checks on every file, and the four
hosted checks of [PUBLISHING.md](PUBLISHING.md). The table is written by `record_runs.py` from
each run's summary and hosted-check result.

| Wave | State-year | Size | Quads with a receipt | With a problem | GB | Share of source | Flown | Lowest overview edge ratio | Pixel checks: quads, median PSNR, lowest (dB) | Tasks started, Spot interruptions | Hosted: listed at recorded size | Hosted: hashed and opened | Hosted: index rows equal to receipts | Hosted checks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Alabama 2025 | 30cm | 3,477 of 3,477 | 0 | 434.1 | 6.8% | 2025-06-24 to 2025-09-28 | 0.886 | 70, 30.88, 29.28 | 90, 4 | 3,477 | 70, all match | 3,477 | pass |
| 1 | Montana 2025 | 30cm | 11,745 of 11,745 | 0 | 877.1 | 5.9% | 2025-06-09 to 2025-10-07 | 0.756 | 235, 33.82, 28.46 | 210, 10 | 11,745 | 235, all match | 11,745 | pass |
| 1 | New Mexico 2024 | 30cm | 8,027 of 8,027 | 0 | 711.0 | 5.9% | 2024-05-02 to 2024-07-10 | 0.921 | 161, 36.01, 32.95 | 172, 8 | 8,027 | 161, all match | 8,027 | pass |
| 2 | Idaho 2025 | 30cm | 6,553 of 6,553 | 0 | 612.1 | 6.6% | 2025-05-19 to 2025-09-27 | 0.904 | 132, 32.08, 29.46 | 130, 5 | 6,553 | 132, all match | 6,553 | pass |
| 2 | Kansas 2025 | 30cm | 5,902 of 5,902 | 0 | 379.6 | 5.0% | 2025-05-03 to 2025-05-21 | 0.803 | 119, 34.98, 32.5 | 107, 3 | 5,902 | 30, all match | 5,902 | pass |
| 2 | Ohio 2025 | 60cm | 3,049 of 3,049 | 0 | 62.5 | 5.8% | 2025-06-01 to 2025-07-06 | 0.697 | 61, 31.62, 29.1 | 19, 2 | 3,049 | 21, all match | 3,049 | pass |
| 2 | South Dakota 2025 | 30cm | 5,991 of 5,991 | 0 | 391.0 | 5.2% | 2025-07-08 to 2025-10-10 | 0.823 | 120, 33.92, 30.26 | 107, 5 | 5,991 | 30, all match | 5,991 | pass |
| 2 | Texas 2024 | 60cm | 17,276 of 17,276 | 0 | 488.6 | 6.2% | 2024-05-14 to 2024-11-22 | 0.749 | 346, 33.46, 30.12 | 106, 3 | 17,276 | 87, all match | 17,276 | pass |
| 3 | Florida 2025 | 30cm | 3,806 of 3,806 | 0 | 434.4 | 6.3% | 2025-04-13 to 2025-11-17 | 0.665 | 77, 32.19, 29.45 | 100, 6 | 3,806 | 21, all match | 3,806 | pass |
| 3 | Georgia 2025 | 30cm | 3,913 of 3,913 | 0 | 481.4 | 6.7% | 2025-07-13 to 2025-10-18 | 0.864 | 79, 32.11, 29.69 | 101, 4 | 3,913 | 21, all match | 3,913 | pass |
| 3 | Maine 2025 | 30cm | 2,754 of 2,754 | 0 | 332.3 | 7.6% | 2025-07-04 to 2025-09-20 | 0.885 | 56, 29.84, 28.12 | 65, 5 | 2,754 | 21, all match | 2,754 | pass |
| 3 | Missouri 2024 | 30cm | 5,018 of 5,018 | 0 | 453.5 | 6.1% | 2024-06-25 to 2024-10-16 | 0.819 | 101, 33.3, 29.38 | 108, 7 | 5,018 | 26, all match | 5,018 | pass |
| 3 | Nebraska 2025 | 30cm | 5,635 of 5,635 | 0 | 383.3 | 5.2% | 2025-07-27 to 2025-09-26 | 0.722 | 113, 34.05, 30.24 | 111, 10 | 5,635 | 29, all match | 5,635 | pass |
| 4 | California 2024 | 60cm | 11,042 of 11,042 | 0 | 323.8 | 6.6% | 2024-04-29 to 2024-10-18 | 0.000 | 221, 32.27, 28.73 | 74, 0 | 11,042 | 56, all match | 11,042 | pass |
| 4 | Massachusetts 2025 | 60cm | 744 of 744 | 0 | 23.4 | 7.3% | 2025-07-04 to 2025-09-20 | 0.912 | 15, 29.02, 26.91 | 5, 0 | 744 | 21, all match | 744 | pass |
| 4 | Mississippi 2025 | 30cm | 3,154 of 3,154 | 0 | 364.7 | 6.4% | 2025-06-21 to 2025-09-27 | 0.894 | 64, 32.82, 30.38 | 77, 0 | 3,154 | 21, all match | 3,154 | pass |
| 4 | North Carolina 2025 | 30cm | 3,575 of 3,575 | 0 | 408.5 | 6.6% | 2025-05-24 to 2025-10-14 | 0.929 | 72, 31.57, 27.89 | 85, 0 | 3,575 | 21, all match | 3,575 | pass |
| 4 | North Dakota 2025 | 30cm | 5,711 of 5,711 | 0 | 321.9 | 4.9% | 2025-06-30 to 2025-09-09 | 0.763 | 115, 34.43, 31.37 | 94, 5 | 5,711 | 29, all match | 5,711 | pass |
| 4 | Tennessee 2025 | 30cm | 3,000 of 3,000 | 0 | 335.1 | 6.4% | 2025-06-10 to 2025-10-15 | 0.895 | 60, 31.56, 29.15 | 74, 3 | 3,000 | 20, all match | 3,000 | pass |
| 4 | Virginia 2025 | 30cm | 3,031 of 3,031 | 0 | 240.4 | 5.7% | 2025-04-16 to 2025-08-30 | 0.896 | 61, 36.72, 33.55 | 59, 1 | 3,031 | 21, all match | 3,031 | pass |
| 5 | Arkansas 2025 | 60cm | 3,600 of 3,600 | 0 | 120.5 | 7.1% | 2025-06-26 to 2025-09-07 | 0.871 | 72, 28.15, 25.86 | 24, 1 | 3,600 | 20, all match | 3,600 | pass |
| 5 | Arizona 2025 | 60cm | 7,629 of 7,629 | 0 | 185.3 | 6.2% | 2025-05-26 to 2025-08-30 | 0.798 | 153, 33.38, 28.54 | 41, 1 | 7,629 | 39, all match | 7,629 | pass |
| 5 | Idaho 2024 | 60cm | 80 of 80 | 0 | 2.5 | 7.7% | 2024-08-01 to 2024-08-01 | 0.941 | 2, 30.74, 30.73 | 1, 0 | 80 | 20, all match | 80 | pass |
| 5 | Indiana 2025 | 60cm | 2,688 of 2,688 | 0 | 73.3 | 6.4% | 2025-07-22 to 2025-09-09 | 0.795 | 54, 27.84, 25.42 | 17, 1 | 2,688 | 21, all match | 2,688 | pass |
| 5 | Louisiana 2025 | 60cm | 3,288 of 3,288 | 0 | 111.0 | 7.0% | 2025-05-04 to 2025-09-08 | 0.799 | 66, 28.92, 25.36 | 23, 2 | 3,288 | 21, all match | 3,288 | pass |
| 5 | Michigan 2024 | 60cm | 4,846 of 4,846 | 0 | 134.9 | 7.0% | 2024-07-25 to 2024-10-06 | 0.802 | 97, 29.39, 26.08 | 27, 1 | 4,846 | 25, all match | 4,846 | pass |
| 5 | Minnesota 2025 | 60cm | 6,791 of 6,791 | 0 | 148.1 | 6.3% | 2025-07-01 to 2025-10-08 | 0.815 | 136, 31.2, 27.7 | 32, 0 | 6,791 | 34, all match | 6,791 | pass |
| 5 | North Dakota 2024 | 60cm | 5,689 of 5,689 | 0 | 106.2 | 5.4% | 2024-07-12 to 2024-09-25 | 0.731 | 114, 31.16, 26.83 | 27, 1 | 5,689 | 29, all match | 5,689 | pass |
| 5 | Nebraska 2024 | 60cm | 5,626 of 5,626 | 0 | 98.8 | 4.8% | 2024-07-13 to 2024-09-25 | 0.750 | 113, 34.75, 32.19 | 27, 0 | 5,626 | 29, all match | 5,626 | pass |
| 5 | Nevada 2024 | 60cm | 7,397 of 7,397 | 0 | 195.5 | 6.2% | 2024-05-16 to 2024-10-05 | 0.000 | 148, 32.42, 29.7 | 73, 0 | 7,397 | 37, all match | 7,397 | pass |
| 5 | New York 2024 | 60cm | 3,882 of 3,882 | 0 | 123.9 | 7.6% | 2024-05-24 to 2024-10-22 | 0.892 | 78, 28.53, 26.82 | 24, 1 | 3,882 | 21, all match | 3,882 | pass |
| 5 | Oklahoma 2025 | 60cm | 4,815 of 4,815 | 0 | 102.3 | 5.6% | 2025-04-12 to 2025-10-10 | 0.722 | 97, 33.3, 29.84 | 25, 0 | 4,815 | 25, all match | 4,815 | pass |
| 5 | Oregon 2024 | 60cm | 7,454 of 7,454 | 0 | 185.5 | 6.3% | 2024-06-06 to 2024-10-06 | 0.891 | 150, 32.82, 29.46 | 41, 2 | 7,454 | 38, all match | 7,454 | pass |
| 5 | South Carolina 2025 | 30cm | 2,152 of 2,152 | 0 | 242.8 | 6.5% | 2025-04-16 to 2025-06-24 | 0.887 | 44, 31.74, 29.81 | 51, 0 | 2,152 | 21, all match | 2,152 | pass |
| 5 | Wisconsin 2024 | 60cm | 4,484 of 4,484 | 0 | 116.2 | 6.7% | 2024-08-19 to 2024-10-10 | 0.788 | 90, 32.2, 29.47 | 23, 0 | 4,484 | 23, all match | 4,484 | pass |
| 5 | Wyoming 2024 | 60cm | 7,357 of 7,357 | 0 | 147.1 | 5.5% | 2024-07-11 to 2024-09-09 | 0.628 | 148, 35.31, 29.88 | 38, 1 | 7,357 | 37, all match | 7,357 | pass |
| 6 | Connecticut 2025 | 60cm | 413 of 413 | 0 | 14.0 | 7.6% | 2025-07-04 to 2025-08-09 | 0.952 | 9, 28.38, 27.55 | 3, 0 | 413 | 21, all match | 413 | pass |
| 6 | Iowa 2025 | 60cm | 4,239 of 4,239 | 0 | 63.4 | 4.5% | 2025-07-28 to 2025-09-27 | 0.772 | 85, 33.13, 31.32 | 20, 1 | 4,239 | 22, all match | 4,239 | pass |
| 6 | Illinois 2025 | 60cm | 4,131 of 4,131 | 0 | 76.1 | 5.2% | 2025-07-01 to 2025-09-29 | 0.704 | 83, 32.28, 29.27 | 22, 2 | 4,131 | 21, all match | 4,131 | pass |
| 6 | Indiana 2024 | 60cm | 2,689 of 2,689 | 0 | 53.7 | 5.4% | 2024-06-24 to 2024-09-18 | 0.859 | 54, 34.51, 31.04 | 14, 0 | 2,689 | 21, all match | 2,689 | pass |
| 6 | Kentucky 2024 | 60cm | 2,930 of 2,930 | 0 | 89.4 | 6.8% | 2024-05-19 to 2024-08-30 | 0.917 | 59, 29.19, 26.91 | 18, 0 | 2,930 | 21, all match | 2,930 | pass |
| 6 | Maine 2024 | 30cm | 839 of 839 | 0 | 91.4 | 7.2% | 2024-07-28 to 2024-09-17 | 0.926 | 17, 32.31, 29.59 | 19, 1 | 839 | 21, all match | 839 | pass |
| 6 | Maine 2024 | 60cm | 1 of 1 | 0 | 0.1 | 7.8% | 2024-09-15 to 2024-09-15 | 0.989 | 1, 31.34, 31.34 | 1, 0 | 1 | 1, all match | 1 | pass |
| 6 | Montana 2024 | 60cm | 1,666 of 1,666 | 0 | 45.0 | 6.8% | 2024-07-21 to 2024-10-04 | 0.931 | 34, 31.7, 29.56 | 10, 1 | 1,666 | 21, all match | 1,666 | pass |
| 6 | North Carolina 2024 | 60cm | 3,582 of 3,582 | 0 | 105.8 | 6.8% | 2024-05-02 to 2024-11-21 | 0.000 | 72, 32.44, 29.51 | 23, 1 | 3,582 | 21, all match | 3,582 | pass |
| 6 | New Jersey 2025 | 60cm | 634 of 634 | 0 | 18.3 | 6.8% | 2025-07-04 to 2025-08-09 | 0.936 | 13, 28.41, 26.49 | 4, 0 | 634 | 21, all match | 634 | pass |
| 6 | Pennsylvania 2024 | 60cm | 1,118 of 1,118 | 0 | 24.8 | 6.3% | 2010-06-24 to 2024-10-18 | 0.776 | 23, 35.28, 32.66 | 6, 0 | 1,118 | 21, all match | 1,118 | pass |
| 6 | West Virginia 2024 | 60cm | 101 of 101 | 0 | 3.0 | 7.4% | 2024-07-02 to 2024-08-23 | 0.942 | 3, 32.94, 32.68 | 1, 0 | 101 | 21, all match | 101 | pass |

Totals: 213,524 of 213,524 quads have a receipt and none records a problem; 10.74 TB written
from 175.89 TB of source (6.1%); 4,293 quads had a pixel check; 2,529 tasks were started and 98
ended in a Spot interruption; 1,746 hosted files were hashed and opened in place. With the four
state-years converted before the national run, the product holds 221,255 files, 11.03 TB, which
is every quad in the source listing of 2026-11-10.

- Waves three to six were not started wave by wave. `rolling_launch.py` started each planned
  run as task slots came free under the account's limit on Fargate Spot vCPUs.
- How the hosted samples were read changed during the run. Wave one and Idaho 2025 were read
  from a laptop at every 50th file (466 and 132 files). The other 44 state-years were read by
  one task in us-west-2 (`sample_hosted.py`) at every 200th file and at least 20 per state-year:
  1,148 files, 52.1 GB, in under two minutes, with the listing and index checks run from the
  laptop as before. The in-region reader was first tried on Idaho 2025, where it gave the same
  verdict on the same 132 files as the laptop had.
- Ohio 2025 was first checked with 3,048 files hosted; the row here is a second check with all
  3,049. An earlier laptop check of Kansas 2025 stopped on a GDAL error while the network was
  down and is not a result; South Dakota and Texas had not been checked before this one.
- A lowest edge ratio under 0.7 means quads the converter refused and that were then converted
  with the edge check lowered or off: one in Ohio at a floor of 0.65, and the 66 of the
  section above (California, Nevada, North Carolina, Florida and Wyoming here). Each of the 66
  was settled against its own full-resolution pixels.
- Four files under Pennsylvania 2024 carry a 2010 flight date in their names
  (`m_3907813_SE_18_60_20100624` and three neighbours). The names are the source's; the files
  were converted and are hosted like the rest. What they show was not looked at.
- The end record of every task was read this time. Wave one's summaries were written again
  with them: 4, 10 and 8 of its tasks ended in a Spot interruption, which settles what stopped
  the shards that were launched a second time.
- Task time at the billed Spot rates comes to $27.02 for 1,422 task-hours ($14.43 vCPU, $5.47
  memory, $7.11 public addresses), against a plan of $26.82 for 1,414
  (`evidence/national-task-hours.json`). That is measured time multiplied by rates, not a bill:
  Cost Explorer had not posted the days of the large waves when this was written, and request
  charges are not in it.
- The index at `https://data.source.coop/nthh/naip/stac/naip.parquet` was rebuilt from the
  receipts of all 52 runs with `build_stac_index.py` and written by one task: 221,255 rows,
  one per hosted file, 39,528,190 bytes in 433 row groups. Read back from outside it has the
  SHA-256 of the local file (`204e8b51...4ba5f0`). The 7,731 rows hosted before are unchanged
  in it. Drawn in a map through it: downtown Boise from the Idaho 2025 files at zoom 14.
- The index was replaced later on 2026-11-14 after validate.stac-geoparquet.org reported four
  faults in it: the `bbox` struct's fields were in alphabetical order, there was no `links`
  column, the file had no `stac-geoparquet` metadata, and it carried the `type` column the
  specification says to omit. The replacement has the same 221,255 rows, equal to the first
  upload in every column both have, plus one `derived_from` link per row to the source file and
  the collection in the file's metadata: 40,819,342 bytes, SHA-256 `9b0904ea...1b7ae4`, read
  back from outside. The validator then reports it valid as Parquet, GeoParquet 1.1.0 and
  stac-geoparquet, with one warning kept on purpose: row groups hold 512 rows, not the 50,000
  it suggests, so that a map view reads 3 to 6 of 433 groups.
- No seam check was run on any state of the national run.
- Evidence: `evidence/<state>-<year>-{summary,hosted-checks}.json` for each row (Maine 2024 has
  one pair per pixel size), `evidence/national-task-hours.json`.

## Overview files: test on Rhode Island 2025 and Nevada 2024 (set 2026-11-14, before any result)

One file per state-year that holds the whole state at reduced resolution, so a wide view reads
one file instead of every quad in it. Built from the reduced levels the hosted quads already
hold, not from the source. Written to our own bucket under `_proto/grid-1/overviews/`, not to
the product. Rhode Island 2025 is 116 quads in one UTM zone; Nevada 2024 is 7,397 quads in
two zones (14 in zone 10) with 54 of the black-edged quads of the section above.

**Method** (`overview.py`, one task per file). Each quad's reduced level is read from the
hosted file and its black border, where it has one, is marked as holding no picture
(GDAL's nearblack at 6 grey levels, widened by two pixels). The quads are warped bilinearly
onto one grid and mosaicked, a later quad over an earlier one, and written as a JPEG COG at
quality 75 with 512-pixel blocks, averaged reduced levels and a mask where no quad has a
picture.

**Variants.** Four files per state, because two choices are open (Nathan, 2026-11-14: build
both, then choose):

| Variant | Grid | Finest level | Quad level read |
|---|---|---|---|
| `utm-9.6` | the state's main UTM zone, as decided 2026-11-12 | 9.6 m | 9.6 m |
| `utm-4.8` | the state's main UTM zone | 4.8 m | 4.8 m |
| `web-14` | Web Mercator, standard zoom grid | zoom 14 (9.55 m at the equator, 7.3 m on the ground at 40 degrees north) | 4.8 m |
| `web-15` | Web Mercator, standard zoom grid | zoom 15 (4.78 m at the equator, 3.7 m on the ground at 40 degrees north) | 2.4 m |

Pass marks, for every file:

1. **It is a valid COG with a mask.** GDAL reports `LAYOUT=COG`, JPEG compression, 512-pixel
   blocks and a mask band, and reads the finest and the coarsest level in place.
2. **The file holds the mosaic.** On 200 windows of 512 pixels at the finest level, chosen at
   random among those at least half covered, PSNR between the file and the mosaic before
   encoding is at least 30.0 dB in each band, in every window.
3. **Every quad is in it.** The centre of every quad's footprint is unmasked.
4. **No black border shows.** Inside the footprint of each black-edged quad, pixels that are
   unmasked and at most 8 in all three bands are at most 0.5% of the footprint. The same
   share is recorded for every other quad, without a mark.
5. **A wide view is one file and few requests.** Read through GDAL with anonymous range
   requests, a 1,280 by 800 pixel view of 37 km across and a view of the whole state each
   take at most 10 requests.

Recorded without a pass mark: file size; task time, peak memory and disk; requests and bytes
read from the quads; masked share inside quad footprints; how each variant draws in the
browser reader and whether the mask shows as transparent there; and, for `utm-9.6`, PSNR
against the 9.6 m level of `utm-4.8` (the same pixels made by averaging instead of by
reading the quads' own 9.6 m level). A failed criterion is recorded as failed.

### Results (2026-11-14)

Result files are in `evidence/overviews/`; the table is made by `summarize_overview_results.py`.
Builds named `-fixed` were made on the test machine with the corrected builder described
below; every other build ran as one task on Fargate with the first builder. `web-15` for
Nevada was interrupted twice by Spot and was not run again. `nv-2024-z10` and `nv-2024-z11`
are Nevada split by UTM zone, each file in its own zone, which is the layout agreed for a
national run (one file per state-year and zone).

| Build | Quads | Pixels | File | Read, copy, write (s) | Own check, lowest dB | Centres masked | Requests, 37 km view and whole file | Against quads: blocks, moved, lowest and median dB |
|---|---|---|---|---|---|---|---|---|
| nv-2024-utm-4.8 | 7,397 | 112,128 by 163,840 | 2,194.5 MB | 257, none, 11112 | 30.02, 30.14, 29.84 (fails) | 71 | 4 and 4 | 6,187, 0, 22.51 and 37.04 |
| nv-2024-utm-9.6 | 7,397 | 56,320 by 81,920 | 530.3 MB | 109, none, 1300 | 32.81, 32.99, 32.68 | 71 | 4 and 4 | 1,334, 0, 25.15 and 37.30 |
| nv-2024-web-14 | 7,397 | 71,168 by 105,472 | 1,019.2 MB | 190, none, 3401 | 29.25, 29.34, 29.14 (fails) | 71 | 4 and 4 | not run |
| nv-2024-z10-utm-9.6-fixed | 14 | 2,048 by 28,160 | 1.7 MB | 3, 2, 1 | 31.58, 31.80, 31.35 | 0 | not run | 335, 0, 29.67 and 39.90 |
| nv-2024-z10-utm-9.6 | 14 | 2,048 by 28,160 | 1.7 MB | 4, none, 20 | 27.12, 27.32, 27.21 (fails) | 0 | not run | 335, 0, 27.53 and 38.30 |
| nv-2024-z11-utm-9.6 | 7,383 | 55,808 by 81,920 | 529.2 MB | 136, none, 2669 | 32.44, 32.81, 32.15 | 71 | not run | 1,326, 0, 25.15 and 37.46 |
| ri-2025-utm-4.8 | 116 | 15,872 by 22,528 | 44.4 MB | 6, none, 153 | 31.23, 31.31, 30.43 | 0 | 4 and 4 | 5,280, 20, 25.37 and 32.82 |
| ri-2025-utm-9.6-fixed | 116 | 8,192 by 11,776 | 10.5 MB | 23, 13, 2 | 33.66, 34.10, 32.72 | 0 | not run | 1,200, 0, 30.02 and 36.19 |
| ri-2025-utm-9.6 | 116 | 8,192 by 11,776 | 10.6 MB | 2, none, 9 | 32.59, 32.96, 31.81 | 0 | 3 and 4 | 1,200, 3, 23.83 and 33.46 |
| ri-2025-web-14 | 116 | 10,752 by 14,848 | 22.0 MB | 3, none, 15 | 30.35, 30.48, 28.86 (fails) | 0 | 4 and 4 | not run |
| ri-2025-web-15 | 116 | 20,992 by 29,696 | 93.9 MB | 14, none, 154 | 29.57, 29.61, 27.55 (fails) | 0 | 4 and 4 | not run |

Against the pass marks:

1. **Valid COG with a mask: passed** by every file.
2. **The file holds the mosaic (30 dB in every window): passed** by both `utm-9.6` files, the
   zone 11 file, Rhode Island `utm-4.8` and both `-fixed` files. **Failed** by every Web
   Mercator file (27.55 to 29.34 dB lowest), by Nevada `utm-4.8` (blue 29.84 dB) and, as first
   recorded, by the zone 10 file (27.12 dB). The zone 10 figure was a fault in the check, not
   the file: see below.
3. **Every quad is in it: failed** by every Nevada file that holds zone 11. 71 quad centres
   are masked, the same 71 in each. 70 are quads that are black in the hosted file itself,
   in one block at 36 to 37 north, 115 to 117 west. The other, `nv_m_3611602_ne`, is half
   black with its centre near the edge of the picture; it has not been looked at further.
4. **No black border shows: passed.** The highest black share inside a black-edged quad is
   0.003%.
5. **A wide view is few requests: passed** by every file measured (3 or 4 requests a view).

Recorded without a mark:

- **Web Mercator costs twice the bytes for a lower score** (Nevada 1,019 MB at zoom 14
  against 530 MB at 9.6 m), so the UTM grid stands.
- **Reading the quads' own 9.6 m level against averaging the 4.8 m file down**: median
  29.92, 30.13, 29.59 dB between the two in Rhode Island and 34.76, 35.14, 34.34 dB in
  Nevada, with the first builder. The two were not placed alike (below), so these
  figures understate how well they agree.
- **Writing is the slow step and grows faster than the file**: 1,300 to 2,669 s for Nevada at
  9.6 m, 3,401 s for zoom 14 and 11,112 s for 4.8 m, on 8 vCPU. Peak memory stayed under 3 GB.
- Not done: pictures of the files side by side, and how they draw in the browser reader.

### Three faults found on 2026-11-14, and the corrected builder

Looking for why the 14-quad zone 10 file scored 27.12 dB turned up three separate faults.
All three were invisible to mark 2, which compares a file with the mosaic it was read from.

1. **The check read its reference on several threads and got moved pixels.** With
   `GDAL_NUM_THREADS=ALL_CPUS`, GDAL 3.13.1 returned 660,635 of the zone 10 mosaic's pixels
   (1.1%) differently from a one-thread read, and the same ones every time: whole strips one
   pixel east or west of where they belong. A one-thread read is identical to an independent
   one-thread reprojection of the same quads. Read with one thread, the first zone 10 file
   scores 32.38, 32.57, 32.12 dB lowest, which passes.
2. **A threaded write from the lazy mosaic moves blocks.** Writing the COG straight from the
   mosaic with 4 or more threads left 23 of the zone 10 file's 220 blocks one pixel out of
   place, the same blocks every time. One thread, or any number of threads without reduced
   levels, or any number of threads from a plain local copy of the mosaic, all write the same
   correct file. The first zone 10 file escaped only because its threaded write failed
   outright and was repeated on one thread.
3. **Quads were placed on the nearest pixel before being resampled.** The first builder made
   a plain mosaic of each zone on a grid that is no quad's own, which puts each quad up to
   three quarters of a pixel east or west of its place (measured per block in two Rhode
   Island quads and one Nevada quad: 0.25 to 0.75 pixel, one sign across a quad).

`check_overview_against_quads.py` was written to see these: for a seeded sample of quads it
reads the quad's own reduced level from the hosted file, puts it on the overview file's grid
with one thread, and compares 128 pixel blocks, recording any block that agrees better moved
by one pixel. It finds none in the one-thread zone 10 file and 27 of 335 in an all-thread
copy of the same mosaic.

- **The large Nevada files show no moved block** in 59 sampled quads each (1,326, 1,334 and
  6,187 blocks), so fault 2 is not seen in them. Fault 3 is in all of them.
- **Rhode Island, first builder**: 3 of 1,200 blocks at 9.6 m and 20 of 5,280 at 4.8 m agree
  better moved, all from fault 3.

The corrected builder (`overview.py`, commit a5fabd1) places each quad once, bilinearly,
straight onto the target grid when the file is in the quad's own zone; reprojects other
zones on one thread; reads on one thread; and writes the COG from a plain local copy of the
mosaic. Rebuilt on the test machine:

- **Zone 10, 14 quads**: identical, pixel for pixel, to a one-thread write of the same
  mosaic; no moved block; own check 31.58, 31.80, 31.35 dB lowest.
- **Rhode Island 9.6 m**: no moved block; against the hosted quads the lowest block rises
  from 23.83 to 30.02 dB and the median from 33.46 to 36.19 dB.

Pass mark added for every later build, set after these results: no sampled block agrees
better moved by one pixel. The Nevada files and Rhode Island 4.8 m have not been rebuilt
with the corrected builder; the choice of finest level waits for that.

## JPEG XL against JPEG and WebP (set 2026-11-14, before any result)

A small local test, to decide whether JPEG XL is worth taking further. Nothing is converted
or published. Two quads whose lossless sources are on the test machine: Zion
(`ut_m_3711241_sw`, the quad with the faded road centre line) and New Hampshire Kancamagus
(`nh_m_4307105_ne`, forest). Built as COGs with GDAL 3.13.3 from conda-forge (libjxl 0.13),
one thread, 512 px blocks, averaged overviews:

- JPEG 65 with overviews at 75, colour at half resolution (what is published);
- WebP 50 and 65;
- JPEG XL, lossy, at distance 1.0, 1.5, 2.0, 2.5, 3.0 and 4.0 (effort 5), overviews at the
  same distance; and distance 2.0 again at effort 3 and 7, for encode time.

The full-colour JPEG 65 file from the colour resolution test is measured again with the same
code, not rebuilt. Reference for every level: a lossless COG of the same quad with the same
averaged overviews.

Pass marks for taking JPEG XL further:

1. **Smaller with no more error and full colour.** Take the largest distance tested whose
   full-resolution PSNR is at least JPEG 65's in every band and whose colour-only PSNR (Cb,
   Cr) is at least the full-colour JPEG 65 file's. Its file is at least 15% smaller than the
   published-settings JPEG file.
2. **Same structure.** `LAYOUT=COG`, 512 px blocks, five overview levels.

Recorded without a pass mark: bytes and PSNR per level, encode and decode CPU seconds, and
which readers open the file: Homebrew GDAL 3.13.1, the conda-forge GDAL, QGIS 4.2.1, Chrome
decoding one tile taken out of the file, and the explorer's TIFF reader. A failed criterion
is recorded as failed.

## JPEG 2000, HTJ2K and AVIF against the same two quads (set 2026-11-14, before any result)

Added to the test above at Nathan's request, on the same two quads, the same machine and one
thread. Set after the JPEG XL results were in and before any of these files was built. None of
the three is a GeoTIFF compression, so these files are not COGs.

- **JPEG 2000** (OpenJPEG through GDAL's `JP2OpenJPEG`): lossy 9/7 wavelet, 1024 px tiles, six
  resolutions (the same five reduced sizes as the COG), `RPCL` order, TLM and PLT markers, at
  `QUALITY` 4, 6, 8, 10, 12 and 15 (the file as a percentage of the uncompressed size).
- **HTJ2K** (OpenJPH `ojph_compress`): the same tiles, resolutions and order, at quantisation
  step 0.02, 0.03, 0.05 and 0.08. Read back through GDAL.
- **AVIF** (GDAL's `AVIF` driver, AOM codec, speed 6): the whole quad as one image with no
  reduced levels, full colour at quality 50, 60 and 70, and half-resolution colour at 60. This
  measures the codec only.
- **JPEG XL with finer overviews**, added because the first JPEG XL builds gave their reduced
  levels the same distance as full resolution while the published JPEG gives its own a higher
  quality: distance 2.5 with overviews at 1.5, and 3.0 with overviews at 2.0
  (`JXL_DISTANCE_OVERVIEW`).

Pass marks:

1. **JPEG 2000 and HTJ2K, smaller with no more error and full colour.** The same rule as
   JPEG XL mark 1: the smallest build whose full-resolution PSNR is at least JPEG 65's in
   every band and whose colour-only PSNR is at least the full-colour JPEG 65 file's is at
   least 15% smaller than the published-settings JPEG file.
2. **JPEG 2000 and HTJ2K, views by range request.** Read through GDAL over HTTP from a server
   that counts requests, a 1024 px window at full resolution and the whole quad at one
   sixteenth each take at most 10 requests, and the whole-quad view transfers at most twice
   the bytes the published JPEG COG does for the same view.
3. **AVIF, codec only.** The same rule as mark 1, against the bytes of the published JPEG's
   full-resolution level alone, since the AVIF file holds no reduced levels.
4. **JPEG XL with finer overviews.** A build is at least 15% smaller than the published JPEG
   file with PSNR at least the published JPEG's in every band at every level.

Recorded without a pass mark: PSNR at each reduced level (a JPEG 2000 reduced level is the
wavelet's low-pass image, not an average, and its size can differ by a pixel, so it is
compared over the shared area and reads lower against an averaged reference for reasons other
than compression error), encode and decode CPU seconds, and the same two views for the
published JPEG, WebP 65, JPEG XL and AVIF files. A failed criterion is recorded as failed.
