"""E4: broad mechanism-discovery screen across physically different forcings.

This stage deliberately goes beyond one vehicle boundary and one perturbation
family.  It reuses naturally reached slotted-reference states, then asks how the
selected-flank reaction margin responds to four complementary experiments:

1. hill/load entry with the ordinary Baja engine + vehicle boundary;
2. downhill combined with a full-throttle -> engine-braking torque transition;
3. bench back-drive with the vehicle removed and the secondary shaft driven;
4. bench resisting-load tests with the vehicle removed.

The slotted topology remains active in every case.  Negative M_h therefore
means that the opposite slot flank is carrying the reaction and marks a
would-be lift-off condition for a single selected flank.  No detached
unilateral mechanics are introduced in this discovery stage.
"""
from __future__ import annotations

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

from metrics import contact_topology_metrics  # noqa: E402
from study_support import (  # noqa: E402
    ARTIFACTS,
    BlendToTorqueBoundary,
    PrescribedTorqueBoundary,
    Restart,
    load_json,
    run_custom_restart_case,
    run_flat_slotted_reference,
    run_slotted_full_launch_programme,
    select_dynamic_restart,
    select_restart,
    transient_grade_programme,
    verify_environment,
    write_reference_provenance,
    write_rows,
)


@dataclass(frozen=True, slots=True)
class DiscoveryCase:
    case_id: str
    family: str
    restart_key: str
    onset_s: float
    ramp_s: float
    hold_s: float
    grade_target_deg: float = 0.0
    primary_target_torque_Nm: float | None = None
    secondary_target_torque_Nm: float | None = None
    bench_secondary_inertia_kg_m2: float | None = None

    @property
    def duration_s(self) -> float:
        return self.onset_s + self.ramp_s + self.hold_s


