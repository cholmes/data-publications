"""Use whole UTC source hours and a bounded half-open release interval."""

from datetime import datetime, timedelta, timezone

START = '2026-11-09T00:00:00Z'
END = '2026-11-16T00:00:00Z'
DATE_FORMAT = '%Y-%m-%dT%H:00:00Z'


def canonical_hour(value):
    stamp = datetime.strptime(value, DATE_FORMAT).replace(tzinfo=timezone.utc)
    if stamp.strftime(DATE_FORMAT) != value:
        raise ValueError('Use an exact whole UTC hour')
    return stamp


def source_hours(start, end):
    first, stop = canonical_hour(start), canonical_hour(end)
    hour = timedelta(hours=1)
    count = (stop - first) // hour
    if not 1 <= count <= 168:
        raise ValueError('Choose an increasing interval of 1–168 UTC hours')
    return [first + index * hour for index in range(count)]
