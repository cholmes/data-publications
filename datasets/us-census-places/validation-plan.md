# US Census counties, places and county subdivisions 2023: validation plan

Recorded on 2026-11-16, before the first build in this repository. An earlier trial build of the
same sources in another layout exists; its outputs are not reused and none of its results are
counted here. The display marks in the last section restate limits that were written down before
their measurements on 2026-11-16 and are listed with that history.

## Source identity and scope

All inputs are US Census Bureau files, public domain, pinned by size and SHA-256 in `source.py`.

| Key | File | Bytes | Rows |
| --- | --- | ---: | ---: |
| counties | `cb_2023_us_county_500k.zip` | 11,630,077 | 3,235 |
| places | `cb_2023_us_place_500k.zip` | 22,856,787 | 32,608 |
| county-subdivisions | `cb_2023_us_cousub_500k.zip` | 40,339,825 | 36,367 |
| gazetteer, places | `2023_Gaz_place_national.zip` | 1,220,953 | |
| gazetteer, county subdivisions | `2023_Gaz_cousubs_national.zip` | 1,491,622 | |
| population estimates | `sub-est2023.csv` | 6,714,548 | |

- The three boundary files are the 2023 cartographic boundary files at 1:500,000. They are
  generalised for mapping and are not the legal boundaries; the TIGER/Line files are the fuller
  source. Row counts above are the shapefile feature counts read on 2026-11-16.
- Scope: every row of every layer, including Puerto Rico and the island areas. No filtering.
- CRS: NAD83 geographic (EPSG:4269), kept. Coordinates are not transformed.
- Three dates are kept apart: boundaries as of 1 January 2023, population estimates for
  1 July 2023 (vintage 2023), conversion in November 2026.

## Required preservation

- Every source field, in source order, with its decoded type, value and null state.
- Source geometry as the WKB that GDAL decodes from the shapefile, with no repair,
  simplification, coordinate change or removal of duplicates.
- Every row once. `source_row` is the 1-based position of the row in the shapefile and restores
  source order.

## Columns added

Four columns are appended after the source fields and are not source values of the boundary file:

- `source_row`: as above.
- `gaz_funcstat`: the `FUNCSTAT` code of the same `GEOID` in the 2023 gazetteer file (places and
  county subdivisions). Null for counties and for a `GEOID` the gazetteer does not list. `A` is an
  active government.
- `popest_2023`: `POPESTIMATE2023` from `sub-est2023.csv`, matched on summary level 050 (county,
  state + county codes), 162 (incorporated place, state + place codes) or 061 (minor civil
  division, state + county + subdivision codes). Null where the estimates file has no such row,
  which includes every census designated place and every row outside the 50 states and DC.
- `bbox`: the bounds of the row's geometry, computed from the unchanged WKB.

## Row order

Rows are written in the order of the 16-bit Hilbert distance of the centre of each row's bounds
(the rule of `scripts/release_tools/spatial_order.py`), ties broken by `source_row`.

## Checks and failure criteria

1. Every input matches its pinned size and SHA-256 before it is read. A changed input stops the
   build.
2. Each boundary layer has the row count above, the listed fields and polygon geometry in
   EPSG:4269. A difference stops the build.
3. The validator is a separate program. It rereads each shapefile and compares, by `source_row`:
   field names, order and types; every value and null; the SHA-256 and length of every WKB value;
   row count and multiplicity (each `source_row` from 1 to N exactly once).
4. The validator recomputes every `bbox` from the output WKB and requires exact equality, and
   requires the GeoParquet bounds to equal the union of them.
5. The validator rebuilds `gaz_funcstat` and `popest_2023` from the pinned gazetteer and estimates
   files with its own reader (the standard `csv` module, not the build's code path) and requires
   every value and null to match. It also requires that no key in either file maps to two
   different values.
6. Row order: recompute the Hilbert key of each row and require a non-decreasing sequence with
   `source_row` ascending inside equal keys.
7. Spatial pruning, with windows fixed here: Front Range `[-105.6, 39.5, -104.6, 40.3]`, central
   Ohio `[-83.4, 39.7, -82.6, 40.3]`, Los Angeles basin `[-118.7, 33.7, -117.6, 34.4]`, Atlanta
   `[-84.7, 33.5, -84.1, 34.1]`. For each layer and window with matching rows, the row-group
   bounds must rule out at least half of the row groups. Counties are exempt if the file has
   fewer than four row groups; the count is then reported and not passed or failed.
8. Fault tests must show the validator rejecting: a removed row, a duplicated row, a changed
   non-null value, a value turned null, a changed `source_row`, a changed WKB byte, a changed
   `bbox` child, a changed `gaz_funcstat`, a changed `popest_2023`, and two rows swapped out of
   order.
9. A second build from the committed code in a clean checkout with the locked environment must
   give byte-identical GeoParquet files.
10. The package must pass the shared packager's gates (STAC, Portolan profile, range requests,
    CORS and a remote subset compared with the local file).

Any failed check is kept as failed evidence and blocks the prepared status.

## Counts expected from the trial, to be confirmed and not assumed

The trial found 19,470 places and 16,186 county subdivisions (in 20 states) with `FUNCSTAT` `A`.
The build reports these counts; a difference is investigated and explained, not silently accepted.

## Display derivative and names index

Out of scope for the analytic release above and built as a separate display package from the
released GeoParquet. Its limits, written before their measurements on 2026-11-16
(`experiments/stac-geoparquet/evidence/outlines/PASS-MARKS.md` in the viewer's repository):

- Counties drawn for a whole-state view: at most 600 KB read.
- Places drawn for a whole-county view: at most 400 KB read.

Tiles met both in the trial and reading the GeoParquet directly did not, which is why a display
package exists. The display package gets its own plan before it is built here.

## Limits

- Source fidelity does not establish the accuracy of the Census boundaries or estimates.
- Nothing here uploads, hosts or registers anything.
- A build must stay under 1 GB of process memory and 1 GB of disk, and needs 40 GB free to start.
