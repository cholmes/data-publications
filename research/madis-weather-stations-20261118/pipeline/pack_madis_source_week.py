#!/usr/bin/env python3
"""Stage only published NOAA category 3 weather in static, range-readable packs."""

import argparse
from collections import Counter
from contextlib import ExitStack
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
from urllib.parse import unquote

from noaa_policy import classify, verified_policy
from release_window import DATE_FORMAT, source_hours

SCHEMA = 'folia.madis-source-week/1'
MAP_SCHEMA = 'folia.madis-station-week-map/1'
HISTORY_SCHEMA = 'folia.madis-station-week-history/1'
MIB = 1024**2
MAX_PART = 24 * MIB
MAX_STATION = 2 * MIB
MIN_FREE = 40 * 1024**3
BASE = 'https://madis.ncep.noaa.gov/'
PRODUCT = 'https://source.coop/nthh/weather-stations'


def compact(value, sort_keys=False):
    return json.dumps(
        value, separators=(',', ':'), allow_nan=False, sort_keys=sort_keys
    ).encode()


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def eligible_map(original, policy):
    stations, index, excluded = [], {}, Counter()
    seen = set()
    for at, station in enumerate(original['stations']):
        key, provider = station['key'], station['provider']
        parts = key.split(':')
        if (
            len(parts) != 3
            or parts[0] != 'noaa-madis'
            or key in seen
            or unquote(parts[1], errors='strict') != provider
        ):
            raise ValueError(
                'station identity does not match the native MADIS provider'
            )
        seen.add(key)
        if classify(provider, policy) != 'eligible':
            excluded[provider] += 1
            continue
        index[at] = len(stations)
        stations.append(station)
    if not stations:
        raise ValueError('provider allowlist accepts no stations')
    mapped = {
        var: [
            [index[at], stamp, value, unit]
            for at, stamp, value, unit in rows
            if at in index
        ]
        for var, rows in original['snapshots'].items()
    }
    result = {
        **original,
        'stations': stations,
        'snapshots': mapped,
        'scope': f'NOAA MADIS · Category 3 weather · {original["source_hours"]} source hours',
        'provenance': 'NOAA MADIS Integrated Mesonet · provider attribution in station metadata',
    }
    return result, index, excluded


def station_blob(root, at, key):
    f = root / 'data' / 'history' / f'{at}.json.gz'
    if f.is_symlink() or not f.is_file() or not 0 < f.stat().st_size <= MAX_STATION:
        raise ValueError(f'invalid private station object {at}')
    blob = f.read_bytes()
    head = compact({'schema': HISTORY_SCHEMA, 'key': key})[:-1] + b',"rows":['
    with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
        if stream.read(len(head)) != head:
            raise ValueError(f'station history identity mismatch at index {at}')
    return blob


def pack_history(root, target, original, retained):
    offsets, members = [], []
    with ExitStack() as shard:
        part = None
        for old, new in retained.items():
            if new != len(offsets):
                raise ValueError('non-contiguous station order')
            blob = station_blob(root, old, original['stations'][old]['key'])
            if part is None or part.tell() + len(blob) > MAX_PART:
                shard.close()
                if shutil.disk_usage(target).free < MIN_FREE + MAX_PART:
                    raise ValueError('new shard would enter the 40 GiB disk reserve')
                f = target / f'part-{len(members):03d}.bin'
                part = shard.enter_context(f.open('xb'))
                members.append(f)
            offsets.append([len(members) - 1, part.tell(), len(blob)])
            part.write(blob)
    return offsets, members


def verify_ranges(root, original, retained, offsets, shards):
    next_offset = 0
    active = 0
    with ExitStack() as read:
        stream = read.enter_context(shards[0].open('rb'))
        for (old, _), (part, offset, size) in zip(
            retained.items(), offsets, strict=True
        ):
            if part != active:
                if part != active + 1 or stream.read(1):
                    raise ValueError('shard coverage or order mismatch')
                read.close()
                stream = read.enter_context(shards[part].open('rb'))
                active, next_offset = part, 0
            if offset != next_offset or stream.read(size) != station_blob(
                root, old, original['stations'][old]['key']
            ):
                raise ValueError(f'packed byte range differs for station index {old}')
            next_offset += size
        if active != len(shards) - 1 or stream.read(1):
            raise ValueError('incomplete shard coverage')


def file_record(root, path, kind):
    return {
        'path': path.relative_to(root).as_posix(),
        'bytes': path.stat().st_size,
        'sha256': digest(path),
        'content_type': kind,
    }


