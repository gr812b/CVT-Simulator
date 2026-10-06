"""Focused adapter tests. CINDER geometry/persistence are explicit test doubles.

Run from backend/: python -m pytest test/test_tune_preview_adapter.py
The production functions are loaded from the current source; these checks do
not claim to run CINDER or an application/database integration.
"""

from __future__ import annotations

import ast
import copy
import json
import math
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from app.schemas.scene import SceneFrame, SceneGeometry, ScenePreview, TuneScenePreview
from app.application.tune_preview import build_tune_preview, _profile_trace

ROOT = Path(__file__).resolve().parents[2]


def source_functions(path, names, **environment):
    """Isolate pure function bodies from unrelated DB/application imports."""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes} == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / path), "exec"), environment)
    return NS(**{name: environment[name] for name in names})


class ApiProblem(Exception):
    def __init__(self, status, code, message, *details):
        super().__init__(message)
        self.status, self.code = status, code


class PlacementChecks(unittest.TestCase):
    def setUp(self):
        self.source = {
            "pulleys": {
                "primary": {
                    "components": [
                        {
                            "kind": "fixed_pivot_roller_flyweight",
                            "geometry": {
                                "arm_length_m": 0.04,
                                "pivot_axial_position_m": 0.02,
                                "pivot_radius_m": 0.03,
                                "ramp_reference_axial_position_m": -0.015,
                                "ramp_reference_radius_m": 0.08,
                                "ramp_profile": {
                                    "kind": "piecewise_ramp",
                                    "segments": [
                                        {
                                            "kind": "linear_segment",
                                            "length_m": 0.05,
                                            "angle_rad": 0.4,
                                        }
                                    ],
                                },
                            },
                            "mass_geometry": {
                                "mass_per_flyweight_kg": 0.1,
                                "number_of_flyweights": 3,
                                "first_moment_u_kg_m": 0.002,
                                "second_moment_u_kg_m2": 0.0001,
                            },
                        }
                    ]
                },
                "secondary": {"components": []},
            },
        }
        self.api = source_functions(
            "backend/app/application/experiment_tuning.py",
            ["parameters", "apply_values", "pointer"],
            math=math,
            deepcopy=copy.deepcopy,
            readable_tuning_schema=lambda *args: {"parameters": []},
            ApiProblem=ApiProblem,
        )
        self.params = self.api.parameters(copy.deepcopy(self.source), {})
        self.axes = {p["key"]: p for p in self.params if p.get("subgroup") == "ramp_position"}

    def geometry(self, assembly):
        return assembly["pulleys"]["primary"]["components"][0]["geometry"]

    def test_defaults_are_signed_offsets_from_pivot(self):
        self.assertAlmostEqual(self.axes["primary_ramp_axial_offset"]["default"], -0.035)
        self.assertAlmostEqual(self.axes["primary_ramp_radial_offset"]["default"], 0.05)
        self.assertEqual({p["unit"] for p in self.axes.values()}, {"m"})
        self.assertEqual({p["group"] for p in self.axes.values()}, {"primary"})

    def test_both_offsets_are_applied_in_native_assembly_coordinates(self):
        result = copy.deepcopy(self.source)
        self.api.apply_values(
            result,
            self.params,
            {"primary_ramp_axial_offset": -0.05, "primary_ramp_radial_offset": 0.07},
        )
        g = self.geometry(result)
        self.assertAlmostEqual(g["ramp_reference_axial_position_m"], -0.03)
        self.assertAlmostEqual(g["ramp_reference_radius_m"], 0.10)
        self.assertEqual(g["pivot_axial_position_m"], 0.02)
        self.assertEqual(g["pivot_radius_m"], 0.03)
        self.assertEqual(g["arm_length_m"], 0.04)
        self.assertEqual(g["ramp_profile"], self.geometry(self.source)["ramp_profile"])

    def test_legacy_tune_with_no_offsets_preserves_placement(self):
        result = copy.deepcopy(self.source)
        self.api.apply_values(result, self.params, {})
        self.assertEqual(result, self.source)

    def test_default_values_roundtrip_to_original_placement(self):
        result = copy.deepcopy(self.source)
        self.api.apply_values(
            result, self.params, {key: field["default"] for key, field in self.axes.items()}
        )
        for key in ("ramp_reference_axial_position_m", "ramp_reference_radius_m"):
            self.assertAlmostEqual(self.geometry(result)[key], self.geometry(self.source)[key])

    def test_saved_intent_roundtrips_to_same_geometry(self):
        values = {"primary_ramp_axial_offset": -0.042, "primary_ramp_radial_offset": 0.091}
        saved = json.loads(json.dumps({"kind": "tunes", "values": values}))
        first, reopened = copy.deepcopy(self.source), copy.deepcopy(self.source)
        self.api.apply_values(first, self.params, values)
        self.api.apply_values(reopened, self.params, saved["values"])
        self.assertEqual(first, reopened)

    def test_axial_edit_does_not_move_radial_reference_or_pivot(self):
        result = copy.deepcopy(self.source)
        self.api.apply_values(result, self.params, {"primary_ramp_axial_offset": -0.01})
        expected = copy.deepcopy(self.source)
        self.geometry(expected)["ramp_reference_axial_position_m"] = 0.01
        self.assertEqual(result, expected)

    def test_nonfinite_and_boolean_offsets_are_rejected(self):
        for value in (float("nan"), float("inf"), True, "1"):
            with self.subTest(value=value), self.assertRaises(ApiProblem):
                self.api.apply_values(
                    copy.deepcopy(self.source), self.params, {"primary_ramp_axial_offset": value}
                )

    def test_offset_is_relative_even_with_different_coordinate_origin(self):
        shifted = copy.deepcopy(self.source)
        g = self.geometry(shifted)
        for field in ("ramp_reference_axial_position_m", "pivot_axial_position_m"):
            g[field] += 0.2
        params = self.api.parameters(shifted, {})
        self.api.apply_values(shifted, params, {"primary_ramp_axial_offset": -0.05})
        self.assertAlmostEqual(self.geometry(shifted)["ramp_reference_axial_position_m"], 0.17)


