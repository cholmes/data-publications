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
