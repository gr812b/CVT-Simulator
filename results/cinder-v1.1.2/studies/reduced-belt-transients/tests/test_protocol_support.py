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


import sys
import unittest
from pathlib import Path

STUDY_ROOT = Path(__file__).resolve().parents[1]
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from infrastructure.protocol_support import SmoothGradeProgram, SmoothOverrunProgram, smoothstep01


class ControlledGradeTests(unittest.TestCase):
    def test_smoothstep_endpoints_and_midpoint(self):
        self.assertEqual(smoothstep01(-1.0), 0.0)
        self.assertEqual(smoothstep01(0.0), 0.0)
        self.assertAlmostEqual(smoothstep01(0.5), 0.5, places=12)
        self.assertEqual(smoothstep01(1.0), 1.0)
        self.assertEqual(smoothstep01(2.0), 1.0)

    def test_smooth_grade_program_has_common_preload_and_exact_hold(self):
        p = SmoothGradeProgram(start_time_s=1.5, rise_time_s=0.2, target_grade_deg=18.0)
        self.assertEqual(p.grade_degrees(1.49), 0.0)
        self.assertEqual(p.phase_name(1.49), "pre_load")
        self.assertAlmostEqual(p.grade_degrees(1.6), 9.0, places=12)
        self.assertEqual(p.phase_name(1.6), "load_rise")
        self.assertEqual(p.grade_degrees(1.7), 18.0)
        self.assertEqual(p.phase_name(1.7), "load_hold")

    def test_zero_rise_is_an_instantaneous_road_load_application(self):
        p = SmoothGradeProgram(start_time_s=1.5, rise_time_s=0.0, target_grade_deg=18.0)
        self.assertEqual(p.grade_degrees(1.499999), 0.0)
        self.assertEqual(p.grade_degrees(1.5), 18.0)
        self.assertEqual(p.phase_name(1.5), "load_hold")

    def test_overrun_program_blends_grade_and_primary_torque_phase(self):
        p = SmoothOverrunProgram(
            start_time_s=2.0, rise_time_s=0.2,
            target_grade_deg=-20.0, target_primary_torque_Nm=-5.0
        )
        self.assertEqual(p.blend(1.9), 0.0)
        self.assertAlmostEqual(p.blend(2.1), 0.5, places=12)
        self.assertEqual(p.blend(2.2), 1.0)
        self.assertEqual(p.phase_name(1.9), "pre_overrun")
        self.assertEqual(p.phase_name(2.1), "overrun_transition")
        self.assertEqual(p.phase_name(2.2), "overrun_hold")


if __name__ == "__main__":
    unittest.main()
