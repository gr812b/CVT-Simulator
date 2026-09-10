"""LSODA trajectory and hybrid-event convergence study for CINDER v1.1.2."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np

import cinder
from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)
from cinder.execution.hybrid import integrate_hybrid

HERE = Path(__file__).resolve().parent
RELEASE_ROOT = HERE.parents[1]
VERIFY = RELEASE_ROOT / "verify_environment.py"
SPEC_FILE = HERE / "study.json"
ARTIFACTS = HERE / "artifacts"
CACHE = HERE / "work" / "cache"
EXPECTED_CINDER_VERSION = "1.1.2"

STATE_KEYS = (
    "primary_omega_rad_s",
    "secondary_omega_rad_s",
    "belt_speed_m_s",
    "shift_m",
    "shift_speed_m_s",
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run a reduced grid to verify the machinery before the full paper-facing sweep.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete this study's numerical cache before running.",
    )
    return parser.parse_args()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload, *, allow_nan=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, allow_nan=allow_nan) + "\n",
        encoding="utf-8",
    )


def write_rows(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields, seen = [], set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def verify_environment():
    subprocess.run([sys.executable, str(VERIFY)], check=True)
    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise RuntimeError(
            f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__} "
            f"at {Path(cinder.__file__).resolve()}."
        )


def validate_and_decode(document):
    validation = validate_simulation_case_document(document)
    if not validation.is_valid:
        for finding in validation.findings:
            print(
                f"[{finding.severity}] "
                f"{finding.document_path or '/'}: {finding.message}"
            )
        raise RuntimeError("Resolved convergence input failed CINDER validation.")
    return decode_simulation_case_document(document)


def resolved_document(spec, *, rtol, atol, max_step):
    base = (HERE / spec["base_document"]).resolve()
    if not base.is_file():
        raise FileNotFoundError(
            f"Frozen default is missing: {base}. "
            "This study intentionally depends only on the release defaults folder."
        )
    document = copy.deepcopy(load_json(base))
    document["scenario"]["time_span_s"] = list(spec["reference"]["time_span_s"])
    integ = document["execution"]["integrator"]
    integ["relative_tolerance"] = float(rtol)
    integ["absolute_tolerance"] = float(atol)
    integ["max_step"] = float(max_step)
    integ["method"] = "LSODA"
    integ["retain_dense_output"] = True
    return document


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def config(spec, *, rtol, atol, max_step, comparison_step):
    base = (HERE / spec["base_document"]).resolve()
    return {
        "cinder_version": EXPECTED_CINDER_VERSION,
        "base_document_sha256": file_sha256(base),
        "analysis_revision": 2,
        "base_document": spec["base_document"],
        "time_span_s": list(spec["reference"]["time_span_s"]),
        "relative_tolerance": float(rtol),
        "absolute_tolerance": float(atol),
        "max_step": float(max_step),
        "comparison_step_s": float(comparison_step),
        "method": "LSODA",
    }


def cache_key(cfg):
    data = json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()[:16]


def transition_rows(result):
    rows = []
    for i, record in enumerate(result.transitions):
        rows.append(
            {
                "index": i,
                "time_s": float(record.time),
                "fired_event_names": "|".join(record.fired_event_names),
                "previous_mode": str(record.previous_mode),
                "next_mode": str(record.transition.next_mode),
                "reason": record.transition.reason,
                "has_successor_state": bool(record.transition.has_successor_state),
            }
        )
    return rows


def segment_rows(result):
    return [
        {
            "index": i,
            "start_time_s": float(segment.start_time),
            "end_time_s": float(segment.end_time),
            "mode": str(segment.mode),
        }
        for i, segment in enumerate(result.segments)
    ]


def uniform_segment_times(start, end, step):
    if end <= start:
        return np.asarray([start], dtype=float)
    values = start + step * np.arange(int(math.floor((end - start) / step)) + 1)
    if end - values[-1] > 1e-12:
        values = np.append(values, end)
    else:
        values[-1] = end
    return values


def compact_trace(result, comparison_step_s):
    """Uniformly sample raw dense segments without interpolating across resets.

    If an exact event time appears on both adjacent segments, the later segment
    overwrites it so the compact comparison trace stores the post-transition state.
    """
    by_time = {}
    for segment in result.segments:
        if segment.has_dense_output:
            times = uniform_segment_times(
                segment.start_time,
                segment.end_time,
                comparison_step_s,
            )
            states = segment.dense_state_at(times)
        else:
            times = segment.time
            states = segment.state
        for j, t in enumerate(times):
            # First five entries are the CVT block by CINDER composed-system contract.
            by_time[float(t)] = np.asarray(states[:5, j], dtype=float)
    times = np.asarray(sorted(by_time), dtype=float)
    matrix = np.column_stack([by_time[t] for t in times])
    return {
        "time_s": times,
        "primary_omega_rad_s": matrix[0],
        "secondary_omega_rad_s": matrix[1],
        "belt_speed_m_s": matrix[2],
        "shift_m": matrix[3],
        "shift_speed_m_s": matrix[4],
    }

def save_trace(path, trace):
    np.savez_compressed(path, **trace)


def load_trace(path):
    with np.load(path) as data:
        return {key: np.asarray(data[key], dtype=float) for key in data.files}


def cache_complete(path, cfg):
    needed = [
        path / "config.json",
        path / "trace.npz",
        path / "transitions.json",
        path / "segments.json",
        path / "metadata.json",
    ]
    return all(p.is_file() for p in needed) and load_json(path / "config.json") == cfg


def run_cached(spec, cfg):
    path = CACHE / cache_key(cfg)
    if cache_complete(path, cfg):
        print(
            "cache hit:",
            f"rtol={cfg['relative_tolerance']:.1e}",
            f"atol={cfg['absolute_tolerance']:.1e}",
            f"max_step={1000*cfg['max_step']:.3g} ms",
        )
        return path

    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)

    print(
        "running:",
        f"rtol={cfg['relative_tolerance']:.1e}",
        f"atol={cfg['absolute_tolerance']:.1e}",
        f"max_step={1000*cfg['max_step']:.3g} ms",
    )
    document = resolved_document(
        spec,
        rtol=cfg["relative_tolerance"],
        atol=cfg["absolute_tolerance"],
        max_step=cfg["max_step"],
    )
    decoded = validate_and_decode(document)
    started = time.perf_counter()
    result = integrate_hybrid(
        system=decoded.system,
        time_span=decoded.time_span,
        initial_state=decoded.initial_state,
        initial_mode=decoded.initial_mode,
        settings=decoded.integrator_settings,
    )
    elapsed = time.perf_counter() - started

    write_json(path / "config.json", cfg)
    save_trace(path / "trace.npz", compact_trace(result, cfg["comparison_step_s"]))
    write_json(path / "transitions.json", transition_rows(result))
    write_json(path / "segments.json", segment_rows(result))
    write_json(
        path / "metadata.json",
        {
            "completed": result.completed,
            "termination_reason": result.termination_reason,
            "final_time_s": result.final_time,
            "transition_count": len(result.transitions),
            "segment_count": len(result.segments),
            "native_solver_point_count": sum(
                int(segment.time.size)
                for segment in result.segments
            ),
            "wall_time_s": elapsed,
        },
    )
    return path


def state_scales(reference):
    floors = {
        "primary_omega_rad_s": 100.0,
        "secondary_omega_rad_s": 100.0,
        "belt_speed_m_s": 5.0,
        "shift_m": 0.02,
        "shift_speed_m_s": 0.05,
    }
    out = {}
    for key in STATE_KEYS:
        values = reference[key]
        out[key] = max(
            float(np.max(np.abs(values))),
            float(np.ptp(values)),
            floors[key],
        )
    return out


def compare_trace(candidate, reference, scales):
    grid = reference["time_s"]
    all_errors = []
    result = {}
    for key in STATE_KEYS:
        ref = reference[key]
        cand = np.interp(grid, candidate["time_s"], candidate[key])
        error = (cand - ref) / scales[key]
        all_errors.append(error)
        result[f"{key}_rms_normalized"] = float(np.sqrt(np.mean(error**2)))
        result[f"{key}_max_abs_normalized"] = float(np.max(np.abs(error)))
        result[f"{key}_final_abs_normalized"] = float(abs(error[-1]))
    stack = np.vstack(all_errors)
    result["trajectory_rms_normalized"] = float(np.sqrt(np.mean(stack**2)))
    result["trajectory_max_abs_normalized"] = float(np.max(np.abs(stack)))
    result["final_state_rms_normalized"] = float(
        np.sqrt(np.mean(stack[:, -1]**2))
    )
    return result


def signature(rows):
    return tuple(
        f"{row['fired_event_names']} -> {row['next_mode']} [reset={row['has_successor_state']}]"
        for row in rows
    )


def modes_on_grid(grid, segments):
    ends = np.asarray([row["end_time_s"] for row in segments], dtype=float)
    modes = np.asarray([row["mode"] for row in segments], dtype=object)
    idx = np.searchsorted(ends, grid, side="right")
    idx = np.clip(idx, 0, len(segments)-1)
    return modes[idx]


def compare_cache(path, reference_path, scales, guards):
    candidate = load_trace(path / "trace.npz")
    reference = load_trace(reference_path / "trace.npz")
    metrics = compare_trace(candidate, reference, scales)

    c_trans = load_json(path / "transitions.json")
    r_trans = load_json(reference_path / "transitions.json")
    c_segments = load_json(path / "segments.json")
    r_segments = load_json(reference_path / "segments.json")
    meta = load_json(path / "metadata.json")

    sig_match = signature(c_trans) == signature(r_trans)
    count_match = len(c_trans) == len(r_trans)
    if sig_match:
        event_errors = [
            abs(float(c["time_s"]) - float(r["time_s"]))
            for c, r in zip(c_trans, r_trans, strict=True)
        ]
        max_event = max(event_errors, default=0.0)
        rms_event = (
            float(np.sqrt(np.mean(np.asarray(event_errors)**2)))
            if event_errors else 0.0
        )
    else:
        max_event = float("nan")
        rms_event = float("nan")

    grid = reference["time_s"]
    mode_mismatch = float(
        np.mean(
            modes_on_grid(grid, c_segments)
            != modes_on_grid(grid, r_segments)
        )
    )

    metrics.update(
        {
            "transition_count": len(c_trans),
            "reference_transition_count": len(r_trans),
            "transition_count_match": count_match,
            "transition_signature_match": sig_match,
            "maximum_event_time_error_s": max_event,
            "rms_event_time_error_s": rms_event,
            "regime_mismatch_fraction": mode_mismatch,
            "wall_time_s": float(meta["wall_time_s"]),
            "native_solver_point_count": int(meta["native_solver_point_count"]),
        }
    )

    metrics["passes_review_guards"] = bool(
        metrics["trajectory_rms_normalized"]
        <= guards["trajectory_rms_normalized"]
        and metrics["trajectory_max_abs_normalized"]
        <= guards["trajectory_max_abs_normalized"]
        and (
            not guards["require_exact_transition_signature"]
            or sig_match
        )
        and (
            math.isfinite(max_event)
            and max_event <= guards["maximum_event_time_error_s"]
        )
        and mode_mismatch <= guards["regime_mismatch_fraction"]
    )
    return metrics


def full_grid(spec, quick):
    if quick:
        return [1e-2, 1e-3, 1e-4, 1e-5], [0.1, 0.02, 0.005]
    return (
        [float(x) for x in spec["main_sweep"]["relative_tolerances"]],
        [float(x) for x in spec["main_sweep"]["max_steps_s"]],
    )


def atol_grid(spec, quick):
    values = [float(x) for x in spec["absolute_tolerance_sweep"]["absolute_tolerances"]]
    return values[::2] if quick else values


def hybrid_code(row, guards):
    if not row["transition_count_match"]:
        return 3
    if not row["transition_signature_match"]:
        return 2
    if (
        math.isfinite(row["maximum_event_time_error_s"])
        and row["maximum_event_time_error_s"] <= guards["maximum_event_time_error_s"]
        and row["regime_mismatch_fraction"] <= guards["regime_mismatch_fraction"]
    ):
        return 0
    return 1


def plot_heatmaps(main_rows, rtols, steps, guards):
    lookup = {
        (float(r["relative_tolerance"]), float(r["max_step"])): r
        for r in main_rows
    }

    error = np.array(
        [
            [lookup[(rtol, step)]["trajectory_rms_normalized"] for rtol in rtols]
            for step in steps
        ],
        dtype=float,
    )
    fig, ax = plt.subplots(figsize=(10.2, 6.4))
    positive = error[np.isfinite(error) & (error > 0)]
    vmin = max(float(np.min(positive)) if positive.size else 1e-12, 1e-12)
    vmax = max(float(np.max(positive)) if positive.size else 1.0, vmin*1.01)
    im = ax.imshow(error, origin="lower", aspect="auto", norm=LogNorm(vmin=vmin, vmax=vmax))
    ax.set_xticks(range(len(rtols)), [f"{x:.0e}" for x in rtols], rotation=45)
    ax.set_yticks(range(len(steps)), [f"{1000*x:g}" for x in steps])
    ax.set_xlabel("Relative tolerance")
    ax.set_ylabel("Maximum step [ms]")
    ax.set_title("Normalized RMS trajectory error")
    fig.colorbar(im, ax=ax, label="Normalized RMS error")
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "01_accuracy_heatmap.png", dpi=180)
    plt.close(fig)

    codes = np.array(
        [
            [hybrid_code(lookup[(rtol, step)], guards) for rtol in rtols]
            for step in steps
        ],
        dtype=float,
    )
    fig, ax = plt.subplots(figsize=(10.2, 6.4))
    im = ax.imshow(codes, origin="lower", aspect="auto", vmin=-0.5, vmax=3.5)
    ax.set_xticks(range(len(rtols)), [f"{x:.0e}" for x in rtols], rotation=45)
    ax.set_yticks(range(len(steps)), [f"{1000*x:g}" for x in steps])
    ax.set_xlabel("Relative tolerance")
    ax.set_ylabel("Maximum step [ms]")
    ax.set_title("Hybrid sequence and event convergence")
    cb = fig.colorbar(im, ax=ax, ticks=[0,1,2,3])
    cb.ax.set_yticklabels(
        ["Sequence+events converged", "Same signature; event drift", "Signature differs", "Transition count differs"]
    )
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "02_hybrid_stability_map.png", dpi=180)
    plt.close(fig)

    event = np.array(
        [
            [
                max(float(lookup[(rtol, step)]["maximum_event_time_error_s"]), 1e-12)
                if math.isfinite(float(lookup[(rtol, step)]["maximum_event_time_error_s"]))
                else np.nan
                for rtol in rtols
            ]
            for step in steps
        ],
        dtype=float,
    )
    fig, ax = plt.subplots(figsize=(10.2, 6.4))
    positive = event[np.isfinite(event) & (event > 0)]
    vmin = max(float(np.min(positive)) if positive.size else 1e-12, 1e-12)
    vmax = max(float(np.max(positive)) if positive.size else 1.0, vmin*1.01)
    im = ax.imshow(event, origin="lower", aspect="auto", norm=LogNorm(vmin=vmin, vmax=vmax))
    ax.set_xticks(range(len(rtols)), [f"{x:.0e}" for x in rtols], rotation=45)
    ax.set_yticks(range(len(steps)), [f"{1000*x:g}" for x in steps])
    ax.set_xlabel("Relative tolerance")
    ax.set_ylabel("Maximum step [ms]")
    ax.set_title("Maximum corresponding event-time error")
    fig.colorbar(im, ax=ax, label="Event-time error [s]")
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "03_event_time_heatmap.png", dpi=180)
    plt.close(fig)


def plot_cost(main_rows):
    fig, ax = plt.subplots(figsize=(9.2, 5.8))
    for status, label in ((False, "Needs review"), (True, "Passes all guards")):
        group = [r for r in main_rows if bool(r["passes_review_guards"]) is status]
        if group:
            ax.scatter(
                [r["wall_time_s"] for r in group],
                [r["trajectory_rms_normalized"] for r in group],
                label=label,
            )
    ax.set_yscale("log")
    ax.set_xlabel("End-to-end numerical-run wall time [s]")
    ax.set_ylabel("Normalized RMS trajectory error")
    ax.set_title("Accuracy versus computational cost")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "04_accuracy_vs_wall_time.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9.2, 5.8))
    ax.scatter(
        [r["native_solver_point_count"] for r in main_rows],
        [r["trajectory_rms_normalized"] for r in main_rows],
    )
    ax.set_yscale("log")
    ax.set_xlabel("Native solve_ivp points retained across hybrid segments")
    ax.set_ylabel("Normalized RMS trajectory error")
    ax.set_title("Accuracy versus solver-native point count")
    ax.grid(True, which="both", alpha=0.25)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "05_accuracy_vs_native_points.png", dpi=180)
    plt.close(fig)


def plot_atol(rows):
    rows = sorted(rows, key=lambda r: float(r["absolute_tolerance"]), reverse=True)
    x = [float(r["absolute_tolerance"]) for r in rows]
    fig, ax = plt.subplots(figsize=(9.2, 5.8))
    ax.plot(x, [r["trajectory_rms_normalized"] for r in rows], marker="o", label="Combined trajectory")
    ax.plot(x, [r["shift_m_rms_normalized"] for r in rows], marker="o", label="Shift position")
    ax.plot(x, [r["shift_speed_m_s_rms_normalized"] for r in rows], marker="o", label="Shift speed")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.invert_xaxis()
    ax.set_xlabel("Absolute tolerance")
    ax.set_ylabel("Normalized RMS error")
    ax.set_title("Absolute-tolerance sensitivity")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "06_absolute_tolerance_sensitivity.png", dpi=180)
    plt.close(fig)


def plot_overlays(reference_path, loose_path, canonical_path):
    traces = [
        ("Loose corner", load_trace(loose_path / "trace.npz")),
        ("Canonical settings", load_trace(canonical_path / "trace.npz")),
        ("Tight reference", load_trace(reference_path / "trace.npz")),
    ]
    reference = traces[-1][1]
    time_s = reference["time_s"]
    specs = [
        ("primary_omega_rad_s", 60/(2*np.pi), "Primary speed [rpm]", "07_primary_speed_overlay.png"),
        ("secondary_omega_rad_s", 60/(2*np.pi), "Secondary speed [rpm]", "08_secondary_speed_overlay.png"),
        ("shift_m", 1000.0, "Shift position [mm]", "09_shift_overlay.png"),
    ]
    for key, factor, ylabel, filename in specs:
        fig, ax = plt.subplots(figsize=(9.5, 5.8))
        for label, trace in traces:
            values = np.interp(time_s, trace["time_s"], trace[key]) * factor
            ax.plot(time_s, values, label=label)
        ax.set_xlabel("Time [s]")
        ax.set_ylabel(ylabel)
        ax.set_title(f"Solver-refinement overlay — {ylabel.split(' [')[0]}")
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(ARTIFACTS / filename, dpi=180)
        plt.close(fig)


def coarsest_passing(rows):
    passing = [r for r in rows if r["passes_review_guards"]]
    if not passing:
        return None
    return max(
        passing,
        key=lambda r: (
            float(r["max_step"]),
            float(r["relative_tolerance"]),
            float(r["absolute_tolerance"]),
        ),
    )


def main():
    args = parse_args()
    verify_environment()
    spec = load_json(SPEC_FILE)

    if args.fresh and CACHE.exists():
        shutil.rmtree(CACHE)
    CACHE.mkdir(parents=True, exist_ok=True)
    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)

    ref = spec["reference"]
    ref_cfg = config(
        spec,
        rtol=ref["relative_tolerance"],
        atol=ref["absolute_tolerance"],
        max_step=ref["max_step"],
        comparison_step=ref["comparison_step_s"],
    )
    print("\nTight numerical reference")
    reference_path = run_cached(spec, ref_cfg)
    reference_trace = load_trace(reference_path / "trace.npz")
    scales = state_scales(reference_trace)
    write_json(ARTIFACTS / "state_normalization_scales.json", scales)

    rtols, steps = full_grid(spec, args.quick)
    main_rows = []
    print(f"\nMain grid: {len(rtols)} × {len(steps)} = {len(rtols)*len(steps)} runs")
    for rtol in rtols:
        for step in steps:
            cfg = config(
                spec,
                rtol=rtol,
                atol=spec["main_sweep"]["absolute_tolerance_ratio"] * rtol,
                max_step=step,
                comparison_step=spec["main_sweep"]["comparison_step_s"],
            )
            path = run_cached(spec, cfg)
            main_rows.append(
                {
                    **cfg,
                    **compare_cache(
                        path, reference_path, scales, spec["review_guards"]
                    ),
                }
            )
    write_rows(ARTIFACTS / "main_sweep.csv", main_rows)

    acfg = spec["absolute_tolerance_sweep"]
    atol_rows = []
    print(f"\nAbsolute-tolerance sweep")
    for atol in atol_grid(spec, args.quick):
        cfg = config(
            spec,
            rtol=acfg["relative_tolerance"],
            atol=atol,
            max_step=acfg["max_step"],
            comparison_step=acfg["comparison_step_s"],
        )
        path = run_cached(spec, cfg)
        atol_rows.append(
            {
                **cfg,
                **compare_cache(
                    path, reference_path, scales, spec["review_guards"]
                ),
            }
        )
    write_rows(ARTIFACTS / "absolute_tolerance_sweep.csv", atol_rows)

    loose_cfg = config(
        spec,
        rtol=max(rtols),
        atol=spec["main_sweep"]["absolute_tolerance_ratio"] * max(rtols),
        max_step=max(steps),
        comparison_step=spec["main_sweep"]["comparison_step_s"],
    )
    loose_path = run_cached(spec, loose_cfg)

    can = spec["canonical"]
    canonical_cfg = config(
        spec,
        rtol=can["relative_tolerance"],
        atol=can["absolute_tolerance"],
        max_step=can["max_step"],
        comparison_step=spec["main_sweep"]["comparison_step_s"],
    )
    canonical_path = run_cached(spec, canonical_cfg)
    canonical_metrics = compare_cache(
        canonical_path, reference_path, scales, spec["review_guards"]
    )

    plot_heatmaps(main_rows, rtols, steps, spec["review_guards"])
    plot_cost(main_rows)
    plot_atol(atol_rows)
    plot_overlays(reference_path, loose_path, canonical_path)

    coarse = coarsest_passing(main_rows)
    summary = {
        "study": spec,
        "cinder_version": cinder.__version__,
        "run_mode": "quick" if args.quick else "full",
        "state_normalization_scales": scales,
        "reference": {
            **ref_cfg,
            **load_json(reference_path / "metadata.json"),
        },
        "canonical": {
            **canonical_cfg,
            **canonical_metrics,
        },
        "passing_main_grid_points": sum(
            bool(r["passes_review_guards"]) for r in main_rows
        ),
        "total_main_grid_points": len(main_rows),
        "coarsest_passing_grid_point": coarse,
    }
    write_json(ARTIFACTS / "summary.json", summary, allow_nan=True)

    lines = [
        "# CINDER v1.1.2 solver-convergence study",
        "",
        f"Mode: **{'quick preview' if args.quick else 'full paper-facing sweep'}**",
        "",
        "## Canonical settings versus tight numerical reference",
        "",
        f"- normalized trajectory RMS: `{canonical_metrics['trajectory_rms_normalized']:.6g}`",
        f"- normalized max trajectory error: `{canonical_metrics['trajectory_max_abs_normalized']:.6g}`",
        f"- transition signature match: **{canonical_metrics['transition_signature_match']}**",
        f"- maximum event-time error: `{canonical_metrics['maximum_event_time_error_s']:.6g} s`",
        f"- regime mismatch fraction: `{canonical_metrics['regime_mismatch_fraction']:.6g}`",
        f"- passes all review guards: **{canonical_metrics['passes_review_guards']}**",
        "",
        f"Main-grid points passing every review guard: **{summary['passing_main_grid_points']}/{summary['total_main_grid_points']}**.",
        "",
    ]
    if coarse is not None:
        lines += [
            "## Coarsest sampled passing point",
            "",
            f"- rtol: `{coarse['relative_tolerance']:.3g}`",
            f"- atol: `{coarse['absolute_tolerance']:.3g}`",
            f"- max step: `{1000*coarse['max_step']:.3g} ms`",
            f"- trajectory RMS: `{coarse['trajectory_rms_normalized']:.6g}`",
            "",
            "This is descriptive only; it does not silently change other frozen-study settings.",
        ]
    else:
        lines += [
            "No main-grid point passed every review guard. Inspect the heatmaps and raw sweep before changing any numerical setting.",
        ]
    lines += [
        "",
        "Wall time is machine-dependent. Native solver-point count is a transparent cost proxy and is not mislabeled as SciPy function evaluations.",
    ]
    (ARTIFACTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nSolver convergence complete: {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
