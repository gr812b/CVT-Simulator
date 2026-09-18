from __future__ import annotations

# --- results study-local import bootstrap ---
from pathlib import Path as _ResultsPath
import sys as _results_sys

_results_file = _ResultsPath(__file__).resolve()
_results_study_root = next(
    (parent for parent in _results_file.parents if (parent / "study.json").is_file()),
    None,
)
if _results_study_root is None:
    raise RuntimeError(f"Could not locate study root for {_results_file}")
_results_release_root = _results_study_root.parents[1]
for _results_path in (str(_results_study_root), str(_results_release_root)):
    while _results_path in _results_sys.path:
        _results_sys.path.remove(_results_path)
_results_sys.path.insert(0, str(_results_release_root))
_results_sys.path.insert(0, str(_results_study_root))
# --- end results study-local import bootstrap ---


import math
import sys
import unittest
from pathlib import Path

STUDY_ROOT = Path(__file__).resolve().parents[1]
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from experiments.envelope_design import apply_tune_variant, build_baja_envelope, halton_point


class EnvelopeDesignTests(unittest.TestCase):
    def test_halton_design_is_deterministic_and_inside_unit_cube(self):
        first = halton_point(1)
        again = halton_point(1)
        self.assertEqual(first, again)
        self.assertTrue(all(0.0 <= value < 1.0 for value in first))

    def test_baja_envelope_respects_physical_bounds_and_contains_both_load_signs(self):
        cases = build_baja_envelope(18)
        self.assertEqual(len(cases), 28)
        reference = [case for case in cases if case.tune_variant == "reference"]
        self.assertTrue(any(case.target_grade_deg > 0.0 for case in reference))
        self.assertTrue(any(case.target_grade_deg < 0.0 for case in reference))
        for case in reference:
            self.assertGreaterEqual(case.target_grade_deg, -20.0)
            self.assertLessEqual(case.target_grade_deg, 30.0)
            self.assertGreaterEqual(case.start_time_s, 1.05)
            self.assertLessEqual(case.start_time_s, 3.35)
            self.assertGreaterEqual(case.rise_time_s, 0.05)
            self.assertLessEqual(case.rise_time_s, 0.80)

    def test_tune_robustness_uses_documented_preload_bounds(self):
        def document():
            return {
                "assembly": {
                    "pulleys": {
                        "secondary": {
                            "components": [
                                {"kind": "axial_spring", "initial_compression_m": 0.110},
                                {"kind": "helical_torque_reaction", "initial_twist_rad": math.radians(300.0)},
                            ]
                        }
                    }
                }
            }

        low = document()
        apply_tune_variant(low, "lower_secondary_preload")
        self.assertAlmostEqual(low["assembly"]["pulleys"]["secondary"]["components"][0]["initial_compression_m"], 0.105)
        self.assertAlmostEqual(low["assembly"]["pulleys"]["secondary"]["components"][1]["initial_twist_rad"], math.radians(280.0))

        high = document()
        apply_tune_variant(high, "higher_secondary_preload")
        self.assertAlmostEqual(high["assembly"]["pulleys"]["secondary"]["components"][0]["initial_compression_m"], 0.115)
        self.assertAlmostEqual(high["assembly"]["pulleys"]["secondary"]["components"][1]["initial_twist_rad"], math.radians(320.0))


if __name__ == "__main__":
    unittest.main()
