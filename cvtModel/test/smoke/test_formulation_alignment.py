from __future__ import annotations

import json
from math import cos, isclose, pi
from pathlib import Path

import numpy as np

from cinder.contracts import decode_assembly_document
from cinder.model.cvt.actuation import (
    CentrifugalRampForce,
    CentrifugalRampForceSpec,
    HelicalCouplingState,
    HelicalTorqueReactionForce,
    HelicalTorqueReactionSpec,
    PulleyActuationContext,
    PulleyClosureChannels,
)
from cinder.model.cvt.closure import ClosureUnknowns
from cinder.model.cvt.contact import (
    ContactInterface,
    ContactTractionUtilization,
    KineticSlipSpecification,
    SlipDirection,
)
from cinder.model.cvt.dynamics.equation_context import TrialEquationContext
from cinder.model.cvt.dynamics.rows.primary_axial import build_primary_axial_equation
from cinder.model.cvt.dynamics.rows.primary_traction import (
    build_primary_traction_equation,
)
from cinder.model.cvt.dynamics.rows.secondary_axial import (
    build_secondary_axial_equation,
)
from cinder.model.cvt.dynamics.rows.secondary_traction import (
    build_secondary_traction_equation,
)
from cinder.model.cvt.profiles import (
    HelixProfile,
    LinearSegment,
    PiecewiseRamp,
    linear_helix_segment,
)
from cinder.model.system import HelicalPulleyCoupling, MechanicalCVTPlant
from cinder.model.system.state import CVTState

ROOT = Path(__file__).resolve().parents[2]
ASSEMBLY = ROOT / "examples" / "baja_baseline_assembly.json"


def _assembly():
    return decode_assembly_document(json.loads(ASSEMBLY.read_text(encoding="utf-8")))


def test_baseline_radius_roles_ratio_range_and_centroid_belt_mass() -> None:
    assembly = _assembly()
    geometry = assembly.geometry
    low = geometry.evaluate(0.0)
    high = geometry.evaluate(geometry.spec.max_shift)
    belt = geometry.spec.belt

    assert isclose(low.primary.outer, 0.0362077, rel_tol=0.0, abs_tol=1e-12)
    assert isclose(low.secondary.outer, 0.1016, rel_tol=0.0, abs_tol=1e-12)
    assert isclose(
        low.primary.effective,
        low.primary.outer - belt.cord_depth_from_outer,
        rel_tol=0.0,
        abs_tol=1e-14,
    )
    assert isclose(
        low.primary.center_of_mass,
        low.primary.outer - belt.center_of_mass_depth_from_outer,
        rel_tol=0.0,
        abs_tol=1e-14,
    )
    assert not isclose(low.primary.effective, low.primary.center_of_mass)

    assert isclose(low.secondary.effective / low.primary.effective, 2.9422859298377966)
    assert isclose(
        high.secondary.effective / high.primary.effective, 0.8559696296255629
    )

    resolved_belt = assembly.inertias.belt
    expected_l_cm = (
        geometry.spec.belt_outer_length
        - 2.0 * pi * belt.center_of_mass_depth_from_outer
    )
    assert isclose(resolved_belt.center_of_mass_path_length, expected_l_cm)
    assert isclose(
        resolved_belt.mass,
        resolved_belt.density * resolved_belt.cross_sectional_area * expected_l_cm,
    )


