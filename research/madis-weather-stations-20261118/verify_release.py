#!/usr/bin/env python3
"""Verify the public MADIS release and read one station with an exact byte range."""

import argparse
import gzip
import hashlib
import io
import json
from urllib.request import Request, urlopen


RELEASE = (
    "https://data.source.coop/nthh/weather-stations/releases/madis-week/"
    "be36afc267791ce19b9822372e3d7d61f6ea4df51d9d1b99430f27f720705ecb/"
)
MANIFEST_SHA256 = "f91229cc093b798781ac291230060bbd43593f9ee646c591d623b952b17d1550"
MAP_PATH = "data/map.json.gz"
DEFAULT_KEY = "noaa-madis:MesoWest:UTBTN"
MIB = 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bounded_body(response, limit):
    data = response.read(limit + 1)
    require(len(data) <= limit, "Response exceeds the expected limit")
    return data


def get(path, limit, byte_range=None, total=None):
    url = RELEASE + path
    headers = {
        "Accept-Encoding": "identity",
        "User-Agent": "Weather-station-release-verifier/1",
    }
    if byte_range is not None:
        start, end = byte_range
        headers["Range"] = f"bytes={start}-{end}"

    with urlopen(Request(url, headers=headers), timeout=30) as response:
        require(response.geturl() == url, "Unexpected redirect")
        require(response.headers.get("Content-Encoding", "identity") == "identity",
                "Expected original compressed object bytes")
        if byte_range is None:
            require(response.status == 200, "Expected an ordinary object response")
        else:
            require(response.status == 206, "Expected HTTP 206 for the station range")
            require(response.headers.get("Content-Range") == f"bytes {start}-{end}/{total}",
                    "Station Content-Range differs from the index")
            require(response.headers.get("Content-Length") == str(end - start + 1),
                    "Station Content-Length differs from the index")
        return bounded_body(response, limit)


def checked_json(data, expected):
    require(hashlib.sha256(data).hexdigest() == expected, "Manifest checksum differs")
    return json.loads(data)


def gzip_json(compressed, limit):
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as decoded:
        return json.loads(bounded_body(decoded, limit))


def verify(station_key):
    manifest = checked_json(get("manifest.json", MIB), MANIFEST_SHA256)
    require(manifest["schema"] == "folia.madis-source-week/1", "Unexpected manifest schema")
    require(manifest["source"]["source_hours"] == 168, "Expected 168 published source hours")
    files = {item["path"]: item for item in manifest["files"]}
    descriptor = files[MAP_PATH]
    require(0 < descriptor["bytes"] <= 8 * MIB, "Map exceeds its compressed size limit")

    compressed = get(MAP_PATH, descriptor["bytes"])
    require(len(compressed) == descriptor["bytes"], "Map byte count differs")
    require(hashlib.sha256(compressed).hexdigest() == descriptor["sha256"], "Map checksum differs")
    snapshot = gzip_json(compressed, 128 * MIB)
    require(snapshot["schema"] == "folia.madis-station-week-map/1", "Unexpected map schema")
    require(snapshot["source_hours"] == 168, "Map does not cover the complete release window")

    stations = snapshot["stations"]
    matches = [i for i, station in enumerate(stations) if station["key"] == station_key]
    require(len(matches) == 1, "Station key is absent or ambiguous")
    station_index = matches[0]
    part, offset, length = snapshot["history_index"][station_index]
    require(type(part) is int and 0 <= part <= 999, "Invalid history part index")
    require(type(offset) is int and type(length) is int and offset >= 0 and 0 < length <= 4 * MIB,
            "Invalid station history range")
    path = f"data/history/part-{part:03d}.bin"
    total = files[path]["bytes"]
    require(offset + length <= total, "Station range exceeds the history pack")

    body = get(path, length, byte_range=(offset, offset + length - 1), total=total)
    require(len(body) == length, "Station body byte count differs")
    history = gzip_json(body, 64 * MIB)
    require(history["schema"] == "folia.madis-station-week-history/1", "Unexpected history schema")
    require(history["key"] == station_key, "Decoded history identifies another station")
    rows = history["rows"]
    require(isinstance(rows, list) and all(isinstance(row, list) and len(row) == 7 for row in rows),
            "Unexpected history row layout")

    clocks = [row[0] for row in rows if row[0] is not None]
    return {
        "status": "verified",
        "station_key": station_key,
        "source_hours": 168,
        "published_station_keys": len(stations),
        "range": f"bytes={offset}-{offset + length - 1}",
        "pack": path,
        "history_bytes": length,
        "history_rows": len(rows),
        "numeric_rows": sum(type(row[3]) in (int, float) for row in rows),
        "first_observation_utc": min(clocks, default=None),
        "last_observation_utc": max(clocks, default=None),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("station_key", nargs="?", default=DEFAULT_KEY)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.station_key), indent=2))
    except (KeyError, OSError, TypeError, ValueError) as error:
        parser.exit(1, f"Verification failed: {error}\n")