class Profile:
    x_min, x_max = 0.0, 0.1

    def evaluate(self, x):
        return NS(value=0.2 * x + x**3, first_derivative=0.2 + 3 * x**2)

    def junction_continuity(self):
        return [NS(coordinate=0.050001), NS(coordinate=0.050011)]


class Surface:
    fail_after = None
    fail_initial = False
    requested = None

    def __init__(self, spec):
        self.spec = spec

    def ramp_surface_point(self, *, contact_coordinate, axial_position):
        return axial_position + contact_coordinate, 0.05 + 0.2 * contact_coordinate

    def trace_contact_branch(self, positions, *, require_complete):
        assert require_complete is False
        assert positions[0] == self.spec.axial_position_min
        assert all(b > a for a, b in zip(positions, positions[1:]))
        Surface.requested = positions.copy()
        if self.fail_initial:
            raise ValueError("Interference at initial position")
        result = []
        for x in positions:
            if self.fail_after is not None and x > self.fail_after:
                break
            coordinate = 0.01 + 0.5 * x
            result.append(
                NS(
                    contact_coordinate=coordinate,
                    roller_center_axial_position=x + coordinate,
                    roller_center_radius=0.055 + 0.2 * coordinate,
                    angle=0.2 + 3 * x,
                )
            )
        return result


class PathGeometry:
    def __init__(self, spec):
        pass

    def evaluate(self, shift):
        return NS(
            primary_axial_coordinate=NS(value=shift),
            secondary_axial_coordinate=NS(value=-0.6 * max(0, shift - 0.004)),
        )


class Coupling:
    opening_offset = 0.01
    opening_per_axial_position = -1.5
    profile = NS(
        circumferential_profile=Profile(),
        radius=0.03,
        opening_travel_min=0.0,
        opening_travel_max=0.1,
        evaluate=lambda q: NS(theta=q / 0.03 * 0.2),
    )

    def evaluate_from_local_coordinate(
        self, *, axial_position, d_axial_position_ds, d2_axial_position_ds2
    ):
        return NS(
            theta=(self.opening_offset + self.opening_per_axial_position * axial_position)
            * 0.2
            / 0.03,
            dtheta_ds=self.opening_per_axial_position * 0.2 / 0.03 * d_axial_position_ds,
        )


