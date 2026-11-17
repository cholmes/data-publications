"""Mark a display package prepared, after its checks have passed.

    finalize_display.py --display DIR --validation REPORT --browser REPORT

Requires both reports to have status "passed" and to name this package's archive by SHA-256. Copies
them into the package's reports, inventories every file and writes status "prepared" last.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from source import digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("display", "validation", "browser"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.display / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["status"] != "provisional":
        raise SystemExit("Only a provisional package can be finalised.")
    archive = {a["source_layer"]: digest(args.display / a["path"]) for a in manifest["assets"]}
    for label, path in (("validation", args.validation), ("browser", args.browser)):
        report = json.loads(path.read_text())
        if report.get("status") != "passed" or report.get("archives_sha256") != archive:
            raise SystemExit(f"The {label} report did not pass or is about another archive.")
        shutil.copyfile(path, args.display / "reports" / f"{label}.json")
    shutil.copyfile(manifest_path, args.display / "reports" / "provisional-manifest.json")
    manifest["status"] = "prepared"
    manifest["files"] = {str(p.relative_to(args.display)): {"sha256": digest(p), "size_bytes": p.stat().st_size}
                         for p in sorted(args.display.rglob("*")) if p.is_file() and p != manifest_path}
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "prepared", "manifest_sha256": digest(manifest_path), "files": len(manifest["files"])}))


if __name__ == "__main__":
    main()
