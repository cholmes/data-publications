#!/usr/bin/env python3
"""Build the two index files of an index release from receipts and overview build results.

    python build_index_release.py --artifacts ROOT --out NEW_DIR

Run with the Python of the environment in index-env.lock.txt. ROOT is the folder of the
national run's captures (it holds `runs/` and `overviews/`); the inputs are named relative to
it, so the report holds no local path. Writes `naip.parquet`, `naip-overviews.parquet` and
`build.json` (commit, environment, every input's SHA-256, each output's size and SHA-256).
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = "https://data.source.coop/nthh/naip/"
OVERVIEW_RESULTS = "overviews/national/results/*-result.json"
NATIONAL_RESULT = "colour-balance/years/national/national-result.json"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def receipts_digest(root, dirs):
    """One SHA-256 over every receipt, in path order: each line is `relative path  sha256`."""
    digest, count = hashlib.sha256(), 0
    for d in dirs:
        for name in sorted(os.listdir(os.path.join(root, d))):
            if name.endswith(".json"):
                path = os.path.join(d, name)
                digest.update(f"{path}  {sha256(os.path.join(root, path))}\n".encode())
                count += 1
    return digest.hexdigest(), count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root, out = os.path.abspath(args.artifacts), os.path.abspath(args.out)
    if os.path.exists(out):
        sys.exit("Use a new output folder; earlier builds are kept.")
    os.makedirs(out)
    with open(os.path.join(HERE, "evidence", "receipt-dirs-62.json")) as f:
        dirs = json.load(f)
    results = sorted(os.path.relpath(p, root) for p in glob.glob(os.path.join(root, OVERVIEW_RESULTS)))
    results.append(NATIONAL_RESULT)
    quads = os.path.join(out, "naip.parquet")
    overviews = os.path.join(out, "naip-overviews.parquet")
    run = lambda *command: subprocess.run([sys.executable, *command], check=True, cwd=HERE)
    run("build_stac_index.py", quads, *[os.path.join(root, d) for d in dirs],
        "--overviews", FILES + "stac/naip-overviews.parquet")
    run("build_overview_index.py", quads, FILES + "overviews/", overviews,
        *[os.path.join(root, r) for r in results])
    digest, count = receipts_digest(root, dirs)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=HERE, capture_output=True, text=True, check=True).stdout
    import osgeo
    import pyarrow
    import pyproj
    report = {
        "schema_version": 1,
        "commit": commit,
        "builders_changed_since_commit": any(name in dirty for name in ("build_stac_index.py", "build_overview_index.py", "partial_years.py", "build_index_release.py")),
        "environment": {"lock_sha256": sha256(os.path.join(HERE, "index-env.lock.txt")), "python": sys.version.split()[0],
                        "gdal": osgeo.__version__, "pyarrow": pyarrow.__version__, "pyproj": pyproj.__version__},
        "inputs": {"receipt_dirs": len(dirs), "receipts": count, "receipts_sha256": digest,
                   "overview_results": {r: sha256(os.path.join(root, r)) for r in results}},
        "outputs": {os.path.basename(p): {"size_bytes": os.path.getsize(p), "sha256": sha256(p)} for p in (quads, overviews)},
    }
    with open(os.path.join(out, "build.json"), "w") as f:
        json.dump(report, f, indent=1)
        f.write("\n")
    print(json.dumps(report["outputs"], indent=1))


if __name__ == "__main__":
    main()
