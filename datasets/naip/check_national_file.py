#!/usr/bin/env python3
"""Pin and check the hosted national overview file (marks 1 and 2 of
research/catalog-presentation-20261117/criteria.md).

    python check_national_file.py --copy LOCAL.tif --out NEW.json

Reads overviews/national-latest.tif in full, unsigned, from data.source.coop into LOCAL.tif, compares
its size with the overview index's file:size, records its SHA-256, and checks HEAD, two byte ranges
and CORS. Writes NEW.json (refuses an existing path). Exit 0 only when every check passed.
"""
import argparse
import hashlib
import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone

URL = "https://data.source.coop/nthh/naip/overviews/national-latest.tif"
INDEX = "https://data.source.coop/nthh/naip/stac/naip-overviews.parquet"
ORIGIN = "https://browser.portolan-sdi.org"


def request(method, headers=None):
    req = urllib.request.Request(URL, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=120) as r:
        # r.headers looks names up without regard to case; a plain dict would not (r1 failed on that).
        return r.status, r.headers, (r.read() if method == "GET" else b"")


def index_size():
    sql = (f"select assets.image.\"file:size\" from read_parquet('{INDEX}') where id = 'national-latest'")
    out = subprocess.run(["duckdb", "-csv", "-noheader", "-c", sql], check=True, capture_output=True, text=True)
    return int(out.stdout.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--copy", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if os.path.exists(args.out) or os.path.exists(args.copy):
        raise SystemExit("Use new paths; earlier results are kept.")
    checks = {}
    digest, size = hashlib.sha256(), 0
    with urllib.request.urlopen(URL, timeout=600) as r, open(args.copy, "wb") as f:
        status = r.status
        while chunk := r.read(1 << 20):
            digest.update(chunk); f.write(chunk); size += len(chunk)
    expected = index_size()
    checks["national_file_pinned"] = "passed" if status == 200 and size == expected else "failed"
    status, headers, _ = request("HEAD")
    head_ok = status == 200 and int(headers.get("Content-Length", -1)) == size
    status, headers, body = request("GET", {"Range": "bytes=0-3"})
    first_ok = status == 206 and headers.get("Content-Range") == f"bytes 0-3/{size}" and body in (b"II*\x00", b"MM\x00*")
    status, headers, body = request("GET", {"Range": "bytes=-8"})
    last_ok = status == 206 and headers.get("Content-Range") == f"bytes {size - 8}-{size - 1}/{size}" and len(body) == 8
    status, headers, _ = request("GET", {"Range": "bytes=0-0", "Origin": ORIGIN})
    allow = headers.get("Access-Control-Allow-Origin")
    expose = [v.strip().lower() for v in (headers.get("Access-Control-Expose-Headers") or "").split(",")]
    cors_ok = allow in ("*", ORIGIN) and ("*" in expose or "content-range" in expose)
    checks["national_file_hosting"] = "passed" if head_ok and first_ok and last_ok and cors_ok else "failed"
    report = {"schema_version": 1, "url": URL, "checked_at": datetime.now(timezone.utc).isoformat(),
              "size_bytes": size, "index_size_bytes": expected, "sha256": digest.hexdigest(),
              "details": {"head": head_ok, "first_bytes": first_ok, "last_bytes": last_ok, "cors": cors_ok},
              "checks": checks, "status": "passed" if all(v == "passed" for v in checks.values()) else "failed"}
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1); f.write("\n")
    print(json.dumps(report))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