def readme(map_, decisions, hashes):
    return f"""# NOAA MADIS mesonet weather station observations

A static slice of NOAA MADIS Integrated Mesonet weather observations. The
UTC window starts at {map_['start']} and ends at {map_['end']}, exclusive. This release uses {map_['source_hours']} original hourly files.
Its latest map shows readings from {map_['source_hour']}. Each observation
keeps its source timestamp.

The release covers {len(map_['stations']):,} source-qualified station keys.
It excludes {sum(decisions.values()):,} keys from providers whose full
weather redistribution rights are restricted or unresolved. Provider IDs
are preserved in the map and station keys. We include category 3 weather
providers when all listed subproviders are also category 3. The NOAA
provider table digest is `{hashes['provider']}`.

The manifest lists checksums for the downloadable map and history packs.
Decode `data/map.json.gz` to find station coordinates, latest readings and
the history index. For a station at index `i`, `history_index[i]` gives the
shard number, byte offset, and byte length. Fetch exactly that byte range
from `data/history/part-NNN.bin` and decompress the gzip member. History
rows contain the UTC observation time, measurement, source channel, value,
unit, known QC failure, and value status. The release preserves missing
values and same-time observations. The latest map excludes known QC failures.

Source and providers are credited in the records. NOAA and its data
providers disclaim liability for the accuracy and reliability of the
observations.

[NOAA MADIS data restrictions]({BASE}madis_restrictions.shtml) ·
[NOAA provider table]({BASE}mesonet_providers.shtml) ·
[Data product]({PRODUCT})
"""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--station-package', type=Path, required=True)
    p.add_argument('--source-manifest', type=Path, required=True)
    p.add_argument('--oracle', type=Path)
    p.add_argument('--noaa-policy', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--development-preview', action='store_true')
    args = p.parse_args()
    os.umask(0o077)
    root, manifest, output = (
        args.station_package.resolve(),
        args.source_manifest.resolve(),
        args.output.resolve(),
    )
    source = json.loads(manifest.read_bytes())
    original_map = root / 'data/map.json.gz'
    with gzip.open(original_map, 'rb') as stream:
        original = json.load(stream)
    start, end = source['range']['start'], source['range']['end']
    expected = [hour.strftime(DATE_FORMAT) for hour in source_hours(start, end)]
    admitted = [hour['nominal_time'] for hour in source['hours']]
    if (
        not admitted
        or admitted != sorted(set(admitted))
        or not set(admitted) <= set(expected)
        or original['schema'] != MAP_SCHEMA
        or (original['start'], original['end']) != (start, end)
        or original['source_hours'] != len(admitted)
        or original['source_hour'] != admitted[-1]
    ):
        raise ValueError('Station archive differs from the source window')
    manifest_sha = digest(manifest)
    if not args.development_preview:
        if (
            source['status'] != 'complete'
            or len(expected) != 168
            or admitted != expected
            or not args.oracle
        ):
            raise ValueError(
                'a full week and its independent private readback are required'
            )
        proof = json.loads(args.oracle.read_bytes())
        if (
            proof.get('status') != 'passed_exact_arrow_oracle'
            or proof.get('source_hours') != 168
            or proof.get('map_sha256') != digest(original_map)
            or proof.get('normalization_manifest_sha256') != manifest_sha
        ):
            raise ValueError(
                'private readback is not bound to the package and source manifest'
            )

    policy, hashes = verified_policy(args.noaa_policy)
    map_, retained, excluded = eligible_map(original, policy)
    if output.exists():
        raise ValueError('choose a new staging path')
    stage = output.with_name('.' + output.name + '.building')
    target = stage / 'data/history'
    target.mkdir(parents=True, mode=0o700)
    offsets, parts = pack_history(root, target, original, retained)
    verify_ranges(root, original, retained, offsets, parts)
    map_['history_index'] = offsets
    map_path = stage / 'data/map.json.gz'
    with map_path.open('xb') as encoded:
        with gzip.GzipFile(
            filename='', fileobj=encoded, mode='wb', compresslevel=3, mtime=0
        ) as stream:
            stream.write(compact(map_))
    README = stage / 'README.md'
    README.write_text(readme(map_, excluded, hashes))
    inventory = [
        file_record(stage, README, 'text/markdown'),
        file_record(stage, map_path, 'application/octet-stream'),
        *(file_record(stage, path, 'application/octet-stream') for path in parts),
    ]
    providers = Counter(s['provider'] for s in map_['stations'])
    publication = {
        'schema': (
            SCHEMA if not args.development_preview else SCHEMA + '/development-preview'
        ),
        'source': {
            'start': start,
            'end': end,
            'source_hours': len(source['hours']),
            'source_manifest_sha256': manifest_sha,
        },
        'policy': {
            'providers_sha256': hashes['provider'],
            'restrictions_sha256': hashes['restrictions'],
            'allowed_station_keys_by_provider': dict(providers),
            'excluded_station_keys_by_provider': dict(excluded),
        },
        'files': inventory,
    }
    publication['release_id'] = hashlib.sha256(
        compact(publication, sort_keys=True)
    ).hexdigest()
    (stage / 'manifest.json').write_bytes(compact(publication, sort_keys=True) + b'\n')
    stage.rename(output)
    print(
        json.dumps(
            {
                'release_id': publication['release_id'],
                'stations': len(retained),
                'excluded': dict(excluded),
                'map_values': sum(map(len, map_['snapshots'].values())),
                'source_hours': len(source['hours']),
                'objects': len(inventory) + 1,
                'bytes': sum(f['bytes'] for f in inventory),
            },
            indent=2,
        )
    )


if __name__ == '__main__':
    main()
