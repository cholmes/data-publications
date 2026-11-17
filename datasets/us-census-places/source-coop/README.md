# US Census counties, places and county subdivisions, 2023 cartographic boundaries

**Locally generated metadata:** product creation, object uploads, and hosting checks have separate execution receipts.

- Dataset: `us-census-places` (US Census counties, places and county subdivisions, 2023 cartographic boundaries)
- Product ID: `us-census-places`
- Local publication status: `prepared`
- Local readiness: `prepared`
- Owner: `nthh` (confirmed)
- Canonical publication review stage: `not recorded`
- Creation readiness: `true`
- Hosted: `false`

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

No versioned display package is recorded.

## Limitations

- Generalised boundaries for mapping at 1:500,000, not legal boundaries. The TIGER/Line files are the fuller source.
- Census designated places, Puerto Rico and the island areas carry no population estimate.
- Coordinates are NAD83 (EPSG:4269) and are not transformed.
- The display tiles draw only county subdivisions that are active governments; all of them are in the GeoParquet.

## Source Cooperative route

Planned source proxy: `s3://nthh/us-census-places`. Check separate creation and hosting receipts for current state.
