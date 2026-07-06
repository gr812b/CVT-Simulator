from __future__ import annotations

import unittest

import numpy as np

from cinder.model.cvt.closure import ClosureUnknown, ClosureUnknowns
from cinder.studies.actuation import (
    ActuationOperatingPoint,
    ActuationResponseAxis,
    ActuationStateCoordinate,
    PulleyClampingForceStudyRequest,
    PulleyLocation,
    sample_pulley_clamping_force,
)
from fixtures import build_baja_trial_baseline


class ActuationStudiesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = build_baja_trial_baseline()
        cls.cvt = cls.baseline.assembly

    def test_input_clamping_response_returns_force_columns_from_existing_actuator(
        self,
    ) -> None:
        field = sample_pulley_clamping_force(
            PulleyClampingForceStudyRequest(
                cvt=self.cvt,
                pulley=PulleyLocation.INPUT,
                point=ActuationOperatingPoint(
                    shift_position=self.cvt.geometry.spec.deadzone_shift,
                ),
                axes=(
                    ActuationResponseAxis(
                        ActuationStateCoordinate.SHIFT_POSITION,
                        np.linspace(
                            self.cvt.geometry.spec.deadzone_shift,
                            self.cvt.geometry.spec.max_shift,
                            9,
                        ),
                    ),
                    ActuationResponseAxis(
                        ActuationStateCoordinate.SHAFT_SPEED,
                        np.linspace(0.0, 500.0, 7),
                    ),
                ),
            )
        )

        self.assertEqual(field.shape, (9, 7))
        self.assertIn("shift_position_m", field.column_keys)
        self.assertIn("shaft_speed_rad_per_s", field.column_keys)
        self.assertIn("centrifugal_ramp_clamping_force_N", field.column_keys)
        self.assertIn("axial_spring_clamping_force_N", field.column_keys)
        self.assertIn("total_clamping_force_N", field.column_keys)
        np.testing.assert_allclose(
            field.column("total_clamping_force_N"),
            field.column("centrifugal_ramp_clamping_force_N")
            + field.column("axial_spring_clamping_force_N"),
            rtol=0.0,
            atol=1.0e-12,
        )
        self.assertGreater(
            field.column("centrifugal_ramp_clamping_force_N")[-1, -1],
            field.column("centrifugal_ramp_clamping_force_N")[-1, 0],
        )

    def test_output_clamping_response_resolves_helix_against_actual_closure_torque(
        self,
    ) -> None:
        field = sample_pulley_clamping_force(
            PulleyClampingForceStudyRequest(
                cvt=self.cvt,
                pulley=PulleyLocation.OUTPUT,
                point=ActuationOperatingPoint(
                    shift_position=(
                        self.cvt.geometry.spec.deadzone_shift
                        + 0.5
                        * (
                            self.cvt.geometry.spec.max_shift
                            - self.cvt.geometry.spec.deadzone_shift
                        )
                    ),
                    shaft_speed=180.0,
                    closure_unknowns=ClosureUnknowns.zeros(),
                ),
                axes=(
                    ActuationResponseAxis(
                        ActuationStateCoordinate.SHIFT_POSITION,
                        np.linspace(
                            self.cvt.geometry.spec.deadzone_shift,
                            self.cvt.geometry.spec.max_shift,
                            8,
                        ),
                    ),
                    ActuationResponseAxis(
                        ClosureUnknown.SECONDARY_TORQUE,
                        np.linspace(0.0, 100.0, 11),
                    ),
                ),
            )
        )

        self.assertIn("secondary_torque_Nm", field.column_keys)
        self.assertIn("helix_reacted_shaft_torque_clamping_force_N", field.column_keys)
        self.assertIn("total_gain_secondary_torque_N_per_Nm", field.column_keys)
        contribution_keys = tuple(
            key
            for key in field.column_keys
            if key.endswith("_clamping_force_N") and key != "total_clamping_force_N"
        )
        np.testing.assert_allclose(
            field.column("total_clamping_force_N"),
            sum((field.column(key) for key in contribution_keys), start=0.0),
            rtol=0.0,
            atol=1.0e-12,
        )
        self.assertFalse(
            np.allclose(
                field.column("total_clamping_force_N")[:, 0],
                field.column("total_clamping_force_N")[:, -1],
            )
        )

    def test_rejects_shift_position_outside_cvt_geometry(self) -> None:
        with self.assertRaises(ValueError):
            sample_pulley_clamping_force(
                PulleyClampingForceStudyRequest(
                    cvt=self.cvt,
                    pulley=PulleyLocation.INPUT,
                    point=ActuationOperatingPoint(
                        shift_position=self.cvt.geometry.spec.max_shift + 1.0e-3,
                    ),
                    axes=(
                        ActuationResponseAxis(
                            ActuationStateCoordinate.SHAFT_SPEED,
                            (0.0, 1.0),
                        ),
                    ),
                )
            )


if __name__ == "__main__":
    unittest.main()
