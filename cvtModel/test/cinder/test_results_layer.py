from __future__ import annotations

import unittest

import numpy as np

from cinder.execution.hybrid import HybridIntegratorSettings
from cinder.model.cvt.dynamics import TrialClosureRuntimeResult
from cinder.results import CVTResultBuilder, ReportingGrid, ReportingSettings
from fixtures import BajaTrialConstants
from fixtures import build_operating_system, launch_initial_state


class ResultsLayerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.system, _ = build_operating_system(BajaTrialConstants())
        self.settings = HybridIntegratorSettings(
            method="LSODA",
            relative_tolerance=3.0e-5,
            absolute_tolerance=1.0e-7,
            max_step=0.005,
            maximum_transitions=30,
        )
        self.initial = launch_initial_state(primary_rpm=1800.0)

    def test_runtime_contact_closure_is_lean(self) -> None:
        trace = self.system.integrate_trace(
            time_span=(0.0, 1.0),
            initial_state=launch_initial_state(primary_rpm=2200.0),
            settings=self.settings,
        )
        engaged = next(segment for segment in trace.segments if segment.mode.contact_regime)
        evaluation = self.system.inspect(
            time=float(engaged.time[-1]),
            state=engaged.state[:, -1],
            mode=engaged.mode,
        )
        self.assertIsInstance(evaluation.branch_result.trial.closure, TrialClosureRuntimeResult)

    def test_result_builder_keeps_trace_and_exposes_standard_channels(self) -> None:
        trace = self.system.integrate_trace(
            time_span=(0.0, 0.5),
            initial_state=self.initial,
            settings=self.settings,
        )
        result = self.system.run(
            time_span=(0.0, 0.5),
            initial_state=self.initial,
            settings=self.settings,
            reporting_settings=ReportingSettings(
                grid=ReportingGrid.uniform_count(30),
            ),
        )
        self.assertEqual(result.summary.final_state.tolist(), trace.final_state.tolist())
        keys = set().union(*(segment.signals.keys() for segment in result.segments))
        self.assertIn("geometry.effective_ratio_secondary_over_primary", keys)
        self.assertIn("actuation.primary.axial_spring", keys)
        self.assertIn("contact.primary_lambda", keys)
        self.assertIn("observer.primary_shaft_angle", keys)

    def test_run_uses_standard_ten_millisecond_uniform_grid_by_default(self) -> None:
        result = self.system.run(
            time_span=(0.0, 0.5),
            initial_state=self.initial,
            settings=self.settings,
        )
        self.assertTrue(all(segment.has_dense_output for segment in result.trace.segments))
        first = result.segments[0]
        self.assertAlmostEqual(first.time[0], 0.0)
        self.assertTrue(np.any(np.isclose(first.time, 0.01)))
        self.assertEqual(result.transitions, result.trace.transitions)
        self.assertEqual(result.segments[0].state.shape[0], 6)

    def test_uniform_grid_uses_solver_dense_output_and_preserves_transition_endpoints(self) -> None:
        result = self.system.run(
            time_span=(0.0, 1.0),
            initial_state=self.initial,
            settings=self.settings,
            reporting_settings=ReportingSettings(
                grid=ReportingGrid.uniform_time_step(0.01),
            ),
        )
        self.assertTrue(all(segment.has_dense_output for segment in result.trace.segments))
        self.assertAlmostEqual(result.segments[0].time[0], 0.0)
        self.assertAlmostEqual(result.segments[-1].time[-1], 1.0)
        reported_times = np.concatenate([segment.time for segment in result.segments])
        self.assertTrue(np.any(np.isclose(reported_times, 0.01)))
        self.assertTrue(np.any(np.isclose(reported_times, 0.99)))

    def test_low_level_builder_defaults_to_native_trace_sampling(self) -> None:
        trace = self.system.integrate_trace(
            time_span=(0.0, 0.2),
            initial_state=self.initial,
            settings=self.settings,
        )
        result = CVTResultBuilder(system=self.system).build(trace)
        self.assertFalse(any(segment.has_dense_output for segment in trace.segments))
        self.assertEqual(
            sum(segment.time.size for segment in result.segments),
            sum(segment.time.size for segment in trace.segments),
        )

    def test_uniform_reporting_rejects_native_only_trace(self) -> None:
        trace = self.system.integrate_trace(
            time_span=(0.0, 0.2),
            initial_state=self.initial,
            settings=self.settings,
        )
        with self.assertRaisesRegex(RuntimeError, "dense output"):
            CVTResultBuilder(system=self.system).build(
                trace,
                settings=ReportingSettings(grid=ReportingGrid.uniform_count(10)),
            )

    def test_audit_is_opt_in_and_materialized_at_report_points_only(self) -> None:
        result = self.system.run(
            time_span=(0.0, 0.2),
            initial_state=launch_initial_state(primary_rpm=2200.0),
            settings=self.settings,
            reporting_settings=ReportingSettings(
                grid=ReportingGrid.uniform_count(5),
                include_closure_audit=True,
            ),
        )
        keys = set().union(*(segment.signals.keys() for segment in result.segments))
        self.assertIn("audit.closure_condition_number", keys)
        self.assertIn("audit.closure_matrix_rank", keys)


if __name__ == "__main__":
    unittest.main()
