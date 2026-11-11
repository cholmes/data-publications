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
