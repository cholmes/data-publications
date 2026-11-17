# NAIP stac/ files, index release r6: hosted checks

Written on 2026-11-17 (UTC) before any r6 file was put in place. The files are `stac/naip.parquet`,
`stac/naip-overviews.parquet`, `stac/naip.fields.json`, `stac/naip-overviews.fields.json`,
`stac/naip.gti` and `stac/naip-overviews.gti` in `nthh/naip`, and must be the bytes of index release
`index-20261117-r6` (package `metadata/gti/` for the two .gti files). They are put in place by
`replace-run-1` from `replace-plan.json`: the four existing keys are replaced only if they still
hold the r5 bytes, and the two .gti keys are written only if absent. Each check is passed or failed
as written; a failure is kept and blocks the published status.

Checks 1 to 7 are those of `research/naip-index-20261117/hosting-criteria.md` (with its amendment
to check 7), applied to the six files, with these differences only:

- Check 3: each .gti file, like each JSON file, answers `bytes=0-0` with 206.
- Check 5: the subset query compares with the r6 release files; the quad row count is 245,554.
- Check 7: the range cache must report the r6 size (45,445,261 bytes). The cache trusts a file's
  length and version for 300 s, so check 7 runs at least 10 minutes after the quad index is
  replaced.

8. **gti_open.** With the Python and GDAL 3.12.4 inside QGIS 4.2.1,
   `/vsicurl/https://data.source.coop/nthh/naip/stac/naip.gti` opens, and the Alta window read at
   full resolution and the whole of Utah read at about 600 m each give a picture (band 1 mean
   between 60 and 200, alpha not all zero); every imagery file is read by range and none whole;
   neither read fetches more than 8 MiB of the index files (`datasets/naip/check_gti_open.py
   --hosted`).
