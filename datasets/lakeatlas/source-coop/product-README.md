# LakeATLAS v1.0 — global lake attributes and pour points

LakeATLAS lake polygons and pour points with hydro-environmental attributes in separate spatially ordered GeoParquet files, with a versioned field-semantics supplement. Separately versioned PMTiles provide map display for both layers and source-ID attribute lookup.

Observation and model-input dates vary by contributing attribute; use the producer catalog and field supplement for interpretation.

## Files

Use GeoParquet for analysis and PMTiles for maps. Field dictionaries describe columns and units.

| File | Size |
| --- | ---: |
| [lakeatlas-polygons-v1.0.parquet](https://data.source.coop/nthh/lakeatlas/lakeatlas-polygons-v1.0.parquet) | 1.14 GB |
| [lakeatlas-polygons-v1.0.fields.json](https://data.source.coop/nthh/lakeatlas/lakeatlas-polygons-v1.0.fields.json) | 19.7 kB |
| [lakeatlas-pour-points-v1.0.parquet](https://data.source.coop/nthh/lakeatlas/lakeatlas-pour-points-v1.0.parquet) | 283.78 MB |
| [lakeatlas-pour-points-v1.0.fields.json](https://data.source.coop/nthh/lakeatlas/lakeatlas-pour-points-v1.0.fields.json) | 19.5 kB |
| [lakeatlas-polygons-v1.0.pmtiles](https://data.source.coop/nthh/lakeatlas/lakeatlas-polygons-v1.0.pmtiles) | 1.19 GB |
| [lakeatlas-pour-points-v1.0.pmtiles](https://data.source.coop/nthh/lakeatlas/lakeatlas-pour-points-v1.0.pmtiles) | 409.21 MB |
| [LICENSE.txt](https://data.source.coop/nthh/lakeatlas/LICENSE.txt) | 0.4 kB |
| [manifest-20261111.json](https://data.source.coop/nthh/lakeatlas/manifest-20261111.json) | 3.3 kB |
| [lakeatlas-polygons-v1.0-presentation-v2.style.json](https://data.source.coop/nthh/lakeatlas/lakeatlas-polygons-v1.0-presentation-v2.style.json) | 2.0 kB |
| [lakeatlas-pour-points-v1.0-presentation-v2.style.json](https://data.source.coop/nthh/lakeatlas/lakeatlas-pour-points-v1.0-presentation-v2.style.json) | 2.8 kB |
| [lakeatlas-preview-v2.png](https://data.source.coop/nthh/lakeatlas/lakeatlas-preview-v2.png) | 118.7 kB |
| [HydroATLAS_TechDoc_v10_1.pdf](https://data.source.coop/nthh/lakeatlas/HydroATLAS_TechDoc_v10_1.pdf) | 3.66 MB |
| [LakeATLAS_Catalog_v10.pdf](https://data.source.coop/nthh/lakeatlas/LakeATLAS_Catalog_v10.pdf) | 54.06 MB |

## Supporting documentation

- [field-semantics.json](https://raw.githubusercontent.com/nthh/data-publications/c0ad1cc5c18d69d3915f01bda478cb300d13b12f/datasets/lakeatlas/metadata-enhancements/v1/field-semantics.json)
- [README.md](https://github.com/nthh/data-publications/blob/c0ad1cc5c18d69d3915f01bda478cb300d13b12f/datasets/lakeatlas/metadata-enhancements/v1/README.md)

## Schema

[Column definitions in the catalog](https://nthh.github.io/data-publications/lakeatlas/collection.json) include names, storage types and descriptions. Use the field dictionaries and producer documentation above for units, coded values and limitations.


## Read with DuckDB

Query the remote GeoParquet directly:

```sql
SELECT count(*) AS feature_count FROM read_parquet('https://data.source.coop/nthh/lakeatlas/lakeatlas-polygons-v1.0.parquet');
SELECT * FROM read_parquet('https://data.source.coop/nthh/lakeatlas/lakeatlas-polygons-v1.0.parquet') LIMIT 5;
```

The `.style.json` files show the PMTiles in a MapLibre viewer with the PMTiles protocol installed. Preview images are generalized displays; they are not analytical geometry.

## Attribution and license

HydroSHEDS / HydroATLAS authors; Lehner, Messager, Korver and Linke (2022), DOI 10.1038/s41597-022-01425-z.

Mixed field-level terms: the producer catalog identifies CC BY 4.0 and ODbL 1.0 attributes. Retain the catalog, source attribution and original-source notices; do not describe the entire attribute table as uniformly CC BY 4.0.

Independently maintained by [nthh](https://source.coop/nthh).

- [License terms](https://creativecommons.org/licenses/by/4.0/)
- [Research paper](https://doi.org/10.1038/s41597-022-01425-z)
- [Dataset release](https://doi.org/10.6084/m9.figshare.19312001.v1)
- [Producer technical documentation](https://ndownloader.figshare.com/files/35959532)
- [Producer attribute catalogue](https://ndownloader.figshare.com/files/35959535)
- [Original download](https://ndownloader.figshare.com/files/35959544)
- [Processor: nthh](https://source.coop/nthh/lakeatlas)
- [Producer: HydroSHEDS / HydroATLAS authors](https://www.hydrosheds.org/products/hydroatlas)

## Release files

- [lakeatlas-polygons.parquet](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/assets/lakeatlas-polygons.parquet) (asset)
- [lakeatlas-pour-points.parquet](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/assets/lakeatlas-pour-points.parquet) (asset)
- [thumbnail.png](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/display/thumbnail.png) (display_derivatives)
- [data-license.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/licenses/data-license.json) (data_license)
- [source-license.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/licenses/source-license.json) (source_license)
- [lakeatlas-polygons-field-dictionary.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/metadata/lakeatlas-polygons-field-dictionary.json) (field_dictionary)
- [lakeatlas-pour-points-field-dictionary.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/metadata/lakeatlas-pour-points-field-dictionary.json) (field_dictionary)
- [clean-rebuild.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/clean-rebuild.json) (supporting_files)
- [evidence-provenance.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/evidence-provenance.json) (supporting_files)
- [rebuild-environment.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/rebuild-environment.json) (supporting_files)
- [source-fidelity.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/source-fidelity.json) (supporting_files)
- [source-inspection.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/source-inspection.json) (supporting_files)
- [spatial-order-polygons-clean.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/spatial-order-polygons-clean.json) (supporting_files)
- [spatial-order-polygons-primary.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/spatial-order-polygons-primary.json) (supporting_files)
- [spatial-order-pour-points-clean.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/spatial-order-pour-points-clean.json) (supporting_files)
- [spatial-order-pour-points-primary.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/spatial-order-pour-points-primary.json) (supporting_files)
- [spatial-pruning-polygons-clean.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/spatial-pruning-polygons-clean.json) (supporting_files)
- [spatial-pruning-polygons-primary.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/spatial-pruning-polygons-primary.json) (supporting_files)
- [spatial-pruning-pour-points-clean.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/spatial-pruning-pour-points-clean.json) (supporting_files)
- [spatial-pruning-pour-points-primary.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/provenance/spatial-pruning-pour-points-primary.json) (supporting_files)
- [ATTRIBUTION.md](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/source/ATTRIBUTION.md) (supporting_files)
- [HydroATLAS_TechDoc_v10_1.pdf](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/source/HydroATLAS_TechDoc_v10_1.pdf) (supporting_files)
- [LakeATLAS_Catalog_v10.pdf](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/source/LakeATLAS_Catalog_v10.pdf) (supporting_files)
- [attribution.json](https://data.source.coop/nthh/lakeatlas/releases/lakeatlas-v1.0-r2/source/attribution.json) (source_attribution)
- [field-semantics.json](https://data.source.coop/nthh/lakeatlas/metadata/field-semantics-v1/field-semantics.json) (supplement)
- [README.md](https://data.source.coop/nthh/lakeatlas/metadata/field-semantics-v1/README.md) (supplement)
- [build_semantics.py](https://data.source.coop/nthh/lakeatlas/metadata/field-semantics-v1/build_semantics.py) (supplement)

## Display package

Display release: `display-v1`. The manifest is pinned at SHA-256 `ed70989525111682a294b6aadf1118a1ebfaefff863d645c6c805c5e8eafb70f`.
Display assets are separate immutable derivatives bound to this analytical release.
- [Display manifest](https://data.source.coop/nthh/lakeatlas/display/display-v1/manifest.json)
- [Lakeatlas Polygons PMTiles](https://data.source.coop/nthh/lakeatlas/display/display-v1/assets/lakeatlas-polygons.pmtiles) (1190009288 bytes; SHA-256 `394594baa10516b5bdea3841cdbbd7f8603412475059f846f5704386a72f71be`)
  - [Map style](https://data.source.coop/nthh/lakeatlas/display/display-v1/styles/lakeatlas-polygons.json)
- [Lakeatlas Pour Points PMTiles](https://data.source.coop/nthh/lakeatlas/display/display-v1/assets/lakeatlas-pour-points.pmtiles) (409205238 bytes; SHA-256 `68c28ecb4585378e0e729a5c72902214e935fa7645a6bef68372f0ec61bc4ffb`)
  - [Map style](https://data.source.coop/nthh/lakeatlas/display/display-v1/styles/lakeatlas-pour-points.json)

## Limitations

- Polygons and pour points are distinct producer layers, each retained separately.
- Attribute codes, scaling, spatial extent and aggregation rules must be interpreted using the versioned field-semantics supplement and producer documentation.
- The metadata supplement is separate from the unchanged immutable r2 analytical package.
- Live GEE counts and 522 sampled IDs per layer match. Both layers have numeric differences including integral GEE GDP values; the polygon layer also has three narrow source spikes absent spatially from GEE. Strict parity fails. No exhaustive GEE or independent scientific-accuracy claim.

[Conversion scripts and validation](https://github.com/nthh/data-publications/tree/main/datasets/lakeatlas) · [Portolan map](https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/lakeatlas/collection.json)

Versioned filenames and checksum manifests identify the published data.


## Query lakeatlas-pour-points-v1.0.parquet

```sql
SELECT count(*) AS feature_count FROM read_parquet('https://data.source.coop/nthh/lakeatlas/lakeatlas-pour-points-v1.0.parquet');
SELECT * FROM read_parquet('https://data.source.coop/nthh/lakeatlas/lakeatlas-pour-points-v1.0.parquet') LIMIT 5;
```