class Gateway:
    def validate_assembly_shape(self, document):
        return document

    def _scene_geometry_spec(self, document):
        return NS(max_shift=0.02, deadzone_shift=0.004)

    def scene_preview(self, document, *, frame_count):
        import numpy as np

        return ScenePreview(
            geometry=SceneGeometry(
                belt_outer_width_m=0.02,
                belt_inner_width_m=0.01,
                belt_height_m=0.01,
                cord_depth_from_outer_m=0.002,
                sheave_half_angle_rad=0.3,
                center_distance_m=0.3,
                primary_outer_radius_min_m=0.02,
                primary_outer_radius_max_m=0.08,
                secondary_outer_radius_min_m=0.03,
                secondary_outer_radius_max_m=0.09,
                deadzone_shift_m=0.004,
                max_shift_m=0.02,
            ),
            frames=[
                SceneFrame(
                    shift_m=float(s),
                    primary_outer_radius_m=0.02 + s,
                    secondary_outer_radius_m=0.09 - s,
                    belt_axial_position_m=0,
                    belt_path_m=[(0.0, 0.0), (1.0, 1.0)],
                    belt_regions=["span", "span"],
                )
                for s in np.linspace(0, 0.02, frame_count)
            ],
        )


class PreviewChecks(unittest.TestCase):
    def setUp(self):
        self.spec = NS(
            axial_position_min=0.0,
            axial_position_max=0.02,
            ramp_profile=Profile(),
            pivot_axial_position=-0.02,
            pivot_radius=0.03,
            roller_radius=0.005,
            roller_side_sign=1,
            ramp_reference_axial_position=0.0,
            ramp_axial_direction=1,
            ramp_reference_radius=0.05,
        )
        self.assembly = {
            "geometry": {},
            "pulleys": {
                "primary": {
                    "components": [
                        {
                            "kind": "fixed_pivot_roller_flyweight",
                            "geometry": {"arm_length_m": 0.04},
                            "mass_geometry": {
                                "number_of_flyweights": 3,
                                "mass_per_flyweight_kg": 0.17,
                                "first_moment_u_kg_m": 0.0064,
                                "second_moment_u_kg_m2": 0.0002506666666666667,
                            },
                        }
                    ]
                },
                "secondary": {"components": [{"kind": "axial_spring"}]},
            },
        }
        self.report = {"is_valid": True, "findings": []}
        self.audit_inputs = []

        def audit(assembly):
            self.audit_inputs.append(copy.deepcopy(assembly))
            raise AssertionError("Editing must not run the full construction audit")

        modules = {}
        for name in (
            "cinder.contracts.document",
            "cinder.model.cvt.actuation.fixed_pivot_flyweight",
            "cinder.model.cvt.geometry",
            "app.application.input_validation",
        ):
            modules[name] = types.ModuleType(name)
        modules["cinder.contracts.document"]._decode_flyweight_geometry = lambda _: self.spec
        modules["cinder.contracts.document"]._decode_pulley = lambda *a, **k: NS(
            helical_coupling=Coupling()
        )
        modules[
            "cinder.model.cvt.actuation.fixed_pivot_flyweight"
        ].PivotedRollerFollowerGeometry = Surface
        modules["cinder.model.cvt.geometry"].BeltPulleyGeometry = PathGeometry
        modules["app.application.input_validation"].validate_assembly = audit
        ctx = patch.dict(sys.modules, modules)
        ctx.start()
        self.addCleanup(ctx.stop)
        Surface.fail_initial, Surface.fail_after = False, None

    def test_complete_preview_uses_only_the_quick_contact_trace(self):
        result = build_tune_preview(Gateway(), self.assembly)
        self.assertTrue(result.validation["is_valid"])
        self.assertAlmostEqual(result.geometry.mechanisms.primary.tip_mass_per_flyweight_kg, 0.15)
        self.assertEqual(self.audit_inputs, [])
        self.assertIsNone(result.primary_contact_failure_m)
        self.assertTrue(all(x is not None for x in result.primary_arm_angles_rad))
        self.assertIn(0.0, Surface.requested)
        self.assertIn(0.02, Surface.requested)
        self.assertGreaterEqual(len(Surface.requested), 129)
        self.assertLessEqual(len(Surface.requested), 129 + len(result.frames) + 1)

    def test_late_contact_loss_disables_submission_without_a_full_audit(self):
        Surface.fail_after = 0.012
        result = build_tune_preview(Gateway(), self.assembly)
        self.assertFalse(result.validation["is_valid"])
        self.assertGreater(result.primary_contact_failure_m, 0.012)
        self.assertLess(result.primary_contact_failure_m, 0.0122)
        self.assertIsNotNone(result.primary_arm_angles_rad[0])
        self.assertIsNone(result.primary_arm_angles_rad[-1])
        self.assertTrue(
            any(
                f["code"] == "actuation.primary_contact_incomplete"
                for f in result.validation["findings"]
            )
        )
        self.assertEqual(self.report, {"is_valid": True, "findings": []})

    def test_missing_final_endpoint_is_not_accepted(self):
        Surface.fail_after = 0.02 - 1e-12
        result = build_tune_preview(Gateway(), self.assembly)
        self.assertFalse(result.validation["is_valid"])
        self.assertEqual(result.primary_contact_failure_m, 0.02)
        self.assertIsNotNone(result.primary_arm_angles_rad[-2])
        self.assertIsNone(result.primary_arm_angles_rad[-1])

    def test_missing_initial_contact_is_not_accepted(self):
        Surface.fail_initial = True
        result = build_tune_preview(Gateway(), self.assembly)
        self.assertFalse(result.validation["is_valid"])
        self.assertEqual(result.primary_contact_failure_m, 0.0)
        self.assertTrue(all(x is None for x in result.primary_arm_angles_rad))

    def test_a_partial_prefix_never_resumes_on_a_different_branch(self):
        Surface.fail_after = 0.005
        result = build_tune_preview(Gateway(), self.assembly)
        valid = [x is not None for x in result.primary_arm_angles_rad]
        first = valid.index(False)
        self.assertTrue(all(not x for x in valid[first:]))
        self.assertTrue(any("no alternative contact branch" in w for w in result.warnings))

    def test_operating_interval_shorter_than_required_travel_is_invalid(self):
        self.spec.axial_position_max = 0.015
        result = build_tune_preview(Gateway(), self.assembly)
        self.assertFalse(result.validation["is_valid"])
        self.assertIsNone(result.primary_arm_angles_rad[-1])

    def test_no_overlap_of_operating_and_required_intervals_is_invalid(self):
        self.spec.axial_position_min, self.spec.axial_position_max = 0.04, 0.05
        result = build_tune_preview(Gateway(), self.assembly)
        self.assertFalse(result.validation["is_valid"])
        self.assertEqual(result.primary_contact_failure_m, 0.0)

    def test_editing_leaves_full_construction_validation_to_save(self):
        # Even an audit failure is not computed in the preview. Save's own
        # validation below remains authoritative and rejects that same draft.
        result = build_tune_preview(Gateway(), self.assembly)
        self.assertTrue(result.validation["is_valid"])
        self.assertTrue(all(x is not None for x in result.primary_arm_angles_rad))
        self.assertEqual(self.audit_inputs, [])

    def test_repeated_edits_do_not_schedule_full_audits(self):
        for offset in (-0.003, 0.001, 0.005):
            self.assembly["pulleys"]["primary"]["components"][0]["geometry"][
                "ramp_reference_axial_position_m"
            ] = offset
            self.assertTrue(build_tune_preview(Gateway(), self.assembly).validation["is_valid"])
        self.assertEqual(self.audit_inputs, [])

    def test_malformed_assembly_is_rejected_by_lightweight_shape_check(self):
        class InvalidGateway(Gateway):
            def validate_assembly_shape(self, document):
                raise ValueError("Malformed assembly")

        with self.assertRaisesRegex(ValueError, "Malformed assembly"):
            build_tune_preview(InvalidGateway(), self.assembly)
        self.assertEqual(self.audit_inputs, [])

    def test_primary_profile_is_sampled_at_exact_contact_coordinates(self):
        result = build_tune_preview(Gateway(), self.assembly)
        for coordinate in result.primary_contact_coordinates_m:
            self.assertIn(coordinate, result.primary_profile.coordinates_m)
        for x, angle in zip(
            result.primary_profile.coordinates_m, result.primary_profile.slope_angles_rad
        ):
            self.assertAlmostEqual(angle, math.atan(0.2 + 3 * x * x))

    def test_short_transitions_have_interior_samples_and_exact_joins(self):
        result = _profile_trace(Profile(), used=(0.01, 0.04))
        self.assertIn(0.01, result.coordinates_m)
        self.assertIn(0.04, result.coordinates_m)
        self.assertGreaterEqual(sum(0.050001 <= x <= 0.050011 for x in result.coordinates_m), 17)

    def test_secondary_percent_window_uses_actual_coupling(self):
        result = build_tune_preview(Gateway(), self.assembly)
        self.assertAlmostEqual(result.secondary_opening_m[0], 0.01)
        self.assertAlmostEqual(result.secondary_opening_m[-1], 0.01 + 1.5 * 0.6 * (0.02 - 0.004))
        self.assertIn(result.secondary_opening_m[-1], result.secondary_profile.coordinates_m)

    def test_required_contract_rejects_an_older_unvalidated_response(self):
        result = build_tune_preview(Gateway(), self.assembly)
        encoded = result.model_dump()
        encoded.pop("validation")
        with self.assertRaises(ValueError):
            TuneScenePreview.model_validate(encoded)
        self.assertIn("validation", TuneScenePreview.model_json_schema()["required"])

    def test_response_roundtrip_and_no_assembly_mutation(self):
        before = copy.deepcopy(self.assembly)
        result = build_tune_preview(Gateway(), self.assembly)
        self.assertEqual(TuneScenePreview.model_validate_json(result.model_dump_json()), result)
        self.assertEqual(self.assembly, before)
        self.assertEqual(len(result.frames), len(result.primary_arm_angles_rad))
        self.assertEqual(len(result.frames), len(result.secondary_opening_m))