def test_physical_normal_resultant_and_signed_lambda_rows_match_formulation() -> None:
    assembly = _assembly()
    plant = MechanicalCVTPlant.from_assembly(assembly)
    s = assembly.geometry.spec.deadzone_shift + 0.25 * (
        assembly.geometry.spec.max_shift - assembly.geometry.spec.deadzone_shift
    )
    state = CVTState(
        primary_angular_speed=250.0,
        secondary_angular_speed=90.0,
        belt_speed=7.0,
        shift_position=s,
        shift_speed=0.0,
    )
    snapshot = plant.snapshot(state=state)
    context = TrialEquationContext(
        snapshot=snapshot,
        traction_utilization=ContactTractionUtilization(
            primary_lambda=0.20,
            secondary_lambda=-0.15,
        ),
    )

    p_axial = build_primary_axial_equation(snapshot=snapshot).residual.gains
    s_axial = build_secondary_axial_equation(snapshot=snapshot).residual.gains
    assert isclose(
        p_axial.primary_normal_resultant, -0.5 * cos(snapshot.sheave_half_angle)
    )
    assert isclose(
        s_axial.secondary_normal_resultant, -0.5 * cos(snapshot.sheave_half_angle)
    )

    p_traction = build_primary_traction_equation(context=context).residual.gains
    s_traction = build_secondary_traction_equation(context=context).residual.gains
    assert isclose(p_traction.primary_normal_resultant, 0.20)
    assert isclose(s_traction.secondary_normal_resultant, -0.15)
    assert isclose(p_traction.primary_torque, 1.0 / snapshot.geometry.primary.effective)
    assert isclose(
        s_traction.secondary_torque, 1.0 / snapshot.geometry.secondary.effective
    )

    sin_beta = np.sin(snapshot.sheave_half_angle)
    assert isclose(
        context.contact_terms.primary_exp_neg,
        np.exp(-0.20 * snapshot.geometry.primary_wrap_angle / sin_beta),
    )
    assert isclose(
        context.contact_terms.secondary_exp_neg,
        np.exp(-(-0.15) * snapshot.geometry.secondary_wrap_angle / sin_beta),
    )


def test_kinetic_lambda_sign_is_global_not_pulley_specific() -> None:
    for interface in (ContactInterface.PRIMARY, ContactInterface.SECONDARY):
        assert (
            KineticSlipSpecification(
                interface=interface,
                direction=SlipDirection.PULLEY_LEADS_BELT,
                kinetic_lambda_magnitude=0.55,
            ).signed_lambda
            == 0.55
        )
        assert (
            KineticSlipSpecification(
                interface=interface,
                direction=SlipDirection.BELT_LEADS_PULLEY,
                kinetic_lambda_magnitude=0.55,
            ).signed_lambda
            == -0.55
        )


def test_point_mass_flyweight_contributes_axial_force_and_shaft_inertia() -> None:
    mass = 0.4
    r0 = 0.05
    profile = PiecewiseRamp((LinearSegment(length=0.03, angle_degrees=30.0),))
    law = CentrifugalRampForce(
        CentrifugalRampForceSpec(
            flyweight_mass=mass,
            radius_at_zero_position=r0,
            radial_displacement_profile=profile,
        )
    )
    x = 0.01
    omega = 200.0
    xdot = 0.02
    context = PulleyActuationContext(
        time=0.0,
        axial_position=x,
        axial_speed=xdot,
        shaft_speed=omega,
        closure_channels=PulleyClosureChannels.primary(),
    )
    element = law.evaluate_element(context)
    ramp = profile.evaluate(x)
    radius = r0 + ramp.value
    dJdx = 2.0 * mass * radius * ramp.first_derivative

    assert isclose(element.closing_force.bias, 0.5 * omega**2 * dJdx)
    assert isclose(
        element.shaft_torque.gains.primary_angular_acceleration,
        -(mass * radius**2),
    )
    assert isclose(element.shaft_torque.bias, -dJdx * xdot * omega)


