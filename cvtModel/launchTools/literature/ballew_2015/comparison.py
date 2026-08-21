"""Reference comparison, metrics, CSV, and plotting for Ballew (2015)."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from math import sqrt
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from numpy.typing import NDArray  # noqa: E402

from constants import PUBLISHED
from simulation import (
    BallewSimulationSetup,
    SampledCinderTrace,
    compact_mode,
    sample_cinder_trace,
)


@dataclass(frozen=True, slots=True)
class ReferenceSeries:
    """One native digitized Ballew trace."""

    time_s: NDArray[np.float64]
    value: NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class ErrorMetrics:
    """Pointwise error summary evaluated at the native reference times."""

    count: int
    mean_error: float
    mean_absolute_error: float
    root_mean_square_error: float
    max_absolute_error: float
    rmse_percent_of_reference_mean: float


def load_reference_series(path: Path, *, value_column: str) -> ReferenceSeries:
    """Load one prepared two-column benchmark reference trace."""

    times: list[float] = []
    values: list[float] = []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"time_s", value_column}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise RuntimeError(
                f"{path.name} must contain time_s and {value_column} columns."
            )
        for row in reader:
            times.append(float(row["time_s"]))
            values.append(float(row[value_column]))

    time_array = np.asarray(times, dtype=float)
    value_array = np.asarray(values, dtype=float)
    _validate_reference_arrays(time_array, value_array, path=path)
    time_array.setflags(write=False)
    value_array.setflags(write=False)
    return ReferenceSeries(time_s=time_array, value=value_array)


def build_reference_ratio(
    input_rpm: ReferenceSeries,
    output_rpm: ReferenceSeries,
) -> ReferenceSeries:
    """Derive Ballew speed ratio without modifying either archived trace.

    The comparison grid is the sorted union of both native Figure 41 time sets
    inside their common visible interval. Each digitized trace is only linearly
    interpolated to the other trace's native timestamps for this derived metric.
    """

    start = max(float(input_rpm.time_s[0]), float(output_rpm.time_s[0]))
    end = min(float(input_rpm.time_s[-1]), float(output_rpm.time_s[-1]))
    merged = np.unique(np.r_[input_rpm.time_s, output_rpm.time_s])
    times = merged[(merged >= start) & (merged <= end)]
    input_values = np.interp(times, input_rpm.time_s, input_rpm.value)
    output_values = np.interp(times, output_rpm.time_s, output_rpm.value)
    if np.any(np.abs(output_values) <= 1.0e-12):
        raise RuntimeError("Figure 41 output RPM passes through zero; ratio undefined.")
    ratio = input_values / output_values
    times.setflags(write=False)
    ratio.setflags(write=False)
    return ReferenceSeries(time_s=times, value=ratio)


def compute_error_metrics(
    *, reference: Sequence[float], predicted: Sequence[float]
) -> ErrorMetrics:
    """Return simple transparent pointwise benchmark metrics."""

    ref = np.asarray(reference, dtype=float)
    pred = np.asarray(predicted, dtype=float)
    if ref.shape != pred.shape or ref.ndim != 1 or ref.size == 0:
        raise ValueError("reference and predicted must be aligned non-empty vectors.")
    if not np.all(np.isfinite(ref)) or not np.all(np.isfinite(pred)):
        raise ValueError("reference and predicted values must be finite.")

    error = pred - ref
    rmse = sqrt(float(np.mean(error**2)))
    reference_mean = float(np.mean(np.abs(ref)))
    return ErrorMetrics(
        count=int(ref.size),
        mean_error=float(np.mean(error)),
        mean_absolute_error=float(np.mean(np.abs(error))),
        root_mean_square_error=rmse,
        max_absolute_error=float(np.max(np.abs(error))),
        rmse_percent_of_reference_mean=(
            100.0 * rmse / reference_mean if reference_mean > 0.0 else float("nan")
        ),
    )


def write_all_outputs(
    *,
    output_dir: Path,
    setup: BallewSimulationSetup,
    result,
    uniform_trace: SampledCinderTrace,
    primary_force: ReferenceSeries,
    input_reference: ReferenceSeries,
    output_reference: ReferenceSeries,
    input_prediction: SampledCinderTrace,
    output_prediction: SampledCinderTrace,
    ratio_reference: ReferenceSeries,
    ratio_prediction: SampledCinderTrace,
    solver_settings: dict[str, object],
    make_plots: bool = True,
) -> dict[str, object]:
    """Materialize reproducible benchmark outputs and return metrics payload."""

    output_dir.mkdir(parents=True, exist_ok=True)

    input_metrics = compute_error_metrics(
        reference=input_reference.value,
        predicted=input_prediction.primary_rpm,
    )
    output_metrics = compute_error_metrics(
        reference=output_reference.value,
        predicted=output_prediction.secondary_rpm,
    )
    ratio_metrics = compute_error_metrics(
        reference=ratio_reference.value,
        predicted=ratio_prediction.speed_ratio,
    )

    _write_uniform_trace(
        output_dir / "cinder_trace.csv",
        trace=uniform_trace,
        primary_force=primary_force,
    )
    _write_comparison_csv(
        output_dir / "input_rpm_comparison.csv",
        time_s=input_reference.time_s,
        reference=input_reference.value,
        predicted=input_prediction.primary_rpm,
        reference_name="ballew_input_rpm",
        predicted_name="cinder_primary_rpm",
    )
    _write_comparison_csv(
        output_dir / "output_rpm_comparison.csv",
        time_s=output_reference.time_s,
        reference=output_reference.value,
        predicted=output_prediction.secondary_rpm,
        reference_name="ballew_output_rpm",
        predicted_name="cinder_secondary_rpm",
    )
    _write_comparison_csv(
        output_dir / "ratio_comparison.csv",
        time_s=ratio_reference.time_s,
        reference=ratio_reference.value,
        predicted=ratio_prediction.speed_ratio,
        reference_name="ballew_speed_ratio",
        predicted_name="cinder_speed_ratio",
    )
    _write_transitions(output_dir / "transitions.csv", result.transitions)

    final_cvt = setup.system.layout.view(result.final_state, "cvt")
    payload: dict[str, object] = {
        "benchmark": "Ballew 2015 simulated vehicle-acceleration case",
        "comparison_kind": "model-to-model; no parameter tuning to Figure 41",
        "completed": bool(result.completed),
        "termination_reason": str(result.termination_reason),
        "final_time_s": float(result.final_time),
        "segment_count": len(result.segments),
        "transition_count": len(result.transitions),
        "solver": solver_settings,
        "reference_visibility": {
            "input_rpm_start_s": float(input_reference.time_s[0]),
            "input_rpm_end_s": float(input_reference.time_s[-1]),
            "output_rpm_start_s": float(output_reference.time_s[0]),
            "output_rpm_end_s": float(output_reference.time_s[-1]),
        },
        "metrics": {
            "primary_rpm": asdict(input_metrics),
            "secondary_rpm": asdict(output_metrics),
            "speed_ratio": asdict(ratio_metrics),
        },
        "initial_conditions": {
            "primary_rpm": PUBLISHED.initial_input_rpm,
            "secondary_rpm": PUBLISHED.initial_output_rpm,
            "shift_m": float(setup.initial_cvt_state.shift_position),
            "belt_speed_m_per_s": float(setup.initial_cvt_state.belt_speed),
        },
        "final_cvt_state": {
            "primary_rpm": float(final_cvt[0] * 60.0 / (2.0 * np.pi)),
            "secondary_rpm": float(final_cvt[1] * 60.0 / (2.0 * np.pi)),
            "belt_speed_m_per_s": float(final_cvt[2]),
            "shift_m": float(final_cvt[3]),
            "shift_speed_m_per_s": float(final_cvt[4]),
        },
        "reconstruction_warnings": [
            (
                "A1/A9 output inertia/final-drive interpretation remains an "
                "explicit reconstruction assumption."
            ),
            "A6 holds the first visible Figure 45 force backward over 0-0.095541 s.",
            (
                "A8 CINDER cannot reproduce Ballew's exact zero-longitudinal-"
                "tension distributed belt state."
            ),
        ],
    }
    _assert_json_finite(payload)
    (output_dir / "metrics.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _write_summary(output_dir / "summary.md", payload)

    if make_plots:
        _plot_comparison_overview(
            path=output_dir / "comparison_overview.png",
            uniform_trace=uniform_trace,
            primary_force=primary_force,
            input_reference=input_reference,
            output_reference=output_reference,
            ratio_reference=ratio_reference,
        )
        _plot_cinder_diagnostics(
            path=output_dir / "cinder_diagnostics.png",
            trace=uniform_trace,
            result=result,
        )

    return payload


def _write_uniform_trace(
    path: Path,
    *,
    trace: SampledCinderTrace,
    primary_force: ReferenceSeries,
) -> None:
    force = np.interp(trace.time_s, primary_force.time_s, primary_force.value)
    headers = (
        "time_s",
        "primary_rpm",
        "secondary_rpm",
        "speed_ratio",
        "belt_speed_m_per_s",
        "shift_m",
        "shift_speed_m_per_s",
        "primary_effective_radius_m",
        "secondary_effective_radius_m",
        "vehicle_speed_m_per_s",
        "vehicle_distance_m",
        "secondary_road_torque_nm",
        "primary_clamp_force_n",
        "mode",
    )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        for i, time in enumerate(trace.time_s):
            writer.writerow(
                (
                    f"{time:.12g}",
                    f"{trace.primary_rpm[i]:.12g}",
                    f"{trace.secondary_rpm[i]:.12g}",
                    f"{trace.speed_ratio[i]:.12g}",
                    f"{trace.belt_speed_m_per_s[i]:.12g}",
                    f"{trace.shift_m[i]:.12g}",
                    f"{trace.shift_speed_m_per_s[i]:.12g}",
                    f"{trace.primary_effective_radius_m[i]:.12g}",
                    f"{trace.secondary_effective_radius_m[i]:.12g}",
                    f"{trace.vehicle_speed_m_per_s[i]:.12g}",
                    f"{trace.vehicle_distance_m[i]:.12g}",
                    f"{trace.secondary_road_torque_nm[i]:.12g}",
                    f"{force[i]:.12g}",
                    trace.mode[i],
                )
            )


def _write_comparison_csv(
    path: Path,
    *,
    time_s: NDArray[np.float64],
    reference: NDArray[np.float64],
    predicted: NDArray[np.float64],
    reference_name: str,
    predicted_name: str,
) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("time_s", reference_name, predicted_name, "error"))
        for time, ref, pred in zip(time_s, reference, predicted, strict=True):
            writer.writerow(
                (
                    f"{time:.12g}",
                    f"{ref:.12g}",
                    f"{pred:.12g}",
                    f"{pred - ref:.12g}",
                )
            )


def _write_transitions(path: Path, transitions: Iterable[object]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ("time_s", "previous_mode", "next_mode", "fired_events", "reason")
        )
        for record in transitions:
            transition = record.transition
            next_mode = (
                "TERMINATED"
                if transition.next_mode is None
                else compact_mode(transition.next_mode)
            )
            writer.writerow(
                (
                    f"{float(record.time):.12g}",
                    compact_mode(record.previous_mode),
                    next_mode,
                    ";".join(record.fired_event_names),
                    transition.reason,
                )
            )


def _plot_comparison_overview(
    *,
    path: Path,
    uniform_trace: SampledCinderTrace,
    primary_force: ReferenceSeries,
    input_reference: ReferenceSeries,
    output_reference: ReferenceSeries,
    ratio_reference: ReferenceSeries,
) -> None:
    t = uniform_trace.time_s
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    primary_axis, secondary_axis, ratio_axis, force_axis = axes.flat

    primary_axis.plot(t, uniform_trace.primary_rpm, label="CINDER")
    primary_axis.plot(
        input_reference.time_s,
        input_reference.value,
        marker=".",
        linestyle="none",
        label="Ballew Figure 41",
    )
    primary_axis.set(title="Primary/input speed", xlabel="Time [s]", ylabel="RPM")
    primary_axis.grid(True, alpha=0.25)
    primary_axis.legend()

    secondary_axis.plot(t, uniform_trace.secondary_rpm, label="CINDER")
    secondary_axis.plot(
        output_reference.time_s,
        output_reference.value,
        marker=".",
        linestyle="none",
        label="Ballew Figure 41",
    )
    secondary_axis.set(title="Secondary/output speed", xlabel="Time [s]", ylabel="RPM")
    secondary_axis.grid(True, alpha=0.25)
    secondary_axis.legend()

    ratio_axis.plot(t, uniform_trace.speed_ratio, label="CINDER")
    ratio_axis.plot(
        ratio_reference.time_s,
        ratio_reference.value,
        marker=".",
        linestyle="none",
        label="Derived from Figure 41",
    )
    ratio_axis.set(
        title="Speed ratio",
        xlabel="Time [s]",
        ylabel=r"$\omega_p/\omega_s$",
    )
    ratio_axis.grid(True, alpha=0.25)
    ratio_axis.legend()

    force_axis.plot(primary_force.time_s, primary_force.value)
    force_axis.set(
        title="Prescribed primary clamp input (Figure 45)",
        xlabel="Time [s]",
        ylabel="Closing force [N]",
    )
    force_axis.grid(True, alpha=0.25)

    fig.suptitle("CINDER vs Ballew (2015): simulated vehicle acceleration")
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_cinder_diagnostics(*, path: Path, trace: SampledCinderTrace, result) -> None:
    t = trace.time_s
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    shift_axis, geometry_axis, vehicle_axis, mode_axis = axes.flat

    shift_axis.plot(t, trace.shift_m * 1.0e3, label="shift")
    shift_axis.plot(t, trace.shift_speed_m_per_s * 1.0e3, label="shift speed")
    shift_axis.set(
        title="CINDER shift state",
        xlabel="Time [s]",
        ylabel="mm / mm s$^{-1}$",
    )
    shift_axis.grid(True, alpha=0.25)
    shift_axis.legend()

    geometry_axis.plot(t, trace.primary_effective_radius_m * 1.0e3, label="primary")
    geometry_axis.plot(t, trace.secondary_effective_radius_m * 1.0e3, label="secondary")
    geometry_axis.set(
        title="Effective pulley radii",
        xlabel="Time [s]",
        ylabel="Effective radius [mm]",
    )
    geometry_axis.grid(True, alpha=0.25)
    geometry_axis.legend()

    vehicle_axis.plot(t, trace.vehicle_speed_m_per_s * 3.6, label="vehicle speed")
    vehicle_axis.set(
        title="Reconstructed vehicle boundary",
        xlabel="Time [s]",
        ylabel="Vehicle speed [km/h]",
    )
    vehicle_axis.grid(True, alpha=0.25)
    vehicle_torque_axis = vehicle_axis.twinx()
    vehicle_torque_axis.plot(
        t, trace.secondary_road_torque_nm, linestyle=":", label="road torque"
    )
    vehicle_torque_axis.set_ylabel("Secondary road-load torque [N m]")
    handles, labels = vehicle_axis.get_legend_handles_labels()
    handles2, labels2 = vehicle_torque_axis.get_legend_handles_labels()
    vehicle_axis.legend(handles + handles2, labels + labels2, loc="best")

    labels = list(dict.fromkeys(trace.mode))
    mode_index = {label: index for index, label in enumerate(labels)}
    values = np.asarray([mode_index[label] for label in trace.mode], dtype=float)
    mode_axis.step(t, values, where="post")
    mode_axis.set(
        title="CINDER hybrid regime/contact history",
        xlabel="Time [s]",
        ylabel="Mode",
    )
    mode_axis.set_yticks(np.arange(len(labels), dtype=float))
    mode_axis.set_yticklabels(labels)
    mode_axis.grid(True, axis="x", alpha=0.25)
    for transition in result.transitions:
        mode_axis.axvline(float(transition.time), linestyle="--", linewidth=0.75, alpha=0.5)

    fig.suptitle("Ballew benchmark: CINDER internal diagnostics")
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _write_summary(path: Path, payload: dict[str, object]) -> None:
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    primary = metrics["primary_rpm"]
    secondary = metrics["secondary_rpm"]
    ratio = metrics["speed_ratio"]
    assert isinstance(primary, dict) and isinstance(secondary, dict) and isinstance(ratio, dict)

    lines = [
        "# Ballew 2015 corrected force-replay comparison",
        "",
        (
            "This is the untouched CINDER baseline using the documented A1-A9 "
            "reconstruction choices. No parameter was fitted to Figure 41."
        ),
        "",
        f"- completed: `{payload['completed']}`",
        f"- termination: `{payload['termination_reason']}`",
        f"- segments/transitions: `{payload['segment_count']}` / `{payload['transition_count']}`",
        "",
        "## Pointwise comparison at digitized reference times",
        "",
        "| Quantity | N | MAE | RMSE | Max abs. error | RMSE / mean reference |",
        "|---|---:|---:|---:|---:|---:|",
        (
            f"| Primary RPM | {primary['count']} | {primary['mean_absolute_error']:.3f} rpm | "
            f"{primary['root_mean_square_error']:.3f} rpm | "
            f"{primary['max_absolute_error']:.3f} rpm | "
            f"{primary['rmse_percent_of_reference_mean']:.3f}% |"
        ),
        (
            f"| Secondary RPM | {secondary['count']} | "
            f"{secondary['mean_absolute_error']:.3f} rpm | "
            f"{secondary['root_mean_square_error']:.3f} rpm | "
            f"{secondary['max_absolute_error']:.3f} rpm | "
            f"{secondary['rmse_percent_of_reference_mean']:.3f}% |"
        ),
        (
            f"| Speed ratio | {ratio['count']} | {ratio['mean_absolute_error']:.6f} | "
            f"{ratio['root_mean_square_error']:.6f} | {ratio['max_absolute_error']:.6f} | "
            f"{ratio['rmse_percent_of_reference_mean']:.3f}% |"
        ),
        "",
        "## Interpretation guardrails",
        "",
        "- Figure 41 is digitized model output, not experimental data.",
        "- A1/A9 vehicle-side reconstruction is intentionally not tuned to improve these errors.",
        "- Figure 45 is prescribed to CINDER; it is an input, not a validation output.",
        "- CINDER and Ballew represent internal belt deformation differently; see A8.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _validate_reference_arrays(
    times: NDArray[np.float64], values: NDArray[np.float64], *, path: Path
) -> None:
    if times.ndim != 1 or times.size < 2 or values.shape != times.shape:
        raise RuntimeError(f"{path.name} must contain at least two aligned rows.")
    if not np.all(np.isfinite(times)) or not np.all(np.isfinite(values)):
        raise RuntimeError(f"{path.name} contains non-finite data.")
    if np.any(np.diff(times) <= 0.0):
        raise RuntimeError(f"{path.name} time coordinates must increase strictly.")


def _assert_json_finite(value: object) -> None:
    if isinstance(value, float):
        if not np.isfinite(value):
            raise RuntimeError("metrics payload contains a non-finite float.")
    elif isinstance(value, dict):
        for item in value.values():
            _assert_json_finite(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_json_finite(item)
