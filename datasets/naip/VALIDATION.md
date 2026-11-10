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

## What this does not establish

- No output file from the Utah pilot has a recorded SHA-256. The converter records one from the
  next run on; the pilot's files need a pass that reads and hashes them.
- 30 cm state-years have not been converted. They have four times the pixels per file.
- The control covers one state and one year. Other states' published files were not compared.
- Overview levels were checked for presence, not compared pixel for pixel with anything.
- Nothing here assesses the imagery itself (cloud, seamlines, colour balance). These files carry
  whatever the source carries.
