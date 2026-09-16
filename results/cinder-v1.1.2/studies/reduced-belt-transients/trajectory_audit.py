"""Post-integration final-equation atlas for unchanged CINDER trajectories.

The scientific unit of analysis is the *surviving final equation term*.  This
module adds operating-regime, road-load, ratio, contact-demand, and
coefficient/driver context so broad exploration is not dominated by the common
initial engagement transient.
"""
from __future__ import annotations

from collections import defaultdict
from math import degrees
from pathlib import Path
from typing import Any, Callable

import numpy as np

from belt_terms import inspect_final_belt_terms
from study_support import integrated_abs_share, summarize_channel, write_json, write_rows

TRANSPORT_TERMS = (
    "transport.belt_inertia_N",
    "transport.primary_reaction_N",
    "transport.secondary_reaction_N",
)
LOOP_TRANSIENT_TERMS = (
    "loop.radial_shift_acceleration_N",
    "loop.radial_geometry_curvature_N",
    "loop.tangential_belt_acceleration_N",
    "loop.tangential_shifting_radius_N",
)
LOOP_ALL_TERMS = (*LOOP_TRANSIENT_TERMS, "loop.normal_contact_N")
RESPONSE_COEFFICIENTS = (
    "loop.response_coefficient.radial_shift_acceleration_N_per_mps2",
    "loop.response_coefficient.radial_geometry_curvature_N_per_m2ps2",
    "loop.response_coefficient.tangential_belt_acceleration_N_per_mps2",
    "loop.response_coefficient.tangential_shifting_radius_N_per_m2ps2",
)
SENSITIVITY_RATIOS = (
    "sensitivity.actual_to_10pct.shift_acceleration",
    "sensitivity.actual_to_10pct.shift_speed_curvature",
    "sensitivity.actual_to_10pct.belt_acceleration",
    "sensitivity.actual_to_10pct.moving_radius_product",
    "sensitivity.actual_to_10pct.transport_belt_acceleration",
)

DRIVER_CHANNELS = (
    "loop.driver.radial_shift_acceleration_mps2",
    "loop.driver.radial_geometry_curvature_m2ps2",
    "loop.driver.tangential_belt_acceleration_mps2",
    "loop.driver.tangential_shifting_radius_m2ps2",
)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _sample_indices(count: int, maximum: int) -> np.ndarray:
    if count <= maximum:
        return np.arange(count, dtype=np.int64)
    return np.unique(np.linspace(0, count - 1, maximum, dtype=np.int64))


def _budgets(sizes: list[int], maximum: int) -> tuple[int, ...]:
    total = sum(sizes)
    if total <= maximum:
        return tuple(sizes)
    minimum = 2 if maximum >= 2 * len(sizes) else 1
    result = [min(size, minimum) for size in sizes]
    while sum(result) < maximum:
        candidates = [i for i, size in enumerate(sizes) if result[i] < size]
        if not candidates:
            break
        i = max(candidates, key=lambda j: sizes[j] / max(1, result[j]))
        result[i] += 1
    return tuple(result)


def _boundary_context(builder: Any, *, time: float, full_state: np.ndarray) -> tuple[Any, dict[str, Any]]:
    boundaries = builder._shaft_boundaries_for_sample(time=time, full_state=full_state)
    context: dict[str, Any] = {}
    if boundaries is None:
        return boundaries, context
    secondary = getattr(boundaries, "secondary", None)
    metadata = dict(getattr(secondary, "metadata", {}) or {})
    if "vehicle_distance" in metadata:
        context["environment.vehicle_distance_m"] = float(metadata["vehicle_distance"])
    if "grade_angle" in metadata:
        context["environment.grade_deg"] = float(degrees(float(metadata["grade_angle"])))
    if "study_phase" in metadata:
        context["environment.study_phase"] = str(metadata["study_phase"])

    # The ordinary locked-final-drive boundary reports distance but not grade.
    # Recover grade from its road profile without changing the boundary model.
    if "environment.grade_deg" not in context and "environment.vehicle_distance_m" in context:
        boundary = getattr(getattr(builder, "_system", None), "secondary_boundary", None)
        profile = getattr(boundary, "road_profile", None)
        if profile is not None and callable(getattr(profile, "sample", None)):
            sample = profile.sample(vehicle_distance=context["environment.vehicle_distance_m"])
            context["environment.grade_deg"] = float(degrees(float(sample.grade_angle)))
    return boundaries, context


