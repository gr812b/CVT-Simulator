"""E3: controlled secondary-torque screen for helix zero crossings.

The screen runs only the bilateral/slotted reference topology.  Its purpose is
candidate discovery: identify naturally reachable states and smooth torque
ramps that stay one-flank, graze M_h=0, or require the opposite slot flank.
No slotted-vs-unilateral performance conclusion is made here.
"""
from __future__ import annotations

import argparse
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
    load_json,
    run_flat_slotted_reference,
    run_secondary_torque_probe,
    select_restart,
    verify_environment,
    write_reference_provenance,
    write_rows,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run a three-case smoke matrix at the 50% restart only.",
    )
    return parser.parse_args()


def response_class(result, onset_s: float) -> str:
    post = [record for record in result.transitions if float(record.time) >= onset_s]
    if any(getattr(record.transition, "has_successor_state", False) for record in post):
        return "impact_reset"
    if post:
        return "contact_switching"
    return "clean_continuous"


def _finite_after(rows, key: str, onset_s: float) -> list[float]:
    out = []
    for row in rows:
        try:
            if float(row["time_s"]) < onset_s:
                continue
            value = float(row[key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            out.append(value)
    return out


def classify(metrics: dict[str, Any], *, near_margin_Nm: float) -> str:
    if metrics["opposite_flank_duration_s"] > 1.0e-9:
        return "opposite_flank_required"
    minimum_abs = metrics.get("minimum_absolute_margin_Nm")
    if minimum_abs is not None and float(minimum_abs) <= near_margin_Nm:
        return "near_boundary"
    return "one_flank"


def shortlist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = [
        row for row in rows
        if row.get("status") == "completed"
        and row.get("response_class") == "clean_continuous"
    ]
    selected: list[dict[str, Any]] = []

    positive = [
        row for row in clean
        if row.get("classification") in {"one_flank", "near_boundary"}
        and row.get("post_minimum_margin_Nm") is not None
        and float(row["post_minimum_margin_Nm"]) >= 0.0
    ]
    if positive:
        best = min(positive, key=lambda row: abs(float(row["post_minimum_margin_Nm"])))
        selected.append({"selection_role": "nearest_positive_boundary", **best})

    reversal = [
        row for row in clean
        if row.get("classification") == "opposite_flank_required"
    ]
    if reversal:
        mild = min(reversal, key=lambda row: float(row["post_I_opp_tau_Nm_s"]))
        strong = max(reversal, key=lambda row: float(row["post_I_opp_tau_Nm_s"]))
        selected.append({"selection_role": "mild_clean_reversal", **mild})
        if strong["case_id"] != mild["case_id"]:
            selected.append({"selection_role": "strong_clean_reversal", **strong})

    # Preserve a representative zero-perturbation control if it completed.
    controls = [row for row in clean if abs(float(row["added_secondary_torque_Nm"])) < 1.0e-12]
    if controls:
        selected.append({"selection_role": "zero_perturbation_control", **controls[0]})
    return selected


def main() -> int:
    args = parse_args()
    verify_environment()
    study = load_json(STUDY_ROOT / "study.json")
    cfg = study["experiments"]["stress_screen"]
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

    if args.quick:
        shift_targets = (50.0,)
        amplitudes = (-120.0, 0.0, 120.0)
        ramps = (0.1,)
    else:
        shift_targets = tuple(float(x) for x in cfg["restart_shift_percents"])
        amplitudes = tuple(float(x) for x in cfg["secondary_added_torques_Nm"])
        ramps = tuple(float(x) for x in cfg["ramp_times_s"])

    restarts = {
        target: select_restart(conditioning, target, maximum_error_percent=1.0)
        for target in shift_targets
    }

    summaries: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    near_margin = float(cfg["near_boundary_margin_Nm"])
    onset_s = float(cfg["onset_s"])
    hold_s = float(cfg["hold_s"])

    for target in shift_targets:
        restart = restarts[target]
        for ramp_s in ramps:
            for amplitude in amplitudes:
                case_id = (
                    f"s{int(round(target)):02d}_"
                    f"{'p' if amplitude >= 0.0 else 'm'}{abs(amplitude):g}_"
                    f"r{1000.0*ramp_s:g}ms"
                )
                duration_s = onset_s + ramp_s + hold_s
                max_step_s = min(
                    float(solver["maximum_step_cap_s"]),
                    max(0.00025, ramp_s / 5.0),
                )
                try:
                    run, raw_result, _status = run_secondary_torque_probe(
                        route=route,
                        ab=ab,
                        restart=restart,
                        assembly=assembly,
                        engine=engine,
                        road_load=road_load,
                        constants=resolved.constants,
                        added_torque_Nm=amplitude,
                        onset_s=onset_s,
                        ramp_s=ramp_s,
                        hold_s=hold_s,
                        sample_step_s=float(solver["sample_step_s"]),
                        rtol=float(solver["relative_tolerance"]),
                        atol=float(solver["absolute_tolerance"]),
                        max_step_s=max_step_s,
                    )
                except Exception as exc:
                    summaries.append(
                        {
                            "case_id": case_id,
                            "status": "exception",
                            "error": f"{type(exc).__name__}: {exc}",
                            "restart_target_shift_percent": target,
                            "restart_actual_shift_percent": restart.actual_shift_percent,
                            "added_secondary_torque_Nm": amplitude,
                            "ramp_s": ramp_s,
                        }
                    )
                    continue

                if run is None:
                    summaries.append(
                        {
                            "case_id": case_id,
                            "status": "integration_failed",
                            "error": raw_result.termination_reason,
                            "restart_target_shift_percent": target,
                            "restart_actual_shift_percent": restart.actual_shift_percent,
                            "added_secondary_torque_Nm": amplitude,
                            "ramp_s": ramp_s,
                        }
                    )
                    continue

                rows = [sample.row for sample in run.samples]
                for row in rows:
                    row.update(
                        {
                            "case_id": case_id,
                            "restart_target_shift_percent": target,
                            "restart_actual_shift_percent": restart.actual_shift_percent,
                            "added_secondary_torque_Nm": amplitude,
                            "ramp_s": ramp_s,
                            "onset_s": onset_s,
                        }
                    )
                trace_rows.extend(rows)

                metrics = contact_topology_metrics(
                    rows,
                    case_start_s=0.0,
                    case_end_s=duration_s,
                )
                post_rows = [
                    row for row in rows
                    if float(row.get("time_s", -float("inf"))) >= onset_s
                ]
                post_metrics = contact_topology_metrics(
                    post_rows,
                    case_start_s=onset_s,
                    case_end_s=duration_s,
                )
                lambdas_p = _finite_after(rows, "lambda_primary", onset_s)
                lambdas_s = _finite_after(rows, "lambda_secondary", onset_s)
                shift_mm = _finite_after(rows, "shift_mm", onset_s)
                normal_s = _finite_after(rows, "normal_secondary_N", onset_s)
                residuals = _finite_after(
                    rows, "helix_force_reconstruction_residual_N", onset_s
                )
                summary = {
                    "case_id": case_id,
                    "status": "completed",
                    "classification": classify(post_metrics, near_margin_Nm=near_margin),
                    "response_class": response_class(run.result, onset_s),
                    "restart_target_shift_percent": target,
                    "restart_actual_shift_percent": restart.actual_shift_percent,
                    "restart_time_s": restart.time_s,
                    "added_secondary_torque_Nm": amplitude,
                    "ramp_s": ramp_s,
                    "onset_s": onset_s,
                    "hold_s": hold_s,
                    "duration_s": duration_s,
                    "transition_count_after_onset": sum(
                        float(record.time) >= onset_s for record in run.result.transitions
                    ),
                    "reset_count_after_onset": sum(
                        float(record.time) >= onset_s
                        and getattr(record.transition, "has_successor_state", False)
                        for record in run.result.transitions
                    ),
                    "max_abs_lambda_primary_after_onset": (
                        max(abs(x) for x in lambdas_p) if lambdas_p else None
                    ),
                    "max_abs_lambda_secondary_after_onset": (
                        max(abs(x) for x in lambdas_s) if lambdas_s else None
                    ),
                    "shift_excursion_mm_after_onset": (
                        max(shift_mm) - min(shift_mm) if shift_mm else None
                    ),
                    "minimum_secondary_normal_N_after_onset": (
                        min(normal_s) if normal_s else None
                    ),
                    "max_abs_helix_force_reconstruction_residual_N": (
                        max(abs(x) for x in residuals) if residuals else None
                    ),
                    **metrics,
                    **{f"post_{key}": value for key, value in post_metrics.items()},
                }
                summaries.append(summary)
                print(
                    f"{case_id}: {summary['classification']} "
                    f"post-onset min M_h={summary['post_minimum_margin_Nm']!r} N m, "
                    f"post D_opp={summary['post_D_opp_case']:.4g}"
                )

    out = ARTIFACTS / "stress-screen"
    out.mkdir(parents=True, exist_ok=True)
    write_rows(out / "screen_summary.csv", summaries)
    write_rows(out / "screen_trace.csv", trace_rows)
    selected = shortlist(summaries)
    write_rows(out / "candidate_shortlist.csv", selected)

    completed = [r for r in summaries if r.get("status") == "completed"]
    aggregate = {
        "stage": "E3",
        "quick": bool(args.quick),
        "completed_cases": len(completed),
        "failed_cases": len(summaries) - len(completed),
        "one_flank_cases": sum(r.get("classification") == "one_flank" for r in completed),
        "near_boundary_cases": sum(r.get("classification") == "near_boundary" for r in completed),
        "opposite_flank_required_cases": sum(
            r.get("classification") == "opposite_flank_required" for r in completed
        ),
        "shortlist_case_ids": [r["case_id"] for r in selected],
        "note": "Candidate discovery only; no unilateral detached-topology comparison is made in E3."
    }
    (out / "summary.json").write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")

    fig, ax = plt.subplots(figsize=(9.0, 5.5))
    for target in shift_targets:
        for ramp_s in ramps:
            subset = [
                r for r in completed
                if float(r["restart_target_shift_percent"]) == target
                and abs(float(r["ramp_s"]) - ramp_s) < 1.0e-12
            ]
            if not subset:
                continue
            subset.sort(key=lambda r: float(r["added_secondary_torque_Nm"]))
            ax.plot(
                [float(r["added_secondary_torque_Nm"]) for r in subset],
                [float(r["post_minimum_margin_Nm"]) for r in subset],
                marker="o",
                label=f"{target:g}% shift, {1000*ramp_s:g} ms ramp",
            )
    ax.axhline(0.0, linewidth=1.0)
    ax.set_xlabel("Added secondary-shaft torque [N m]")
    ax.set_ylabel("Post-onset minimum selected-flank margin $M_h$ [N m]")
    ax.set_title("E3 zero-crossing screen")
    ax.grid(True, alpha=0.25)
    if completed:
        ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "minimum_margin_vs_added_torque.png", dpi=180)
    plt.close(fig)

    write_reference_provenance(
        out / "provenance",
        plant=conditioning.system.cvt.model,
        extra={
            "study_stage": "E3_stress_screen",
            "screen_configuration": cfg,
            "quick": bool(args.quick),
            "interpretation": "slotted candidate discovery only",
        },
    )
    print(json.dumps(aggregate, indent=2))
    print(f"Wrote E3 stress-screen artifacts to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