def test_helix_same_element_can_be_mounted_on_either_pulley() -> None:
    profile = HelixProfile(
        circumferential_profile=PiecewiseRamp(
            (linear_helix_segment(length=0.03, helix_angle_degrees=30.0),)
        ),
        radius=0.05,
    )
    law = HelicalTorqueReactionForce(
        spec=HelicalTorqueReactionSpec(
            torsional_stiffness=3.0,
            initial_twist=1.0,
            movable_member_torque_fraction=0.5,
        )
    )

    def resolved_force(*, primary: bool) -> float:
        x = 0.01 if primary else -0.01
        gain = 1.0 if primary else -1.0
        coupling = HelicalPulleyCoupling(
            profile=profile,
            opening_per_axial_position=gain,
        )
        kin = coupling.evaluate_from_local_coordinate(
            axial_position=x,
            d_axial_position_ds=1.0,
            d2_axial_position_ds2=0.0,
        )
        context = PulleyActuationContext(
            time=0.0,
            axial_position=x,
            axial_speed=0.0,
            shaft_speed=100.0,
            shift_speed=0.0,
            closure_channels=(
                PulleyClosureChannels.primary()
                if primary
                else PulleyClosureChannels.secondary()
            ),
            helical_coupling=HelicalCouplingState(
                kinematics=kin,
                opening_per_axial_position=gain,
            ),
            movable_member_rotational_inertia=0.003,
        )
        unknowns = ClosureUnknowns(
            primary_angular_acceleration=0.0,
            secondary_angular_acceleration=0.0,
            belt_acceleration=0.0,
            shift_acceleration=0.0,
            primary_torque=(-20.0 if primary else 0.0),
            secondary_torque=(0.0 if primary else 20.0),
            primary_normal_resultant=0.0,
            secondary_normal_resultant=0.0,
        )
        return law.evaluate_element(context).closing_force.evaluate(unknowns)

    # Forward-transfer belt torque has opposite signs on the two shafts, while
    # opposite helix handedness/mapping gives a positive torque-reactive clamp
    # contribution on either mounting.
    assert resolved_force(primary=True) > 0.0
    assert resolved_force(primary=False) > 0.0


def test_engagement_boundary_uses_explicit_one_sided_tangents() -> None:
    assembly = _assembly()
    geometry = assembly.geometry
    s_e = geometry.spec.deadzone_shift

    deadzone = geometry.evaluate_deadzone(s_e)
    engaged = geometry.evaluate_engaged(s_e)
    assert deadzone.primary.d_effective_ds == 0.0
    assert deadzone.secondary.d_effective_ds == 0.0
    assert deadzone.belt_axial_coordinate.d_value_ds == 0.0
    assert engaged.primary.d_effective_ds > 0.0
    assert engaged.secondary.d_effective_ds < 0.0
    assert engaged.belt_axial_coordinate.d_value_ds == 0.5

    # Event localization may land a few ULPs across the common position; that
    # must snap to the requested topology rather than selecting the other side.
    above = np.nextafter(s_e, np.inf)
    below = np.nextafter(s_e, -np.inf)
    assert geometry.evaluate_deadzone(above).primary.d_effective_ds == 0.0
    assert geometry.evaluate_engaged(below).primary.d_effective_ds > 0.0


