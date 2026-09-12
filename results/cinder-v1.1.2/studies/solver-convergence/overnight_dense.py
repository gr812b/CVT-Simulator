#!/usr/bin/env python3
r"""High-density exploratory solver-convergence sweep for CINDER v1.1.2.

This script is intentionally NOT imported or called by the formal run.py study.
It uses the same frozen machine/scenario and the same revision-4 event-aligned
comparison machinery, but writes everything it creates underneath:

    studies/solver-convergence/artifacts/dense-overnight/

Default behavior:
- six worker PROCESSES (safer than threads for SciPy/LSODA workloads);
- calibrate real throughput on this machine;
- size a rectangular grid to approximately fill a six-hour wall-clock budget;
- cover the entire formal grid plus a modest coarse extension;
- stream CSV checkpoints so the run can resume after interruption;
- delete ordinary per-point caches after metrics are extracted to keep disk use sane;
- retain the reference and selected extreme trajectories for overlays;
- generate dense heatmaps, filled contours, hybrid/failure maps, and a three-panel
  accuracy/event/regime-vs-cost dashboard.

Typical use from results/cinder-v1.1.2:

    python .\studies\solver-convergence\overnight_dense.py

Useful overrides:

    python .\studies\solver-convergence\overnight_dense.py --hours 8 --workers 6
    python .\studies\solver-convergence\overnight_dense.py --plan-only
    python .\studies\solver-convergence\overnight_dense.py --formal-domain-only
"""

from __future__ import annotations

import argparse
import contextlib
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any

# Avoid accidental BLAS/OpenMP oversubscription inside six worker processes.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np

HERE = Path(__file__).resolve().parent
FORMAL_RUN = HERE / "run.py"
SPEC_FILE = HERE / "study.json"
ROOT = HERE / "artifacts" / "dense-overnight"
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"
ROWS_FILE = ROOT / "dense_sweep.csv"
FAILURES_FILE = ROOT / "failed_runs.csv"
GRID_FILE = ROOT / "grid.json"
CALIBRATION_FILE = ROOT / "calibration.json"
SUMMARY_FILE = ROOT / "summary.json"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hours", type=float, default=6.0, help="Approximate total wall-clock budget.")
    p.add_argument("--workers", type=int, default=6, help="Parallel worker processes.")
    p.add_argument("--max-points", type=int, default=4200, help="Hard cap after calibration.")
    p.add_argument("--min-points", type=int, default=600, help="Minimum dense-grid target.")
    p.add_argument("--rtol-min", type=float, default=3e-6)
    p.add_argument("--rtol-max", type=float, default=3e-2)
    p.add_argument("--max-step-min", type=float, default=0.005)
    p.add_argument("--max-step-max", type=float, default=0.150)
    p.add_argument(
        "--formal-domain-only",
        action="store_true",
        help="Use exactly the formal domain: rtol<=1e-2 and max_step<=100 ms.",
    )
    p.add_argument(
        "--fixed-shape",
        metavar="NRxNS",
        help="Skip throughput sizing and force a grid shape, e.g. 80x30.",
    )
    p.add_argument(
        "--keep-cache",
        action="store_true",
        help="Keep every numerical cache (can consume many GB). Default keeps only reference/selected overlays.",
    )
    p.add_argument(
        "--fresh",
        action="store_true",
        help="Delete dense-overnight artifacts/cache before starting.",
    )
    p.add_argument(
        "--plan-only",
        action="store_true",
        help="Print the configured domain and fixed-shape plan without running CINDER. With auto sizing, prints calibration intent.",
    )
    return p.parse_args()


def load_formal():
    spec = importlib.util.spec_from_file_location("cinder_solver_convergence_formal", FORMAL_RUN)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import formal study: {FORMAL_RUN}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_csv_rows(path: Path):
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        parsed = {}
        for k, v in row.items():
            if v == "True":
                parsed[k] = True
            elif v == "False":
                parsed[k] = False
            elif v in ("", None):
                parsed[k] = v
            else:
                try:
                    parsed[k] = float(v)
                except (TypeError, ValueError):
                    parsed[k] = v
        out.append(parsed)
    return out


def write_csv_rows(path: Path, rows: list[dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=True) + "\n", encoding="utf-8")


def point_key(rtol: float, step: float):
    return f"{float(rtol):.17g}|{float(step):.17g}"


