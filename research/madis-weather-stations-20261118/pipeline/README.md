# Rebuild the MADIS station release

Use Python 3.12 and the [pinned dependencies](requirements.txt). Run these
commands from this directory. The work directory should be outside the
checkout or inside an ignored `.local/` directory. The week used 5.54 GB
of compressed inputs, with additional space for Parquet and temporary build
files. The pack builder checks for at least 40 GiB free.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -v

WORK="$(mktemp -d)"
python ingest_madis_archive.py "$WORK/normalized"
python noaa_policy.py "$WORK/noaa-policy"
python build_static_madis_week.py --manifest "$WORK/normalized/manifest.json" \
  --output "$WORK/stations"
python verify_normalized_projection.py --manifest "$WORK/normalized/manifest.json" \
  --station-package "$WORK/stations" --output "$WORK/oracle.json"
python pack_madis_source_week.py --source-manifest "$WORK/normalized/manifest.json" \
  --station-package "$WORK/stations" --oracle "$WORK/oracle.json" \
  --noaa-policy "$WORK/noaa-policy" --output "$WORK/release"
```

The default is the published November 9–15, 2026 UTC week. For a one-hour
smoke test, add `--hour 2026-11-15T23:00:00Z` to ingestion and
`--development-preview` to packaging. For an offline run, point
`--archive-dir` to original NOAA files named `YYYYMMDD_HH00.gz` and
supply retained NOAA policy files and their matching receipts.

The standalone decoder uses Python and the NetCDF library. The original
week used a native converter. A replay of November 15 at 23:00 UTC matched
1,980,990 rows across 18 fields, including IDs, clocks, values, units, QC
and coordinates. NOAA can revise its archive files, and the
manifest records the bytes and acquisition time used for each rebuild.
Repacking all 168 original source hours with the original policy
capture matched the SHA-256 of the hosted map and all 85 history packs.
Use the immutable Source Cooperative release for the original metadata
and observations.

## Historical and fresh collection

For historical backfills, use `--start` and `--end` to select disjoint
half-open UTC windows of at most 168 hours. For a scheduled fresh job, call
`ingest_madis_archive.py OUTPUT --current --hour YYYY-MM-DDTHH:00:00Z`.
The archive and current paths both go directly to NOAA. Allow for source
files to arrive late and retain their original observation timestamps.
Publish a full-week package only after every expected hour is present and
the independent Arrow check passes.

One deployment option is a task per historical window on AWS Fargate
Spot or another batch runner, with source bodies and Parquet checkpointed
to persistent storage. A fresh job can run on a regular schedule and
retry the archive route once the hour reaches it. Use source-hour and
body-digest keys so retries can reuse completed work and retain revisions.
These scripts run as local commands. Scheduling, checkpoint storage and
cloud deployment are separate from the release build.

## Data contract

- [Parquet schema](observation_schema.py) defines 41 fields. Every source
  report emits ten channel rows with their own value status and QC.
  Native values, units, observation/report/receipt clocks and coordinates
  are retained. When available, period fields carry measurement
  semantics. These core channels do not supply those periods.
- `station_key` is `noaa-madis:<provider>:<provider-station-id>` with
  percent-encoded components. `observation_id` binds a row to its source
  body, record index and measurement. Repeated reports remain separate.
- `data/map.json.gz` uses `folia.madis-station-week-map/1`. Each current
  reading is `[station_index, observation_time_utc, value, unit]`.
  `history_index[station_index]` is `[part, byte_offset, byte_length]`.
- A range contains one gzip member with schema
  `folia.madis-station-week-history/1`, the station key and seven fields per
  observation row. These fields are observation UTC time, variable, native
  channel, value, unit, known QC failure and value status.
- `manifest.json` ties the complete interval, NOAA policy digests and each
  output object's SHA-256 to an immutable release ID. The Arrow check
  compares all final-hour readings and the four station history controls.
  The packer independently checks the byte range of every included member.

Keep raw bodies and unfiltered intermediates in private storage. The
packager only emits category 3 weather from exact NOAA provider IDs
whose listed subproviders are all category 3. Review the official rules
and notify NOAA before redistribution. Preserve provider attribution
and the reliability disclaimer. [NOAA redistribution rules](https://madis.ncep.noaa.gov/madis_restrictions.shtml) · [NOAA provider categories](https://madis.ncep.noaa.gov/mesonet_providers.shtml)