def test_mass_metric_engagement_capture_redistributes_shift_momentum_without_energy_creation() -> (
    None
):
    from cinder.execution.hybrid.cvt_impact import (
        CVTVelocityTopology,
        project_cvt_velocity_topology,
    )

    plant = MechanicalCVTPlant.from_assembly(_assembly())
    s_e = plant.geometry.spec.deadzone_shift
    incoming = CVTState(
        primary_angular_speed=210.0,
        secondary_angular_speed=0.0,
        belt_speed=0.0,
        shift_position=s_e,
        shift_speed=0.30,
    )
    capture = project_cvt_velocity_topology(
        model=plant,
        vector=incoming.as_vector(),
        shift_position=s_e,
        from_topology=CVTVelocityTopology.DEADZONE,
        to_topology=CVTVelocityTopology.ENGAGED,
        lock_secondary_belt=True,
    )
    outgoing = CVTState.from_vector(capture.successor_state)
    r_s = plant.geometry.evaluate_engaged(s_e).secondary.effective

    assert 0.0 < outgoing.shift_speed < incoming.shift_speed
    assert outgoing.secondary_angular_speed != incoming.secondary_angular_speed
    assert isclose(
        outgoing.belt_speed,
        r_s * outgoing.secondary_angular_speed,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert capture.dissipated_energy >= 0.0
    assert capture.post_kinetic_energy <= capture.pre_kinetic_energy + 1e-11
    assert capture.constraint_residual < 1e-12
    assert capture.momentum_residual < 1e-11


def test_upper_stop_projection_transfers_helix_relative_momentum_into_secondary_shaft() -> (
    None
):
    from cinder.execution.hybrid.cvt_impact import (
        CVTVelocityTopology,
        project_cvt_velocity_topology,
    )

    plant = MechanicalCVTPlant.from_assembly(_assembly())
    s_hi = plant.geometry.spec.max_shift
    geometry = plant.geometry.evaluate_engaged(s_hi)
    incoming = CVTState(
        primary_angular_speed=430.0,
        secondary_angular_speed=390.0,
        belt_speed=geometry.secondary.effective * 390.0,
        shift_position=s_hi,
        shift_speed=0.002,
    )
    impact = project_cvt_velocity_topology(
        model=plant,
        vector=incoming.as_vector(),
        shift_position=s_hi,
        from_topology=CVTVelocityTopology.ENGAGED,
        to_topology=CVTVelocityTopology.ENGAGED,
        stop_shift_velocity=True,
    )
    outgoing = CVTState.from_vector(impact.successor_state)

    assert abs(outgoing.shift_speed) < 1e-15
    # A nonzero secondary helix dtheta/ds means killing s_dot must redistribute
    # some angular momentum into the common secondary shaft speed.
    assert not isclose(
        outgoing.secondary_angular_speed,
        incoming.secondary_angular_speed,
        rel_tol=0.0,
        abs_tol=1e-10,
    )
    assert impact.dissipated_energy >= 0.0
    assert impact.post_kinetic_energy <= impact.pre_kinetic_energy + 1e-11
    assert impact.constraint_residual < 1e-12
    assert impact.momentum_residual < 1e-11


def test_low_ratio_seat_constrains_secondary_axial_row_not_primary_axial_balance() -> (
    None
):
    from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint
    from cinder.model.cvt.dynamics.state_fixed_equations import (
        build_state_fixed_equations,
    )

    plant = MechanicalCVTPlant.from_assembly(_assembly())
    s_e = plant.geometry.spec.deadzone_shift
    state = CVTState(
        primary_angular_speed=210.0,
        secondary_angular_speed=5.0,
        belt_speed=plant.geometry.evaluate_engaged(s_e).secondary.effective * 5.0,
        shift_position=s_e,
        shift_speed=0.0,
    )
    snapshot = plant.snapshot(state=state, geometry_side="engaged")
    rows = build_state_fixed_equations(
        snapshot=snapshot,
        shift_constraint=EngagedShiftConstraint.LOW_RATIO_SEAT,
    )

    assert rows.shift_coordinate.name == "primary_axial"
    assert rows.secondary_axial.name == "low_ratio_seat_constraint"


def test_geometry_event_surfaces_snap_only_roundoff_sized_boundary_differences() -> (
    None
):
    from cinder.execution.hybrid.cvt_operating_limits import CVTShiftOperatingLimits
    from cinder.execution.hybrid.cvt_regime_events import (
        CVTRegimeEvent,
        build_engaged_free_boundary_events,
    )

    s_e = _assembly().geometry.spec.deadzone_shift
    limits = CVTShiftOperatingLimits(
        lower_stop_shift=0.0,
        engagement_shift=s_e,
        upper_stop_shift=_assembly().geometry.spec.max_shift,
    )
    events = {
        event.name: event for event in build_engaged_free_boundary_events(limits=limits)
    }
    low = events[CVTRegimeEvent.LOW_RATIO_SEAT_REACHED.value]

    vector = np.array([0.0, 0.0, 0.0, s_e, 0.0], dtype=float)
    vector[3] = np.nextafter(s_e, -np.inf)
    assert low.function(0.0, vector) == 0.0
    vector[3] = np.nextafter(s_e, np.inf)
    assert low.function(0.0, vector) == 0.0

    # The snap is strictly floating-point bookkeeping, not a shifted physical
    # event surface: a materially different position retains its real sign.
    vector[3] = s_e + 1.0e-12
    assert low.function(0.0, vector) > 0.0
    vector[3] = s_e - 1.0e-12
    assert low.function(0.0, vector) < 0.0
