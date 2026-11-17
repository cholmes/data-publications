"""Compare a release with a second build of the same commit made in a clean checkout.

    compare_rebuild.py --release DIR --rebuild DIR --report NEW_FILE

Passes when every GeoParquet file is byte-identical and both builds name the same commit with no
uncommitted changes. The report has the shape the shared packager expects of a clean-rebuild report.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from source import LAYERS, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("release", "rebuild", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise SystemExit("Use a new report path; earlier reports are kept.")
    first, second = (json.loads((d / "build-manifest.json").read_text()) for d in (args.release, args.rebuild))
    assets, problems = [], []
    for asset in LAYERS:
        a, b = (d / "data" / f"{asset}.parquet" for d in (args.release, args.rebuild))
        one, two = digest(a), digest(b)
        if one != two:
            problems.append(f"{asset}: {one} and {two}")
        assets.append({"asset_id": asset, "sha256": one, "size_bytes": a.stat().st_size, "rebuild_sha256": two})
    commits = [first["created_from_commit"], second["created_from_commit"]]
    if commits[0] != commits[1] or "+uncommitted" in commits[0]:
        problems.append(f"builds name commits {commits}")
    if first["workflow_files"] != second["workflow_files"]:
        problems.append("workflow file hashes differ between the builds")
    report = {"status": "failed" if problems else "passed", "assets": assets,
              "evidence": {"commit": commits[0], "tool_versions": [first["tool_versions"], second["tool_versions"]],
                           "problems": problems}}
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True, indent=2))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
