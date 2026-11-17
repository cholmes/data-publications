# NAIP stac/ files: hosted checks

Written on 2026-11-17 (UTC) before any of these checks was run, after the four files were put in
place by `replace-run-1` (plan `0b934d05…`). The files are `stac/naip.parquet`,
`stac/naip-overviews.parquet`, `stac/naip.fields.json` and `stac/naip-overviews.fields.json` in
`nthh/naip`, and must be the bytes of index release `index-20261116-r5`. Each check is passed or
failed as written; a failure is kept and blocks the published status.

1. **anonymous_access.** Each file answers an unsigned GET through `data.source.coop` with 200.
2. **asset_checksums.** The full bytes of each file read that way have the size and SHA-256 of
   the release. (`replace-run-1` read each back in full; this is a fresh read.)
3. **range_requests.** For each Parquet file, `bytes=0-3` and the last 8 bytes answer 206 with
   the right `Content-Range` and length, and both read `PAR1` where Parquet puts it. For each JSON
   file, `bytes=0-0` answers 206.
4. **cors.** A GET with an `Origin` header returns `Access-Control-Allow-Origin` of `*` or that
   origin, and `Access-Control-Expose-Headers` of `*` or a list holding `Content-Range`.
5. **subset_query.** DuckDB reads the hosted quad index over HTTP for the window
   [-111.70, 40.50, -111.50, 40.65] (Alta, Utah) using the `bbox` columns, and the sorted ids equal
   those from the local release file with the same query; at least one row must match. The same
   for the overview index with the window of the whole of Utah [-114.1, 36.9, -109.0, 42.1]. The
   hosted quad index's row count is 245,554.
6. **catalog_links.** Every `https://data.source.coop/` address in the generated NAIP catalogue
   collection answers 200 to an unsigned HEAD. Every `raw.githubusercontent.com` address points
   to a file that exists at the named commit with the recorded SHA-256 in this repository; those
   addresses are read over HTTP again after the push, before this record is relied on.
7. **browser_render.** The production explorer (`experiments.folia.sh/stac-geoparquet/`) opened in
   headless Chrome at Alta, Utah, zoom 14, reading in the browser (`execution=browser`): it
   requests `stac/naip.parquet` only with byte ranges, then requests at least one quad COG from
   `data.source.coop/nthh/naip/`, and the page reports no error. Request lists are recorded.
