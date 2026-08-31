"""Numerical-robustness sweep for the Ballew closed-loop benchmark.

The benchmark physics and controller remain unchanged. Each sweep point is
compared with a tighter CINDER-only numerical reference to measure continuous
trajectory drift, hybrid-topology drift, accepted adaptive step sizes, and
integration time. This is a numerical robustness study, not a fit to Ballew.

Ballew's reported ~1e-5 s fixed RK4 step is retained only as a literature work /
time-scale reference. It is not treated as a measured wall-clock benchmark.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any, Sequence

import cinder
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from benchmark.simulation import (  # noqa: E402
    build_closed_loop_setup,
    run_setup,
    sample_dense,
)

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
VERIFY_ENVIRONMENT = RELEASE_ROOT / "verify_environment.py"
VERIFY_STUDY = STUDY_ROOT / "verify_study.py"
OUTPUT_ROOT = STUDY_ROOT / "artifacts" / "numerical-stability"
EXPECTED_CINDER_VERSION = "1.0.0"
DURATION_S = 5.0
BALLEW_FIXED_STEP_S = 1.0e-5

NOMINAL = {
    "method": "LSODA",
    "max_step_s": 1.0e-3,
    "rtol": 1.0e-7,
    "atol": 1.0e-9,
}
REFERENCE = {
    "method": "LSODA",
    "max_step_s": 1.0e-4,
    "rtol": 1.0e-10,
    "atol": 1.0e-12,
}

PRESETS = {
    "smoke": {
        "max_step_ms": [0.10, 1.0, 100.0],
        "rtol": [1e-9, 1e-7, 1e-4],
    },
    "quick": {
        "max_step_ms": [0.03, 0.10, 0.30, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0],
        "rtol": [1e-10, 1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3],
    },
    "full": {
        "max_step_ms": [0.01, 0.03, 0.10, 0.30, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0],
        "rtol": [1e-11, 3e-11, 1e-10, 3e-10, 1e-9, 3e-9, 1e-8, 3e-8, 1e-7, 1e-6, 1e-5, 1e-4],
    },
    "extreme": {
        "max_step_ms": [0.01, 0.03, 0.10, 0.30, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 5000.0],
        "rtol": [1e-11, 1e-10, 1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 3e-3, 1e-2],
    },
}

METHODS_FOR_COMPARISON = ("LSODA", "BDF", "Radau", "DOP853", "RK45")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=tuple(PRESETS), default="quick")
    parser.add_argument("--report-step", type=float, default=5.0e-4)
    parser.add_argument("--maximum-transitions", type=int, default=5000)
    parser.add_argument("--timing-repeats", type=int, default=1)
    parser.add_argument("--compare-methods", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def _rms(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.sqrt(np.mean(values * values))) if values.size else math.nan


def _relative_rms(
    delta: np.ndarray,
    reference: np.ndarray,
    floor: float,
) -> float:
    delta = np.asarray(delta, dtype=float)
    reference = np.asarray(reference, dtype=float)
    mask = np.isfinite(delta) & np.isfinite(reference)
    if not np.any(mask):
        return math.nan
    denominator = max(_rms(reference[mask]), float(floor))
    return _rms(delta[mask]) / denominator


def _transition_signature(result: Any) -> tuple[tuple[str, tuple[str, ...], str], ...]:
    return tuple(
        (
            str(record.previous_mode),
            tuple(str(name) for name in record.fired_event_names),
            str(record.transition.reason),
        )
        for record in result.transitions
    )


def _mode_occupancy(modes: Sequence[str]) -> dict[str, float]:
    if not modes:
        return {}
    counts = Counter(modes)
    total = float(sum(counts.values()))
    return {key: value / total for key, value in counts.items()}


def _occupancy_l1(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    return float(sum(abs(a.get(key, 0.0) - b.get(key, 0.0)) for key in keys))


def _accepted_step_stats(result: Any) -> dict[str, float | int | None]:
    chunks: list[np.ndarray] = []
    accepted_steps = 0
    for segment in result.trace.segments:
        time_values = np.asarray(segment.time, dtype=float)
        if time_values.size < 2:
            continue
        dt = np.diff(time_values)
        dt = dt[np.isfinite(dt) & (dt > 0.0)]
        accepted_steps += int(dt.size)
        if dt.size:
            chunks.append(dt)

    if not chunks:
        return {
            "accepted_steps": accepted_steps,
            "actual_dt_min_ms": None,
            "actual_dt_p05_ms": None,
            "actual_dt_median_ms": None,
            "actual_dt_p95_ms": None,
            "actual_dt_max_ms": None,
        }

    dt = np.concatenate(chunks)
    return {
        "accepted_steps": accepted_steps,
        "actual_dt_min_ms": float(np.min(dt) * 1e3),
        "actual_dt_p05_ms": float(np.quantile(dt, 0.05) * 1e3),
        "actual_dt_median_ms": float(np.median(dt) * 1e3),
        "actual_dt_p95_ms": float(np.quantile(dt, 0.95) * 1e3),
        "actual_dt_max_ms": float(np.max(dt) * 1e3),
    }


def _trajectory_metrics(current, reference) -> dict[str, float]:
    primary_delta = current.primary_rpm - reference.primary_rpm
    secondary_delta = current.secondary_rpm - reference.secondary_rpm
    ratio_delta = current.speed_ratio - reference.speed_ratio
    shift_delta = current.shift_m - reference.shift_m

    relative_errors = np.asarray(
        [
            _relative_rms(primary_delta, reference.primary_rpm, 1.0),
            _relative_rms(secondary_delta, reference.secondary_rpm, 1.0),
            _relative_rms(ratio_delta, reference.speed_ratio, 1.0e-3),
            _relative_rms(shift_delta, reference.shift_m, 1.0e-5),
        ],
        dtype=float,
    )

    return {
        "primary_rpm_rms_delta": _rms(primary_delta),
        "primary_rpm_max_delta": float(np.nanmax(np.abs(primary_delta))),
        "secondary_rpm_rms_delta": _rms(secondary_delta),
        "secondary_rpm_max_delta": float(np.nanmax(np.abs(secondary_delta))),
        "ratio_rms_delta": _rms(ratio_delta),
        "ratio_max_delta": float(np.nanmax(np.abs(ratio_delta))),
        "shift_rms_delta_um": _rms(shift_delta * 1e6),
        "shift_max_delta_um": float(np.nanmax(np.abs(shift_delta * 1e6))),
        "composite_relative_error_ppm": float(np.nanmax(relative_errors) * 1e6),
    }


def _integration_once(
    *,
    method: str,
    rtol: float,
    atol: float,
    max_step_s: float,
    report_step_s: float,
    maximum_transitions: int,
):
    setup = build_closed_loop_setup()
    start = time.perf_counter()
    result = run_setup(
        setup,
        relative_tolerance=rtol,
        absolute_tolerance=atol,
        max_step_s=max_step_s,
        maximum_transitions=maximum_transitions,
        report_step_s=report_step_s,
        method=method,
    )
    wall_time = time.perf_counter() - start
    return setup, result, wall_time


def _sample_grid(report_step_s: float) -> np.ndarray:
    times = np.arange(
        0.0,
        DURATION_S + 0.5 * report_step_s,
        report_step_s,
        dtype=float,
    )
    if times[-1] != DURATION_S:
        times = np.r_[times[times < DURATION_S], DURATION_S]
    else:
        times[-1] = DURATION_S
    return times


def _run_point(
    *,
    method: str,
    rtol: float,
    atol: float,
    max_step_s: float,
    report_step_s: float,
    maximum_transitions: int,
    timing_repeats: int,
    reference_sample,
    reference_transition_signature,
    reference_mode_occupancy,
) -> dict[str, object]:
    wall_times: list[float] = []
    setup = None
    result = None

    for _ in range(max(1, timing_repeats)):
        setup_i, result_i, wall_time_i = _integration_once(
            method=method,
            rtol=rtol,
            atol=atol,
            max_step_s=max_step_s,
            report_step_s=report_step_s,
            maximum_transitions=maximum_transitions,
        )
        wall_times.append(wall_time_i)
        setup = setup_i
        result = result_i
        if not result_i.completed:
            break

    assert setup is not None and result is not None
    wall_time = float(statistics.median(wall_times))
    row: dict[str, object] = {
        "method": method,
        "rtol": rtol,
        "atol": atol,
        "max_step_ms": max_step_s * 1e3,
        "completed": bool(result.completed),
        "termination_reason": str(result.termination_reason),
        "wall_time_s": wall_time,
        "timing_repeats_completed": len(wall_times),
        "real_time_factor": DURATION_S / wall_time if wall_time > 0.0 else math.nan,
        "segment_count": len(result.trace.segments),
        "transition_count": len(result.transitions),
        **_accepted_step_stats(result),
    }

    if not result.completed:
        return row

    times = reference_sample.time_s
    current = sample_dense(setup, result, times)
    row.update(_trajectory_metrics(current, reference_sample))

    signature = _transition_signature(result)
    row["transition_signature_match"] = signature == reference_transition_signature
    row["transition_count_delta"] = len(signature) - len(reference_transition_signature)
    row["mode_occupancy_l1"] = _occupancy_l1(
        _mode_occupancy(current.mode),
        reference_mode_occupancy,
    )
    return row


def _resume_key(row: dict[str, object]) -> tuple[str, float, float, float]:
    return (
        str(row["method"]),
        float(row["rtol"]),
        float(row["atol"]),
        float(row["max_step_ms"]),
    )


def _load_existing(path: Path) -> dict[tuple[str, float, float, float], dict[str, object]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {_resume_key(row): row for row in payload.get("cases", [])}


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _plot_stability(rows: list[dict[str, object]], output_dir: Path) -> None:
    completed = [
        row
        for row in rows
        if row.get("method") == "LSODA"
        and bool(row.get("completed"))
        and row.get("composite_relative_error_ppm") is not None
    ]
    if not completed:
        return

    x = np.asarray([float(row["max_step_ms"]) for row in completed])
    y = np.asarray([float(row["rtol"]) for row in completed])
    error = np.asarray(
        [max(float(row["composite_relative_error_ppm"]), 1.0e-12) for row in completed]
    )

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    points = ax.scatter(x, y, c=np.log10(error), s=48)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Maximum allowed step [ms]")
    ax.set_ylabel("Relative tolerance")
    ax.set_title("Ballew closed loop: CINDER numerical-stability sweep")
    colorbar = fig.colorbar(points, ax=ax)
    colorbar.set_label("log10 composite trajectory error [ppm]")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "01_stability_envelope.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    wall = np.asarray([float(row["wall_time_s"]) for row in completed])
    ax.scatter(error, wall)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Composite trajectory error [ppm]")
    ax.set_ylabel("Integration wall time [s]")
    ax.set_title("CINDER speed/accuracy tradeoff")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "02_speed_accuracy.png", dpi=180)
    plt.close(fig)

    with_step = [row for row in completed if row.get("actual_dt_p95_ms") is not None]
    if with_step:
        fig, ax = plt.subplots(figsize=(8.5, 5.5))
        x_step = np.asarray([float(row["max_step_ms"]) for row in with_step])
        y_step = np.asarray([float(row["actual_dt_p95_ms"]) for row in with_step])
        ax.scatter(x_step, y_step)
        ax.axhline(BALLEW_FIXED_STEP_S * 1e3, linestyle="--", label="Ballew ~0.01 ms scale")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Maximum allowed step [ms]")
        ax.set_ylabel("95th-percentile accepted CINDER step [ms]")
        ax.set_title("Allowed versus actually accepted adaptive step scale")
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(output_dir / "03_actual_step_scale.png", dpi=180)
        plt.close(fig)


def main() -> int:
    args = parse_args()
    if args.timing_repeats < 1:
        raise SystemExit("--timing-repeats must be at least 1.")

    subprocess.run([sys.executable, str(VERIFY_ENVIRONMENT)], check=True)
    subprocess.run([sys.executable, str(VERIFY_STUDY)], check=True)
    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise SystemExit(
            f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__}."
        )

    output_dir = (args.output_dir or (OUTPUT_ROOT / args.preset)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    times = _sample_grid(args.report_step)
    reference_setup, reference_result, reference_wall = _integration_once(
        method=str(REFERENCE["method"]),
        rtol=float(REFERENCE["rtol"]),
        atol=float(REFERENCE["atol"]),
        max_step_s=float(REFERENCE["max_step_s"]),
        report_step_s=args.report_step,
        maximum_transitions=args.maximum_transitions,
    )
    if not reference_result.completed:
        raise RuntimeError(
            "Tight CINDER numerical reference did not complete: "
            f"{reference_result.termination_reason}"
        )
    reference_sample = sample_dense(reference_setup, reference_result, times)
    reference_signature = _transition_signature(reference_result)
    reference_occupancy = _mode_occupancy(reference_sample.mode)

    json_path = output_dir / "stress_sweep.json"
    existing = _load_existing(json_path) if args.resume else {}
    rows: list[dict[str, object]] = []

    preset = PRESETS[args.preset]
    requested = [
        (
            "LSODA",
            float(rtol),
            float(rtol) * 1.0e-2,
            float(max_step_ms) * 1.0e-3,
        )
        for rtol in preset["rtol"]
        for max_step_ms in preset["max_step_ms"]
    ]
    if args.compare_methods:
        requested.extend(
            (
                method,
                float(NOMINAL["rtol"]),
                float(NOMINAL["atol"]),
                float(NOMINAL["max_step_s"]),
            )
            for method in METHODS_FOR_COMPARISON
            if method != "LSODA"
        )

    for index, (method, rtol, atol, max_step_s) in enumerate(requested, start=1):
        key = (method, rtol, atol, max_step_s * 1e3)
        if key in existing:
            print(f"[{index}/{len(requested)}] reusing {method}, rtol={rtol:g}, max_step={max_step_s*1e3:g} ms")
            rows.append(existing[key])
            continue

        print(f"[{index}/{len(requested)}] {method}, rtol={rtol:g}, max_step={max_step_s*1e3:g} ms")
        try:
            row = _run_point(
                method=method,
                rtol=rtol,
                atol=atol,
                max_step_s=max_step_s,
                report_step_s=args.report_step,
                maximum_transitions=args.maximum_transitions,
                timing_repeats=args.timing_repeats,
                reference_sample=reference_sample,
                reference_transition_signature=reference_signature,
                reference_mode_occupancy=reference_occupancy,
            )
        except Exception as exc:
            row = {
                "method": method,
                "rtol": rtol,
                "atol": atol,
                "max_step_ms": max_step_s * 1e3,
                "completed": False,
                "termination_reason": f"{type(exc).__name__}: {exc}",
            }
        rows.append(row)

        # Persist partial progress so long sweeps can be resumed.
        payload = {
            "cinder_version": cinder.__version__,
            "preset": args.preset,
            "reference": {
                **REFERENCE,
                "wall_time_s": reference_wall,
                "transition_count": len(reference_signature),
                **_accepted_step_stats(reference_result),
            },
            "ballew_reported_fixed_step_s": BALLEW_FIXED_STEP_S,
            "ballew_fixed_step_count_scale_over_5s": DURATION_S / BALLEW_FIXED_STEP_S,
            "interpretation": (
                "The tight run is a CINDER-only numerical reference. Composite error "
                "is not a fit metric, and Ballew's reported timestep is not a wall-clock benchmark."
            ),
            "cases": rows,
        }
        json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    _write_csv(output_dir / "stress_sweep.csv", rows)
    _plot_stability(rows, output_dir)

    completed = sum(bool(row.get("completed")) for row in rows)
    summary = [
        "# Numerical-stability sweep summary",
        "",
        f"- CINDER version: `{cinder.__version__}`",
        f"- preset: `{args.preset}`",
        f"- completed cases: {completed}/{len(rows)}",
        f"- tight reference transitions: {len(reference_signature)}",
        f"- Ballew literature step scale: {BALLEW_FIXED_STEP_S:g} s",
        "",
        "Interpret numerical convergence separately from physical/model agreement. ",
        "The Ballew timestep is a literature work scale, not a measured runtime comparator.",
    ]
    (output_dir / "SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"Artifacts: {output_dir}")
    return 0 if completed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