def collect_rows(
    *,
    system: Any,
    trace: Any,
    maximum_samples: int = 6000,
    max_shift_m: float | None = None,
    static_friction_coefficient: float | None = None,
) -> list[dict[str, Any]]:
    from cinder.results import CVTResultBuilder, inspect_cvt_state

    builder = CVTResultBuilder(system=system)
    sizes = [segment.state.shape[1] for segment in trace.segments]
    rows: list[dict[str, Any]] = []
    for segment_index, (segment, budget) in enumerate(
        zip(trace.segments, _budgets(sizes, maximum_samples), strict=True)
    ):
        cvt_states = builder._cvt_state_matrix(segment.state)
        cvt_mode = builder._cvt_mode(segment.mode)
        contact_regime = getattr(cvt_mode, "contact_regime", None)
        for native_index in _sample_indices(segment.state.shape[1], budget):
            t = float(segment.time[native_index])
            full = np.asarray(segment.state[:, native_index], dtype=float)
            shaft_boundaries, boundary_context = _boundary_context(
                builder, time=t, full_state=full
            )
            inspection = inspect_cvt_state(
                system=builder._cvt_system,
                time=t,
                vector=np.asarray(cvt_states[:, native_index], dtype=float),
                mode=cvt_mode,
                shaft_boundaries=shaft_boundaries,
                include_closure_audit=False,
            )
            row = inspect_final_belt_terms(inspection)
            if row is None:
                continue
            row.update(boundary_context)
            row["segment_index"] = segment_index
            row["native_index"] = int(native_index)
            row["regime.engagement"] = _enum_value(getattr(cvt_mode, "engagement", "unknown"))
            row["regime.shift_constraint"] = _enum_value(getattr(cvt_mode, "shift_constraint", "unknown"))
            row["regime.contact_mode"] = _enum_value(getattr(contact_regime, "mode", "unknown"))
            row["regime.primary_slip_direction"] = _enum_value(
                getattr(contact_regime, "primary_slip_direction", "none")
            )
            row["regime.secondary_slip_direction"] = _enum_value(
                getattr(contact_regime, "secondary_slip_direction", "none")
            )
            if max_shift_m is not None and max_shift_m > 0.0:
                row["state.shift_fraction"] = float(row["state.shift_position_m"]) / float(max_shift_m)
            if static_friction_coefficient is not None and static_friction_coefficient > 0.0:
                demand = max(
                    abs(float(row["contact.primary_lambda"])),
                    abs(float(row["contact.secondary_lambda"])),
                )
                row["contact.max_static_utilization_fraction"] = demand / float(static_friction_coefficient)
            rows.append(row)
    return rows


