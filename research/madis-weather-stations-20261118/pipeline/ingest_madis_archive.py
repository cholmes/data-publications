#!/usr/bin/env python3
"""Capture a fixed NOAA archive window and normalize its ten core weather channels."""

import argparse
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile

import netCDF4
import numpy as np
import pyarrow.parquet as pq

from native_values import DATASET, _json, _number, _qc, _text, _variable_metadata
from netcdf_extent import MAX_INFLATED_BYTES, validate_extent
from noaa_policy import fetch
from observation_schema import OBS_SCHEMA, make_observation, table, utc
from release_window import DATE_FORMAT, END, START, canonical_hour, source_hours

BASE = 'https://madis-data.ncep.noaa.gov/madisPublic1/data/'
MAX_COMPRESSED_BYTES = 45_000_000
MAX_REPORTS = 300_000
FILE_FORMAT = '%Y%m%d_%H00.gz'
CLOCKS = ('observationTime', 'reportTime', 'receivedTime')
TEXT = ('stationId', 'providerId', 'dataProvider', 'stationName')
MEASUREMENTS = {
    'windSpeed': ('wind_speed', 'm/s', ('meter/sec', 'm/s'), 1.0),
    'windDir': ('wind_direction', 'degree', ('degree',), 1.0),
    'windGust': ('wind_gust', 'm/s', ('meter/sec', 'm/s'), 1.0),
    'temperature': ('air_temp', 'degree_Celsius', ('K', 'kelvin'), 1.0),
    'dewpoint': ('dew_point_temperature', 'degree_Celsius', ('K', 'kelvin'), 1.0),
    'relHumidity': ('relative_humidity', '%', ('%', 'percent'), 1.0),
    'stationPressure': ('station_pressure', 'hPa', ('Pa', 'pascal'), 0.01),
    'seaLevelPressure': ('sea_level_pressure', 'hPa', ('Pa', 'pascal'), 0.01),
    'precipAccum': ('precip_accum', 'mm', ('mm', 'millimeter'), 1.0),
    'precipRate': (
        'precip_rate',
        'mm/hour',
        ('m/s', 'meter/sec', 'meter/second'),
        3_600_000.0,
    ),
}
WIND = {'windSpeed', 'windDir', 'windGust'}
QC_SUFFIXES = ('DD', 'QCA', 'QCR', 'QCD')


def canonical(raw, value, channel, raw_unit):
    _, unit, spellings, scale = MEASUREMENTS[channel]
    if np.ma.is_masked(raw):
        return None, None, 'missing'
    if value is None:
        return None, None, 'invalid'
    if channel in {'windSpeed', 'windGust'} and value < 0:
        return None, None, 'invalid'
    if channel == 'windDir' and not 0 <= value <= 360:
        return None, None, 'invalid'
    if raw_unit not in spellings:
        return None, None, 'unit_unknown'
    if channel == 'relHumidity' and not 0 <= value <= 100:
        return None, None, 'invalid'
    if channel not in WIND and channel != 'relHumidity' and value < 0:
        return None, None, 'invalid'
    if channel in {'temperature', 'dewpoint'}:
        return value - 273.15, unit, 'valid'
    return value * scale, unit, 'valid'


def clocks(values, variable):
    unit = getattr(variable, 'units', None)
    if not unit:
        raise ValueError(f'{variable.name} lacks CF time units')
    raw = np.ma.masked_invalid(values)
    if raw.count() == 0:
        return [None] * len(raw)
    calendar = getattr(variable, 'calendar', 'standard')
    decoded = netCDF4.num2date(
        raw.compressed(),
        unit,
        calendar=calendar,
        only_use_cftime_datetimes=False,
        only_use_python_datetimes=True,
    )
    present = iter(decoded)
    return [
        None if masked else utc(next(present).replace(tzinfo=timezone.utc))
        for masked in np.ma.getmaskarray(raw)
    ]


