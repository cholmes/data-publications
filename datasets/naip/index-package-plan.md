# NAIP display copies: packaging the two index files

Recorded on 2026-11-17 (UTC), before any build or check described here was run. The two index
files have been hosted since 2026-11-16 and their SHA-256 is in VALIDATION.md ("Partial years
left out of the indexes"). Nothing in this plan changes a hosted file.

## What the package is

The catalogue's shared packager takes vector GeoParquet. NAIP's imagery is 245,554 COG files and
115 overview files, which are not packaged. What is packaged is the product's two STAC-GeoParquet
index files, which list every one of those files with its address, size, checksum, footprint and
flight date:

| Asset | File | Rows |
| --- | --- | --- |
| `quads` | `naip.parquet` | one per quarter-quad file |
| `overviews` | `naip-overviews.parquet` | one per overview file |

The release is named `index-20261116-r1`. Its two files must be the bytes already hosted at
`stac/naip.parquet` and `stac/naip-overviews.parquet`; the package adds a second, versioned
address for the same bytes and the catalogue record. The imagery itself is checked by the
per-state hosted checks already recorded in VALIDATION.md, not here.

## Inputs

- The receipts of the 62 conversion runs in `evidence/receipt-dirs-62.json` (one JSON per file
  written: path, bytes, SHA-256, source).
- The build results of the overview files (what `overview.py` and `national.py` wrote).
- An anonymous listing of the hosted product, made by the validator.

## Checks and failure criteria

1. **Rebuild equals the hosted bytes.** `build_stac_index.py` and `build_overview_index.py`, run
   from committed code on the inputs above, give files whose SHA-256 equals the hosted files
   read anonymously. If the bytes differ, the check fails; a rebuild with equal rows and values
   but different bytes is reported as that and is still a failure of this check.
2. **Clean checkout.** The same build in a fresh checkout of the commit gives the same bytes.
3. **Accounting against receipts.** The validator is a separate program that does not import
   the builders. It works out the listed state-years itself (every run's state-year, less any
   year holding under 90% of the quads of an older year of the same state). The set of file
   addresses in the quad index equals the set of receipt paths of those state-years: none
   missing, none extra, no address twice.
4. **Size and checksum.** For every quad row, the size and checksum in its `image` asset equal
   the receipt's.
5. **Hosted listing.** Every quad row's file is in an anonymous listing of the product at the
   size the index gives. Every overview row's file likewise.
6. **Footprint.** For every row of both files, the `bbox` columns equal the bounds of the
   footprint the validator decodes from WKB itself (to 1e-9 degrees). For every quad row the
   four corners of `proj:bbox`, taken from the file's own CRS to longitude and latitude, lie
   within 1e-6 degrees of the footprint's outline.
7. **Flight date.** Every quad row's `datetime` is the date at the end of its file name.
8. **Overview index.** Its state rows are exactly the listed state-years' overview files; no
   row belongs to a state-year the quad index leaves out; the national row's quad count equals
   the number of quad rows.
9. **Fault tests.** The validator rejects each of these changes to a copy of the quad index, for
   the stated reason: a row removed; a row duplicated; a size changed; a checksum changed; an
   address changed; a `bbox` value changed; a footprint byte changed; a `datetime` changed; the
   rows of a left-out year added back.
10. **Shared packager.** `scripts/release_tools/package_release.py` passes its gates (STAC,
    Portolan profile, range and CORS on loopback, remote subset query).

Any failed check is kept as failed evidence and blocks the prepared status.

## Limits

- This checks that the index says what the receipts and the hosted listing say. It does not
  look at pixels.
- Checksums are compared with receipts, which the converter wrote. The hosted bytes of a sample
  of files were compared with their receipts in the per-state hosted checks.
- The listing is anonymous and free of charge to us; it is about 250 requests.
- No requester-pays read, no paid run, no upload.

## Addendum for r2 (2026-11-17 UTC, written after r1's result and before any r2 build)

`index-20261116-r1` failed check 1 and is kept in `releases/index-20261116-r1-failed/`. The
rebuilt quad index had the hosted rows and values but not its bytes: the hosted file was written
by a newer pyarrow than the documented command uses, and its collection record still gives the
first flight date of a year the index no longer lists (it was rewritten with `--from-index`,
which keeps the old collection record).

Nathan chose to make the rebuild the release and then replace the hosted files with it. For
`index-20261116-r2`:

- **Environment.** Both builders run in one conda-forge environment whose full package list is
  committed as `datasets/naip/index-env.lock.txt` (`conda list --explicit`): Python 3.12,
  GDAL 3.12.4, pyarrow 21.0.0, pyproj 3.8.0. The overview builder needs GDAL; the hosted
  overview index was built with another GDAL and GEOS, so its outlines may differ in vertices.
- **Inputs of the overview index.** The 116 state results under `overviews/national/results`
  (`*-result.json`) and the national result of the year-rule build
  (`colour-balance/years/national/national-result.json`, 114 sources, 38,077,264 bytes, the
  size of the hosted national file). Their SHA-256 are recorded in the build report.
- **Check 1 is replaced by 1a to 1c.**
  - 1a. Two builds from the same commit give byte-identical files (and check 2 a third, from a
    clean checkout).
  - 1b. Quad index: rows, schema and every value equal the hosted file's; the collection record
    differs only in its temporal extent, whose first date must be the earliest `datetime` of
    the rows.
  - 1c. Overview index: the same ids in the same order, and every column except `geometry`
    equal to the hosted file's; the collection record may differ only in the same way as 1b.
    For `geometry`, each state row's outline must cover the footprint of every quad of its
    state, year and zone (checked by the validator with its own geometry code, allowing 1e-9
    degrees); how far each outline is from the hosted one is reported, not passed or failed.
- **After the files are replaced** (on Nathan's go for that action), the original check 1 is
  run: the hosted files read anonymously have the release's SHA-256.

Checks 3 to 10 are unchanged. A failure keeps r2 as failed evidence, as before.

## Addendum for r3 (2026-11-17 UTC, written after r2's result and before any r3 build)

`index-20261116-r2` failed and is kept in `releases/index-20261116-r2-failed/` (build report and
validator report). Checks 1a, 3, 4, 5, 6, 8 and 9 passed. What failed:

- **1b, a real difference.** 2,452 quad footprints and their `bbox` differ from the hosted
  file's by at most 7.1e-15 degrees. r2's pyproj carried PROJ 9.9.0; the hosted file was made
  with pyproj 3.7.2, which carries PROJ 9.5.1.
- **1c, a real difference.** The overview outlines differ from the hosted ones by up to 0.00099
  degrees, so their `bbox` column differs; every outline still covers all its quads. r2 used GDAL
  3.12.4; the hosted file was made with GDAL 3.13.1 and GEOS 3.14.1.
- **7, the check was wrong.** 14,370 rows failed, all 2023 file names in five states, which carry
  two dates: the day flown, then the day the file was made (README, and VALIDATION.md "A fault in
  the index builders"). Every one is dated by the first. The plan said "the date at the end of its
  file name", which is wrong for those names. Corrected: the date after the resolution field
  (`..._060_<flown>[_<made>]`).

For r3 the environment matches the libraries that wrote the hosted files (Homebrew Python on
2026-11-16): GDAL 3.13.1 and GEOS 3.14.1 from conda-forge, pyarrow 23.0.1, and the PyPI wheel of
pyproj 3.7.2 (PROJ 9.5.1), in the new `index-env.lock.txt`. The pass marks of 1a, 1b, 1c and 3 to
10 are otherwise unchanged. If the files come out byte-identical to the hosted ones apart from the
quad index's collection record, that is reported.