def parse_fixed_shape(text: str | None):
    if not text:
        return None
    parts = text.lower().replace("×", "x").split("x")
    if len(parts) != 2:
        raise ValueError("--fixed-shape must look like NRxNS, e.g. 80x30")
    nr, ns = map(int, parts)
    if nr < 2 or ns < 2:
        raise ValueError("Both fixed-shape dimensions must be >= 2")
    return nr, ns


def calibration_pairs(rtol_min, rtol_max, step_min, step_max):
    # Interior-heavy set so one fast-failing coarse corner does not inflate throughput.
    rf = np.geomspace(rtol_max / 2.0, max(rtol_min * 2.0, rtol_max / 5000.0), 12)
    sf = np.geomspace(step_min * 1.25, step_max / 1.25, 12)
    order = [0, 6, 3, 9, 1, 7, 4, 10, 2, 8, 5, 11]
    return [(float(rf[i]), float(sf[(i * 5) % 12])) for i in order]


def choose_shape(target_points, rtol_min, rtol_max, step_min, step_max):
    tol_decades = max(math.log10(rtol_max / rtol_min), 1e-6)
    step_decades = max(math.log10(step_max / step_min), 1e-6)
    ratio = min(max(tol_decades / step_decades, 1.25), 4.0)
    ns = max(12, int(round(math.sqrt(target_points / ratio))))
    nr = max(20, int(round(target_points / ns)))
    return nr, ns


def merge_required_axis(dense, required, reverse=False):
    vals = {float(x) for x in dense}
    vals.update(float(x) for x in required)
    return sorted(vals, reverse=reverse)


def build_grid(nr, ns, rtol_min, rtol_max, step_min, step_max, formal_spec):
    rtols = np.geomspace(rtol_max, rtol_min, nr)
    steps = np.geomspace(step_min, step_max, ns)
    # Preserve all formal axis values and the canonical settings inside the dense grid.
    formal_rtols = [float(x) for x in formal_spec["main_sweep"]["relative_tolerances"]]
    formal_steps = [float(x) for x in formal_spec["main_sweep"]["max_steps_s"]]
    can = formal_spec["canonical"]
    rtols = merge_required_axis(rtols, formal_rtols + [float(can["relative_tolerance"])], reverse=True)
    steps = merge_required_axis(steps, formal_steps + [float(can["max_step"])], reverse=False)
    return rtols, steps


def worker(job):
    (
        rtol, step, spec_path, cache_root, ref_path, scales, guards,
        atol_ratio, comparison_step, keep_cache,
    ) = job
    formal = load_formal()
    formal.CACHE = Path(cache_root)
    spec = formal.load_json(Path(spec_path))
    cfg = formal.config(
        spec,
        rtol=float(rtol),
        atol=float(atol_ratio) * float(rtol),
        max_step=float(step),
        comparison_step=float(comparison_step),
    )
    started = time.perf_counter()
    # Thousands of worker-level run_cached() messages are not useful in overnight mode.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        path = formal.run_cached(spec, cfg, allow_failure=True)
        metrics = formal.compare_cache(path, Path(ref_path), scales, guards)
    end_to_end = time.perf_counter() - started
    row = {**cfg, **metrics, "dense_end_to_end_wall_time_s": end_to_end}
    if not keep_cache and Path(path).resolve() != Path(ref_path).resolve():
        shutil.rmtree(path, ignore_errors=True)
    return row


def isfinite(v):
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def rows_lookup(rows):
    return {(float(r["relative_tolerance"]), float(r["max_step"])): r for r in rows}


def dense_matrix(rows, rtols, steps, key, floor=None):
    lookup = rows_lookup(rows)
    z = np.full((len(steps), len(rtols)), np.nan)
    for iy, step in enumerate(steps):
        for ix, rtol in enumerate(rtols):
            row = lookup.get((rtol, step))
            if row and isfinite(row.get(key)):
                value = float(row[key])
                if floor is not None:
                    value = max(value, floor)
                z[iy, ix] = value
    return z


