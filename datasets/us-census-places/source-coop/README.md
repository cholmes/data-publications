# US Census counties, places and county subdivisions, 2023 cartographic boundaries

**Locally generated metadata:** product creation, object uploads, and hosting checks have separate execution receipts.

- Dataset: `us-census-places` (US Census counties, places and county subdivisions, 2023 cartographic boundaries)
- Product ID: `us-census-places`
- Local publication status: `published`
- Local readiness: `prepared`
- Owner: `nthh` (confirmed)
- Canonical publication review stage: `not recorded`
- Creation readiness: `true`
- Hosted: `true`

## Summary

Shore-clipped outlines of US counties, cities and other places, and county subdivisions, from the Census Bureau's 2023 cartographic boundary files, as GeoParquet with government status and 2023 population estimates added, and a display package of outline tiles and a names index for choosing places on a map.

The proposed Source Cooperative maintainer is separate from the immutable release package metadata; this draft does not change existing producer or converter credits.

## Credits and license

- Producer attribution: Source: US Census Bureau, 2023 cartographic boundary files, gazetteer files and vintage 2023 population estimates.
- License note: US Government work in the public domain. The Census Bureau asks to be cited as the source. These files are a format conversion, not a Census Bureau product.
- Temporal scope: Boundaries as of 1 January 2023. Population estimates are for 1 July 2023.

## Sources and DOI references

- [Host: nthh](https://github.com/nthh/data-publications)
- [Producer: US Census Bureau](https://www.census.gov/)
- [License terms](https://www.census.gov/about/policies/citation.html)
- [Original download](https://www2.census.gov/geo/tiger/GENZ2023/shp/)

## Related datasets

- [Census TIGER/Line 2024 counties and places (cboettig/census)](https://source.coop/cboettig/census)
- [HIFLD archive with Census TIGER 2024 counties, places and county subdivisions (seerai/hifld)](https://source.coop/seerai/hifld)

## Versioned metadata supplements

No separate metadata supplements are recorded.

## Snapshot assets

- `counties`: Counties and county equivalents (application/vnd.apache.parquet)
- `counties_fields`: counties field dictionary (application/json)
- `county-subdivisions`: County subdivisions (application/vnd.apache.parquet)
- `county-subdivisions_fields`: county-subdivisions field dictionary (application/json)
- `places`: Incorporated places and census designated places (application/vnd.apache.parquet)
- `places_fields`: places field dictionary (application/json)
- `support-1`: Pinned Census inputs: address, size and SHA-256 (application/json)
- `support-2`: Build commit, tool versions and output facts (application/json)
- `support-3`: Checks written before the first build (text/markdown)
- `thumbnail`: Sampled display-only overview; not an analytic asset (image/png)

## Versioned display package

- [Display manifest](display/cb2023-display-r3/manifest.json) (SHA-256 `b6e7c08220ab117cc242b4324c447681e893fc8fa4ab447f7e544bcf14600164`)
- [Counties PMTiles](display/cb2023-display-r3/assets/census_counties.pmtiles) (23766772 bytes; SHA-256 `23e2e5abf8a7cc3c94e81c5d345adbf5d2a893c21e7c0467a885a1070b925ac2`)
  - [Map style](display/cb2023-display-r3/styles/census_counties.json)
- [Cities, towns and census designated places PMTiles](display/cb2023-display-r3/assets/census_places.pmtiles) (37275676 bytes; SHA-256 `79520f8f8bb67d09b6e443539865494bf80d02049dcd9a2a8869544db987cadf`)
  - [Map style](display/cb2023-display-r3/styles/census_places.json)
- [Governing townships and towns PMTiles](display/cb2023-display-r3/assets/census_towns.pmtiles) (20349807 bytes; SHA-256 `a56dc97780b3e0d71393f211a1025e8e2fffbbdc95432164bf344f6c3e3a2be5`)
  - [Map style](display/cb2023-display-r3/styles/census_towns.json)

## Limitations

- Generalised boundaries for mapping at 1:500,000, not legal boundaries. The TIGER/Line files are the fuller source.
- Census designated places, Puerto Rico and the island areas carry no population estimate.
- Coordinates are NAD83 (EPSG:4269) and are not transformed.
- The display tiles draw only county subdivisions that are active governments; all of them are in the GeoParquet.

## Source Cooperative route

Hosted product: `s3://nthh/us-census-places`. The published release is bound to a checksum-verified hosting report.
