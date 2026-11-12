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
