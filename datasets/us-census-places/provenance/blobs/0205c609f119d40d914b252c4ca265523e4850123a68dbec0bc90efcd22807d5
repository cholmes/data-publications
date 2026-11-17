# US Census outlines: display package plan

Recorded on 2026-11-16, before the first display build in this repository. A trial tile file with
the same layers was built and drawn earlier the same day outside this repository; the two read
limits below were written before that trial's measurements, and the trial's other results are not
counted here. The marks that are new in this plan are labelled new.

## What the package is

One PMTiles archive and one JSON names index, both made from the released GeoParquet of
`cb2023-r1` and nothing else. They are for drawing and choosing places on a map. The GeoParquet
stays the data.

`assets/outlines.pmtiles`, zooms 3 to 11 for counties and 7 to 11 for the rest:

| Layer | Rows of the release | Geometry |
| --- | --- | --- |
| `census_counties` | every county | outline |
| `census_places` | every place | outline |
| `census_towns` | county subdivisions with `gaz_funcstat` `A` | outline |
| `<layer>_label` | the same rows | one point inside each outline |

An outline carries `id` (GEOID, also the feature id), `name`, `state`, `kind`, `population`
(`popest_2023`, absent when null) and the row's bounds as `xmin`, `ymin`, `xmax`, `ymax`. `kind`
is `county`, `incorporated` (a place with `gaz_funcstat` `A`), `unincorporated` (any other place)
or `township`. A label point carries `id`, `name`, `kind`, `area` (land area in square km, two
decimals) and `population`.

Only governing county subdivisions are drawn. The other 20,181 are statistical or inactive
divisions that few people know by name; they stay in the GeoParquet.

`assets/place-names.json`: `{version, source, kinds, columns, rows}` with one row per drawn
outline, `[name, state, kind index, population or null, xmin, ymin, xmax, ymax]`, bounds rounded
to three decimals, most populous first and then by land area.

Coordinates are NAD83 degrees written into tiles as if WGS84. The two differ by about a metre in
the 50 states, which is below what a tile at zoom 11 can show.

## Build rules

- Tippecanoe v2.79.0 with the binary hash in `datasets/grwl/tippecanoe.lock.json`, two threads.
- No feature is dropped at any zoom and tiny polygons are not merged or removed. Outlines are
  simplified below zoom 11 (factor 15) with shared borders kept together.
- All layers share one maximum zoom, 11.

## Checks and failure criteria

The validator is a separate program that reads the archive itself with its own tile decoder.

1. Inputs: the three GeoParquet files match the SHA-256 in the release manifest.
2. Accounting at zoom 11 (new): the set of `id` values decoded from each outline layer equals the
   set of GEOIDs expected for that layer, with none missing and none extra. Each label layer has
   exactly one point per expected GEOID.
3. Attributes (new): for every decoded outline and label, `name`, `state`, `kind`, `population`,
   `area` and the four bounds equal the values derived from the GeoParquet by GEOID. Bounds must
   match to 1e-6 degrees.
4. Label position (new): every label point lies inside or within 30 m of its source outline.
5. Geometry sample (new): for each outline layer, take the 32 lowest GEOIDs whose bounds cover at
   most 16 tiles at zoom 11. Rebuild each from its zoom 11 tile pieces, clipped to the tile, and
   require a Hausdorff distance to the source outline of at most 30 m in Web Mercator.
6. Read cost, limits written before the trial: the tiles a 1440 x 900 window draws for a whole
   state (counties layer; CO, TX, OH, CA, GA, PA) total at most 600 KB each, and for a whole
   county (places and towns; Boulder CO, Travis TX, Franklin OH, Los Angeles CA, Fulton GA,
   Allegheny PA, Polk IA, Cherry NE) at most 400 KB each. Because every layer shares the tiles,
   the whole tile is counted, not one layer's share.
7. Names index (new): one row per drawn outline, each equal to the values derived from the
   GeoParquet, in the stated order.
8. Repeat build (new): a second build from the same commit gives a byte-identical names index.
   Whether the PMTiles archive is byte-identical is reported; if it is not, the second archive
   must pass checks 2 to 6 itself.
9. Browser (new): served from loopback with range requests, a map draws a state's counties, a
   county's places and towns, lights an outline under the pointer and reads its name, with no page
   errors and no whole-file request for the archive.

Any failed check is kept as failed evidence and blocks the prepared status.

## Limits

- This checks the display conversion, not the accuracy of the Census boundaries.
- Loopback success is not a hosting claim. Nothing here uploads anything.
- Needs 40 GB free to start and stays under 2 GB of disk.
