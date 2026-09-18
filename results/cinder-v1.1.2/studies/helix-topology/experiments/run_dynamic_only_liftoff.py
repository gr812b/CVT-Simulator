"""E5.5: isolate dynamic-only helix lift-off under forward power flow.

E5 showed that the retained movable-member inertia can flip the selected helix
flank even while the trajectory-frozen torque+spring diagnostic remains
positive, but every vehicle crossing found there occurred after belt traction
had already entered slip.  This stage searches deliberately for the stronger
mechanism-isolation condition

    P_belt,s > 0,
    belt contact = stick-stick,
    M_h,QS > 0,
    M_h < 0,

away from a travel-stop impact.

The study varies secondary torsional preload and transient severity.  Each
preload is fully reconditioned from launch before restart states are selected;
preload therefore changes clamp, shift history, and belt contact consistently
rather than acting as an algebraic post-processing offset.
"""
from __future__ import annotations

# --- results study-local import bootstrap ---
from pathlib import Path as _ResultsPath
import sys as _results_sys

_results_file = _ResultsPath(__file__).resolve()
_results_study_root = next(
    (parent for parent in _results_file.parents if (parent / "study.json").is_file()),
    None,
)
if _results_study_root is None:
    raise RuntimeError(f"Could not locate study root for {_results_file}")
_results_release_root = _results_study_root.parents[1]
for _results_path in (str(_results_study_root), str(_results_release_root)):
    while _results_path in _results_sys.path:
        _results_sys.path.remove(_results_path)
_results_sys.path.insert(0, str(_results_release_root))
_results_sys.path.insert(0, str(_results_study_root))
# --- end results study-local import bootstrap ---


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

from infrastructure.metrics import contact_topology_metrics, deduplicate_by_time  # noqa: E402
from infrastructure.study_support import (  # noqa: E402
    ARTIFACTS,
    AddedTorqueBoundary,
    BlendTorqueScaleBoundary,
    SmoothStep,
    build_reference_components,
    flat_programme,
    load_study_modules,
    run_custom_restart_case,
    run_flat_slotted_reference_with_constants,
    select_restart,
    verify_environment,
    write_reference_provenance,
    write_rows,
)
try:
    import run_liftoff_envelope as e5  # type: ignore  # noqa: E402
except ModuleNotFoundError:  # package import in tests
    from experiments import run_liftoff_envelope as e5  # type: ignore  # noqa: E402


@dataclass(frozen=True, slots=True)
class Perturbation:
    family: str
    value: float
    label: str
    role: str


@dataclass(frozen=True, slots=True)
class Case:
    preload_deg: float
    restart_key: str
    perturbation: Perturbation
    ramp_s: float
    phase: str

    @property
    def case_id(self) -> str:
        preload = str(int(round(self.preload_deg))).zfill(3)
        ramp = str(int(round(1000.0 * self.ramp_s))).zfill(3)
        value = f"{abs(self.perturbation.value):05.2f}".replace(".", "p")
        sign = "m" if self.perturbation.value < 0.0 else "p"
        return (
            f"E55_p{preload}_{self.restart_key}_{self.perturbation.family}_"
            f"{sign}{value}_r{ramp}_{self.phase}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Small plumbing check; not suitable for scientific interpretation.",
    )
    return parser.parse_args()


