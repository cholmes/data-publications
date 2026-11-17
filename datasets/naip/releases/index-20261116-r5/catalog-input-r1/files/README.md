# NAIP display copies

Local analytic vector release package. This package is not publicly hosted and has not been submitted to a registry.

Dataset ID: `naip`  
Release: `index-20261116-r5` (`1.0.0`)  
Spatial extent: `[-125.15624999999999, 23.241346102386135, -66.09375, 49.83798245308484]`  
Source: [National Agriculture Imagery Program (NAIP) on AWS, s3://naip-analytic](https://registry.opendata.aws/naip/)

## Analytic assets

| Asset | Path | Rows | Identifier column | SHA-256 |
|---|---|---:|---|---|
| `quads` | `assets/quads.parquet` | 245554 | `id` | `5d7d5404a0e8de0f67a1b41d6058640918396a62c1229c533505274b01f8eb12` |
| `overviews` | `assets/overviews.parquet` | 115 | `id` | `5c9d86db67043857c7c67981469c3cd4d31c6c6ad1dda369b62374feac134c2f` |

## Evidence

The source-fidelity and clean-rebuild reports are copied under `evidence/` and must bind every listed asset by `asset_id`, SHA-256, and byte size. Schema, asset-integrity, loopback HTTP range/CORS, and DuckDB subset results are also in `evidence/`. `manifest.json` binds the canonical record snapshot, sources, assets, workflow revision and report hashes.

## Licenses and attribution

Source attribution: USDA Farm Production and Conservation Business Center, Geospatial Enterprise Operations (NAIP).

Upstream source terms are recorded in `licenses/source-license.json`; the dataset license is recorded in `licenses/data-license.json` and the canonical `dataset.yaml` snapshot. Packaging code is licensed separately; see `licenses/software/`.

## Reproduction

The helper and locked environment are under `verification/workflow/scripts/release_tools/`. Each source converter is captured at the repository-relative path and content hash listed in `manifest.json`. This package includes no raw source archive unless explicitly listed in the source attribution materials.
