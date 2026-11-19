#!/usr/bin/env python3
"""Build the MADIS latest map and station history intermediates."""

from argparse import ArgumentParser
from contextlib import closing
import gzip
from itertools import groupby
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

import duckdb

from station_data import Archive, json_bytes, select_inputs, snapshot_readings

GIB = 1024**3
MAP_SCHEMA = 'folia.madis-station-week-map/1'
HISTORY_SCHEMA = 'folia.madis-station-week-history/1'

# Partition the seven-column history projection once. Bucket identities
# are only for temporary build memory and do not reach the client.
PROJECT = """
    SELECT station_key, observed_at, variable, channel, value, unit,
        qc_known_failure, value_status, hash(station_key) % 256 AS bucket
    FROM hour_files WHERE station_key IS NOT NULL
"""
SORTED_ROWS = """
    SELECT station_key, json_array(
        strftime(make_timestamp(epoch_us(observed_at)), '%Y-%m-%dT%H:%M:%S.%fZ'),
        variable, channel, CASE WHEN isfinite(value) THEN value END,
        unit, qc_known_failure, value_status
    )
    FROM read_parquet(?)
    ORDER BY station_key, observed_at, variable, channel, value, unit, qc_known_failure, value_status
"""


def disk_floor(path):
    if shutil.disk_usage(path).free < 40 * GIB:
        raise ValueError(
            'at least 40 GiB free disk is required for private MADIS packaging'
        )


def gzip_file(path, body):
    with path.open('xb') as encoded:
        with gzip.GzipFile(
            filename='', fileobj=encoded, mode='wb', compresslevel=3, mtime=0
        ) as out:
            out.write(body)
    return path.stat().st_size


def build_map(args, scratch, output):
    # The offline snapshot and local baseline share catalog and QC semantics.
    archive = Archive(*select_inputs(args), scratch)
    with closing(archive.db):
        catalog = archive.catalog
        indices = {s['key']: index for index, s in enumerate(catalog['stations'])}
        hour = next(reversed(archive.paths))
        snapshots = {variable['id']: [] for variable in catalog['variables']}
        for row in snapshot_readings(archive.db, archive.paths[hour]):
            snapshots[row['variable']].append(
                [indices[row['key']], row['time'], row['value'], row['unit']]
            )
        product = {
            'schema': MAP_SCHEMA,
            'scope': catalog['scope'],
            'start': catalog['start'],
            'end': catalog['end'],
            'source_hour': hour,
            'source_hours': len(archive.paths),
            'provenance': catalog['provenance'],
            'stations': catalog['stations'],
            'variables': catalog['variables'],
            'snapshots': snapshots,
        }
        size = gzip_file(output, json_bytes(product))
        if size > 8 * 1024**2:
            raise ValueError(f'map exceeds 8 MiB transfer cap: {size}')
        return (
            indices,
            archive.files,
            size,
            {name: len(rows) for name, rows in snapshots.items()},
        )


def read_sorted_rows(db, paths):
    # Stream the externally sortable projection. LIST(... ORDER BY ...) kept
    # several copies of a bucket in DuckDB and exceeded the memory limit.
    cursor = db.execute(SORTED_ROWS, [paths])
    while batch := cursor.fetchmany(8192):
        yield from batch


def build_history(files, indices, scratch, output):
    projected = scratch / 'projection'
    temp = scratch / 'duckdb'
    settings = {
        'threads': 2,
        'memory_limit': '768MB',
        'temp_directory': str(temp),
        'max_temp_directory_size': '3GB',
        'partitioned_write_max_open_files': 16,
        'preserve_insertion_order': 'false',
        'autoload_known_extensions': 'false',
        'autoinstall_known_extensions': 'false',
    }
    disk_floor(scratch)
    remaining = set(indices)
    count = total_rows = total_bytes = largest = 0
    with closing(duckdb.connect(config=settings)) as db:
        db.from_parquet(files).create_view('hour_files')
        db.sql(PROJECT).write_parquet(
            str(projected),
            partition_by=['bucket'],
            row_group_size=32768,
            compression='zstd',
        )
        projection_bytes = sum(p.stat().st_size for p in projected.glob('*/*.parquet'))
        disk_floor(scratch)
        print(f'projected {projection_bytes:,} scratch bytes', flush=True)
        for index, bucket in enumerate(sorted(projected.iterdir()), start=1):
            disk_floor(scratch)
            paths = sorted(str(p) for p in bucket.glob('*.parquet'))
            if not paths:
                raise ValueError(f'empty projection bucket {bucket.name}')
            for key, station in groupby(
                read_sorted_rows(db, paths), key=lambda row: row[0]
            ):
                if key not in indices:
                    continue
                remaining.remove(key)
                at = output / f'{indices[key]}.json.gz'
                header = json_bytes({'schema': HISTORY_SCHEMA, 'key': key})[:-1]
                rows = [row for _, row in station]
                size = gzip_file(
                    at, header + b',"rows":[' + ','.join(rows).encode() + b']}'
                )
                total_rows += len(rows)
                total_bytes += size
                count += 1
                largest = max(largest, size)
            if index % 32 == 0:
                print(
                    f'wrote {count:,} station files ({total_rows:,} rows)', flush=True
                )
    if remaining:
        raise ValueError(
            f'{len(remaining)} catalog stations lack a complete history file'
        )
    return {
        'objects': count,
        'rows': total_rows,
        'bytes': total_bytes,
        'max_bytes': largest,
        'projection_bytes': projection_bytes,
    }


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('choose a new output directory')
    stage = output.with_name(f'.{output.name}.building')
    start = time.monotonic()
    os.umask(0o077)
    stage.mkdir(mode=0o700)
    data = stage / 'data'
    history = data / 'history'
    history.mkdir(parents=True, mode=0o700)
    with tempfile.TemporaryDirectory(
        prefix='madis-static-work-', dir=output.parent
    ) as temp:
        scratch = Path(temp)
        disk_floor(scratch)
        indices, files, map_size, snapshots = build_map(
            args, scratch, data / 'map.json.gz'
        )
        print(
            f'prepared map for {len(indices):,} stations, {map_size:,} compressed bytes',
            flush=True,
        )
        histories = build_history(files, indices, scratch, history)
    if output.exists():
        raise ValueError('output directory appeared during package build')
    stage.rename(output)
    print(
        json.dumps(
            {
                'source_hours': len(files),
                'map_bytes': map_size,
                'snapshots': snapshots,
                'history': histories,
                'seconds': time.monotonic() - start,
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == '__main__':
    main()
