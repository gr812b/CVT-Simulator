"""E5: targeted helix lift-off envelope and dynamic-novelty refinement.

E1-E4 established two useful mechanisms:

* reverse-power-flow / engine-braking can drive the selected-flank margin M_h
  through zero in a vehicle-like transient;
* movable-member inertia can make M_h negative even while the torque+spring
  quasi-static margin remains positive.

This stage stops broad discovery and maps those mechanisms deliberately.  It
answers three questions:

1. Across naturally reached ratios and downhill grades, what primary braking
   torque is required for M_h=0?
2. Does that threshold lie inside the magnitude of the reference engine's
   configured braking envelope, or only in an exploratory extension?
3. Can the full dynamic helix produce a clean selected-flank lift-off while
   M_h,QS remains positive, i.e. a condition the quasi-static helix diagnostic
   would miss on the same trajectory?

The slotted topology remains active.  No detached unilateral mechanics are
introduced here.
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
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY_ROOT = HERE.parent
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from infrastructure.metrics import (  # noqa: E402
    contact_topology_metrics,
    deduplicate_by_time,
    first_negative_entry_with_companion,
    integrate_negative_part,
    integrate_sign_partition,
)
from infrastructure.study_support import (  # noqa: E402
    ARTIFACTS,
    BlendToTorqueBoundary,
    PrescribedTorqueBoundary,
    Restart,
    load_json,
    run_custom_restart_case,
    run_flat_slotted_reference,
    select_dynamic_restart,
    select_restart,
    transient_grade_programme,
    verify_environment,
    write_reference_provenance,
    write_rows,
)
import run_scenario_discovery as e4  # noqa: E402


@dataclass(frozen=True, slots=True)
class VehiclePoint:
    restart_key: str
    grade_deg: float
    primary_target_torque_Nm: float
    ramp_s: float
    phase: str

    @property
    def case_id(self) -> str:
        grade = str(abs(int(round(self.grade_deg)))).zfill(2)
        brake = f"{abs(self.primary_target_torque_Nm):05.2f}".replace(".", "p")
        ramp_ms = str(int(round(1000.0 * self.ramp_s))).zfill(3)
        phase = self.phase.replace("trajectory_frozen_qs", "qs").replace("full_dynamic", "full")
        return f"E5V_{self.restart_key}_g{grade}_b{brake}_r{ramp_ms}_{phase}"


@dataclass(frozen=True, slots=True)
class BenchPoint:
    primary_target_torque_Nm: float
    secondary_target_torque_Nm: float
    ramp_s: float

    @property
    def case_id(self) -> str:
        p = str(abs(int(round(self.primary_target_torque_Nm)))).zfill(2)
        s = str(abs(int(round(self.secondary_target_torque_Nm)))).zfill(2)
        r = str(int(round(1000.0 * self.ramp_s))).zfill(3)
        return f"E5B_dyn_p{p}_s{s}_r{r}"


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


def _max_abs(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [_finite(row.get(key)) for row in rows]
    finite = [x for x in values if x is not None]
    return max((abs(x) for x in finite), default=None)


def _min(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [_finite(row.get(key)) for row in rows]
    finite = [x for x in values if x is not None]
    return min(finite) if finite else None


def _rows_after(rows: list[dict[str, Any]], onset_s: float) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if (_finite(row.get("time_s")) is not None and float(row["time_s"]) >= onset_s)
    ]


def _augment_qs(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        belt = _finite(row.get("helix_belt_reaction_torque_Nm"))
        spring = _finite(row.get("helix_torsional_spring_torque_Nm"))
        shaft = _finite(row.get("helix_shaft_accel_reaction_torque_Nm"))
        shift = _finite(row.get("helix_shift_accel_reaction_torque_Nm"))
        curvature = _finite(row.get("helix_curvature_reaction_torque_Nm"))
        if None in (belt, spring, shaft, shift, curvature):
            row["helix_quasi_static_margin_Nm"] = float("nan")
            row["helix_dynamic_correction_Nm"] = float("nan")
            continue
        row["helix_quasi_static_margin_Nm"] = float(belt + spring)
        row["helix_dynamic_correction_Nm"] = float(shaft + shift + curvature)


def _novelty_metrics(
    rows: list[dict[str, Any]],
    *,
    start_s: float,
    end_s: float,
) -> dict[str, Any]:
    """Compare full and quasi-static margins without bridging unresolved gaps."""

    unique = deduplicate_by_time(rows)
    runs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    full_values: list[float] = []
    qs_values: list[float] = []
    dyn_values: list[float] = []

    for row in unique:
        t = _finite(row.get("time_s"))
        full = _finite(row.get("helix_reacted_torque_margin_Nm"))
        qs = _finite(row.get("helix_quasi_static_margin_Nm"))
        dyn = _finite(row.get("helix_dynamic_correction_Nm"))
        if t is None or full is None or qs is None or dyn is None:
            if current:
                runs.append(current)
                current = []
            continue
        current.append({"t": t, "full": full, "qs": qs, "dyn": dyn})
        full_values.append(full)
        qs_values.append(qs)
        dyn_values.append(dyn)
    if current:
        runs.append(current)

    if not runs:
        return {
            "minimum_full_margin_Nm": None,
            "minimum_qs_margin_Nm": None,
            "minimum_dynamic_correction_Nm": None,
            "full_negative_duration_s": 0.0,
            "qs_negative_duration_s": 0.0,
            "dynamic_only_duration_s": 0.0,
            "both_negative_duration_s": 0.0,
            "qs_only_duration_s": 0.0,
            "first_full_negative_time_s": None,
            "qs_margin_at_first_full_crossing_Nm": None,
            "dynamic_only_at_first_full_crossing": False,
            "strict_dynamic_only_case": False,
        }

    full_neg_duration = 0.0
    qs_neg_duration = 0.0
    dyn_only_duration = 0.0
    both_neg_duration = 0.0
    qs_only_duration = 0.0
    first_full: float | None = None
    qs_at_first: float | None = None

    for run in runs:
        t = [item["t"] for item in run]
        full = [item["full"] for item in run]
        qs = [item["qs"] for item in run]
        full_neg = integrate_negative_part(t, full)
        qs_neg = integrate_negative_part(t, qs)
        partition = integrate_sign_partition(t, full, qs)
        full_neg_duration += full_neg.duration_s
        qs_neg_duration += qs_neg.duration_s
        dyn_only_duration += partition.full_negative_qs_positive_s
        both_neg_duration += partition.both_negative_s
        qs_only_duration += partition.full_positive_qs_negative_s
        entry, companion = first_negative_entry_with_companion(t, full, qs)
        if entry is not None and (first_full is None or entry < first_full):
            first_full = entry
            qs_at_first = companion

    minimum_full = min(full_values)
    minimum_qs = min(qs_values)
    return {
        "minimum_full_margin_Nm": minimum_full,
        "minimum_qs_margin_Nm": minimum_qs,
        "minimum_dynamic_correction_Nm": min(dyn_values),
        "maximum_dynamic_correction_Nm": max(dyn_values),
        "full_negative_duration_s": full_neg_duration,
        "qs_negative_duration_s": qs_neg_duration,
        "dynamic_only_duration_s": dyn_only_duration,
        "both_negative_duration_s": both_neg_duration,
        "qs_only_duration_s": qs_only_duration,
        "first_full_negative_time_s": first_full,
        "qs_margin_at_first_full_crossing_Nm": qs_at_first,
        "dynamic_only_at_first_full_crossing": (
            bool(first_full is not None and qs_at_first is not None and qs_at_first > 0.0)
        ),
        "strict_dynamic_only_case": bool(minimum_full < 0.0 and minimum_qs > 0.0),
    }


def _response_class(result, onset_s: float, *, ignore_initial_s: float = 0.0) -> str:
    cutoff = max(float(onset_s), float(ignore_initial_s))
    post = [record for record in result.transitions if float(record.time) >= cutoff]
    if any(getattr(record.transition, "has_successor_state", False) for record in post):
        return "impact_reset"
    if post:
        return "contact_switching"
    return "clean_continuous"


def _completed_summary(
    *,
    case_id: str,
    family: str,
    phase: str,
    restart: Restart,
    restart_key: str,
    run,
    onset_s: float,
    duration_s: float,
    grade_deg: float | None,
    primary_target_torque_Nm: float | None,
    secondary_target_torque_Nm: float | None,
    ramp_s: float,
    reference_brake_magnitude_Nm: float,
    ignore_initial_transition_s: float = 0.0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = [sample.row for sample in run.samples]
    _augment_qs(rows)
    for row in rows:
        row.update(
            {
                "e5_case_id": case_id,
                "e5_family": family,
                "e5_phase": phase,
                "e5_restart_key": restart_key,
                "e5_grade_deg": grade_deg,
                "e5_primary_target_torque_Nm": primary_target_torque_Nm,
                "e5_secondary_target_torque_Nm": secondary_target_torque_Nm,
                "e5_ramp_s": ramp_s,
            }
        )
    post = _rows_after(rows, onset_s)
    topo = contact_topology_metrics(
        post,
        case_start_s=onset_s,
        case_end_s=duration_s,
    )
    novelty = _novelty_metrics(post, start_s=onset_s, end_s=duration_s)
    decomposition = e4.minimum_margin_decomposition(post)
    transitions = [
        record for record in run.result.transitions
        if float(record.time) >= max(onset_s, ignore_initial_transition_s)
    ]
    max_lambda_p = _max_abs(post, "lambda_primary")
    max_lambda_s = _max_abs(post, "lambda_secondary")
    resolved_modes = [
        str(row.get("cvt_mode", ""))
        for row in post
        if _finite(row.get("helix_reacted_torque_margin_Nm")) is not None
    ]
    all_stick_stick = bool(
        resolved_modes
        and all("stick_stick" in mode.lower() for mode in resolved_modes)
    )
    clean_static = bool(
        not transitions
        and all_stick_stick
        and max_lambda_p is not None
        and max_lambda_s is not None
        and max(max_lambda_p, max_lambda_s) < 0.649
    )
    brake_mag = abs(float(primary_target_torque_Nm)) if primary_target_torque_Nm is not None else None
    summary = {
        "case_id": case_id,
        "family": family,
        "phase": phase,
        "status": "completed",
        "restart_key": restart_key,
        "restart_target_shift_percent": restart.target_shift_percent,
        "restart_actual_shift_percent": restart.actual_shift_percent,
        "restart_conditioning_time_s": restart.time_s,
        "grade_deg": grade_deg,
        "primary_target_torque_Nm": primary_target_torque_Nm,
        "primary_brake_magnitude_Nm": brake_mag,
        "secondary_target_torque_Nm": secondary_target_torque_Nm,
        "ramp_s": ramp_s,
        "onset_s": onset_s,
        "duration_s": duration_s,
        "reference_engine_brake_magnitude_Nm": reference_brake_magnitude_Nm,
        "within_reference_brake_magnitude": (
            bool(brake_mag is not None and brake_mag <= reference_brake_magnitude_Nm + 1.0e-12)
            if brake_mag is not None else None
        ),
        "response_class": _response_class(
            run.result, onset_s, ignore_initial_s=ignore_initial_transition_s
        ),
        "transition_count_after_onset": len(transitions),
        "all_resolved_stick_stick": all_stick_stick,
        "clean_static_continuous": clean_static,
        "max_abs_lambda_primary_after_onset": max_lambda_p,
        "max_abs_lambda_secondary_after_onset": max_lambda_s,
        "minimum_secondary_normal_N_after_onset": _min(post, "normal_secondary_N"),
        "max_abs_shift_speed_m_s_after_onset": _max_abs(post, "shift_speed_m_s"),
        **topo,
        **novelty,
        **decomposition,
    }
    return summary, rows


def _vehicle_boundaries(route, engine, road_load, constants, programme, *, onset_s, ramp_s, torque_Nm):
    from cinder.model.boundaries.shaft import FullThrottleEngineBoundary

    base = FullThrottleEngineBoundary(
        engine,
        equivalent_rotational_inertia=constants.engine_rotational_inertia,
    )
    primary = BlendToTorqueBoundary(
        base,
        onset_s=onset_s,
        ramp_s=ramp_s,
        target_torque_Nm=torque_Nm,
        label="e5_primary_braking_target",
    )
    secondary = route.TimeProgrammedLockedFinalDriveBoundary(
        road_load=road_load,
        programme=programme,
        direct_secondary_shaft_inertia=constants.gearbox_input_rotational_inertia,
    )
    return primary, secondary


def _evaluate_vehicle(
    *,
    point: VehiclePoint,
    restart: Restart,
    route,
    ab,
    assembly,
    engine,
    road_load,
    constants,
    cfg,
    reference_brake_magnitude_Nm: float,
):
    onset = float(cfg["onset_s"])
    hold = float(cfg["hold_s"])
    duration = onset + point.ramp_s + hold
    programme = transient_grade_programme(
        route,
        onset_s=onset,
        ramp_s=point.ramp_s,
        hold_s=hold,
        target_degrees=point.grade_deg,
    )
    primary, secondary = _vehicle_boundaries(
        route, engine, road_load, constants, programme,
        onset_s=onset, ramp_s=point.ramp_s,
        torque_Nm=point.primary_target_torque_Nm,
    )
    solver = cfg["solver"]
    max_step = min(
        float(solver["maximum_step_cap_s"]),
        max(float(solver["minimum_max_step_s"]), point.ramp_s / 8.0),
    )
    try:
        run, raw, _status = run_custom_restart_case(
            route=route,
            ab=ab,
            restart=restart,
            assembly=assembly,
            engine=engine,
            road_load=road_load,
            constants=constants,
            programme=programme,
            duration_s=duration,
            sample_step_s=float(solver["sample_step_s"]),
            rtol=float(solver["relative_tolerance"]),
            atol=float(solver["absolute_tolerance"]),
            max_step_s=max_step,
            primary_boundary=primary,
            secondary_boundary=secondary,
            reclassify_initial_mode=False,
        )
    except Exception as exc:
        return {
            "case_id": point.case_id,
            "family": "vehicle_braking_envelope",
            "phase": point.phase,
            "status": "exception",
            "restart_target_shift_percent": restart.target_shift_percent,
            "restart_actual_shift_percent": restart.actual_shift_percent,
            "grade_deg": point.grade_deg,
            "primary_target_torque_Nm": point.primary_target_torque_Nm,
            "primary_brake_magnitude_Nm": abs(point.primary_target_torque_Nm),
            "ramp_s": point.ramp_s,
            "error": f"{type(exc).__name__}: {exc}",
        }, []
    if run is None:
        return {
            "case_id": point.case_id,
            "family": "vehicle_braking_envelope",
            "phase": point.phase,
            "status": "integration_failed",
            "restart_target_shift_percent": restart.target_shift_percent,
            "restart_actual_shift_percent": restart.actual_shift_percent,
            "grade_deg": point.grade_deg,
            "primary_target_torque_Nm": point.primary_target_torque_Nm,
            "primary_brake_magnitude_Nm": abs(point.primary_target_torque_Nm),
            "ramp_s": point.ramp_s,
            "error": raw.termination_reason,
        }, []
    return _completed_summary(
        case_id=point.case_id,
        family="vehicle_braking_envelope",
        phase=point.phase,
        restart=restart,
        restart_key=point.restart_key,
        run=run,
        onset_s=onset,
        duration_s=duration,
        grade_deg=point.grade_deg,
        primary_target_torque_Nm=point.primary_target_torque_Nm,
        secondary_target_torque_Nm=None,
        ramp_s=point.ramp_s,
        reference_brake_magnitude_Nm=reference_brake_magnitude_Nm,
    )


def _evaluate_bench(
    *,
    point: BenchPoint,
    restart: Restart,
    route,
    ab,
    assembly,
    engine,
    road_load,
    constants,
    cfg,
    reference_brake_magnitude_Nm: float,
):
    onset = 0.0
    hold = float(cfg["bench_dynamic_novelty"]["hold_s"])
    duration = point.ramp_s + hold
    programme = transient_grade_programme(
        route,
        onset_s=0.0,
        ramp_s=point.ramp_s,
        hold_s=hold,
        target_degrees=0.0,
    )
    from cinder.model.boundaries.shaft import FullThrottleEngineBoundary

    base = FullThrottleEngineBoundary(
        engine,
        equivalent_rotational_inertia=constants.engine_rotational_inertia,
    )
    primary = BlendToTorqueBoundary(
        base,
        onset_s=0.0,
        ramp_s=point.ramp_s,
        target_torque_Nm=point.primary_target_torque_Nm,
        label="e5_bench_primary_target",
    )
    secondary = PrescribedTorqueBoundary(
        equivalent_inertia=float(cfg["bench_dynamic_novelty"]["secondary_inertia_kg_m2"]),
        onset_s=0.0,
        ramp_s=point.ramp_s,
        initial_torque_Nm=0.0,
        target_torque_Nm=point.secondary_target_torque_Nm,
        label="e5_bench_secondary_drive",
    )
    solver = cfg["solver"]
    max_step = min(
        float(solver["maximum_step_cap_s"]),
        max(float(solver["minimum_max_step_s"]), point.ramp_s / 8.0),
    )
    try:
        run, raw, _status = run_custom_restart_case(
            route=route,
            ab=ab,
            restart=restart,
            assembly=assembly,
            engine=engine,
            road_load=road_load,
            constants=constants,
            programme=programme,
            duration_s=duration,
            sample_step_s=float(solver["sample_step_s"]),
            rtol=float(solver["relative_tolerance"]),
            atol=float(solver["absolute_tolerance"]),
            max_step_s=max_step,
            primary_boundary=primary,
            secondary_boundary=secondary,
            reclassify_initial_mode=True,
        )
    except Exception as exc:
        return {
            "case_id": point.case_id,
            "family": "bench_dynamic_novelty",
            "phase": "bench_refinement",
            "status": "exception",
            "primary_target_torque_Nm": point.primary_target_torque_Nm,
            "secondary_target_torque_Nm": point.secondary_target_torque_Nm,
            "ramp_s": point.ramp_s,
            "error": f"{type(exc).__name__}: {exc}",
        }, []
    if run is None:
        return {
            "case_id": point.case_id,
            "family": "bench_dynamic_novelty",
            "phase": "bench_refinement",
            "status": "integration_failed",
            "primary_target_torque_Nm": point.primary_target_torque_Nm,
            "secondary_target_torque_Nm": point.secondary_target_torque_Nm,
            "ramp_s": point.ramp_s,
            "error": raw.termination_reason,
        }, []
    return _completed_summary(
        case_id=point.case_id,
        family="bench_dynamic_novelty",
        phase="bench_refinement",
        restart=restart,
        restart_key="dynamic",
        run=run,
        onset_s=0.0,
        duration_s=duration,
        grade_deg=0.0,
        primary_target_torque_Nm=point.primary_target_torque_Nm,
        secondary_target_torque_Nm=point.secondary_target_torque_Nm,
        ramp_s=point.ramp_s,
        reference_brake_magnitude_Nm=reference_brake_magnitude_Nm,
        ignore_initial_transition_s=1.0e-6,
    )


def _first_sign_brackets(rows: list[dict[str, Any]], key: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    completed = [r for r in rows if r.get("status") == "completed" and _finite(r.get(key)) is not None]
    completed.sort(key=lambda r: float(r["primary_brake_magnitude_Nm"]))
    brackets = []
    for left, right in zip(completed, completed[1:]):
        yl = float(left[key])
        yr = float(right[key])
        if yl == 0.0:
            continue
        if (yl > 0.0 and yr < 0.0) or (yl < 0.0 and yr > 0.0):
            brackets.append((left, right))
    return brackets


def _bisection_threshold(
    *,
    left: dict[str, Any],
    right: dict[str, Any],
    metric_key: str,
    iterations: int,
    evaluate_by_torque,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Refine one observed local sign bracket without assuming global monotonicity."""

    a = float(left["primary_target_torque_Nm"])
    b = float(right["primary_target_torque_Nm"])
    ya = float(left[metric_key])
    yb = float(right[metric_key])
    extra: list[dict[str, Any]] = []
    if ya * yb > 0.0:
        raise ValueError("threshold refinement requires a sign bracket")

    for _ in range(iterations):
        mid = 0.5 * (a + b)
        row = evaluate_by_torque(mid)
        extra.append(row)
        y = _finite(row.get(metric_key))
        if y is None:
            break
        if y == 0.0:
            a = b = mid
            ya = yb = 0.0
            break
        if ya * y <= 0.0:
            b, yb = mid, y
        else:
            a, ya = mid, y

    weak = a if abs(a) < abs(b) else b
    strong = b if abs(b) > abs(a) else a
    estimate = 0.5 * (a + b)
    return {
        "weak_brake_torque_Nm": weak,
        "strong_brake_torque_Nm": strong,
        "estimated_threshold_torque_Nm": estimate,
        "estimated_threshold_brake_magnitude_Nm": abs(estimate),
        "final_bracket_width_Nm": abs(abs(a) - abs(b)),
    }, extra


