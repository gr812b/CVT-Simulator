"""Post-integration final-equation atlas for unchanged CINDER trajectories."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

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


def collect_rows(*, system: Any, trace: Any, maximum_samples: int = 6000) -> list[dict[str, Any]]:
    from cinder.results import CVTResultBuilder, inspect_cvt_state

    builder = CVTResultBuilder(system=system)
    sizes = [segment.state.shape[1] for segment in trace.segments]
    rows: list[dict[str, Any]] = []
    for segment_index, (segment, budget) in enumerate(zip(trace.segments, _budgets(sizes, maximum_samples), strict=True)):
        cvt_states = builder._cvt_state_matrix(segment.state)
        cvt_mode = builder._cvt_mode(segment.mode)
        for native_index in _sample_indices(segment.state.shape[1], budget):
            t = float(segment.time[native_index])
            full = np.asarray(segment.state[:, native_index], dtype=float)
            inspection = inspect_cvt_state(
                system=builder._cvt_system,
                time=t,
                vector=np.asarray(cvt_states[:, native_index], dtype=float),
                mode=cvt_mode,
                shaft_boundaries=builder._shaft_boundaries_for_sample(time=t, full_state=full),
                include_closure_audit=False,
            )
            row = inspect_final_belt_terms(inspection)
            if row is None:
                continue
            row["segment_index"] = segment_index
            row["native_index"] = int(native_index)
            rows.append(row)
    return rows


def _peak_context(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    if not rows:
        return None
    candidates = [row for row in rows if isinstance(row.get(key), (int, float))]
    if not candidates:
        return None
    row = max(candidates, key=lambda item: abs(float(item[key])))
    return {
        "value": float(row[key]),
        "time_s": float(row["time_s"]),
        "mode": row["mode"],
        "shift_position_m": float(row["state.shift_position_m"]),
        "shift_speed_m_per_s": float(row["state.shift_speed_m_per_s"]),
        "shift_acceleration_m_per_s2": float(row["state.shift_acceleration_m_per_s2"]),
        "belt_speed_m_per_s": float(row["state.belt_speed_m_per_s"]),
        "belt_acceleration_m_per_s2": float(row["state.belt_acceleration_m_per_s2"]),
        "primary_lambda": float(row["contact.primary_lambda"]),
        "secondary_lambda": float(row["contact.secondary_lambda"]),
    }


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
    peaks = {key: _peak_context(rows, key) for key in terms}
    return {
        "engaged_sample_count": len(rows),
        "channels": channels,
        "integrated_activity_share": integrated,
        "peak_context": peaks,
        "equation_residuals": {
            "transport": summarize_channel(rows, "transport.residual_N"),
            "tension_loop": summarize_channel(rows, "loop.residual_N"),
        },
    }


def write_atlas(*, system: Any, trace: Any, output_dir: Path, protocol: dict[str, Any], maximum_samples: int = 6000) -> dict[str, Any]:
    rows = collect_rows(system=system, trace=trace, maximum_samples=maximum_samples)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_rows(output_dir / "belt_terms.csv", rows)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["mode"])].append(row)
    payload = {
        "protocol": protocol,
        "governing_model_modified": False,
        "overall": summarize(rows),
        "by_mode": {mode: summarize(group) for mode, group in grouped.items()},
        "by_exploration_window": _exploration_windows(rows),
    }
    write_json(output_dir / "summary.json", payload)
    plot_atlas(rows, output_dir=output_dir, title=str(protocol.get("title", protocol.get("name", "belt exploration"))))
    return payload


def _exploration_windows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize naturally occurring kinematic windows without importance cutoffs."""
    if not rows:
        return {}

    def subset(predicate):
        selected = [row for row in rows if predicate(row)]
        return summarize(selected) if selected else None

    shift_speed = np.asarray([abs(float(row["state.shift_speed_m_per_s"])) for row in rows])
    shift_accel = np.asarray([abs(float(row["state.shift_acceleration_m_per_s2"])) for row in rows])
    belt_accel = np.asarray([abs(float(row["state.belt_acceleration_m_per_s2"])) for row in rows])
    q75_sdot = float(np.percentile(shift_speed, 75.0))
    q75_sddot = float(np.percentile(shift_accel, 75.0))
    q75_vbdot = float(np.percentile(belt_accel, 75.0))

    windows = {
        "upshift": subset(lambda row: float(row["state.shift_speed_m_per_s"]) > 0.0),
        "backshift": subset(lambda row: float(row["state.shift_speed_m_per_s"]) < 0.0),
        "upper_quartile_shift_speed": subset(lambda row: abs(float(row["state.shift_speed_m_per_s"])) >= q75_sdot),
        "upper_quartile_shift_acceleration": subset(lambda row: abs(float(row["state.shift_acceleration_m_per_s2"])) >= q75_sddot),
        "upper_quartile_belt_acceleration": subset(lambda row: abs(float(row["state.belt_acceleration_m_per_s2"])) >= q75_vbdot),
    }
    return {
        "thresholds": {
            "abs_shift_speed_q75_m_per_s": q75_sdot,
            "abs_shift_acceleration_q75_m_per_s2": q75_sddot,
            "abs_belt_acceleration_q75_m_per_s2": q75_vbdot,
        },
        "windows": {key: value for key, value in windows.items() if value is not None},
    }


