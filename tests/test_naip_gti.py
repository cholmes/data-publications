"""NAIP index: the naip:gti_location column and the GTI files that open the index in GDAL/QGIS."""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import sys
import tempfile
import unittest

import pyarrow as pa

ROOT = Path(__file__).resolve().parents[1]
NAIP = ROOT / "datasets" / "naip"
sys.path.insert(0, str(NAIP))
import build_stac_index as bsi
import check_index_release as cir

RECEIPT = {
    "id": "ut_m_3610901_ne_12_060_20240708",
    "out_uri": "s3://us-west-2.opendata.source.coop/nthh/naip/ut/2024/60cm/rgb/36109/m_3610901_ne_12_060_20240708.tif",
    "output_bytes": 25396144,
    "output_sha256": "1a0e78f436d823e1060b56d11f316d9cd3f6ff5442233b765bfc934bf8993a92",
    "output": {"width": 10080, "height": 12330, "geotransform": [594336.0, 0.6, 0.0, 4095666.0, 0.0, -0.6], "epsg": "26912"},
    "run_id": "ut2024-pub-1",
}


def table(rows):
    return pa.Table.from_pylist([{"assets": {"image": {"href": href}}, cir.GTI_LOCATION: location} for href, location in rows])


class LocationColumnTest(unittest.TestCase):
    def test_item_location_is_relative_to_stac_and_names_the_href(self):
        item = bsi.item(RECEIPT, bsi_base(), {})
        self.assertEqual(item[bsi.GTI_LOCATION], "../ut/2024/60cm/rgb/36109/m_3610901_ne_12_060_20240708.tif")
        self.assertEqual(item["assets"]["image"]["href"],
                         "https://data.source.coop/nthh/naip/ut/2024/60cm/rgb/36109/m_3610901_ne_12_060_20240708.tif")
        self.assertTrue(cir.check_gti_locations(table([(item["assets"]["image"]["href"], item[bsi.GTI_LOCATION])]))["passed"])

    def test_checker_accepts_overview_locations(self):
        href = "https://data.source.coop/nthh/naip/overviews/ut-2024-utm12.tif"
        self.assertTrue(cir.check_gti_locations(table([(href, "../overviews/ut-2024-utm12.tif")]))["passed"])

    def test_checker_rejects_other_file_absolute_and_missing(self):
        href = "https://data.source.coop/nthh/naip/ut/2024/60cm/rgb/36109/a.tif"
        for location in ("../ut/2024/60cm/rgb/36109/b.tif", href, "/vsicurl/" + href, "ut/2024/60cm/rgb/36109/a.tif", None):
            with self.subTest(location=location):
                self.assertFalse(cir.check_gti_locations(table([(href, location)]))["passed"])
        self.assertFalse(cir.check_gti_locations(pa.Table.from_pylist([{"assets": {"image": {"href": href}}}]))["passed"])


class GtiFilesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        for name in ("naip.gti", "naip-overviews.gti"):
            shutil.copyfile(NAIP / "gti" / name, os.path.join(self.dir, name))

    def test_checked_in_files_pass(self):
        result = cir.check_gti_files(self.dir)
        self.assertTrue(result["passed"], result["problems"])
        self.assertEqual(set(result["files"]["naip.gti"]["overviews"]), {"naip-overviews.gti"})

    def test_wrong_location_field_or_missing_overview_file_fails(self):
        path = os.path.join(self.dir, "naip.gti")
        text = Path(path).read_text()
        Path(path).write_text(text.replace("<LocationField>naip:gti_location</LocationField>", "<LocationField>location</LocationField>"))
        self.assertFalse(cir.check_gti_files(self.dir)["passed"])
        Path(path).write_text(text)
        os.remove(os.path.join(self.dir, "naip-overviews.gti"))
        self.assertFalse(cir.check_gti_files(self.dir)["passed"])


def bsi_base():
    return "https://data.source.coop/nthh/naip/"


if __name__ == "__main__":
    unittest.main()
