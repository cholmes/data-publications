#!/usr/bin/env python3
"""Checks 1 to 6 of research/naip-index-20261117/hosting-criteria.md on the hosted stac/ files.

    python check_hosted_stac.py --release-dir DIR --out NEW_FILE [--collection catalog/naip/collection.json]

DIR holds the release's files (assets/quads.parquet, assets/overviews.parquet and the two field
dictionaries under metadata/). Reads only anonymously through data.source.coop. Without
--collection, check 6 is reported as not run.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

import duckdb

BASE = "https://data.source.coop/nthh/naip/"
FILES = {"stac/naip.parquet": "assets/quads.parquet", "stac/naip-overviews.parquet": "assets/overviews.parquet",
         "stac/naip.fields.json": "metadata/quads-field-dictionary.json",
         "stac/naip-overviews.fields.json": "metadata/overviews-field-dictionary.json"}
ORIGIN = "https://example.org"
WINDOWS = {"stac/naip.parquet": [-111.70, 40.50, -111.50, 40.65], "stac/naip-overviews.parquet": [-114.1, 36.9, -109.0, 42.1]}
QUAD_ROWS = 245554
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def request(url, method="GET", headers=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, b""


def ids_in(source, window):
    xmin, ymin, xmax, ymax = window
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    rows = con.execute(f"SELECT id FROM read_parquet('{source}') WHERE bbox.xmax >= ? AND bbox.xmin <= ? AND bbox.ymax >= ? AND bbox.ymin <= ? ORDER BY id",
                       [xmin, xmax, ymin, ymax]).fetchall()
    return [r[0] for r in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--collection")
    args = parser.parse_args()
    if os.path.exists(args.out):
        sys.exit("Use a new output path; earlier results are kept.")
    files, checks = [], {}
    access = checksums = ranges = cors = True
    for key, local in FILES.items():
        with open(os.path.join(args.release_dir, local), "rb") as f:
            want = f.read()
        status, _, body = request(BASE + key)
        same = status == 200 and len(body) == len(want) and hashlib.sha256(body).hexdigest() == hashlib.sha256(want).hexdigest()
        access &= status == 200
        checksums &= same
        size = len(want)
        probes = [(0, 3), (size - 8, size - 1)] if key.endswith(".parquet") else [(0, 0)]
        range_results = []
        for start, end in probes:
            s, h, b = request(BASE + key, headers={"Range": f"bytes={start}-{end}"})
            ok = s == 206 and h.get("content-range") == f"bytes {start}-{end}/{size}" and len(b) == end - start + 1
            if key.endswith(".parquet"):
                ok &= (b == b"PAR1") if start == 0 else (b[-4:] == b"PAR1")
            range_results.append({"range": f"{start}-{end}", "status": s, "content_range": h.get("content-range"), "passed": ok})
            ranges &= ok
        s, h, _ = request(BASE + key, headers={"Origin": ORIGIN, "Range": "bytes=0-0"})
        allow, expose = h.get("access-control-allow-origin"), h.get("access-control-expose-headers", "")
        cors_ok = allow in ("*", ORIGIN) and (expose.strip() == "*" or "content-range" in [e.strip().lower() for e in expose.split(",")])
        cors &= cors_ok
        files.append({"filename": key, "status": "verified" if same else "mismatch", "http_status": status,
                      "size_bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "ranges": range_results,
                      "cors": {"allow_origin": allow, "expose_headers": expose, "passed": cors_ok}})
    checks["anonymous_access"], checks["asset_checksums"] = access, checksums
    checks["range_requests"], checks["cors"] = ranges, cors

    subset = []
    for key, window in WINDOWS.items():
        hosted, local = ids_in(BASE + key, window), ids_in(os.path.join(args.release_dir, FILES[key]), window)
        subset.append({"filename": key, "window": window, "hosted_rows": len(hosted), "local_rows": len(local),
                       "equal": hosted == local and len(hosted) > 0})
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    count = con.execute(f"SELECT count(*) FROM read_parquet('{BASE}stac/naip.parquet')").fetchone()[0]
    checks["subset_query"] = all(s["equal"] for s in subset) and count == QUAD_ROWS

    links = None
    if args.collection:
        with open(args.collection) as f:
            collection = json.load(f)
        hrefs = sorted({a["href"] for a in collection.get("assets", {}).values() if isinstance(a, dict) and isinstance(a.get("href"), str)}
                       | {l["href"] for l in collection.get("links", []) if isinstance(l.get("href"), str)})
        links = []
        for href in hrefs:
            if href.startswith("https://data.source.coop/"):
                s, _, _ = request(href, method="HEAD")
                links.append({"href": href, "kind": "source", "status": s, "passed": s == 200})
            elif href.startswith("https://raw.githubusercontent.com/nthh/data-publications/"):
                revision, path = href.split("/", 6)[5], href.split("/", 6)[6]
                shown = subprocess.run(["git", "show", f"{revision}:{path}"], cwd=REPO, capture_output=True)
                links.append({"href": href, "kind": "git", "exists_at_revision": shown.returncode == 0,
                              "sha256": hashlib.sha256(shown.stdout).hexdigest() if shown.returncode == 0 else None,
                              "passed": shown.returncode == 0})
        checks["catalog_links"] = all(l["passed"] for l in links) and any(l["kind"] == "source" for l in links)

    report = {"schema_version": 1, "criteria": "research/naip-index-20261117/hosting-criteria.md", "base": BASE,
              "checks": {k: ("passed" if v else "failed") for k, v in checks.items()},
              "files": files, "subset_query": subset, "quad_rows_hosted": count, "catalog_links": links}
    if links is None:
        report["checks"]["catalog_links"] = "not_run"
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1)
        f.write("\n")
    print(json.dumps(report["checks"]))


if __name__ == "__main__":
    main()
