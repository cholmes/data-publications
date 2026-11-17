#!/usr/bin/env python3
"""Put a few exact files at fixed keys of one product, replacing a known object only.

    python replace.py --plan PLAN.json --data-root DIR --output NEW_DIR \
        [--execute --credential-helper PATH --expected-plan-sha256 SHA]

A plan names, for each object, its key, the local file (relative to --data-root), the file's
size and SHA-256, its content type, and `replaces`: the size and SHA-256 of the object it
replaces, or null for a new key. Without --execute the plan is checked, every local file is
hashed, and every key is read anonymously: a replaced object must have the stated bytes and a
new key must be absent. With --execute each object is checked the same way just before it is
written; a replacement is written only if its ETag is unchanged since that check (If-Match),
a new key only if it is still absent (If-None-Match), and every written object is read back in
full and must have the planned SHA-256. Nothing is deleted. One receipt per object is written.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import urllib.error
import urllib.request

from upload import ALLOWED_PRODUCTS, BUCKET, ENDPOINT, S3Session, UploadError, _head, _remote_error

SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_BYTES = 256 * 1024 * 1024
TYPES = {".parquet": "application/vnd.apache.parquet", ".json": "application/json", ".md": "text/markdown"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_plan(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    plan = json.loads(raw)
    product = plan.get("product_id")
    if plan.get("schema_version") != 1 or plan.get("owner") != BUCKET or product not in ALLOWED_PRODUCTS:
        raise UploadError("plan identity is not an allowed product of this owner")
    entries = plan.get("objects")
    if not isinstance(entries, list) or not entries:
        raise UploadError("plan has no objects")
    keys = set()
    for entry in entries:
        key = entry.get("object_key")
        parts = PurePosixPath(key).parts if isinstance(key, str) else ()
        if (not parts or parts[0] != product or len(parts) < 2 or key in keys or "\\" in key
                or any(p in ("", ".", "..") or p.startswith(".") for p in parts)):
            raise UploadError(f"unsafe or repeated object key: {key!r}")
        keys.add(key)
        local = entry.get("local_path")
        if not isinstance(local, str) or PurePosixPath(local).is_absolute() or any(p in ("", ".", "..") for p in local.split("/")):
            raise UploadError(f"unsafe local path for {key}")
        if TYPES.get(PurePosixPath(key).suffix) != entry.get("content_type"):
            raise UploadError(f"content type does not follow the key's extension: {key}")
        if not SHA256.fullmatch(str(entry.get("sha256"))) or type(entry.get("size_bytes")) is not int or not 0 < entry["size_bytes"] <= MAX_BYTES:
            raise UploadError(f"invalid size or SHA-256 for {key}")
        old = entry.get("replaces", "missing")
        if old == "missing" or (old is not None and (not isinstance(old, dict) or not SHA256.fullmatch(str(old.get("sha256")))
                                                     or type(old.get("size_bytes")) is not int)):
            raise UploadError(f"replaces must be null or {{sha256, size_bytes}} for {key}")
    return plan, sha256_bytes(raw)


def local_file(root: Path, entry: dict) -> bytes:
    path = (root / entry["local_path"])
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise UploadError(f"local file missing or outside the data root: {entry['local_path']}")
    data = path.read_bytes()
    if len(data) != entry["size_bytes"] or sha256_bytes(data) != entry["sha256"]:
        raise UploadError(f"local size or SHA-256 differs from plan: {entry['local_path']}")
    return data


def anonymous(key: str) -> bytes | None:
    """The object's bytes read anonymously, or None when it does not exist."""
    try:
        with urllib.request.urlopen(f"{ENDPOINT}/{BUCKET}/{key}", timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise UploadError(f"anonymous read of {key} failed with HTTP {exc.code}") from None


def check_current(key: str, old: dict | None) -> dict:
    data = anonymous(key)
    if old is None:
        if data is not None:
            raise UploadError(f"{key} already exists; the plan expects a new key")
        return {"state": "absent"}
    if data is None:
        raise UploadError(f"{key} does not exist; the plan expects to replace it")
    if len(data) != old["size_bytes"] or sha256_bytes(data) != old["sha256"]:
        raise UploadError(f"{key} is not the object the plan replaces")
    return {"state": "expected_old_bytes", "size_bytes": len(data), "sha256": old["sha256"]}


def write_one(session: S3Session, entry: dict, data: bytes) -> dict:
    key = entry["object_key"]
    client = session.client()
    head = _head(client, key)
    old = entry["replaces"]
    current = check_current(key, old)
    if old is None:
        if head is not None:
            raise UploadError(f"{key} appeared since the check")
        condition = {"IfNoneMatch": "*"}
    else:
        if head is None or head.get("ContentLength") != old["size_bytes"] or not head.get("ETag"):
            raise UploadError(f"{key} changed since the check")
        condition = {"IfMatch": head["ETag"]}
    try:
        client.put_object(Bucket=BUCKET, Key=key, Body=data, ContentLength=len(data), ContentType=entry["content_type"],
                          Metadata={"sha256": entry["sha256"]}, **condition)
    except Exception as exc:
        raise _remote_error("PUT failed", "PutObject", exc) from None
    back = anonymous(key)
    verified = back is not None and len(back) == entry["size_bytes"] and sha256_bytes(back) == entry["sha256"]
    return {"object_key": key, "before": current, "condition": next(iter(condition)),
            "written_sha256": entry["sha256"], "size_bytes": entry["size_bytes"],
            "anonymous_readback": "verified" if verified else "mismatch",
            "finished_utc": datetime.now(timezone.utc).isoformat()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--credential-helper", type=Path)
    parser.add_argument("--expected-plan-sha256")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise UploadError("use a new output folder; receipts are kept")
        plan, plan_sha = load_plan(args.plan)
        if args.execute and (args.expected_plan_sha256 != plan_sha or args.credential_helper is None):
            raise UploadError("--execute needs --credential-helper and the plan's SHA-256 in --expected-plan-sha256")
        root = args.data_root.resolve()
        files = [(entry, local_file(root, entry)) for entry in plan["objects"]]
        args.output.mkdir(parents=True)
        records = []
        if not args.execute:
            for entry, _ in files:
                records.append({"object_key": entry["object_key"], "before": check_current(entry["object_key"], entry["replaces"]),
                                "local": "verified"})
        else:
            session = S3Session(args.credential_helper)
            for index, (entry, data) in enumerate(files):
                record = write_one(session, entry, data)
                records.append(record)
                (args.output / f"{index:02d}.json").write_text(json.dumps(record, indent=1) + "\n")
                if record["anonymous_readback"] != "verified":
                    raise UploadError(f"readback of {entry['object_key']} does not match the plan")
        summary = {"schema_version": 1, "mode": "execute" if args.execute else "dry_run", "plan_sha256": plan_sha,
                   "product_id": plan["product_id"], "objects": records, "status": "complete"}
        (args.output / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
        print(json.dumps({k: summary[k] for k in ("mode", "plan_sha256", "status")} | {"objects": len(records)}))
        return 0
    except UploadError as exc:
        print(f"replace failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
