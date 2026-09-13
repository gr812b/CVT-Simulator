"""Shared operating-case search helpers for closure-conditioning.

The numerical recipes live in release ``defaults/verification_operating_cases.json``.
This module only turns a requested recipe into an actual CINDER production state;
it adds no alternative CVT mechanics.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
from cinder.execution.hybrid.cvt_regime import CVTEngagementState, CVTShiftConstraint
from cinder.hosts import NoHost
from cinder.model.boundaries.shaft import FixedShaftBoundary
from cinder.model.cvt.contact import ContactInterface, EngagedContactMode, evaluate_contact_relative_speed
from cinder.model.system import CVTState
from cinder.results.fields import recover_belt_tension_boundaries
from cinder.results.inspection import inspect_cvt_state


@dataclass(frozen=True)
class SearchedStickCase:
    case_id: str
    system: Any
    full_state: np.ndarray
    mode: Any
    cvt_state: CVTState
    metadata: dict[str, Any]


def load_case_library(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_bench_system(decoded, library: dict, *, primary_torque: float, secondary_torque: float):
    bench = library["fixed_boundary_bench"]
    return ComposedCVTHybridSystem.from_plant(
        plant=decoded.plant,
        primary_boundary=FixedShaftBoundary(
            external_torque=float(primary_torque),
            equivalent_inertia=float(bench["primary_inertia_kg_m2"]),
        ),
        secondary_boundary=FixedShaftBoundary(
            external_torque=float(secondary_torque),
            equivalent_inertia=float(bench["secondary_inertia_kg_m2"]),
        ),
        host=NoHost(),
    )


def full_state(system, cvt_state: CVTState) -> np.ndarray:
    return np.asarray(
        system.initial_state(cvt_state=cvt_state, host_state=system.host.initial_state()),
        dtype=float,
    )


def zero_relative_speed_state(
    system,
    *,
    shift: float,
    shift_speed: float,
    belt_speed: float,
) -> CVTState:
    """Construct v_rel,p=v_rel,s=0 using production representative kinematics."""
    g = system.cvt.model.geometry.evaluate_engaged(float(shift))
    omega_p = float(belt_speed) / g.primary.effective
    omega_s = float(belt_speed) / g.secondary.effective
    for _ in range(2):
        cvt = CVTState(omega_p, omega_s, float(belt_speed), float(shift), float(shift_speed))
        state = full_state(system, cvt)
        boundaries = system._shaft_boundaries(time=0.0, state=state)
        snapshot = system.cvt.model.snapshot_at_time(
            time=0.0,
            state=cvt,
            shaft_boundaries=boundaries,
            geometry_side="engaged",
        )
        vp = evaluate_contact_relative_speed(snapshot=snapshot, interface=ContactInterface.PRIMARY)
        vs = evaluate_contact_relative_speed(snapshot=snapshot, interface=ContactInterface.SECONDARY)
        omega_p += vp / g.primary.effective
        omega_s += vs / g.secondary.effective
    return CVTState(omega_p, omega_s, float(belt_speed), float(shift), float(shift_speed))


def _local_normal_min(inspection, tensions, interface: ContactInterface) -> float:
    contact = inspection.contact
    unknowns = inspection.closure_unknowns
    assert contact is not None and unknowns is not None
    snap = contact.snapshot
    radius = snap.geometry.primary if interface is ContactInterface.PRIMARY else snap.geometry.secondary
    tmin = (
        min(tensions.primary_in, tensions.primary_out)
        if interface is ContactInterface.PRIMARY
        else min(tensions.secondary_in, tensions.secondary_out)
    )
    rddot = (
        radius.d2_center_of_mass_ds2 * snap.state.shift_speed**2
        + radius.d_center_of_mass_ds * unknowns.shift_acceleration
    )
    c = snap.belt_linear_density * (
        snap.state.belt_speed**2 - radius.center_of_mass * rddot
    )
    return float((tmin - c) / math.sin(snap.sheave_half_angle))


def admissible_stick_snapshot(system, *, state: np.ndarray, mode: Any, library: dict):
    """Return (pass, diagnostics) for a production-classified stick-stick snapshot."""
    cvt_mode = mode.cvt
    if (
        cvt_mode.engagement is not CVTEngagementState.ENGAGED
        or cvt_mode.shift_constraint is not CVTShiftConstraint.FREE
        or cvt_mode.contact_regime is None
        or cvt_mode.contact_regime.mode is not EngagedContactMode.STICK_STICK
    ):
        return False, {"reason": "not_engaged_free_stick_stick"}
    boundaries = system._shaft_boundaries(time=0.0, state=state)
    inspection = inspect_cvt_state(
        system=system.cvt,
        time=0.0,
        vector=system.layout.view(state, "cvt"),
        mode=cvt_mode,
        shaft_boundaries=boundaries,
        include_closure_audit=True,
    )
    contact = inspection.contact
    if contact is None or inspection.closure_audit is None:
        return False, {"reason": "missing_contact_or_closure"}
    law = system.cvt.traction_law
    p_margin = law.static_margin_at(ContactInterface.PRIMARY, contact.traction_utilization.primary_lambda)
    s_margin = law.static_margin_at(ContactInterface.SECONDARY, contact.traction_utilization.secondary_lambda)
    tensions = recover_belt_tension_boundaries(inspection)
    if tensions is None:
        return False, {"reason": "missing_tension_field"}
    min_tension = min(tensions.primary_in, tensions.primary_out, tensions.secondary_in, tensions.secondary_out)
    p_local = _local_normal_min(inspection, tensions, ContactInterface.PRIMARY)
    s_local = _local_normal_min(inspection, tensions, ContactInterface.SECONDARY)
    mechanism_margin = min((float(v) for _k, v in contact.mechanism_contact_margins), default=float("inf"))
    search = library["stick_state_search"]
    ok = (
        contact.normal_primary >= float(search["minimum_normal_N"])
        and contact.normal_secondary >= float(search["minimum_normal_N"])
        and p_margin >= float(search["minimum_static_margin"])
        and s_margin >= float(search["minimum_static_margin"])
        and min_tension >= float(search["minimum_tension_N"])
        and p_local >= float(search["minimum_local_normal_N_per_rad"])
        and s_local >= float(search["minimum_local_normal_N_per_rad"])
        and mechanism_margin >= 0.0
    )
    return ok, {
        "reason": "accepted" if ok else "physical_admissibility",
        "lambda_p": contact.traction_utilization.primary_lambda,
        "lambda_s": contact.traction_utilization.secondary_lambda,
        "N_p": contact.normal_primary,
        "N_s": contact.normal_secondary,
        "primary_static_margin": p_margin,
        "secondary_static_margin": s_margin,
        "minimum_belt_tension_N": min_tension,
        "primary_min_local_normal_N_per_rad": p_local,
        "secondary_min_local_normal_N_per_rad": s_local,
        "minimum_mechanism_margin": mechanism_margin,
        "scaled_condition_A": inspection.closure_audit.scaled_condition_number,
    }


def search_named_stick_case(decoded, library: dict, recipe: dict):
    """Search the shared fixed-boundary bench for one admissible named stick state."""
    gs = decoded.plant.geometry.spec
    shift = gs.deadzone_shift + float(recipe["shift_fraction"]) * (gs.max_shift - gs.deadzone_shift)
    shift_speed = float(recipe["shift_speed_m_s"])
    rotation_sign = int(recipe.get("rotation_sign", 1))
    bench = library["fixed_boundary_bench"]
    belt_speeds = [rotation_sign * abs(float(v)) for v in bench["belt_speeds_m_s"] + bench.get("extended_belt_speeds_m_s", [])]
    torque_pairs = [(float(tp), float(ts)) for tp in bench["primary_torques_Nm"] for ts in bench["secondary_torques_Nm"]]
    if recipe.get("prefer_high_boundary_load", False):
        torque_pairs.sort(key=lambda pair: abs(pair[0]) + abs(pair[1]), reverse=True)

    attempts = []
    accepted = []
    for vb in belt_speeds:
        for tp, ts in torque_pairs:
            system = make_bench_system(decoded, library, primary_torque=tp, secondary_torque=ts)
            try:
                cvt = zero_relative_speed_state(
                    system, shift=shift, shift_speed=shift_speed, belt_speed=vb
                )
                state = full_state(system, cvt)
                mode = system.classify_initial_mode(state)
                ok, diag = admissible_stick_snapshot(system, state=state, mode=mode, library=library)
            except Exception as exc:
                attempts.append({"belt_speed_m_s": vb, "primary_torque_Nm": tp, "secondary_torque_Nm": ts, "accepted": False, "reason": f"{type(exc).__name__}: {exc}"})
                continue
            attempts.append({"belt_speed_m_s": vb, "primary_torque_Nm": tp, "secondary_torque_Nm": ts, "accepted": bool(ok), **diag})
            if ok:
                accepted.append((system, state, mode, cvt, tp, ts, vb, diag))
                if not recipe.get("prefer_high_boundary_load", False):
                    break
        if accepted and not recipe.get("prefer_high_boundary_load", False):
            break
    if not accepted:
        return None, attempts
    system, state, mode, cvt, tp, ts, vb, diag = accepted[0]
    return SearchedStickCase(
        case_id=str(recipe["id"]),
        system=system,
        full_state=state,
        mode=mode,
        cvt_state=cvt,
        metadata={
            "case_id": recipe["id"],
            "purpose": recipe.get("purpose", ""),
            "shift_fraction": recipe["shift_fraction"],
            "shift_speed_m_s": shift_speed,
            "rotation_sign": rotation_sign,
            "belt_speed_m_s": vb,
            "primary_torque_Nm": tp,
            "secondary_torque_Nm": ts,
            **diag,
        },
    ), attempts
