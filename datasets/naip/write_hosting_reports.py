#!/usr/bin/env python3
"""The two hosting reports of the NAIP record, from the hosted checks of its stac/ files.

    python write_hosting_reports.py --stac CHECK.json --explorer EXPLORER.json --out-dir DIR \
        [--release ID --layout ID --replace-summary PATH --criteria PATH [--gti CHECK8.json]]

CHECK.json is check_hosted_stac.py's report (checks 1 to 6), EXPLORER.json is
hosted_explorer_check.mjs's (check 7). Writes DIR/flat-hosting.json, which the flat layout pins
(flat_publication.py), and DIR/hosting-report.json, which the catalogue pins
(publication_catalog.py). Each check is passed only where the source report says passed. The
defaults are those of release index-20261116-r5. With --gti, check 8 (a check_gti_open.py report) is
added and must pass too.
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CHECKS = ("anonymous_access", "range_requests", "cors", "asset_checksums", "subset_query", "catalog_links", "browser_render")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stac", required=True)
    parser.add_argument("--explorer", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--release", default="index-20261116-r5")
    parser.add_argument("--layout", default="flat-20261117")
    parser.add_argument("--replace-summary", default="research/naip-index-20261117/replace-run-1/summary.json")
    parser.add_argument("--criteria", default="research/naip-index-20261117/hosting-criteria.md")
    parser.add_argument("--gti")
    args = parser.parse_args()
    RELEASE, BASE = args.release, f"https://data.source.coop/nthh/naip/releases/{args.release}/"
    with open(args.stac) as f:
        stac = json.load(f)
    with open(args.explorer) as f:
        explorer = json.load(f)
    checks = {name: stac["checks"].get(name, "not_run") for name in CHECKS if name != "browser_render"}
    checks["browser_render"] = "passed" if explorer.get("status") == "passed" else "failed"
    sources = [args.stac, args.explorer]
    if args.gti:
        with open(args.gti) as f:
            checks["gti_open"] = "passed" if json.load(f).get("status") == "passed" else "failed"
        sources.append(args.gti)
    status = "passed" if all(v == "passed" for v in checks.values()) else "failed"
    manifest = os.path.join(ROOT, f"datasets/naip/source-coop/{args.layout}/manifest.json")
    snapshot = os.path.join(ROOT, f"datasets/naip/releases/{RELEASE}/catalog-input-r1/snapshot.json")
    with open(snapshot) as f:
        package_manifest = json.load(f)["package_manifest_sha256"]
    evidence = [{"path": os.path.relpath(os.path.abspath(p), ROOT), "sha256": sha256(p)} for p in sources]
    evidence.append({"path": args.replace_summary, "sha256": sha256(os.path.join(ROOT, args.replace_summary))})
    checked_at = datetime.now(timezone.utc).isoformat()
    flat = {"schema_version": 1, "dataset_id": "naip", "layout_id": args.layout, "manifest_sha256": sha256(manifest),
            "checked_at": checked_at, "checks": checks, "status": status, "evidence": evidence,
            "criteria": args.criteria,
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
