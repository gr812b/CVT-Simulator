from __future__ import annotations

import json
import unittest
from dataclasses import replace

import numpy as np

from cinder.contracts import (
    AssemblyValidationOptions,
    component_catalog_document,
    decode_assembly_document,
    decode_simulation_case_document,
    encode_assembly_document,
    encode_simulation_case_document,
    project_clamping_force_response,
    project_geometry_path,
    project_radius_plane,
    project_ratio_sensitivity_field,
    project_simulation_result,
    public_conventions,
    summarize_simulation,
    validate_assembly,
    validate_simulation_case_document,
)
from cinder.execution.hybrid import HybridIntegratorSettings
from cinder.model.cvt.closure import ClosureUnknown
from cinder.studies.actuation import (
    ActuationOperatingPoint,
    ActuationResponseAxis,
    PulleyClampingForceStudyRequest,
    PulleyLocation,
    sample_pulley_clamping_force,
)
from cinder.studies.geometry import (
    EndpointRadiiDesignRequest,
    GeometryDesignContext,
    evaluate_radius_plane,
    evaluate_ratio_sensitivity_field,
    sample_geometry_path,
    solve_geometry_from_endpoint_radii,
)
from fixtures import build_baja_trial_baseline
from fixtures import build_operating_configuration, launch_initial_state


class PublicContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = build_baja_trial_baseline()
        cls.assembly = cls.baseline.assembly

    def test_versioned_assembly_document_round_trip_preserves_runtime_geometry(
        self,
    ) -> None:
        document = encode_assembly_document(self.assembly)
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(document["document_type"], "cinder_cvt_assembly")
        json.dumps(document)

        reconstructed = decode_assembly_document(document)
        self.assertAlmostEqual(
            reconstructed.geometry.spec.center_distance,
            self.assembly.geometry.spec.center_distance,
        )
        self.assertEqual(
            tuple(
                type(item) for item in reconstructed.pulleys.input.actuator.force_laws
            ),
            tuple(
                type(item) for item in self.assembly.pulleys.input.actuator.force_laws
            ),
        )
        self.assertEqual(validate_assembly(reconstructed).errors, ())

    def test_catalog_and_conventions_are_json_safe_and_useful_without_a_ui(
        self,
    ) -> None:
        conventions = public_conventions().as_dict()
        catalog = component_catalog_document()
        json.dumps(conventions)
        json.dumps(catalog)
        self.assertEqual(conventions["canonical_unit_system"], "SI")
        self.assertEqual(
            {item["kind"] for item in catalog["components"]},
            {
                "axial_spring",
                "centrifugal_ramp",
                "fixed_pivot_roller_flyweight",
                "helical_torque_reaction",
            },
        )

    def test_validator_reports_optional_wrap_thresholds_as_structured_findings(
        self,
    ) -> None:
        report = validate_assembly(
            self.assembly,
            options=AssemblyValidationOptions(
                minimum_primary_wrap_angle_rad=10.0,
                minimum_secondary_wrap_angle_rad=10.0,
            ),
        )
        self.assertTrue(report.is_valid)
        self.assertEqual(
            {item.code for item in report.warnings},
            {
                "geometry.primary_wrap_below_threshold",
                "geometry.secondary_wrap_below_threshold",
            },
        )

    def test_geometry_and_actuation_fields_project_to_self_describing_json_columns(
        self,
    ) -> None:
        spec = self.assembly.geometry.spec
        context = GeometryDesignContext(
            belt=spec.belt,
            belt_outer_length=spec.belt_outer_length,
            sheave_half_angle=spec.sheave_half_angle,
            deadzone_shift=spec.deadzone_shift,
            max_shift=spec.max_shift,
        )
        design = solve_geometry_from_endpoint_radii(
            EndpointRadiiDesignRequest(
                context=context,
                primary_outer_radius_at_zero_shift=spec.primary_outer_radius_at_zero_shift,
                secondary_outer_radius_at_zero_shift=spec.secondary_outer_radius_at_zero_shift,
            )
        )
        path = sample_geometry_path(design, sample_count=11)
        plane = evaluate_radius_plane(
            belt=spec.belt,
            center_distance=spec.center_distance,
            primary_outer_radius=np.linspace(
                spec.primary_outer_radius_at_zero_shift,
                spec.primary_outer_radius_at_max_shift,
                5,
            ),
            secondary_outer_radius=np.linspace(
                spec.secondary_outer_radius_at_max_shift,
                spec.secondary_outer_radius_at_zero_shift,
                5,
            ),
        )
        sensitivity = evaluate_ratio_sensitivity_field(
            belt=spec.belt,
            center_distance=spec.center_distance,
            sheave_half_angle=spec.sheave_half_angle,
            primary_outer_radius=plane.primary_outer_radius,
            secondary_outer_radius=plane.secondary_outer_radius,
        )
        clamping = sample_pulley_clamping_force(
            PulleyClampingForceStudyRequest(
                cvt=self.assembly,
                pulley=PulleyLocation.OUTPUT,
                point=ActuationOperatingPoint(
                    time=0.0,
                    shift_position=spec.deadzone_shift,
                ),
                axes=(
                    ActuationResponseAxis(
                        ClosureUnknown.SECONDARY_TORQUE,
                        (0.0, 50.0),
                    ),
                ),
            )
        )
        payloads = (
            project_geometry_path(path),
            project_radius_plane(plane),
            project_ratio_sensitivity_field(sensitivity),
            project_clamping_force_response(clamping),
        )
        for payload in payloads:
            json.dumps(payload)
            self.assertIn("columns", payload)
            self.assertTrue(payload["columns"])
            self.assertTrue(
                all(
                    "key" in column and "unit" in column
                    for column in payload["columns"]
                )
            )

    def test_piecewise_constant_road_profile_document_is_executable_by_distance(
        self,
    ) -> None:
        configuration, _ = build_operating_configuration(self.baseline.constants)
        case = replace(self.baseline.case, cvt=self.assembly)
        case = replace(
            case,
            scenario=replace(
                case.scenario,
                initial_state=launch_initial_state(primary_rpm=1800.0),
            ),
        )
        document = encode_simulation_case_document(
            case,
            operating_system_config=configuration,
            integrator_settings=HybridIntegratorSettings(max_step=0.01),
        )
        document["output_boundary"]["road_profile"] = {
            "kind": "piecewise_constant_grade",
            "segments": [
                {"start_distance_m": 0.0, "grade_angle_rad": 0.0},
                {"start_distance_m": 90.0, "grade_angle_rad": 0.5235987755982988},
            ],
        }

        report = validate_simulation_case_document(document)
        self.assertTrue(report.is_valid, [item.message for item in report.findings])

        decoded = decode_simulation_case_document(document)
        boundary = decoded.case.output_boundary
        self.assertAlmostEqual(
            boundary.road_profile.sample(vehicle_distance=0.0).grade_angle, 0.0
        )
        self.assertAlmostEqual(
            boundary.road_profile.sample(vehicle_distance=89.999).grade_angle, 0.0
        )
        self.assertAlmostEqual(
            boundary.road_profile.sample(vehicle_distance=90.0).grade_angle,
            0.5235987755982988,
        )

        round_trip = encode_simulation_case_document(
            decoded.case,
            operating_system_config=decoded.operating_system_config,
            integrator_settings=decoded.integrator_settings,
            reporting_settings=decoded.reporting_settings,
        )
        self.assertEqual(
            round_trip["output_boundary"]["road_profile"]["kind"],
            "piecewise_constant_grade",
        )

    def test_result_metrics_and_projection_are_derived_without_a_second_simulation(
        self,
    ) -> None:
        configuration, _ = build_operating_configuration(self.baseline.constants)
        case = replace(self.baseline.case, cvt=self.assembly)
        system = configuration.build(case)
        result = system.run(
            time_span=(0.0, 0.3),
            initial_state=launch_initial_state(primary_rpm=1800.0),
            settings=HybridIntegratorSettings(
                method="LSODA",
                relative_tolerance=3.0e-5,
                absolute_tolerance=1.0e-7,
                max_step=0.01,
                maximum_transitions=30,
            ),
        )
        metrics = summarize_simulation(result)
        self.assertGreater(metrics.duration_s, 0.0)
        self.assertGreaterEqual(metrics.transition_count, 0)
        self.assertIsNotNone(metrics.primary_angular_speed_max_rad_per_s)

        payload = project_simulation_result(result)
        json.dumps(payload)
        self.assertEqual(payload["kind"], "simulation_result")
        self.assertIn("metrics", payload)
        self.assertIn("report_table", payload)
        self.assertGreater(payload["report_table"]["row_count"], 0)
        self.assertNotIn("segments", payload)
        self.assertNotIn("reported_segments", payload)


if __name__ == "__main__":
    unittest.main()
