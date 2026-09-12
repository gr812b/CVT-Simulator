"""LSODA trajectory and hybrid-event convergence study for CINDER v1.1.2."""
# solver-convergence event-aligned hybrid metrics patch v2
# solver-convergence failure-aware sweep patch v1

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
        # Revision 3 adds per-segment traces and hybrid event-aligned metrics.
        # Bumping this intentionally invalidates older numerical caches because
        # those caches do not preserve the two sides of hybrid resets.
        "analysis_revision": 3,
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
    """Uniformly sample raw dense segments for absolute-time diagnostics.

    If an exact event time appears on both adjacent segments, the later segment
    overwrites it so this compact trace stores the post-transition state. This
    representation is retained for intuitive absolute-time overlays only; the
    convergence metric itself uses ``segment_traces.npz`` so reset sides remain
    distinct.
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


def segment_trace_payload(result, comparison_step_s):
    """Sample every hybrid segment separately, preserving both event sides."""
    payload = {"segment_count": np.asarray([len(result.segments)], dtype=int)}
    for i, segment in enumerate(result.segments):
        if segment.has_dense_output:
            times = uniform_segment_times(
                segment.start_time,
                segment.end_time,
                comparison_step_s,
            )
            states = segment.dense_state_at(times)
        else:
            times = np.asarray(segment.time, dtype=float)
            states = np.asarray(segment.state, dtype=float)
        prefix = f"segment_{i:03d}_"
        payload[prefix + "time_s"] = np.asarray(times, dtype=float)
        for k, key in enumerate(STATE_KEYS):
            payload[prefix + key] = np.asarray(states[k], dtype=float)
    return payload


def save_segment_traces(path, payload):
    np.savez_compressed(path, **payload)


def load_segment_traces(path):
    with np.load(path) as data:
        return {key: np.asarray(data[key]) for key in data.files}


def unpack_segment_trace(payload, index):
    prefix = f"segment_{index:03d}_"
    return {
        "time_s": np.asarray(payload[prefix + "time_s"], dtype=float),
        **{
            key: np.asarray(payload[prefix + key], dtype=float)
            for key in STATE_KEYS
        },
    }

def save_trace(path, trace):
    np.savez_compressed(path, **trace)


def load_trace(path):
    with np.load(path) as data:
        return {key: np.asarray(data[key], dtype=float) for key in data.files}


def cache_status(path, cfg):
    """Return cached run status when the revision-3 cache is complete."""
    config_path = path / "config.json"
    metadata_path = path / "metadata.json"
    if not config_path.is_file() or not metadata_path.is_file():
        return None
    if load_json(config_path) != cfg:
        return None

    meta = load_json(metadata_path)
    status = meta.get("run_status", "completed")
    if status == "integration_failed":
        return status

    needed = [
        path / "trace.npz",
        path / "segment_traces.npz",
        path / "transitions.json",
        path / "segments.json",
    ]
    if all(p.is_file() for p in needed):
        return "completed"
    return None

def cache_complete(path, cfg):
    return cache_status(path, cfg) == "completed"

def run_cached(spec, cfg, *, allow_failure=False):
    """Run or load one numerical point with failure-aware exploratory sweeps."""
    path = CACHE / cache_key(cfg)
    cached_status = cache_status(path, cfg)
    if cached_status is not None:
        suffix = " (FAILED)" if cached_status == "integration_failed" else ""
        print(
            f"cache hit{suffix}:",
            f"rtol={cfg['relative_tolerance']:.1e}",
            f"atol={cfg['absolute_tolerance']:.1e}",
            f"max_step={1000*cfg['max_step']:.3g} ms",
        )
        if cached_status == "integration_failed" and not allow_failure:
            meta = load_json(path / "metadata.json")
            raise RuntimeError(
                "Strict convergence run resolved to a cached integration failure: "
                f"{meta.get('exception_type', 'Exception')}: "
                f"{meta.get('exception_message', '')}"
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

    try:
        result = integrate_hybrid(
            system=decoded.system,
            time_span=decoded.time_span,
            initial_state=decoded.initial_state,
            initial_mode=decoded.initial_mode,
            settings=decoded.integrator_settings,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - started
        write_json(path / "config.json", cfg)
        write_json(
            path / "metadata.json",
            {
                "run_status": "integration_failed",
                "completed": False,
                "termination_reason": "exception",
                "final_time_s": None,
                "transition_count": None,
                "segment_count": None,
                "native_solver_point_count": None,
                "wall_time_s": elapsed,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        )
        print(
            "FAILED:",
            f"rtol={cfg['relative_tolerance']:.1e}",
            f"atol={cfg['absolute_tolerance']:.1e}",
            f"max_step={1000*cfg['max_step']:.3g} ms",
            f"-> {type(exc).__name__}: {exc}",
        )
        if allow_failure:
            return path
        raise

    elapsed = time.perf_counter() - started

    write_json(path / "config.json", cfg)
    save_trace(path / "trace.npz", compact_trace(result, cfg["comparison_step_s"]))
    save_segment_traces(
        path / "segment_traces.npz",
        segment_trace_payload(result, cfg["comparison_step_s"]),
    )
    write_json(path / "transitions.json", transition_rows(result))
    write_json(path / "segments.json", segment_rows(result))
    write_json(
        path / "metadata.json",
        {
            "run_status": "completed",
            "completed": result.completed,
            "termination_reason": result.termination_reason,
            "final_time_s": result.final_time,
            "transition_count": len(result.transitions),
            "segment_count": len(result.segments),
            "native_solver_point_count": sum(
                int(segment.time.size) for segment in result.segments
            ),
            "wall_time_s": elapsed,
            "exception_type": "",
            "exception_message": "",
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
    """Absolute-time comparison retained as a diagnostic only."""
    grid = reference["time_s"]
    all_errors = []
    result = {}
    for key in STATE_KEYS:
        ref = reference[key]
        cand = np.interp(grid, candidate["time_s"], candidate[key])
        error = (cand - ref) / scales[key]
        all_errors.append(error)
        result[f"raw_time_{key}_rms_normalized"] = float(
            np.sqrt(np.mean(error**2))
        )
        result[f"raw_time_{key}_max_abs_normalized"] = float(
            np.max(np.abs(error))
        )
        result[f"raw_time_{key}_final_abs_normalized"] = float(abs(error[-1]))
    stack = np.vstack(all_errors)
    result["raw_time_trajectory_rms_normalized"] = float(
        np.sqrt(np.mean(stack**2))
    )
    result["raw_time_trajectory_max_abs_normalized"] = float(
        np.max(np.abs(stack))
    )
    result["raw_time_final_state_rms_normalized"] = float(
        np.sqrt(np.mean(stack[:, -1]**2))
    )
    return result


def compare_event_aligned_segments(candidate_path, reference_path, scales):
    """Compare corresponding hybrid segments on normalized within-segment time.

    This removes the artificial O(1) pointwise error produced when two otherwise
    converged trajectories execute the same finite reset a few microseconds apart.
    Event-time error is reported independently by ``compare_cache``.
    """
    candidate = load_segment_traces(candidate_path / "segment_traces.npz")
    reference = load_segment_traces(reference_path / "segment_traces.npz")
    c_count = int(candidate["segment_count"][0])
    r_count = int(reference["segment_count"][0])
    if c_count != r_count:
        raise ValueError(
            "Event-aligned comparison requires equal segment counts; "
            f"candidate={c_count}, reference={r_count}."
        )

    integrals = {key: 0.0 for key in STATE_KEYS}
    maxima = {key: 0.0 for key in STATE_KEYS}
    total_reference_time = 0.0

    for i in range(r_count):
        c_seg = unpack_segment_trace(candidate, i)
        r_seg = unpack_segment_trace(reference, i)
        c_t = c_seg["time_s"]
        r_t = r_seg["time_s"]
        c_duration = float(c_t[-1] - c_t[0]) if c_t.size > 1 else 0.0
        r_duration = float(r_t[-1] - r_t[0]) if r_t.size > 1 else 0.0

        # Use a shared phase grid. Separate segment storage means u=0 and u=1
        # retain the correct post-/pre-reset states for this particular segment.
        n = max(int(c_t.size), int(r_t.size), 2)
        u = np.linspace(0.0, 1.0, n)
        c_phase = (
            (c_t - c_t[0]) / c_duration
            if c_duration > 0.0
            else np.zeros_like(c_t)
        )
        r_phase = (
            (r_t - r_t[0]) / r_duration
            if r_duration > 0.0
            else np.zeros_like(r_t)
        )

        for key in STATE_KEYS:
            if c_duration > 0.0 and c_t.size > 1:
                c_values = np.interp(u, c_phase, c_seg[key])
            else:
                c_values = np.full_like(u, float(c_seg[key][-1]), dtype=float)
            if r_duration > 0.0 and r_t.size > 1:
                r_values = np.interp(u, r_phase, r_seg[key])
            else:
                r_values = np.full_like(u, float(r_seg[key][-1]), dtype=float)

            error = (c_values - r_values) / scales[key]
            maxima[key] = max(maxima[key], float(np.max(np.abs(error))))
            if r_duration > 0.0:
                integrals[key] += float(np.trapezoid(error**2, u)) * r_duration

        total_reference_time += r_duration

    if total_reference_time <= 0.0:
        raise ValueError("Reference trajectory has zero total segment duration.")

    result = {}
    for key in STATE_KEYS:
        result[f"{key}_rms_normalized"] = float(
            math.sqrt(integrals[key] / total_reference_time)
        )
        result[f"{key}_max_abs_normalized"] = maxima[key]

    # Final-state error is evaluated from the final side of the final segment.
    c_final = unpack_segment_trace(candidate, c_count - 1)
    r_final = unpack_segment_trace(reference, r_count - 1)
    final_errors = []
    for key in STATE_KEYS:
        err = abs(float(c_final[key][-1] - r_final[key][-1])) / scales[key]
        result[f"{key}_final_abs_normalized"] = float(err)
        final_errors.append(err)

    result["trajectory_rms_normalized"] = float(
        math.sqrt(
            sum(integrals.values())
            / (len(STATE_KEYS) * total_reference_time)
        )
    )
    result["trajectory_max_abs_normalized"] = float(max(maxima.values()))
    result["final_state_rms_normalized"] = float(
        math.sqrt(np.mean(np.asarray(final_errors, dtype=float) ** 2))
    )
    result["comparison_method"] = "event_aligned_piecewise_linear_segment_time"
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


def mode_at_time(time_s, segments):
    for row in segments:
        if float(row["start_time_s"]) <= time_s < float(row["end_time_s"]):
            return row["mode"]
    # Exact final endpoint belongs to the final segment.
    if segments and math.isclose(
        time_s,
        float(segments[-1]["end_time_s"]),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        return segments[-1]["mode"]
    return None


def exact_regime_mismatch_fraction(candidate_segments, reference_segments):
    """Exact duration fraction spent in different hybrid modes.

    The union of all segment boundaries partitions time into intervals on which
    both mode histories are constant, so midpoint classification is exact up to
    the stored event-time precision and requires no arbitrary comparison grid.
    """
    boundaries = sorted(
        {
            float(row[field])
            for rows in (candidate_segments, reference_segments)
            for row in rows
            for field in ("start_time_s", "end_time_s")
        }
    )
    if len(boundaries) < 2:
        return 0.0
    total = float(boundaries[-1] - boundaries[0])
    if total <= 0.0:
        return 0.0
    mismatch = 0.0
    for left, right in zip(boundaries[:-1], boundaries[1:], strict=True):
        duration = float(right - left)
        if duration <= 0.0:
            continue
        midpoint = 0.5 * (left + right)
        if mode_at_time(midpoint, candidate_segments) != mode_at_time(
            midpoint, reference_segments
        ):
            mismatch += duration
    return mismatch / total

def compare_cache(path, reference_path, scales, guards):
    meta = load_json(path / "metadata.json")
    run_status = meta.get("run_status", "completed")

    if run_status == "integration_failed":
        nan = float("nan")
        metrics = {}
        for key in STATE_KEYS:
            for stem in (
                f"{key}_rms_normalized",
                f"{key}_max_abs_normalized",
                f"{key}_final_abs_normalized",
                f"raw_time_{key}_rms_normalized",
                f"raw_time_{key}_max_abs_normalized",
                f"raw_time_{key}_final_abs_normalized",
            ):
                metrics[stem] = nan
        metrics.update(
            {
                "trajectory_rms_normalized": nan,
                "trajectory_max_abs_normalized": nan,
                "final_state_rms_normalized": nan,
                "raw_time_trajectory_rms_normalized": nan,
                "raw_time_trajectory_max_abs_normalized": nan,
                "raw_time_final_state_rms_normalized": nan,
                "comparison_method": "event_aligned_piecewise_linear_segment_time",
                "transition_count": nan,
                "reference_transition_count": len(
                    load_json(reference_path / "transitions.json")
                ),
                "transition_count_match": False,
                "transition_signature_match": False,
                "maximum_event_time_error_s": nan,
                "rms_event_time_error_s": nan,
                "regime_mismatch_fraction": nan,
                "wall_time_s": float(meta["wall_time_s"]),
                "native_solver_point_count": nan,
                "run_status": "integration_failed",
                "exception_type": meta.get("exception_type", "Exception"),
                "exception_message": meta.get("exception_message", ""),
                "passes_review_guards": False,
            }
        )
        return metrics

    candidate = load_trace(path / "trace.npz")
    reference = load_trace(reference_path / "trace.npz")
    raw_metrics = compare_trace(candidate, reference, scales)

    c_trans = load_json(path / "transitions.json")
    r_trans = load_json(reference_path / "transitions.json")
    c_segments = load_json(path / "segments.json")
    r_segments = load_json(reference_path / "segments.json")

    sig_match = signature(c_trans) == signature(r_trans)
    count_match = len(c_trans) == len(r_trans)
    if sig_match:
        event_errors = [
            abs(float(c["time_s"]) - float(r["time_s"]))
            for c, r in zip(c_trans, r_trans, strict=True)
        ]
        max_event = max(event_errors, default=0.0)
        rms_event = (
            float(np.sqrt(np.mean(np.asarray(event_errors) ** 2)))
            if event_errors else 0.0
        )
    else:
        max_event = float("nan")
        rms_event = float("nan")

    mode_mismatch = exact_regime_mismatch_fraction(c_segments, r_segments)

    if sig_match and len(c_segments) == len(r_segments):
        aligned_metrics = compare_event_aligned_segments(path, reference_path, scales)
    else:
        nan = float("nan")
        aligned_metrics = {
            "trajectory_rms_normalized": nan,
            "trajectory_max_abs_normalized": nan,
            "final_state_rms_normalized": nan,
            "comparison_method": "event_aligned_unavailable_signature_mismatch",
        }
        for key in STATE_KEYS:
            aligned_metrics[f"{key}_rms_normalized"] = nan
            aligned_metrics[f"{key}_max_abs_normalized"] = nan
            aligned_metrics[f"{key}_final_abs_normalized"] = nan

    metrics = {**aligned_metrics, **raw_metrics}
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
            "run_status": "completed",
            "exception_type": "",
            "exception_message": "",
        }
    )

    metrics["passes_review_guards"] = bool(
        math.isfinite(metrics["trajectory_rms_normalized"])
        and metrics["trajectory_rms_normalized"]
        <= guards["trajectory_rms_normalized"]
        and metrics["trajectory_max_abs_normalized"]
        <= guards["trajectory_max_abs_normalized"]
        and (
            not guards["require_exact_transition_signature"] or sig_match
        )
        and math.isfinite(max_event)
        and max_event <= guards["maximum_event_time_error_s"]
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
    if row.get("run_status", "completed") != "completed":
        return 4
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

    def annotate_failures(ax):
        for iy, step in enumerate(steps):
            for ix, rtol in enumerate(rtols):
                row = lookup[(rtol, step)]
                if row.get("run_status", "completed") != "completed":
                    ax.text(ix, iy, "FAIL", ha="center", va="center", fontsize=8)

    error = np.array(
        [
            [lookup[(rtol, step)]["trajectory_rms_normalized"] for rtol in rtols]
            for step in steps
        ],
        dtype=float,
    )
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    positive = error[np.isfinite(error) & (error > 0)]
    vmin = max(float(np.min(positive)) if positive.size else 1e-12, 1e-12)
    vmax = max(float(np.max(positive)) if positive.size else 1.0, vmin * 1.01)
    im = ax.imshow(
        np.ma.masked_invalid(error),
        origin="lower",
        aspect="auto",
        norm=LogNorm(vmin=vmin, vmax=vmax),
    )
    ax.set_xticks(range(len(rtols)), [f"{x:.0e}" for x in rtols], rotation=45)
    ax.set_yticks(range(len(steps)), [f"{1000*x:g}" for x in steps])
    ax.set_xlabel("Relative tolerance")
    ax.set_ylabel("Maximum step [ms]")
    ax.set_title("Event-aligned normalized RMS trajectory error")
    fig.colorbar(im, ax=ax, label="Event-aligned normalized RMS error")
    annotate_failures(ax)
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
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    im = ax.imshow(codes, origin="lower", aspect="auto", vmin=-0.5, vmax=4.5)
    ax.set_xticks(range(len(rtols)), [f"{x:.0e}" for x in rtols], rotation=45)
    ax.set_yticks(range(len(steps)), [f"{1000*x:g}" for x in steps])
    ax.set_xlabel("Relative tolerance")
    ax.set_ylabel("Maximum step [ms]")
    ax.set_title("Hybrid sequence and event convergence")
    cb = fig.colorbar(im, ax=ax, ticks=[0, 1, 2, 3, 4])
    cb.ax.set_yticklabels(
        [
            "Sequence + events converged",
            "Same signature; event/regime drift",
            "Signature differs",
            "Transition count differs",
            "Integration/domain failure",
        ]
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
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    positive = event[np.isfinite(event) & (event > 0)]
    vmin = max(float(np.min(positive)) if positive.size else 1e-12, 1e-12)
    vmax = max(float(np.max(positive)) if positive.size else 1.0, vmin * 1.01)
    im = ax.imshow(
        np.ma.masked_invalid(event),
        origin="lower",
        aspect="auto",
        norm=LogNorm(vmin=vmin, vmax=vmax),
    )
    ax.set_xticks(range(len(rtols)), [f"{x:.0e}" for x in rtols], rotation=45)
    ax.set_yticks(range(len(steps)), [f"{1000*x:g}" for x in steps])
    ax.set_xlabel("Relative tolerance")
    ax.set_ylabel("Maximum step [ms]")
    ax.set_title("Maximum corresponding event-time error")
    fig.colorbar(im, ax=ax, label="Event-time error [s]")
    annotate_failures(ax)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "03_event_time_heatmap.png", dpi=180)
    plt.close(fig)

    regime = np.array(
        [
            [
                max(float(lookup[(rtol, step)]["regime_mismatch_fraction"]), 1e-12)
                if math.isfinite(float(lookup[(rtol, step)]["regime_mismatch_fraction"]))
                else np.nan
                for rtol in rtols
            ]
            for step in steps
        ],
        dtype=float,
    )
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    positive = regime[np.isfinite(regime) & (regime > 0)]
    vmin = max(float(np.min(positive)) if positive.size else 1e-12, 1e-12)
    vmax = max(float(np.max(positive)) if positive.size else 1.0, vmin * 1.01)
    im = ax.imshow(
        np.ma.masked_invalid(regime),
        origin="lower",
        aspect="auto",
        norm=LogNorm(vmin=vmin, vmax=vmax),
    )
    ax.set_xticks(range(len(rtols)), [f"{x:.0e}" for x in rtols], rotation=45)
    ax.set_yticks(range(len(steps)), [f"{1000*x:g}" for x in steps])
    ax.set_xlabel("Relative tolerance")
    ax.set_ylabel("Maximum step [ms]")
    ax.set_title("Exact hybrid-regime mismatch fraction")
    fig.colorbar(im, ax=ax, label="Fraction of trajectory in different mode")
    annotate_failures(ax)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "04_regime_mismatch_heatmap.png", dpi=180)
    plt.close(fig)

def plot_cost(main_rows):
    completed = [
        r for r in main_rows
        if r.get("run_status", "completed") == "completed"
        and math.isfinite(float(r["trajectory_rms_normalized"]))
    ]

    fig, ax = plt.subplots(figsize=(9.2, 5.8))
    for status, label in (
        (False, "Needs review (completed)"),
        (True, "Passes all guards"),
    ):
        group = [r for r in completed if bool(r["passes_review_guards"]) is status]
        if group:
            ax.scatter(
                [r["wall_time_s"] for r in group],
                [r["trajectory_rms_normalized"] for r in group],
                label=label,
            )
    ax.set_yscale("log")
    ax.set_xlabel("Pure hybrid-integration wall time [s]")
    ax.set_ylabel("Event-aligned normalized RMS error")
    ax.set_title("Event-aligned accuracy versus computational cost")
    ax.grid(True, which="both", alpha=0.25)
    if completed:
        ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "05_accuracy_vs_wall_time.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9.2, 5.8))
    if completed:
        ax.scatter(
            [r["native_solver_point_count"] for r in completed],
            [r["trajectory_rms_normalized"] for r in completed],
        )
    ax.set_yscale("log")
    ax.set_xlabel("Native solve_ivp points retained across hybrid segments")
    ax.set_ylabel("Event-aligned normalized RMS error")
    ax.set_title("Event-aligned accuracy versus solver-native point count")
    ax.grid(True, which="both", alpha=0.25)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "06_accuracy_vs_native_points.png", dpi=180)
    plt.close(fig)

def plot_atol(rows):
    rows = [
        r for r in rows
        if r.get("run_status", "completed") == "completed"
        and math.isfinite(float(r["trajectory_rms_normalized"]))
    ]
    rows = sorted(rows, key=lambda r: float(r["absolute_tolerance"]), reverse=True)
    if not rows:
        return
    x = [float(r["absolute_tolerance"]) for r in rows]
    fig, ax = plt.subplots(figsize=(9.2, 5.8))
    ax.plot(
        x,
        [r["trajectory_rms_normalized"] for r in rows],
        marker="o",
        label="Combined trajectory",
    )
    ax.plot(
        x,
        [r["shift_m_rms_normalized"] for r in rows],
        marker="o",
        label="Shift position",
    )
    ax.plot(
        x,
        [r["shift_speed_m_s_rms_normalized"] for r in rows],
        marker="o",
        label="Shift speed",
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.invert_xaxis()
    ax.set_xlabel("Absolute tolerance")
    ax.set_ylabel("Event-aligned normalized RMS error")
    ax.set_title("Absolute-tolerance sensitivity")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "07_absolute_tolerance_sensitivity.png", dpi=180)
    plt.close(fig)

def plot_overlays(
    reference_path,
    loose_path,
    canonical_path,
    *,
    loose_label="Coarsest successful sampled point",
):
    traces = [
        (loose_label, load_trace(loose_path / "trace.npz")),
        ("Canonical settings", load_trace(canonical_path / "trace.npz")),
        ("Tight reference", load_trace(reference_path / "trace.npz")),
    ]
    reference = traces[-1][1]
    time_s = reference["time_s"]
    specs = [
        (
            "primary_omega_rad_s",
            60 / (2 * np.pi),
            "Primary speed [rpm]",
            "08_primary_speed_overlay.png",
        ),
        (
            "secondary_omega_rad_s",
            60 / (2 * np.pi),
            "Secondary speed [rpm]",
            "09_secondary_speed_overlay.png",
        ),
        ("shift_m", 1000.0, "Shift position [mm]", "10_shift_overlay.png"),
    ]
    for key, factor, ylabel, filename in specs:
        fig, ax = plt.subplots(figsize=(9.5, 5.8))
        for label, trace in traces:
            values = np.interp(time_s, trace["time_s"], trace[key]) * factor
            ax.plot(time_s, values, label=label)
        ax.set_xlabel("Time [s]")
        ax.set_ylabel(ylabel)
        ax.set_title(f"Absolute-time solver overlay — {ylabel.split(' [')[0]}")
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


def coarsest_completed(rows):
    completed = [
        r for r in rows
        if r.get("run_status", "completed") == "completed"
    ]
    if not completed:
        return None
    return max(
        completed,
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
            path = run_cached(spec, cfg, allow_failure=True)
            main_rows.append(
                {
                    **cfg,
                    **compare_cache(path, reference_path, scales, spec["review_guards"]),
                }
            )
    write_rows(ARTIFACTS / "main_sweep.csv", main_rows)

    acfg = spec["absolute_tolerance_sweep"]
    atol_rows = []
    print("\nAbsolute-tolerance sweep")
    for atol in atol_grid(spec, args.quick):
        cfg = config(
            spec,
            rtol=acfg["relative_tolerance"],
            atol=atol,
            max_step=acfg["max_step"],
            comparison_step=acfg["comparison_step_s"],
        )
        path = run_cached(spec, cfg, allow_failure=True)
        atol_rows.append(
            {
                **cfg,
                **compare_cache(path, reference_path, scales, spec["review_guards"]),
            }
        )
    write_rows(ARTIFACTS / "absolute_tolerance_sweep.csv", atol_rows)

    failed_rows = [
        {"sweep": "main", **r}
        for r in main_rows
        if r.get("run_status") == "integration_failed"
    ] + [
        {"sweep": "absolute_tolerance", **r}
        for r in atol_rows
        if r.get("run_status") == "integration_failed"
    ]
    write_rows(ARTIFACTS / "failed_runs.csv", failed_rows)

    loose = coarsest_completed(main_rows)
    if loose is None:
        raise RuntimeError(
            "No main-grid point completed successfully; there is no trajectory "
            "available for convergence comparison."
        )
    loose_cfg = config(
        spec,
        rtol=loose["relative_tolerance"],
        atol=loose["absolute_tolerance"],
        max_step=loose["max_step"],
        comparison_step=loose["comparison_step_s"],
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
    plot_overlays(
        reference_path,
        loose_path,
        canonical_path,
        loose_label="Coarsest successful sampled point",
    )

    coarse = coarsest_passing(main_rows)
    main_failures = [
        r for r in main_rows if r.get("run_status") == "integration_failed"
    ]
    failure_classes = {}
    for row in main_failures:
        key = row.get("exception_type") or "Exception"
        failure_classes[key] = failure_classes.get(key, 0) + 1

    summary = {
        "study": spec,
        "cinder_version": cinder.__version__,
        "run_mode": "quick" if args.quick else "full",
        "continuous_comparison_method": (
            "event-aligned corresponding hybrid segments; piecewise-linear time "
            "normalization within each segment"
        ),
        "regime_mismatch_method": (
            "exact duration over union of candidate/reference hybrid boundaries"
        ),
        "state_normalization_scales": scales,
        "reference": {**ref_cfg, **load_json(reference_path / "metadata.json")},
        "canonical": {**canonical_cfg, **canonical_metrics},
        "successful_main_grid_points": len(main_rows) - len(main_failures),
        "failed_main_grid_points": len(main_failures),
        "main_grid_failure_classes": failure_classes,
        "passing_main_grid_points": sum(
            bool(r["passes_review_guards"]) for r in main_rows
        ),
        "total_main_grid_points": len(main_rows),
        "coarsest_completed_grid_point": loose,
        "coarsest_passing_grid_point": coarse,
    }
    write_json(ARTIFACTS / "summary.json", summary, allow_nan=True)

    lines = [
        "# CINDER v1.1.2 solver-convergence study",
        "",
        f"Mode: **{'quick preview' if args.quick else 'full paper-facing sweep'}**",
        "",
        "Continuous-state pass/fail metrics are event-aligned segment by segment. "
        "Raw absolute-time errors are retained in the CSV as diagnostics but are not "
        "used to penalize finite reset jumps for microsecond event-time offsets.",
        "",
        "## Canonical settings versus tight numerical reference",
        "",
        f"- event-aligned normalized trajectory RMS: `{canonical_metrics['trajectory_rms_normalized']:.6g}`",
        f"- event-aligned normalized max trajectory error: `{canonical_metrics['trajectory_max_abs_normalized']:.6g}`",
        f"- raw absolute-time normalized trajectory RMS: `{canonical_metrics['raw_time_trajectory_rms_normalized']:.6g}`",
        f"- raw absolute-time normalized max trajectory error: `{canonical_metrics['raw_time_trajectory_max_abs_normalized']:.6g}`",
        f"- transition signature match: **{canonical_metrics['transition_signature_match']}**",
        f"- maximum event-time error: `{canonical_metrics['maximum_event_time_error_s']:.6g} s`",
        f"- exact regime mismatch fraction: `{canonical_metrics['regime_mismatch_fraction']:.6g}`",
        f"- passes all review guards: **{canonical_metrics['passes_review_guards']}**",
        "",
        (
            "Main-grid integrations completed: "
            f"**{summary['successful_main_grid_points']}/{summary['total_main_grid_points']}**; "
            f"integration/domain failures: **{summary['failed_main_grid_points']}**."
        ),
        (
            "Main-grid points passing every review guard: "
            f"**{summary['passing_main_grid_points']}/{summary['total_main_grid_points']}**."
        ),
        "",
    ]
    if main_failures:
        lines += ["## Integration/domain failures", ""]
        for kind, count in sorted(failure_classes.items()):
            lines.append(f"- `{kind}`: **{count}** grid point(s)")
        lines += [
            "",
            "These cells remain explicit failed numerical configurations. See "
            "`failed_runs.csv` for exception text.",
            "",
        ]

    if coarse is not None:
        lines += [
            "## Coarsest sampled passing point",
            "",
            f"- rtol: `{coarse['relative_tolerance']:.3g}`",
            f"- atol: `{coarse['absolute_tolerance']:.3g}`",
            f"- max step: `{1000*coarse['max_step']:.3g} ms`",
            f"- event-aligned trajectory RMS: `{coarse['trajectory_rms_normalized']:.6g}`",
            "",
            "This is descriptive only; it does not silently change other frozen-study settings.",
        ]
    else:
        lines += [
            "No main-grid point passed every review guard. Inspect the event-aligned "
            "heatmaps and raw sweep before changing any numerical setting."
        ]
    lines += [
        "",
        "Wall time is machine-dependent and times only the hybrid integration call. "
        "Native solver-point count is a transparent cost proxy and is not mislabeled "
        "as SciPy function evaluations.",
    ]
    (ARTIFACTS / "summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    print(f"\nSolver convergence complete: {ARTIFACTS}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
