"""Shared MADIS release-window and Parquet projection rules."""

from contextlib import closing
from datetime import datetime, timezone
from hashlib import file_digest
import json
import math

import duckdb
import pyarrow.parquet as pq


from release_window import DATE_FORMAT, source_hours

LABELS = {
    'air_temp': 'Air temperature',
    'air_temperature': 'Air temperature',
    'dew_point_temperature': 'Dew point',
    'relative_humidity': 'Relative humidity',
    'wind_speed': 'Wind speed',
    'wind_from_direction': 'Wind direction',
    'wind_direction': 'Wind direction',
    'wind_speed_of_gust': 'Wind gust',
    'wind_gust': 'Wind gust',
    'air_pressure': 'Air pressure',
    'air_pressure_at_mean_sea_level': 'Sea-level pressure',
    'precip_accum': 'Accumulated precipitation',
    'precip_rate': 'Precipitation rate',
    'precipitation_amount': 'Precipitation amount',
}
GEO = """station_key IS NOT NULL AND isfinite(latitude) AND isfinite(longitude)
          AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180"""


def json_value(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def rows_as_dict(cursor):
    names = [item[0] for item in cursor.description]
    return [
        dict(zip(names, map(json_value, row), strict=True)) for row in cursor.fetchall()
    ]


def snapshot_readings(db, path, variable=None):
    # Keep readings outside aggregate structs so signed zero survives.
    one_variable = 'AND variable = ?' if variable is not None else ''
    params = [str(path)] + ([variable] if variable is not None else [])
    rows = rows_as_dict(
        db.execute(
            f"""
        SELECT station_key AS key, observed_at AS "time", value, unit, variable
        FROM read_parquet(?) WHERE {GEO} {one_variable} AND isfinite(value)
          AND observed_at IS NOT NULL AND value_status = 'valid'
          AND qc_known_failure IS DISTINCT FROM TRUE
        QUALIFY row_number() OVER (
            PARTITION BY station_key, variable ORDER BY observed_at DESC, observation_id DESC NULLS FIRST
        ) = 1
        ORDER BY key, variable
    """,
            params,
        )
    )
    if variable is not None:
        for row in rows:
            row.pop('variable')
    return rows


def select_inputs(args):
    data = json.loads(args.manifest.read_text())
    if data['schema'] != 'folia.madis-private-week-normalization/1':
        raise ValueError('unexpected normalization manifest schema')
    start, end = data['range']['start'], data['range']['end']
    expected = {hour.strftime(DATE_FORMAT) for hour in source_hours(start, end)}
    paths = {}
    for hour in data['hours']:
        nominal, parquet = hour['nominal_time'], hour['parquet']
        if nominal in paths or nominal not in expected:
            raise ValueError('duplicate or out-of-window source hour')
        path = (args.manifest.parent / parquet['path']).resolve(strict=True)
        with path.open('rb') as stream:
            checksum = file_digest(stream, 'sha256').hexdigest()
        if path.stat().st_size != parquet['bytes'] or checksum != parquet['sha256']:
            raise ValueError(f'derived hour changed: {nominal}')
        paths[nominal] = path
    return (
        f'Full public MADIS feed · {len(paths)}/{len(expected)} normalized hours',
        start,
        end,
        paths,
    )


def json_bytes(payload):
    return json.dumps(payload, separators=(',', ':'), allow_nan=False).encode()


class Archive:
    def __init__(self, scope, start, end, paths, scratch):
        if not paths or len(paths) > 168:
            raise ValueError('viewer needs 1–168 normalized source hours')
        self.paths = {key: paths[key].resolve(strict=True) for key in sorted(paths)}
        self.db = duckdb.connect(
            config={
                'threads': 2,
                'memory_limit': '512MB',
                'temp_directory': str(scratch),
                'max_temp_directory_size': '5GB',
                'enable_external_access': 'true',
            }
        )
        self.files = list(map(str, self.paths.values()))

        for hour, path in self.paths.items():
            with closing(pq.ParquetFile(path)) as file:
                names = file.schema_arrow.names
                if (
                    'station_key' not in names
                    or 'source_body_sha256' not in names
                    or len(names) < 41
                ):
                    raise ValueError(f'unexpected Folia observation schema at {hour}')
        stations = rows_as_dict(
            self.db.execute(
                f"""
            SELECT station_key AS key, m.name, m.provider, m.lat, m.lon, m.elevation_m
            FROM (
              SELECT station_key, arg_max(
                struct_pack(name := coalesce(nullif(station_name, ''), station_id, station_key),
                  provider := provider_id, lat := latitude, lon := longitude, elevation_m := elevation_m),
                row(observed_at, observation_id)
              ) AS m
              FROM read_parquet(?) WHERE {GEO}
              GROUP BY station_key
            )
            ORDER BY key
        """,
                [self.files],
            )
        )
        variables = rows_as_dict(
            self.db.execute(
                """
            SELECT variable AS id, mode(unit) AS unit
              FROM read_parquet(?) WHERE variable IS NOT NULL
              GROUP BY variable ORDER BY variable
        """,
                [self.files],
            )
        )
        for entry in variables:
            entry['label'] = LABELS.get(
                entry['id'], entry['id'].replace('_', ' ').capitalize()
            )
        self.catalog = {
            'scope': scope,
            'start': start,
            'end': end,
            'stations': stations,
            'variables': variables,
            'provenance': 'NOAA MADIS Integrated Mesonet · local station data preparation',
        }
