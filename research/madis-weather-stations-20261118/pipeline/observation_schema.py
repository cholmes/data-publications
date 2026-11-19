"""Version 1 source-native observation contract. No implicit station or clock inference."""

from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import re
from urllib.parse import quote
import pyarrow as pa

VERSION = 1
UTC = dt.timezone.utc
TIME = pa.timestamp('us', tz='UTC')
STRINGS = [
    'observation_id',
    'observation_key',
    'source_id',
    'provider_id',
    'provider_station_id',
    'station_key',
    'station_id',
    'station_name',
    'physical_site_id',
    'region_ids_json',
    'channel',
    'variable',
    'native_time',
    'raw_value_text',
    'raw_unit',
    'unit',
    'statistic',
    'value_status',
    'semantics_status',
    'qc_status',
    'native_qc_json',
    'origin',
    'source_body_sha256',
    'source_record',
    'source_locator',
    'metadata_json',
    'normalization_version',
]
TIMES = [
    'observed_at',
    'period_start',
    'period_end',
    'reported_at',
    'received_at',
    'captured_at',
]
NUMBERS = ['latitude', 'longitude', 'elevation_m', 'raw_value', 'value']
OBS_SCHEMA = pa.schema(
    [('schema_version', pa.int16())]
    + [(x, pa.string()) for x in STRINGS]
    + [(x, TIME) for x in TIMES]
    + [(x, pa.float64()) for x in NUMBERS]
    + [('qc_known_failure', pa.bool_()), ('quantity_qualified', pa.bool_())]
)


def encoded(v):
    return (
        json.dumps(
            v, sort_keys=True, separators=(',', ':'), allow_nan=False, default=str
        )
        + '\n'
    ).encode()


def sha(v):
    return hashlib.sha256(v).hexdigest()


def utc(value):
    if value is None:
        return None
    t = (
        value
        if isinstance(value, dt.datetime)
        else dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    )
    if t.tzinfo is None:
        raise ValueError('Explicit UTC offset required')
    return t.astimezone(UTC)


def iso(value):
    t = utc(value)
    return t.isoformat(timespec='microseconds').replace('+00:00', 'Z') if t else None


def numeric(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        r = float(value)
    except (ValueError, TypeError):
        return None
    return r if math.isfinite(r) else None


def text(value):
    if isinstance(value, bytes):
        return value.split(b'\0')[0].decode('utf-8', 'replace').strip()
    return '' if value is None else str(value).strip()


def station_key(source, provider, native):
    return ':'.join(quote(text(x), safe='') for x in (source, provider, native))


def make_observation(asset, **kw):
    required = ['provider_id', 'station_id', 'channel', 'variable', 'source_record']
    if any(not text(kw.get(k)) for k in required):
        raise ValueError(
            'Native provider/station/channel/variable/source record required'
        )
    if not asset.get('source_id') or not re.fullmatch(
        r'[0-9a-f]{64}', asset.get('sha256', '')
    ):
        raise ValueError('Source asset identity required')
    source = asset['source_id']
    provider = text(kw['provider_id'])
    sid = text(kw['station_id'])
    pid = text(kw.get('provider_station_id') or sid)
    row = {k: None for k in OBS_SCHEMA.names}
    row.update(
        schema_version=VERSION,
        source_id=source,
        provider_id=provider,
        provider_station_id=pid,
        station_id=sid,
        station_key=station_key(source, provider, pid),
        region_ids_json='[]',
        native_qc_json='{}',
        metadata_json='{}',
        normalization_version='weather_archive/1',
        statistic='unknown',
        value_status='missing',
        semantics_status='native_only',
        qc_status='unknown',
        qc_known_failure=None,
        origin='observed',
        source_body_sha256=asset['sha256'],
        captured_at=utc(asset['captured_at']),
    )
    unknown = set(kw) - set(row)
    if unknown:
        raise ValueError('Unknown observation fields: ' + str(sorted(unknown)))
    row.update(kw)
    row['source_record'] = str(row['source_record'])
    row['provider_station_id'] = pid
    row['station_key'] = station_key(source, provider, pid)
    if row['source_id'] != source or row['source_body_sha256'] != asset['sha256']:
        raise ValueError('Observation asset binding changed')
    for name in TIMES:
        row[name] = utc(row[name])
    if row['captured_at'] != utc(asset['captured_at']):
        raise ValueError('Capture clock differs from asset')
    for name in NUMBERS:
        if row[name] is not None:
            n = numeric(row[name])
            if n is None:
                raise ValueError('Nonfinite normalized/native numeric field: ' + name)
            row[name] = n
    if row['raw_value_text'] is None and kw.get('raw_value') is not None:
        row['raw_value_text'] = str(kw['raw_value'])
    if row['native_time'] is None:
        row['native_time'] = iso(row['observed_at'])
    if row['value'] is not None and not row['unit']:
        raise ValueError('Normalized value requires explicit unit')
    if (
        row['value_status']
        in {
            'missing',
            'invalid',
            'unit_unknown',
            'nonfinite',
            'masked',
            'negative',
            'outside_direction_range',
        }
        and row['value'] is not None
    ):
        raise ValueError('Invalid/missing value cannot be normalized')
    if row['qc_known_failure'] is not None and not isinstance(
        row['qc_known_failure'], bool
    ):
        raise ValueError('QC failure must be bool or unknown')
    if row['qc_known_failure'] is True and row['qc_status'].startswith('passed'):
        raise ValueError('Contradictory QC')
    if (
        row['qc_status'] in {'unknown', 'unchecked'}
        and row['qc_known_failure'] is False
    ):
        raise ValueError('Unknown QC is not an explicit nonfailed classification')
    for name in ['metadata_json', 'native_qc_json', 'region_ids_json']:
        json.loads(row[name])
    if (
        row['period_start']
        and row['period_end']
        and row['period_start'] > row['period_end']
    ):
        raise ValueError('Reversed observation interval')
    row['quantity_qualified'] = bool(
        row['value'] is not None
        and row['value_status'] == 'valid'
        and row['semantics_status'] == 'qualified'
        and row['observed_at']
        and row['qc_known_failure'] is not True
        and row['origin'] == 'observed'
    )
    time_key = (
        iso(row['observed_at'])
        if row['observed_at']
        else {
            'unresolved_native_time': row['native_time'],
            'source_body_sha256': asset['sha256'],
            'source_record': row['source_record'],
        }
    )
    row['observation_key'] = sha(
        encoded(
            [
                row['station_key'],
                row['channel'],
                row['variable'],
                time_key,
                iso(row['period_start']),
                iso(row['period_end']),
                row['statistic'],
            ]
        )
    )
    row['observation_id'] = sha(
        encoded(
            [
                source,
                asset['sha256'],
                row['source_record'],
                row['channel'],
                row['variable'],
            ]
        )
    )
    return row


def table(rows):
    return pa.Table.from_pylist(rows, schema=OBS_SCHEMA)
