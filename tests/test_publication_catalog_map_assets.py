"""publication.catalog.map_assets: hosted COG map layers bound to passed evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publication_catalog as pc

HREF = "https://data.source.coop/owner/product/overviews/national.tif"
SHA = "a" * 64


class MapAssetsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, evidence=None, **changes):
        evidence = evidence or {"status": "passed", "url": HREF, "size_bytes": 100, "sha256": SHA}
        data = json.dumps(evidence).encode()
        (self.root / "evidence.json").write_bytes(data)
        entry = {"asset_id": "overview_national", "href": HREF, "type": pc.COG_TYPE, "roles": ["overview"],
                 "title": "National overview", "proj_code": "EPSG:3857", "size_bytes": 100, "sha256": SHA,
                 "evidence_path": "evidence.json", "evidence_sha256": hashlib.sha256(data).hexdigest()}
        entry.update(changes)
        return {"publication": {"catalog": {"map_assets": [entry]}}}

    def test_adds_pinned_asset_and_extensions(self):
        collection = {"assets": {"data": {"href": "x"}}, "stac_extensions": []}
        pc._add_map_assets(self.root, "p", self.record(), collection)
        asset = collection["assets"]["overview_national"]
        self.assertEqual(asset["file:checksum"], "1220" + SHA)
        self.assertEqual(asset["file:size"], 100)
        self.assertEqual(asset["proj:code"], "EPSG:3857")
        self.assertIn(pc.PROJECTION_SCHEMA, collection["stac_extensions"])
        self.assertIn(pc.FILE_SCHEMA, collection["stac_extensions"])

    def test_no_entries_changes_nothing(self):
        collection = {"assets": {}}
        pc._add_map_assets(self.root, "p", {"publication": {"catalog": {}}}, collection)
        self.assertEqual(collection, {"assets": {}})

    def test_refuses_changed_evidence(self):
        record = self.record()
        (self.root / "evidence.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "evidence SHA-256"):
            pc._add_map_assets(self.root, "p", record, {"assets": {}})

    def test_refuses_failed_or_different_evidence(self):
        for evidence in ({"status": "failed", "url": HREF, "size_bytes": 100, "sha256": SHA},
                         {"status": "passed", "url": HREF, "size_bytes": 101, "sha256": SHA},
                         {"status": "passed", "url": HREF, "size_bytes": 100, "sha256": "b" * 64},
                         {"status": "passed", "url": HREF + "x", "size_bytes": 100, "sha256": SHA}):
            with self.subTest(evidence=evidence), self.assertRaisesRegex(ValueError, "differs from its passed evidence"):
                pc._add_map_assets(self.root, "p", self.record(evidence), {"assets": {}})

    def test_refuses_other_roles_or_non_cog(self):
        for changes in ({"roles": ["visual", "overview"]}, {"roles": ["data"]}, {"type": "image/png"}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "overview role"):
                pc._add_map_assets(self.root, "p", self.record(**changes), {"assets": {}})

    def test_refuses_existing_asset_id(self):
        with self.assertRaisesRegex(ValueError, "already used"):
            pc._add_map_assets(self.root, "p", self.record(), {"assets": {"overview_national": {}}})


if __name__ == "__main__":
    unittest.main()
