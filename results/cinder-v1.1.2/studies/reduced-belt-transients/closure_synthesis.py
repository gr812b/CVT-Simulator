"""Synthesis for the final reduced-belt closure studies."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from study_support import write_json, write_rows

MIXED_MODES = {"primary_slip_secondary_stick", "primary_stick_secondary_slip"}
SLIP_MODES = MIXED_MODES | {"both_slip"}


def _read(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _f(row: dict[str, str], key: str, default: float = float("nan")) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return default


def _finite(values):
    return [float(v) for v in values if np.isfinite(float(v))]


def _max(rows: list[dict[str, str]], key: str, *, absolute: bool = False) -> float:
    vals = _finite(_f(row, key) for row in rows)
    if not vals:
        return float("nan")
    return max(abs(v) for v in vals) if absolute else max(vals)


def _contact_synthesis(*, artifacts_dir: Path, families: dict[str, str]) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    examples: list[dict[str, Any]] = []
    modes_seen: set[str] = set()
    stick_pool: list[tuple[str, dict[str, str]]] = []
    for case, family in families.items():
        if family != "contact_closure":
            continue
        rows = _read(artifacts_dir / case / "belt_terms.csv")
        if not rows:
            continue
        engaged = [r for r in rows if r.get("regime.engagement") == "engaged"]
        stick = [r for r in engaged if r.get("regime.contact_mode") == "stick_stick"]
        stick_pool.extend((case, r) for r in stick)
        modes = sorted({r.get("regime.contact_mode", "unknown") for r in engaged})
        modes_seen.update(modes)
        protocol = json.loads((artifacts_dir / case / "protocol.json").read_text(encoding="utf-8"))
        summary = {
            "case": case,
            "primary_flyweight_scale": protocol.get("contact_stress", {}).get("primary_flyweight_scale"),
            "secondary_reaction_scale": protocol.get("contact_stress", {}).get("secondary_reaction_scale"),
            "engaged_sample_count": len(engaged),
            "contact_modes": ";".join(modes),
            "mixed_slip_observed": any(mode in MIXED_MODES for mode in modes),
            "both_slip_observed": "both_slip" in modes,
            "max_stick_primary_utilization": _max(stick, "contact.primary_static_utilization_fraction"),
            "max_stick_secondary_utilization": _max(stick, "contact.secondary_static_utilization_fraction"),
            "max_stick_utilization": _max(stick, "contact.max_static_utilization_fraction"),
            "max_stick_utilization_asymmetry": _max(stick, "contact.utilization_asymmetry"),
            "max_abs_moving_radius_coefficient": _max(engaged, "loop.response_coefficient.tangential_shifting_radius_N_per_m2ps2", absolute=True),
            "max_abs_moving_radius_contribution_N": _max(engaged, "loop.tangential_shifting_radius_N", absolute=True),
            "max_moving_radius_activity_share": _max(engaged, "loop.share.tangential_shifting_radius"),
            "max_belt_acceleration_activity_share": _max(engaged, "loop.share.tangential_belt_acceleration"),
        }
        summaries.append(summary)
        for mode in sorted(SLIP_MODES):
            subset = [r for r in engaged if r.get("regime.contact_mode") == mode]
            if not subset:
                continue
            peak = max(subset, key=lambda r: abs(_f(r, "loop.tangential_shifting_radius_N", 0.0)))
            examples.append({
                "case": case,
                "contact_mode": mode,
                "sample_count": len(subset),
                "peak_time_s": _f(peak, "time_s"),
                "shift_fraction": _f(peak, "state.shift_fraction"),
                "shift_speed_m_per_s": _f(peak, "state.shift_speed_m_per_s"),
                "belt_speed_m_per_s": _f(peak, "state.belt_speed_m_per_s"),
                "primary_lambda": _f(peak, "contact.primary_lambda"),
                "secondary_lambda": _f(peak, "contact.secondary_lambda"),
                "primary_utilization": _f(peak, "contact.primary_static_utilization_fraction"),
                "secondary_utilization": _f(peak, "contact.secondary_static_utilization_fraction"),
                "utilization_asymmetry": _f(peak, "contact.utilization_asymmetry"),
                "moving_radius_coefficient": _f(peak, "loop.response_coefficient.tangential_shifting_radius_N_per_m2ps2"),
                "moving_radius_contribution_N": _f(peak, "loop.tangential_shifting_radius_N"),
                "moving_radius_activity_share": _f(peak, "loop.share.tangential_shifting_radius"),
                "belt_acceleration_contribution_N": _f(peak, "loop.tangential_belt_acceleration_N"),
                "belt_acceleration_activity_share": _f(peak, "loop.share.tangential_belt_acceleration"),
            })
    target_rows: list[dict[str, Any]] = []
    for target in (0.40, 0.60, 0.80, 0.95):
        candidates = [
            (case, row) for case, row in stick_pool
            if np.isfinite(_f(row, "contact.max_static_utilization_fraction"))
        ]
        if not candidates:
            continue
        case, row = min(
            candidates,
            key=lambda item: abs(_f(item[1], "contact.max_static_utilization_fraction") - target),
        )
        target_rows.append({
            "target_static_utilization": target,
            "case": case,
            "time_s": _f(row, "time_s"),
            "actual_static_utilization": _f(row, "contact.max_static_utilization_fraction"),
            "primary_utilization": _f(row, "contact.primary_static_utilization_fraction"),
            "secondary_utilization": _f(row, "contact.secondary_static_utilization_fraction"),
            "utilization_asymmetry": _f(row, "contact.utilization_asymmetry"),
            "shift_fraction": _f(row, "state.shift_fraction"),
            "shift_speed_m_per_s": _f(row, "state.shift_speed_m_per_s"),
            "belt_speed_m_per_s": _f(row, "state.belt_speed_m_per_s"),
            "moving_radius_coefficient": _f(row, "loop.response_coefficient.tangential_shifting_radius_N_per_m2ps2"),
            "moving_radius_activity_share": _f(row, "loop.share.tangential_shifting_radius"),
            "belt_acceleration_activity_share": _f(row, "loop.share.tangential_belt_acceleration"),
        })
    write_rows(artifacts_dir / "contact_closure_summary.csv", summaries)
    write_rows(artifacts_dir / "contact_stick_targets.csv", target_rows)
    write_rows(artifacts_dir / "mixed_slip_examples.csv", examples)
    _plot_contact_closure(artifacts_dir, summaries, examples)
    return {
        "contact_modes_seen": sorted(modes_seen),
        "mixed_slip_found": any(mode in MIXED_MODES for mode in modes_seen),
        "both_slip_found": "both_slip" in modes_seen,
        "case_summaries": summaries,
        "stick_target_examples": target_rows,
        "mixed_slip_examples": examples,
    }



def _plot_contact_closure(artifacts_dir: Path, summaries: list[dict[str, Any]], examples: list[dict[str, Any]]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    if summaries:
        fig, ax = plt.subplots(figsize=(8.5, 5.4))
        x = [float(r.get("max_stick_utilization_asymmetry") or 0.0) for r in summaries]
        y = [100.0 * float(r.get("max_moving_radius_activity_share") or 0.0) for r in summaries]
        ax.scatter(x, y)
        for r, xx, yy in zip(summaries, x, y, strict=True):
            if r.get("mixed_slip_observed") or r.get("both_slip_observed"):
                ax.annotate(str(r["case"]), (xx, yy), fontsize=7, xytext=(3, 3), textcoords="offset points")
        ax.set_xlabel("Maximum primary/secondary traction-utilization asymmetry [-]")
        ax.set_ylabel("Maximum moving-radius equation activity [%]")
        ax.set_title("Does contact asymmetry activate moving-radius transport?")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(artifacts_dir / "contact_asymmetry_vs_moving_radius.png", dpi=180)
        plt.close(fig)
    if examples:
        modes = sorted({str(r["contact_mode"]) for r in examples})
        values = []
        for mode in modes:
            group = [r for r in examples if r["contact_mode"] == mode]
            values.append(100.0 * max(float(r.get("moving_radius_activity_share") or 0.0) for r in group))
        fig, ax = plt.subplots(figsize=(8.0, 5.0))
        ax.bar(modes, values)
        ax.set_ylabel("Peak moving-radius equation activity [%]")
        ax.set_title("Moving-radius transport across realized slip branches")
        ax.tick_params(axis="x", rotation=20)
        ax.grid(True, axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(artifacts_dir / "moving_radius_by_slip_mode.png", dpi=180)
        plt.close(fig)

def _overrun_synthesis(*, artifacts_dir: Path, families: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for case, family in families.items():
        if family != "overrun":
            continue
        rows = _read(artifacts_dir / case / "belt_terms.csv")
        if not rows:
            continue
        post = [r for r in rows if r.get("environment.study_phase") in {"overrun_transition", "overrun_hold"}]
        true_overrun = [
            r for r in post
            if _f(r, "boundary.primary_power_W") < 0.0 and _f(r, "boundary.secondary_power_W") > 0.0
        ]
        active = true_overrun or post
        out.append({
            "case": case,
            "post_sample_count": len(post),
            "true_overrun_sample_count": len(true_overrun),
            "true_overrun_fraction": len(true_overrun) / len(post) if post else 0.0,
            "min_primary_power_W": min((_f(r, "boundary.primary_power_W") for r in post), default=float("nan")),
            "max_secondary_power_W": max((_f(r, "boundary.secondary_power_W") for r in post), default=float("nan")),
            "min_primary_lambda": min((_f(r, "contact.primary_lambda") for r in active), default=float("nan")),
            "max_primary_lambda": max((_f(r, "contact.primary_lambda") for r in active), default=float("nan")),
            "min_secondary_lambda": min((_f(r, "contact.secondary_lambda") for r in active), default=float("nan")),
            "max_secondary_lambda": max((_f(r, "contact.secondary_lambda") for r in active), default=float("nan")),
            "max_abs_belt_acceleration_contribution_N": _max(active, "loop.tangential_belt_acceleration_N", absolute=True),
            "max_abs_moving_radius_contribution_N": _max(active, "loop.tangential_shifting_radius_N", absolute=True),
            "max_shift_acceleration_activity_share": _max(active, "loop.share.radial_shift_acceleration"),
            "max_belt_acceleration_activity_share": _max(active, "loop.share.tangential_belt_acceleration"),
            "max_moving_radius_activity_share": _max(active, "loop.share.tangential_shifting_radius"),
        })
    write_rows(artifacts_dir / "overrun_summary.csv", out)
    return out


def _unique_series(rows: list[dict[str, str]], key: str) -> tuple[np.ndarray, np.ndarray]:
    pairs = sorted(((_f(r, "time_s"), _f(r, key)) for r in rows), key=lambda p: p[0])
    pairs = [(t, v) for t, v in pairs if np.isfinite(t) and np.isfinite(v)]
    if not pairs:
        return np.asarray([]), np.asarray([])
    times = []
    values = []
    for t, v in pairs:
        if times and abs(t - times[-1]) <= 1.0e-12:
            values[-1] = v
        else:
            times.append(t)
            values.append(v)
    return np.asarray(times), np.asarray(values)


def _compare_trajectory(reference: list[dict[str, str]], variant: list[dict[str, str]]) -> dict[str, Any]:
    state_keys = (
        "state.primary_angular_speed_rad_per_s",
        "state.secondary_angular_speed_rad_per_s",
        "state.belt_speed_m_per_s",
        "state.shift_position_m",
        "state.shift_speed_m_per_s",
    )
    result: dict[str, Any] = {}
    tref, _ = _unique_series(reference, state_keys[0])
    tvar, _ = _unique_series(variant, state_keys[0])
    if tref.size < 2 or tvar.size < 2:
        return result
    t0 = max(tref[0], tvar[0])
    t1 = min(tref[-1], tvar[-1])
    grid = np.linspace(t0, t1, 1000)
    for key in state_keys:
        tr, yr = _unique_series(reference, key)
        tv, yv = _unique_series(variant, key)
        if tr.size < 2 or tv.size < 2:
            continue
        a = np.interp(grid, tr, yr)
        b = np.interp(grid, tv, yv)
        error = b - a
        span = max(float(np.ptp(a)), float(np.max(np.abs(a))), 1.0e-12)
        short = key.removeprefix("state.")
        result[f"{short}_rmse"] = float(np.sqrt(np.mean(error**2)))
        result[f"{short}_max_abs_error"] = float(np.max(np.abs(error)))
        result[f"{short}_normalized_rmse"] = float(np.sqrt(np.mean(error**2)) / span)
    return result


def _inertia_synthesis(*, artifacts_dir: Path, families: dict[str, str]) -> list[dict[str, Any]]:
    inertia_cases = [case for case, family in families.items() if family == "inertia_continuation"]
    groups: dict[str, list[str]] = {}
    for case in inertia_cases:
        protocol_path = artifacts_dir / case / "protocol.json"
        if not protocol_path.is_file():
            continue
        protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
        scenario = protocol.get("inertia_continuation", {}).get("scenario")
        if scenario:
            groups.setdefault(str(scenario), []).append(case)
    out: list[dict[str, Any]] = []
    for scenario, cases in groups.items():
        ref_case = next((c for c in cases if json.loads((artifacts_dir/c/"protocol.json").read_text())["inertia_continuation"]["kind"] == "reference"), None)
        if ref_case is None:
            continue
        reference = _read(artifacts_dir / ref_case / "belt_terms.csv")
        ref_run = json.loads((artifacts_dir / ref_case / "run_summary.json").read_text(encoding="utf-8"))
        for case in cases:
            protocol = json.loads((artifacts_dir / case / "protocol.json").read_text(encoding="utf-8"))
            info = protocol["inertia_continuation"]
            variant = _read(artifacts_dir / case / "belt_terms.csv")
            run = json.loads((artifacts_dir / case / "run_summary.json").read_text(encoding="utf-8"))
            row = {
                "scenario": scenario,
                "case": case,
                "kind": info["kind"],
                "scale": info["scale"],
                "completed": run.get("completed"),
                "transition_count": run.get("transition_count"),
                "transition_count_delta": (run.get("transition_count") or 0) - (ref_run.get("transition_count") or 0),
            }
            row.update(_compare_trajectory(reference, variant))
            out.append(row)
    write_rows(artifacts_dir / "inertia_continuation_comparison.csv", out)
    _plot_inertia(artifacts_dir, out)
    return out


def _plot_inertia(artifacts_dir: Path, rows: list[dict[str, Any]]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    for scenario in sorted({r["scenario"] for r in rows}):
        group = [r for r in rows if r["scenario"] == scenario and r["kind"] != "reference"]
        if not group:
            continue
        fig, ax = plt.subplots(figsize=(8.0, 5.2))
        for kind in ("global_transport", "coherent_density"):
            subset = sorted([r for r in group if r["kind"] == kind], key=lambda r: float(r["scale"]))
            if not subset:
                continue
            ax.plot(
                [float(r["scale"]) for r in subset],
                [float(r.get("shift_position_m_normalized_rmse", np.nan)) for r in subset],
                marker="o",
                label=kind.replace("_", " "),
            )
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Retained belt-inertia scale [-]")
        ax.set_ylabel("Shift-position normalized RMSE vs full model [-]")
        ax.set_title(f"Belt-inertia continuation — {scenario.replace('_', ' ')}")
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(artifacts_dir / f"inertia_continuation_{scenario}.png", dpi=180)
        plt.close(fig)


def synthesize_closure(*, artifacts_dir: Path, families: dict[str, str], failures: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    contact = _contact_synthesis(artifacts_dir=artifacts_dir, families=families)
    overrun = _overrun_synthesis(artifacts_dir=artifacts_dir, families=families)
    inertia = _inertia_synthesis(artifacts_dir=artifacts_dir, families=families)
    failures = list(failures or [])
    write_rows(artifacts_dir / "closure_failures.csv", failures)
    payload = {
        "contact": contact,
        "overrun": overrun,
        "inertia_continuation": inertia,
        "failures": failures,
        "interpretation_guardrails": {
            "contact_stress": "friction coefficients are unchanged; clamp mechanics are stressed and CINDER chooses contact regime",
            "overrun": "controlled torque/grade boundary, not a calibrated closed-throttle engine map",
            "global_transport_continuation": "isolation test of the m_b*v_b_dot row; not by itself a physical reduced belt",
            "coherent_density_continuation": "belt density is scaled so global and local belt inertia vanish together",
        },
    }
    write_json(artifacts_dir / "closure_synthesis.json", payload)
    return payload
