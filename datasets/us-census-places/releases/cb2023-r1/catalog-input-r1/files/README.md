# US Census counties, places and county subdivisions, 2023 cartographic boundaries

Local analytic vector release package. This package is not publicly hosted and has not been submitted to a registry.

Dataset ID: `us-census-places`  
Release: `cb2023-r1` (`1.0.0`)  
Spatial extent: `[-179.146711, -14.548699, 179.77847, 71.387815]`  
Source: [US Census Bureau cartographic boundary files, 2023](https://www2.census.gov/geo/tiger/GENZ2023/shp/)

## Analytic assets

| Asset | Path | Rows | Identifier column | SHA-256 |
|---|---|---:|---|---|
| `counties` | `assets/counties.parquet` | 3235 | `GEOID` | `e5c1ccc121761bc2cf845262e0563f6ae507ea53d262314f9244eb8987f9c13f` |
| `places` | `assets/places.parquet` | 32608 | `GEOID` | `485aeee60f416eba6c1b63c244ee61914c6afca99e0d1581789371a02b1187fe` |
| `county-subdivisions` | `assets/county-subdivisions.parquet` | 36367 | `GEOID` | `4176013a9a35142d25e6f54170bf15ac2f2f463718ef42820f36b511326f1381` |

## Evidence

The source-fidelity and clean-rebuild reports are copied under `evidence/` and must bind every listed asset by `asset_id`, SHA-256, and byte size. Schema, asset-integrity, loopback HTTP range/CORS, and DuckDB subset results are also in `evidence/`. `manifest.json` binds the canonical record snapshot, sources, assets, workflow revision and report hashes.

## Licenses and attribution

Source attribution: Source: US Census Bureau.

Upstream source terms are recorded in `licenses/source-license.json`; the dataset license is recorded in `licenses/data-license.json` and the canonical `dataset.yaml` snapshot. Packaging code is licensed separately; see `licenses/software/`.

## Reproduction

The helper and locked environment are under `verification/workflow/scripts/release_tools/`. Each source converter is captured at the repository-relative path and content hash listed in `manifest.json`. This package includes no raw source archive unless explicitly listed in the source attribution materials.