class SaveAuditChecks(unittest.TestCase):
    def test_save_rejects_failed_cinder_audit_independently_of_browser(self):
        calls = []
        report = {
            "is_valid": False,
            "findings": [{"message": "No roller contact at full closure."}],
        }
        service = source_functions(
            "backend/app/application/experiments.py",
            ["validate_document"],
            validate_scenario=lambda *_: None,
            cvt_tuning=lambda *_: (NS(cvt_design_id="cvt"), {}, []),
            apply_values=lambda *_: calls.append("values"),
            CinderGateway=lambda: NS(validate_assembly_shape=lambda _: calls.append("shape")),
            validate_assembly=lambda _: report,
            ApiProblem=ApiProblem,
        )
        with self.assertRaises(ApiProblem) as error:
            service.validate_document(
                None, None, NS(kind="tunes", cvt_revision_id="r", values={}), None
            )
        self.assertEqual(error.exception.status, 422)
        self.assertEqual(calls, ["values", "shape"])
        self.assertIn("No roller contact", str(error.exception))

    def test_save_still_runs_full_audit_once_per_explicit_submission(self):
        calls = []
        service = source_functions(
            "backend/app/application/experiments.py",
            ["validate_document"],
            validate_scenario=lambda *_: None,
            cvt_tuning=lambda *_: (NS(cvt_design_id="cvt"), {}, []),
            apply_values=lambda *_: calls.append("values"),
            CinderGateway=lambda: NS(validate_assembly_shape=lambda _: calls.append("shape")),
            validate_assembly=lambda _: calls.append("full_audit")
            or {"is_valid": True, "findings": []},
            ApiProblem=ApiProblem,
        )
        self.assertEqual(
            service.validate_document(
                None, None, NS(kind="tunes", cvt_revision_id="r", values={}), None
            ),
            "cvt",
        )
        self.assertEqual(calls, ["values", "shape", "full_audit"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
