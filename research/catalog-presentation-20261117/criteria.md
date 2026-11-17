# NAIP and Census catalogue cards and NAIP map layer: pass marks

Written on 2026-11-17 (UTC) before any render or catalogue change. Each mark is passed or failed as
written; a failed attempt is kept under `attempts/` and is not published.

## Why

- The NAIP card picture is the shared packager's sketch: the first 50,000 rows of `stac/naip.parquet`.
  That file runs south to north, so the sketch holds 11 southern states (rows 1 to 50,000 lie between
  25.8 and 39.4 degrees north; the other 195,554 rows reach 49.4).
- The Census card picture is the same sketch against the collection extent, which runs from -179.1 to
  179.8 degrees because of the Aleutians and Guam, so the lower 48 fill a sliver.
- Portolan's map draws nothing for NAIP: it skips GeoParquet over 10,000 rows, and the national
  overview file, which it can draw, is not in the catalogue.

## Marks

1. **national_file_pinned.** `overviews/national-latest.tif` is read in full anonymously from
   `data.source.coop`; its size equals the overview index's `file:size` for `national-latest`
   (38,077,264 bytes), and its SHA-256 is recorded. Every later step uses those pinned bytes.
2. **national_file_hosting.** For that file: an unsigned HEAD answers 200; `bytes=0-3` answers 206
   with the right `Content-Range` and the TIFF header; the last 8 bytes answer 206; a GET with an
   `Origin` header returns `Access-Control-Allow-Origin` of `*` or that origin and exposes
   `Content-Range` (or `*`).
3. **map_layer_in_catalogue.** The generated NAIP collection carries the national file as an asset
   with roles `visual` and `overview`, the COG media type, `proj:code` `EPSG:3857`, and the pinned
   `file:size` and `file:checksum`. The generator refuses the asset when the record's evidence file is
   missing, changed, or records a different size or hash. No other NAIP asset changes.
4. **map_layer_draws.** The latest Portolan Browser, run locally against the locally staged catalogue,
   opens the NAIP collection page; its map requests the national file only with byte ranges and draws
   imagery inside the NAIP extent (screenshot inspected), with no page error naming the file.
5. **cards_render.** Both pictures come from `scripts/cloud_viewer/render-thumbnails.mjs` at
   1200 x 720 with the shared card frame (title, land context, attribution).
   - NAIP: a downsample of the pinned national file, made with GDAL from the pinned bytes (its PNG
     hash recorded), drawn as a map image over the land context. The render must report a nonzero
     count of opaque image pixels.
   - Census: the published counties PMTiles with its pinned catalogue style, framed on the lower 48
     (-125, 24) to (-66.5, 49.5); the subtitle says the lower 48 are shown. Nonzero rendered features.
6. **cards_reviewed.** Each PNG is looked at full size and at card size: the NAIP picture shows imagery
   across the whole lower 48; the Census picture shows county lines across the whole lower 48. Bound by
   SHA-256 under `publication.catalog.thumbnail`.
7. **catalogue_checks.** `scripts/publication_catalog.py check` passes, the focused catalogue tests and
   any new tests pass, and the other generated products are byte-identical to before.
8. **cards_in_browser.** The local Portolan Browser home page against the local stage shows both new
   card pictures (screenshot inspected).

No upload, listing change, push or Pages deploy is part of this work.