def _select_dynamic_ramp_seed(group: list[dict[str, Any]], *, near_qs_upper_Nm: float):
    completed = [r for r in group if r.get("status") == "completed"]
    preferred = [
        r for r in completed
        if _finite(r.get("minimum_qs_margin_Nm")) is not None
        and float(r["minimum_qs_margin_Nm"]) > 0.0
        and float(r["minimum_qs_margin_Nm"]) <= near_qs_upper_Nm
    ]
    if not preferred:
        preferred = [
            r for r in completed
            if _finite(r.get("minimum_qs_margin_Nm")) is not None
            and float(r["minimum_qs_margin_Nm"]) > 0.0
            and _finite(r.get("minimum_full_margin_Nm")) is not None
            and float(r["minimum_full_margin_Nm"]) <= near_qs_upper_Nm
        ]
    if not preferred:
        return None

    # Prefer a reference-scale torque when it is already close enough; otherwise
    # use the closest positive-QS extension point.
    reference = [r for r in preferred if bool(r.get("within_reference_brake_magnitude"))]
    pool = reference or preferred
    return min(pool, key=lambda r: abs(float(r["minimum_full_margin_Nm"])))


def _write_plots(out: Path, vehicle_rows, thresholds, dynamic_rows, bench_rows) -> None:
    completed = [r for r in vehicle_rows if r.get("status") == "completed"]
    if completed:
        fig, ax = plt.subplots(figsize=(10.5, 6.0))
        for restart in sorted({r["restart_target_shift_percent"] for r in completed}):
            subset = [r for r in completed if r["restart_target_shift_percent"] == restart and r["phase"] == "coarse"]
            for grade in sorted({r["grade_deg"] for r in subset}):
                points = sorted(
                    [r for r in subset if r["grade_deg"] == grade],
                    key=lambda r: r["primary_brake_magnitude_Nm"],
                )
                if not points:
                    continue
                ax.plot(
                    [r["primary_brake_magnitude_Nm"] for r in points],
                    [r["minimum_full_margin_Nm"] for r in points],
                    marker="o",
                    markersize=3,
                    label=f"{restart:.0f}% shift, {grade:+.0f}°",
                )
        ax.axhline(0.0, linewidth=1.0)
        ax.axvline(28.0, linewidth=1.0, linestyle="--", label="reference brake magnitude 28 N m")
        ax.set_xlabel("Primary braking magnitude [N m]")
        ax.set_ylabel("Minimum full dynamic M_h [N m]")
        ax.set_title("Vehicle lift-off envelope: full dynamic margin")
        ax.legend(fontsize=7, ncol=2)
        fig.tight_layout()
        fig.savefig(out / "vehicle_margin_envelope.png", dpi=160)
        plt.close(fig)

    comparison = [r for r in thresholds if r.get("margin_kind") == "comparison"]
    if comparison:
        fig, ax = plt.subplots(figsize=(9.5, 5.5))
        for restart in sorted({r["restart_target_shift_percent"] for r in comparison}):
            subset = sorted(
                [r for r in comparison if r["restart_target_shift_percent"] == restart],
                key=lambda r: r["grade_deg"],
            )
            ax.plot(
                [r["grade_deg"] for r in subset],
                [r.get("full_threshold_brake_magnitude_Nm", np.nan) for r in subset],
                marker="o",
                label=f"full, {restart:.0f}% shift",
            )
            ax.plot(
                [r["grade_deg"] for r in subset],
                [r.get("qs_threshold_brake_magnitude_Nm", np.nan) for r in subset],
                marker="x",
                linestyle="--",
                label=f"QS diagnostic, {restart:.0f}% shift",
            )
        ax.axhline(28.0, linewidth=1.0, linestyle=":")
        ax.set_xlabel("Grade [deg; downhill negative]")
        ax.set_ylabel("Estimated braking magnitude at M_h=0 [N m]")
        ax.set_title("Full-dynamic vs trajectory-frozen quasi-static lift-off threshold")
        ax.legend(fontsize=7, ncol=2)
        fig.tight_layout()
        fig.savefig(out / "threshold_vs_grade.png", dpi=160)
        plt.close(fig)

    novelty = [r for r in [*dynamic_rows, *bench_rows] if r.get("status") == "completed"]
    if novelty:
        fig, ax = plt.subplots(figsize=(7.0, 7.0))
        for family, marker in (("vehicle_dynamic_ramp", "o"), ("bench_dynamic_novelty", "x")):
            subset = [r for r in novelty if r.get("family") == family]
            if not subset:
                continue
            ax.scatter(
                [r["minimum_qs_margin_Nm"] for r in subset],
                [r["minimum_full_margin_Nm"] for r in subset],
                marker=marker,
                label=family,
            )
        ax.axhline(0.0, linewidth=1.0)
        ax.axvline(0.0, linewidth=1.0)
        lim = ax.get_xlim()
        lo, hi = min(lim[0], ax.get_ylim()[0]), max(lim[1], ax.get_ylim()[1])
        ax.plot([lo, hi], [lo, hi], linewidth=0.8, linestyle="--")
        ax.set_xlabel("Minimum quasi-static margin M_h,QS [N m]")
        ax.set_ylabel("Minimum full dynamic margin M_h [N m]")
        ax.set_title("Dynamic novelty search")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out / "dynamic_novelty_full_vs_qs.png", dpi=160)
        plt.close(fig)