def heatmap(rows, rtols, steps, key, title, label, filename, canonical, *, floor=1e-12):
    z = dense_matrix(rows, rtols, steps, key, floor=floor)
    valid = z[np.isfinite(z) & (z > 0)]
    if not valid.size:
        return
    fig, ax = plt.subplots(figsize=(12.2, 7.0))
    im = ax.imshow(
        np.ma.masked_invalid(z),
        origin="lower",
        aspect="auto",
        norm=LogNorm(vmin=max(float(valid.min()), floor), vmax=max(float(valid.max()), float(valid.min()) * 1.01)),
    )
    # Dense axes: avoid hundreds of labels.
    nx = min(10, len(rtols))
    ny = min(9, len(steps))
    xt = np.unique(np.linspace(0, len(rtols) - 1, nx).round().astype(int))
    yt = np.unique(np.linspace(0, len(steps) - 1, ny).round().astype(int))
    ax.set_xticks(xt, [f"{rtols[i]:.1e}" for i in xt], rotation=45)
    ax.set_yticks(yt, [f"{1000*steps[i]:.1f}" for i in yt])
    ax.set_xlabel("Relative tolerance")
    ax.set_ylabel("Maximum step [ms]")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, label=label)
    cr, cs = float(canonical["relative_tolerance"]), float(canonical["max_step"])
    ix = min(range(len(rtols)), key=lambda i: abs(math.log(rtols[i]) - math.log(cr)))
    iy = min(range(len(steps)), key=lambda i: abs(math.log(steps[i]) - math.log(cs)))
    ax.scatter([ix], [iy], marker="*", s=190, linewidths=1.1, zorder=10)
    fig.tight_layout()
    fig.savefig(PLOTS / filename, dpi=210)
    plt.close(fig)


def contour_plot(rows, rtols, steps, key, title, label, filename, canonical, *, floor=1e-12):
    z = dense_matrix(rows, rtols, steps, key, floor=floor)
    logz = np.where(np.isfinite(z) & (z > 0), np.log10(z), np.nan)
    valid = logz[np.isfinite(logz)]
    if valid.size < 12:
        return
    X, Y = np.meshgrid(np.log10(np.asarray(rtols)), np.log10(np.asarray(steps)))
    levels = np.linspace(float(valid.min()), float(valid.max()), 18)
    fig, ax = plt.subplots(figsize=(12.2, 7.0))
    cf = ax.contourf(X, Y, np.ma.masked_invalid(logz), levels=levels)
    ax.contour(X, Y, np.ma.masked_invalid(logz), levels=levels[::2], linewidths=0.6, alpha=0.65)
    cb = fig.colorbar(cf, ax=ax)
    cb.set_label(f"log10({label})")
    ax.set_xlabel("log10(relative tolerance)")
    ax.set_ylabel("log10(maximum step [s])")
    ax.set_title(title)
    ax.scatter([math.log10(float(canonical["relative_tolerance"]))], [math.log10(float(canonical["max_step"]))], marker="*", s=190, linewidths=1.1)
    fig.tight_layout()
    fig.savefig(PLOTS / filename, dpi=210)
    plt.close(fig)


def hybrid_code(row, guards):
    if row.get("run_status", "completed") != "completed":
        return 4
    if not bool(row.get("transition_count_match", False)):
        return 3
    if not bool(row.get("transition_signature_match", False)):
        return 2
    event = float(row.get("maximum_event_time_error_s", float("nan")))
    regime = float(row.get("regime_mismatch_fraction", float("nan")))
    if math.isfinite(event) and event <= float(guards["maximum_event_time_error_s"]) and math.isfinite(regime) and regime <= float(guards["regime_mismatch_fraction"]):
        return 0
    return 1


def plot_hybrid(rows, rtols, steps, guards):
    lookup = rows_lookup(rows)
    z = np.full((len(steps), len(rtols)), np.nan)
    for iy, step in enumerate(steps):
        for ix, rtol in enumerate(rtols):
            row = lookup.get((rtol, step))
            if row:
                z[iy, ix] = hybrid_code(row, guards)
    fig, ax = plt.subplots(figsize=(12.2, 7.0))
    im = ax.imshow(np.ma.masked_invalid(z), origin="lower", aspect="auto", vmin=-0.5, vmax=4.5)
    nx = min(10, len(rtols)); ny = min(9, len(steps))
    xt = np.unique(np.linspace(0, len(rtols) - 1, nx).round().astype(int))
    yt = np.unique(np.linspace(0, len(steps) - 1, ny).round().astype(int))
    ax.set_xticks(xt, [f"{rtols[i]:.1e}" for i in xt], rotation=45)
    ax.set_yticks(yt, [f"{1000*steps[i]:.1f}" for i in yt])
    ax.set_xlabel("Relative tolerance")
    ax.set_ylabel("Maximum step [ms]")
    ax.set_title("Dense hybrid stability / breakdown map")
    cb = fig.colorbar(im, ax=ax, ticks=[0, 1, 2, 3, 4])
    cb.ax.set_yticklabels(["Converged", "Event/regime drift", "Signature differs", "Count differs", "Failure"])
    fig.tight_layout()
    fig.savefig(PLOTS / "06_dense_hybrid_stability.png", dpi=210)
    plt.close(fig)


