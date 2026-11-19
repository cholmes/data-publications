#!/usr/bin/env python3
"""Check candidate static objects against independent Arrow projections."""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime
import gzip
from hashlib import file_digest
import json
import math
from pathlib import Path
import struct

import pyarrow.dataset as ds

from station_data import select_inputs

CONTROLS = {
    'Wasatch': (40.6039, -111.5831),
    'Seattle': (47.6062, -122.3321),
    'Denver': (39.7392, -104.9903),
    'Miami': (25.7617, -80.1918),
}
SERIES_COLUMNS = [
    'observed_at',
    'variable',
    'channel',
    'value',
    'unit',
    'qc_known_failure',
    'value_status',
]


def canon_time(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def bits(value):
    return (
        struct.pack('!d', value) if value is not None and math.isfinite(value) else None
    )


def vector(latitude, longitude):
    phi, lam = math.radians(latitude), math.radians(longitude)
    return (math.cos(phi) * math.cos(lam), math.cos(phi) * math.sin(lam), math.sin(phi))


def distance_projection(site, where):
    return math.fsum(
        a * b for a, b in zip(vector(site['lat'], site['lon']), where, strict=True)
    )


SNAPSHOT_COLUMNS = [
    'station_key',
    'observed_at',
    'observation_id',
    'latitude',
    'longitude',
    'value',
    'unit',
    'qc_known_failure',
    'value_status',
]
HISTORY_COLUMNS = ['station_key', 'latitude', 'longitude', *SERIES_COLUMNS]
MAP_LIMIT = 128 * 1024 * 1024
HISTORY_LIMIT = 64 * 1024 * 1024


def content_hash(path):
    with path.open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def record_batches(path, columns, selection):
    table = ds.dataset(path, format='parquet')
    scanner = table.scanner(
        columns=columns,
        filter=selection,
        batch_size=8192,
        batch_readahead=1,
        fragment_readahead=1,
        use_threads=False,
        cache_metadata=False,
    )
    yield from scanner.to_batches()


def snapshot_oracle(path, variable):
    winners = {}
    selection = ds.field('variable') == variable
    for batch in record_batches(path, SNAPSHOT_COLUMNS, selection):
        for row in batch.to_pylist():
            key, stamp = row['station_key'], row['observed_at']
            lon, lat, value = row['longitude'], row['latitude'], row['value']
            if (
                not key
                or stamp is None
                or lon is None
                or lat is None
                or not -180 <= lon <= 180
                or not -90 <= lat <= 90
                or value is None
                or not math.isfinite(value)
                or row['qc_known_failure'] is True
                or row['value_status'] != 'valid'
            ):
                continue
            rank = stamp, row['observation_id']
            reading = bits(value), row['unit']
            prior = winners.get(key)
            if prior is None or rank > prior[0]:
                winners[key] = rank, reading
            elif rank == prior[0]:
                assert reading == prior[1], (
                    variable,
                    key,
                    'ambiguous maximum identity',
                )
    return {key: (stamp, *reading) for key, ((stamp, _), reading) in winners.items()}


def verify_snapshots(path, catalog):
    stations = catalog['stations']
    assert {v['id'] for v in catalog['variables']} == set(catalog['snapshots'])
    counts = {}
    for variable, rows in catalog['snapshots'].items():
        got = {}
        for index, stamp, value, unit in rows:
            assert type(index) is int and 0 <= index < len(stations)
            key = stations[index]['key']
            assert key not in got
            assert stamp is not None and value is not None and math.isfinite(value)
            got[key] = canon_time(stamp), bits(value), unit
        expected = snapshot_oracle(path, variable)
        assert got == expected, {
            'variable': variable,
            'captured_rows': len(got),
            'oracle_rows': len(expected),
            'missing_keys': len(expected.keys() - got.keys()),
            'unexpected_keys': len(got.keys() - expected.keys()),
            'different_values': sum(
                got[key] != expected[key] for key in got.keys() & expected.keys()
            ),
        }
        counts[variable] = len(got)
    return counts


def normalized_history(row):
    stamp, variable, channel, value, unit, failure, status = row
    return canon_time(stamp), variable, channel, bits(value), unit, failure, status


def verify_histories(paths, stations, histories):
    selection = ds.field('station_key').isin(list(stations))
    reference = {key: Counter() for key in stations}
    observed_positions = set()
    for path in paths:
        for batch in record_batches(path, HISTORY_COLUMNS, selection):
            for row in batch.to_pylist():
                key = row['station_key']
                station = stations[key]
                if (row['latitude'], row['longitude']) == (
                    station['lat'],
                    station['lon'],
                ):
                    observed_positions.add(key)
                reference[key][
                    normalized_history([row[field] for field in SERIES_COLUMNS])
                ] += 1
    assert observed_positions == stations.keys(), sorted(
        stations.keys() - observed_positions
    )
    for key, rows in histories.items():
        captured_rows = Counter(normalized_history(row) for row in rows)
        expected = reference[key]
        assert captured_rows == expected, {
            'station': key,
            'captured_rows': sum(captured_rows.values()),
            'oracle_rows': sum(expected.values()),
            'missing_rows': sum((expected - captured_rows).values()),
            'unexpected_rows': sum((captured_rows - expected).values()),
        }
    return reference


def read_gzip_json(path, limit):
    with gzip.open(path, 'rb') as source:
        body = source.read(limit + 1)
    if len(body) > limit:
        raise ValueError(f'{path.name} exceeds the decoded byte limit')
    return json.loads(body)


def main():
    if not __debug__:
        raise ValueError('Run the Arrow oracle without Python optimization')
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--station-package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    scope, start, end, paths = select_inputs(args)
    if not paths:
        raise ValueError('No canonical source hours')
    map_path = args.station_package / 'data/map.json.gz'
    catalog = read_gzip_json(map_path, MAP_LIMIT)
    expected = (
        'folia.madis-station-week-map/1',
        scope,
        start,
        end,
        max(paths),
        len(paths),
    )
    got = tuple(
        catalog[field]
        for field in ('schema', 'scope', 'start', 'end', 'source_hour', 'source_hours')
    )
    if got != expected:
        raise ValueError('Map metadata differs from the normalization manifest')

    stations = catalog['stations']
    keys = {station['key'] for station in stations}
    if not keys or len(keys) != len(stations):
        raise ValueError('Missing or duplicate station keys')
    if not all(
        -90 <= row['lat'] <= 90 and -180 <= row['lon'] <= 180 for row in stations
    ):
        raise ValueError('Map includes invalid station coordinates')
    selected, histories, checked = {}, {}, []
    for label, coords in CONTROLS.items():
        point = vector(*coords)
        index, station = min(
            enumerate(stations),
            key=lambda row: (-distance_projection(row[1], point), row[1]['key']),
        )
        history_path = args.station_package / 'data/history' / f'{index}.json.gz'
        history = read_gzip_json(history_path, HISTORY_LIMIT)
        key = station['key']
        if (history['schema'], history['key']) != (
            'folia.madis-station-week-history/1',
            key,
        ):
            raise ValueError(f'Station history identity differs for {label}')
        selected[key] = station
        histories[key] = history['rows']
        checked.append(
            {
                'label': label,
                'key': key,
                'rows': len(history['rows']),
                'sha256': content_hash(history_path),
            }
        )

    snapshot_rows = verify_snapshots(paths[max(paths)], catalog)
    verify_histories(paths.values(), selected, histories)
    result = {
        'status': 'passed_exact_arrow_oracle',
        'source_hour': max(paths),
        'source_hours': len(paths),
        'normalization_manifest_sha256': content_hash(args.manifest),
        'map_sha256': content_hash(map_path),
        'snapshot_rows': snapshot_rows,
        'history_controls': checked,
    }
    with args.output.open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(
        f'Passed exact Arrow checks for {sum(snapshot_rows.values()):,} map readings and {len(checked)} history controls'
    )


if __name__ == '__main__':
    main()
