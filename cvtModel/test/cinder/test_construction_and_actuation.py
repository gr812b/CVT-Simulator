from __future__ import annotations

import unittest

from cinder.execution.hybrid.cvt_operating_hybrid import CVTOperatingHybridSystem
from cinder.model.cvt.actuation import (
    HelicalCouplingState,
    HelicalTorqueReactionForce,
    PulleyActuationContext,
    PulleyClosureChannels,
)
from cinder.model.cvt.closure import ClosureUnknown
from cinder.model.boundaries.output.vehicle import ConstantGradeRoadProfile
from cinder.model.system import CVTDynamicsModel
from fixtures import build_baja_trial_baseline
from fixtures import (
    build_operating_configuration,
    build_operating_system,
    build_system_from_case,
    case_with_output_road_profile,
)


class ConstructionAndActuationTest(unittest.TestCase):
    def test_baseline_exposes_case_not_prebuilt_model(self) -> None:
        baseline = build_baja_trial_baseline()
        self.assertFalse(hasattr(baseline, "model"))
        self.assertIs(baseline.case.cvt, baseline.assembly)

    def test_runtime_system_is_built_only_from_case(self) -> None:
        system, baseline = build_operating_system(build_baja_trial_baseline().constants)
        self.assertIsInstance(system, CVTOperatingHybridSystem)
        self.assertFalse(hasattr(system, "case"))
        self.assertIs(system.model.output_boundary, baseline.case.output_boundary)

    def test_route_edit_replaces_case_boundary_then_rebuilds(self) -> None:
        baseline = build_baja_trial_baseline()
        configuration, _ = build_operating_configuration(baseline.constants)
        road = ConstantGradeRoadProfile(grade_angle=0.12)
        edited_case = case_with_output_road_profile(baseline.case, road)
        rebuilt = build_system_from_case(edited_case, configuration=configuration)
        self.assertIs(rebuilt.model.output_boundary.road_profile, road)
        self.assertIsNot(rebuilt.model.output_boundary, baseline.case.output_boundary)

    def test_runtime_model_rejects_direct_construction(self) -> None:
        with self.assertRaises(TypeError):
            CVTDynamicsModel()

    def test_helix_uses_host_context_not_pulley_name(self) -> None:
        baseline = build_baja_trial_baseline()
        model = CVTOperatingHybridSystem.from_case(
            baseline.case,
            traction_law=build_operating_system(baseline.constants)[0].traction_law,
            solve_settings=build_operating_system(baseline.constants)[0].solve_settings,
            operating_limits=build_operating_system(baseline.constants)[0].operating_limits,
        ).model
        snapshot = model.snapshot_at_time(time=0.0, state=baseline.active_shift_state)
        helix = next(
            law
            for law in model.secondary_actuator.force_laws
            if isinstance(law, HelicalTorqueReactionForce)
        )
        coordinate = snapshot.geometry.secondary_axial_coordinate
        coupling = model.output_helical_coupling
        base = dict(
            axial_position=coordinate.value,
            axial_speed=coordinate.d_value_ds * baseline.active_shift_state.shift_speed,
            shaft_speed=baseline.active_shift_state.secondary_angular_speed,
            shift_speed=baseline.active_shift_state.shift_speed,
            helical_coupling=HelicalCouplingState(
                kinematics=snapshot.secondary_helix,
                opening_per_axial_position=coupling.opening_per_axial_position,
                opening_offset=coupling.opening_offset,
            ),
            movable_member_rotational_inertia=(
                model.inertias.secondary.movable_sheave_rotational_inertia
            ),
        )
        output_relation = helix.evaluate(
            PulleyActuationContext(
                time=0.0,
                closure_channels=PulleyClosureChannels.output_pulley(),
                **base,
            )
        )
        input_relation = helix.evaluate(
            PulleyActuationContext(
                time=0.0,
                closure_channels=PulleyClosureChannels.input_pulley(),
                **base,
            )
        )
        self.assertAlmostEqual(output_relation.bias, input_relation.bias)
        self.assertNotEqual(output_relation.gains[ClosureUnknown.SECONDARY_TORQUE], 0.0)
        self.assertEqual(output_relation.gains[ClosureUnknown.PRIMARY_TORQUE], 0.0)
        self.assertNotEqual(input_relation.gains[ClosureUnknown.PRIMARY_TORQUE], 0.0)
        self.assertEqual(input_relation.gains[ClosureUnknown.SECONDARY_TORQUE], 0.0)


if __name__ == "__main__":
    unittest.main()
