#!/usr/bin/env python3
"""The two hosting reports of the NAIP record, from the hosted checks of its stac/ files.

    python write_hosting_reports.py --stac CHECK.json --explorer EXPLORER.json --out-dir DIR

CHECK.json is check_hosted_stac.py's report (checks 1 to 6), EXPLORER.json is
hosted_explorer_check.mjs's (check 7). Writes DIR/flat-hosting.json, which the flat layout pins
(flat_publication.py), and DIR/hosting-report.json, which the catalogue pins
(publication_catalog.py). Each check is passed only where the source report says passed.
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RELEASE = "index-20261116-r5"
BASE = f"https://data.source.coop/nthh/naip/releases/{RELEASE}/"
CHECKS = ("anonymous_access", "range_requests", "cors", "asset_checksums", "subset_query", "catalog_links", "browser_render")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stac", required=True)
    parser.add_argument("--explorer", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    with open(args.stac) as f:
        stac = json.load(f)
    with open(args.explorer) as f:
        explorer = json.load(f)
    checks = {name: stac["checks"].get(name, "not_run") for name in CHECKS if name != "browser_render"}
    checks["browser_render"] = "passed" if explorer.get("status") == "passed" else "failed"
    status = "passed" if all(checks[name] == "passed" for name in CHECKS) else "failed"
    manifest = os.path.join(ROOT, "datasets/naip/source-coop/flat-20261117/manifest.json")
    snapshot = os.path.join(ROOT, f"datasets/naip/releases/{RELEASE}/catalog-input-r1/snapshot.json")
    with open(snapshot) as f:
        package_manifest = json.load(f)["package_manifest_sha256"]
    evidence = [{"path": os.path.relpath(os.path.abspath(p), ROOT), "sha256": sha256(p)} for p in (args.stac, args.explorer)]
    evidence.append({"path": "research/naip-index-20261117/replace-run-1/summary.json",
                     "sha256": sha256(os.path.join(ROOT, "research/naip-index-20261117/replace-run-1/summary.json"))})
    checked_at = datetime.now(timezone.utc).isoformat()
    flat = {"schema_version": 1, "dataset_id": "naip", "layout_id": "flat-20261117", "manifest_sha256": sha256(manifest),
            "checked_at": checked_at, "checks": checks, "status": status, "evidence": evidence,
            "criteria": "research/naip-index-20261117/hosting-criteria.md",
            "files": [{"filename": item["filename"], "status": item["status"], "sha256": item["sha256"], "size_bytes": item["size_bytes"]}
                      for item in stac["files"]]}
    catalogue = {"schema_version": 1, "dataset_id": "naip", "release": RELEASE, "package_manifest_sha256": package_manifest,
                 "package_base_url": BASE, "checked_at": checked_at, "checks": checks, "status": status, "evidence": evidence,
                 "note": ("The package base names the release's package layout; that prefix was never hosted. Every catalogue "
                          "address is rewritten to the files at stac/ (flat layout) or to the repository (support layout), and "
                          "the support layout refuses a catalogue that still names a releases/ address. The checks are those "
                          "of the stac/ files.")}
    os.makedirs(args.out_dir, exist_ok=True)
    for name, doc in (("flat-hosting.json", flat), ("hosting-report.json", catalogue)):
        with open(os.path.join(args.out_dir, name), "w") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")
    print(status, checks)


if __name__ == "__main__":
    main()