def plot_cost_dashboard(rows, canonical):
    completed = [r for r in rows if r.get("run_status", "completed") == "completed" and isfinite(r.get("dense_end_to_end_wall_time_s"))]
    if not completed:
        return
    metrics = [
        ("trajectory_rms_normalized", "Event-aligned trajectory RMS", "Normalized RMS error"),
        ("maximum_event_time_error_s", "Maximum event-time error", "Event-time error [s]"),
        ("regime_mismatch_fraction", "Exact regime-history mismatch", "Fraction of trajectory"),
    ]
    cr, cs = float(canonical["relative_tolerance"]), float(canonical["max_step"])
    can = min(completed, key=lambda r: abs(math.log(float(r["relative_tolerance"]))-math.log(cr)) + abs(math.log(float(r["max_step"]))-math.log(cs)))
    fig, axes = plt.subplots(1, 3, figsize=(16.8, 5.3))
    for ax, (key, title, ylabel) in zip(axes, metrics, strict=True):
        sub = [r for r in completed if isfinite(r.get(key)) and float(r[key]) > 0]
        ax.scatter([float(r["dense_end_to_end_wall_time_s"]) for r in sub], [float(r[key]) for r in sub], s=12, alpha=0.45)
        if isfinite(can.get(key)) and float(can[key]) > 0:
            ax.scatter([float(can["dense_end_to_end_wall_time_s"])], [float(can[key])], marker="*", s=220, linewidths=1.1, label="Canonical")
            ax.legend()
        ax.set_yscale("log")
        ax.set_xlabel("Dense-run end-to-end wall time per point [s]")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, which="both", alpha=0.2)
    fig.suptitle("High-density numerical accuracy versus computational cost")
    fig.tight_layout()
    fig.savefig(PLOTS / "07_dense_cost_vs_convergence_dashboard.png", dpi=210)
    plt.close(fig)


def plot_failure_fraction(rows, rtols, steps):
    lookup = rows_lookup(rows)
    z = np.full((len(steps), len(rtols)), np.nan)
    for iy, step in enumerate(steps):
        for ix, rtol in enumerate(rtols):
            row = lookup.get((rtol, step))
            if row:
                z[iy, ix] = 1.0 if row.get("run_status", "completed") != "completed" else 0.0
    fig, ax = plt.subplots(figsize=(12.2, 7.0))
    im = ax.imshow(np.ma.masked_invalid(z), origin="lower", aspect="auto", vmin=0, vmax=1)
    nx = min(10, len(rtols)); ny = min(9, len(steps))
    xt = np.unique(np.linspace(0, len(rtols) - 1, nx).round().astype(int))
    yt = np.unique(np.linspace(0, len(steps) - 1, ny).round().astype(int))
    ax.set_xticks(xt, [f"{rtols[i]:.1e}" for i in xt], rotation=45)
    ax.set_yticks(yt, [f"{1000*steps[i]:.1f}" for i in yt])
    ax.set_xlabel("Relative tolerance")
    ax.set_ylabel("Maximum step [ms]")
    ax.set_title("Integration/domain failure boundary")
    cb = fig.colorbar(im, ax=ax, ticks=[0, 1])
    cb.ax.set_yticklabels(["Completed", "Failed"])
    fig.tight_layout()
    fig.savefig(PLOTS / "08_dense_failure_boundary.png", dpi=210)
    plt.close(fig)


