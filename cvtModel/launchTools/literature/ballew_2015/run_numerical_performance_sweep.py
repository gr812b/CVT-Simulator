"""Benchmark numerical cost and stability of the Ballew closed-loop CINDER case.

This script deliberately times the existing canonical runner as a subprocess so
that each point starts from a clean Python process and uses exactly the same
benchmark setup.  It does not benchmark Ballew's original executable.

Run from cvtModel/ (or anywhere; paths are resolved from this file):

    python launchTools/literature/ballew_2015/run_numerical_performance_sweep.py

Outputs are written to results/numerical_performance_sweep/.
"""
from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "run_closed_loop_comparison.py"
OUTPUT = ROOT / "results" / "numerical_performance_sweep"

# Broad enough to reveal when solver controls stop being irrelevant, while
# retaining the published nominal and tight cases exactly.
CASES = [
    (0.25e-3, 3e-8, 3e-10, "tight_0p25ms"),
    (0.50e-3, 3e-8, 3e-10, "tight_0p50ms_reference"),
    (1.00e-3, 3e-8, 3e-10, "tight_1p00ms"),
    (0.25e-3, 1e-7, 1e-9, "nominal_0p25ms"),
    (0.50e-3, 1e-7, 1e-9, "nominal_0p50ms"),
    (1.00e-3, 1e-7, 1e-9, "nominal_1p00ms"),
    (2.00e-3, 1e-7, 1e-9, "nominal_2p00ms"),
    (5.00e-3, 1e-7, 1e-9, "nominal_5p00ms"),
    (10.0e-3, 1e-7, 1e-9, "nominal_10p0ms"),
    (20.0e-3, 1e-7, 1e-9, "nominal_20p0ms"),
    (1.00e-3, 1e-6, 1e-8, "relaxed1_1p00ms"),
    (5.00e-3, 1e-6, 1e-8, "relaxed1_5p00ms"),
    (10.0e-3, 1e-6, 1e-8, "relaxed1_10p0ms"),
    (20.0e-3, 1e-6, 1e-8, "relaxed1_20p0ms"),
    (1.00e-3, 1e-5, 1e-7, "relaxed2_1p00ms"),
    (5.00e-3, 1e-5, 1e-7, "relaxed2_5p00ms"),
    (10.0e-3, 1e-5, 1e-7, "relaxed2_10p0ms"),
    (20.0e-3, 1e-5, 1e-7, "relaxed2_20p0ms"),
]
REFERENCE_LABEL = "tight_0p50ms_reference"


def _read_trace(path: Path):
    data = np.genfromtxt(path, delimiter=",", names=True, dtype=None, encoding="utf-8")
    return data


def _rms(x):
    x = np.asarray(x, dtype=float)
    return float(np.sqrt(np.mean(x * x)))


def _maxabs(x):
    return float(np.max(np.abs(np.asarray(x, dtype=float))))


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = []

    for max_step, rtol, atol, label in CASES:
        case_dir = OUTPUT / label
        case_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, str(RUNNER),
            "--output-dir", str(case_dir),
            "--max-step", repr(max_step),
            "--rtol", repr(rtol),
            "--atol", repr(atol),
            "--no-plots",
        ]
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, text=True, capture_output=True)
        elapsed = time.perf_counter() - t0
        (case_dir / "benchmark_stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (case_dir / "benchmark_stderr.txt").write_text(proc.stderr, encoding="utf-8")

        row = {
            "label": label,
            "max_step_ms": max_step * 1e3,
            "rtol": rtol,
            "atol": atol,
            "wall_time_s": elapsed,
            "simulated_time_s": 5.0,
            "real_time_factor": 5.0 / elapsed if elapsed > 0 else math.nan,
            "return_code": proc.returncode,
            "completed": False,
        }
        metrics_path = case_dir / "metrics.json"
        if proc.returncode == 0 and metrics_path.exists():
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            row.update({
                "completed": bool(metrics.get("completed", False)),
                "primary_rpm_rmse": metrics["metrics"]["primary_rpm"]["root_mean_square_error"],
                "secondary_rpm_rmse": metrics["metrics"]["secondary_rpm"]["root_mean_square_error"],
                "speed_ratio_rmse": metrics["metrics"]["speed_ratio"]["root_mean_square_error"],
                "primary_force_rmse_n": metrics["metrics"]["primary_force"]["root_mean_square_error"],
                "transition_count": metrics.get("transition_count"),
                "segment_count": metrics.get("segment_count"),
            })
        rows.append(row)
        print(f"{label}: return={proc.returncode}, wall={elapsed:.3f}s")

    # Trajectory drift against the tight 0.50 ms reference on the common report grid.
    ref_path = OUTPUT / REFERENCE_LABEL / "cinder_trace.csv"
    if ref_path.exists():
        ref = _read_trace(ref_path)
        for row in rows:
            trace_path = OUTPUT / row["label"] / "cinder_trace.csv"
            if not trace_path.exists():
                continue
            cur = _read_trace(trace_path)
            if len(cur) != len(ref) or not np.allclose(cur["time_s"], ref["time_s"], rtol=0, atol=1e-12):
                continue
            row["rms_primary_delta_vs_reference_rpm"] = _rms(cur["primary_rpm"] - ref["primary_rpm"])
            row["max_primary_delta_vs_reference_rpm"] = _maxabs(cur["primary_rpm"] - ref["primary_rpm"])
            row["rms_secondary_delta_vs_reference_rpm"] = _rms(cur["secondary_rpm"] - ref["secondary_rpm"])
            row["max_ratio_delta_vs_reference"] = _maxabs(cur["speed_ratio"] - ref["speed_ratio"])
            row["max_shift_delta_vs_reference_um"] = _maxabs(cur["shift_m"] - ref["shift_m"]) * 1e6

    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with (OUTPUT / "performance_sweep.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return 0 if all(r["return_code"] == 0 for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