COMPONENT_KEYS = (
    ("helix_belt_reaction_torque_Nm", "belt_torque"),
    ("helix_torsional_spring_torque_Nm", "torsional_spring"),
    ("helix_shaft_accel_reaction_torque_Nm", "shaft_acceleration"),
    ("helix_shift_accel_reaction_torque_Nm", "shift_acceleration"),
    ("helix_curvature_reaction_torque_Nm", "profile_curvature"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run one representative case from each family as a smoke test.",
    )
    return parser.parse_args()


def _finite(row: dict[str, Any], key: str) -> float | None:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _rows_after(rows: list[dict[str, Any]], onset_s: float) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        t = _finite(row, "time_s")
        if t is not None and t >= onset_s:
            out.append(row)
    return out


def _rows_between(
    rows: list[dict[str, Any]],
    start_s: float,
    end_s: float | None = None,
) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        t = _finite(row, "time_s")
        if t is None or t < start_s:
            continue
        if end_s is not None and t > end_s:
            continue
        out.append(row)
    return out


def legacy_hill_specs(cfg: dict[str, Any], *, quick: bool) -> list[dict[str, Any]]:
    replay = cfg.get("legacy_hill_replays", {})
    if quick or not replay.get("enabled", False):
        return []
    return [dict(item) for item in replay.get("cases", [])]


def build_legacy_hill_programme(route, spec: dict[str, Any]):
    kind = str(spec["kind"])
    if kind == "tagged_route_default":
        # This is the exact physical grade programme selected by
        # run_dynamic_actuator_ablation.py --scenario hill in the pinned
        # release helper.
        return route.GradeProgramme.default()
    if kind == "natural_hard_hill":
        flat = float(spec["flat_runup_s"])
        ramp = float(spec["ramp_s"])
        hold = float(spec["hold_s"])
        grade = float(spec["target_grade_deg"])
        return route.GradeProgramme(
            (
                route.GradePhase(
                    name="natural flat run-up",
                    start_s=0.0,
                    end_s=flat,
                    start_degrees=0.0,
                    end_degrees=0.0,
                    transition=False,
                ),
                route.GradePhase(
                    name="hard hill entry",
                    start_s=flat,
                    end_s=flat + ramp,
                    start_degrees=0.0,
                    end_degrees=grade,
                    transition=True,
                ),
                route.GradePhase(
                    name="hard hill hold",
                    start_s=flat + ramp,
                    end_s=flat + ramp + hold,
                    start_degrees=grade,
                    end_degrees=grade,
                    transition=False,
                ),
            )
        )
    raise ValueError(f"Unsupported legacy hill replay kind: {kind}")


def programme_phase_name(programme, time_s: float) -> str:
    phases = tuple(programme.phases)
    for index, phase in enumerate(phases):
        if phase.contains(float(time_s), include_end=index == len(phases) - 1):
            return str(phase.name)
    return str(phases[-1].name) if phases else ""


def response_class(result, onset_s: float) -> str:
    post = [record for record in result.transitions if float(record.time) >= onset_s]
    if any(getattr(record.transition, "has_successor_state", False) for record in post):
        return "impact_reset"
    if post:
        return "contact_switching"
    return "clean_continuous"


def classify(metrics: dict[str, Any], *, near_margin_Nm: float) -> str:
    if float(metrics.get("opposite_flank_duration_s", 0.0)) > 1.0e-9:
        return "opposite_flank_required"
    minimum_abs = metrics.get("minimum_absolute_margin_Nm")
    if minimum_abs is not None and float(minimum_abs) <= near_margin_Nm:
        return "near_boundary"
    return "one_flank"


def minimum_margin_decomposition(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = []
    for row in rows:
        margin = _finite(row, "helix_reacted_torque_margin_Nm")
        if margin is not None:
            usable.append((margin, row))
    if not usable:
        return {}

    margin, row = min(usable, key=lambda item: item[0])
    values: dict[str, float | None] = {}
    negative_terms: list[tuple[float, str]] = []
    for key, label in COMPONENT_KEYS:
        value = _finite(row, key)
        values[f"minimum_margin_{label}_Nm"] = value
        if value is not None:
            negative_terms.append((value, label))

    dynamic_terms = [
        values.get("minimum_margin_shaft_acceleration_Nm"),
        values.get("minimum_margin_shift_acceleration_Nm"),
        values.get("minimum_margin_profile_curvature_Nm"),
    ]
    dynamic_sum = sum(float(x) for x in dynamic_terms if x is not None)
    dominant = min(negative_terms, key=lambda item: item[0])[1] if negative_terms else None

    return {
        "minimum_margin_time_s": _finite(row, "time_s"),
        "minimum_margin_Nm_from_row": margin,
        "minimum_margin_dominant_negative_term": dominant,
        "minimum_margin_dynamic_sum_Nm": dynamic_sum,
        "minimum_margin_secondary_closure_torque_Nm": _finite(
            row, "helix_secondary_closure_torque_Nm"
        ),
        "minimum_margin_secondary_internal_power_W": _finite(
            row, "helix_secondary_internal_power_W"
        ),
        "minimum_margin_shift_speed_m_s": _finite(row, "shift_speed_m_s"),
        "minimum_margin_shift_mm": _finite(row, "shift_mm"),
        "minimum_margin_primary_rpm": _finite(row, "primary_rpm"),
        "minimum_margin_secondary_rpm": _finite(row, "secondary_rpm"),
        "minimum_margin_ratio_secondary_over_primary": _finite(
            row, "ratio_secondary_over_primary"
        ),
        "minimum_margin_route_phase": row.get("route_phase"),
        "minimum_margin_primary_external_torque_Nm": _finite(
            row, "primary_external_torque_Nm"
        ),
        "minimum_margin_secondary_external_torque_Nm": _finite(
            row, "secondary_external_torque_Nm"
        ),
        **values,
    }


def _max_abs(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [_finite(row, key) for row in rows]
    values = [x for x in values if x is not None]
    return max((abs(x) for x in values), default=None)


def _min(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [_finite(row, key) for row in rows]
    values = [x for x in values if x is not None]
    return min(values) if values else None


def _range(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [_finite(row, key) for row in rows]
    values = [x for x in values if x is not None]
    return max(values) - min(values) if values else None


def build_cases(cfg: dict[str, Any], *, quick: bool) -> list[DiscoveryCase]:
    onset = float(cfg["onset_s"])
    hold = float(cfg["hold_s"])
    cases: list[DiscoveryCase] = []
    counter = 0

    def add(**kwargs) -> None:
        nonlocal counter
        counter += 1
        family = kwargs.pop("family")
        case_onset = float(kwargs.pop("onset_s", onset))
        cases.append(
            DiscoveryCase(
                case_id=f"E4_{counter:03d}_{family}",
                family=family,
                onset_s=case_onset,
                hold_s=hold,
                **kwargs,
            )
        )

    if quick:
        add(
            family="hill_entry",
            restart_key="s50",
            ramp_s=0.25,
            grade_target_deg=30.0,
        )
        add(
            family="downhill_engine_braking",
            restart_key="s90",
            ramp_s=0.25,
            grade_target_deg=-25.0,
            primary_target_torque_Nm=-20.0,
        )
        add(
            family="bench_backdrive",
            restart_key="dynamic",
            onset_s=0.0,
            ramp_s=0.10,
            primary_target_torque_Nm=-20.0,
            secondary_target_torque_Nm=60.0,
            bench_secondary_inertia_kg_m2=float(cfg["bench_secondary_inertia_kg_m2"]),
        )
        add(
            family="bench_resisting_load",
            restart_key="s50",
            onset_s=0.0,
            ramp_s=0.10,
            secondary_target_torque_Nm=-60.0,
            bench_secondary_inertia_kg_m2=float(cfg["bench_secondary_inertia_kg_m2"]),
        )
        return cases

    hill = cfg["hill_entry"]
    for restart_key in hill["restart_keys"]:
        for ramp in hill["ramp_times_s"]:
            for grade in hill["grade_targets_deg"]:
                add(
                    family="hill_entry",
                    restart_key=str(restart_key),
                    ramp_s=float(ramp),
                    grade_target_deg=float(grade),
                )

    downhill = cfg["downhill_engine_braking"]
    for restart_key in downhill["restart_keys"]:
        for grade in downhill["grade_targets_deg"]:
            for brake in downhill["primary_target_torques_Nm"]:
                add(
                    family="downhill_engine_braking",
                    restart_key=str(restart_key),
                    ramp_s=float(downhill["ramp_s"]),
                    grade_target_deg=float(grade),
                    primary_target_torque_Nm=float(brake),
                )

    backdrive = cfg["bench_backdrive"]
    for restart_key in backdrive["restart_keys"]:
        for primary in backdrive["primary_target_torques_Nm"]:
            for secondary in backdrive["secondary_drive_torques_Nm"]:
                add(
                    family="bench_backdrive",
                    restart_key=str(restart_key),
                    onset_s=0.0,
                    ramp_s=float(backdrive["ramp_s"]),
                    primary_target_torque_Nm=float(primary),
                    secondary_target_torque_Nm=float(secondary),
                    bench_secondary_inertia_kg_m2=float(cfg["bench_secondary_inertia_kg_m2"]),
                )

    load = cfg["bench_resisting_load"]
    for restart_key in load["restart_keys"]:
        for secondary in load["secondary_load_torques_Nm"]:
            add(
                family="bench_resisting_load",
                restart_key=str(restart_key),
                onset_s=0.0,
                ramp_s=float(load["ramp_s"]),
                secondary_target_torque_Nm=float(secondary),
                bench_secondary_inertia_kg_m2=float(cfg["bench_secondary_inertia_kg_m2"]),
            )

    return cases


def build_boundaries(
    *,
    case: DiscoveryCase,
    route,
    engine,
    road_load,
    constants,
    programme,
):
    from cinder.model.boundaries.shaft import FullThrottleEngineBoundary

    primary = FullThrottleEngineBoundary(
        engine,
        equivalent_rotational_inertia=constants.engine_rotational_inertia,
    )
    secondary = route.TimeProgrammedLockedFinalDriveBoundary(
        road_load=road_load,
        programme=programme,
        direct_secondary_shaft_inertia=constants.gearbox_input_rotational_inertia,
    )

    if case.family == "downhill_engine_braking":
        primary = BlendToTorqueBoundary(
            primary,
            onset_s=case.onset_s,
            ramp_s=case.ramp_s,
            target_torque_Nm=float(case.primary_target_torque_Nm),
            label="primary_braking_target",
        )
    elif case.family == "bench_backdrive":
        primary = BlendToTorqueBoundary(
            primary,
            onset_s=case.onset_s,
            ramp_s=case.ramp_s,
            target_torque_Nm=float(case.primary_target_torque_Nm),
            label="primary_bench_target",
        )
        secondary = PrescribedTorqueBoundary(
            equivalent_inertia=float(case.bench_secondary_inertia_kg_m2),
            onset_s=case.onset_s,
            ramp_s=case.ramp_s,
            initial_torque_Nm=0.0,
            target_torque_Nm=float(case.secondary_target_torque_Nm),
            label="secondary_bench_drive",
        )
    elif case.family == "bench_resisting_load":
        secondary = PrescribedTorqueBoundary(
            equivalent_inertia=float(case.bench_secondary_inertia_kg_m2),
            onset_s=case.onset_s,
            ramp_s=case.ramp_s,
            initial_torque_Nm=0.0,
            target_torque_Nm=float(case.secondary_target_torque_Nm),
            label="secondary_bench_load",
        )

    return primary, secondary


def run_legacy_hill_replays(
    *,
    cfg: dict[str, Any],
    quick: bool,
    route,
    ab,
    assembly,
    engine,
    road_load,
    constants,
    near_margin: float,
):
    replay_cfg = cfg.get("legacy_hill_replays", {})
    solver = replay_cfg.get("solver", {})
    summaries: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []

    for spec in legacy_hill_specs(cfg, quick=quick):
        case_id = str(spec["case_id"])
        family = "legacy_hill_replay"
        programme = build_legacy_hill_programme(route, spec)
        duration_s = float(programme.end_time_s)
        analysis_start = float(spec.get("analysis_start_s", 0.0))
        analysis_end_raw = spec.get("analysis_end_s")
        analysis_end = (
            float(analysis_end_raw) if analysis_end_raw is not None else duration_s
        )

        try:
            run, raw_result, _status = run_slotted_full_launch_programme(
                route=route,
                ab=ab,
                assembly=assembly,
                engine=engine,
                road_load=road_load,
                constants=constants,
                programme=programme,
                duration_s=duration_s,
                sample_step_s=float(solver.get("sample_step_s", 0.001)),
                rtol=float(solver.get("relative_tolerance", 3.0e-4)),
                atol=float(solver.get("absolute_tolerance", 3.0e-7)),
                max_step_s=float(solver.get("max_step_s", 0.003)),
                maximum_transitions=int(solver.get("maximum_transitions", 500)),
            )
        except Exception as exc:
            summaries.append(
                {
                    "case_id": case_id,
                    "family": family,
                    "status": "exception",
                    "error": f"{type(exc).__name__}: {exc}",
                    "replay_kind": spec.get("kind"),
                    "description": spec.get("description"),
                }
            )
            continue

        if run is None:
            summaries.append(
                {
                    "case_id": case_id,
                    "family": family,
                    "status": "integration_failed",
                    "error": raw_result.termination_reason,
                    "replay_kind": spec.get("kind"),
                    "description": spec.get("description"),
                }
            )
            continue

        rows = [sample.row for sample in run.samples]
        for row in rows:
            t = float(row["time_s"])
            row.update(
                {
                    "scenario_case_id": case_id,
                    "scenario_family": family,
                    "scenario_restart_key": "full_natural_launch",
                    "scenario_grade_target_deg": spec.get("target_grade_deg", 30.0),
                    "scenario_primary_target_torque_Nm": None,
                    "scenario_secondary_target_torque_Nm": None,
                    "scenario_onset_s": analysis_start,
                    "scenario_ramp_s": spec.get("ramp_s", 2.0),
                    "scenario_hold_s": spec.get("hold_s"),
                    "grade_deg": math.degrees(programme.grade_radians(t)),
                    "route_phase": programme_phase_name(programme, t),
                }
            )
        traces.extend(rows)
        for record in run.result.transitions:
            transitions.append(
                {
                    "case_id": case_id,
                    "family": family,
                    "time_s": float(record.time),
                    "route_phase": programme_phase_name(programme, float(record.time)),
                    "transition_type": type(record.transition).__name__,
                    "transition": str(record.transition),
                    "has_successor_state": bool(
                        getattr(record.transition, "has_successor_state", False)
                    ),
                }
            )

        route_metrics = contact_topology_metrics(
            rows,
            case_start_s=0.0,
            case_end_s=duration_s,
        )
        analysis_rows = _rows_between(rows, analysis_start, analysis_end)
        analysis_metrics = contact_topology_metrics(
            analysis_rows,
            case_start_s=analysis_start,
            case_end_s=analysis_end,
        )
        decomposition = minimum_margin_decomposition(analysis_rows)
        summary = {
            "case_id": case_id,
            "family": family,
            "status": "completed",
            "classification": classify(analysis_metrics, near_margin_Nm=near_margin),
            "route_classification": classify(route_metrics, near_margin_Nm=near_margin),
            "response_class": response_class(run.result, analysis_start),
            "replay_kind": spec.get("kind"),
            "description": spec.get("description"),
            "restart_key": "full_natural_launch",
            "restart_actual_shift_percent": None,
            "restart_conditioning_time_s": None,
            "onset_s": analysis_start,
            "analysis_end_s": analysis_end,
            "duration_s": duration_s,
            "grade_target_deg": spec.get("target_grade_deg", 30.0),
            "primary_target_torque_Nm": None,
            "secondary_target_torque_Nm": None,
            "bench_secondary_inertia_kg_m2": None,
            "transition_count_after_onset": sum(
                analysis_start <= float(record.time) <= analysis_end
                for record in run.result.transitions
            ),
            "reset_count_after_onset": sum(
                analysis_start <= float(record.time) <= analysis_end
                and getattr(record.transition, "has_successor_state", False)
                for record in run.result.transitions
            ),
            "shift_excursion_mm_after_onset": _range(analysis_rows, "shift_mm"),
            "minimum_secondary_normal_N_after_onset": _min(
                analysis_rows, "normal_secondary_N"
            ),
            "max_abs_lambda_primary_after_onset": _max_abs(
                analysis_rows, "lambda_primary"
            ),
            "max_abs_lambda_secondary_after_onset": _max_abs(
                analysis_rows, "lambda_secondary"
            ),
            "max_abs_shift_speed_m_s_after_onset": _max_abs(
                analysis_rows, "shift_speed_m_s"
            ),
            "max_abs_helix_force_reconstruction_residual_N": _max_abs(
                analysis_rows, "helix_force_reconstruction_residual_N"
            ),
            **{f"route_{key}": value for key, value in route_metrics.items()},
            **{f"post_{key}": value for key, value in analysis_metrics.items()},
            **decomposition,
        }
        summaries.append(summary)
        print(
            f"{case_id} {family}: {summary['classification']} | "
            f"hill-window min M_h={summary.get('post_minimum_margin_Nm')!r} N m | "
            f"whole-route min M_h={summary.get('route_minimum_margin_Nm')!r} N m | "
            f"driver={summary.get('minimum_margin_dominant_negative_term')}"
        )

    return summaries, traces, transitions


def shortlist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed = [row for row in rows if row.get("status") == "completed"]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def keep(role: str, row: dict[str, Any]) -> None:
        key = str(row["case_id"])
        token = f"{role}:{key}"
        if token in seen:
            return
        seen.add(token)
        selected.append({"selection_role": role, **row})

    for family in sorted({str(row["family"]) for row in completed}):
        fam = [row for row in completed if row["family"] == family]
        positive = [
            row for row in fam
            if row.get("post_minimum_margin_Nm") is not None
            and float(row["post_minimum_margin_Nm"]) >= 0.0
        ]
        if positive:
            keep(
                f"{family}:nearest_positive_boundary",
                min(positive, key=lambda row: abs(float(row["post_minimum_margin_Nm"]))),
            )
        reversal = [
            row for row in fam
            if row.get("classification") == "opposite_flank_required"
        ]
        if reversal:
            clean = [row for row in reversal if row.get("response_class") == "clean_continuous"]
            pool = clean or reversal
            keep(
                f"{family}:mild_reversal",
                min(pool, key=lambda row: float(row["post_I_opp_tau_Nm_s"])),
            )
            keep(
                f"{family}:strong_reversal",
                max(pool, key=lambda row: float(row["post_I_opp_tau_Nm_s"])),
            )

    # Ensure the strongest inertia-driven case is easy to find even if its
    # family-level selection happened to be controlled by belt torque instead.
    inertial = [
        row for row in completed
        if row.get("minimum_margin_dominant_negative_term")
        in {"shaft_acceleration", "shift_acceleration", "profile_curvature"}
    ]
    if inertial:
        keep(
            "overall:strongest_inertial_driver",
            min(inertial, key=lambda row: float(row["post_minimum_margin_Nm"])),
        )

    return selected


def main() -> int:
    args = parse_args()
    verify_environment()
    study = load_json(STUDY_ROOT / "study.json")
    cfg = study["experiments"]["scenario_discovery"]
    forward_cfg = study["experiments"]["forward_control"]
    forward_solver = forward_cfg["solver"]
    solver = cfg["solver"]

    conditioning, resolved, assembly, engine, road_load, ab, route = run_flat_slotted_reference(
        duration_s=float(cfg["conditioning_duration_s"]),
        sample_step_s=float(forward_cfg["sample_step_s"]),
        rtol=float(forward_solver["relative_tolerance"]),
        atol=float(forward_solver["absolute_tolerance"]),
        max_step_s=float(forward_solver["max_step_s"]),
    )

    restarts: dict[str, Restart] = {}
    for target in cfg["ratio_restart_shift_percents"]:
        key = f"s{int(round(float(target))):02d}"
        restarts[key] = select_restart(
            conditioning,
            float(target),
            maximum_error_percent=float(cfg["restart_maximum_error_percent"]),
        )
    dynamic_restart, dynamic_score = select_dynamic_restart(conditioning)
    restarts["dynamic"] = dynamic_restart

    restart_rows = []
    for key, restart in restarts.items():
        restart_rows.append(
            {
                "restart_key": key,
                "selection_basis": (
                    "maximum_natural_helix_dynamic_term_sum"
                    if key == "dynamic"
                    else "target_shift_fraction"
                ),
                "target_shift_percent": restart.target_shift_percent,
                "actual_shift_percent": restart.actual_shift_percent,
                "conditioning_time_s": restart.time_s,
                "dynamic_selection_score_Nm": dynamic_score if key == "dynamic" else None,
            }
        )

    cases = build_cases(cfg, quick=bool(args.quick))
    summaries: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    transition_rows: list[dict[str, Any]] = []
    near_margin = float(cfg["near_boundary_margin_Nm"])

    for case in cases:
        restart = restarts[case.restart_key]
        programme = transient_grade_programme(
            route,
            onset_s=case.onset_s,
            ramp_s=case.ramp_s,
            hold_s=case.hold_s,
            target_degrees=case.grade_target_deg,
        )
        primary, secondary = build_boundaries(
            case=case,
            route=route,
            engine=engine,
            road_load=road_load,
            constants=resolved.constants,
            programme=programme,
        )
        max_step_s = min(
            float(solver["maximum_step_cap_s"]),
            max(float(solver["minimum_max_step_s"]), case.ramp_s / 6.0),
        )

        try:
            run, raw_result, _status = run_custom_restart_case(
                route=route,
                ab=ab,
                restart=restart,
                assembly=assembly,
                engine=engine,
                road_load=road_load,
                constants=resolved.constants,
                programme=programme,
                duration_s=case.duration_s,
                sample_step_s=float(solver["sample_step_s"]),
                rtol=float(solver["relative_tolerance"]),
                atol=float(solver["absolute_tolerance"]),
                max_step_s=max_step_s,
                primary_boundary=primary,
                secondary_boundary=secondary,
                reclassify_initial_mode=case.family.startswith("bench_"),
            )
        except Exception as exc:
            summaries.append(
                {
                    "case_id": case.case_id,
                    "family": case.family,
                    "status": "exception",
                    "error": f"{type(exc).__name__}: {exc}",
                    "restart_key": case.restart_key,
                    "grade_target_deg": case.grade_target_deg,
                    "primary_target_torque_Nm": case.primary_target_torque_Nm,
                    "secondary_target_torque_Nm": case.secondary_target_torque_Nm,
                    "ramp_s": case.ramp_s,
                }
            )
            continue

        if run is None:
            summaries.append(
                {
                    "case_id": case.case_id,
                    "family": case.family,
                    "status": "integration_failed",
                    "error": raw_result.termination_reason,
                    "restart_key": case.restart_key,
                    "grade_target_deg": case.grade_target_deg,
                    "primary_target_torque_Nm": case.primary_target_torque_Nm,
                    "secondary_target_torque_Nm": case.secondary_target_torque_Nm,
                    "ramp_s": case.ramp_s,
                }
            )
            continue

        rows = [sample.row for sample in run.samples]
        for row in rows:
            row.update(
                {
                    "scenario_case_id": case.case_id,
                    "scenario_family": case.family,
                    "scenario_restart_key": case.restart_key,
                    "scenario_grade_target_deg": case.grade_target_deg,
                    "scenario_primary_target_torque_Nm": case.primary_target_torque_Nm,
                    "scenario_secondary_target_torque_Nm": case.secondary_target_torque_Nm,
                    "scenario_onset_s": case.onset_s,
                    "scenario_ramp_s": case.ramp_s,
                    "scenario_hold_s": case.hold_s,
                    "grade_deg": math.degrees(programme.grade_radians(float(row["time_s"]))),
                }
            )
        traces.extend(rows)
        for record in run.result.transitions:
            transition_rows.append(
                {
                    "case_id": case.case_id,
                    "family": case.family,
                    "time_s": float(record.time),
                    "transition_type": type(record.transition).__name__,
                    "transition": str(record.transition),
                    "has_successor_state": bool(
                        getattr(record.transition, "has_successor_state", False)
                    ),
                }
            )

        metrics = contact_topology_metrics(
            rows,
            case_start_s=0.0,
            case_end_s=case.duration_s,
        )
        post_rows = _rows_after(rows, case.onset_s)
        post_metrics = contact_topology_metrics(
            post_rows,
            case_start_s=case.onset_s,
            case_end_s=case.duration_s,
        )
        decomposition = minimum_margin_decomposition(post_rows)
        force_residual = _max_abs(post_rows, "helix_force_reconstruction_residual_N")
        summary = {
            "case_id": case.case_id,
            "family": case.family,
            "status": "completed",
            "classification": classify(post_metrics, near_margin_Nm=near_margin),
            "response_class": response_class(run.result, case.onset_s),
            "restart_key": case.restart_key,
            "restart_actual_shift_percent": restart.actual_shift_percent,
            "restart_conditioning_time_s": restart.time_s,
            "onset_s": case.onset_s,
            "ramp_s": case.ramp_s,
            "hold_s": case.hold_s,
            "duration_s": case.duration_s,
            "grade_target_deg": case.grade_target_deg,
            "primary_target_torque_Nm": case.primary_target_torque_Nm,
            "secondary_target_torque_Nm": case.secondary_target_torque_Nm,
            "bench_secondary_inertia_kg_m2": case.bench_secondary_inertia_kg_m2,
            "transition_count_after_onset": sum(
                float(record.time) >= case.onset_s for record in run.result.transitions
            ),
            "reset_count_after_onset": sum(
                float(record.time) >= case.onset_s
                and getattr(record.transition, "has_successor_state", False)
                for record in run.result.transitions
            ),
            "shift_excursion_mm_after_onset": _range(post_rows, "shift_mm"),
            "minimum_secondary_normal_N_after_onset": _min(post_rows, "normal_secondary_N"),
            "max_abs_lambda_primary_after_onset": _max_abs(post_rows, "lambda_primary"),
            "max_abs_lambda_secondary_after_onset": _max_abs(post_rows, "lambda_secondary"),
            "max_abs_shift_speed_m_s_after_onset": _max_abs(post_rows, "shift_speed_m_s"),
            "max_abs_helix_force_reconstruction_residual_N": force_residual,
            **metrics,
            **{f"post_{key}": value for key, value in post_metrics.items()},
            **decomposition,
        }
        summaries.append(summary)
        print(
            f"{case.case_id} {case.family}: {summary['classification']} | "
            f"min M_h={summary.get('post_minimum_margin_Nm')!r} N m | "
            f"driver={summary.get('minimum_margin_dominant_negative_term')}"
        )

    legacy_summaries, legacy_traces, legacy_transitions = run_legacy_hill_replays(
        cfg=cfg,
        quick=bool(args.quick),
        route=route,
        ab=ab,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=resolved.constants,
        near_margin=near_margin,
    )

    out = ARTIFACTS / "scenario-discovery"
    out.mkdir(parents=True, exist_ok=True)
    write_rows(out / "restart_states.csv", restart_rows)
    write_rows(out / "scenario_summary.csv", summaries)
    write_rows(out / "scenario_trace.csv", traces)
    write_rows(out / "scenario_transitions.csv", transition_rows)
    write_rows(out / "legacy_hill_summary.csv", legacy_summaries)
    write_rows(out / "legacy_hill_trace.csv", legacy_traces)
    write_rows(out / "legacy_hill_transitions.csv", legacy_transitions)
    for legacy in legacy_summaries:
        if legacy.get("status") != "completed":
            continue
        case_id = str(legacy["case_id"])
        case_rows = [
            row for row in legacy_traces
            if str(row.get("scenario_case_id")) == case_id
        ]
        if not case_rows:
            continue
        times = [float(row["time_s"]) for row in case_rows]
        margins = [float(row["helix_reacted_torque_margin_Nm"]) for row in case_rows]
        grades = [float(row["grade_deg"]) for row in case_rows]
        fig, ax = plt.subplots(figsize=(11.0, 5.5))
        ax.plot(times, margins, label="selected-flank margin M_h")
        ax.axhline(0.0, linewidth=1.0)
        ax.axvspan(
            float(legacy["onset_s"]),
            float(legacy["analysis_end_s"]),
            alpha=0.08,
            label="hill analysis window",
        )
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("M_h [N m]")
        ax.grid(True, alpha=0.25)
        ax2 = ax.twinx()
        ax2.plot(times, grades, linestyle="--", label="grade")
        ax2.set_ylabel("Grade [deg]")
        ax.set_title(case_id.replace("_", " "))
        handles1, labels1 = ax.get_legend_handles_labels()
        handles2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(handles1 + handles2, labels1 + labels2, loc="best", fontsize=8)
        fig.tight_layout()
        fig.savefig(out / f"{case_id}_margin_and_grade.png", dpi=180)
        plt.close(fig)

    selected = shortlist(summaries + legacy_summaries)
    write_rows(out / "candidate_shortlist.csv", selected)

    completed = [row for row in summaries if row.get("status") == "completed"]
    aggregate = {
        "stage": "E4",
        "quick": bool(args.quick),
        "case_count": len(cases) + len(legacy_hill_specs(cfg, quick=bool(args.quick))),
        "short_restart_case_count": len(cases),
        "legacy_hill_case_count": len(legacy_hill_specs(cfg, quick=bool(args.quick))),
        "completed_cases": len(completed) + sum(
            row.get("status") == "completed" for row in legacy_summaries
        ),
        "failed_cases": (len(summaries) - len(completed)) + sum(
            row.get("status") != "completed" for row in legacy_summaries
        ),
        "families": {},
        "shortlist_case_ids": [row["case_id"] for row in selected],
        "dynamic_restart": {
            "actual_shift_percent": dynamic_restart.actual_shift_percent,
            "conditioning_time_s": dynamic_restart.time_s,
            "dynamic_term_score_Nm": dynamic_score,
        },
        "legacy_hill_replays": {
            "completed": sum(row.get("status") == "completed" for row in legacy_summaries),
            "opposite_flank_required_in_hill_window": sum(
                row.get("classification") == "opposite_flank_required"
                for row in legacy_summaries
                if row.get("status") == "completed"
            ),
            "case_ids": [row.get("case_id") for row in legacy_summaries],
        },
        "note": (
            "Broad discovery under the slotted topology only. Negative M_h is a "
            "would-be selected-flank lift-off condition, not detached motion."
        ),
    }
    for family in sorted({case.family for case in cases}):
        fam = [row for row in completed if row["family"] == family]
        aggregate["families"][family] = {
            "completed": len(fam),
            "opposite_flank_required": sum(
                row.get("classification") == "opposite_flank_required" for row in fam
            ),
            "near_boundary": sum(row.get("classification") == "near_boundary" for row in fam),
            "one_flank": sum(row.get("classification") == "one_flank" for row in fam),
        }
    (out / "summary.json").write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")

    # One compact family-level diagnostic: minimum post-onset margin by case.
    fig, ax = plt.subplots(figsize=(11.0, 6.0))
    families = sorted({row["family"] for row in completed})
    x_cursor = 0
    ticks = []
    labels = []
    for family in families:
        fam = [row for row in completed if row["family"] == family]
        fam.sort(key=lambda row: float(row["post_minimum_margin_Nm"]))
        xs = list(range(x_cursor, x_cursor + len(fam)))
        ys = [float(row["post_minimum_margin_Nm"]) for row in fam]
        ax.scatter(xs, ys, label=family)
        if xs:
            ticks.append(0.5 * (xs[0] + xs[-1]))
            labels.append(family.replace("_", "\n"))
        x_cursor += len(fam) + 1
    ax.axhline(0.0, linewidth=1.0)
    ax.set_ylabel("Post-onset minimum selected-flank margin $M_h$ [N m]")
    ax.set_title("E4 multi-family helix reaction discovery")
    ax.set_xticks(ticks, labels)
    ax.grid(True, axis="y", alpha=0.25)
    if families:
        ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "minimum_margin_by_family.png", dpi=180)
    plt.close(fig)

    write_reference_provenance(
        out / "provenance",
        plant=conditioning.system.cvt.model,
        extra={
            "study_stage": "E4_scenario_discovery",
            "configuration": cfg,
            "quick": bool(args.quick),
            "interpretation": "slotted multi-family mechanism discovery only",
        },
    )
    print(json.dumps(aggregate, indent=2))
    print(f"Wrote E4 scenario-discovery artifacts to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
