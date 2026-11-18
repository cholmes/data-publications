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

## Addendum for r4 (2026-11-17 UTC, written after r3's result and before the r4 build)

`index-20261116-r3` failed check 7 only and is kept in `releases/index-20261116-r3-failed/`. Its
overview index is byte-identical to the hosted file; its quad index differs from the hosted one
only in the collection record's first date (2021-06-16, the earliest row; hosted 2010-06-24),
and checks 1a, 1b, 1c, 3, 4, 5, 6, 8 and 9 passed.

**Check 7, the corrected pattern was too narrow.** 12,647 rows failed: 7,629 Arizona 2025 names
with upper-case quarters (`_NE_`) and 5,018 Missouri 2024 names with upper-case quarters and a
two-digit resolution (`_15_30_`), as the source names them. Every one is dated by its flight
date. The pattern now accepts either case for the quarter and two or three digits for the
resolution. Nothing else changes; r4 is built again from the commit that holds this addendum.

## Addendum for r5 (2026-11-17 UTC, written after r4's result and before the r5 build)

`index-20261116-r4` passed checks 1a, 1b, 1c and 2 to 9 (reports in
`releases/index-20261116-r4-failed/`) and failed check 10: the shared packager refuses a
GeoParquet file whose geometry column does not state its CRS. Both index files leave `crs` out,
which GeoParquet reads as OGC:CRS84, but the packager wants it written.

