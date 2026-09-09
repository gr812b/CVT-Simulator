from __future__ import annotations

import json
from math import isclose
from pathlib import Path

import numpy as np

from cinder.contracts import decode_assembly_document
from cinder.execution.hybrid.cvt_impact import (
    CVTVelocityTopology,
    _physical_velocity_map,
    belt_wrap_radial_shift_inertia,
    kinetic_energy_for_topology,
    project_cvt_velocity_topology,
)
from cinder.model.cvt.actuation import HelicalTorqueReactionForce
from cinder.model.system import MechanicalCVTPlant
from cinder.model.system.ports import CVTShaftBoundaryValues
from cinder.model.system.state import CVTState

ROOT = Path(__file__).resolve().parents[2]
ASSEMBLY = ROOT / "examples" / "baja_baseline_assembly.json"


def _plant() -> MechanicalCVTPlant:
    assembly = decode_assembly_document(
        json.loads(ASSEMBLY.read_text(encoding="utf-8"))
    )
    return MechanicalCVTPlant.from_assembly(assembly)


def _helix_shift_ratio(model, side: str, coordinate) -> float:
    coupling = (
        model.primary_helical_coupling
        if side == "primary"
        else model.secondary_helical_coupling
    )
    if coupling is None:
        return 0.0
    return float(
        coupling.evaluate_from_local_coordinate(
            axial_position=coordinate.value,
            d_axial_position_ds=coordinate.d_value_ds,
            d2_axial_position_ds2=coordinate.d2_value_ds2,
        ).dtheta_ds
    )


def _torque_fraction(model, side: str) -> float:
    actuator = model.primary_actuator if side == "primary" else model.secondary_actuator
    laws = tuple(
        law
        for law in actuator.force_laws
        if isinstance(law, HelicalTorqueReactionForce)
    )
    if not laws:
        return 0.0
    assert len(laws) == 1
    return float(laws[0].spec.movable_member_torque_fraction)


def _independent_shift_only_energy(model, state: CVTState) -> float:
    geometry = model.geometry.evaluate_engaged(state.shift_position)
    sdot = state.shift_speed
    pcoord = geometry.primary_axial_coordinate
    scoord = geometry.secondary_axial_coordinate

    energy = 0.0
    energy += (
        0.5
        * model.inertias.primary.movable_sheave_rotational_inertia
        * (_helix_shift_ratio(model, "primary", pcoord) * sdot) ** 2
    )
    energy += (
        0.5
        * model.inertias.secondary.movable_sheave_rotational_inertia
        * (_helix_shift_ratio(model, "secondary", scoord) * sdot) ** 2
    )

    energy += (
        0.5
        * model.inertias.axial_translation.primary_moving_sheave_mass
        * (pcoord.d_value_ds * sdot) ** 2
    )
    energy += (
        0.5
        * model.inertias.axial_translation.secondary_moving_sheave_mass
        * (scoord.d_value_ds * sdot) ** 2
    )

    energy += (
        0.5
        * belt_wrap_radial_shift_inertia(
            model=model,
            shift_position=state.shift_position,
            topology=CVTVelocityTopology.ENGAGED,
        )
        * sdot**2
    )

    pctx = model.primary_actuation_context(time=0.0, state=state, geometry=geometry)
    sctx = model.secondary_actuation_context(time=0.0, state=state, geometry=geometry)
    for mode in model.primary_actuator.kinetic_modes(pctx):
        speed = mode.axial_speed_coefficient * pcoord.d_value_ds * sdot
        energy += 0.5 * mode.inertia * speed**2
    for mode in model.secondary_actuator.kinetic_modes(sctx):
        speed = mode.axial_speed_coefficient * scoord.d_value_ds * sdot
        energy += 0.5 * mode.inertia * speed**2

    return float(energy)


def test_engaged_shift_only_kinetic_energy_contains_wrap_radial_motion() -> None:
    model = _plant()
    s_e = model.geometry.spec.deadzone_shift
    s_hi = model.geometry.spec.max_shift

    for fraction in (0.0, 0.25, 0.50, 0.75, 1.0):
        s = s_e + fraction * (s_hi - s_e)
        state = CVTState(
            primary_angular_speed=0.0,
            secondary_angular_speed=0.0,
            belt_speed=0.0,
            shift_position=s,
            shift_speed=0.017,
        )
        actual = kinetic_energy_for_topology(
            model=model,
            state=state,
            topology=CVTVelocityTopology.ENGAGED,
        )
        expected = _independent_shift_only_energy(model, state)
        assert isclose(actual, expected, rel_tol=1.0e-12, abs_tol=1.0e-13)

        radial_mass = belt_wrap_radial_shift_inertia(
            model=model,
            shift_position=s,
        )
        assert radial_mass > 0.0


