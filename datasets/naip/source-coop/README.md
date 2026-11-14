# NAIP display copies, 2024 onward

**Locally generated metadata:** product creation, object uploads, and hosting checks have separate execution receipts.

- Dataset: `naip` (NAIP display copies, 2024 onward)
- Product ID: `naip`
- Local publication status: `candidate`
- Local readiness: `blocked`
- Owner: `nthh` (confirmed)
- Canonical publication review stage: `not recorded`
- Creation readiness: `false`
- Hosted: `false`

## Summary

RGB JPEG Cloud-Optimized GeoTIFFs of USDA NAIP quarter quads for the state-years that the AWS naip-visualization bucket does not hold, converted from the naip-analytic MRF files with the same settings, file names and key layout.

The proposed Source Cooperative maintainer is separate from the immutable release package metadata; this draft does not change existing producer or converter credits.

## Credits and license

- Producer attribution: USDA Farm Production and Conservation Business Center, Geospatial Enterprise Operations (NAIP). Source files from the NAIP on AWS open data buckets maintained by Esri.
- License note: NAIP imagery is produced by the USDA Farm Production and Conservation Business Center and is in the public domain. USDA asks for credit; these files are a format conversion, not a USDA product.
- Temporal scope: One file per quarter quad per state-year. Each file name ends in the date it was flown. Utah 2024 was flown from 2024-06-23 to 2024-08-31.

## Sources and DOI references

No source or DOI links are recorded.

## Related datasets

No related dataset links are recorded.

## Versioned metadata supplements

No separate metadata supplements are recorded.

## Snapshot assets

No release assets are included in this draft.

## Versioned display package

No versioned display package is recorded.

## Limitations

- Display copy only. The files hold red, green and blue as lossy JPEG at quality 65, with overviews at quality 75 and colour at half resolution. The near-infrared band and the lossless pixels stay in s3://naip-analytic.
- Four Pennsylvania 2024 files carry a 2010 flight date in their names, as they do in the source.
- There are no overview files above the quad yet. A view wider than a few quads opens one file per quad.
- Adjacent quarter quads overlap, as they do in the source.

## Source Cooperative route

Planned source proxy: `s3://nthh/naip`. Check separate creation and hosting receipts for current state.

## Blockers

- Source Cooperative account verification is not recorded
- canonical publication status is candidate, not prepared or published