For r5 both builders write the CRS as the PROJJSON of OGC:CRS84 (`crs84.projjson`), and nothing
else changes. Both files therefore differ from the hosted ones in their `geo` metadata, and both
hosted files are to be replaced (each on Nathan's go). Checks 1b and 1c now compare `geo` without
its `crs`, and require the release's `crs` to carry the id OGC:CRS84. The other marks are
unchanged.

## Addendum for r6 (2026-11-17 UTC, written after r5 was published and before any r6 build)

`index-20261116-r5` passed every check and is the hosted release. r6 makes the index open in
QGIS and GDAL as one mosaic, through GDAL's tile index driver (GTI), and puts the product's new
name in the files. The intended differences from the hosted r5 files are written in
`releases/index-20261117-r6/changes.json` before the build, and are these only:

- Both files gain a column, `naip:gti_location`: the file's address relative to `stac/`
  (`../<state>/<year>/...tif`, `../overviews/<name>.tif`). `assets.image.href` is unchanged.
- The collection records in the `stac-geoparquet` metadata take the name NAIP visualization COGs
  (title of both, and the overview collection's description where it named the old one).
- The release adds two GTI files, `naip.gti` and `naip-overviews.gti`, copied from `gti/`.

Checks 1b and 1c compare with the hosted r5 files with those changes made; anything else that
differs fails them. Check 9 adds two fault cases (a location naming another file, a location made
absolute), which check 11 must reject. New checks:

11. **GTI locations and files.** In both files every row's `naip:gti_location` is relative, and
    resolved against `https://data.source.coop/nthh/naip/stac/` it is the row's `href`. `naip.gti`
    names `naip.parquet` and the location column, has red, green, blue and alpha bands, and every
    overview level opens `naip-overviews.gti`, which names `naip-overviews.parquet` the same way.
12. **Opens in GDAL as QGIS 4.2.1 would.** With GDAL 3.12.4 (`~/.cache/folia/envs/naip-index`),
    the release's `naip.gti` opened through `/vsicurl/` from a loopback server that serves the
    release's four files under `/nthh/naip/stac/` and sends every other path to
    `data.source.coop`: the Alta window [-111.632, 40.585, -111.618, 40.596] read at full
    resolution and the whole of Utah read at about 600 m both give a picture (mean of band 1
    between 60 and 200, alpha not all zero), every request for an imagery file is a byte range,
    and no index file is read whole.

Check 1 (bytes equal the hosted files) does not apply to r6: its files are meant to differ. Check
2 (clean checkout gives the same bytes) and checks 3 to 10 are unchanged.

### Amendment to check 12 (written after its first run, before the second)

The first run (`check-gti-open-r6-1.json`, kept) failed before reading anything: the
`naip-index` environment's GDAL 3.12.4 has no Parquet driver. Check 12 now runs in the Python
that ships inside QGIS 4.2.1, whose GDAL 3.12.4 has the Parquet and GTI drivers; that is the
GDAL a QGIS user opens the file with. The pass marks are unchanged.

The second run (`check-gti-open-r6-2.json`, kept) also failed before reading: started outside the
app, QGIS's Python did not find PROJ's database. The third run sets `PROJ_DATA` and `GDAL_DATA` to
the app's own folders, as QGIS does when it starts. Nothing else changes.

The third run (`check-gti-open-r6-3.json`, kept) passed, but its count of index bytes per read
included HEAD requests at the file's full size (47.5 MB for Alta). Counted as GET bytes, the Alta
read takes about 1.5 MB of the quad index: the first 16 KiB, the footer, and one 1.36 MB range.
The fourth run counts GET bytes only, records every index request, and adds a mark: neither read
takes more than 8 MiB of the index files.

### Amendment to checks 1b and 1c (written after the first r6 check, before the second)

The first check of r6 (`check-r6-1.json`, kept) failed 1b and 1c on `geo_equal` alone; every
value, the schema and the collection records matched with the stated changes made. The
comparison left out `crs` on the release's side only, as written for r5, whose hosted
predecessor had none; hosted r5 has it. Both files' `geo` metadata is byte-identical to hosted
r5's. The comparison now leaves `crs` out on both sides, and the release's `crs` must still be
OGC:CRS84.

## Addendum for r7 (2026-11-17 UTC, written after r6 was hosted and before any r7 build)

QGIS 4.2.1 froze when the hosted r6 `naip.gti` was added as a layer. Adding a layer makes QGIS
take approximate statistics and draw the whole extent; GDAL takes both from the coarsest overview,
which in r6 was the national file at 0.00256 degrees (23,125 x 10,438 pixels), so one band's
statistics fetched 29 MB and warped 241 million pixels (22 s). r7 adds four coarser overview levels
of the national file (0.00512, 0.01024, 0.02048 and 0.04096 degrees, down to 1,445 x 652 pixels).
Nothing else changes: the two index files are to be byte-identical to hosted r6, and
`releases/index-20261117-r7/changes.json` states no changes against them.

Check 11 now runs whenever the index has the `naip:gti_location` column, not only when the column
is new, and so do its two fault cases. Check 12 adds a third step that does what QGIS does on adding
the layer (approximate statistics of band 1, then a 1,000-pixel draw of the whole extent) and must
fetch no more than 8 MiB in all. Run on the r6 files it fails (28.5 MB fetched;
`releases/index-20261117-r7/check-gti-open-on-r6.json`).

Before any r7 check: a QGIS view also took several seconds. Measured with QGIS's GDAL, a first view
of a new area is about 25 to 29 requests in sequence at about 0.25 s each; without
`GDAL_DISABLE_READDIR_ON_OPEN`, which QGIS does not set, GDAL also asks for side files of each quad
(176 404s for one Alta view, 20 s instead of 6 s). The address `/vsicurl?empty_dir=yes&url=...`
stops that with no setting, so the README gives that address. (`gti/naip.gti` itself cannot carry
it: it is an option of the address the file is opened with.) The r7 files are those built at
d88994f; nothing that goes into them changes.

## Addendum for r8 (2026-11-18 UTC, written before the r8 package is made)

r7's two XML tile index files, `naip.gti` and `naip-overviews.gti`, are dropped. Through GDAL 3.12.3
and later they leave out about a quarter of the quarter quads at full resolution, with no warning:
GDAL skips a reprojected file whose footprint is the reprojection of its four corners. The tile index
offered to QGIS and GDAL users is now the FlatGeobuf pair at `stac/naip.gti.fgb` and
`stac/naip-overviews.gti.fgb`, built from the two index files by `build_gti_fgb.py` and checked by
`check_gti_fgb.py`. The FlatGeobuf files are not part of the package; they sit beside it at `stac/`
like the imagery.

`index-20261118-r8` is a new package of r7's index files, not a rebuild. Its two files are the bytes
built at d88994f and hosted at `stac/` since r7 (the SHA-256 in r7's `source-fidelity.json`), so r7's
build manifest, validator report (checks 1b to 9 and 11), source-fidelity and clean-rebuild reports
apply to them unchanged and are reused, not run again. `releases/index-20261118-r8/changes.json` states
no changes against hosted r7. What differs is package metadata only:

- The package no longer holds `metadata/gti/naip.gti` or `metadata/gti/naip-overviews.gti`, nor r7's
  check 12 reports, which opened them.
- The two asset descriptions and the package description name the FlatGeobuf pair where they named
  `stac/naip.gti`; the `naip:gti_location` column is unchanged and is the pair's location field.
- `build_index_release.py` no longer copies the XML files, and check 11 tests the location column
  only.

Checks for r8:

1. **Same bytes.** Both package files equal r7's by SHA-256 and size, and the hosted `stac/` files
   read anonymously have that SHA-256.
12. **Opens in GDAL as QGIS 4.2.1 would, replacing r7's check 12.** With the GDAL inside QGIS 4.2.1
    (3.12.4), the hosted `GTI:/vsicurl/https://data.source.coop/nthh/naip/stac/naip.gti.fgb`: the Alta
    window read at full resolution and the whole of Utah at about 600 m both give a picture (mean of
    band 1 between 60 and 200, alpha not all zero), every imagery request is a byte range, no index
    file is read whole, neither read takes more than 8 MiB of the index files, and the add-layer step
    (approximate statistics of band 1, then a 1,000-pixel draw of the whole extent) fetches no more
    than 8 MiB in all. Every address in the FlatGeobuf files is absolute, so this check opens the
    hosted files and has no loopback copy.
13. **The FlatGeobuf pair matches the index.** `check_gti_fgb.py` passes on the hosted pair against
    the package's two files, and `build_gti_fgb.py` run on them gives the hosted pair byte for byte.
10. **Shared packager.** As before.

The hosted checks of the `stac/` files (anonymous access, checksums, ranges, CORS, subset query,
catalogue links, explorer render) are run again for r8's flat layout, which lists the four `stac/`
files of the package and no XML tile index. After r8 is bound, `stac/naip.gti` and
`stac/naip-overviews.gti` are deleted from Source (Nathan's go of 2026-11-18); local copies are kept
outside the repository.
