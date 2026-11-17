#!/usr/bin/env python3
"""Keep the exact bytes of every workflow file the Census releases pin by commit.

    python3 datasets/us-census-places/provenance/export.py

The analytic release (cb2023-r1) and the display builds name the commit they were built from
and the SHA-256 of their workflow files (build-manifest.json, build-report.json). Files the
packager added later are carried as snapshots inside each hosted package and are not needed
here. Those commits may not survive a history rewrite, so each pinned file is copied from Git at its commit into blobs/<sha256>, and index.json binds the
commit and path to its size and hash. Run while the commits exist; a file whose bytes at the
commit differ from the hash the release recorded stops the export.
"""
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = HERE.parent
ROOT = DATASET.parents[1]
PREFIX = "datasets/us-census-places/"


def git_bytes(commit, path):
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True, check=True).stdout


def pins():
    """(commit, repository path, recorded sha256 or None, snapshot label)."""
    out = []
    spec = json.loads((DATASET / "releases/cb2023-r1/package-spec.json").read_text())
    manifest = json.loads((DATASET / "releases/cb2023-r1/build-manifest.json").read_text())
    commit = spec["code_revision"]
    if manifest["created_from_commit"] != commit:
        raise SystemExit("cb2023-r1: build manifest and package spec name different commits")
    recorded = {PREFIX + name if "/" not in name else name: sha for name, sha in manifest["workflow_files"].items()}
    for path, sha in recorded.items():
        out.append((commit, path, sha, "cb2023-r1"))
    for report in sorted(DATASET.glob("display/*/**/build-report.json")) + sorted(DATASET.glob("display/*/build-report.json")):
        data = json.loads(report.read_text())
        label = report.relative_to(DATASET / "display").parts[0]
        for name, sha in data["workflow_files"].items():
            out.append((data["created_from_commit"], PREFIX + name, sha, label))
    return sorted(set(out))


def main():
    (HERE / "blobs").mkdir(exist_ok=True)
    files = []
    for commit, path, recorded, label in pins():
        raw = git_bytes(commit, path)
        digest = hashlib.sha256(raw).hexdigest()
        if recorded is not None and recorded != digest:
            raise SystemExit(f"{commit[:10]}:{path} is {digest}, the release recorded {recorded}")
        (HERE / "blobs" / digest).write_bytes(raw)
        files.append({"path": path, "git_revision": commit, "snapshot": label, "bytes": len(raw),
                      "sha256": digest, "blob": f"blobs/{digest}"})
    index = {"schema_version": 1,
             "purpose": "Exact bytes of the workflow files the Census releases pin by commit; paths and revisions name the original snapshots.",
             "files": files}
    (HERE / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    print(len(files), "files,", len({f["sha256"] for f in files}), "blobs")


if __name__ == "__main__":
    main()
