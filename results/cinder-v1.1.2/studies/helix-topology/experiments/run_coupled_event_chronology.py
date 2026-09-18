"""E5.7: coupled helix / clamp / traction chronology from E5.6 artifacts.

This stage is intentionally post-processing only.  It does not re-integrate the
CVT.  It answers two questions from the completed E5.6 severity sweep:

1. Near reverse-power helix-flank reversal, how do helix reaction, secondary
   actuator closing force, pulley normal force, and belt traction evolve?
2. With the stock 300 deg torsional preload, how large are the dynamic helix
   terms while the belt is still sticking, and what happens when slip follows?

The script selects exemplars algorithmically from E5.6 so the analysis remains
reproducible if the severity matrix is regenerated.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY_ROOT = HERE.parent
DEFAULT_ARTIFACTS = STUDY_ROOT / "artifacts"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_ARTIFACTS / "transient-severity-race",
        help="E5.6 artifact directory containing case_summary.csv and retained_trace.csv.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_ARTIFACTS / "coupled-event-chronology",
        help="Output directory for E5.7 analysis artifacts.",
    )
    return p.parse_args()


def f(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_rows(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def select_reversal_exemplar(rows: list[dict[str, str]]) -> dict[str, str]:
    candidates = []
    for row in rows:
        if row.get("status") != "completed":
            continue
        if row.get("event_order") != "simultaneous_or_unresolved":
            continue
        qs = f(row.get("qs_margin_at_first_full_crossing_Nm"))
        dt = f(row.get("helix_minus_traction_event_time_s"))
        if qs is None or qs <= 0.0 or dt is None:
            continue
        if not truthy(row.get("dynamic_only_at_first_full_crossing")):
            continue
        preload = f(row.get("preload_deg"))
        if preload is None:
            continue
        candidates.append((preload, -abs(dt), qs, row))
    if not candidates:
        raise RuntimeError("No E5.6 dynamic-only simultaneous reversal exemplar is available.")
    # Prefer the highest (most stock-like) preload, then the tightest event race.
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return candidates[0][3]


def select_stock_exemplar(rows: list[dict[str, str]], *, preload_deg: float) -> dict[str, str]:
    candidates = []
    for row in rows:
        if row.get("status") != "completed":
            continue
        preload = f(row.get("preload_deg"))
        shift_term = f(row.get("pretraction_minimum_shift_accel_term_Nm"))
        if preload is None or abs(preload - preload_deg) > 1.0e-9 or shift_term is None:
            continue
        candidates.append((shift_term, row))
    if not candidates:
        raise RuntimeError(f"No completed E5.6 cases exist at stock preload {preload_deg:g} deg.")
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


TRACE_FLOAT_FIELDS = {
    "time_s",
    "helix_reacted_torque_margin_Nm",
    "helix_quasi_static_margin_Nm",
    "helix_dynamic_correction_Nm",
    "helix_full_reaction_force_N",
    "secondary_actuator_closing_force_N",
    "normal_secondary_N",
    "lambda_primary",
    "lambda_secondary",
    "helix_shaft_accel_reaction_torque_Nm",
    "helix_shift_accel_reaction_torque_Nm",
    "helix_curvature_reaction_torque_Nm",
    "helix_secondary_internal_power_W",
    "helix_shift_acceleration_m_s2",
    "helix_secondary_angular_acceleration_rad_s2",
    "tau_secondary_belt_Nm",
}


def load_selected_traces(path: Path, case_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    traces = {case_id: [] for case_id in case_ids}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            case_id = raw.get("e56_case_id", "")
            if case_id not in traces:
                continue
            if raw.get("model") not in {None, "", "full"}:
                continue
            row: dict[str, Any] = {
                "case_id": case_id,
                "contact_mode": raw.get("cvt_mode", raw.get("mode", "")),
            }
            for key in TRACE_FLOAT_FIELDS:
                row[key] = f(raw.get(key))
            traces[case_id].append(row)
    for rows in traces.values():
        rows.sort(key=lambda r: float(r["time_s"]) if r["time_s"] is not None else math.inf)
    missing = [case_id for case_id, rows in traces.items() if not rows]
    if missing:
        raise RuntimeError("Selected E5.6 traces were not retained for: " + ", ".join(missing))
    return traces


def nearest_row(rows: list[dict[str, Any]], time_s: float) -> dict[str, Any]:
    return min(rows, key=lambda r: abs(float(r["time_s"]) - time_s))


def window(rows: list[dict[str, Any]], center_s: float, half_width_s: float) -> list[dict[str, Any]]:
    return [
        r for r in rows
        if r["time_s"] is not None and abs(float(r["time_s"]) - center_s) <= half_width_s
    ]


def array(rows: list[dict[str, Any]], key: str) -> np.ndarray:
    return np.asarray([np.nan if r.get(key) is None else float(r[key]) for r in rows], dtype=float)


def plot_reversal_chronology(
    out: Path,
    summary: dict[str, str],
    rows: list[dict[str, Any]],
    *,
    mu_static: float,
    window_s: float,
) -> None:
    crossing = f(summary.get("crossing_time_s"))
    traction = f(summary.get("traction_exit_time_s"))
    if crossing is None:
        raise RuntimeError("Reversal exemplar has no crossing_time_s.")
    rows = window(rows, crossing, window_s)
    t_ms = 1000.0 * (array(rows, "time_s") - crossing)

    fig, axes = plt.subplots(4, 1, figsize=(10.0, 11.5), sharex=True)

    axes[0].plot(t_ms, array(rows, "helix_reacted_torque_margin_Nm"), label="Full $M_h$")
    axes[0].plot(t_ms, array(rows, "helix_quasi_static_margin_Nm"), label="$M_{h,QS}$")
    axes[0].plot(t_ms, array(rows, "helix_dynamic_correction_Nm"), label="Dynamic correction")
    axes[0].axhline(0.0, linewidth=1.0)
    axes[0].set_ylabel("Helix torque [N m]")
    axes[0].legend(fontsize=8, ncol=3)

    axes[1].plot(t_ms, array(rows, "helix_full_reaction_force_N"), label="Helix axial reaction")
    axes[1].plot(t_ms, array(rows, "secondary_actuator_closing_force_N"), label="Total secondary actuator closing")
    axes[1].plot(t_ms, array(rows, "normal_secondary_N"), label="Secondary normal resultant")
    axes[1].axhline(0.0, linewidth=1.0)
    axes[1].set_ylabel("Force [N]")
    axes[1].legend(fontsize=8, ncol=3)

    axes[2].plot(t_ms, np.abs(array(rows, "lambda_primary")), label="$|\\lambda_p|$")
    axes[2].plot(t_ms, np.abs(array(rows, "lambda_secondary")), label="$|\\lambda_s|$")
    axes[2].axhline(mu_static, linewidth=1.0, linestyle="--", label="$\\mu_s$")
    axes[2].set_ylabel("Traction ratio")
    axes[2].legend(fontsize=8, ncol=3)

    axes[3].plot(t_ms, array(rows, "helix_shift_accel_reaction_torque_Nm"), label="Shift acceleration")
    axes[3].plot(t_ms, array(rows, "helix_shaft_accel_reaction_torque_Nm"), label="Shaft acceleration")
    axes[3].plot(t_ms, array(rows, "helix_curvature_reaction_torque_Nm"), label="Curvature")
    axes[3].axhline(0.0, linewidth=1.0)
    axes[3].set_ylabel("Dynamic term [N m]")
    axes[3].set_xlabel("Time relative to helix zero crossing [ms]")
    axes[3].legend(fontsize=8, ncol=3)

    for ax in axes:
        ax.axvline(0.0, linewidth=1.2, linestyle="--", label="helix zero")
        if traction is not None:
            ax.axvline(1000.0 * (traction - crossing), linewidth=1.0, linestyle=":")
        ax.grid(True, alpha=0.25)

    fig.suptitle(
        f"Reverse-power coupled chronology: {summary['case_id']}\n"
        "dashed = helix M_h=0; dotted = first traction exit"
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out / "reversal_coupled_chronology.png", dpi=180)
    plt.close(fig)


def plot_stock_dynamics(
    out: Path,
    summary: dict[str, str],
    rows: list[dict[str, Any]],
    *,
    mu_static: float,
    window_s: float,
) -> dict[str, Any]:
    stick_rows = [r for r in rows if "STICK_STICK" in str(r.get("contact_mode", "")).upper()]
    if not stick_rows:
        stick_rows = rows
    trigger = min(
        stick_rows,
        key=lambda r: math.inf if r.get("helix_shift_accel_reaction_torque_Nm") is None else float(r["helix_shift_accel_reaction_torque_Nm"]),
    )
    center = float(trigger["time_s"])
    rows = window(rows, center, window_s)
    t_ms = 1000.0 * (array(rows, "time_s") - center)

    fig, axes = plt.subplots(3, 1, figsize=(10.0, 9.0), sharex=True)
    axes[0].plot(t_ms, array(rows, "helix_shift_accel_reaction_torque_Nm"), label="Shift acceleration")
    axes[0].plot(t_ms, array(rows, "helix_shaft_accel_reaction_torque_Nm"), label="Shaft acceleration")
    axes[0].plot(t_ms, array(rows, "helix_curvature_reaction_torque_Nm"), label="Curvature")
    axes[0].plot(t_ms, array(rows, "helix_dynamic_correction_Nm"), label="Total dynamic", linewidth=1.8)
    axes[0].axhline(0.0, linewidth=1.0)
    axes[0].set_ylabel("Dynamic torque [N m]")
    axes[0].legend(fontsize=8, ncol=4)

    axes[1].plot(t_ms, array(rows, "helix_reacted_torque_margin_Nm"), label="Full $M_h$")
    axes[1].plot(t_ms, array(rows, "helix_quasi_static_margin_Nm"), label="$M_{h,QS}$")
    axes[1].axhline(0.0, linewidth=1.0)
    axes[1].set_ylabel("Helix margin [N m]")
    axes[1].legend(fontsize=8)

    axes[2].plot(t_ms, np.abs(array(rows, "lambda_primary")), label="$|\\lambda_p|$")
    axes[2].plot(t_ms, np.abs(array(rows, "lambda_secondary")), label="$|\\lambda_s|$")
    axes[2].axhline(mu_static, linewidth=1.0, linestyle="--", label="$\\mu_s$")
    axes[2].set_ylabel("Traction ratio")
    axes[2].set_xlabel("Time relative to strongest sticking shift-inertia event [ms]")
    axes[2].legend(fontsize=8, ncol=3)

    for ax in axes:
        ax.axvline(0.0, linewidth=1.0, linestyle="--")
        ax.grid(True, alpha=0.25)
    fig.suptitle(f"Stock-preload dynamic helix terms: {summary['case_id']}")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out / "stock_preload_dynamic_terms.png", dpi=180)
    plt.close(fig)

    return {
        "stock_dynamic_event_time_s": center,
        "stock_dynamic_shift_accel_term_Nm": trigger.get("helix_shift_accel_reaction_torque_Nm"),
        "stock_dynamic_shaft_accel_term_Nm": trigger.get("helix_shaft_accel_reaction_torque_Nm"),
        "stock_dynamic_curvature_term_Nm": trigger.get("helix_curvature_reaction_torque_Nm"),
        "stock_dynamic_total_correction_Nm": trigger.get("helix_dynamic_correction_Nm"),
        "stock_dynamic_full_margin_Nm": trigger.get("helix_reacted_torque_margin_Nm"),
        "stock_dynamic_qs_margin_Nm": trigger.get("helix_quasi_static_margin_Nm"),
        "stock_dynamic_lambda_primary": trigger.get("lambda_primary"),
        "stock_dynamic_lambda_secondary": trigger.get("lambda_secondary"),
        "stock_dynamic_normal_secondary_N": trigger.get("normal_secondary_N"),
    }


def plot_crossing_normal_vs_preload(out: Path, rows: list[dict[str, str]]) -> None:
    pts = []
    for row in rows:
        if row.get("status") != "completed":
            continue
        normal = f(row.get("crossing_normal_secondary_N"))
        preload = f(row.get("preload_deg"))
        qs = f(row.get("qs_margin_at_first_full_crossing_Nm"))
        if normal is None or preload is None or qs is None:
            continue
        pts.append((preload, normal, qs > 0.0))
    if not pts:
        return
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    for dynamic_only, label in ((True, "QS still positive at helix crossing"), (False, "QS also non-positive")):
        subset = [(p, n) for p, n, d in pts if d == dynamic_only]
        if subset:
            ax.scatter([p for p, _ in subset], [n for _, n in subset], label=label)
    ax.axhline(0.0, linewidth=1.0)
    ax.set_xlabel("Secondary torsional preload [deg]")
    ax.set_ylabel("Secondary normal resultant at helix crossing [N]")
    ax.set_title("Helix-flank reversal does not require belt normal contact to vanish")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out / "normal_force_at_helix_crossing.png", dpi=180)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    inp = args.input_dir.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    study = json.loads((STUDY_ROOT / "study.json").read_text(encoding="utf-8"))
    cfg = study["experiments"]["coupled_event_chronology"]
    mu_static = float(cfg["static_friction_coefficient"])
    plot_window_s = float(cfg["event_window_s"])

    summaries = read_rows(inp / "case_summary.csv")
    reversal = select_reversal_exemplar(summaries)
    stock = select_stock_exemplar(summaries, preload_deg=float(cfg["stock_preload_deg"]))
    selected_ids = {reversal["case_id"], stock["case_id"]}
    traces = load_selected_traces(inp / "retained_trace.csv", selected_ids)

    crossing = f(reversal.get("crossing_time_s"))
    traction = f(reversal.get("traction_exit_time_s"))
    if crossing is None or traction is None:
        raise RuntimeError("Selected reversal exemplar must contain both helix and traction event clocks.")
    reversal_trace = traces[reversal["case_id"]]
    crossing_row = nearest_row(reversal_trace, crossing)
    traction_row = nearest_row(reversal_trace, traction)

    plot_reversal_chronology(
        out,
        reversal,
        reversal_trace,
        mu_static=mu_static,
        window_s=plot_window_s,
    )
    stock_metrics = plot_stock_dynamics(
        out,
        stock,
        traces[stock["case_id"]],
        mu_static=mu_static,
        window_s=plot_window_s,
    )
    plot_crossing_normal_vs_preload(out, summaries)

    event_rows = []
    for row in summaries:
        if row.get("status") != "completed" or f(row.get("crossing_time_s")) is None:
            continue
        event_rows.append({
            "case_id": row.get("case_id"),
            "preload_deg": f(row.get("preload_deg")),
            "event_order": row.get("event_order"),
            "helix_minus_traction_event_time_us": None if f(row.get("helix_minus_traction_event_time_s")) is None else 1.0e6 * float(row["helix_minus_traction_event_time_s"]),
            "qs_margin_at_helix_crossing_Nm": f(row.get("qs_margin_at_first_full_crossing_Nm")),
            "dynamic_correction_at_helix_crossing_Nm": f(row.get("crossing_helix_dynamic_correction_Nm")),
            "secondary_internal_power_at_helix_crossing_W": f(row.get("crossing_helix_secondary_internal_power_W")),
            "normal_secondary_at_helix_crossing_N": f(row.get("crossing_normal_secondary_N")),
            "lambda_primary_at_helix_crossing": f(row.get("crossing_lambda_primary")),
            "lambda_secondary_at_helix_crossing": f(row.get("crossing_lambda_secondary")),
            "traction_exit_full_margin_before_Nm": f(row.get("traction_exit_full_margin_before_Nm")),
            "traction_exit_qs_margin_before_Nm": f(row.get("traction_exit_qs_margin_before_Nm")),
            "dynamic_only_at_first_full_crossing": truthy(row.get("dynamic_only_at_first_full_crossing")),
        })
    write_rows(out / "helix_traction_event_coupling.csv", event_rows)

    stock_rows = []
    for row in summaries:
        if row.get("status") != "completed":
            continue
        preload = f(row.get("preload_deg"))
        if preload is None or abs(preload - float(cfg["stock_preload_deg"])) > 1.0e-9:
            continue
        stock_rows.append({
            "case_id": row.get("case_id"),
            "restart_key": row.get("restart_key"),
            "perturbation_family": row.get("perturbation_family"),
            "perturbation_value": f(row.get("perturbation_value")),
            "ramp_s": f(row.get("ramp_s")),
            "event_order": row.get("event_order"),
            "pretraction_minimum_dynamic_correction_Nm": f(row.get("pretraction_minimum_dynamic_correction_Nm")),
            "pretraction_minimum_shift_accel_term_Nm": f(row.get("pretraction_minimum_shift_accel_term_Nm")),
            "pretraction_minimum_shaft_accel_term_Nm": f(row.get("pretraction_minimum_shaft_accel_term_Nm")),
            "pretraction_maximum_abs_shift_acceleration_m_s2": f(row.get("pretraction_maximum_abs_shift_acceleration_m_s2")),
            "pretraction_maximum_abs_lambda_primary": f(row.get("pretraction_maximum_abs_lambda_primary")),
            "pretraction_maximum_abs_lambda_secondary": f(row.get("pretraction_maximum_abs_lambda_secondary")),
            "pretraction_minimum_full_margin_Nm": f(row.get("pretraction_minimum_full_margin_Nm")),
            "pretraction_minimum_qs_margin_Nm": f(row.get("pretraction_minimum_qs_margin_Nm")),
        })
    stock_rows.sort(key=lambda r: math.inf if r["pretraction_minimum_shift_accel_term_Nm"] is None else r["pretraction_minimum_shift_accel_term_Nm"])
    write_rows(out / "stock_preload_dynamic_summary.csv", stock_rows)

    dynamic_only_events = [r for r in event_rows if r["dynamic_only_at_first_full_crossing"]]
    crossing_normals = [r["normal_secondary_at_helix_crossing_N"] for r in event_rows if r["normal_secondary_at_helix_crossing_N"] is not None]
    dynamic_only_normals = [r["normal_secondary_at_helix_crossing_N"] for r in dynamic_only_events if r["normal_secondary_at_helix_crossing_N"] is not None]

    summary = {
        "stage": "E5.7",
        "source_stage": "E5.6 transient-severity-race",
        "reruns_cinder": False,
        "question_1": cfg["question_clamp_traction"],
        "question_2": cfg["question_stock_dynamics"],
        "reversal_exemplar_case_id": reversal["case_id"],
        "reversal_exemplar_preload_deg": f(reversal.get("preload_deg")),
        "reversal_event_gap_us": 1.0e6 * (crossing - traction),
        "reversal_qs_margin_at_crossing_Nm": f(reversal.get("qs_margin_at_first_full_crossing_Nm")),
        "reversal_dynamic_correction_at_crossing_Nm": f(reversal.get("crossing_helix_dynamic_correction_Nm")),
        "reversal_secondary_internal_power_W": f(reversal.get("crossing_helix_secondary_internal_power_W")),
        "reversal_normal_secondary_at_crossing_N": f(reversal.get("crossing_normal_secondary_N")),
        "reversal_nearest_trace_normal_secondary_at_crossing_N": crossing_row.get("normal_secondary_N"),
        "reversal_nearest_trace_normal_secondary_at_traction_exit_N": traction_row.get("normal_secondary_N"),
        "reversal_nearest_trace_secondary_actuator_closing_at_crossing_N": crossing_row.get("secondary_actuator_closing_force_N"),
        "reversal_nearest_trace_helix_axial_reaction_at_crossing_N": crossing_row.get("helix_full_reaction_force_N"),
        "reversal_lambda_primary_at_crossing": f(reversal.get("crossing_lambda_primary")),
        "reversal_lambda_secondary_at_crossing": f(reversal.get("crossing_lambda_secondary")),
        "event_case_count_with_helix_crossing": len(event_rows),
        "dynamic_only_crossing_count": len(dynamic_only_events),
        "minimum_secondary_normal_at_any_helix_crossing_N": min(crossing_normals) if crossing_normals else None,
        "minimum_secondary_normal_at_dynamic_only_helix_crossing_N": min(dynamic_only_normals) if dynamic_only_normals else None,
        "normal_contact_zero_seen_at_helix_crossing": bool(crossing_normals and min(crossing_normals) <= 0.0),
        "stock_exemplar_case_id": stock["case_id"],
        "stock_preload_deg": float(cfg["stock_preload_deg"]),
        **stock_metrics,
        "interpretation_guard": (
            "Helix selected-flank lift-off (M_h=0), belt traction saturation (|lambda|=mu_s), "
            "and belt normal contact loss (N_s=0) are distinct events.  E5.7 reports their "
            "measured chronology and does not infer one event from another."
        ),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    notes = f"""# E5.7 Coupled Event Chronology\n\nThis stage performs no new integration. It post-processes E5.6.\n\n## Automatically selected exemplars\n\n- Reverse-power helix/traction chronology: `{reversal['case_id']}`\n- Stock-preload dynamic-term exemplar: `{stock['case_id']}`\n\n## Event definitions\n\n- Helix selected-flank boundary: `M_h = 0`.\n- Belt traction boundary: first departure from stick-stick contact.\n- Belt normal-contact boundary: `N_s = 0`.\n\nThese are intentionally kept separate. The outputs are designed to show whether reduced helix reaction accompanies lower secondary normal force and higher traction utilization, and how the shaft/shift/curvature dynamic torque terms behave before and after slip.\n"""
    (out / "README.md").write_text(notes, encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"Wrote E5.7 coupled-event chronology artifacts to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
