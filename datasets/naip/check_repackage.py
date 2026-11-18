#!/usr/bin/env python3
"""Checks 1 and 13 of index release r8 (index-package-plan.md, addendum for r8).

    python check_repackage.py --index-dir DIR --fgb-dir FGB --reference RELEASE_DIR --out NEW_FILE

DIR holds the package's naip.parquet and naip-overviews.parquet; FGB the hosted naip.gti.fgb and
naip-overviews.gti.fgb (downloaded beforehand); RELEASE_DIR the earlier release whose
source-fidelity.json gives the SHA-256 the files must have. Run with a Python whose GDAL writes
FlatGeobuf (the naip-index environment).

1. Both index files have the SHA-256 and size in the reference release's source-fidelity.json, and the
   hosted stac/ files read anonymously have the same SHA-256.
13. check_gti_fgb.py passes on the hosted pair against the two index files, and build_gti_fgb.py run
    on them gives the hosted pair byte for byte.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
HOSTED = "https://data.source.coop/nthh/naip/stac/"
ASSETS = {"quads": "naip.parquet", "overviews": "naip-overviews.parquet"}
FGB = ("naip.gti.fgb", "naip-overviews.gti.fgb")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_url(url):
    digest, size = hashlib.sha256(), 0
    with urllib.request.urlopen(url, timeout=120) as response:
        for block in iter(lambda: response.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-dir", required=True)
    parser.add_argument("--fgb-dir", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if os.path.exists(args.out):
        sys.exit("Use a new output path; earlier results are kept.")
    with open(os.path.join(args.reference, "source-fidelity.json")) as f:
        expected = {a["asset_id"]: a for a in json.load(f)["assets"]}

    same = {}
    for asset, name in ASSETS.items():
        path = os.path.join(args.index_dir, name)
        local = {"sha256": sha256_file(path), "size_bytes": os.path.getsize(path)}
        hosted_sha, hosted_size = sha256_url(HOSTED + name)
        same[name] = {"local": local, "hosted": {"sha256": hosted_sha, "size_bytes": hosted_size},
                      "reference": {k: expected[asset][k] for k in ("sha256", "size_bytes")},
                      "passed": local == {k: expected[asset][k] for k in ("sha256", "size_bytes")}
                      == {"sha256": hosted_sha, "size_bytes": hosted_size}}

    checker = subprocess.run([sys.executable, os.path.join(HERE, "check_gti_fgb.py"), args.index_dir, args.fgb_dir],
                             capture_output=True, text=True)
    check = json.loads(checker.stdout) if checker.stdout.strip().startswith("{") else {"error": checker.stderr[-2000:]}
    with tempfile.TemporaryDirectory() as rebuilt:
        builder = subprocess.run([sys.executable, os.path.join(HERE, "build_gti_fgb.py"), args.index_dir, rebuilt],
                                 capture_output=True, text=True)
        rebuild = {name: {"rebuilt": sha256_file(os.path.join(rebuilt, name)) if builder.returncode == 0 else None,
                          "hosted": sha256_file(os.path.join(args.fgb_dir, name))} for name in FGB}
    for item in rebuild.values():
        item["passed"] = item["rebuilt"] == item["hosted"]

    passed_1 = all(v["passed"] for v in same.values())
    passed_13 = checker.returncode == 0 and not check.get("failures") and builder.returncode == 0 and all(v["passed"] for v in rebuild.values())
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True).stdout.strip()
    from osgeo import gdal
    report = {
        "schema_version": 1,
        "plan": "datasets/naip/index-package-plan.md, addendum for r8, checks 1 and 13",
        "commit": commit,
        "gdal": gdal.__version__,
        "1_same_bytes": {"files": same, "passed": passed_1},
        "13_fgb_pair": {"check_gti_fgb": check, "rebuild_byte_identical": rebuild, "passed": passed_13},
        "status": "passed" if passed_1 and passed_13 else "failed",
    }
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1)
        f.write("\n")
    print(json.dumps({"1": passed_1, "13": passed_13, "status": report["status"]}))
    sys.exit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
