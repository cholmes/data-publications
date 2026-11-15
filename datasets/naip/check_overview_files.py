#!/usr/bin/env python3
"""Run check_overview_against_quads.py on every overview file that has a build result.

    python3 check_overview_files.py <folder of *-result.json> <base url of the files> <naip stac index.parquet> \
        [--sample 6] [--at-once 4]

A file is named <state>-<year>-utm<zone>. Writes <name>-against-quads.json beside each
result and skips the ones already there, so it can be run again after a failure. Prints one
line per file and exits 1 if any check could not be run.
"""
import argparse
import concurrent.futures
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def check(name, a):
    out = os.path.join(a.folder, name + "-against-quads.json")
    if not (os.path.exists(out) and os.path.getsize(out)):
        state, year, zone = name.split("-")
        done = subprocess.run([sys.executable, os.path.join(HERE, "check_overview_against_quads.py"),
                               f"{a.base.rstrip('/')}/{name}.tif", a.index, state, year,
                               "--zone", str(26900 + int(zone[3:])), "--sample", str(a.sample)],
                              capture_output=True, text=True)
        if done.returncode != 0:
            return name, None, done.stderr.strip().splitlines()[-1:]
        with open(out, "w") as f:
            f.write(done.stdout)
    with open(out) as f:
        return name, json.load(f), None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("folder")
    p.add_argument("base")
    p.add_argument("index")
    p.add_argument("--sample", type=int, default=6)
    p.add_argument("--at-once", type=int, default=4)
    a = p.parse_args()
    names = sorted(os.path.basename(path)[:-len("-result.json")] for path in glob.glob(os.path.join(a.folder, "*-result.json")))
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(a.at_once) as pool:
        for name, r, error in pool.map(lambda n: check(n, a), names):
            if r is None:
                failed += 1
                print(name, "not checked:", error, flush=True)
            else:
                print(name, r["quads_sampled"], "quads", r["blocks"], "blocks", r["blocks_better_moved_by_one_pixel"], "moved,",
                      "lowest", r["psnr_db"]["lowest"], "median", r["psnr_db"]["median"], flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
