#!/usr/bin/env python3
"""Run the four hosted checks of PUBLISHING.md on one published state-year.

Every request to the product is anonymous, because that is how a reader reaches the files.

    python3 check_hosted.py <receipts dir> <index.parquet> <out.json> \
        [--bucket us-west-2.opendata.source.coop] [--prefix nthh/naip/] [--every 50] [--least 20]

Needs the aws CLI, GDAL's Python bindings and pyarrow. Exits 1 when a check fails; the
result file is written either way.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

import pyarrow.parquet as pq

gdal = None  # imported in main, after pyarrow has read the index: GDAL's own Arrow clashes otherwise


def load_receipts(receipts_dir):
    out = {}
    for name in sorted(os.listdir(receipts_dir)):
        if name.endswith(".json"):
            with open(os.path.join(receipts_dir, name)) as f:
                r = json.load(f)
            out[r["out_uri"].split("/", 3)[3]] = r
    return out


def listing(bucket, prefix):
    """Anonymous listing of a prefix as {key: size}."""
    found, token = {}, None
    while True:
        cmd = ["aws", "s3api", "list-objects-v2", "--no-sign-request", "--region", "us-west-2",
               "--bucket", bucket, "--prefix", prefix, "--output", "json"]
        if token:
            cmd += ["--starting-token", token]
        page = json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout or "{}")
        for o in page.get("Contents", []):
            found[o["Key"]] = o["Size"]
        token = page.get("NextToken")
        if not token:
            return found


def sha256_of(url):
    h = hashlib.sha256()
    with urllib.request.urlopen(url) as resp:
        while chunk := resp.read(1 << 22):
            h.update(chunk)
    return h.hexdigest()


def open_in_place(bucket, key):
    """Problems found opening the file over /vsis3/; an empty list is a pass."""
    problems = []
    ds = gdal.Open(f"/vsis3/{bucket}/{key}")
    structure = ds.GetMetadata("IMAGE_STRUCTURE")
    if structure.get("LAYOUT") != "COG":
        problems.append(f"layout {structure.get('LAYOUT')}")
    if structure.get("COMPRESSION") not in ("JPEG", "YCbCr JPEG"):
        problems.append(f"compression {structure.get('COMPRESSION')}")
    band = ds.GetRasterBand(1)
    if band.GetOverviewCount() < 1:
        problems.append("no overview")
    else:
        ov = band.GetOverview(band.GetOverviewCount() - 1)
        if ov.ReadRaster(0, 0, min(512, ov.XSize), min(512, ov.YSize)) is None:
            problems.append("overview read failed")
    if ds.ReadRaster(ds.RasterXSize // 2, ds.RasterYSize // 2, 512, 512) is None:
        problems.append("full-resolution read failed")
    return problems


def main():
    p = argparse.ArgumentParser()
    p.add_argument("receipts_dir")
    p.add_argument("index")
    p.add_argument("out")
    p.add_argument("--bucket", default="us-west-2.opendata.source.coop")
    p.add_argument("--prefix", default="nthh/naip/")
    p.add_argument("--every", type=int, default=50)
    p.add_argument("--least", type=int, default=20)
    a = p.parse_args()

    rows = {r["path"]: r for r in pq.read_table(a.index, columns=["path", "bytes", "sha256"]).to_pylist()}
    global gdal
    from osgeo import gdal
    gdal.UseExceptions()
    gdal.SetConfigOption("AWS_NO_SIGN_REQUEST", "YES")
    gdal.SetConfigOption("AWS_REGION", "us-west-2")

    receipts = load_receipts(a.receipts_dir)
    keys = sorted(receipts)
    state_year = os.path.commonprefix(keys).rsplit("/", 1)[0] + "/"
    result = {"bucket": a.bucket, "prefix": state_year, "receipts": len(keys),
              "runs": sorted({r["run_id"] for r in receipts.values()})}

    # 1. every file is there at its size
    listed = listing(a.bucket, state_year)
    wrong_size = [k for k in keys if k in listed and listed[k] != receipts[k]["output_bytes"]]
    result["listing"] = {
        "listed": len(listed), "bytes": sum(listed.values()),
        "missing": sorted(set(keys) - set(listed)), "extra": sorted(set(listed) - set(keys)),
        "wrong_size": wrong_size}
    result["listing"]["pass"] = not (result["listing"]["missing"] or result["listing"]["extra"] or wrong_size)

    # 2 and 3. a sample is the bytes that were made, and opens in place
    step = max(1, min(a.every, len(keys) // a.least))
    sample = keys[::step]
    bad_hash, bad_open = [], []
    for i, k in enumerate(sample):
        want = receipts[k].get("output_sha256")
        got = sha256_of(f"https://s3.us-west-2.amazonaws.com/{a.bucket}/{k}")
        if got != want:
            bad_hash.append({"key": k, "receipt": want, "hosted": got})
        problems = open_in_place(a.bucket, k)
        if problems:
            bad_open.append({"key": k, "problems": problems})
        print(f"sample {i + 1}/{len(sample)}", file=sys.stderr)
    result["sample"] = {"every": step, "files": len(sample),
                        "sha256": {"mismatches": bad_hash, "pass": not bad_hash},
                        "open_in_place": {"gdal": gdal.__version__, "problems": bad_open, "pass": not bad_open}}

    # 4. the index matches
    strip = len(a.prefix)
    differ = [k for k in keys if k[strip:] not in rows
              or rows[k[strip:]]["bytes"] != receipts[k]["output_bytes"]
              or rows[k[strip:]]["sha256"] != receipts[k].get("output_sha256")]
    result["index"] = {"rows": len(rows), "differ": differ,
                       "pass": len(rows) == len(listed) and not differ}

    result["pass"] = all([result["listing"]["pass"], result["sample"]["sha256"]["pass"],
                          result["sample"]["open_in_place"]["pass"], result["index"]["pass"]])
    with open(a.out, "w") as f:
        json.dump(result, f, indent=1)
        f.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "listing"} | {
        "listing": {k: (len(v) if isinstance(v, list) else v) for k, v in result["listing"].items()}}, indent=1))
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
