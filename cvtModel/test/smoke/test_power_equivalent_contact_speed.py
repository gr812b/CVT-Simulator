from __future__ import annotations

import json
from math import isclose
from pathlib import Path

from cinder.contracts import decode_assembly_document
from cinder.model.cvt.closure import ClosureUnknowns
from cinder.model.cvt.contact import (
    ContactInterface,
    evaluate_contact_relative_motion,
    evaluate_contact_relative_speed,
)
from cinder.model.system import MechanicalCVTPlant
from cinder.model.system.state import CVTState

ROOT = Path(__file__).resolve().parents[2]
ASSEMBLY = ROOT / "examples" / "baja_baseline_assembly.json"


def _plant() -> MechanicalCVTPlant:
    assembly = decode_assembly_document(
        json.loads(ASSEMBLY.read_text(encoding="utf-8"))
    )
    return MechanicalCVTPlant.from_assembly(assembly)


def test_secondary_relative_motion_uses_power_equivalent_face_speed() -> None:
    plant = _plant()
    s_e = plant.geometry.spec.deadzone_shift
    s_hi = plant.geometry.spec.max_shift
    s = s_e + 0.45 * (s_hi - s_e)
    state = CVTState(
        primary_angular_speed=315.0,
        secondary_angular_speed=168.0,
        belt_speed=11.3,
        shift_position=s,
        shift_speed=0.018,
    )
    snapshot = plant.snapshot(state=state, geometry_side="engaged")
    assert snapshot.secondary_helix is not None

    unknowns = ClosureUnknowns(
        primary_angular_acceleration=14.0,
        secondary_angular_acceleration=-8.0,
        belt_acceleration=0.65,
        shift_acceleration=0.031,
        primary_torque=-12.0,
        secondary_torque=12.0,
        primary_normal_resultant=800.0,
        secondary_normal_resultant=900.0,
    )
    relative = evaluate_contact_relative_motion(
        snapshot=snapshot,
        unknowns=unknowns,
    )
    speed_only = evaluate_contact_relative_speed(
        snapshot=snapshot,
        interface=ContactInterface.SECONDARY,
    )

    geometry = snapshot.geometry
    helix = snapshot.secondary_helix
    xprime = geometry.secondary_axial_coordinate.d_value_ds
    torque_gain = snapshot.secondary_actuation.gains.secondary_torque

    # The actuation gain is f*dtheta/dx; multiplying by dx/ds gives f*dtheta/ds.
    weighted_h = torque_gain * xprime
    f = weighted_h / helix.dtheta_ds
    assert isclose(f, 0.5, rel_tol=0.0, abs_tol=1.0e-12)

    omega_bar = state.secondary_angular_speed + weighted_h * state.shift_speed
    alpha_bar = (
        unknowns.secondary_angular_acceleration
        + weighted_h * unknowns.shift_acceleration
        + f * helix.d2theta_ds2 * state.shift_speed**2
    )
    expected_vrel = state.belt_speed - geometry.secondary.effective * omega_bar
    expected_arel = (
        unknowns.belt_acceleration
        - geometry.secondary.effective * alpha_bar
        - geometry.secondary.d_effective_ds * state.shift_speed * omega_bar
    )

    assert isclose(
        relative.secondary_relative_speed,
        expected_vrel,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )
    assert isclose(
        speed_only,
        expected_vrel,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )
    assert isclose(
        relative.secondary_relative_acceleration,
        expected_arel,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )


def test_primary_without_helix_remains_shaft_referenced() -> None:
    plant = _plant()
    s = plant.geometry.spec.deadzone_shift + 0.3 * (
        plant.geometry.spec.max_shift - plant.geometry.spec.deadzone_shift
    )
    state = CVTState(
        primary_angular_speed=280.0,
        secondary_angular_speed=120.0,
        belt_speed=8.0,
        shift_position=s,
        shift_speed=0.01,
    )
    snapshot = plant.snapshot(state=state, geometry_side="engaged")
    assert snapshot.primary_helix is None
    unknowns = ClosureUnknowns(
        primary_angular_acceleration=7.0,
        secondary_angular_acceleration=3.0,
        belt_acceleration=0.4,
        shift_acceleration=-0.02,
    )
    relative = evaluate_contact_relative_motion(snapshot=snapshot, unknowns=unknowns)
    primary = snapshot.geometry.primary
    assert isclose(
        relative.primary_relative_speed,
        state.belt_speed - primary.effective * state.primary_angular_speed,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )
    assert isclose(
        relative.primary_relative_acceleration,
        unknowns.belt_acceleration
        - primary.effective * unknowns.primary_angular_acceleration
        - primary.d_effective_ds * state.shift_speed * state.primary_angular_speed,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )


def test_public_slip_direction_helper_is_preserved() -> None:
    from cinder.model.cvt.contact import (
        ContactKinematicTolerances,
        SlipDirection,
        infer_slip_direction,
    )

    tolerances = ContactKinematicTolerances()
    assert (
        infer_slip_direction(
            relative_speed=10.0 * tolerances.relative_speed_tolerance,
            relative_acceleration=0.0,
            tolerances=tolerances,
        )
        is SlipDirection.BELT_LEADS_PULLEY
    )
    assert (
        infer_slip_direction(
            relative_speed=-10.0 * tolerances.relative_speed_tolerance,
            relative_acceleration=0.0,
            tolerances=tolerances,
        )
        is SlipDirection.PULLEY_LEADS_BELT
    )
