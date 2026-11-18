# NAIP stac/ files, index release r8: hosted checks

Written on 2026-11-18 (UTC) before any r8 hosted check. r8 changes no hosted file: its four package
files (the two index files and their field dictionaries) are r7's bytes, already at `stac/`. r8 drops
the two XML GDAL tile index files from the package; they leave the flat layout, and are deleted from
`stac/` once r8 is bound (index-package-plan.md, addendum for r8).

Checks 1 to 7 are those of `research/naip-index-r6-20261117/hosting-criteria.md`, on the four files.
Check 8 is check 12 of the r8 addendum: `check_gti_open.py` opening the hosted
`GTI:/vsicurl/https://data.source.coop/nthh/naip/stac/naip.gti.fgb`
(`datasets/naip/releases/index-20261118-r8/check-gti-open.json`). The quad index is unchanged, so
check 7 does not wait for the range cache.
