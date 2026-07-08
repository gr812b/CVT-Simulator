from __future__ import annotations

import unittest

import numpy as np

from cinder.model.cvt.dynamics.deadzone import build_deadzone_snapshot
from cinder.model.system.evaluator import CVTDynamicsModel
from fixtures import BajaTrialConstants, build_baja_trial_baseline


class ShiftDomainToleranceTest(unittest.TestCase):
    """Regression checks for floating-point endpoint states at shift stops."""

    def test_geometry_accepts_roundoff_outside_shift_endpoints(self) -> None:
        baseline = build_baja_trial_baseline(BajaTrialConstants())
        geometry = baseline.assembly.geometry
        lower_outside = np.nextafter(0.0, -np.inf)
        upper_outside = np.nextafter(geometry.spec.max_shift, np.inf)

        self.assertEqual(geometry.evaluate(lower_outside).shift, 0.0)
        self.assertEqual(
            geometry.evaluate(upper_outside).shift,
            geometry.spec.max_shift,
        )

    def test_geometry_rejects_material_shift_domain_errors(self) -> None:
        baseline = build_baja_trial_baseline(BajaTrialConstants())
        geometry = baseline.assembly.geometry

        with self.assertRaises(ValueError):
            geometry.evaluate(-1.0e-8)
        with self.assertRaises(ValueError):
            geometry.evaluate(geometry.spec.max_shift + 1.0e-8)

    def test_deadzone_snapshot_accepts_engagement_roundoff(self) -> None:
        baseline = build_baja_trial_baseline(BajaTrialConstants())
        model = CVTDynamicsModel.from_case(baseline.case)
        state = baseline.deadzone_state
        rounded_state = type(state)(
            primary_angular_speed=state.primary_angular_speed,
            secondary_angular_speed=state.secondary_angular_speed,
            belt_speed=state.belt_speed,
            shift_position=np.nextafter(model.geometry.spec.deadzone_shift, np.inf),
            shift_speed=state.shift_speed,
            secondary_shaft_angle=state.secondary_shaft_angle,
        )

        snapshot = build_deadzone_snapshot(model=model, state=rounded_state)

        self.assertEqual(snapshot.state.shift_position, model.geometry.spec.deadzone_shift)


if __name__ == "__main__":
    unittest.main()
