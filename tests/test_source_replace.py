import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "source_publish"))
import replace  # noqa: E402
from upload import UploadError  # noqa: E402


def sha(data):
    return hashlib.sha256(data).hexdigest()


class FakeClient:
    def __init__(self, store):
        self.store = store
        self.puts = []

    def head_object(self, Bucket, Key):
        if Key not in self.store:
            raise type("E", (Exception,), {"response": {"Error": {"Code": "404"}}})()
        return {"ContentLength": len(self.store[Key]), "ETag": '"' + sha(self.store[Key])[:8] + '"'}

    def put_object(self, Bucket, Key, Body, ContentLength, ContentType, Metadata, **condition):
        self.puts.append((Key, condition))
        if "IfNoneMatch" in condition and Key in self.store:
            raise RuntimeError("precondition")
        if "IfMatch" in condition and condition["IfMatch"] != self.head_object(Bucket, Key)["ETag"]:
            raise RuntimeError("precondition")
        self.store[Key] = Body


class FakeSession:
    def __init__(self, client):
        self._client = client

    def client(self):
        return self._client


class ReplaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        self.new = b"new index bytes"
        self.old = b"old index bytes!"
        (self.root / "data" / "a.parquet").write_bytes(self.new)
        (self.root / "data" / "a.json").write_bytes(b"{}")
        self.store = {"naip/stac/a.parquet": self.old}
        self.client = FakeClient(self.store)
        replace.anonymous = lambda key: self.store.get(key)

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, **changes):
        objects = [{"object_key": "naip/stac/a.parquet", "local_path": "data/a.parquet", "size_bytes": len(self.new),
                    "sha256": sha(self.new), "content_type": "application/vnd.apache.parquet",
                    "replaces": {"sha256": sha(self.old), "size_bytes": len(self.old)}},
                   {"object_key": "naip/stac/a.fields.json", "local_path": "data/a.json", "size_bytes": 2,
                    "sha256": sha(b"{}"), "content_type": "application/json", "replaces": None}]
        for index, change in changes.items():
            objects[int(index[1:])].update(change)
        path = self.root / "plan.json"
        path.write_text(json.dumps({"schema_version": 1, "owner": "nthh", "product_id": "naip", "objects": objects}))
        return path

    def test_keys_outside_the_product_are_refused(self):
        with self.assertRaises(UploadError):
            replace.load_plan(self.plan(o0={"object_key": "other/stac/a.parquet"}))
        with self.assertRaises(UploadError):
            replace.load_plan(self.plan(o0={"object_key": "naip/../x.parquet"}))

    def test_local_bytes_must_match(self):
        plan, _ = replace.load_plan(self.plan(o0={"sha256": "0" * 64}))
        with self.assertRaises(UploadError):
            replace.local_file(self.root, plan["objects"][0])

    def test_replacement_needs_the_stated_old_bytes(self):
        self.store["naip/stac/a.parquet"] = b"something else"
        with self.assertRaises(UploadError):
            replace.check_current("naip/stac/a.parquet", {"sha256": sha(self.old), "size_bytes": len(self.old)})

    def test_new_key_must_be_absent(self):
        self.store["naip/stac/a.fields.json"] = b"x"
        with self.assertRaises(UploadError):
            replace.check_current("naip/stac/a.fields.json", None)

    def test_execute_uses_if_match_and_if_none_match_and_reads_back(self):
        plan, _ = replace.load_plan(self.plan())
        session = FakeSession(self.client)
        records = [replace.write_one(session, entry, replace.local_file(self.root, entry)) for entry in plan["objects"]]
        self.assertEqual([c for _, c in self.client.puts][0].keys(), {"IfMatch"})
        self.assertEqual([c for _, c in self.client.puts][1], {"IfNoneMatch": "*"})
        self.assertTrue(all(r["anonymous_readback"] == "verified" for r in records))
        self.assertEqual(self.store["naip/stac/a.parquet"], self.new)


if __name__ == "__main__":
    unittest.main()
