#!/usr/bin/env python3
"""Run the four hosted checks of PUBLISHING.md on one published state-year.

Every request to the product is anonymous, because that is how a reader reaches the files.

    python3 check_hosted.py <receipts dir> <index.parquet> <out.json> \
        [--bucket us-west-2.opendata.source.coop] [--prefix nthh/naip/] [--every 50] [--least 20]

The sample reads (checks 2 and 3) are a download of every sampled file. They can be done
beside the bucket instead: `--list-samples keys.json` writes the keys this run would read and
stops; sample_hosted.py reads them in a task and writes a result; `--samples result.json`
then judges that result here in place of reading the files again.

Needs the aws CLI, GDAL's Python bindings and pyarrow. Exits 1 when a check fails; the
result file is written either way.
"""

import argparse
import json
import os
import subprocess
import sys

import pyarrow.parquet as pq

from sample_hosted import open_in_place, sha256_of

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


def sample_of(keys, every, least):
    """Every Nth key in name order, with N small enough to give at least `least` files."""
    return keys[::max(1, min(every, len(keys) // least))]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("receipts_dir")
    p.add_argument("index")
    p.add_argument("out")
    p.add_argument("--bucket", default="us-west-2.opendata.source.coop")
    p.add_argument("--prefix", default="nthh/naip/")
    p.add_argument("--every", type=int, default=50)
    p.add_argument("--least", type=int, default=20)
    p.add_argument("--list-samples", help="write the keys of the sample to this file and stop")
    p.add_argument("--samples", help="result of sample_hosted.py to judge in place of reading the files here")
    a = p.parse_args()

    if a.list_samples:
        keys = sorted(load_receipts(a.receipts_dir))
        with open(a.list_samples, "w") as f:
            json.dump({"bucket": a.bucket, "keys": sample_of(keys, a.every, a.least)}, f)
        print(len(sample_of(keys, a.every, a.least)), "of", len(keys), "files in the sample")
        return

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
    sample = sample_of(keys, a.every, a.least)
    remote = None
    if a.samples:
        with open(a.samples) as f:
            remote = json.load(f)
    bad_hash, bad_open, not_read = [], [], []
    for i, k in enumerate(sample):
        want = receipts[k].get("output_sha256")
        if remote is None:
            got, _ = sha256_of(f"https://s3.us-west-2.amazonaws.com/{a.bucket}/{k}")
            problems = open_in_place(gdal, a.bucket, k)
            print(f"sample {i + 1}/{len(sample)}", file=sys.stderr)
        elif k in remote["files"]:
            got, problems = remote["files"][k]["sha256"], remote["files"][k]["problems"]
        else:
            not_read.append({"key": k, "error": remote["errors"].get(k, "not read")})
            continue
        if got != want:
            bad_hash.append({"key": k, "receipt": want, "hosted": got})
        if problems:
            bad_open.append({"key": k, "problems": problems})
    result["sample"] = {"every": max(1, min(a.every, len(keys) // a.least)), "files": len(sample),
                        "read_from": "a task in us-west-2 (sample_hosted.py)" if remote else "this machine",
                        "not_read": not_read,
                        "sha256": {"mismatches": bad_hash, "pass": not bad_hash and not not_read},
                        "open_in_place": {"gdal": remote["gdal"] if remote else gdal.__version__,
                                          "problems": bad_open, "pass": not bad_open and not not_read}}

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
