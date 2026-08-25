from __future__ import annotations

import json
from dataclasses import replace
from math import isclose, isfinite
from pathlib import Path

from cinder.contracts import (
    decode_assembly_document,
    decode_simulation_case_document,
    encode_assembly_document,
    validate_simulation_case_document,
)
from cinder.execution.hybrid.cvt_impact import (
    CVTVelocityTopology,
    kinetic_energy_for_topology,
)
from cinder.model.cvt.actuation import (
    FixedPivotFlyweightForce,
    FixedPivotFlyweightForceSpec,
    FlyweightMassGeometry,
    PivotedRollerFollowerFlyweightMap,
    PivotedRollerFollowerGeometrySpec,
    PulleyActuationContext,
    PulleyActuator,
    PulleyClosureChannels,
)
from cinder.model.cvt.closure import AffineClosureScalar, ClosureGains
from cinder.model.cvt.dynamics.deadzone.free import (
    solve_deadzone_secondary_rotation,
)
from cinder.model.cvt.dynamics.deadzone.snapshot import build_deadzone_snapshot
from cinder.model.cvt.profiles import LinearSegment, PiecewiseRamp
from cinder.model.system import MechanicalCVTPlant
from cinder.model.system.ports import CVTShaftBoundaryValues, ShaftBoundaryValue
from cinder.model.system.state import CVTState

ROOT = Path(__file__).resolve().parents[2]
ASSEMBLY = ROOT / "examples" / "baja_baseline_assembly.json"
SIMULATION_CASE = ROOT / "examples" / "baja_baseline_simulation_case.json"


def _baseline_assembly():
    return decode_assembly_document(json.loads(ASSEMBLY.read_text(encoding="utf-8")))


def _fixed_pivot_map(
    *,
    axial_position_min: float = 0.0,
    axial_position_max: float = 0.02,
) -> PivotedRollerFollowerFlyweightMap:
    # A transparent, regular straight-ramp mechanism used only for regression.
    # The physical ramp has negative local slope; translating it in +x makes
    # the fixed-pivot arm rotate outward with q'(x) > 0.
    profile = PiecewiseRamp(
        (LinearSegment(length=0.12, angle_degrees=-30.0),)
    )
    geometry = PivotedRollerFollowerGeometrySpec(
        pivot_axial_position=0.0,
        pivot_radius=0.05,
        arm_length=0.04,
        roller_radius=0.005,
        ramp_reference_axial_position=-axial_position_min,
        ramp_reference_radius=0.05,
        ramp_profile=profile,
        axial_position_min=axial_position_min,
        axial_position_max=axial_position_max,
        roller_side_sign=-1,
        root_scan_points=129,
        validation_positions=9,
    )
    mass = FlyweightMassGeometry.uniform_arm_with_end_mass(
        number_of_flyweights=3,
        arm_length=0.04,
        arm_mass_per_flyweight=0.05,
        end_mass_per_flyweight=0.10,
    )
    return PivotedRollerFollowerFlyweightMap(
        geometry_spec=geometry,
        mass_geometry=mass,
        compilation_points=65,
    )


def _fixed_pivot_force(**map_kwargs) -> FixedPivotFlyweightForce:
    return FixedPivotFlyweightForce(
        FixedPivotFlyweightForceSpec(
            mechanism_map=_fixed_pivot_map(**map_kwargs)
        )
    )