def keep_selected_overlay(formal, spec, rows, ref_path, scales, guards, atol_ratio, comparison_step):
    candidates = [
        r for r in rows
        if r.get("run_status", "completed") == "completed"
        and bool(r.get("transition_signature_match", False))
        and isfinite(r.get("trajectory_rms_normalized"))
    ]
    if not candidates:
        return None
    selected = max(candidates, key=lambda r: float(r["trajectory_rms_normalized"]))
    cfg = formal.config(
        spec,
        rtol=float(selected["relative_tolerance"]),
        atol=float(selected["absolute_tolerance"]),
        max_step=float(selected["max_step"]),
        comparison_step=float(comparison_step),
    )
    with contextlib.redirect_stdout(io.StringIO()):
        selected_path = formal.run_cached(spec, cfg, allow_failure=True)
    if formal.load_json(selected_path / "metadata.json").get("run_status", "completed") != "completed":
        return None

    can = spec["canonical"]
    can_cfg = formal.config(
        spec,
        rtol=float(can["relative_tolerance"]),
        atol=float(can["absolute_tolerance"]),
        max_step=float(can["max_step"]),
        comparison_step=float(comparison_step),
    )
    with contextlib.redirect_stdout(io.StringIO()):
        can_path = formal.run_cached(spec, can_cfg, allow_failure=False)

    traces = [
        (f"Worst completed dense point ({float(selected['relative_tolerance']):.2g}, {1000*float(selected['max_step']):.1f} ms)", formal.load_trace(selected_path / "trace.npz")),
        ("Canonical", formal.load_trace(can_path / "trace.npz")),
        ("Tight reference", formal.load_trace(Path(ref_path) / "trace.npz")),
    ]
    ref = traces[-1][1]
    t = ref["time_s"]
    specs = [
        ("primary_omega_rad_s", 60/(2*np.pi), "Primary speed [rpm]", "09_dense_extreme_primary_overlay.png"),
        ("secondary_omega_rad_s", 60/(2*np.pi), "Secondary speed [rpm]", "10_dense_extreme_secondary_overlay.png"),
        ("shift_m", 1000.0, "Shift position [mm]", "11_dense_extreme_shift_overlay.png"),
    ]
    for key, factor, ylabel, filename in specs:
        fig, ax = plt.subplots(figsize=(10.0, 5.8))
        for label, trace in traces:
            ax.plot(t, np.interp(t, trace["time_s"], trace[key]) * factor, label=label)
        ax.set_xlabel("Time [s]")
        ax.set_ylabel(ylabel)
        ax.set_title(f"Dense exploratory overlay — {ylabel.split(' [')[0]}")
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(PLOTS / filename, dpi=210)
        plt.close(fig)
    return {
        "relative_tolerance": float(selected["relative_tolerance"]),
        "absolute_tolerance": float(selected["absolute_tolerance"]),
        "max_step": float(selected["max_step"]),
        "trajectory_rms_normalized": float(selected["trajectory_rms_normalized"]),
        "maximum_event_time_error_s": float(selected["maximum_event_time_error_s"]) if isfinite(selected.get("maximum_event_time_error_s")) else None,
    }


def generate_plots(rows, rtols, steps, spec):
    PLOTS.mkdir(parents=True, exist_ok=True)
    canonical = spec["canonical"]
    heatmap(rows, rtols, steps, "trajectory_rms_normalized", "Dense event-aligned RMS trajectory error", "Normalized RMS error", "01_dense_accuracy_heatmap.png", canonical)
    contour_plot(rows, rtols, steps, "trajectory_rms_normalized", "Dense event-aligned RMS trajectory-error contours", "normalized RMS error", "02_dense_accuracy_contours.png", canonical)
    heatmap(rows, rtols, steps, "maximum_event_time_error_s", "Dense maximum event-time error", "Event-time error [s]", "03_dense_event_time_heatmap.png", canonical)
    contour_plot(rows, rtols, steps, "maximum_event_time_error_s", "Dense maximum event-time-error contours", "event-time error [s]", "04_dense_event_time_contours.png", canonical)
    heatmap(rows, rtols, steps, "regime_mismatch_fraction", "Dense exact regime-mismatch fraction", "Fraction of trajectory", "05_dense_regime_mismatch_heatmap.png", canonical)
    plot_hybrid(rows, rtols, steps, spec["review_guards"])
    plot_cost_dashboard(rows, canonical)
    plot_failure_fraction(rows, rtols, steps)