def _peak_context(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    candidates = [row for row in rows if isinstance(row.get(key), (int, float))]
    if not candidates:
        return None
    row = max(candidates, key=lambda item: abs(float(item[key])))
    payload: dict[str, Any] = {
        "value": float(row[key]),
        "time_s": float(row["time_s"]),
        "shift_constraint": row.get("regime.shift_constraint"),
        "contact_mode": row.get("regime.contact_mode"),
        "shift_position_m": float(row["state.shift_position_m"]),
        "shift_speed_m_per_s": float(row["state.shift_speed_m_per_s"]),
        "shift_acceleration_m_per_s2": float(row["state.shift_acceleration_m_per_s2"]),
        "belt_speed_m_per_s": float(row["state.belt_speed_m_per_s"]),
        "belt_acceleration_m_per_s2": float(row["state.belt_acceleration_m_per_s2"]),
        "primary_lambda": float(row["contact.primary_lambda"]),
        "secondary_lambda": float(row["contact.secondary_lambda"]),
    }
    for source, target in (
        ("state.shift_fraction", "shift_fraction"),
        ("contact.max_static_utilization_fraction", "max_static_utilization_fraction"),
        ("environment.vehicle_distance_m", "vehicle_distance_m"),
        ("environment.grade_deg", "grade_deg"),
    ):
        if source in row:
            payload[target] = float(row[source])
    if "environment.study_phase" in row:
        payload["study_phase"] = row["environment.study_phase"]
    return payload


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    terms = (*TRANSPORT_TERMS, *LOOP_ALL_TERMS)
    channels = {key: summarize_channel(rows, key) for key in terms}
    channels = {key: value for key, value in channels.items() if value is not None}
    integrated = {
        key: integrated_abs_share(
            rows,
            key,
            "transport.activity_scale_N" if key.startswith("transport.") else "loop.activity_scale_N",
        )
        for key in terms
    }
    share_keys = {
        "transport.belt_inertia_N": "transport.share.belt_inertia",
        "transport.primary_reaction_N": "transport.share.primary_reaction",
        "transport.secondary_reaction_N": "transport.share.secondary_reaction",
        "loop.radial_shift_acceleration_N": "loop.share.radial_shift_acceleration",
        "loop.radial_geometry_curvature_N": "loop.share.radial_geometry_curvature",
        "loop.tangential_belt_acceleration_N": "loop.share.tangential_belt_acceleration",
        "loop.tangential_shifting_radius_N": "loop.share.tangential_shifting_radius",
        "loop.normal_contact_N": "loop.share.normal_contact",
    }
    instantaneous_shares = {
        term: summarize_channel(rows, share_key) for term, share_key in share_keys.items()
    }
    result: dict[str, Any] = {
        "sample_count": len(rows),
        "time_span_s": (
            [float(min(row["time_s"] for row in rows)), float(max(row["time_s"] for row in rows))]
            if rows else None
        ),
        "channels": channels,
        "integrated_activity_share": integrated,
        "instantaneous_activity_share": instantaneous_shares,
        "peak_context": {key: _peak_context(rows, key) for key in terms},
        "response_coefficients": {
            key: summarize_channel(rows, key) for key in RESPONSE_COEFFICIENTS
        },
        "drivers": {key: summarize_channel(rows, key) for key in DRIVER_CHANNELS},
        "sensitivity_to_10pct": {key: summarize_channel(rows, key) for key in SENSITIVITY_RATIOS},
        "context": {
            key: summarize_channel(rows, key)
            for key in (
                "state.shift_fraction",
                "state.shift_position_m",
                "state.shift_speed_m_per_s",
                "state.shift_acceleration_m_per_s2",
                "state.belt_speed_m_per_s",
                "state.belt_acceleration_m_per_s2",
                "contact.max_static_utilization_fraction",
                "environment.vehicle_distance_m",
                "environment.grade_deg",
                "loop.contact_scale_N",
                "transport.reaction_scale_N",
                *SENSITIVITY_RATIOS,
            )
        },
        "equation_residuals": {
            "transport": summarize_channel(rows, "transport.residual_N"),
            "tension_loop": summarize_channel(rows, "loop.residual_N"),
        },
    }
    result["engaged_sample_count"] = len(rows)  # retained for compatibility with run_summary
    return result


def _subset(rows: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
    selected = [row for row in rows if predicate(row)]
    return summarize(selected) if selected else None


def _fraction_band(value: float) -> str | None:
    for lo, hi in ((0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0000001)):
        if lo <= value < hi:
            return f"{lo:.2f}-{min(hi, 1.0):.2f}"
    return None


def _demand_band(value: float) -> str:
    for lo, hi in ((0.0, 0.1), (0.1, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0), (1.0, float("inf"))):
        if lo <= value < hi:
            return f"{lo:.2f}-{hi:.2f}" if np.isfinite(hi) else ">=1.00"
    return "unknown"


def _phase_summaries(rows: list[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    """Mechanically defined windows plus free-stick-only exploratory slices."""
    if not rows:
        return {}

    exact: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        exact[f"{row.get('regime.shift_constraint', 'unknown')}__{row.get('regime.contact_mode', 'unknown')}"] .append(row)

    free_stick = [
        row for row in rows
        if row.get("regime.shift_constraint") == "free" and row.get("regime.contact_mode") == "stick_stick"
    ]
    named: dict[str, Any] = {
        "contact_transition_or_slip": _subset(rows, lambda r: r.get("regime.contact_mode") != "stick_stick"),
        "low_ratio_stick": _subset(rows, lambda r: r.get("regime.shift_constraint") == "low_ratio_seat" and r.get("regime.contact_mode") == "stick_stick"),
        "free_stick_all": summarize(free_stick) if free_stick else None,
        "free_stick_upshift": _subset(free_stick, lambda r: float(r["state.shift_speed_m_per_s"]) > 0.0),
        "free_stick_backshift": _subset(free_stick, lambda r: float(r["state.shift_speed_m_per_s"]) < 0.0),
        "upper_stop_stick": _subset(rows, lambda r: r.get("regime.shift_constraint") == "upper_stop" and r.get("regime.contact_mode") == "stick_stick"),
    }

    thresholds: dict[str, float] = {}
    if free_stick:
        for source, name in (
            ("state.shift_speed_m_per_s", "abs_shift_speed_q75_m_per_s"),
            ("state.shift_acceleration_m_per_s2", "abs_shift_acceleration_q75_m_per_s2"),
            ("state.belt_acceleration_m_per_s2", "abs_belt_acceleration_q75_m_per_s2"),
        ):
            threshold = float(np.percentile([abs(float(row[source])) for row in free_stick], 75.0))
            thresholds[name] = threshold
        named["free_stick_upper_quartile_shift_speed"] = _subset(
            free_stick, lambda r: abs(float(r["state.shift_speed_m_per_s"])) >= thresholds["abs_shift_speed_q75_m_per_s"]
        )
        named["free_stick_upper_quartile_shift_acceleration"] = _subset(
            free_stick, lambda r: abs(float(r["state.shift_acceleration_m_per_s2"])) >= thresholds["abs_shift_acceleration_q75_m_per_s2"]
        )
        named["free_stick_upper_quartile_belt_acceleration"] = _subset(
            free_stick, lambda r: abs(float(r["state.belt_acceleration_m_per_s2"])) >= thresholds["abs_belt_acceleration_q75_m_per_s2"]
        )

    shift_bands: dict[str, list[dict[str, Any]]] = defaultdict(list)
    demand_bands: dict[str, list[dict[str, Any]]] = defaultdict(list)
    study_phases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in free_stick:
        if "state.shift_fraction" in row:
            band = _fraction_band(float(row["state.shift_fraction"]))
            if band is not None:
                shift_bands[band].append(row)
        if "contact.max_static_utilization_fraction" in row:
            demand_bands[_demand_band(float(row["contact.max_static_utilization_fraction"]))].append(row)
        if "environment.study_phase" in row:
            study_phases[str(row["environment.study_phase"])].append(row)

    controlled: dict[str, Any] = {}
    control = protocol.get("controlled_load")
    if isinstance(control, dict):
        start = float(control["start_time_s"])
        rise = float(control["rise_time_s"])
        end = start + rise
        windows = {
            "pre_load_reference": (max(0.0, start - 0.5), start),
            "first_0p25s_after_start": (start, start + 0.25),
            "first_1s_after_start": (start, start + 1.0),
            "post_rise_0p5s": (end, end + 0.5),
        }
        if rise > 0.0:
            windows["load_rise"] = (start, end)
        for name, (t0, t1) in windows.items():
            selected = [row for row in free_stick if t0 <= float(row["time_s"]) <= t1]
            if selected:
                controlled[name] = {
                    "bounds_s": [t0, t1],
                    "summary": summarize(selected),
                }

    return {
        "exact_regimes": {key: summarize(group) for key, group in exact.items()},
        "named_phases": {key: value for key, value in named.items() if value is not None},
        "free_stick_thresholds": thresholds,
        "free_stick_by_shift_fraction": {key: summarize(group) for key, group in shift_bands.items()},
        "free_stick_by_contact_demand": {key: summarize(group) for key, group in demand_bands.items()},
        "free_stick_by_study_phase": {key: summarize(group) for key, group in study_phases.items()},
        "controlled_windows": controlled,
    }


def _phase_rows(case_name: str, phases: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for family, groups in (
        ("named", phases.get("named_phases", {})),
        ("shift_fraction", phases.get("free_stick_by_shift_fraction", {})),
        ("contact_demand", phases.get("free_stick_by_contact_demand", {})),
        ("study_phase", phases.get("free_stick_by_study_phase", {})),
    ):
        for phase, summary in groups.items():
            for term in (*TRANSPORT_TERMS, *LOOP_ALL_TERMS):
                stats = summary.get("channels", {}).get(term, {})
                rows.append({
                    "case": case_name,
                    "family": family,
                    "phase": phase,
                    "term": term,
                    "sample_count": summary.get("sample_count"),
                    "max_abs_N": stats.get("max_abs"),
                    "p95_abs_N": stats.get("p95_abs"),
                    "integrated_activity_share": summary.get("integrated_activity_share", {}).get(term),
                })
    return rows


def write_atlas(
    *,
    system: Any,
    trace: Any,
    output_dir: Path,
    protocol: dict[str, Any],
    maximum_samples: int = 6000,
) -> dict[str, Any]:
    rows = collect_rows(
        system=system,
        trace=trace,
        maximum_samples=maximum_samples,
        max_shift_m=protocol.get("max_shift_m"),
        static_friction_coefficient=protocol.get("static_friction_coefficient"),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_rows(output_dir / "belt_terms.csv", rows)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["mode"])].append(row)
    phases = _phase_summaries(rows, protocol)
    payload = {
        "protocol": protocol,
        "governing_model_modified": False,
        "overall": summarize(rows),
        "by_mode": {mode: summarize(group) for mode, group in grouped.items()},
        "phase_analysis": phases,
    }
    write_json(output_dir / "summary.json", payload)
    write_rows(output_dir / "phase_summary.csv", _phase_rows(str(protocol.get("name", "case")), phases))
    plot_atlas(rows, output_dir=output_dir, title=str(protocol.get("title", protocol.get("name", "belt exploration"))))
    return payload


def plot_atlas(rows: list[dict[str, Any]], *, output_dir: Path, title: str) -> None:
    if not rows:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = sorted(rows, key=lambda row: (float(row["time_s"]), int(row["segment_index"])))
    t = np.asarray([float(row["time_s"]) for row in rows])

    def series(key: str, default: float = np.nan) -> np.ndarray:
        return np.asarray([float(row.get(key, default)) for row in rows])

    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    for key, label in (
        ("loop.radial_shift_acceleration_N", "shift acceleration"),
        ("loop.radial_geometry_curvature_N", "shift-path curvature"),
        ("loop.tangential_belt_acceleration_N", "belt acceleration"),
        ("loop.tangential_shifting_radius_N", "moving-radius transport"),
        ("loop.normal_contact_N", "normal/contact"),
    ):
        ax.plot(t, series(key), label=label)
    ax.axhline(0.0, linewidth=0.8)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Tension-loop contribution [N]")
    ax.set_title(f"{title}: final tension-loop decomposition")
    ax.legend(ncol=2)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "tension_loop_terms.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    for key, label in (
        ("loop.share.radial_shift_acceleration", "shift acceleration"),
        ("loop.share.radial_geometry_curvature", "shift-path curvature"),
        ("loop.share.tangential_belt_acceleration", "belt acceleration"),
        ("loop.share.tangential_shifting_radius", "moving-radius transport"),
        ("loop.share.normal_contact", "normal/contact"),
    ):
        ax.plot(t, series(key), label=label)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Absolute equation activity share [-]")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title(f"{title}: tension-loop activity shares")
    ax.legend(ncol=2)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "tension_loop_activity_shares.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    for key, label in (
        ("transport.belt_inertia_N", r"$m_b\dot{v}_b$"),
        ("transport.primary_reaction_N", r"$\tau_p/r_p$"),
        ("transport.secondary_reaction_N", r"$\tau_s/r_s$"),
    ):
        ax.plot(t, series(key), label=label)
    ax.axhline(0.0, linewidth=0.8)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Whole-belt transport contribution [N]")
    ax.set_title(f"{title}: whole-belt transport")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "whole_belt_transport_terms.png", dpi=180)
    plt.close(fig)

    drivers = (
        ("state.shift_acceleration_m_per_s2", "loop.radial_shift_acceleration_N", r"$\ddot{s}$ [m/s²]", "shift-acceleration contribution [N]"),
        ("loop.driver.radial_geometry_curvature_m2ps2", "loop.radial_geometry_curvature_N", r"$\dot{s}^2$ [m²/s²]", "path-curvature contribution [N]"),
        ("state.belt_acceleration_m_per_s2", "loop.tangential_belt_acceleration_N", r"$\dot{v}_b$ [m/s²]", "belt-acceleration contribution [N]"),
        ("loop.driver.tangential_shifting_radius_m2ps2", "loop.tangential_shifting_radius_N", r"$\dot{s}v_b$ [m²/s²]", "moving-radius contribution [N]"),
    )
    for i, (xkey, ykey, xlabel, ylabel) in enumerate(drivers, start=1):
        fig, ax = plt.subplots(figsize=(6.5, 5.5))
        color = series("state.shift_fraction") if "state.shift_fraction" in rows[0] else series("state.shift_position_m")
        scatter = ax.scatter(series(xkey), series(ykey), c=color, s=12)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(f"{title}: driver map")
        ax.grid(True, alpha=0.25)
        fig.colorbar(scatter, ax=ax, label="Shift fraction [-]" if "state.shift_fraction" in rows[0] else "Shift position [m]")
        fig.tight_layout()
        fig.savefig(output_dir / f"driver_map_{i}.png", dpi=180)
        plt.close(fig)

    if "state.shift_fraction" in rows[0]:
        fig, ax = plt.subplots(figsize=(9.0, 5.5))
        for key, label in (
            (RESPONSE_COEFFICIENTS[0], r"$K_{\ddot{s}}$"),
            (RESPONSE_COEFFICIENTS[1], r"$K_{\dot{s}^2}$"),
            (RESPONSE_COEFFICIENTS[2], r"$K_{\dot{v}_b}$"),
            (RESPONSE_COEFFICIENTS[3], r"$K_{\dot{s}v_b}$"),
        ):
            ax.scatter(series("state.shift_fraction"), series(key), s=10, label=label)
        ax.set_xlabel("Shift fraction [-]")
        ax.set_ylabel("Final-equation response coefficient [channel-specific units]")
        ax.set_title(f"{title}: operating-point coefficients")
        ax.legend(ncol=2)
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(output_dir / "response_coefficients_vs_shift.png", dpi=180)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    ax.plot(t, series("state.shift_fraction"), label="shift fraction") if "state.shift_fraction" in rows[0] else None
    if "environment.grade_deg" in rows[0]:
        ax.plot(t, series("environment.grade_deg") / 30.0, label="grade / 30°")
    if "contact.max_static_utilization_fraction" in rows[0]:
        ax.plot(t, series("contact.max_static_utilization_fraction"), label="max |lambda| / mu_s")
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Normalized operating context [-]")
    ax.set_title(f"{title}: operating context")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "operating_context.png", dpi=180)
    plt.close(fig)
