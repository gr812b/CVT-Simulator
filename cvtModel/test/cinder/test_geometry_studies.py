from __future__ import annotations

import unittest

import numpy as np

from cinder.studies.geometry import (
    EndpointRadiiDesignRequest,
    GeometryDesignContext,
    GeometryDesignInfeasibleError,
    TargetRatioDesignRequest,
    evaluate_geometry_feasibility,
    evaluate_radius_plane,
    evaluate_ratio_sensitivity_field,
    sample_geometry_path,
    solve_geometry_from_endpoint_radii,
    solve_geometry_from_target_ratios,
    summarize_geometry_design,
)
from fixtures import build_baja_trial_baseline


class GeometryStudiesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        baseline = build_baja_trial_baseline()
        cls.reference_spec = baseline.assembly.geometry.spec
        cls.context = GeometryDesignContext(
            belt=cls.reference_spec.belt,
            belt_outer_length=cls.reference_spec.belt_outer_length,
            sheave_half_angle=cls.reference_spec.sheave_half_angle,
            deadzone_shift=cls.reference_spec.deadzone_shift,
            max_shift=cls.reference_spec.max_shift,
        )
        cls.case_a = solve_geometry_from_endpoint_radii(
            EndpointRadiiDesignRequest(
                context=cls.context,
                primary_outer_radius_at_zero_shift=(
                    cls.reference_spec.primary_outer_radius_at_zero_shift
                ),
                secondary_outer_radius_at_zero_shift=(
                    cls.reference_spec.secondary_outer_radius_at_zero_shift
                ),
            )
        )

    def test_case_a_reconstructs_existing_resolved_geometry(self) -> None:
        resolved = self.case_a.geometry_spec
        reference = self.reference_spec
        self.assertAlmostEqual(resolved.center_distance, reference.center_distance, places=12)
        self.assertAlmostEqual(
            resolved.primary_outer_radius_at_max_shift,
            reference.primary_outer_radius_at_max_shift,
            places=12,
        )
        self.assertAlmostEqual(
            resolved.secondary_outer_radius_at_max_shift,
            reference.secondary_outer_radius_at_max_shift,
            places=12,
        )

    def test_case_b_reconstructs_case_a_from_target_ratios(self) -> None:
        reconstructed = solve_geometry_from_target_ratios(
            TargetRatioDesignRequest(
                context=self.context,
                maximum_ratio=self.case_a.maximum_ratio_endpoint.ratio,
                minimum_ratio=self.case_a.minimum_ratio_endpoint.ratio,
            )
        )
        self.assertAlmostEqual(
            reconstructed.center_distance,
            self.case_a.center_distance,
            places=11,
        )
        self.assertAlmostEqual(
            reconstructed.geometry_spec.primary_outer_radius_at_zero_shift,
            self.case_a.geometry_spec.primary_outer_radius_at_zero_shift,
            places=11,
        )
        self.assertAlmostEqual(
            reconstructed.geometry_spec.secondary_outer_radius_at_zero_shift,
            self.case_a.geometry_spec.secondary_outer_radius_at_zero_shift,
            places=11,
        )

    def test_case_b_reports_unattainable_ratio_pair(self) -> None:
        with self.assertRaises(GeometryDesignInfeasibleError):
            solve_geometry_from_target_ratios(
                TargetRatioDesignRequest(
                    context=self.context,
                    maximum_ratio=2.5,
                    minimum_ratio=1.2,
                )
            )

    def test_path_matches_resolved_endpoints_and_summary(self) -> None:
        path = sample_geometry_path(self.case_a, sample_count=101)
        summary = summarize_geometry_design(self.case_a)
        self.assertAlmostEqual(path.ratio[0], summary.maximum_ratio, places=12)
        self.assertAlmostEqual(path.ratio[-1], summary.minimum_ratio, places=12)
        self.assertAlmostEqual(
            path.primary_outer_radius[-1],
            summary.primary_outer_radius_max,
            places=12,
        )
        self.assertTrue(np.all(path.ratio_change_per_mm_shift <= 1.0e-12))
        self.assertEqual(path.shift.flags.writeable, False)

    def test_plane_and_sensitivity_fields_are_consistent_with_path_point(self) -> None:
        path = sample_geometry_path(self.case_a, sample_count=5)
        primary_axis = np.array(
            [
                0.020,
                path.primary_outer_radius[2],
                0.080,
            ],
            dtype=float,
        )
        secondary_axis = np.array(
            [
                0.030,
                path.secondary_outer_radius[2],
                0.120,
            ],
            dtype=float,
        )
        plane = evaluate_radius_plane(
            belt=self.reference_spec.belt,
            center_distance=self.case_a.center_distance,
            primary_outer_radius=primary_axis,
            secondary_outer_radius=secondary_axis,
        )
        sensitivity = evaluate_ratio_sensitivity_field(
            belt=self.reference_spec.belt,
            center_distance=self.case_a.center_distance,
            sheave_half_angle=self.reference_spec.sheave_half_angle,
            primary_outer_radius=primary_axis,
            secondary_outer_radius=secondary_axis,
        )
        self.assertTrue(plane.feasible_mask[1, 1])
        self.assertAlmostEqual(plane.ratio[1, 1], path.ratio[2], places=11)
        self.assertAlmostEqual(
            sensitivity.ratio_change_per_mm_shift[1, 1],
            path.ratio_change_per_mm_shift[2],
            places=11,
        )

    def test_feasibility_reports_optional_wrap_threshold_warning(self) -> None:
        report = evaluate_geometry_feasibility(
            self.case_a,
            minimum_primary_wrap_angle=3.0,
        )
        self.assertTrue(report.is_feasible)
        self.assertEqual(
            report.issues[0].code,
            "primary_wrap_angle_below_threshold",
        )


if __name__ == "__main__":
    unittest.main()