def main():
    args = parse_args()
    if args.formal_domain_only:
        args.rtol_max = 1e-2
        args.max_step_max = 0.100
    if args.workers < 1:
        raise ValueError("--workers must be >= 1")
    if args.hours <= 0:
        raise ValueError("--hours must be > 0")

    if args.fresh and ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)

    fixed = parse_fixed_shape(args.fixed_shape)
    if args.plan_only:
        print("Dense overnight explorer (plan only)")
        print(f"  workers: {args.workers}")
        print(f"  requested budget: {args.hours:g} h")
        print(f"  rtol domain: [{args.rtol_min:.2g}, {args.rtol_max:.2g}]")
        print(f"  max-step domain: [{1000*args.max_step_min:g}, {1000*args.max_step_max:g}] ms")
        if fixed:
            print(f"  fixed base shape: {fixed[0]} x {fixed[1]} ~= {fixed[0]*fixed[1]} points before formal-axis insertion")
        else:
            print("  grid size: auto-sized after a 12-point parallel throughput calibration")
        print(f"  output root: {ROOT}")
        return 0

    formal = load_formal()
    formal.verify_environment()
    spec = formal.load_json(SPEC_FILE)
    formal.CACHE = CACHE

    # Tight reference is strict and remains in the dense cache.
    ref = spec["reference"]
    ref_cfg = formal.config(
        spec,
        rtol=float(ref["relative_tolerance"]),
        atol=float(ref["absolute_tolerance"]),
        max_step=float(ref["max_step"]),
        comparison_step=float(ref["comparison_step_s"]),
    )
    print("Preparing tight numerical reference...")
    ref_path = formal.run_cached(spec, ref_cfg, allow_failure=False)
    scales = formal.state_scales(formal.load_trace(ref_path / "trace.npz"))
    guards = spec["review_guards"]
    atol_ratio = float(spec["main_sweep"]["absolute_tolerance_ratio"])
    comparison_step = float(spec["main_sweep"]["comparison_step_s"])

    if GRID_FILE.is_file() and not args.fresh:
        grid = json.loads(GRID_FILE.read_text(encoding="utf-8"))
        rtols = [float(x) for x in grid["relative_tolerances"]]
        steps = [float(x) for x in grid["max_steps_s"]]
        print(f"Resuming existing dense grid: {len(rtols)} x {len(steps)} = {len(rtols)*len(steps)} points")
        calibration = grid.get("calibration", {})
        executor = ProcessPoolExecutor(max_workers=args.workers)
    else:
        executor = ProcessPoolExecutor(max_workers=args.workers)
        if fixed:
            nr, ns = fixed
            calibration = {"mode": "fixed_shape", "requested_shape": [nr, ns]}
        else:
            pairs = calibration_pairs(args.rtol_min, args.rtol_max, args.max_step_min, args.max_step_max)
            print(f"Calibrating throughput with {len(pairs)} points on {args.workers} workers...")
            jobs = [
                (
                    rtol, step, str(SPEC_FILE), str(CACHE), str(ref_path), scales, guards,
                    atol_ratio, comparison_step, False,
                )
                for rtol, step in pairs
            ]
            t0 = time.perf_counter()
            futures = [executor.submit(worker, job) for job in jobs]
            calibration_rows = [f.result() for f in as_completed(futures)]
            elapsed = time.perf_counter() - t0
            throughput = len(calibration_rows) / max(elapsed, 1e-9)
            # Leave headroom for plotting, failures, and slower tight points.
            remaining_budget_s = max(args.hours * 3600.0 - elapsed, 0.0)
            estimated = int(throughput * remaining_budget_s * 0.82)
            target = min(args.max_points, max(args.min_points, estimated))
            nr, ns = choose_shape(target, args.rtol_min, args.rtol_max, args.max_step_min, args.max_step_max)
            calibration = {
                "mode": "throughput_calibrated",
                "points": len(calibration_rows),
                "elapsed_s": elapsed,
                "throughput_points_per_s": throughput,
                "raw_estimated_points_for_budget": estimated,
                "target_points_before_axis_insertion": target,
                "chosen_base_shape": [nr, ns],
                "requested_hours": args.hours,
                "remaining_budget_after_calibration_s": remaining_budget_s,
                "workers": args.workers,
            }
            write_json(CALIBRATION_FILE, {"summary": calibration, "rows": calibration_rows})
            print(f"Calibration throughput: {throughput:.4f} points/s")
            print(f"Chosen base grid: {nr} x {ns} ~= {nr*ns} points")

        rtols, steps = build_grid(nr, ns, args.rtol_min, args.rtol_max, args.max_step_min, args.max_step_max, spec)
        grid = {
            "relative_tolerances": rtols,
            "max_steps_s": steps,
            "total_points": len(rtols) * len(steps),
            "domain": {
                "rtol_min": args.rtol_min,
                "rtol_max": args.rtol_max,
                "max_step_min_s": args.max_step_min,
                "max_step_max_s": args.max_step_max,
            },
            "calibration": calibration,
            "formal_axis_values_forced_into_grid": True,
        }
        write_json(GRID_FILE, grid)
        print(f"Final grid after formal-axis insertion: {len(rtols)} x {len(steps)} = {len(rtols)*len(steps)} points")

    try:
        existing = read_csv_rows(ROWS_FILE)
        done = {point_key(r["relative_tolerance"], r["max_step"]) for r in existing}
        rows = list(existing)
        pending = [
            (rtol, step)
            for rtol in rtols
            for step in steps
            if point_key(rtol, step) not in done
        ]
        print(f"Already complete: {len(rows)}; pending: {len(pending)}")

        jobs = [
            (
                rtol, step, str(SPEC_FILE), str(CACHE), str(ref_path), scales, guards,
                atol_ratio, comparison_step, args.keep_cache,
            )
            for rtol, step in pending
        ]
        start = time.perf_counter()
        futures = {executor.submit(worker, job): (job[0], job[1]) for job in jobs}
        since_checkpoint = 0
        for i, future in enumerate(as_completed(futures), start=1):
            rtol, step = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {
                    "relative_tolerance": float(rtol),
                    "absolute_tolerance": atol_ratio * float(rtol),
                    "max_step": float(step),
                    "run_status": "worker_exception",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "passes_review_guards": False,
                }
            rows.append(row)
            since_checkpoint += 1
            if since_checkpoint >= 20 or i == len(futures):
                rows.sort(key=lambda r: (-float(r["relative_tolerance"]), float(r["max_step"])))
                write_csv_rows(ROWS_FILE, rows)
                failed = [r for r in rows if r.get("run_status", "completed") != "completed"]
                write_csv_rows(FAILURES_FILE, failed)
                since_checkpoint = 0
            if i % 50 == 0 or i == len(futures):
                elapsed = time.perf_counter() - start
                rate = i / max(elapsed, 1e-9)
                remaining = (len(futures) - i) / max(rate, 1e-9)
                print(
                    f"progress {i}/{len(futures)} new points | "
                    f"{rate:.3f} pt/s | approx {remaining/60:.1f} min remaining | "
                    f"failures {sum(r.get('run_status','completed')!='completed' for r in rows)}"
                )
    finally:
        executor.shutdown(wait=True, cancel_futures=False)

    rows = read_csv_rows(ROWS_FILE)
    generate_plots(rows, rtols, steps, spec)
    selected = keep_selected_overlay(formal, spec, rows, ref_path, scales, guards, atol_ratio, comparison_step)

    completed = [r for r in rows if r.get("run_status", "completed") == "completed"]
    failures = [r for r in rows if r.get("run_status", "completed") != "completed"]
    exact = [r for r in completed if bool(r.get("transition_signature_match", False))]
    summary = {
        "exploratory_only": True,
        "formal_sweep_unchanged": True,
        "grid_points": len(rows),
        "grid_shape": [len(rtols), len(steps)],
        "completed": len(completed),
        "failures": len(failures),
        "exact_transition_signature_completed": len(exact),
        "domain": json.loads(GRID_FILE.read_text(encoding="utf-8"))["domain"],
        "calibration": calibration,
        "selected_worst_completed_same_signature_overlay": selected,
        "workers": args.workers,
        "keep_cache": bool(args.keep_cache),
    }
    write_json(SUMMARY_FILE, summary)

    print("\nDense exploratory sweep complete.")
    print(f"  rows:  {ROWS_FILE}")
    print(f"  plots: {PLOTS}")
    print(f"  summary: {SUMMARY_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