def test_deadzone_and_engaged_impact_bases_match_at_first_contact() -> None:
    model = _plant()
    s_e = model.geometry.spec.deadzone_shift
    state = CVTState(
        primary_angular_speed=210.0,
        secondary_angular_speed=20.0,
        belt_speed=model.geometry.evaluate_deadzone(s_e).secondary.effective * 20.0,
        shift_position=s_e,
        shift_speed=0.25,
    )
    zero = CVTShaftBoundaryValues.zero()
    rows_minus, weights_minus = _physical_velocity_map(
        model=model,
        state=state,
        topology=CVTVelocityTopology.DEADZONE,
        shaft_boundaries=zero,
    )
    rows_plus, weights_plus = _physical_velocity_map(
        model=model,
        state=state,
        topology=CVTVelocityTopology.ENGAGED,
        shaft_boundaries=zero,
    )
    assert rows_minus.shape == rows_plus.shape
    assert np.allclose(weights_minus, weights_plus, rtol=1.0e-13, atol=1.0e-15)

    # The new belt radial rows are dormant in deadzone and active in engagement,
    # so the topology tangent genuinely changes even though the component basis
    # and physical position are continuous.
    assert not np.allclose(rows_minus, rows_plus)


def test_engagement_capture_with_wrap_radial_inertia_is_dissipative_and_constrained() -> (
    None
):
    model = _plant()
    s_e = model.geometry.spec.deadzone_shift
    geometry = model.geometry.evaluate_deadzone(s_e)
    incoming = CVTState(
        primary_angular_speed=210.0,
        secondary_angular_speed=25.0,
        belt_speed=geometry.secondary.effective * 25.0,
        shift_position=s_e,
        shift_speed=0.30,
    )
    capture = project_cvt_velocity_topology(
        model=model,
        vector=incoming.as_vector(),
        shift_position=s_e,
        from_topology=CVTVelocityTopology.DEADZONE,
        to_topology=CVTVelocityTopology.ENGAGED,
        lock_secondary_belt=True,
    )
    outgoing = CVTState.from_vector(capture.successor_state)
    engaged = model.geometry.evaluate_engaged(s_e)
    r_s = engaged.secondary.effective
    h_s = _helix_shift_ratio(model, "secondary", engaged.secondary_axial_coordinate)
    f_s = _torque_fraction(model, "secondary")
    representative_omega_s = (
        outgoing.secondary_angular_speed + f_s * h_s * outgoing.shift_speed
    )

    assert capture.dissipated_energy >= 0.0
    assert capture.post_kinetic_energy <= capture.pre_kinetic_energy + 1.0e-10
    assert capture.constraint_residual < 1.0e-11
    assert capture.momentum_residual < 1.0e-10
    assert isclose(
        outgoing.belt_speed,
        r_s * representative_omega_s,
        rel_tol=0.0,
        abs_tol=1.0e-11,
    )


def test_upper_stop_with_wrap_radial_inertia_is_dissipative() -> None:
    model = _plant()
    s_hi = model.geometry.spec.max_shift
    geometry = model.geometry.evaluate_engaged(s_hi)
    incoming = CVTState(
        primary_angular_speed=430.0,
        secondary_angular_speed=390.0,
        belt_speed=geometry.secondary.effective * 390.0,
        shift_position=s_hi,
        shift_speed=0.004,
    )
    impact = project_cvt_velocity_topology(
        model=model,
        vector=incoming.as_vector(),
        shift_position=s_hi,
        from_topology=CVTVelocityTopology.ENGAGED,
        to_topology=CVTVelocityTopology.ENGAGED,
        stop_shift_velocity=True,
    )
    outgoing = CVTState.from_vector(impact.successor_state)
    assert abs(outgoing.shift_speed) < 1.0e-14
    assert impact.dissipated_energy >= 0.0
    assert impact.post_kinetic_energy <= impact.pre_kinetic_energy + 1.0e-10
    assert impact.constraint_residual < 1.0e-11
    assert impact.momentum_residual < 1.0e-10
