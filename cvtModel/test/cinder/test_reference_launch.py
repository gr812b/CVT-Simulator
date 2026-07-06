from __future__ import annotations

from dataclasses import replace
import unittest

from cinder.execution.hybrid import HybridIntegratorSettings
from fixtures import (
    BajaTrialConstants,
    build_operating_configuration,
    build_operating_system,
    launch_initial_state,
)


class ReferenceLaunchTest(unittest.TestCase):
    """CINDER-owned hybrid regression checks using only test-local fixtures."""

    def test_standard_three_second_hybrid_reference(self) -> None:
        system, _ = build_operating_system(BajaTrialConstants())
        result = system.integrate(
            time_span=(0.0, 3.0),
            initial_state=launch_initial_state(primary_rpm=1800.0),
            settings=HybridIntegratorSettings(
                method="LSODA",
                relative_tolerance=3.0e-5,
                absolute_tolerance=1.0e-7,
                max_step=0.005,
                maximum_transitions=30,
            ),
        )
        expected = (
            400.2355139994592,
            88.21088288769612,
            8.038864928086767,
            0.008598466530414205,
            -1.5904072322829304e-06,
            107.83974641620406,
        )
        self.assertEqual(result.termination_reason, "final_time_reached")
        self.assertEqual(len(result.segments), 5)
        self.assertEqual(len(result.transitions), 4)
        for actual, target in zip(result.final_state, expected, strict=True):
            self.assertAlmostEqual(float(actual), target, places=12)

    def test_dense_output_preserves_native_hybrid_solution(self) -> None:
        configuration, baseline = build_operating_configuration(BajaTrialConstants())
        settings = HybridIntegratorSettings(
            method="LSODA",
            relative_tolerance=3.0e-5,
            absolute_tolerance=1.0e-7,
            max_step=0.005,
            maximum_transitions=30,
        )

        def run(current_settings: HybridIntegratorSettings):
            return configuration.build(baseline.case).integrate(
                time_span=(0.0, 3.0),
                initial_state=launch_initial_state(primary_rpm=1800.0),
                settings=current_settings,
            )

        native = run(settings)
        dense = run(replace(settings, retain_dense_output=True))
        self.assertEqual(native.final_state.tolist(), dense.final_state.tolist())
        self.assertEqual(
            tuple(record.transition.reason for record in native.transitions),
            tuple(record.transition.reason for record in dense.transitions),
        )
        self.assertTrue(all(segment.has_dense_output for segment in dense.segments))


if __name__ == "__main__":
    unittest.main()
