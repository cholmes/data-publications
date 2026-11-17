"""publication.catalog.title_correction: rename a published product in the catalogue only."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publication_catalog as pc


def record(title="New name", **correction):
    entry = {"from": "Old name", "to": "New name", "reason": "Renamed"}
    entry.update(correction)
    return {"title": title, "publication": {"catalog": {"title_correction": entry}}}


class TitleCorrectionTest(unittest.TestCase):
    def test_replaces_old_name_in_description(self):
        snapshot = {"title": "Old name", "description": "Files of the Old name; Old name again."}
        out = {"title": "New name", "description": snapshot["description"]}
        pc._apply_title_correction(snapshot, out, "p", record())
        self.assertEqual(out, {"title": "New name", "description": "Files of the New name; New name again."})
        self.assertEqual(snapshot["description"], "Files of the Old name; Old name again.")

    def test_no_correction_changes_nothing(self):
        out = {"title": "T", "description": "Old name"}
        pc._apply_title_correction({"title": "T"}, out, "p", {"publication": {"catalog": {}}})
        self.assertEqual(out["description"], "Old name")

    def test_refuses_mismatched_snapshot_title(self):
        with self.assertRaisesRegex(ValueError, "snapshot title"):
            pc._apply_title_correction({"title": "Other"}, {}, "p", record())

    def test_refuses_record_title_other_than_target(self):
        with self.assertRaisesRegex(ValueError, "record title"):
            pc._apply_title_correction({"title": "Old name"}, {}, "p", record(title="Third name"))


if __name__ == "__main__":
    unittest.main()
