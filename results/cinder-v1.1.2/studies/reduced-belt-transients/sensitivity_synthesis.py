"""Connect direct equation thresholds to simulated Baja operating envelopes."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from study_support import write_json, write_rows

MECHANISMS = (
    {
        "key": "shift_acceleration",
        "label": "shift acceleration",
        "ratio": "sensitivity.actual_to_10pct_activity.shift_acceleration",
        "term": "loop.radial_shift_acceleration_N",
        "driver": "state.shift_acceleration_m_per_s2",
        "coefficient": "loop.response_coefficient.radial_shift_acceleration_N_per_mps2",
        "threshold": "loop.activity_threshold.10pct.shift_acceleration_m_per_s2",
    },
    {
        "key": "path_curvature",
        "label": "shift-path curvature",
        "ratio": "sensitivity.actual_to_10pct_activity.shift_speed_curvature",
        "term": "loop.radial_geometry_curvature_N",
        "driver": "state.shift_speed_m_per_s",
        "coefficient": "loop.response_coefficient.radial_geometry_curvature_N_per_m2ps2",
        "threshold": "loop.activity_threshold.10pct.shift_speed_curvature_m_per_s",
    },
    {
        "key": "belt_acceleration",
        "label": "belt transport acceleration",
        "ratio": "sensitivity.actual_to_10pct_activity.belt_acceleration",
        "term": "loop.tangential_belt_acceleration_N",
        "driver": "state.belt_acceleration_m_per_s2",
        "coefficient": "loop.response_coefficient.tangential_belt_acceleration_N_per_mps2",
        "threshold": "loop.activity_threshold.10pct.belt_acceleration_m_per_s2",
    },
    {
        "key": "moving_radius",
        "label": "moving-radius transport",
        "ratio": "sensitivity.actual_to_10pct_activity.moving_radius_product",
        "term": "loop.tangential_shifting_radius_N",
        "driver": "loop.driver.tangential_shifting_radius_m2ps2",
        "coefficient": "loop.response_coefficient.tangential_shifting_radius_N_per_m2ps2",
        "threshold": "loop.activity_threshold.10pct.shift_speed_times_belt_speed_m2_per_s2",
    },
    {
        "key": "whole_belt_inertia",
        "label": "whole-belt transport inertia",
        "ratio": "sensitivity.actual_to_10pct_activity.transport_belt_acceleration",
        "term": "transport.belt_inertia_N",
        "driver": "state.belt_acceleration_m_per_s2",
        "coefficient": None,
        "threshold": "transport.activity_threshold.10pct.belt_acceleration_m_per_s2",
    },
)


def _float(row: dict[str, str], key: str, default: float = float("nan")) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return default


def _free_stick(row: dict[str, str]) -> bool:
    return row.get("regime.shift_constraint") == "free" and row.get("regime.contact_mode") == "stick_stick"


def _read_case_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def synthesize_sensitivity_connections(
    *,
    artifacts_dir: Path,
    families: dict[str, str],
) -> dict[str, Any]:
    per_case: list[dict[str, Any]] = []
    global_examples: list[dict[str, Any]] = []
    all_rows: dict[str, list[dict[str, str]]] = {}

    for case, family in families.items():
        csv_path = artifacts_dir / case / "belt_terms.csv"
        if not csv_path.is_file():
            continue
        rows = [row for row in _read_case_rows(csv_path) if _free_stick(row)]
        if rows:
            all_rows[case] = rows
        for mechanism in MECHANISMS:
            finite = [
                row for row in rows
                if np.isfinite(_float(row, mechanism["ratio"]))
            ]
            if not finite:
                continue
            ratios = np.asarray([_float(row, mechanism["ratio"]) for row in finite], dtype=float)
            peak_index = int(np.argmax(ratios))
            peak = finite[peak_index]
            record = {
                "case": case,
                "family": family,
                "mechanism": mechanism["key"],
                "sample_count": len(finite),
                "max_actual_to_10pct_threshold": float(np.max(ratios)),
                "p95_actual_to_10pct_threshold": float(np.percentile(ratios, 95.0)),
                "fraction_samples_at_or_above_10pct": float(np.mean(ratios >= 1.0)),
                "peak_time_s": _float(peak, "time_s"),
                "peak_shift_fraction": _float(peak, "state.shift_fraction"),
                "peak_grade_deg": _float(peak, "environment.grade_deg"),
                "peak_contact_static_fraction": _float(peak, "contact.max_static_utilization_fraction"),
                "peak_driver": _float(peak, mechanism["driver"]),
                "peak_10pct_threshold": _float(peak, mechanism["threshold"]),
                "peak_term_N": _float(peak, mechanism["term"]),
                "peak_contact_scale_N": _float(peak, "loop.contact_scale_N"),
                "peak_belt_speed_m_per_s": _float(peak, "state.belt_speed_m_per_s"),
                "peak_shift_speed_m_per_s": _float(peak, "state.shift_speed_m_per_s"),
                "peak_shift_acceleration_m_per_s2": _float(peak, "state.shift_acceleration_m_per_s2"),
                "peak_belt_acceleration_m_per_s2": _float(peak, "state.belt_acceleration_m_per_s2"),
                "peak_primary_lambda": _float(peak, "contact.primary_lambda"),
                "peak_secondary_lambda": _float(peak, "contact.secondary_lambda"),
            }
            if mechanism["coefficient"]:
                record["peak_response_coefficient"] = _float(peak, mechanism["coefficient"])
            per_case.append(record)

    for mechanism in MECHANISMS:
        candidates = [row for row in per_case if row["mechanism"] == mechanism["key"]]
        if candidates:
            global_examples.append(max(candidates, key=lambda row: row["max_actual_to_10pct_threshold"]))

    write_rows(artifacts_dir / "equation_threshold_coverage.csv", per_case)
    write_rows(artifacts_dir / "equation_connection_examples.csv", global_examples)

    # Aggregate only the physically bounded Baja-envelope family for the claim
    # about what reasonable operating conditions actually visit.
    envelope = [row for row in per_case if row["family"] == "baja_envelope"]
    envelope_summary: list[dict[str, Any]] = []
    for mechanism in MECHANISMS:
        group = [row for row in envelope if row["mechanism"] == mechanism["key"]]
        if not group:
            continue
        envelope_summary.append({
            "mechanism": mechanism["key"],
            "case_count": len(group),
            "max_actual_to_10pct_threshold": max(row["max_actual_to_10pct_threshold"] for row in group),
            "p95_of_case_max_actual_to_10pct_threshold": float(np.percentile(
                [row["max_actual_to_10pct_threshold"] for row in group], 95.0
            )),
            "cases_reaching_10pct": sum(row["max_actual_to_10pct_threshold"] >= 1.0 for row in group),
            "cases_reaching_25pct_equivalent": sum(row["max_actual_to_10pct_threshold"] >= 2.5 for row in group),
            "max_fraction_samples_at_or_above_10pct": max(row["fraction_samples_at_or_above_10pct"] for row in group),
        })
    write_rows(artifacts_dir / "baja_envelope_equation_coverage.csv", envelope_summary)

    observed_rows: list[dict[str, Any]] = []
    for case, family in families.items():
        if family != "baja_envelope":
            continue
        protocol_path = artifacts_dir / case / "protocol.json"
        csv_path = artifacts_dir / case / "belt_terms.csv"
        if not protocol_path.is_file() or not csv_path.is_file():
            continue
        import json
        protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
        control = protocol.get("controlled_load", {})
        start = float(control.get("start_time_s", 0.0))
        rows_case = [row for row in _read_case_rows(csv_path) if _free_stick(row)]
        if not rows_case:
            continue
        pre = min(rows_case, key=lambda row: abs(_float(row, "time_s") - start))
        post = [row for row in rows_case if _float(row, "time_s") >= start]
        if not post:
            post = rows_case
        observed_rows.append({
            "case": case,
            "design_source": protocol.get("design_source"),
            "tune_variant": protocol.get("tune_variant"),
            "target_grade_deg": control.get("target_grade_deg"),
            "rise_time_s": control.get("rise_time_s"),
            "start_time_s": start,
            "pre_shift_fraction": _float(pre, "state.shift_fraction"),
            "pre_belt_speed_m_per_s": _float(pre, "state.belt_speed_m_per_s"),
            "pre_primary_speed_rad_per_s": _float(pre, "state.primary_angular_speed_rad_per_s"),
            "pre_secondary_speed_rad_per_s": _float(pre, "state.secondary_angular_speed_rad_per_s"),
            "pre_contact_static_fraction": _float(pre, "contact.max_static_utilization_fraction"),
            "post_min_shift_fraction": min(_float(row, "state.shift_fraction") for row in post),
            "post_max_shift_fraction": max(_float(row, "state.shift_fraction") for row in post),
            "post_min_shift_speed_m_per_s": min(_float(row, "state.shift_speed_m_per_s") for row in post),
            "post_max_shift_speed_m_per_s": max(_float(row, "state.shift_speed_m_per_s") for row in post),
            "post_max_abs_shift_acceleration_m_per_s2": max(abs(_float(row, "state.shift_acceleration_m_per_s2")) for row in post),
            "post_max_abs_belt_acceleration_m_per_s2": max(abs(_float(row, "state.belt_acceleration_m_per_s2")) for row in post),
            "post_max_contact_static_fraction": max(_float(row, "contact.max_static_utilization_fraction") for row in post),
        })
    write_rows(artifacts_dir / "baja_envelope_observed_coverage.csv", observed_rows)

    payload = {
        "threshold_definition": (
            "actual_to_10pct_activity = instantaneous kinematic driver / driver required for that "
            "term to become exactly 10% of total absolute final-equation activity if the other "
            "surviving terms are locally frozen. Gross contact-force thresholds are reported "
            "separately and are not used as the equation-importance verdict."
        ),
        "per_case": per_case,
        "global_connection_examples": global_examples,
        "baja_envelope": envelope_summary,
        "baja_envelope_observed_coverage": observed_rows,
    }
    write_json(artifacts_dir / "equation_to_simulation_synthesis.json", payload)
    _plot_connection_summary(artifacts_dir=artifacts_dir, rows=per_case)
    return payload


def _plot_connection_summary(*, artifacts_dir: Path, rows: list[dict[str, Any]]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return

    envelope = [row for row in rows if row["family"] == "baja_envelope"]
    if not envelope:
        return
    labels = []
    values = []
    for mechanism in MECHANISMS:
        group = [row for row in envelope if row["mechanism"] == mechanism["key"]]
        if group:
            labels.append(mechanism["label"])
            values.append(max(row["max_actual_to_10pct_threshold"] for row in group))
    fig, ax = plt.subplots(figsize=(9.0, 5.4))
    ax.bar(labels, values)
    ax.axhline(1.0, linewidth=1.2, linestyle="--", label="10% final-equation activity threshold")
    ax.set_yscale("log")
    ax.set_ylabel("Largest actual driver / 10% threshold [-]")
    ax.set_title("Baja envelope versus equation-derived growth thresholds")
    ax.tick_params(axis="x", rotation=20)
    ax.legend()
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(artifacts_dir / "baja_envelope_vs_equation_thresholds.png", dpi=180)
    plt.close(fig)

    # Contact demand versus tangential coupling: this shows whether the sweep
    # actually reaches the part of the equation where lambda-sensitive terms grow.
    x = []
    y = []
    for case, case_rows in ((case, _read_case_rows(artifacts_dir / case / "belt_terms.csv")) for case in set(row["case"] for row in envelope)):
        for row in case_rows:
            if not _free_stick(row):
                continue
            demand = _float(row, "contact.max_static_utilization_fraction")
            coefficient = abs(_float(row, "loop.response_coefficient.tangential_belt_acceleration_N_per_mps2"))
            if np.isfinite(demand) and np.isfinite(coefficient):
                x.append(demand)
                y.append(coefficient)
    if x:
        fig, ax = plt.subplots(figsize=(7.0, 5.5))
        ax.scatter(x, y, s=8, alpha=0.35)
        ax.set_xlabel(r"Observed contact demand $\max|\lambda|/\mu_s$ [-]")
        ax.set_ylabel(r"$|K_{\dot{v}_b}|$ [N/(m/s²)]")
        ax.set_title("Baja envelope: contact demand versus tangential coupling")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(artifacts_dir / "contact_demand_vs_belt_acceleration_coupling.png", dpi=180)
        plt.close(fig)
