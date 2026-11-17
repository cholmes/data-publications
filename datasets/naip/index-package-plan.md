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