def plot_atlas(rows: list[dict[str, Any]], *, output_dir: Path, title: str) -> None:
    if not rows:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = sorted(rows, key=lambda row: (float(row["time_s"]), int(row["segment_index"])))
    t = np.asarray([float(row["time_s"]) for row in rows])

    def series(key: str) -> np.ndarray:
        return np.asarray([float(row[key]) for row in rows])

    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    for key, label in (
        ("loop.radial_shift_acceleration_N", r"radial $\ddot{s}$"),
        ("loop.radial_geometry_curvature_N", r"radial $\dot{s}^2$"),
        ("loop.tangential_belt_acceleration_N", r"tangential $\dot{v}_b$"),
        ("loop.tangential_shifting_radius_N", r"tangential $\dot{s}v_b$"),
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
        ("loop.share.radial_shift_acceleration", r"radial $\ddot{s}$"),
        ("loop.share.radial_geometry_curvature", r"radial $\dot{s}^2$"),
        ("loop.share.tangential_belt_acceleration", r"tangential $\dot{v}_b$"),
        ("loop.share.tangential_shifting_radius", r"tangential $\dot{s}v_b$"),
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
        ("state.shift_acceleration_m_per_s2", "loop.radial_shift_acceleration_N", r"$\ddot{s}$ [m/s²]", r"$R_{\ddot{s}}$ [N]"),
        ("state.shift_speed_m_per_s", "loop.radial_geometry_curvature_N", r"$\dot{s}$ [m/s]", r"$R_{\dot{s}^2}$ [N]"),
        ("state.belt_acceleration_m_per_s2", "loop.tangential_belt_acceleration_N", r"$\dot{v}_b$ [m/s²]", r"$R_{\dot{v}_b}$ [N]"),
        ("state.shift_speed_m_per_s", "loop.tangential_shifting_radius_N", r"$\dot{s}$ [m/s]", r"$R_{\dot{s}v_b}$ [N]"),
    )
    for i, (xkey, ykey, xlabel, ylabel) in enumerate(drivers, start=1):
        fig, ax = plt.subplots(figsize=(6.5, 5.5))
        scatter = ax.scatter(series(xkey), series(ykey), c=series("state.shift_position_m"), s=12)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(f"{title}: driver map")
        ax.grid(True, alpha=0.25)
        fig.colorbar(scatter, ax=ax, label="Shift position [m]")
        fig.tight_layout()
        fig.savefig(output_dir / f"driver_map_{i}.png", dpi=180)
        plt.close(fig)
