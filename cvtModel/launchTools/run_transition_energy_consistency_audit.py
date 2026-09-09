"""Audit CINDER transition kinetics, retained kinetic modes, and energy closure.

This runner is intentionally adversarial.  It does not merely verify that the
new radial-wrap code path exists.  It checks four layers:

1. structural/source consistency:
   - smooth wrap equations retain changing-radius terms;
   - sticking compatibility retains the r_dot * omega term;
   - transition kinetic metric contains belt radial wrap modes;
   - stale result-tool references are reported;

2. independent kinetic-mode reconstruction:
   - rebuild the generalized kinetic mass matrix from the current explicit
     inertia objects + actuator kinetic modes + belt transport + belt radial
     wrap motion;
   - compare it with the production impact map across the engaged shift range;

3. finite-speed transition checks:
   - first engagement;
   - backshift into deadzone;
   - upper stop;
   - lower stop;
   with momentum residual, constraint residual, and non-increasing kinetic
   energy checks;

4. integrated energy/numerical audit:
   - run the current fixed-pivot Baja reference through the hybrid integrator;
   - compute the work / stored-energy / slip / impact balance on two independent
     quadrature grids using the SAME dense solver trajectory;
   - report residuals specifically during active shift;
   - localize continuous energy defects segment-by-segment and separate them from exact event jumps;
   - verify the power-equivalent helical contact-speed implementation is present;
   - measure signed power from any numerical velocity-level drift at interfaces declared sticking;
   - repeat the residual accounting on the already-computed tighter solver trajectory;
   - rerun the trajectory with tighter solver controls and compare final states.

The audit can expose inconsistencies inside the retained CINDER model.  It
cannot prove that omitted physics (belt elasticity, straight-span transverse
motion, seating/creep, radial face friction, etc.) is negligible.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TOOLS = ROOT / "tools"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import run_route_grade_response as route  # noqa: E402
import audit_energy_balance as energy  # noqa: E402

from cinder.contracts import decode_assembly_document  # noqa: E402
from cinder.execution.hybrid import (  # noqa: E402
    HybridIntegratorSettings,
    integrate_hybrid,
)
from cinder.execution.hybrid.cvt_impact import (  # noqa: E402
    CVTVelocityTopology,
    _physical_velocity_map,
    _representative_contact_shift_gain,
    belt_wrap_radial_shift_inertia,
    project_cvt_velocity_topology,
)
from cinder.execution.hybrid.cvt_regime import CVTEngagementState  # noqa: E402
from cinder.model.system import MechanicalCVTPlant  # noqa: E402
from cinder.model.system.ports import CVTShaftBoundaryValues  # noqa: E402
from cinder.model.system.state import CVTState  # noqa: E402
from cinder.model.cvt.contact import ContactInterface  # noqa: E402


@dataclass
class Finding:
    level: str
    key: str
    message: str
    data: dict[str, Any] | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/transition_energy_consistency_audit"),
    )
    parser.add_argument("--duration-s", type=float, default=10.0)
    parser.add_argument("--rtol", type=float, default=1.0e-4)
    parser.add_argument("--atol", type=float, default=1.0e-7)
    parser.add_argument("--max-step-s", type=float, default=0.02)
    parser.add_argument("--audit-step-s", type=float, default=0.02)
    parser.add_argument(
        "--skip-refinement",
        action="store_true",
        help="Skip the second, tighter ODE integration.",
    )
    parser.add_argument(
        "--full-smoke",
        action="store_true",
        help="Run the complete test/smoke suite if pytest is installed.",
    )
    parser.add_argument(
        "--no-pytest",
        action="store_true",
        help="Skip pytest; direct audit checks still run.",
    )
    return parser.parse_args()


def record(findings: list[Finding], level: str, key: str, message: str, **data) -> None:
    item = Finding(level=level, key=key, message=message, data=data or None)
    findings.append(item)
    tag = f"[{level}]"
    print(f"{tag:7s} {key}: {message}")
    if data:
        for name, value in data.items():
            print(f"          {name} = {value}")


def load_plant() -> MechanicalCVTPlant:
    path = ROOT / "examples" / "baja_baseline_assembly.json"
    assembly = decode_assembly_document(json.loads(path.read_text(encoding="utf-8")))
    return MechanicalCVTPlant.from_assembly(assembly)


def structural_source_audit(findings: list[Finding]) -> None:
    checks = [
        (
            ROOT / "src/cinder/model/cvt/dynamics/rows/tension_loop.py",
            ("d_radius_ds", "shift_speed * belt_speed"),
            "smooth_wrap_changing_radius",
        ),
        (
            ROOT / "src/cinder/model/cvt/contact/relative_motion.py",
            ("d_effective_ds", "state.shift_speed"),
            "stick_compatibility_rdot",
        ),
        (
            ROOT / "src/cinder/model/cvt/contact/relative_motion.py",
            ("power-equivalent", "weighted_dtheta_ds", "d2theta_ds2_weighted"),
            "power_equivalent_contact_speed",
        ),
        (
            ROOT / "src/cinder/model/cvt/dynamics/engaged_contact.py",
            ("snapshot=self.snapshot", "unknowns=closure.unknowns"),
            "engaged_contact_uses_power_equivalent_kinematics",
        ),
        (
            ROOT / "src/cinder/execution/hybrid/cvt_contact_switching.py",
            ("evaluate_contact_relative_speed", "ContactInterface.SECONDARY"),
            "hybrid_switching_uses_power_equivalent_speed",
        ),
        (
            ROOT / "src/cinder/execution/hybrid/cvt_impact.py",
            ("linear_density", "d_center_of_mass_ds", "primary_wrap_mass", "secondary_wrap_mass"),
            "impact_wrap_radial_modes",
        ),
        (
            ROOT / "src/cinder/execution/hybrid/cvt_impact.py",
            ("_representative_contact_shift_gain", "movable_member_torque_fraction"),
            "impact_power_equivalent_belt_lock",
        ),
    ]
    for path, tokens, key in checks:
        text = path.read_text(encoding="utf-8")
        missing = [token for token in tokens if token not in text]
        if missing:
            record(
                findings,
                "FAIL",
                key,
                f"Expected retained-mechanics markers are missing from {path.relative_to(ROOT)}.",
                missing=missing,
            )
        else:
            record(findings, "PASS", key, f"{path.relative_to(ROOT)} contains the expected terms.")

    legacy_energy = ROOT / "tools/audit_energy_balance.py"
    if legacy_energy.exists():
        text = legacy_energy.read_text(encoding="utf-8")
        if "circular_traction_first_reference.json" in text:
            record(
                findings,
                "WARN",
                "stale_energy_audit_preset",
                "The old standalone energy audit still references the retired circular_traction_first_reference.json. "
                "This runner bypasses that stale entry point and uses route.DEFAULT_FIXED_PIVOT_PRESET.",
            )
        else:
            record(findings, "PASS", "energy_audit_preset", "Standalone energy audit does not reference the retired preset.")


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


def independent_velocity_map(model, state: CVTState, topology: CVTVelocityTopology):
    geometry = (
        model.geometry.evaluate_engaged(state.shift_position)
        if topology is CVTVelocityTopology.ENGAGED
        else model.geometry.evaluate_deadzone(state.shift_position)
    )
    if topology is CVTVelocityTopology.DEADZONE and state.shift_position != model.geometry.spec.deadzone_shift:
        locked = model.geometry.evaluate_deadzone(model.geometry.spec.deadzone_shift)
        geometry = type(geometry)(
            shift=geometry.shift,
            primary=geometry.primary,
            secondary=locked.secondary,
            primary_wrap_angle=locked.primary_wrap_angle,
            secondary_wrap_angle=locked.secondary_wrap_angle,
            primary_axial_coordinate=geometry.primary_axial_coordinate,
            secondary_axial_coordinate=locked.secondary_axial_coordinate,
            belt_axial_coordinate=locked.belt_axial_coordinate,
        )

    pcoord = geometry.primary_axial_coordinate
    scoord = geometry.secondary_axial_coordinate
    rows: list[tuple[float, float, float, float]] = []
    weights: list[float] = []

    def add(weight: float, row):
        if weight > 0.0:
            rows.append(tuple(float(v) for v in row))
            weights.append(float(weight))

    add(model.inertias.primary.fixed_rotating_hardware_inertia, (1, 0, 0, 0))
    add(
        model.inertias.primary.movable_sheave_rotational_inertia,
        (1, 0, 0, _helix_shift_ratio(model, "primary", pcoord)),
    )
    add(model.inertias.secondary.fixed_side.total, (0, 1, 0, 0))
    add(
        model.inertias.secondary.movable_sheave_rotational_inertia,
        (0, 1, 0, _helix_shift_ratio(model, "secondary", scoord)),
    )
    add(model.inertias.belt.mass, (0, 0, 1, 0))

    if topology is CVTVelocityTopology.ENGAGED:
        radial_reference = geometry
        pdr = geometry.primary.d_center_of_mass_ds
        sdr = geometry.secondary.d_center_of_mass_ds
    else:
        radial_reference = model.geometry.evaluate_engaged(model.geometry.spec.deadzone_shift)
        pdr = 0.0
        sdr = 0.0
    q = model.inertias.belt.linear_density
    add(
        q * radial_reference.primary.center_of_mass * radial_reference.primary_wrap_angle,
        (0, 0, 0, pdr),
    )
    add(
        q * radial_reference.secondary.center_of_mass * radial_reference.secondary_wrap_angle,
        (0, 0, 0, sdr),
    )

    add(
        model.inertias.axial_translation.primary_moving_sheave_mass,
        (0, 0, 0, pcoord.d_value_ds),
    )
    add(
        model.inertias.axial_translation.secondary_moving_sheave_mass,
        (0, 0, 0, scoord.d_value_ds),
    )

    pctx = model.primary_actuation_context(time=0.0, state=state, geometry=geometry)
    sctx = model.secondary_actuation_context(time=0.0, state=state, geometry=geometry)
    for mode in model.primary_actuator.kinetic_modes(pctx):
        add(
            mode.inertia,
            (
                mode.shaft_speed_coefficient,
                0,
                0,
                mode.axial_speed_coefficient * pcoord.d_value_ds,
            ),
        )
    for mode in model.secondary_actuator.kinetic_modes(sctx):
        add(
            mode.inertia,
            (
                0,
                mode.shaft_speed_coefficient,
                0,
                mode.axial_speed_coefficient * scoord.d_value_ds,
            ),
        )
    return np.asarray(rows, dtype=float), np.asarray(weights, dtype=float)


def kinetic_inventory_audit(findings: list[Finding], model: MechanicalCVTPlant) -> None:
    s_e = model.geometry.spec.deadzone_shift
    s_hi = model.geometry.spec.max_shift
    zero = CVTShaftBoundaryValues.zero()
    max_mass_matrix_error = 0.0
    rows_report = []

    for fraction in (0.0, 0.25, 0.50, 0.75, 1.0):
        s = s_e + fraction * (s_hi - s_e)
        state = CVTState(
            primary_angular_speed=317.0,
            secondary_angular_speed=163.0,
            belt_speed=8.4,
            shift_position=s,
            shift_speed=0.018,
        )
        prod_rows, prod_weights = _physical_velocity_map(
            model=model,
            state=state,
            topology=CVTVelocityTopology.ENGAGED,
            shaft_boundaries=zero,
        )
        exp_rows, exp_weights = independent_velocity_map(
            model, state, CVTVelocityTopology.ENGAGED
        )
        prod_mass = prod_rows.T @ (prod_rows * prod_weights[:, None])
        exp_mass = exp_rows.T @ (exp_rows * exp_weights[:, None])
        err = float(np.max(np.abs(prod_mass - exp_mass)))
        max_mass_matrix_error = max(max_mass_matrix_error, err)

        geometry = model.geometry.evaluate_engaged(s)
        axial = model.inertias.axial_translation.evaluate(
            primary_axial_coordinate=geometry.primary_axial_coordinate,
            secondary_axial_coordinate=geometry.secondary_axial_coordinate,
        )
        radial = belt_wrap_radial_shift_inertia(model=model, shift_position=s)
        rows_report.append(
            {
                "shift_fraction": fraction,
                "shift_m": s,
                "belt_radial_shift_inertia_kg": radial,
                "literal_sheave_shift_inertia_kg": axial.generalized_mass,
                "radial_over_literal_sheave": radial / max(axial.generalized_mass, 1.0e-30),
            }
        )

    if max_mass_matrix_error > 1.0e-10:
        record(
            findings,
            "FAIL",
            "kinetic_mass_matrix_inventory",
            "Production transition metric does not match the independent inventory of explicit retained inertial modes.",
            max_abs_matrix_error=max_mass_matrix_error,
        )
    else:
        record(
            findings,
            "PASS",
            "kinetic_mass_matrix_inventory",
            "Production transition metric matches an independently reconstructed kinetic-mode inventory across the engaged range.",
            max_abs_matrix_error=max_mass_matrix_error,
        )

    for row in rows_report:
        print(
            "          shift={shift_fraction:>4.0%}: M_b,rad={belt_radial_shift_inertia_kg:.6f} kg, "
            "M_sheaves={literal_sheave_shift_inertia_kg:.6f} kg, ratio={radial_over_literal_sheave:.3f}".format(**row)
        )

    # Cross-topology component basis must match exactly at first contact.
    boundary_state = CVTState(
        primary_angular_speed=210.0,
        secondary_angular_speed=25.0,
        belt_speed=model.geometry.evaluate_deadzone(s_e).secondary.effective * 25.0,
        shift_position=s_e,
        shift_speed=0.2,
    )
    rm, wm = _physical_velocity_map(
        model=model,
        state=boundary_state,
        topology=CVTVelocityTopology.DEADZONE,
        shaft_boundaries=zero,
    )
    rp, wp = _physical_velocity_map(
        model=model,
        state=boundary_state,
        topology=CVTVelocityTopology.ENGAGED,
        shaft_boundaries=zero,
    )
    if rm.shape != rp.shape or not np.allclose(wm, wp, rtol=1e-13, atol=1e-15):
        record(
            findings,
            "FAIL",
            "engagement_component_basis",
            "Deadzone and engaged physical component bases do not match at first contact.",
            deadzone_shape=rm.shape,
            engaged_shape=rp.shape,
            weight_error=float(np.max(np.abs(wm - wp))) if wm.shape == wp.shape else None,
        )
    else:
        record(
            findings,
            "PASS",
            "engagement_component_basis",
            "Deadzone and engaged maps use the same component weights at first contact while retaining different one-sided tangents.",
        )


def _check_projection(findings, key, projection, extra_ok=True):
    tol_ke = 1.0e-9 * max(1.0, abs(projection.pre_kinetic_energy))
    ok = (
        projection.post_kinetic_energy <= projection.pre_kinetic_energy + tol_ke
        and projection.dissipated_energy >= -tol_ke
        and projection.constraint_residual < 1.0e-9
        and projection.momentum_residual < 1.0e-8
        and extra_ok
    )
    record(
        findings,
        "PASS" if ok else "FAIL",
        key,
        "Finite-speed projection is dissipative and satisfies its impulse/velocity constraints."
        if ok
        else "Finite-speed projection failed an energy, momentum, or constraint check.",
        pre_KE_J=projection.pre_kinetic_energy,
        post_KE_J=projection.post_kinetic_energy,
        loss_J=projection.dissipated_energy,
        constraint_residual=projection.constraint_residual,
        momentum_residual=projection.momentum_residual,
    )


def transition_audit(findings: list[Finding], model: MechanicalCVTPlant) -> None:
    s_e = model.geometry.spec.deadzone_shift
    s_hi = model.geometry.spec.max_shift

    dz = model.geometry.evaluate_deadzone(s_e)
    incoming = CVTState(210.0, 25.0, dz.secondary.effective * 25.0, s_e, 0.30)
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
    rs = engaged.secondary.effective
    g_s = _representative_contact_shift_gain(
        model=model,
        side="secondary",
        coordinate=engaged.secondary_axial_coordinate,
    )
    representative_omega_s = (
        outgoing.secondary_angular_speed + g_s * outgoing.shift_speed
    )
    _check_projection(
        findings,
        "first_engagement_projection",
        capture,
        extra_ok=abs(outgoing.belt_speed - rs * representative_omega_s) < 1e-9,
    )

    eng = model.geometry.evaluate_engaged(s_e)
    incoming = CVTState(220.0, 65.0, eng.secondary.effective * 65.0, s_e, -0.08)
    backshift = project_cvt_velocity_topology(
        model=model,
        vector=incoming.as_vector(),
        shift_position=s_e,
        from_topology=CVTVelocityTopology.ENGAGED,
        to_topology=CVTVelocityTopology.DEADZONE,
        lock_secondary_belt=True,
    )
    _check_projection(findings, "backshift_deadzone_projection", backshift)

    hi = model.geometry.evaluate_engaged(s_hi)
    incoming = CVTState(430.0, 390.0, hi.secondary.effective * 390.0, s_hi, 0.004)
    upper = project_cvt_velocity_topology(
        model=model,
        vector=incoming.as_vector(),
        shift_position=s_hi,
        from_topology=CVTVelocityTopology.ENGAGED,
        to_topology=CVTVelocityTopology.ENGAGED,
        stop_shift_velocity=True,
    )
    _check_projection(
        findings,
        "upper_stop_projection",
        upper,
        extra_ok=abs(CVTState.from_vector(upper.successor_state).shift_speed) < 1e-12,
    )

    s_lo = 0.0
    dz_lo = model.geometry.evaluate_deadzone(s_lo)
    incoming = CVTState(
        180.0, 40.0, dz_lo.secondary.effective * 40.0, s_lo, -0.10
    )
    lower = project_cvt_velocity_topology(
        model=model,
        vector=incoming.as_vector(),
        shift_position=s_lo,
        from_topology=CVTVelocityTopology.DEADZONE,
        to_topology=CVTVelocityTopology.DEADZONE,
        stop_shift_velocity=True,
        lock_secondary_belt=True,
    )
    _check_projection(
        findings,
        "lower_stop_projection",
        lower,
        extra_ok=abs(CVTState.from_vector(lower.successor_state).shift_speed) < 1e-12,
    )


def build_reference_system():
    programme = route.GradeProgramme.default()
    candidate = route.load_candidate(route.DEFAULT_FIXED_PIVOT_PRESET)
    resolved = route.resolve_primary_preload(
        candidate,
        target_engagement_rpm=2000.0,
        programme=programme,
    )
    system, _engine, _road = route.build_composed_system(
        resolved.constants,
        programme,
    )
    initial_cvt = route.launch_cvt_state(primary_rpm=1800.0)
    initial_full = system.initial_state(
        cvt_state=initial_cvt,
        host_state=system.host.initial_state(secondary_shaft_angle=0.0),
    )
    initial_mode = system.classify_initial_mode(initial_full)
    return programme, system, initial_full, initial_mode


def integrate_reference(system, initial_full, initial_mode, *, duration, rtol, atol, max_step):
    return integrate_hybrid(
        system=system,
        time_span=(0.0, duration),
        initial_state=initial_full,
        initial_mode=initial_mode,
        settings=HybridIntegratorSettings(
            relative_tolerance=rtol,
            absolute_tolerance=atol,
            method="LSODA",
            max_step=max_step,
            maximum_transitions=400,
            retain_dense_output=True,
        ),
    )


def segment_times(start: float, end: float, step: float) -> np.ndarray:
    """Sample a segment without leaving short event intervals under-resolved."""
    if end <= start:
        return np.asarray([start], dtype=float)
    duration = end - start
    intervals = max(int(np.ceil(duration / step)), 12)
    return np.linspace(start, end, intervals + 1, dtype=float)


def radial_wrap_energy(model, state: CVTState, mode) -> float:
    if mode.cvt.engagement is CVTEngagementState.DEADZONE:
        return 0.0
    mass = belt_wrap_radial_shift_inertia(
        model=model,
        shift_position=state.shift_position,
    )
    return 0.5 * mass * state.shift_speed**2


def energy_trace(system, result, initial_full, initial_mode, step: float):
    initial_energy = energy.stored_energy(
        system=system, time=0.0, full_state=initial_full, mode=initial_mode
    )
    transitions = sorted(result.transitions, key=lambda rec: rec.time)
    impact_times = np.asarray([rec.time for rec in transitions], dtype=float)
    impact_losses = np.asarray(
        [energy._impact_loss_from_transition(rec) for rec in transitions], dtype=float
    )
    cumulative_impact = np.cumsum(impact_losses) if impact_losses.size else impact_losses

    rows = []
    cum_ext = 0.0
    cum_slip = 0.0

    for segment in result.segments:
        times = segment_times(segment.start_time, segment.end_time, step)
        states = segment.dense_state_at(times)
        ext_power = np.zeros(times.size)
        slip_power = np.zeros(times.size)
        stored = np.zeros(times.size)
        sdot = np.zeros(times.size)
        radial_ke = np.zeros(times.size)

        for i, (t, full_state) in enumerate(zip(times, states.T, strict=True)):
            boundaries = system._shaft_boundaries(time=float(t), state=full_state)
            cvt_state = CVTState.from_vector(system.layout.view(full_state, "cvt"))
            ext_power[i] = (
                boundaries.primary.external_torque * cvt_state.primary_angular_speed
                + boundaries.secondary.external_torque * cvt_state.secondary_angular_speed
            )
            slip_power[i] = energy.kinetic_slip_dissipation_power(
                system=system,
                time=float(t),
                full_state=full_state,
                mode=segment.mode,
                boundaries=boundaries,
            )
            stored[i] = energy.stored_energy(
                system=system,
                time=float(t),
                full_state=full_state,
                mode=segment.mode,
                boundaries=boundaries,
            )
            sdot[i] = cvt_state.shift_speed
            radial_ke[i] = radial_wrap_energy(system.cvt.model, cvt_state, segment.mode)

        ext_inc = energy._cumulative_trapezoid(ext_power, times)
        slip_inc = energy._cumulative_trapezoid(slip_power, times)

        for i, t in enumerate(times):
            if impact_times.size:
                idx = np.searchsorted(impact_times, float(t) + 1e-12, side="right") - 1
                impacts = float(cumulative_impact[idx]) if idx >= 0 else 0.0
            else:
                impacts = 0.0
            external = cum_ext + float(ext_inc[i])
            slip = cum_slip + float(slip_inc[i])
            stored_change = float(stored[i] - initial_energy)
            residual = external - stored_change - slip - impacts
            rows.append(
                {
                    "time_s": float(t),
                    "mode": str(segment.mode.cvt),
                    "shift_speed_m_per_s": float(sdot[i]),
                    "belt_wrap_radial_ke_J": float(radial_ke[i]),
                    "external_work_J": external,
                    "stored_energy_change_J": stored_change,
                    "slip_dissipation_J": slip,
                    "impact_dissipation_J": impacts,
                    "balance_residual_J": residual,
                }
            )

        cum_ext += float(ext_inc[-1])
        cum_slip += float(slip_inc[-1])

    dedup = {}
    for row in rows:
        dedup[round(row["time_s"], 12)] = row
    rows = [dedup[key] for key in sorted(dedup)]

    abs_residuals = np.asarray([abs(row["balance_residual_J"]) for row in rows])
    active = np.asarray([abs(row["shift_speed_m_per_s"]) > 1e-6 for row in rows])
    ext = np.asarray([abs(row["external_work_J"]) for row in rows])
    summary = {
        "audit_step_s": step,
        "final_residual_J": rows[-1]["balance_residual_J"],
        "max_abs_residual_J": float(np.max(abs_residuals)),
        "max_abs_residual_during_active_shift_J": (
            float(np.max(abs_residuals[active])) if np.any(active) else 0.0
        ),
        "max_radial_wrap_ke_J": float(
            max(row["belt_wrap_radial_ke_J"] for row in rows)
        ),
        "max_abs_external_work_J": float(np.max(ext)),
        "final_residual_fraction_of_external": (
            abs(rows[-1]["balance_residual_J"]) / max(abs(rows[-1]["external_work_J"]), 1.0)
        ),
    }
    return summary, rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)



def _sample_segment_power(system, segment, step: float):
    """Return continuous external/slip work over one fixed-mode segment."""
    times = segment_times(segment.start_time, segment.end_time, step)
    states = segment.dense_state_at(times)
    ext_power = np.zeros(times.size, dtype=float)
    slip_power = np.zeros(times.size, dtype=float)
    for i, (t, full_state) in enumerate(zip(times, states.T, strict=True)):
        boundaries = system._shaft_boundaries(time=float(t), state=full_state)
        cvt_state = CVTState.from_vector(system.layout.view(full_state, "cvt"))
        ext_power[i] = (
            boundaries.primary.external_torque * cvt_state.primary_angular_speed
            + boundaries.secondary.external_torque * cvt_state.secondary_angular_speed
        )
        slip_power[i] = energy.kinetic_slip_dissipation_power(
            system=system,
            time=float(t),
            full_state=full_state,
            mode=segment.mode,
            boundaries=boundaries,
        )
    ext_work = float(energy._cumulative_trapezoid(ext_power, times)[-1])
    slip_work = float(energy._cumulative_trapezoid(slip_power, times)[-1])
    return ext_work, slip_work


def continuous_segment_defects(system, result, steps: tuple[float, ...]):
    """Localize energy defects inside continuous hybrid segments.

    No impact bookkeeping appears here: each row starts at the exact post-event
    state of a segment and ends at its exact pre-event state.  Therefore

        defect = W_external - Delta E_stored - E_slip

    should converge to zero for a mechanically/energetically closed continuous
    regime as the power quadrature is refined.
    """
    all_rows = []
    for index, segment in enumerate(result.segments):
        start_state = np.asarray(segment.state[:, 0], dtype=float)
        end_state = np.asarray(segment.state[:, -1], dtype=float)
        start_boundaries = system._shaft_boundaries(
            time=segment.start_time, state=start_state
        )
        end_boundaries = system._shaft_boundaries(
            time=segment.end_time, state=end_state
        )
        e0 = energy.stored_energy(
            system=system,
            time=segment.start_time,
            full_state=start_state,
            mode=segment.mode,
            boundaries=start_boundaries,
        )
        e1 = energy.stored_energy(
            system=system,
            time=segment.end_time,
            full_state=end_state,
            mode=segment.mode,
            boundaries=end_boundaries,
        )
        cvt0 = CVTState.from_vector(system.layout.view(start_state, "cvt"))
        cvt1 = CVTState.from_vector(system.layout.view(end_state, "cvt"))
        radial0 = radial_wrap_energy(system.cvt.model, cvt0, segment.mode)
        radial1 = radial_wrap_energy(system.cvt.model, cvt1, segment.mode)

        row = {
            "segment_index": index,
            "mode": str(segment.mode.cvt),
            "start_time_s": segment.start_time,
            "end_time_s": segment.end_time,
            "duration_s": segment.end_time - segment.start_time,
            "stored_delta_J": float(e1 - e0),
            "radial_wrap_ke_start_J": radial0,
            "radial_wrap_ke_end_J": radial1,
            "radial_wrap_ke_delta_J": radial1 - radial0,
        }
        for step in steps:
            ext_work, slip_work = _sample_segment_power(system, segment, step)
            defect = ext_work - (e1 - e0) - slip_work
            tag = f"{step:.9g}".replace(".", "p")
            row[f"external_work_h_{tag}_J"] = ext_work
            row[f"slip_work_h_{tag}_J"] = slip_work
            row[f"defect_h_{tag}_J"] = float(defect)
        all_rows.append(row)
    return all_rows


def event_energy_defects(system, result):
    """Check the exact stored-energy jump against recorded impact loss."""
    rows = []
    for index, rec in enumerate(result.transitions):
        meta = rec.transition.metadata.get("cvt", rec.transition.metadata)
        if not isinstance(meta, dict) or "impact_model" not in meta:
            continue

        # Segment index aligns with transition record index for event-ending segments.
        pre_segment = result.segments[index]
        pre_state = np.asarray(pre_segment.state[:, -1], dtype=float)
        post_state = np.asarray(rec.post_transition_state, dtype=float)
        pre_boundaries = system._shaft_boundaries(time=rec.time, state=pre_state)
        post_boundaries = system._shaft_boundaries(time=rec.time, state=post_state)

        pre_energy = energy.stored_energy(
            system=system,
            time=rec.time,
            full_state=pre_state,
            mode=rec.previous_mode,
            boundaries=pre_boundaries,
        )
        post_energy = energy.stored_energy(
            system=system,
            time=rec.time,
            full_state=post_state,
            mode=rec.transition.next_mode,
            boundaries=post_boundaries,
        )
        recorded_loss = float(meta["impact_dissipated_energy_J"])
        exact_drop = float(pre_energy - post_energy)
        rows.append(
            {
                "transition_index": index,
                "time_s": rec.time,
                "reason": rec.transition.reason,
                "previous_mode": str(rec.previous_mode.cvt),
                "next_mode": str(rec.transition.next_mode.cvt),
                "pre_stored_energy_J": float(pre_energy),
                "post_stored_energy_J": float(post_energy),
                "exact_stored_energy_drop_J": exact_drop,
                "recorded_impact_loss_J": recorded_loss,
                "event_energy_defect_J": exact_drop - recorded_loss,
                "momentum_residual": float(meta["impact_momentum_residual"]),
                "constraint_residual": float(meta["impact_constraint_residual"]),
            }
        )
    return rows



def stick_constraint_pair_power(system, segment, step: float):
    """Integrate signed contact-pair power at interfaces declared sticking.

    For the reduced contact law,

        P_pair,j = lambda_j N_j (v_b - r_j omega_j).

    Exact sticking has ``v_rel = 0`` and therefore zero pair power.  The
    continuous stick closure constrains acceleration-level compatibility; a
    finite-tolerance ODE trajectory can nevertheless drift slightly from the
    velocity-level invariant.  This diagnostic measures the energetic
    consequence of that drift without modifying the trajectory.

    Negative pair work acts like dissipation; positive pair work acts like
    numerical energy injection.  Because the ordinary audit excludes static
    contact from slip dissipation, the energy residual corrected for this
    numerical invariant drift is

        R_corrected = R + integral(P_pair dt).
    """
    times = segment_times(segment.start_time, segment.end_time, step)
    states = segment.dense_state_at(times)

    primary_power = np.zeros(times.size, dtype=float)
    secondary_power = np.zeros(times.size, dtype=float)
    max_abs_primary_vrel = 0.0
    max_abs_secondary_vrel = 0.0
    max_abs_primary_arel = 0.0
    max_abs_secondary_arel = 0.0

    cvt_mode = segment.mode.cvt
    if cvt_mode.engagement is CVTEngagementState.DEADZONE:
        return {
            "primary_stick_pair_work_J": 0.0,
            "secondary_stick_pair_work_J": 0.0,
            "total_stick_pair_work_J": 0.0,
            "max_abs_primary_stick_vrel_m_s": 0.0,
            "max_abs_secondary_stick_vrel_m_s": 0.0,
            "max_abs_primary_stick_arel_m_s2": 0.0,
            "max_abs_secondary_stick_arel_m_s2": 0.0,
            "min_stick_pair_power_W": 0.0,
            "max_stick_pair_power_W": 0.0,
        }

    contact = cvt_mode.contact_regime
    assert contact is not None
    sticking = tuple(contact.mode.sticking_interfaces)
    if not sticking:
        return {
            "primary_stick_pair_work_J": 0.0,
            "secondary_stick_pair_work_J": 0.0,
            "total_stick_pair_work_J": 0.0,
            "max_abs_primary_stick_vrel_m_s": 0.0,
            "max_abs_secondary_stick_vrel_m_s": 0.0,
            "max_abs_primary_stick_arel_m_s2": 0.0,
            "max_abs_secondary_stick_arel_m_s2": 0.0,
            "min_stick_pair_power_W": 0.0,
            "max_stick_pair_power_W": 0.0,
        }

    for i, (t, full_state) in enumerate(zip(times, states.T, strict=True)):
        boundaries = system._shaft_boundaries(time=float(t), state=full_state)
        cvt_vector = system.layout.view(full_state, "cvt")
        physics = system.cvt._evaluate_physics(
            time=float(t),
            state=cvt_vector,
            mode=cvt_mode,
            shaft_boundaries=boundaries,
        )
        for interface in sticking:
            if interface is ContactInterface.PRIMARY:
                lam = float(physics.traction_utilization.primary_lambda)
                normal = float(physics.normal_primary)
                vrel = float(physics.relative_motion.primary_relative_speed)
                arel = float(physics.relative_motion.primary_relative_acceleration)
                primary_power[i] += lam * normal * vrel
                max_abs_primary_vrel = max(max_abs_primary_vrel, abs(vrel))
                max_abs_primary_arel = max(max_abs_primary_arel, abs(arel))
            elif interface is ContactInterface.SECONDARY:
                lam = float(physics.traction_utilization.secondary_lambda)
                normal = float(physics.normal_secondary)
                vrel = float(physics.relative_motion.secondary_relative_speed)
                arel = float(physics.relative_motion.secondary_relative_acceleration)
                secondary_power[i] += lam * normal * vrel
                max_abs_secondary_vrel = max(max_abs_secondary_vrel, abs(vrel))
                max_abs_secondary_arel = max(max_abs_secondary_arel, abs(arel))

    primary_work = float(energy._cumulative_trapezoid(primary_power, times)[-1])
    secondary_work = float(energy._cumulative_trapezoid(secondary_power, times)[-1])
    total_power = primary_power + secondary_power
    return {
        "primary_stick_pair_work_J": primary_work,
        "secondary_stick_pair_work_J": secondary_work,
        "total_stick_pair_work_J": primary_work + secondary_work,
        "max_abs_primary_stick_vrel_m_s": max_abs_primary_vrel,
        "max_abs_secondary_stick_vrel_m_s": max_abs_secondary_vrel,
        "max_abs_primary_stick_arel_m_s2": max_abs_primary_arel,
        "max_abs_secondary_stick_arel_m_s2": max_abs_secondary_arel,
        "min_stick_pair_power_W": float(np.min(total_power)),
        "max_stick_pair_power_W": float(np.max(total_power)),
    }


def stick_power_localization(system, result, segment_rows, step: float):
    """Attach stick-constraint pair work to each continuous segment."""
    tag = f"{step:.9g}".replace(".", "p")
    defect_key = f"defect_h_{tag}_J"
    rows = []
    for segment, defect_row in zip(result.segments, segment_rows, strict=True):
        diag = stick_constraint_pair_power(system, segment, step)
        defect = float(defect_row[defect_key])
        work = float(diag["total_stick_pair_work_J"])
        rows.append(
            {
                "segment_index": defect_row["segment_index"],
                "mode": defect_row["mode"],
                "start_time_s": defect_row["start_time_s"],
                "end_time_s": defect_row["end_time_s"],
                "continuous_energy_defect_J": defect,
                **diag,
                "defect_plus_stick_pair_work_J": defect + work,
            }
        )
    return rows


def summarize_stick_power_candidate(
    findings: list[Finding],
    rows: list[dict[str, Any]],
):
    total_defect = sum(float(r["continuous_energy_defect_J"]) for r in rows)
    total_work = sum(float(r["total_stick_pair_work_J"]) for r in rows)
    max_vrel = max(
        max(
            float(r["max_abs_primary_stick_vrel_m_s"]),
            float(r["max_abs_secondary_stick_vrel_m_s"]),
        )
        for r in rows
    )
    max_arel = max(
        max(
            float(r["max_abs_primary_stick_arel_m_s2"]),
            float(r["max_abs_secondary_stick_arel_m_s2"]),
        )
        for r in rows
    )
    print("\n--- Velocity-level stick-invariant drift diagnostic ---")
    print(f"integral lambda*N*v_rel on declared sticks : {total_work:+.12f} J")
    print(f"largest |v_rel| on declared stick          : {max_vrel:.12e} m/s")
    print(f"largest |a_rel| on declared stick          : {max_arel:.12e} m/s^2")
    ranked = sorted(
        rows,
        key=lambda r: abs(float(r["total_stick_pair_work_J"])),
        reverse=True,
    )
    print("largest stick pair-work segments:")
    for row in ranked[:8]:
        print(
            f"  seg {int(row['segment_index']):02d}: "
            f"W_pair={float(row['total_stick_pair_work_J']):+.12f} J, "
            f"R={float(row['continuous_energy_defect_J']):+.12f} J, "
            f"R+W_pair={float(row['defect_plus_stick_pair_work_J']):+.12f} J"
        )
    record(
        findings,
        "WARN" if abs(total_work) > 1e-4 else "PASS",
        "stick_velocity_invariant_drift",
        (
            "Declared sticking interfaces carry measurable signed pair work because "
            "the integrated trajectory is not exactly on v_rel=0. This is a numerical "
            "velocity-level invariant drift diagnostic, not physical static-friction dissipation."
            if abs(total_work) > 1e-4
            else
            "Declared sticking interfaces remain energetically negligible at the velocity level."
        ),
        integrated_stick_pair_work_J=total_work,
        max_abs_stick_relative_speed_m_s=max_vrel,
        max_abs_stick_relative_acceleration_m_s2=max_arel,
    )
    return {
        "integrated_stick_pair_work_J": total_work,
        "max_abs_stick_relative_speed_m_s": max_vrel,
        "max_abs_stick_relative_acceleration_m_s2": max_arel,
        "largest_segments": ranked[:8],
    }


def numerical_contact_correction(
    segment_rows,
    stick_rows,
    step: float,
):
    """Correct only numerical velocity-level stick drift on the same grid.

    The helical movable-face power channel is no longer a missing term: it is
    represented directly by the power-equivalent contact speed in production
    mechanics.  Therefore it must NOT be added again here.
    """
    tag = f"{step:.9g}".replace(".", "p")
    defect_key = f"defect_h_{tag}_J"
    rows = []
    for base, stick in zip(segment_rows, stick_rows, strict=True):
        defect = float(base[defect_key])
        stick_work = float(stick["total_stick_pair_work_J"])
        rows.append(
            {
                "segment_index": base["segment_index"],
                "mode": base["mode"],
                "start_time_s": base["start_time_s"],
                "end_time_s": base["end_time_s"],
                "raw_continuous_defect_J": defect,
                "stick_invariant_pair_work_J": stick_work,
                "corrected_defect_J": defect + stick_work,
            }
        )
    return rows


def summarize_numerical_contact_correction(
    findings: list[Finding],
    rows: list[dict[str, Any]],
    *,
    label: str,
):
    raw = sum(float(r["raw_continuous_defect_J"]) for r in rows)
    stick = sum(float(r["stick_invariant_pair_work_J"]) for r in rows)
    corrected = sum(float(r["corrected_defect_J"]) for r in rows)
    print(f"\n--- Numerical contact-power accounting ({label}) ---")
    print(f"raw continuous defect      : {raw:+.12f} J")
    print(f"stick invariant pair work  : {stick:+.12f} J")
    print(f"corrected continuous defect: {corrected:+.12f} J")
    print("helix face-power correction : NOT APPLIED (represented in contact speed)")
    ranked = sorted(rows, key=lambda r: abs(float(r["corrected_defect_J"])), reverse=True)
    print("largest corrected segments:")
    for row in ranked[:8]:
        print(
            f"  seg {int(row['segment_index']):02d}: "
            f"{float(row['corrected_defect_J']):+.12f} J"
        )
    record(
        findings,
        "WARN" if abs(corrected) > 0.1 else "PASS",
        f"numerical_contact_power_{label}",
        "Residual after correcting only measured numerical stick-invariant drift; "
        "the helix face-power channel is already inside the production contact kinematics.",
        raw_continuous_defect_J=raw,
        stick_invariant_pair_work_J=stick,
        corrected_continuous_defect_J=corrected,
    )
    return {
        "raw_continuous_defect_J": raw,
        "stick_invariant_pair_work_J": stick,
        "corrected_continuous_defect_J": corrected,
        "largest_segments": ranked[:8],
    }

def summarize_localized_defects(
    findings: list[Finding],
    segment_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
    steps: tuple[float, ...],
):
    fine = steps[-1]
    fine_tag = f"{fine:.9g}".replace(".", "p")
    fine_key = f"defect_h_{fine_tag}_J"

    ranked = sorted(segment_rows, key=lambda r: abs(float(r[fine_key])), reverse=True)
    total_continuous = sum(float(r[fine_key]) for r in segment_rows)
    total_event = sum(float(r["event_energy_defect_J"]) for r in event_rows)

    print("\n--- Continuous segment energy-defect localization ---")
    print(f"finest quadrature step: {fine:g} s")
    print(f"sum continuous defects: {total_continuous:.9f} J")
    print(f"sum exact event defects: {total_event:.9f} J")
    print("largest continuous defects:")
    for row in ranked[:10]:
        print(
            "  seg {segment_index:02d}  {start_time_s:8.5f}->{end_time_s:8.5f} s  "
            "defect={defect:+.9f} J  dE_rad={drad:+.9f} J  mode={mode}".format(
                segment_index=row["segment_index"],
                start_time_s=row["start_time_s"],
                end_time_s=row["end_time_s"],
                defect=float(row[fine_key]),
                drad=float(row["radial_wrap_ke_delta_J"]),
                mode=row["mode"],
            )
        )

    group: dict[str, float] = {}
    for row in segment_rows:
        group[row["mode"]] = group.get(row["mode"], 0.0) + float(row[fine_key])
    print("defect summed by continuous mode:")
    for mode, value in sorted(group.items(), key=lambda kv: abs(kv[1]), reverse=True):
        print(f"  {value:+.9f} J  {mode}")

    worst_event = max(
        (abs(float(r["event_energy_defect_J"])) for r in event_rows),
        default=0.0,
    )
    record(
        findings,
        "PASS" if worst_event < 1e-8 else "FAIL",
        "event_energy_jump_consistency",
        "Exact pre/post stored-energy drops agree with recorded impact/capture losses."
        if worst_event < 1e-8
        else "At least one impact/capture recorded loss disagrees with the exact stored-energy jump.",
        max_abs_event_energy_defect_J=worst_event,
        sum_event_energy_defect_J=total_event,
    )

    # Quadrature convergence of the sum of continuous segment defects.
    totals = {}
    for step in steps:
        tag = f"{step:.9g}".replace(".", "p")
        key = f"defect_h_{tag}_J"
        totals[step] = sum(float(row[key]) for row in segment_rows)
    print("continuous-defect quadrature sweep:")
    for step in steps:
        print(f"  h={step:.8g} s : {totals[step]:+.9f} J")

    if len(steps) >= 3:
        h0, h1, h2 = steps[-3:]
        r0, r1, r2 = totals[h0], totals[h1], totals[h2]
        # Richardson estimate for a smooth trapezoidal O(h^2) quadrature error.
        richardson = (4.0 * r2 - r1) / 3.0
        record(
            findings,
            "WARN" if abs(richardson) > 1.0 else "PASS",
            "continuous_energy_defect_asymptote",
            "Richardson extrapolation estimates the residual continuous-regime energy defect after removing leading trapezoid quadrature error.",
            estimated_zero_step_defect_J=richardson,
            finest_observed_defect_J=r2,
            previous_observed_defect_J=r1,
        )
    return {
        "sum_continuous_defect_finest_J": total_continuous,
        "sum_event_defect_J": total_event,
        "quadrature_totals_J": {str(k): v for k, v in totals.items()},
        "largest_segments": ranked[:10],
    }


def integrated_audit(findings: list[Finding], args, output_dir: Path):
    _, system, initial_full, initial_mode = build_reference_system()
    nominal = integrate_reference(
        system,
        initial_full,
        initial_mode,
        duration=args.duration_s,
        rtol=args.rtol,
        atol=args.atol,
        max_step=args.max_step_s,
    )
    if not nominal.completed:
        record(findings, "FAIL", "nominal_integration", nominal.termination_reason)
        return None

    record(
        findings,
        "PASS",
        "nominal_integration",
        "Reference hybrid trajectory completed.",
        transitions=len(nominal.transitions),
        final_time_s=nominal.final_time,
    )

    coarse, coarse_rows = energy_trace(
        system, nominal, initial_full, initial_mode, args.audit_step_s
    )
    fine_step = max(args.audit_step_s / 2.0, 1e-4)
    fine, fine_rows = energy_trace(
        system, nominal, initial_full, initial_mode, fine_step
    )
    write_csv(output_dir / "energy_trace_coarse.csv", coarse_rows)
    write_csv(output_dir / "energy_trace_fine.csv", fine_rows)

    record(
        findings,
        "PASS",
        "energy_balance_observed",
        "Energy balance was evaluated on two quadrature grids; inspect magnitudes below rather than treating this as an automatic validation threshold.",
        coarse_final_residual_J=coarse["final_residual_J"],
        fine_final_residual_J=fine["final_residual_J"],
        coarse_max_active_shift_residual_J=coarse["max_abs_residual_during_active_shift_J"],
        fine_max_active_shift_residual_J=fine["max_abs_residual_during_active_shift_J"],
        fine_final_fraction_of_external=fine["final_residual_fraction_of_external"],
        max_radial_wrap_ke_J=fine["max_radial_wrap_ke_J"],
    )

    # A large non-converging residual is a warning, not something to hide.
    coarse_mag = abs(coarse["final_residual_J"])
    fine_mag = abs(fine["final_residual_J"])
    if fine["final_residual_fraction_of_external"] > 1e-3:
        record(
            findings,
            "WARN",
            "energy_balance_scale",
            "Final energy residual exceeds 0.1% of accumulated external work. Investigate before freezing results.",
        )
    if coarse_mag > 1e-6 and fine_mag > 1.25 * coarse_mag:
        record(
            findings,
            "WARN",
            "energy_quadrature_behavior",
            "Halving the audit quadrature step made the final residual materially larger; inspect the time trace for a structural rather than quadrature-localized discrepancy.",
        )
    else:
        record(
            findings,
            "PASS",
            "energy_quadrature_behavior",
            "No obvious worsening of the final energy residual under the finer audit quadrature.",
        )

    # Transition metadata audit over the actual trajectory.
    bad_transition = False
    worst_momentum = 0.0
    worst_constraint = 0.0
    min_loss = float("inf")
    impact_count = 0
    for rec in nominal.transitions:
        meta = rec.transition.metadata.get("cvt", rec.transition.metadata)
        if not isinstance(meta, dict) or "impact_model" not in meta:
            continue
        impact_count += 1
        loss = float(meta["impact_dissipated_energy_J"])
        momentum = abs(float(meta["impact_momentum_residual"]))
        constraint = abs(float(meta["impact_constraint_residual"]))
        worst_momentum = max(worst_momentum, momentum)
        worst_constraint = max(worst_constraint, constraint)
        min_loss = min(min_loss, loss)
        if loss < -1e-9 or momentum > 1e-7 or constraint > 1e-8:
            bad_transition = True
    if impact_count == 0:
        record(
            findings,
            "WARN",
            "trajectory_impact_metadata",
            "This trajectory contained no recorded finite-speed impact/capture projections.",
        )
    else:
        record(
            findings,
            "FAIL" if bad_transition else "PASS",
            "trajectory_impact_metadata",
            "Actual hybrid transition metadata is mechanically admissible."
            if not bad_transition
            else "At least one actual hybrid transition has a negative loss or large residual.",
            impact_count=impact_count,
            min_dissipated_energy_J=min_loss,
            max_momentum_residual=worst_momentum,
            max_constraint_residual=worst_constraint,
        )

    localization_steps = tuple(
        max(args.audit_step_s / factor, 2.5e-4)
        for factor in (1.0, 2.0, 4.0, 8.0)
    )
    # Preserve order while removing duplicates caused by the lower floor.
    localization_steps = tuple(dict.fromkeys(localization_steps))
    segment_rows = continuous_segment_defects(
        system, nominal, localization_steps
    )
    event_rows = event_energy_defects(system, nominal)
    write_csv(output_dir / "continuous_segment_energy_defects.csv", segment_rows)
    if event_rows:
        write_csv(output_dir / "event_energy_defects.csv", event_rows)
    localization = summarize_localized_defects(
        findings,
        segment_rows,
        event_rows,
        localization_steps,
    )

    stick_rows = stick_power_localization(
        system,
        nominal,
        segment_rows,
        localization_steps[-1],
    )
    write_csv(output_dir / "stick_constraint_power_candidate.csv", stick_rows)
    stick_candidate = summarize_stick_power_candidate(findings, stick_rows)

    numerical_rows = numerical_contact_correction(
        segment_rows,
        stick_rows,
        localization_steps[-1],
    )
    write_csv(output_dir / "numerical_contact_power_accounting.csv", numerical_rows)
    numerical_nominal = summarize_numerical_contact_correction(
        findings,
        numerical_rows,
        label="nominal",
    )

    refinement = None
    tight_energy_accounting = None
    if not args.skip_refinement:
        tight = integrate_reference(
            system,
            initial_full,
            initial_mode,
            duration=args.duration_s,
            rtol=max(args.rtol * 0.3, 1e-9),
            atol=max(args.atol * 0.3, 1e-12),
            max_step=max(args.max_step_s * 0.5, 1e-5),
        )
        if not tight.completed:
            record(findings, "FAIL", "refined_integration", tight.termination_reason)
        else:
            nom_cvt = CVTState.from_vector(system.layout.view(nominal.final_state, "cvt"))
            tight_cvt = CVTState.from_vector(system.layout.view(tight.final_state, "cvt"))
            labels = (
                "omega_p_rad_s",
                "omega_s_rad_s",
                "belt_speed_m_s",
                "shift_position_m",
                "shift_speed_m_s",
            )
            a = np.asarray(nom_cvt.as_vector(), dtype=float)
            b = np.asarray(tight_cvt.as_vector(), dtype=float)
            delta = b - a
            scales = np.maximum(np.maximum(np.abs(a), np.abs(b)), np.asarray([1, 1, 1, 1e-3, 1e-3]))
            normalized = np.abs(delta) / scales
            refinement = {
                "nominal_transitions": len(nominal.transitions),
                "tight_transitions": len(tight.transitions),
                "max_normalized_final_state_delta": float(np.max(normalized)),
                "final_state_deltas": {
                    label: float(value) for label, value in zip(labels, delta, strict=True)
                },
            }
            level = "WARN" if np.max(normalized) > 1e-2 else "PASS"
            record(
                findings,
                level,
                "solver_refinement",
                "Nominal and tighter integrations were compared at the final physical state.",
                **refinement,
            )

            # Repeat the exact same energy/contact accounting on the tighter
            # trajectory. If the remaining defect is numerical invariant drift,
            # it should shrink with solver refinement.
            tight_steps = (localization_steps[-1],)
            tight_segment_rows = continuous_segment_defects(
                system, tight, tight_steps
            )
            tight_stick_rows = stick_power_localization(
                system,
                tight,
                tight_segment_rows,
                localization_steps[-1],
            )
            tight_numerical_rows = numerical_contact_correction(
                tight_segment_rows,
                tight_stick_rows,
                localization_steps[-1],
            )
            write_csv(
                output_dir / "tight_numerical_contact_power_accounting.csv",
                tight_numerical_rows,
            )
            tight_energy_accounting = summarize_numerical_contact_correction(
                findings,
                tight_numerical_rows,
                label="tight",
            )

    return {
        "coarse_energy": coarse,
        "fine_energy": fine,
        "localization": localization,
        "stick_velocity_invariant_drift": stick_candidate,
        "numerical_contact_power_nominal": numerical_nominal,
        "tight_energy_accounting": tight_energy_accounting,
        "refinement": refinement,
    }


def run_pytest(findings: list[Finding], args) -> None:
    if args.no_pytest:
        record(findings, "WARN", "pytest", "pytest execution skipped by request.")
        return
    if importlib.util.find_spec("pytest") is None:
        record(
            findings,
            "WARN",
            "pytest",
            "pytest is not installed; direct mechanics checks still ran. Install the dev extra to execute the regression suite.",
        )
        return
    targets = (
        ["test/smoke"]
        if args.full_smoke
        else [
            "test/smoke/test_formulation_alignment.py",
            "test/smoke/test_zero_width_deadzone_low_ratio.py",
            "test/smoke/test_impact_belt_radial_modes.py",
            "test/smoke/test_power_equivalent_contact_speed.py",
        ]
    )
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *targets],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    log = completed.stdout + ("\n" + completed.stderr if completed.stderr else "")
    print(log)
    record(
        findings,
        "PASS" if completed.returncode == 0 else "FAIL",
        "pytest",
        "Selected regression suite passed." if completed.returncode == 0 else "Selected regression suite failed.",
        return_code=completed.returncode,
    )


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    findings: list[Finding] = []

    print("\n=== CINDER transition / energy consistency audit ===\n")
    structural_source_audit(findings)

    model = load_plant()
    kinetic_inventory_audit(findings, model)
    transition_audit(findings, model)

    integrated = integrated_audit(findings, args, args.output_dir)
    run_pytest(findings, args)

    record(
        findings,
        "WARN",
        "scope_boundary",
        "This audit covers the kinetic modes explicitly retained by current CINDER. It does NOT establish negligibility of omitted physics such as belt longitudinal elasticity, straight-span transverse path motion, local seating/creep, radial face friction, or other V2 effects.",
    )
    record(
        findings,
        "WARN",
        "manual_followup",
        "With the helix face-power channel now represented directly, investigate only residuals that remain after solver refinement, dense short-segment quadrature, and stick-invariant checks.",
    )

    payload = {
        "findings": [
            {
                "level": item.level,
                "key": item.key,
                "message": item.message,
                "data": item.data,
            }
            for item in findings
        ],
        "integrated_audit": integrated,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

    fail_count = sum(item.level == "FAIL" for item in findings)
    warn_count = sum(item.level == "WARN" for item in findings)
    print("\n=== Summary ===")
    print(f"FAIL: {fail_count}")
    print(f"WARN: {warn_count}")
    print(f"Report: {args.output_dir / 'summary.json'}")
    if fail_count:
        print("RESULT: NOT READY — at least one mechanical/regression check failed.")
        return 1
    if warn_count:
        print("RESULT: NO HARD FAILURES, BUT REVIEW WARNINGS BEFORE FREEZING RESULTS.")
        return 0
    print("RESULT: ALL IMPLEMENTED CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