def test_appendix_geometry_returns_q_j_i_and_verified_derivatives() -> None:
    mechanism = _fixed_pivot_map()
    x = 0.011
    step = 2.0e-6
    sample = mechanism.evaluate(x)
    exact = mechanism.evaluate_exact(x)
    lower = mechanism.evaluate_exact(x - step)
    upper = mechanism.evaluate_exact(x + step)

    q_gradient_fd = (upper.angle - lower.angle) / (2.0 * step)
    q_curvature_fd = (
        upper.angle_gradient - lower.angle_gradient
    ) / (2.0 * step)
    inertia_gradient_fd = (
        upper.shaft_inertia - lower.shaft_inertia
    ) / (2.0 * step)

    assert isclose(exact.angle_gradient, q_gradient_fd, rel_tol=2.0e-7)
    assert isclose(exact.angle_curvature, q_curvature_fd, rel_tol=2.0e-6, abs_tol=1e-7)
    assert isclose(
        exact.shaft_inertia_gradient,
        inertia_gradient_fd,
        rel_tol=2.0e-7,
    )
    assert isclose(sample.angle, exact.angle, rel_tol=0.0, abs_tol=2.0e-11)
    assert isclose(
        sample.angle_gradient,
        exact.angle_gradient,
        rel_tol=2.0e-8,
    )
    assert isclose(
        sample.angle_curvature,
        exact.angle_curvature,
        rel_tol=3.0e-5,
        abs_tol=3.0e-4,
    )
    assert sample.angle_gradient > 0.0
    assert sample.pivot_inertia > 0.0


def test_fixed_pivot_force_targets_whichever_pulley_owns_it() -> None:
    law = _fixed_pivot_force()
    x = 0.01
    x_dot = 0.02
    omega = 200.0
    sample = law.spec.mechanism_map.evaluate(x)

    def element(*, primary: bool):
        axial_gain = 0.8 if primary else -0.65
        axial_bias = 0.004 if primary else -0.002
        context = PulleyActuationContext(
            time=0.0,
            axial_position=x,
            axial_speed=x_dot,
            shaft_speed=omega,
            shift_speed=0.03,
            axial_acceleration=AffineClosureScalar(
                bias=axial_bias,
                gains=ClosureGains(shift_acceleration=axial_gain),
            ),
            closure_channels=(
                PulleyClosureChannels.primary()
                if primary
                else PulleyClosureChannels.secondary()
            ),
        )
        return context, law.evaluate_element(context)

    primary_context, primary = element(primary=True)
    secondary_context, secondary = element(primary=False)

    expected_primary_bias = (
        0.5 * omega**2 * sample.shaft_inertia_gradient
        - sample.pivot_inertia
        * sample.angle_gradient
        * sample.angle_curvature
        * x_dot**2
        - sample.pivot_inertia
        * sample.angle_gradient**2
        * primary_context.axial_acceleration.bias
    )
    assert isclose(primary.closing_force.bias, expected_primary_bias)
    assert isclose(
        primary.closing_force.gains.shift_acceleration,
        -sample.pivot_inertia * sample.angle_gradient**2 * 0.8,
    )
    assert isclose(
        secondary.closing_force.gains.shift_acceleration,
        -sample.pivot_inertia * sample.angle_gradient**2 * -0.65,
    )

    assert isclose(
        primary.shaft_torque.gains.primary_angular_acceleration,
        -sample.shaft_inertia,
    )
    assert primary.shaft_torque.gains.secondary_angular_acceleration == 0.0
    assert isclose(
        secondary.shaft_torque.gains.secondary_angular_acceleration,
        -sample.shaft_inertia,
    )
    assert secondary.shaft_torque.gains.primary_angular_acceleration == 0.0
    expected_redistribution = -sample.shaft_inertia_gradient * x_dot * omega
    assert isclose(primary.shaft_torque.bias, expected_redistribution)
    assert isclose(secondary.shaft_torque.bias, expected_redistribution)


