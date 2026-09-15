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
            secondary_target_torque_Nm=300.0,
            bench_secondary_inertia_kg_m2=float(cfg["bench_secondary_inertia_kg_m2"]),
        )
        add(
            family="bench_resisting_load",
            restart_key="s50",
            onset_s=0.0,
            ramp_s=0.10,
            secondary_target_torque_Nm=-300.0,
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

    out = ARTIFACTS / "scenario-discovery"
    out.mkdir(parents=True, exist_ok=True)
    write_rows(out / "restart_states.csv", restart_rows)
    write_rows(out / "scenario_summary.csv", summaries)
    write_rows(out / "scenario_trace.csv", traces)
    write_rows(out / "scenario_transitions.csv", transition_rows)
    selected = shortlist(summaries)
    write_rows(out / "candidate_shortlist.csv", selected)

    completed = [row for row in summaries if row.get("status") == "completed"]
    aggregate = {
        "stage": "E4",
        "quick": bool(args.quick),
        "case_count": len(cases),
        "completed_cases": len(completed),
        "failed_cases": len(summaries) - len(completed),
        "families": {},
        "shortlist_case_ids": [row["case_id"] for row in selected],
        "dynamic_restart": {
            "actual_shift_percent": dynamic_restart.actual_shift_percent,
            "conditioning_time_s": dynamic_restart.time_s,
            "dynamic_term_score_Nm": dynamic_score,
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
