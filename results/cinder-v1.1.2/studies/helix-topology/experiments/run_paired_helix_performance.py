"""E5.8 paired full-dynamic versus quasi-static helix transient comparison.

This stage turns the local E5.7 mechanism result into a trajectory/performance
comparison.  Two systems start from the SAME naturally conditioned CVT state
and receive the SAME boundary transient:

    1. full dynamic slotted helix (production CINDER formulation),
    2. quasi-static slotted helix (same static torque+spring law, with the
       movable-sheave rotational inertia returned to classical rigid shaft
       inertia rather than deleted).

The quasi-static reduction is the tagged CINDER dynamic-actuator ablation
variant, not a new ad-hoc force law.  The comparison therefore asks what the
helix dynamic terms change in shift trajectory, ratio, shaft speeds, clamp,
normal force and belt contact regime.

This is NOT the true unilateral-detachment comparator: both trajectories keep
the helical kinematic constraint and permit signed/slotted helix reaction.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import math
from math import radians
from pathlib import Path
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY_ROOT = HERE.parent
for path in (STUDY_ROOT, HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from study_support import (  # noqa: E402
    ARTIFACTS,
    AddedTorqueBoundary,
    BlendToTorqueBoundary,
    SmoothStep,
    build_reference_components,
    build_slotted_system,
    flat_programme,
    integrate_system,
    load_tagged_modules,
    run_flat_slotted_reference_with_constants,
    select_restart,
    verify_environment,
    write_rows,
)
try:
    import run_transient_severity_race as e56  # type: ignore  # noqa: E402
except ModuleNotFoundError:  # package import in tests
    from experiments import run_transient_severity_race as e56  # type: ignore  # noqa: E402


@dataclass(frozen=True, slots=True)
class PairedCase:
    case_id: str
    label: str
    preload_deg: float
    restart_shift_percent: float
    perturbation_family: str
    perturbation_value: float
    ramp_s: float
    onset_s: float
    hold_s: float


@dataclass(slots=True)
class VariantRun:
    variant: Any
    assembly: Any
    system: Any
    result: Any
    samples: list[Any]
    rows: list[dict[str, Any]]
    topology_status: Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use shorter hold/sample settings for plumbing only.",
    )
    return parser.parse_args()


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _variant(ab, key: str):
    return next(item for item in ab.VARIANTS if item.key == key)


def _build_cases(cfg: dict[str, Any], *, quick: bool) -> list[PairedCase]:
    cases = []
    for item in cfg["cases"]:
        cases.append(
            PairedCase(
                case_id=str(item["case_id"]),
                label=str(item["label"]),
                preload_deg=float(item["preload_deg"]),
                restart_shift_percent=float(item["restart_shift_percent"]),
                perturbation_family=str(item["perturbation_family"]),
                perturbation_value=float(item["perturbation_value"]),
                ramp_s=float(item["ramp_s"]),
                onset_s=float(item["onset_s"]),
                hold_s=(
                    min(float(item["hold_s"]), 0.08)
                    if quick
                    else float(item["hold_s"])
                ),
            )
        )
    return cases


def _case_boundaries(*, case: PairedCase, route, engine, road_load, constants, programme):
    from cinder.model.boundaries.shaft import FullThrottleEngineBoundary

    primary = None
    secondary = None
    if case.perturbation_family == "engine_target_torque":
        base = FullThrottleEngineBoundary(
            engine,
            equivalent_rotational_inertia=constants.engine_rotational_inertia,
        )
        primary = BlendToTorqueBoundary(
            base,
            onset_s=case.onset_s,
            ramp_s=case.ramp_s,
            target_torque_Nm=case.perturbation_value,
            label="e58_engine_target",
        )
    elif case.perturbation_family == "output_load_step":
        base = route.TimeProgrammedLockedFinalDriveBoundary(
            road_load=road_load,
            programme=programme,
            direct_secondary_shaft_inertia=constants.gearbox_input_rotational_inertia,
        )
        signal = SmoothStep(
            onset_s=case.onset_s,
            ramp_s=case.ramp_s,
            target=case.perturbation_value,
        )
        secondary = AddedTorqueBoundary(base, signal, label="e58_output_load_step")
    else:  # pragma: no cover
        raise ValueError(f"Unsupported E5.8 perturbation family: {case.perturbation_family}")
    return primary, secondary


def _find_helix_law(ab, system):
    laws = [
        law
        for law in system.cvt.model.secondary_actuator.force_laws
        if isinstance(law, ab.HelicalTorqueReactionForce)
    ]
    if len(laws) != 1:
        raise RuntimeError(f"Expected exactly one secondary helix law; found {len(laws)}")
    return laws[0]


def _annotate_rows(*, ab, samples, system, variant, physical_movable_inertia: float, case: PairedCase):
    helix = _find_helix_law(ab, system)
    for sample in samples:
        row = sample.row
        row["e58_case_id"] = case.case_id
        row["e58_case_label"] = case.label
        row["e58_model"] = variant.key
        row["e58_model_label"] = variant.label
        row["e58_preload_deg"] = case.preload_deg
        row["e58_perturbation_family"] = case.perturbation_family
        row["e58_perturbation_value"] = case.perturbation_value
        row["e58_ramp_s"] = case.ramp_s
        row["e58_onset_s"] = case.onset_s
        row["e58_time_from_onset_s"] = float(row["time_s"]) - case.onset_s

        closure = sample.closure
        if closure is None:
            for key in (
                "e58_helix_qs_margin_Nm",
                "e58_helix_physical_dynamic_correction_Nm",
                "e58_helix_actual_margin_Nm",
                "e58_helix_counterfactual_full_margin_Nm",
                "e58_helix_actual_force_N",
                "e58_helix_counterfactual_full_force_N",
                "e58_secondary_internal_power_W",
                "e58_primary_internal_power_W",
                "e58_max_abs_lambda",
            ):
                row[key] = float("nan")
            row["e58_stick_stick"] = False
            continue

        theta = float(row["helix_theta_rad"])
        dtheta_ds = float(row["helix_dtheta_ds_rad_per_m"])
        d2theta_ds2 = float(row["helix_d2theta_ds2_rad_per_m2"])
        dx_ds = float(row["secondary_dx_ds"])
        motion_ratio = dtheta_ds / dx_ds if abs(dx_ds) > 1.0e-15 else float("nan")
        sdot = float(row["shift_speed_m_s"])
        sddot = float(closure.shift_acceleration)
        alpha_s = float(closure.secondary_angular_acceleration)
        tau_s = float(closure.secondary_torque)
        tau_p = float(closure.primary_torque)

        belt = helix.spec.movable_member_torque_fraction * tau_s
        spring = helix.spec.torsional_stiffness * (helix.spec.initial_twist - theta)
        qs = belt + spring
        shaft = -physical_movable_inertia * alpha_s
        shift = -physical_movable_inertia * dtheta_ds * sddot
        curvature = -physical_movable_inertia * d2theta_ds2 * sdot**2
        dynamic = shaft + shift + curvature
        counterfactual_full = qs + dynamic
        actual = counterfactual_full if variant.dynamic_helix else qs

        row["e58_helix_belt_term_Nm"] = belt
        row["e58_helix_spring_term_Nm"] = spring
        row["e58_helix_physical_shaft_term_Nm"] = shaft
        row["e58_helix_physical_shift_term_Nm"] = shift
        row["e58_helix_physical_curvature_term_Nm"] = curvature
        row["e58_helix_qs_margin_Nm"] = qs
        row["e58_helix_physical_dynamic_correction_Nm"] = dynamic
        row["e58_helix_actual_margin_Nm"] = actual
        row["e58_helix_counterfactual_full_margin_Nm"] = counterfactual_full
        row["e58_helix_actual_force_N"] = actual * motion_ratio
        row["e58_helix_counterfactual_full_force_N"] = counterfactual_full * motion_ratio
        row["e58_secondary_internal_power_W"] = tau_s * float(sample.cvt_state.secondary_angular_speed)
        row["e58_primary_internal_power_W"] = tau_p * float(sample.cvt_state.primary_angular_speed)
        lp = _finite(row.get("lambda_primary"))
        ls = _finite(row.get("lambda_secondary"))
        row["e58_max_abs_lambda"] = max(abs(lp or 0.0), abs(ls or 0.0))
        row["e58_stick_stick"] = e56.contact_is_stick_stick(row.get("cvt_mode"))


def _run_variant_case(
    *,
    case: PairedCase,
    restart,
    route,
    ab,
    full_assembly,
    engine,
    road_load,
    constants,
    variant,
    solver: dict[str, Any],
) -> VariantRun:
    duration_s = case.onset_s + case.ramp_s + case.hold_s
    programme = flat_programme(route, duration_s)
    primary_boundary, secondary_boundary = _case_boundaries(
        case=case,
        route=route,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
    )
    assembly = (
        full_assembly
        if variant.key == "full"
        else ab.ablate_assembly(full_assembly, variant)
    )
    physical_movable_inertia = float(
        full_assembly.inertias.secondary.movable_sheave_rotational_inertia
    )

    system, topology_status = build_slotted_system(
        route=route,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        primary_boundary=primary_boundary,
        secondary_boundary=secondary_boundary,
    )
    system.cvt.deadzone_evaluator.belt_secondary_lock_absolute_tolerance = float(
        solver.get("deadzone_lock_absolute_tolerance_m_s", 1.0e-6)
    )

    if variant.dynamic_helix:
        initial_mode = restart.mode
    else:
        initial_mode = system.classify_initial_mode(restart.full_state)

    max_step = max(
        float(solver["minimum_max_step_s"]),
        min(
            float(solver["maximum_step_cap_s"]),
            case.ramp_s / float(solver["ramp_step_divisor"]),
        ),
    )
    result = integrate_system(
        system=system,
        initial_state=restart.full_state,
        initial_mode=initial_mode,
        duration_s=duration_s,
        rtol=float(solver["relative_tolerance"]),
        atol=float(solver["absolute_tolerance"]),
        max_step_s=max_step,
        maximum_transitions=int(solver.get("maximum_transitions", 400)),
    )
    # An intentional hybrid termination is itself a performance outcome.
    # In particular, contact_loss_normal_resultant_floor means that this
    # formulation has reached the edge of the modeled belt-contact domain.
    # Preserve and report the trajectory up to that event rather than
    # converting a physical terminal condition into a study failure.
    # Unexpected solve_ivp failures still raise inside integrate_system.

    # Fresh equivalent system for chronological reporting, avoiding the
    # nonlinear contact continuation-cache issue documented in E4/E5.
    reporting_system, reporting_topology = build_slotted_system(
        route=route,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        primary_boundary=primary_boundary,
        secondary_boundary=secondary_boundary,
    )
    reporting_system.cvt.deadzone_evaluator.belt_secondary_lock_absolute_tolerance = float(
        solver.get("deadzone_lock_absolute_tolerance_m_s", 1.0e-6)
    )
    samples, _ = ab.sample_variant(
        variant=variant,
        system=reporting_system,
        result=result,
        step_s=float(solver["sample_step_s"]),
    )
    _annotate_rows(
        ab=ab,
        samples=samples,
        system=reporting_system,
        variant=variant,
        physical_movable_inertia=physical_movable_inertia,
        case=case,
    )
    rows = [sample.row for sample in samples]
    return VariantRun(
        variant=variant,
        assembly=assembly,
        system=reporting_system,
        result=result,
        samples=samples,
        rows=rows,
        topology_status=reporting_topology,
    )


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_time: dict[float, dict[str, Any]] = {}
    for row in rows:
        t = _finite(row.get("time_s"))
        if t is not None:
            by_time[t] = row
    return [by_time[t] for t in sorted(by_time)]


def _series(rows: list[dict[str, Any]], key: str) -> tuple[np.ndarray, np.ndarray]:
    t, y = [], []
    for row in _dedupe_rows(rows):
        tv = _finite(row.get("time_s"))
        yv = _finite(row.get(key))
        if tv is not None and yv is not None:
            t.append(tv)
            y.append(yv)
    return np.asarray(t, dtype=float), np.asarray(y, dtype=float)


def _interp(rows: list[dict[str, Any]], key: str, grid: np.ndarray) -> np.ndarray:
    t, y = _series(rows, key)
    if len(t) < 2:
        return np.full_like(grid, np.nan)
    return np.interp(grid, t, y)


def _first_true_time(rows: list[dict[str, Any]], *, onset_s: float, predicate) -> float | None:
    for row in _dedupe_rows(rows):
        t = _finite(row.get("time_s"))
        if t is None or t < onset_s:
            continue
        if predicate(row):
            return t
    return None


def _first_zero_crossing(rows: list[dict[str, Any]], key: str, *, onset_s: float) -> float | None:
    previous = None
    for row in _dedupe_rows(rows):
        t = _finite(row.get("time_s"))
        value = _finite(row.get(key))
        if t is None or value is None or t < onset_s:
            continue
        if previous is not None:
            t0, y0 = previous
            if y0 > 0.0 and value <= 0.0:
                denom = value - y0
                return t if abs(denom) < 1.0e-15 else t0 + (0.0 - y0) * (t - t0) / denom
        previous = (t, value)
    return None


def _slip_duration(rows: list[dict[str, Any]], *, onset_s: float) -> float:
    unique = [row for row in _dedupe_rows(rows) if float(row["time_s"]) >= onset_s]
    total = 0.0
    for left, right in zip(unique, unique[1:]):
        if not bool(left.get("e58_stick_stick")):
            total += float(right["time_s"]) - float(left["time_s"])
    return total


def _comparison_summary(*, case: PairedCase, full: VariantRun, qs: VariantRun, cfg: dict[str, Any]) -> dict[str, Any]:
    full_rows = _dedupe_rows(full.rows)
    qs_rows = _dedupe_rows(qs.rows)
    end = min(float(full_rows[-1]["time_s"]), float(qs_rows[-1]["time_s"]))
    step = float(cfg["comparison_grid_step_s"])
    grid = np.arange(0.0, end + 0.5 * step, step)
    post = grid >= case.onset_s

    pairs = {
        "shift_mm": "shift_mm",
        "ratio": "ratio_secondary_over_primary",
        "primary_rpm": "primary_rpm",
        "secondary_rpm": "secondary_rpm",
        "normal_secondary_N": "normal_secondary_N",
        "secondary_actuator_closing_force_N": "secondary_actuator_closing_force_N",
        "secondary_internal_power_W": "e58_secondary_internal_power_W",
    }
    deltas: dict[str, np.ndarray] = {}
    for label, key in pairs.items():
        deltas[label] = _interp(full_rows, key, grid) - _interp(qs_rows, key, grid)

    def max_abs(name: str) -> float:
        vals = deltas[name][post]
        vals = vals[np.isfinite(vals)]
        return float(np.max(np.abs(vals))) if len(vals) else float("nan")

    full_slip = _first_true_time(
        full_rows,
        onset_s=case.onset_s,
        predicate=lambda r: not bool(r.get("e58_stick_stick")),
    )
    qs_slip = _first_true_time(
        qs_rows,
        onset_s=case.onset_s,
        predicate=lambda r: not bool(r.get("e58_stick_stick")),
    )
    full_helix = _first_zero_crossing(full_rows, "e58_helix_actual_margin_Nm", onset_s=case.onset_s)
    qs_helix = _first_zero_crossing(qs_rows, "e58_helix_actual_margin_Nm", onset_s=case.onset_s)

    def min_field(rows, key):
        vals = [_finite(r.get(key)) for r in rows if float(r["time_s"]) >= case.onset_s]
        vals = [x for x in vals if x is not None]
        return min(vals) if vals else None

    def max_field(rows, key):
        vals = [_finite(r.get(key)) for r in rows if float(r["time_s"]) >= case.onset_s]
        vals = [x for x in vals if x is not None]
        return max(vals) if vals else None

    return {
        "case_id": case.case_id,
        "case_label": case.label,
        "preload_deg": case.preload_deg,
        "restart_shift_percent": case.restart_shift_percent,
        "perturbation_family": case.perturbation_family,
        "perturbation_value": case.perturbation_value,
        "ramp_s": case.ramp_s,
        "onset_s": case.onset_s,
        "full_status": "completed" if full.result.completed else "terminated",
        "qs_status": "completed" if qs.result.completed else "terminated",
        "full_termination_reason": str(full.result.termination_reason),
        "qs_termination_reason": str(qs.result.termination_reason),
        "full_final_time_s": float(full.result.final_time),
        "qs_final_time_s": float(qs.result.final_time),
        "termination_time_qs_minus_full_ms": 1.0e3 * (float(qs.result.final_time) - float(full.result.final_time)),
        "full_first_helix_reversal_s": full_helix,
        "qs_first_helix_reversal_s": qs_helix,
        "full_first_nonstick_s": full_slip,
        "qs_first_nonstick_s": qs_slip,
        "slip_timing_qs_minus_full_ms": (
            None if full_slip is None or qs_slip is None else 1.0e3 * (qs_slip - full_slip)
        ),
        "full_nonstick_duration_s": _slip_duration(full_rows, onset_s=case.onset_s),
        "qs_nonstick_duration_s": _slip_duration(qs_rows, onset_s=case.onset_s),
        "max_abs_shift_difference_mm": max_abs("shift_mm"),
        "max_abs_ratio_difference": max_abs("ratio"),
        "max_abs_primary_rpm_difference": max_abs("primary_rpm"),
        "max_abs_secondary_rpm_difference": max_abs("secondary_rpm"),
        "max_abs_secondary_normal_difference_N": max_abs("normal_secondary_N"),
        "max_abs_secondary_actuator_force_difference_N": max_abs("secondary_actuator_closing_force_N"),
        "max_abs_secondary_internal_power_difference_W": max_abs("secondary_internal_power_W"),
        "full_min_secondary_normal_N": min_field(full_rows, "normal_secondary_N"),
        "qs_min_secondary_normal_N": min_field(qs_rows, "normal_secondary_N"),
        "full_min_actual_helix_margin_Nm": min_field(full_rows, "e58_helix_actual_margin_Nm"),
        "qs_min_actual_helix_margin_Nm": min_field(qs_rows, "e58_helix_actual_margin_Nm"),
        "full_max_traction_utilization": max_field(full_rows, "e58_max_abs_lambda"),
        "qs_max_traction_utilization": max_field(qs_rows, "e58_max_abs_lambda"),
    }


def _plot_pair(case: PairedCase, runs: dict[str, VariantRun], out: Path, cfg: dict[str, Any]) -> None:
    full = runs["full"].rows
    qs = runs["quasi_static_helix"].rows
    labels = {"full": "Full dynamic helix", "quasi_static_helix": "Quasi-static helix"}
    onset_ms = 0.0
    ramp_end_ms = case.ramp_s * 1000.0

    def plot_field(ax, key, ylabel):
        for name, rows in (("full", full), ("quasi_static_helix", qs)):
            t, y = _series(rows, key)
            ax.plot((t - case.onset_s) * 1000.0, y, label=labels[name])
        ax.axvline(onset_ms, linewidth=1.0)
        ax.axvline(ramp_end_ms, linewidth=1.0)
        for name, run in runs.items():
            if not run.result.completed:
                ax.axvline(
                    (float(run.result.final_time) - case.onset_s) * 1000.0,
                    linewidth=1.0,
                    linestyle=":",
                    label=(
                        f"{labels[name]} terminal: {run.result.termination_reason}"
                        if ax is axes[0] else None
                    ),
                )
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25)

    # System trajectory/performance.
    fig, axes = plt.subplots(4, 1, figsize=(10, 10), sharex=True)
    plot_field(axes[0], "shift_mm", "Shift [mm]")
    plot_field(axes[1], "ratio_secondary_over_primary", "Speed ratio $\\omega_s/\\omega_p$")
    plot_field(axes[2], "primary_rpm", "Primary [rpm]")
    plot_field(axes[3], "secondary_rpm", "Secondary [rpm]")
    axes[0].set_title(f"{case.label}: trajectory consequence")
    axes[-1].set_xlabel("Time from perturbation onset [ms]")
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(out / f"{case.case_id}__trajectory_performance.png", dpi=180)
    plt.close(fig)

    # Clamp and traction.
    fig, axes = plt.subplots(4, 1, figsize=(10, 10), sharex=True)
    plot_field(axes[0], "secondary_actuator_closing_force_N", "Secondary actuator [N]")
    plot_field(axes[1], "normal_secondary_N", "$N_s$ [N]")
    for name, rows in (("full", full), ("quasi_static_helix", qs)):
        t, lp = _series(rows, "lambda_primary")
        _, ls = _series(rows, "lambda_secondary")
        if len(t) == len(lp):
            axes[2].plot(t * 1000.0, np.abs(lp), label=f"{labels[name]} $|\\lambda_p|$")
        ts, ls2 = _series(rows, "lambda_secondary")
        axes[2].plot(ts * 1000.0, np.abs(ls2), label=f"{labels[name]} $|\\lambda_s|$")
    axes[2].axhline(float(cfg["static_friction_coefficient"]), linewidth=1.0)
    axes[2].axvline(onset_ms, linewidth=1.0)
    axes[2].axvline(ramp_end_ms, linewidth=1.0)
    axes[2].set_ylabel("Traction utilization")
    axes[2].grid(True, alpha=0.25)
    for name, rows in (("full", full), ("quasi_static_helix", qs)):
        t = np.asarray([float(r["time_s"]) for r in _dedupe_rows(rows)])
        slip = np.asarray([0.0 if bool(r.get("e58_stick_stick")) else 1.0 for r in _dedupe_rows(rows)])
        axes[3].step((t - case.onset_s) * 1000.0, slip, where="post", label=labels[name])
    axes[3].set_yticks([0.0, 1.0], labels=["stick-stick", "non-stick"])
    axes[3].set_xlabel("Time from perturbation onset [ms]")
    axes[3].grid(True, alpha=0.25)
    axes[0].set_title(f"{case.label}: clamp and belt-contact consequence")
    axes[0].legend()
    axes[2].legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(out / f"{case.case_id}__clamp_traction.png", dpi=180)
    plt.close(fig)

    # Helix topology/reaction.
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    plot_field(axes[0], "e58_helix_actual_margin_Nm", "Actual $M_h$ [N m]")
    axes[0].axhline(0.0, linewidth=1.0)
    plot_field(axes[1], "e58_helix_actual_force_N", "Actual helix axial [N]")
    axes[1].axhline(0.0, linewidth=1.0)
    plot_field(axes[2], "e58_helix_physical_dynamic_correction_Nm", "Physical dynamic correction [N m]")
    axes[2].axhline(0.0, linewidth=1.0)
    axes[0].set_title(f"{case.label}: helix-model difference")
    axes[-1].set_xlabel("Time from perturbation onset [ms]")
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(out / f"{case.case_id}__helix_topology.png", dpi=180)
    plt.close(fig)

    # Belt torque/power.
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    plot_field(axes[0], "tau_secondary_belt_Nm", "Secondary belt torque [N m]")
    plot_field(axes[1], "e58_secondary_internal_power_W", "Secondary belt power [W]")
    axes[1].axhline(0.0, linewidth=1.0)
    axes[0].set_title(f"{case.label}: transmitted torque / power")
    axes[-1].set_xlabel("Time from perturbation onset [ms]")
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(out / f"{case.case_id}__belt_power.png", dpi=180)
    plt.close(fig)

    # Direct trajectory deltas on a common clock: full - quasi-static.
    end = min(max(_series(full, "shift_mm")[0]), max(_series(qs, "shift_mm")[0]))
    step = float(cfg["comparison_grid_step_s"])
    grid = np.arange(0.0, end + 0.5 * step, step)
    fig, axes = plt.subplots(4, 1, figsize=(10, 9), sharex=True)
    specs = [
        ("shift_mm", "Full - QS shift [mm]"),
        ("ratio_secondary_over_primary", "Full - QS ratio"),
        ("primary_rpm", "Full - QS primary [rpm]"),
        ("normal_secondary_N", "Full - QS $N_s$ [N]"),
    ]
    for ax, (key, ylabel) in zip(axes, specs):
        delta = _interp(full, key, grid) - _interp(qs, key, grid)
        ax.plot((grid - case.onset_s) * 1000.0, delta)
        ax.axhline(0.0, linewidth=1.0)
        ax.axvline(onset_ms, linewidth=1.0)
        ax.axvline(ramp_end_ms, linewidth=1.0)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25)
    axes[0].set_title(f"{case.label}: direct trajectory divergence")
    axes[-1].set_xlabel("Time from perturbation onset [ms]")
    fig.tight_layout()
    fig.savefig(out / f"{case.case_id}__trajectory_delta.png", dpi=180)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    verify_environment()
    study = json.loads((STUDY_ROOT / "study.json").read_text(encoding="utf-8"))
    cfg = study["experiments"]["paired_helix_performance"]
    _, ab, route = load_tagged_modules()

    _, resolved, _, _, _ = build_reference_components(
        route, duration_s=float(cfg["conditioning_duration_s"])
    )
    base_constants = resolved.constants
    cases = _build_cases(cfg, quick=bool(args.quick))
    out = ARTIFACTS / "paired-helix-performance"
    out.mkdir(parents=True, exist_ok=True)

    contexts: dict[float, dict[str, Any]] = {}
    conditioning_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    # Condition only the two physical preloads actually used by the exemplars.
    for preload in sorted({case.preload_deg for case in cases}):
        constants = replace(
            base_constants,
            secondary_torsional_initial_twist=radians(preload),
        )
        run, result, assembly, engine, road_load, topology = run_flat_slotted_reference_with_constants(
            route=route,
            ab=ab,
            constants=constants,
            duration_s=float(cfg["conditioning_duration_s"]),
            sample_step_s=float(cfg["conditioning_solver"]["sample_step_s"]),
            rtol=float(cfg["conditioning_solver"]["relative_tolerance"]),
            atol=float(cfg["conditioning_solver"]["absolute_tolerance"]),
            max_step_s=float(cfg["conditioning_solver"]["max_step_s"]),
        )
        if run is None:
            raise RuntimeError(
                f"E5.8 conditioning failed at {preload:g} deg: {result.termination_reason}"
            )
        conditioning_rows.append(
            {
                "preload_deg": preload,
                "status": "completed",
                "termination_reason": str(result.termination_reason),
                "topology": str(topology),
            }
        )
        contexts[preload] = {
            "constants": constants,
            "assembly": assembly,
            "engine": engine,
            "road_load": road_load,
            "run": run,
        }

    variants = {
        "full": _variant(ab, "full"),
        "quasi_static_helix": _variant(ab, "quasi_static_helix"),
    }

    for case in cases:
        context = contexts[case.preload_deg]
        restart = select_restart(
            context["run"],
            case.restart_shift_percent,
            maximum_error_percent=float(cfg["restart_maximum_error_percent"]),
        )
        print(
            f"E5.8 {case.case_id}: common restart {restart.actual_shift_percent:.4f}% "
            f"at conditioning t={restart.time_s:.6f} s"
        )
        runs: dict[str, VariantRun] = {}
        for key, variant in variants.items():
            run = _run_variant_case(
                case=case,
                restart=restart,
                route=route,
                ab=ab,
                full_assembly=context["assembly"],
                engine=context["engine"],
                road_load=context["road_load"],
                constants=context["constants"],
                variant=variant,
                solver=cfg["solver"],
            )
            runs[key] = run
            trace_rows.extend(run.rows)
            status = "completed" if run.result.completed else f"terminated:{run.result.termination_reason}"
            print(
                f"  {variant.label}: {status}, t_end={run.result.final_time:.6f} s, "
                f"transitions={len(run.result.segments)-1}, "
                f"min M_h={min(float(r['e58_helix_actual_margin_Nm']) for r in run.rows if _finite(r.get('e58_helix_actual_margin_Nm')) is not None):.4f} N m"
            )

        summary_rows.append(
            _comparison_summary(
                case=case,
                full=runs["full"],
                qs=runs["quasi_static_helix"],
                cfg=cfg,
            )
        )
        _plot_pair(case, runs, out, cfg)

    write_rows(out / "conditioning.csv", conditioning_rows)
    write_rows(out / "case_comparison_summary.csv", summary_rows)
    write_rows(out / "paired_trace.csv", trace_rows)

    summary = {
        "stage": "E5.8",
        "comparison": "full_dynamic_slotted_helix_vs_quasi_static_slotted_helix",
        "reruns_cinder": True,
        "common_initial_state": True,
        "comparator_definition": (
            "Tagged CINDER quasi_static_helix ablation: removes helix movable-member "
            "dynamic coupling while returning movable-sheave rotational inertia to "
            "the classical rigid secondary shaft inertia."
        ),
        "important_boundary": (
            "This is not true unilateral detachment. Both variants retain theta=theta(s) "
            "and signed/slotted helix support."
        ),
        "cases": summary_rows,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    readme = [
        "# E5.8 paired helix performance comparison",
        "",
        "Same initial state and same transient boundary are integrated under the full dynamic and tagged quasi-static helix formulations.",
        "",
        "Primary outputs:",
        "- `case_comparison_summary.csv`: quantitative trajectory/performance divergence.",
        "- `paired_trace.csv`: all sampled rows from both variants.",
        "- `*__trajectory_performance.png`: shift, ratio and shaft-speed histories.",
        "- `*__clamp_traction.png`: actuator force, normal force and belt contact state.",
        "- `*__helix_topology.png`: actual helix reaction and dynamic correction.",
        "- `*__belt_power.png`: secondary belt torque and internal power.",
        "- `*__trajectory_delta.png`: direct full-minus-QS trajectory divergence over their common valid interval.",
        "",
        "If a formulation reaches `contact_loss_normal_resultant_floor`, E5.8 treats that as a physical terminal outcome and retains its pre-termination trajectory. A shorter admissible trajectory is therefore itself part of the performance comparison.",
        "",
        "Interpretation boundary: this compares two slotted/constrained helix formulations. It is not a detached one-flank topology model.",
    ]
    (out / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    print(f"E5.8 artifacts written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