def test_event_metric_collects_fixed_pivot_modes_from_either_pulley() -> None:
    baseline = _baseline_assembly()
    shift = baseline.geometry.spec.deadzone_shift + 0.35 * (
        baseline.geometry.spec.max_shift - baseline.geometry.spec.deadzone_shift
    )
    state = CVTState(
        primary_angular_speed=260.0,
        secondary_angular_speed=110.0,
        belt_speed=8.0,
        shift_position=shift,
        shift_speed=0.025,
    )

    def energy(assembly) -> float:
        return kinetic_energy_for_topology(
            model=MechanicalCVTPlant.from_assembly(assembly),
            state=state,
            topology=CVTVelocityTopology.ENGAGED,
        )

    primary_spring = baseline.pulleys.primary.actuator.force_laws[1]
    primary_reference = replace(
        baseline.pulleys.primary,
        actuator=PulleyActuator(primary_spring),
    )
    primary_force = _fixed_pivot_force(
        axial_position_min=0.0,
        axial_position_max=baseline.geometry.spec.max_shift,
    )
    primary_with_flyweight = replace(
        baseline.pulleys.primary,
        actuator=PulleyActuator(primary_force, primary_spring),
    )
    reference_assembly = replace(
        baseline,
        pulleys=replace(baseline.pulleys, primary=primary_reference),
    )
    primary_assembly = replace(
        baseline,
        pulleys=replace(baseline.pulleys, primary=primary_with_flyweight),
    )

    geometry = baseline.geometry.evaluate_engaged(shift)
    primary_coordinate = geometry.primary_axial_coordinate
    primary_sample = primary_force.spec.mechanism_map.evaluate(
        primary_coordinate.value
    )
    expected_primary = (
        0.5 * primary_sample.shaft_inertia * state.primary_angular_speed**2
        + 0.5
        * primary_sample.pivot_inertia
        * (
            primary_sample.angle_gradient
            * primary_coordinate.d_value_ds
            * state.shift_speed
        )
        ** 2
    )
    assert isclose(
        energy(primary_assembly) - energy(reference_assembly),
        expected_primary,
        rel_tol=2.0e-13,
        abs_tol=2.0e-13,
    )

    secondary_coordinate = geometry.secondary_axial_coordinate
    secondary_endpoints = (
        baseline.geometry.evaluate(0.0).secondary_axial_coordinate.value,
        baseline.geometry.evaluate(
            baseline.geometry.spec.max_shift
        ).secondary_axial_coordinate.value,
    )
    secondary_force = _fixed_pivot_force(
        axial_position_min=min(secondary_endpoints),
        axial_position_max=max(secondary_endpoints),
    )
    secondary_with_flyweight = replace(
        baseline.pulleys.secondary,
        actuator=PulleyActuator(
            *baseline.pulleys.secondary.actuator.force_laws,
            secondary_force,
        ),
    )
    secondary_assembly = replace(
        baseline,
        pulleys=replace(
            baseline.pulleys,
            primary=primary_reference,
            secondary=secondary_with_flyweight,
        ),
    )
    secondary_sample = secondary_force.spec.mechanism_map.evaluate(
        secondary_coordinate.value
    )
    expected_secondary = (
        0.5 * secondary_sample.shaft_inertia * state.secondary_angular_speed**2
        + 0.5
        * secondary_sample.pivot_inertia
        * (
            secondary_sample.angle_gradient
            * secondary_coordinate.d_value_ds
            * state.shift_speed
        )
        ** 2
    )
    assert isclose(
        energy(secondary_assembly) - energy(reference_assembly),
        expected_secondary,
        rel_tol=2.0e-13,
        abs_tol=2.0e-13,
    )


def test_secondary_flyweight_remains_in_deadzone_rotational_dynamics() -> None:
    baseline = _baseline_assembly()
    endpoint_positions = (
        baseline.geometry.evaluate(0.0).secondary_axial_coordinate.value,
        baseline.geometry.evaluate(
            baseline.geometry.spec.max_shift
        ).secondary_axial_coordinate.value,
    )
    flyweight = _fixed_pivot_force(
        axial_position_min=min(endpoint_positions),
        axial_position_max=max(endpoint_positions),
    )
    augmented_secondary = replace(
        baseline.pulleys.secondary,
        actuator=PulleyActuator(
            *baseline.pulleys.secondary.actuator.force_laws,
            flyweight,
        ),
    )
    augmented = replace(
        baseline,
        pulleys=replace(baseline.pulleys, secondary=augmented_secondary),
    )

    shift = 0.5 * baseline.geometry.spec.deadzone_shift
    locked = baseline.geometry.evaluate_deadzone(shift)
    state = CVTState(
        primary_angular_speed=180.0,
        secondary_angular_speed=90.0,
        belt_speed=locked.secondary.effective * 90.0,
        shift_position=shift,
        shift_speed=0.01,
    )
    boundaries = CVTShaftBoundaryValues(
        secondary=ShaftBoundaryValue(external_torque=12.0)
    )
    reference_snapshot = build_deadzone_snapshot(
        time=0.0,
        model=MechanicalCVTPlant.from_assembly(baseline),
        state=state,
        shaft_boundaries=boundaries,
    )
    augmented_snapshot = build_deadzone_snapshot(
        time=0.0,
        model=MechanicalCVTPlant.from_assembly(augmented),
        state=state,
        shaft_boundaries=boundaries,
    )
    reference_alpha = solve_deadzone_secondary_rotation(reference_snapshot)
    augmented_alpha = solve_deadzone_secondary_rotation(augmented_snapshot)

    local_x = locked.secondary_axial_coordinate.value
    sample = flyweight.spec.mechanism_map.evaluate(local_x)
    reference_effective_inertia = 12.0 / reference_alpha
    assert isclose(
        augmented_alpha,
        12.0 / (reference_effective_inertia + sample.shaft_inertia),
        rel_tol=2.0e-13,
    )
    assert augmented_alpha < reference_alpha