def main() -> int:
    args = parse_args()
    verify_environment()
    study = load_json(STUDY_ROOT / "study.json")
    cfg = study["experiments"]["liftoff_envelope_refinement"]

    if args.quick:
        vehicle_cfg = dict(cfg["vehicle_envelope"])
        vehicle_cfg["restart_shift_percents"] = [50.0]
        vehicle_cfg["grade_targets_deg"] = [-15.0, -30.0]
        vehicle_cfg["primary_target_torques_Nm"] = [-28.0, -40.0]
        dynamic_ramps = [0.10, 0.25]
        bench_primary = [-25.0]
        bench_secondary = [15.0, 20.0]
        bench_ramps = [0.10]
        bisection_iterations = 1
    else:
        vehicle_cfg = cfg["vehicle_envelope"]
        dynamic_ramps = list(cfg["dynamic_ramp_refinement"]["ramp_times_s"])
        bench_primary = list(cfg["bench_dynamic_novelty"]["primary_target_torques_Nm"])
        bench_secondary = list(cfg["bench_dynamic_novelty"]["secondary_drive_torques_Nm"])
        bench_ramps = list(cfg["bench_dynamic_novelty"]["ramp_times_s"])
        bisection_iterations = int(vehicle_cfg["bisection_iterations"])

    conditioning, resolved, assembly, engine, road_load, ab, route = run_flat_slotted_reference(
        duration_s=float(cfg["conditioning_duration_s"]),
        sample_step_s=float(cfg["conditioning_solver"]["sample_step_s"]),
        rtol=float(cfg["conditioning_solver"]["relative_tolerance"]),
        atol=float(cfg["conditioning_solver"]["absolute_tolerance"]),
        max_step_s=float(cfg["conditioning_solver"]["max_step_s"]),
    )
    reference_brake_magnitude = abs(float(resolved.constants.engine_governed_overspeed_torque))

    restarts: dict[str, Restart] = {}
    for target in vehicle_cfg["restart_shift_percents"]:
        key = f"s{int(round(float(target))):02d}"
        restart = select_restart(
            conditioning,
            float(target),
            maximum_error_percent=float(cfg["restart_maximum_error_percent"]),
        )
        # Attach a convenient non-contract attribute only through a side map;
        # Restart itself stays frozen.
        restarts[key] = restart
    dynamic_restart, dynamic_score = select_dynamic_restart(conditioning)

    out = ARTIFACTS / "liftoff-envelope"
    out.mkdir(parents=True, exist_ok=True)

    cache: dict[tuple[str, float, float, float], tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    vehicle_rows: list[dict[str, Any]] = []
    vehicle_trace: list[dict[str, Any]] = []

    def evaluate_vehicle_point(point: VehiclePoint):
        key = (
            point.restart_key,
            round(point.grade_deg, 9),
            round(point.primary_target_torque_Nm, 9),
            round(point.ramp_s, 9),
        )
        if key in cache:
            return cache[key]
        summary, rows = _evaluate_vehicle(
            point=point,
            restart=restarts[point.restart_key],
            route=route,
            ab=ab,
            assembly=assembly,
            engine=engine,
            road_load=road_load,
            constants=resolved.constants,
            cfg=cfg,
            reference_brake_magnitude_Nm=reference_brake_magnitude,
        )
        cache[key] = (summary, rows)
        vehicle_rows.append(summary)
        if summary.get("status") == "completed":
            full_min = float(summary["minimum_full_margin_Nm"])
            qs_min = float(summary["minimum_qs_margin_Nm"])
            if full_min <= float(cfg["trace_retention_margin_Nm"]) or qs_min <= float(cfg["trace_retention_margin_Nm"]):
                vehicle_trace.extend(rows)
        print(
            f"{point.case_id}: full={summary.get('minimum_full_margin_Nm')} N m, "
            f"QS={summary.get('minimum_qs_margin_Nm')} N m, "
            f"dyn-only={summary.get('strict_dynamic_only_case')}"
        )
        return summary, rows

    # ------------------------------------------------------------------
    # A. Coarse vehicle envelope at a moderate transition rate.
    # ------------------------------------------------------------------
    base_ramp = float(vehicle_cfg["ramp_s"])
    coarse_groups: dict[tuple[str, float], list[dict[str, Any]]] = {}
    for restart_key in restarts:
        for grade in vehicle_cfg["grade_targets_deg"]:
            group = []
            for torque in vehicle_cfg["primary_target_torques_Nm"]:
                point = VehiclePoint(
                    restart_key=restart_key,
                    grade_deg=float(grade),
                    primary_target_torque_Nm=float(torque),
                    ramp_s=base_ramp,
                    phase="coarse",
                )
                summary, _ = evaluate_vehicle_point(point)
                group.append(summary)
            coarse_groups[(restart_key, float(grade))] = group

    # ------------------------------------------------------------------
    # B. Refine every observed local full and QS zero bracket.
    # ------------------------------------------------------------------
    threshold_rows: list[dict[str, Any]] = []
    bisection_rows: list[dict[str, Any]] = []
    for (restart_key, grade), group in coarse_groups.items():
        for metric_key, kind in (
            ("minimum_full_margin_Nm", "full_dynamic"),
            ("minimum_qs_margin_Nm", "trajectory_frozen_qs"),
        ):
            brackets = _first_sign_brackets(group, metric_key)
            for bracket_index, (left, right) in enumerate(brackets, start=1):
                def eval_torque(torque_Nm: float):
                    point = VehiclePoint(
                        restart_key=restart_key,
                        grade_deg=grade,
                        primary_target_torque_Nm=float(torque_Nm),
                        ramp_s=base_ramp,
                        phase=f"bisect_{kind}",
                    )
                    summary, _ = evaluate_vehicle_point(point)
                    return summary

                refined, extra = _bisection_threshold(
                    left=left,
                    right=right,
                    metric_key=metric_key,
                    iterations=bisection_iterations,
                    evaluate_by_torque=eval_torque,
                )
                bisection_rows.extend(extra)
                threshold_rows.append(
                    {
                        "margin_kind": kind,
                        "restart_key": restart_key,
                        "restart_target_shift_percent": restarts[restart_key].target_shift_percent,
                        "restart_actual_shift_percent": restarts[restart_key].actual_shift_percent,
                        "grade_deg": grade,
                        "ramp_s": base_ramp,
                        "bracket_index": bracket_index,
                        **refined,
                        "inside_reference_brake_magnitude": bool(
                            refined["estimated_threshold_brake_magnitude_Nm"]
                            <= reference_brake_magnitude + 1.0e-12
                        ),
                    }
                )

    # One comparison row per restart/grade using the first threshold by brake magnitude.
    comparison_rows: list[dict[str, Any]] = []
    for (restart_key, grade), _group in coarse_groups.items():
        full = sorted(
            [r for r in threshold_rows if r["margin_kind"] == "full_dynamic" and r["restart_key"] == restart_key and r["grade_deg"] == grade],
            key=lambda r: r["estimated_threshold_brake_magnitude_Nm"],
        )
        qs = sorted(
            [r for r in threshold_rows if r["margin_kind"] == "trajectory_frozen_qs" and r["restart_key"] == restart_key and r["grade_deg"] == grade],
            key=lambda r: r["estimated_threshold_brake_magnitude_Nm"],
        )
        f = full[0] if full else None
        q = qs[0] if qs else None
        comparison = {
            "margin_kind": "comparison",
            "restart_key": restart_key,
            "restart_target_shift_percent": restarts[restart_key].target_shift_percent,
            "restart_actual_shift_percent": restarts[restart_key].actual_shift_percent,
            "grade_deg": grade,
            "ramp_s": base_ramp,
            "full_threshold_brake_magnitude_Nm": (
                f["estimated_threshold_brake_magnitude_Nm"] if f else None
            ),
            "qs_threshold_brake_magnitude_Nm": (
                q["estimated_threshold_brake_magnitude_Nm"] if q else None
            ),
            "dynamic_threshold_advancement_Nm": (
                q["estimated_threshold_brake_magnitude_Nm"] - f["estimated_threshold_brake_magnitude_Nm"]
                if f and q else None
            ),
            "full_threshold_inside_reference_magnitude": (
                f["inside_reference_brake_magnitude"] if f else None
            ),
            "qs_threshold_inside_reference_magnitude": (
                q["inside_reference_brake_magnitude"] if q else None
            ),
        }
        comparison_rows.append(comparison)
    threshold_rows.extend(comparison_rows)

    # ------------------------------------------------------------------
    # C. Near-boundary ramp-rate refinement for dynamic-only vehicle cases.
    # ------------------------------------------------------------------
    dynamic_rows: list[dict[str, Any]] = []
    dynamic_trace: list[dict[str, Any]] = []
    near_qs_upper = float(cfg["dynamic_ramp_refinement"]["near_qs_margin_upper_Nm"])
    for (restart_key, grade), group in coarse_groups.items():
        seed = _select_dynamic_ramp_seed(group, near_qs_upper_Nm=near_qs_upper)
        if seed is None:
            continue
        torque = float(seed["primary_target_torque_Nm"])
        for ramp in dynamic_ramps:
            point = VehiclePoint(
                restart_key=restart_key,
                grade_deg=grade,
                primary_target_torque_Nm=torque,
                ramp_s=float(ramp),
                phase="dynamic_ramp",
            )
            summary, rows = evaluate_vehicle_point(point)
            # Clone with a distinct family/phase in the dedicated table even if
            # the run was served from the cache.
            row = dict(summary)
            row["family"] = "vehicle_dynamic_ramp"
            row["phase"] = "dynamic_ramp"
            row["seed_coarse_case_id"] = seed["case_id"]
            dynamic_rows.append(row)
            if rows:
                dynamic_trace.extend(rows)

    # ------------------------------------------------------------------
    # D. Bench refinement around the inertia-dominated E4 back-drive result.
    # ------------------------------------------------------------------
    bench_rows: list[dict[str, Any]] = []
    bench_trace: list[dict[str, Any]] = []
    for primary in bench_primary:
        for secondary in bench_secondary:
            for ramp in bench_ramps:
                point = BenchPoint(
                    primary_target_torque_Nm=float(primary),
                    secondary_target_torque_Nm=float(secondary),
                    ramp_s=float(ramp),
                )
                summary, rows = _evaluate_bench(
                    point=point,
                    restart=dynamic_restart,
                    route=route,
                    ab=ab,
                    assembly=assembly,
                    engine=engine,
                    road_load=road_load,
                    constants=resolved.constants,
                    cfg=cfg,
                    reference_brake_magnitude_Nm=reference_brake_magnitude,
                )
                bench_rows.append(summary)
                if rows:
                    bench_trace.extend(rows)
                print(
                    f"{point.case_id}: full={summary.get('minimum_full_margin_Nm')} N m, "
                    f"QS={summary.get('minimum_qs_margin_Nm')} N m, "
                    f"strict dyn-only={summary.get('strict_dynamic_only_case')}"
                )

    # Candidate catalogue: deliberately factual filters, not a performance ranking.
    candidates: list[dict[str, Any]] = []
    for source, rows in (
        ("vehicle", vehicle_rows),
        ("vehicle_dynamic_ramp", dynamic_rows),
        ("bench", bench_rows),
    ):
        for row in rows:
            if row.get("status") != "completed":
                continue
            role = None
            if bool(row.get("strict_dynamic_only_case")) and bool(row.get("clean_static_continuous")):
                role = "clean_strict_dynamic_only"
            elif bool(row.get("strict_dynamic_only_case")):
                role = "strict_dynamic_only_with_contact_events"
            elif float(row.get("dynamic_only_duration_s", 0.0) or 0.0) > 0.0:
                role = "contains_dynamic_only_interval"
            elif float(row.get("minimum_full_margin_Nm", 1.0e9)) < 0.0:
                role = "full_liftoff"
            elif abs(float(row.get("minimum_full_margin_Nm", 1.0e9))) <= 1.0:
                role = "near_full_boundary"
            if role is not None:
                candidates.append({"candidate_role": role, "source": source, **row})

    # Put the most scientifically discriminating labels first, then shallower margins.
    role_order = {
        "clean_strict_dynamic_only": 0,
        "strict_dynamic_only_with_contact_events": 1,
        "contains_dynamic_only_interval": 2,
        "full_liftoff": 3,
        "near_full_boundary": 4,
    }
    candidates.sort(
        key=lambda r: (
            role_order.get(str(r["candidate_role"]), 99),
            abs(float(r.get("minimum_full_margin_Nm", 1.0e9))),
        )
    )

    write_rows(out / "vehicle_envelope_summary.csv", vehicle_rows)
    write_rows(out / "vehicle_near_boundary_trace.csv", vehicle_trace)
    write_rows(out / "thresholds.csv", threshold_rows)
    write_rows(out / "dynamic_ramp_summary.csv", dynamic_rows)
    write_rows(out / "dynamic_ramp_trace.csv", dynamic_trace)
    write_rows(out / "bench_dynamic_summary.csv", bench_rows)
    write_rows(out / "bench_dynamic_trace.csv", bench_trace)
    write_rows(out / "candidate_catalogue.csv", candidates)
    write_rows(
        out / "restart_states.csv",
        [
            {
                "restart_key": key,
                "target_shift_percent": r.target_shift_percent,
                "actual_shift_percent": r.actual_shift_percent,
                "conditioning_time_s": r.time_s,
                "baseline_margin_Nm": r.baseline_margin_Nm,
            }
            for key, r in restarts.items()
        ]
        + [
            {
                "restart_key": "dynamic",
                "target_shift_percent": dynamic_restart.target_shift_percent,
                "actual_shift_percent": dynamic_restart.actual_shift_percent,
                "conditioning_time_s": dynamic_restart.time_s,
                "baseline_margin_Nm": dynamic_restart.baseline_margin_Nm,
                "dynamic_selection_score_Nm": dynamic_score,
            }
        ],
    )

    _write_plots(out, vehicle_rows, threshold_rows, dynamic_rows, bench_rows)
    write_reference_provenance(
        out / "provenance",
        plant=conditioning.system.cvt.model,
        extra={
            "experiment": "E5_liftoff_envelope_refinement",
            "reference_engine_brake_magnitude_Nm": reference_brake_magnitude,
            "interpretation_note": (
                "The reference braking magnitude is the largest configured braking "
                "torque magnitude in the pinned engine boundary; it is not a validated "
                "closed-throttle torque map at every engine speed."
            ),
        },
    )

    strict_clean = [
        r for r in candidates if r["candidate_role"] == "clean_strict_dynamic_only"
    ]
    strict_any = [
        r for r in candidates
        if r["candidate_role"] in {"clean_strict_dynamic_only", "strict_dynamic_only_with_contact_events"}
    ]
    reference_liftoff = [
        r for r in vehicle_rows
        if r.get("status") == "completed"
        and bool(r.get("within_reference_brake_magnitude"))
        and float(r.get("minimum_full_margin_Nm", 1.0)) < 0.0
    ]
    payload = {
        "status": "complete",
        "quick": bool(args.quick),
        "reference_engine_brake_magnitude_Nm": reference_brake_magnitude,
        "vehicle_case_count": len(vehicle_rows),
        "threshold_row_count": len(threshold_rows),
        "dynamic_ramp_case_count": len(dynamic_rows),
        "bench_case_count": len(bench_rows),
        "reference_scale_vehicle_liftoff_case_count": len(reference_liftoff),
        "strict_dynamic_only_candidate_count": len(strict_any),
        "clean_strict_dynamic_only_candidate_count": len(strict_clean),
        "candidate_count": len(candidates),
        "scientific_boundary": (
            "Dynamic-only means the full dynamic margin is negative while the "
            "trajectory-frozen torque+spring diagnostic is positive. It does not by "
            "itself prove that no prior published dynamic helix model could predict "
            "the same effect."
        ),
    }
    (out / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