def rows_for_slice(dataset, columns, first, stop, asset, units, attrs):
    arrays = {name: dataset[name][first:stop] for name in columns}
    time_axes = {name: clocks(arrays[name], dataset[name]) for name in CLOCKS}
    for offset in range(stop - first):
        index = first + offset
        native_station, provider_station, provider, name = (
            _text(arrays[field][offset]) for field in TEXT
        )
        station = native_station or f'unresolved-source-record-{index}'
        observed, reported, received = (time_axes[field][offset] for field in CLOCKS)
        time_var = dataset['observationTime']
        calendar = getattr(time_var, 'calendar', 'standard')
        raw_time = f"{_text(arrays['observationTime'][offset])} {time_var.units} calendar={calendar}".strip()
        common = {
            'provider_id': provider or 'unknown_provider',
            'provider_station_id': provider_station or station,
            'station_id': station,
            'station_name': name or None,
            'latitude': _number(arrays['latitude'][offset]),
            'longitude': _number(arrays['longitude'][offset]),
            'elevation_m': _number(arrays['elevation'][offset]),
            'observed_at': observed,
            'reported_at': reported,
            'received_at': received,
            'source_record': str(index),
            'native_time': raw_time,
        }
        for channel, (variable, _, _, _) in MEASUREMENTS.items():
            raw = arrays[channel][offset]
            raw_value = _number(raw)
            value, unit, status = canonical(raw, raw_value, channel, units[channel])
            qc = [
                arrays[channel + suffix][offset] if channel + suffix in arrays else None
                for suffix in QC_SUFFIXES
            ]
            qc_status, qc_failure, native_qc = _qc(*qc)
            provenance = {
                'dataset': DATASET,
                'native_variable': channel,
                'native_variable_attributes': attrs[channel],
                'native_time_basis': {
                    'variable': 'observationTime',
                    'units': time_var.units,
                    'calendar': calendar,
                    'raw_value': raw_time,
                },
                'native_station_metadata': {
                    field: _text(arrays[field][offset]) or None for field in TEXT
                },
                'native_station_id_fallback': not bool(native_station),
                'period_metadata': 'not provided by this primary variable',
            }
            yield make_observation(
                asset,
                **common,
                channel=channel,
                variable=variable,
                statistic='maximum' if channel == 'windGust' else 'unknown',
                raw_value=raw_value,
                raw_value_text=_text(raw),
                raw_unit=units[channel],
                value=value,
                unit=unit,
                value_status=status,
                qc_status=qc_status,
                qc_known_failure=qc_failure,
                native_qc_json=native_qc,
                source_locator=_json(
                    {
                        'format': 'classic_netcdf',
                        'record_index': index,
                        'variable': channel,
                    }
                ),
                metadata_json=_json(provenance),
            )


def inflate(source, target):
    size = 0
    with gzip.open(source, 'rb') as compressed, target.open('xb') as decoded:
        while block := compressed.read(1024 * 1024):
            size += len(block)
            if size > MAX_INFLATED_BYTES:
                raise ValueError('MADIS NetCDF exceeds the inflated byte ceiling')
            decoded.write(block)
    validate_extent(target)


def normalize(source, target, hour, asset):
    with tempfile.TemporaryDirectory(dir=target.parent, prefix='.decode-') as directory:
        decoded = Path(directory) / 'hour.nc'
        staged = Path(directory) / 'hour.parquet'
        inflate(source, decoded)
        with netCDF4.Dataset(decoded) as dataset:
            reports = len(dataset.dimensions['recNum'])
            if not 0 <= reports <= MAX_REPORTS:
                raise ValueError('Unexpected MADIS report count')
            start = getattr(dataset, 'startTime', None)
            if start and utc(start) != hour:
                raise ValueError('MADIS startTime differs from the archive hour')
            columns = [
                *TEXT,
                'latitude',
                'longitude',
                'elevation',
                *CLOCKS,
                *MEASUREMENTS,
            ]
            for channel in MEASUREMENTS:
                columns.extend(
                    channel + suffix
                    for suffix in QC_SUFFIXES
                    if channel + suffix in dataset.variables
                )
            if any(dataset[name].dimensions[0:1] != ('recNum',) for name in columns):
                raise ValueError('A required variable is missing the report dimension')
            if not start and reports:
                clock = dataset['observationTime']
                lo, hi = netCDF4.date2num(
                    [hour, hour + timedelta(hours=1)],
                    clock.units,
                    calendar=getattr(clock, 'calendar', 'standard'),
                )
                if not np.ma.filled((clock[:] >= lo) & (clock[:] < hi), False).any():
                    raise ValueError(
                        'No observed clock binds this file to the archive hour'
                    )
            units = {
                name: _text(getattr(dataset[name], 'units', '')) or None
                for name in MEASUREMENTS
            }
            attrs = {name: _variable_metadata(dataset[name]) for name in MEASUREMENTS}
            with pq.ParquetWriter(staged, OBS_SCHEMA, compression='zstd') as writer:
                for first in range(0, reports, 2048):
                    rows = list(
                        rows_for_slice(
                            dataset,
                            columns,
                            first,
                            min(first + 2048, reports),
                            asset,
                            units,
                            attrs,
                        )
                    )
                    writer.write_table(table(rows))
        if pq.read_metadata(staged).num_rows != reports * len(MEASUREMENTS):
            raise ValueError('Parquet row count differs from the source report count')
        staged.rename(target)
    return reports


