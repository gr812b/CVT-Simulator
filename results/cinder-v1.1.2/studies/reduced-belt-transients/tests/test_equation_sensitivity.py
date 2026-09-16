from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

STUDY_ROOT = Path(__file__).resolve().parents[1]
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from equation_sensitivity import (
    contact_coefficients_from_lambda,
    driver_thresholds,
    transient_coefficients,
)


class EquationSensitivityTests(unittest.TestCase):
    def test_H_is_odd_and_G_is_even_under_traction_reversal(self):
        phi = 2.7
        sin_beta = math.sin(math.radians(20.0))
        hp, gp = contact_coefficients_from_lambda(
            traction_lambda=0.24, wrap_angle=phi, sin_beta=sin_beta
        )
        hm, gm = contact_coefficients_from_lambda(
            traction_lambda=-0.24, wrap_angle=phi, sin_beta=sin_beta
        )
        self.assertAlmostEqual(hp, -hm, places=12)
        self.assertAlmostEqual(gp, gm, places=12)

    def test_tangential_coupling_vanishes_at_zero_traction(self):
        H, G = contact_coefficients_from_lambda(
            traction_lambda=0.0,
            wrap_angle=2.4,
            sin_beta=math.sin(math.radians(20.0)),
        )
        self.assertAlmostEqual(H, 0.0, places=15)
        self.assertGreater(G, 0.0)

    def test_thresholds_reconstruct_requested_force_fraction(self):
        coefficients = {
            "shift_acceleration_N_per_mps2": -0.2,
            "path_curvature_N_per_m2ps2": 2.5,
            "belt_acceleration_N_per_mps2": 0.03,
            "moving_radius_N_per_m2ps2": -0.004,
        }
        threshold = driver_thresholds(
            coefficients=coefficients, contact_scale_N=10.0, fraction=0.10
        )
        target = 1.0
        self.assertAlmostEqual(abs(coefficients["shift_acceleration_N_per_mps2"]) * threshold["shift_acceleration_m_per_s2"], target)
        self.assertAlmostEqual(abs(coefficients["path_curvature_N_per_m2ps2"]) * threshold["shift_speed_curvature_m_per_s"]**2, target)
        self.assertAlmostEqual(abs(coefficients["belt_acceleration_N_per_mps2"]) * threshold["belt_acceleration_m_per_s2"], target)
        self.assertAlmostEqual(abs(coefficients["moving_radius_N_per_m2ps2"]) * threshold["shift_speed_times_belt_speed_m2_per_s2"], target)

    def test_driver_growth_laws_are_distinct(self):
        coeff = transient_coefficients(
            linear_density=0.4,
            primary_radius_cm=0.06,
            secondary_radius_cm=0.09,
            primary_d_radius_ds=1.2,
            secondary_d_radius_ds=-0.8,
            primary_d2_radius_ds2=0.0,
            secondary_d2_radius_ds2=-16.0,
            primary_H=-0.2,
            secondary_H=0.25,
        )
        self.assertNotEqual(coeff["shift_acceleration_N_per_mps2"], 0.0)
        self.assertNotEqual(coeff["path_curvature_N_per_m2ps2"], 0.0)
        self.assertNotEqual(coeff["belt_acceleration_N_per_mps2"], 0.0)
        self.assertNotEqual(coeff["moving_radius_N_per_m2ps2"], 0.0)


if __name__ == "__main__":
    unittest.main()
