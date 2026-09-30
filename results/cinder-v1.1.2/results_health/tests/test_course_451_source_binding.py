from __future__ import annotations
import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

REQUIRED = {"active_shift_fraction", "primary_spring_opening_N", "centrifugal_force_3000rpm_N"}

class Course451SourceBindingTests(unittest.TestCase):
    def test_shape_map_has_paper_fields_while_geometry_map_need_not(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            geometry = root / "mechanism_map.csv"
            shape = root / "shape_mechanism_map.csv"
            geometry.write_text("active_shift_fraction,shift_mm\n0,0\n", encoding="utf-8")
            shape.write_text(
                "active_shift_fraction,primary_spring_opening_N,centrifugal_force_3000rpm_N\n0,1234,2978\n",
                encoding="utf-8",
            )
            with geometry.open(newline="", encoding="utf-8") as f:
                self.assertFalse(REQUIRED.issubset(set(next(csv.reader(f)))))
            with shape.open(newline="", encoding="utf-8") as f:
                self.assertTrue(REQUIRED.issubset(set(next(csv.reader(f)))))

    def test_exporter_binds_451_mechanism_to_shape_map(self):
        exporter = Path(__file__).resolve().parents[2] / "studies" / "course-tuning" / "analysis" / "course_publication_export.py"
        text = exporter.read_text(encoding="utf-8")
        self.assertIn('source = case_dir / "shape_mechanism_map.csv"', text)
        self.assertNotIn('shutil.copy2(case_dir / "mechanism_map.csv", fs / f"mechanism_{case}.csv")', text)

if __name__ == "__main__":
    unittest.main()
