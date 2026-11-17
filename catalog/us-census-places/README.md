# US Census counties, places and county subdivisions, 2023 cartographic boundaries

The 2023 Census cartographic boundary files for counties, places and county subdivisions as three GeoParquet files. Every source row and field and the geometry GDAL decodes are kept, in NAD83 (EPSG:4269). Added columns: source_row, gaz_funcstat (functional status from the 2023 gazetteer), popest_2023 (1 July 2023 estimate) and bbox. Rows follow a Hilbert curve. These are boundaries generalised for mapping at 1:500,000, as of 1 January 2023, not legal boundaries.

License: other.

Immutable package: https://data.source.coop/nthh/us-census-places/releases/cb2023-r1/

Catalog preview: County boundaries of the lower 48 from the published display tiles. Display only; use GeoParquet for analysis.

Source producers: US Census Bureau

Source provenance: https://www2.census.gov/geo/tiger/GENZ2023/shp/
Original describedby notes: https://data.source.coop/nthh/us-census-places/releases/cb2023-r1/README.md
Original agents notes: https://data.source.coop/nthh/us-census-places/releases/cb2023-r1/AGENTS.md

Canonical publication limits:

- Hosted on Source Cooperative as an unlisted product since 2026-11-16. The hosted
  checks passed on 2026-11-17 (UTC); they check the hosted copy against the package,
  not the accuracy of the Census boundaries.
- The browser part of the hosted checks used a check written for this dataset (hosted_browser_check.mjs),
  not the shared hosted viewer, and did not read the GeoParquet in a browser.
- The first display build, r1, failed three checks and is kept as failed evidence.
  r2 passed and was replaced by r3, which differs only in its styles.