def describe(path, root):
    with path.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {
        'path': path.relative_to(root).as_posix(),
        'bytes': path.stat().st_size,
        'sha256': checksum,
    }


def capture_hour(hour, root, archive_dir, current):
    name = hour.strftime(FILE_FORMAT)
    archive_prefix = '' if current else hour.strftime('archive/%Y/%m/%d/')
    url = BASE + archive_prefix + 'LDAD/mesonet/netCDF/' + name
    raw = root / 'raw' / name
    if archive_dir:
        with (archive_dir / name).open('rb') as stream:
            body = stream.read(MAX_COMPRESSED_BYTES + 1)
    else:
        body = fetch(url, MAX_COMPRESSED_BYTES)
    if not 0 < len(body) <= MAX_COMPRESSED_BYTES:
        raise ValueError(f'Compressed input outside the archive limit for {name}')
    raw.write_bytes(body)
    source = {
        **describe(raw, root),
        'url': url,
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'acquisition': 'local_archive_copy' if archive_dir else 'noaa_https',
    }
    parquet = root / 'hourly' / name.replace('.gz', '.parquet')
    asset = {
        'source_id': 'noaa-madis',
        'sha256': source['sha256'],
        'captured_at': source['captured_at'],
    }
    reports = normalize(raw, parquet, hour, asset)
    return {
        'nominal_time': hour.strftime(DATE_FORMAT),
        'reports': reports,
        'source': source,
        'parquet': {
            **describe(parquet, root),
            'rows': reports * len(MEASUREMENTS),
            'columns': len(OBS_SCHEMA),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'output', type=Path, help='new directory for local source and Parquet files'
    )
    parser.add_argument(
        '--archive-dir',
        type=Path,
        help='local directory containing original NOAA hourly .gz files',
    )
    parser.add_argument(
        '--start', default=START, help='inclusive whole UTC archive hour'
    )
    parser.add_argument('--end', default=END, help='exclusive whole UTC archive hour')
    parser.add_argument(
        '--current',
        action='store_true',
        help='fetch the explicit hour from the live directory',
    )
    interval = parser.add_mutually_exclusive_group()
    interval.add_argument(
        '--max-hours', type=int, choices=range(1, 169), default=168, metavar='N'
    )
    interval.add_argument('--hour', help='one whole UTC hour')
    args = parser.parse_args()
    if args.current and (not args.hour or args.archive_dir):
        parser.error('--current needs --hour and fetches directly from NOAA')
    if args.hour:
        # Retain the declared interval for single-hour rehearsals inside it.
        hour = canonical_hour(args.hour)
        if args.current:
            args.start = args.hour
            args.end = (hour + timedelta(hours=1)).strftime(DATE_FORMAT)
        if hour not in source_hours(args.start, args.end):
            parser.error('choose a whole UTC hour within the declared archive interval')
        hours = [hour]
    else:
        hours = source_hours(args.start, args.end)[: args.max_hours]
    os.umask(0o077)
    args.output.mkdir(mode=0o700)
    (args.output / 'raw').mkdir()
    (args.output / 'hourly').mkdir()
    entries = []
    for hour in hours:
        entry = capture_hour(hour, args.output, args.archive_dir, args.current)
        entries.append(entry)
        print(f"{entry['nominal_time']}  {entry['reports']:,} reports", flush=True)
    manifest = {
        'schema': 'folia.madis-private-week-normalization/1',
        'status': (
            'complete'
            if len(entries) == len(source_hours(args.start, args.end))
            else 'partial'
        ),
        'range': {'start': args.start, 'end': args.end},
        'hours': entries,
    }
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
