from __future__ import annotations

import sys
import unittest
from pathlib import Path

STUDY_ROOT = Path(__file__).resolve().parents[1]
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from protocol_support import SmoothGradeProgram, smoothstep01


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

    def test_zero_rise_is_an_ideal_step(self):
        p = SmoothGradeProgram(start_time_s=1.5, rise_time_s=0.0, target_grade_deg=18.0)
        self.assertEqual(p.grade_degrees(1.499999), 0.0)
        self.assertEqual(p.grade_degrees(1.5), 18.0)
        self.assertEqual(p.phase_name(1.5), "load_hold")


if __name__ == "__main__":
    unittest.main()