def _finite(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _minimum(rows: list[dict[str, Any]], key: str) -> float | None:
    xs = [_finite(row.get(key)) for row in rows]
    finite = [x for x in xs if x is not None]
    return min(finite) if finite else None


def _maximum_abs(rows: list[dict[str, Any]], key: str) -> float | None:
    xs = [_finite(row.get(key)) for row in rows]
    finite = [abs(x) for x in xs if x is not None]
    return max(finite) if finite else None


def _is_stick_stick(mode: Any) -> bool:
    text = str(mode).lower()
    return "stick_stick" in text and "cvtshiftconstraint.free" in text


def _interp(row0: dict[str, Any], row1: dict[str, Any], key: str, w: float) -> float | None:
    a = _finite(row0.get(key))
    b = _finite(row1.get(key))
    if a is None or b is None:
        return None
    return float(a + w * (b - a))


def first_full_crossing(rows: list[dict[str, Any]], *, onset_s: float) -> dict[str, Any] | None:
    """Return linearly interpolated metadata at the first + -> - full-M_h crossing."""

    unique = [
        row for row in deduplicate_by_time(rows)
        if (_finite(row.get("time_s")) is not None and float(row["time_s"]) >= onset_s)
    ]
    numeric_keys = (
        "helix_quasi_static_margin_Nm",
        "helix_dynamic_correction_Nm",
        "helix_secondary_internal_power_W",
        "lambda_primary",
        "lambda_secondary",
        "shift_m",
        "shift_speed_m_s",
        "helix_shift_acceleration_m_s2",
        "helix_secondary_angular_acceleration_rad_s2",
        "helix_belt_reaction_torque_Nm",
        "helix_torsional_spring_torque_Nm",
        "helix_shaft_accel_reaction_torque_Nm",
        "helix_shift_accel_reaction_torque_Nm",
        "helix_curvature_reaction_torque_Nm",
        "tau_secondary_belt_Nm",
        "primary_external_torque_Nm",
        "secondary_external_torque_Nm",
        "primary_rpm",
        "secondary_rpm",
        "normal_primary_N",
        "normal_secondary_N",
    )
    for left, right in zip(unique, unique[1:]):
        t0 = _finite(left.get("time_s"))
        t1 = _finite(right.get("time_s"))
        y0 = _finite(left.get("helix_reacted_torque_margin_Nm"))
        y1 = _finite(right.get("helix_reacted_torque_margin_Nm"))
        if None in (t0, t1, y0, y1) or t1 <= t0:
            continue
        if not (y0 >= 0.0 and y1 < 0.0):
            continue
        denom = y0 - y1
        w = 0.0 if denom == 0.0 else y0 / denom
        w = min(1.0, max(0.0, float(w)))
        out: dict[str, Any] = {
            "crossing_time_s": float(t0 + w * (t1 - t0)),
            "crossing_full_margin_Nm": 0.0,
            "crossing_mode_left": str(left.get("cvt_mode", "")),
            "crossing_mode_right": str(right.get("cvt_mode", "")),
            "crossing_stick_stick": bool(
                _is_stick_stick(left.get("cvt_mode"))
                and _is_stick_stick(right.get("cvt_mode"))
            ),
        }
        for key in numeric_keys:
            out[f"crossing_{key}"] = _interp(left, right, key, w)
        return out
    return None


def classify_crossing(
    crossing: dict[str, Any] | None,
    *,
    run,
    onset_s: float,
    geometry_spec,
    qs_guard_Nm: float,
    friction_guard: float,
    interior_guard_percent: float,
) -> dict[str, Any]:
    if crossing is None:
        return {
            "dynamic_only_at_crossing": False,
            "forward_power_at_crossing": False,
            "no_prior_hybrid_transition": False,
            "interior_at_crossing": False,
            "clean_forward_stick_dynamic_only_crossing": False,
        }

    t = float(crossing["crossing_time_s"])
    qs = _finite(crossing.get("crossing_helix_quasi_static_margin_Nm"))
    power = _finite(crossing.get("crossing_helix_secondary_internal_power_W"))
    lp = _finite(crossing.get("crossing_lambda_primary"))
    ls = _finite(crossing.get("crossing_lambda_secondary"))
    shift = _finite(crossing.get("crossing_shift_m"))

    transitions = [
        record for record in run.result.transitions
        if onset_s - 1.0e-12 <= float(record.time) <= t + 1.0e-12
    ]
    no_prior = len(transitions) == 0

    interior = False
    shift_percent = None
    if shift is not None:
        span = geometry_spec.max_shift - geometry_spec.deadzone_shift
        if span > 0.0:
            shift_percent = 100.0 * (shift - geometry_spec.deadzone_shift) / span
            interior = (
                interior_guard_percent
                < shift_percent
                < 100.0 - interior_guard_percent
            )
    crossing["crossing_shift_percent"] = shift_percent
    crossing["transitions_before_or_at_crossing"] = len(transitions)

    dynamic_only = bool(qs is not None and qs > qs_guard_Nm)
    forward_power = bool(power is not None and power > 0.0)
    friction_ok = bool(
        lp is not None and ls is not None
        and abs(lp) < friction_guard
        and abs(ls) < friction_guard
    )
    stick = bool(crossing.get("crossing_stick_stick"))
    clean = bool(dynamic_only and forward_power and friction_ok and stick and no_prior and interior)
    return {
        "dynamic_only_at_crossing": dynamic_only,
        "forward_power_at_crossing": forward_power,
        "friction_guard_at_crossing": friction_ok,
        "no_prior_hybrid_transition": no_prior,
        "interior_at_crossing": interior,
        "clean_forward_stick_dynamic_only_crossing": clean,
    }


def conditioning_summary(*, preload_deg: float, run, result) -> dict[str, Any]:
    if run is None:
        return {
            "preload_deg": preload_deg,
            "status": "integration_failed",
            "termination_reason": str(result.termination_reason),
        }
    rows = [sample.row for sample in run.samples]
    e5._augment_qs(rows)
    resolved = [row for row in rows if _finite(row.get("helix_reacted_torque_margin_Nm")) is not None]
    modes = [str(row.get("cvt_mode", "")) for row in resolved]
    return {
        "preload_deg": preload_deg,
        "status": "completed",
        "minimum_full_margin_Nm": _minimum(resolved, "helix_reacted_torque_margin_Nm"),
        "minimum_qs_margin_Nm": _minimum(resolved, "helix_quasi_static_margin_Nm"),
        "minimum_dynamic_correction_Nm": _minimum(resolved, "helix_dynamic_correction_Nm"),
        "maximum_abs_lambda_primary": _maximum_abs(resolved, "lambda_primary"),
        "maximum_abs_lambda_secondary": _maximum_abs(resolved, "lambda_secondary"),
        "all_resolved_stick_stick": bool(modes and all(_is_stick_stick(mode) for mode in modes)),
        "opposite_flank_required_during_conditioning": bool(
            (_minimum(resolved, "helix_reacted_torque_margin_Nm") or 0.0) < 0.0
        ),
        "quasi_static_liftoff_during_conditioning": bool(
            (_minimum(resolved, "helix_quasi_static_margin_Nm") or 0.0) < 0.0
        ),
        "hybrid_transition_count": len(result.transitions),
    }


def make_perturbations(cfg: dict[str, Any]) -> list[Perturbation]:
    out: list[Perturbation] = []
    for value in cfg["throttle_drop_scales"]:
        out.append(Perturbation("throttle_drop", float(value), f"engine torque scale -> {value:g}", "target"))
    for value in cfg["secondary_load_steps_Nm"]:
        out.append(Perturbation("output_load_step", float(value), f"secondary added torque {value:+g} N m", "target"))
    for value in cfg["throttle_raise_scales"]:
        out.append(Perturbation("throttle_raise", float(value), f"engine torque scale -> {value:g}", "sign_control"))
    for value in cfg["secondary_assist_steps_Nm"]:
        out.append(Perturbation("output_assist", float(value), f"secondary added torque {value:+g} N m", "sign_control"))
    return out


def evaluate_case(
    *,
    case: Case,
    restart,
    route,
    ab,
    assembly,
    engine,
    road_load,
    constants,
    cfg,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from cinder.model.boundaries.shaft import FullThrottleEngineBoundary

    onset_s = float(cfg["onset_s"])
    hold_s = float(cfg["hold_s"])
    duration_s = onset_s + case.ramp_s + hold_s
    programme = flat_programme(route, duration_s)
    primary_boundary = None
    secondary_boundary = None

    if case.perturbation.family in {"throttle_drop", "throttle_raise"}:
        base = FullThrottleEngineBoundary(
            engine,
            equivalent_rotational_inertia=constants.engine_rotational_inertia,
        )
        primary_boundary = BlendTorqueScaleBoundary(
            base,
            onset_s=onset_s,
            ramp_s=case.ramp_s,
            target_scale=case.perturbation.value,
            label=case.perturbation.family,
        )
    elif case.perturbation.family in {"output_load_step", "output_assist"}:
        base = route.TimeProgrammedLockedFinalDriveBoundary(
            road_load=road_load,
            programme=programme,
            direct_secondary_shaft_inertia=constants.gearbox_input_rotational_inertia,
        )
        signal = SmoothStep(
            onset_s=onset_s,
            ramp_s=case.ramp_s,
            target=case.perturbation.value,
        )
        secondary_boundary = AddedTorqueBoundary(
            base,
            signal,
            label=case.perturbation.family,
        )
    else:  # pragma: no cover
        raise ValueError(case.perturbation.family)

    solver = cfg["solver"]
    max_step = max(
        float(solver["minimum_max_step_s"]),
        min(float(solver["maximum_step_cap_s"]), case.ramp_s / float(solver["ramp_step_divisor"])),
    )
    run, result, _ = run_custom_restart_case(
        route=route,
        ab=ab,
        restart=restart,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        duration_s=duration_s,
        sample_step_s=float(solver["sample_step_s"]),
        rtol=float(solver["relative_tolerance"]),
        atol=float(solver["absolute_tolerance"]),
        max_step_s=max_step,
        primary_boundary=primary_boundary,
        secondary_boundary=secondary_boundary,
        reclassify_initial_mode=False,
    )
    base_summary = {
        "case_id": case.case_id,
        "phase": case.phase,
        "status": "completed" if run is not None else "integration_failed",
        "preload_deg": case.preload_deg,
        "restart_key": case.restart_key,
        "restart_target_shift_percent": restart.target_shift_percent,
        "restart_actual_shift_percent": restart.actual_shift_percent,
        "perturbation_family": case.perturbation.family,
        "perturbation_value": case.perturbation.value,
        "perturbation_label": case.perturbation.label,
        "perturbation_role": case.perturbation.role,
        "ramp_s": case.ramp_s,
        "onset_s": onset_s,
        "duration_s": duration_s,
    }
    if run is None:
        base_summary["termination_reason"] = str(result.termination_reason)
        return base_summary, []

    rows = [sample.row for sample in run.samples]
    e5._augment_qs(rows)
    for row in rows:
        row.update(
            {
                "e55_case_id": case.case_id,
                "e55_phase": case.phase,
                "e55_preload_deg": case.preload_deg,
                "e55_restart_key": case.restart_key,
                "e55_perturbation_family": case.perturbation.family,
                "e55_perturbation_value": case.perturbation.value,
                "e55_ramp_s": case.ramp_s,
            }
        )
    post = [
        row for row in rows
        if (_finite(row.get("time_s")) is not None and float(row["time_s"]) >= onset_s)
    ]
    novelty = e5._novelty_metrics(post, start_s=onset_s, end_s=duration_s)
    topology = contact_topology_metrics(post, case_start_s=onset_s, case_end_s=duration_s)
    crossing = first_full_crossing(rows, onset_s=onset_s)
    crossing_class = classify_crossing(
        crossing,
        run=run,
        onset_s=onset_s,
        geometry_spec=run.system.cvt.model.geometry.spec,
        qs_guard_Nm=float(cfg["success_criteria"]["minimum_qs_margin_at_crossing_Nm"]),
        friction_guard=float(cfg["success_criteria"]["lambda_guard"]),
        interior_guard_percent=float(cfg["success_criteria"]["interior_shift_guard_percent"]),
    )
    transitions_after = [r for r in result.transitions if float(r.time) >= onset_s]
    modes = [
        str(row.get("cvt_mode", ""))
        for row in post
        if _finite(row.get("helix_reacted_torque_margin_Nm")) is not None
    ]
    summary = {
        **base_summary,
        "termination_reason": str(result.termination_reason),
        "transition_count_after_onset": len(transitions_after),
        "all_resolved_stick_stick": bool(modes and all(_is_stick_stick(mode) for mode in modes)),
        "maximum_abs_lambda_primary": _maximum_abs(post, "lambda_primary"),
        "maximum_abs_lambda_secondary": _maximum_abs(post, "lambda_secondary"),
        "minimum_internal_secondary_power_W": _minimum(post, "helix_secondary_internal_power_W"),
        "minimum_shift_accel_term_Nm": _minimum(post, "helix_shift_accel_reaction_torque_Nm"),
        "minimum_shaft_accel_term_Nm": _minimum(post, "helix_shaft_accel_reaction_torque_Nm"),
        "minimum_curvature_term_Nm": _minimum(post, "helix_curvature_reaction_torque_Nm"),
        **topology,
        **novelty,
        **crossing_class,
    }
    if crossing:
        summary.update(crossing)
    summary["gold_case"] = bool(
        summary.get("clean_forward_stick_dynamic_only_crossing")
        and summary.get("strict_dynamic_only_case")
    )
    return summary, rows


def candidate_score(row: dict[str, Any]) -> tuple:
    """Lower tuple is more interesting for refinement."""
    role = 0 if row.get("perturbation_role") == "target" else 1
    full = _finite(row.get("minimum_full_margin_Nm"))
    dyn = _finite(row.get("minimum_dynamic_correction_Nm"))
    full_score = full if full is not None else 1.0e9
    dyn_score = dyn if dyn is not None else 1.0e9
    return role, full_score, dyn_score


def make_plots(out: Path, rows: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> None:
    completed = [r for r in rows if r.get("status") == "completed"]
    if completed:
        fig, ax = plt.subplots(figsize=(8.0, 6.0))
        for preload in sorted({float(r["preload_deg"]) for r in completed}):
            subset = [r for r in completed if float(r["preload_deg"]) == preload]
            ax.scatter(
                [r.get("minimum_qs_margin_Nm", np.nan) for r in subset],
                [r.get("minimum_full_margin_Nm", np.nan) for r in subset],
                label=f"{preload:.0f}° preload",
                s=22,
            )
        ax.axhline(0.0, linewidth=1.0)
        ax.axvline(0.0, linewidth=1.0)
        lim = [*ax.get_xlim(), *ax.get_ylim()]
        lo, hi = min(lim), max(lim)
        ax.plot([lo, hi], [lo, hi], linestyle="--", linewidth=0.8)
        ax.set_xlabel("Minimum torque + spring margin M_h,QS [N m]")
        ax.set_ylabel("Minimum full dynamic margin M_h [N m]")
        ax.set_title("Dynamic-only lift-off search by torsional preload")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out / "full_vs_qs_by_preload.png", dpi=170)
        plt.close(fig)

    target = [r for r in completed if r.get("perturbation_role") == "target"]
    if target:
        fig, ax = plt.subplots(figsize=(9.0, 5.5))
        for family in sorted({str(r["perturbation_family"]) for r in target}):
            subset = [r for r in target if r["perturbation_family"] == family and r["phase"] == "coarse"]
            if not subset:
                continue
            grouped = {}
            for row in subset:
                grouped.setdefault(float(row["preload_deg"]), []).append(row)
            xs, ys = [], []
            for preload, group in sorted(grouped.items()):
                finite = [_finite(r.get("minimum_full_margin_Nm")) for r in group]
                finite = [x for x in finite if x is not None]
                if finite:
                    xs.append(preload)
                    ys.append(min(finite))
            if xs:
                ax.plot(xs, ys, marker="o", label=family)
        ax.axhline(0.0, linewidth=1.0)
        ax.set_xlabel("Secondary torsional preload [deg]")
        ax.set_ylabel("Lowest coarse full-dynamic margin [N m]")
        ax.set_title("How lowering preload moves the dynamic lift-off reserve")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out / "margin_vs_preload.png", dpi=170)
        plt.close(fig)

    gold = [r for r in candidates if r.get("gold_case")]
    best = gold[0] if gold else (candidates[0] if candidates else None)
    if best is not None:
        siblings = [
            r for r in completed
            if r.get("preload_deg") == best.get("preload_deg")
            and r.get("restart_key") == best.get("restart_key")
            and r.get("perturbation_family") == best.get("perturbation_family")
            and r.get("perturbation_value") == best.get("perturbation_value")
        ]
        siblings.sort(key=lambda r: float(r["ramp_s"]))
        if siblings:
            fig, ax = plt.subplots(figsize=(8.0, 5.0))
            ax.plot(
                [1000.0 * float(r["ramp_s"]) for r in siblings],
                [r.get("minimum_full_margin_Nm", np.nan) for r in siblings],
                marker="o",
                label="full dynamic",
            )
            ax.plot(
                [1000.0 * float(r["ramp_s"]) for r in siblings],
                [r.get("minimum_qs_margin_Nm", np.nan) for r in siblings],
                marker="o",
                label="torque + spring",
            )
            ax.axhline(0.0, linewidth=1.0)
            ax.set_xlabel("Transient ramp duration [ms]")
            ax.set_ylabel("Minimum helix margin [N m]")
            ax.set_title(f"Ramp-rate sensitivity of {best['case_id']}")
            ax.legend()
            fig.tight_layout()
            fig.savefig(out / "best_candidate_ramp_sensitivity.png", dpi=170)
            plt.close(fig)


def main() -> int:
    args = parse_args()
    verify_environment()
    study = json.loads((STUDY_ROOT / "study.json").read_text(encoding="utf-8"))
    cfg = study["experiments"]["dynamic_only_liftoff"]

    _, ab, route = load_study_modules()
    _, resolved, _, _, _ = build_reference_components(
        route, duration_s=float(cfg["conditioning_duration_s"])
    )
    base_constants = resolved.constants

    if args.quick:
        preloads = [300.0, 240.0]
        restart_targets = [50.0]
        coarse_ramp = 0.05
        perturbations = [
            Perturbation("throttle_drop", 0.0, "engine torque scale -> 0", "target"),
            Perturbation("output_load_step", -20.0, "secondary added torque -20 N m", "target"),
        ]
        refinement_ramps = [0.01, 0.05]
        max_refine_per_restart = 1
    else:
        preloads = [float(x) for x in cfg["preload_degrees"]]
        restart_targets = [float(x) for x in cfg["restart_shift_percents"]]
        coarse_ramp = float(cfg["coarse_ramp_s"])
        perturbations = make_perturbations(cfg["perturbations"])
        refinement_ramps = [float(x) for x in cfg["refinement_ramp_times_s"]]
        max_refine_per_restart = int(cfg["maximum_refinement_perturbations_per_preload_restart"])

    out = ARTIFACTS / "dynamic-only-liftoff"
    out.mkdir(parents=True, exist_ok=True)

    conditioning_rows: list[dict[str, Any]] = []
    restart_rows: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    retained_trace: list[dict[str, Any]] = []
    crossing_rows: list[dict[str, Any]] = []
    preload_context: dict[float, dict[str, Any]] = {}

    for preload_deg in preloads:
        constants = replace(
            base_constants,
            secondary_torsional_initial_twist=radians(preload_deg),
        )
        outcome = run_flat_slotted_reference_with_constants(
            route=route,
            ab=ab,
            constants=constants,
            duration_s=float(cfg["conditioning_duration_s"]),
            sample_step_s=float(cfg["conditioning_solver"]["sample_step_s"]),
            rtol=float(cfg["conditioning_solver"]["relative_tolerance"]),
            atol=float(cfg["conditioning_solver"]["absolute_tolerance"]),
            max_step_s=float(cfg["conditioning_solver"]["max_step_s"]),
        )
        run, result, assembly, engine, road_load, topology = outcome
        csum = conditioning_summary(preload_deg=preload_deg, run=run, result=result)
        conditioning_rows.append(csum)
        print(
            f"preload {preload_deg:.0f} deg conditioning: {csum['status']}, "
            f"full={csum.get('minimum_full_margin_Nm')}, QS={csum.get('minimum_qs_margin_Nm')}"
        )
        if run is None:
            continue

        restarts = {}
        for target in restart_targets:
            key = f"s{int(round(target)):02d}"
            try:
                restart = select_restart(
                    run,
                    target,
                    maximum_error_percent=float(cfg["restart_maximum_error_percent"]),
                )
            except RuntimeError as exc:
                restart_rows.append(
                    {
                        "preload_deg": preload_deg,
                        "restart_key": key,
                        "target_shift_percent": target,
                        "status": "unavailable",
                        "detail": str(exc),
                    }
                )
                continue
            restarts[key] = restart
            restart_rows.append(
                {
                    "preload_deg": preload_deg,
                    "restart_key": key,
                    "target_shift_percent": target,
                    "actual_shift_percent": restart.actual_shift_percent,
                    "conditioning_time_s": restart.time_s,
                    "baseline_margin_Nm": restart.baseline_margin_Nm,
                    "status": "available",
                }
            )

        preload_context[preload_deg] = {
            "constants": constants,
            "run": run,
            "assembly": assembly,
            "engine": engine,
            "road_load": road_load,
            "topology": topology,
            "restarts": restarts,
        }

    cache: dict[tuple, tuple[dict[str, Any], list[dict[str, Any]]]] = {}

    def run_case(case: Case):
        key = (
            case.preload_deg,
            case.restart_key,
            case.perturbation.family,
            case.perturbation.value,
            case.ramp_s,
        )
        if key in cache:
            return cache[key]
        ctx = preload_context[case.preload_deg]
        summary, rows = evaluate_case(
            case=case,
            restart=ctx["restarts"][case.restart_key],
            route=route,
            ab=ab,
            assembly=ctx["assembly"],
            engine=ctx["engine"],
            road_load=ctx["road_load"],
            constants=ctx["constants"],
            cfg=cfg,
        )
        cache[key] = (summary, rows)
        all_rows.append(summary)
        if summary.get("crossing_time_s") is not None:
            crossing_rows.append({k: v for k, v in summary.items() if k.startswith("crossing_") or k in {
                "case_id", "preload_deg", "restart_key", "perturbation_family",
                "perturbation_value", "ramp_s", "gold_case",
                "clean_forward_stick_dynamic_only_crossing",
            }})
        keep = bool(
            summary.get("gold_case")
            or summary.get("clean_forward_stick_dynamic_only_crossing")
            or (
                summary.get("status") == "completed"
                and _finite(summary.get("minimum_full_margin_Nm")) is not None
                and float(summary["minimum_full_margin_Nm"]) <= float(cfg["trace_retention_margin_Nm"])
            )
        )
        if keep:
            retained_trace.extend(rows)
        print(
            f"{case.case_id}: full={summary.get('minimum_full_margin_Nm')}, "
            f"QS={summary.get('minimum_qs_margin_Nm')}, "
            f"Pcross={summary.get('crossing_helix_secondary_internal_power_W')}, "
            f"clean={summary.get('clean_forward_stick_dynamic_only_crossing')}"
        )
        return summary, rows

    # Coarse screen at one transition rate.
    coarse_by_group: dict[tuple[float, str], list[dict[str, Any]]] = {}
    for preload_deg, ctx in preload_context.items():
        csum = next(r for r in conditioning_rows if r["preload_deg"] == preload_deg)
        # If the unperturbed conditioning trajectory is already quasi-statically
        # inadmissible, this preload cannot isolate a dynamic-only mechanism.
        if csum.get("quasi_static_liftoff_during_conditioning"):
            continue
        for restart_key in ctx["restarts"]:
            group = []
            for perturbation in perturbations:
                case = Case(preload_deg, restart_key, perturbation, coarse_ramp, "coarse")
                summary, _ = run_case(case)
                group.append(summary)
            coarse_by_group[(preload_deg, restart_key)] = group

    # Select only the most informative perturbations per preload/restart for a
    # dense ramp-rate sweep.
    refine_specs: list[tuple[float, str, Perturbation]] = []
    full_upper = float(cfg["refinement_selection"]["full_margin_upper_Nm"])
    dyn_upper = float(cfg["refinement_selection"]["dynamic_correction_upper_Nm"])
    qs_min = float(cfg["refinement_selection"]["minimum_qs_margin_Nm"])
    for (preload_deg, restart_key), group in coarse_by_group.items():
        eligible = []
        for row in group:
            if row.get("status") != "completed":
                continue
            full = _finite(row.get("minimum_full_margin_Nm"))
            qs = _finite(row.get("minimum_qs_margin_Nm"))
            dyn = _finite(row.get("minimum_dynamic_correction_Nm"))
            if None in (full, qs, dyn) or qs <= qs_min:
                continue
            if full <= full_upper or dyn <= dyn_upper or row.get("clean_forward_stick_dynamic_only_crossing"):
                eligible.append(row)
        eligible.sort(key=candidate_score)
        seen = set()
        for row in eligible:
            spec = (str(row["perturbation_family"]), float(row["perturbation_value"]))
            if spec in seen:
                continue
            seen.add(spec)
            perturbation = next(
                p for p in perturbations
                if p.family == spec[0] and abs(p.value - spec[1]) <= 1.0e-12
            )
            refine_specs.append((preload_deg, restart_key, perturbation))
            if len(seen) >= max_refine_per_restart:
                break

    for preload_deg, restart_key, perturbation in refine_specs:
        for ramp_s in refinement_ramps:
            case = Case(preload_deg, restart_key, perturbation, ramp_s, "ramp_refinement")
            run_case(case)

    completed = [row for row in all_rows if row.get("status") == "completed"]
    gold = [row for row in completed if row.get("gold_case")]
    clean_local = [
        row for row in completed
        if row.get("clean_forward_stick_dynamic_only_crossing")
    ]
    dynamic_only = [
        row for row in completed
        if row.get("dynamic_only_at_crossing")
    ]
    forward_dynamic_only = [
        row for row in dynamic_only
        if row.get("forward_power_at_crossing")
    ]
    gold.sort(
        key=lambda row: (
            -float(row.get("crossing_helix_quasi_static_margin_Nm") or 0.0),
            float(row.get("minimum_full_margin_Nm") or 0.0),
        )
    )
    candidate_catalog = gold or clean_local or forward_dynamic_only or sorted(
        completed,
        key=lambda row: (
            abs(float(row.get("minimum_full_margin_Nm") or 1.0e9)),
            float(row.get("minimum_qs_margin_Nm") or 1.0e9),
        ),
    )[:20]

    write_rows(out / "conditioning_by_preload.csv", conditioning_rows)
    write_rows(out / "restart_states.csv", restart_rows)
    write_rows(out / "case_summary.csv", all_rows)
    write_rows(out / "first_crossings.csv", crossing_rows)
    write_rows(out / "candidate_catalog.csv", candidate_catalog)
    write_rows(out / "retained_trace.csv", retained_trace)
    make_plots(out, all_rows, candidate_catalog)

    summary = {
        "stage": "E5.5",
        "quick": bool(args.quick),
        "preloads_deg": preloads,
        "conditioning_completed": sum(r.get("status") == "completed" for r in conditioning_rows),
        "case_count": len(all_rows),
        "completed_case_count": len(completed),
        "integration_failed_case_count": sum(r.get("status") != "completed" for r in all_rows),
        "dynamic_only_first_crossing_count": len(dynamic_only),
        "forward_power_dynamic_only_first_crossing_count": len(forward_dynamic_only),
        "clean_forward_stick_dynamic_only_crossing_count": len(clean_local),
        "gold_case_count": len(gold),
        "gold_case_ids": [row["case_id"] for row in gold],
        "candidate_case_ids": [row["case_id"] for row in candidate_catalog[:20]],
        "success_definition": cfg["success_definition"],
        "interpretation_guardrail": (
            "A gold case isolates a dynamic helix flank-admissibility change in this model. "
            "It does not by itself establish literature priority or experimental occurrence."
        ),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    first_ctx = next(iter(preload_context.values()), None)
    if first_ctx is not None:
        write_reference_provenance(
            out,
            plant=first_ctx["run"].system.cvt.model,
            extra={
                "stage": "E5.5",
                "preloads_deg": preloads,
                "fully_reconditioned_per_preload": True,
                "success_definition": cfg["success_definition"],
            },
        )

    print(json.dumps(summary, indent=2))
    print(f"Wrote E5.5 dynamic-only lift-off artifacts to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
