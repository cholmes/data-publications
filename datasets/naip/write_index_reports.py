#!/usr/bin/env python3
"""The two reports the shared packager needs, from an index release's builds and check.

    python write_index_reports.py --release-dir DIR --build A --build B --clean-build C --check CHECK.json

Writes DIR/source-fidelity.json (the validator's report, bound to the two files) and
DIR/clean-rebuild.json (two builds from the commit and one from a clean checkout of it, which
must all give the same bytes), and copies the first build's build.json and the check to DIR as
build-manifest.json and check.json. The status of each is passed only when its checks passed.
"""
import argparse
import json
import os
import shutil

ASSETS = {"quads": "naip.parquet", "overviews": "naip-overviews.parquet"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--build", action="append", required=True)
    parser.add_argument("--clean-build", required=True)
    parser.add_argument("--check", required=True)
    args = parser.parse_args()
    builds = []
    for folder in args.build + [args.clean_build]:
        with open(os.path.join(folder, "build.json")) as f:
            builds.append(json.load(f))
    with open(args.check) as f:
        check = json.load(f)
    first = builds[0]["outputs"]
    assets = [{"asset_id": asset, "sha256": first[name]["sha256"], "size_bytes": first[name]["size_bytes"]} for asset, name in ASSETS.items()]
    same = all(b["outputs"] == builds[0]["outputs"] for b in builds)
    one_commit = len({b["commit"] for b in builds}) == 1 and not any(b["builders_changed_since_commit"] for b in builds)
    rebuild = {"status": "passed" if same and one_commit else "failed", "assets": assets,
               "evidence": {"commit": builds[0]["commit"], "builds": len(args.build), "clean_checkout_builds": 1,
                            "byte_identical": same, "same_commit_unchanged_builders": one_commit,
                            "environments": [b["environment"] for b in builds]}}
    checked = check["release_files"]
    bound = all(checked[name] == first[name] for name in ASSETS.values())
    fidelity = {"status": "passed" if check["status"] == "passed" and bound else "failed", "assets": assets,
                "evidence": {"validator": "datasets/naip/check_index_release.py", "report": "check.json",
                             "bound_to_these_files": bound, "checks": {k: v["passed"] for k, v in check["checks"].items()},
                             "receipts": check["receipts"], "listing": check["listing"],
                             "left_out_state_years": check["left_out_state_years"]}}
    os.makedirs(args.release_dir, exist_ok=True)
    for name, doc in (("clean-rebuild.json", rebuild), ("source-fidelity.json", fidelity)):
        path = os.path.join(args.release_dir, name)
        if os.path.exists(path):
            raise SystemExit(f"{path} exists; reports are kept.")
        with open(path, "w") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")
    shutil.copyfile(os.path.join(args.build[0], "build.json"), os.path.join(args.release_dir, "build-manifest.json"))
    shutil.copyfile(args.check, os.path.join(args.release_dir, "check.json"))
    print(rebuild["status"], fidelity["status"])


if __name__ == "__main__":
    main()
