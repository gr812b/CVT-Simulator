from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

STUDY_ROOT = Path(__file__).resolve().parents[1]
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from belt_terms import FinalBeltInputs, contact_coefficients, decompose_final_equations


def sample(**updates) -> FinalBeltInputs:
    base = dict(
        belt_mass=0.35,
        linear_density=0.37,
        belt_speed=12.0,
        belt_acceleration=2.4,
        shift_speed=0.015,
        shift_acceleration=0.8,
        primary_effective_radius=0.065,
        secondary_effective_radius=0.095,
        primary_radius_cm=0.062,
        secondary_radius_cm=0.092,
        primary_d_radius_ds=1.4,
        secondary_d_radius_ds=-1.0,
        primary_d2_radius_ds2=0.0,
        secondary_d2_radius_ds2=-18.0,
        primary_wrap_angle=2.5,
        secondary_wrap_angle=2.0 * math.pi - 2.5,
        primary_torque=-12.0,
        secondary_torque=17.53846153846154,
        primary_normal=900.0,
        secondary_normal=700.0,
        primary_lambda=0.12,
        secondary_lambda=-0.10,
        sin_beta=math.sin(math.radians(20.0)),
        primary_phi_minus=0.86,
        secondary_phi_minus=1.12,
        primary_psi_minus=0.43,
        secondary_psi_minus=0.55,
        primary_exp_neg=0.72,
        secondary_exp_neg=1.31,
    )
    base.update(updates)
    return FinalBeltInputs(**base)


class FinalEquationTests(unittest.TestCase):
    def test_contact_coefficients_match_endpoint_sum_algebra(self):
        x = sample()
        H, G = contact_coefficients(
            wrap_angle=x.primary_wrap_angle,
            sin_beta=x.sin_beta,
            phi_minus=x.primary_phi_minus,
            psi_minus=x.primary_psi_minus,
            exp_neg=x.primary_exp_neg,
        )
        C = 13.0
        A = -4.0
        N = x.primary_normal
        entry = C + N * x.sin_beta / (x.primary_wrap_angle * x.primary_phi_minus) - A * x.primary_wrap_angle * x.primary_psi_minus / x.primary_phi_minus
        exit_ = C + x.primary_exp_neg * (entry - C) + A * x.primary_wrap_angle * x.primary_phi_minus
        self.assertAlmostEqual(entry + exit_, 2.0 * C + H * A + G * N, places=12)

    def test_loop_decomposition_matches_collapsed_equation(self):
        x = sample()
        row = decompose_final_equations(x)
        Hp, Gp = contact_coefficients(wrap_angle=x.primary_wrap_angle, sin_beta=x.sin_beta, phi_minus=x.primary_phi_minus, psi_minus=x.primary_psi_minus, exp_neg=x.primary_exp_neg)
        Hs, Gs = contact_coefficients(wrap_angle=x.secondary_wrap_angle, sin_beta=x.sin_beta, phi_minus=x.secondary_phi_minus, psi_minus=x.secondary_psi_minus, exp_neg=x.secondary_exp_neg)
        rddotp = x.primary_d2_radius_ds2 * x.shift_speed**2 + x.primary_d_radius_ds * x.shift_acceleration
        rddots = x.secondary_d2_radius_ds2 * x.shift_speed**2 + x.secondary_d_radius_ds * x.shift_acceleration
        Cp = x.linear_density * (x.belt_speed**2 - x.primary_radius_cm * rddotp)
        Cs = x.linear_density * (x.belt_speed**2 - x.secondary_radius_cm * rddots)
        Ap = x.linear_density * (x.primary_radius_cm * x.belt_acceleration + x.primary_d_radius_ds * x.shift_speed * x.belt_speed)
        As = x.linear_density * (x.secondary_radius_cm * x.belt_acceleration + x.secondary_d_radius_ds * x.shift_speed * x.belt_speed)
        expected = 2.0 * (Cp - Cs) + Hp * Ap - Hs * As + Gp * x.primary_normal - Gs * x.secondary_normal
        self.assertAlmostEqual(row["loop.residual_N"], expected, places=12)

    def test_common_centripetal_term_is_absent_from_final_loop_channels(self):
        row = decompose_final_equations(sample())
        self.assertFalse(any("centripetal" in key for key in row))

    def test_transport_uses_effective_not_centroid_radii(self):
        x = sample(primary_effective_radius=0.05, primary_radius_cm=0.08, primary_torque=10.0)
        row = decompose_final_equations(x)
        self.assertAlmostEqual(row["transport.primary_reaction_N"], 200.0, places=12)

    def test_activity_shares_sum_to_one_when_balance_is_active(self):
        row = decompose_final_equations(sample())
        loop_share = sum(value for key, value in row.items() if key.startswith("loop.share."))
        transport_share = sum(value for key, value in row.items() if key.startswith("transport.share."))
        self.assertAlmostEqual(loop_share, 1.0, places=12)
        self.assertAlmostEqual(transport_share, 1.0, places=12)

    def test_each_transient_term_is_response_coefficient_times_driver(self):
        row = decompose_final_equations(sample())
        triples = (
            ("radial_shift_acceleration", "N_per_mps2", "mps2"),
            ("radial_geometry_curvature", "N_per_m2ps2", "m2ps2"),
            ("tangential_belt_acceleration", "N_per_mps2", "mps2"),
            ("tangential_shifting_radius", "N_per_m2ps2", "m2ps2"),
        )
        for name, coefficient_unit, driver_unit in triples:
            coefficient = row[f"loop.response_coefficient.{name}_{coefficient_unit}"]
            driver = row[f"loop.driver.{name}_{driver_unit}"]
            self.assertAlmostEqual(
                row[f"loop.{name}_N"], coefficient * driver, places=12
            )

    def test_equation_threshold_channels_are_self_consistent(self):
        row = decompose_final_equations(sample())
        contact_scale = row["loop.contact_scale_N"]
        target = 0.10 * contact_scale
        checks = (
            ("loop.response_coefficient.radial_shift_acceleration_N_per_mps2", "loop.threshold.10pct.shift_acceleration_m_per_s2", 1),
            ("loop.response_coefficient.radial_geometry_curvature_N_per_m2ps2", "loop.threshold.10pct.shift_speed_curvature_m_per_s", 2),
            ("loop.response_coefficient.tangential_belt_acceleration_N_per_mps2", "loop.threshold.10pct.belt_acceleration_m_per_s2", 1),
            ("loop.response_coefficient.tangential_shifting_radius_N_per_m2ps2", "loop.threshold.10pct.shift_speed_times_belt_speed_m2_per_s2", 1),
        )
        for coefficient_key, threshold_key, power in checks:
            contribution = abs(row[coefficient_key]) * row[threshold_key] ** power
            self.assertAlmostEqual(contribution, target, places=12)


if __name__ == "__main__":
    unittest.main()