def test_fixed_pivot_flyweight_round_trips_through_public_document() -> None:
    baseline = _baseline_assembly()
    spring = baseline.pulleys.primary.actuator.force_laws[1]
    force = _fixed_pivot_force(
        axial_position_min=0.0,
        axial_position_max=baseline.geometry.spec.max_shift,
    )
    assembly = replace(
        baseline,
        pulleys=replace(
            baseline.pulleys,
            primary=replace(
                baseline.pulleys.primary,
                actuator=PulleyActuator(force, spring),
            ),
        ),
    )
    document = encode_assembly_document(assembly)
    component = document["pulleys"]["primary"]["components"][0]
    assert component["kind"] == "fixed_pivot_roller_flyweight"

    decoded = decode_assembly_document(document)
    decoded_force = decoded.pulleys.primary.actuator.force_laws[0]
    assert isinstance(decoded_force, FixedPivotFlyweightForce)
    x = 0.013
    original = force.spec.mechanism_map.evaluate(x)
    restored = decoded_force.spec.mechanism_map.evaluate(x)
    assert isclose(restored.angle, original.angle, rel_tol=0.0, abs_tol=1.0e-13)
    assert isclose(restored.angle_gradient, original.angle_gradient, rel_tol=1.0e-13)
    assert isclose(restored.shaft_inertia, original.shaft_inertia, rel_tol=1.0e-13)
    assert isclose(restored.pivot_inertia, original.pivot_inertia, rel_tol=1.0e-13)


def test_composed_case_with_fixed_pivot_flyweight_evaluates() -> None:
    baseline = _baseline_assembly()
    spring = baseline.pulleys.primary.actuator.force_laws[1]
    force = _fixed_pivot_force(
        axial_position_min=0.0,
        axial_position_max=baseline.geometry.spec.max_shift,
    )
    assembly = replace(
        baseline,
        pulleys=replace(
            baseline.pulleys,
            primary=replace(
                baseline.pulleys.primary,
                actuator=PulleyActuator(force, spring),
            ),
        ),
    )
    document = json.loads(SIMULATION_CASE.read_text(encoding="utf-8"))
    document["assembly"] = encode_assembly_document(assembly)
    report = validate_simulation_case_document(document)
    assert report.is_valid, [finding.message for finding in report.findings]

    decoded = decode_simulation_case_document(document)
    derivative = decoded.system.rhs(
        0.0,
        decoded.initial_state,
        decoded.initial_mode,
    )
    assert derivative.shape == decoded.initial_state.shape
    assert all(isfinite(float(value)) for value in derivative)

    result = decoded.system.run(
        time_span=(0.0, 0.05),
        initial_state=decoded.initial_state,
        initial_mode=decoded.initial_mode,
        settings=decoded.integrator_settings,
        reporting_settings=decoded.reporting_settings,
    )
    assert result.termination_reason == "final_time_reached"
    assert all(isfinite(float(value)) for value in result.final_state)
