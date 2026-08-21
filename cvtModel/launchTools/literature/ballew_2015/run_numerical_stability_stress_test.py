"""CINDER numerical stability / performance stress test for the Ballew benchmark.

Drop this file into:
    cvtModel/launchTools/literature/ballew_2015/

Then, from cvtModel/, run for example:
    python launchTools/literature/ballew_2015/run_numerical_stability_stress_test.py

A broader paper-quality sweep:
    python launchTools/literature/ballew_2015/run_numerical_stability_stress_test.py --preset full --timing-repeats 3

Optional solver comparison:
    python launchTools/literature/ballew_2015/run_numerical_stability_stress_test.py --preset full --compare-methods

What this script measures
-------------------------
For every (max_step, rtol) point it runs the *unchanged* closed-loop Ballew CINDER
case and records:
  * trajectory drift from a tight CINDER reference;
  * wall-clock time and real-time factor;
  * solve_ivp RHS/Jacobian/LU work (nfev/njev/nlu);
  * accepted internal step count and actual internal dt statistics;
  * hybrid segment/transition counts and transition-signature agreement;
  * completion/failure.

It then creates a filled stability heat map, a speed-vs-accuracy Pareto plot,
solver-work plots, stress-trajectory overlays, an optional method comparison,
and a 2x2 summary figure intended to be much more publication-friendly than a
four-point convergence plot.

Important interpretation
------------------------
`max_step` is only an upper bound for adaptive solve_ivp methods. Therefore the
script separately records the *actual accepted internal step sizes*.  The Ballew
reference of ~1e-5 s is shown only as a literature-reported fixed-step scale; it
is not treated as a measured wall-clock benchmark.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import json
import math
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np

ROOT = Path(__file__).resolve().parent
CVT_MODEL_ROOT = ROOT.parents[2]
SRC = CVT_MODEL_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Existing benchmark plumbing. The plant/controller physics are not changed here.
from constants import PUBLISHED  # noqa: E402
from simulation import (  # noqa: E402
    build_closed_loop_simulation_setup,
    integrate_ballew_case_to,
    sample_cinder_trace,
)

# Patch the exact solve_ivp global used by integrate_hybrid so we can collect
# work counters without altering the equations or solver settings.
import cinder.execution.hybrid.hybrid as hybrid_core  # noqa: E402


BALLEW_FIXED_STEP_S = 1.0e-5  # thesis: "on the order of 10^-5 seconds"
BALLEW_FIXED_STEP_MS = BALLEW_FIXED_STEP_S * 1e3
BALLEW_DURATION_S = float(PUBLISHED.simulation_duration_s)
BALLEW_FIXED_STEP_COUNT_SCALE = BALLEW_DURATION_S / BALLEW_FIXED_STEP_S
BALLEW_RK4_STAGE_EVAL_SCALE = 4.0 * BALLEW_FIXED_STEP_COUNT_SCALE

# Current benchmark nominal settings.
NOMINAL_METHOD = "LSODA"
NOMINAL_MAX_STEP_S = 1.0e-3
NOMINAL_RTOL = 1.0e-7
NOMINAL_ATOL = 1.0e-9

# A deliberately tighter CINDER-only numerical reference. It is not Ballew.
REFERENCE_METHOD = "LSODA"
REFERENCE_MAX_STEP_S = 1.0e-4  # 0.1 ms
REFERENCE_RTOL = 1.0e-10
REFERENCE_ATOL = 1.0e-12

# Engineering labels only; all raw errors are retained regardless of these cuts.
PPM_INDISTINGUISHABLE = 1.0
PPM_STRONGLY_CONVERGED = 100.0      # 0.01 %
PPM_ENGINEERING_AGREEMENT = 1000.0  # 0.1 %


PRESETS = {
    # Small verification run before committing to the broad sweep.
    "smoke": {
        "max_step_ms": [0.10, 1.0, 100.0],
        "rtol": [1e-9, 1e-7, 1e-4],
    },
    # 8 x 9 = 72 points. Covers four orders of magnitude in allowed max step.
    "quick": {
        "max_step_ms": [0.03, 0.10, 0.30, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0],
        "rtol": [1e-10, 1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3],
    },
    # 11 x 12 = 132 points. Roughly five decades in tolerance and step scale.
    "full": {
        "max_step_ms": [0.01, 0.03, 0.10, 0.30, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0],
        "rtol": [1e-11, 3e-11, 1e-10, 3e-10, 1e-9, 3e-9, 1e-8, 3e-8, 1e-7, 1e-6, 1e-5, 1e-4],
    },
    # Deliberately abusive: intended to locate degradation/failure boundaries.
    "extreme": {
        "max_step_ms": [0.01, 0.03, 0.10, 0.30, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 5000.0],
        "rtol": [1e-11, 1e-10, 1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 3e-3, 1e-2],
    },
}

METHODS_FOR_COMPARISON = ("LSODA", "BDF", "Radau", "DOP853", "RK45")


@dataclass
class SolveIVPWork:
    calls: int = 0
    nfev: int = 0
    njev: int = 0
    nlu: int = 0
    accepted_steps: int = 0
    internal_steps_s: list[float] | None = None

    def __post_init__(self) -> None:
        if self.internal_steps_s is None:
            self.internal_steps_s = []

    def observe(self, result: Any) -> None:
        self.calls += 1
        self.nfev += int(getattr(result, "nfev", 0) or 0)
        self.njev += int(getattr(result, "njev", 0) or 0)
        self.nlu += int(getattr(result, "nlu", 0) or 0)
        t = np.asarray(getattr(result, "t", []), dtype=float)
        if t.size >= 2:
            dt = np.diff(t)
            dt = dt[np.isfinite(dt) & (dt > 0.0)]
            self.accepted_steps += int(dt.size)
            self.internal_steps_s.extend(float(x) for x in dt)

    def as_metrics(self) -> dict[str, float | int]:
        dt = np.asarray(self.internal_steps_s, dtype=float)
        out: dict[str, float | int] = {
            "solve_ivp_calls": self.calls,
            "nfev": self.nfev,
            "njev": self.njev,
            "nlu": self.nlu,
            "accepted_steps": self.accepted_steps,
        }
        if dt.size:
            out.update(
                {
                    "actual_dt_min_ms": float(np.min(dt) * 1e3),
                    "actual_dt_p05_ms": float(np.quantile(dt, 0.05) * 1e3),
                    "actual_dt_median_ms": float(np.median(dt) * 1e3),
                    "actual_dt_p95_ms": float(np.quantile(dt, 0.95) * 1e3),
                    "actual_dt_max_ms": float(np.max(dt) * 1e3),
                }
            )
        return out


@contextlib.contextmanager
def capture_solve_ivp_work() -> Iterable[SolveIVPWork]:
    """Temporarily wrap the solve_ivp used by the hybrid integrator."""
    original = hybrid_core.solve_ivp
    work = SolveIVPWork()

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        work.observe(result)
        return result

    hybrid_core.solve_ivp = wrapped
    try:
        yield work
    finally:
        hybrid_core.solve_ivp = original


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--preset", choices=tuple(PRESETS), default="quick")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results" / "numerical_stability_stress_test",
    )
    p.add_argument("--timing-repeats", type=int, default=1)
    p.add_argument("--report-step", type=float, default=5.0e-4,
                   help="Dense comparison grid in seconds (default: 0.5 ms).")
    p.add_argument("--maximum-transitions", type=int, default=5000)
    p.add_argument("--compare-methods", action="store_true")
    p.add_argument("--resume", action="store_true",
                   help="Reuse completed points from raw_results.jsonl when possible.")
    return p.parse_args()


def _rms(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.sqrt(np.mean(x * x))) if x.size else math.nan


def _maxabs(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.max(np.abs(x))) if x.size else math.nan


def _relative_rms(delta: np.ndarray, reference: np.ndarray, floor: float) -> float:
    d = np.asarray(delta, dtype=float)
    r = np.asarray(reference, dtype=float)
    mask = np.isfinite(d) & np.isfinite(r)
    if not np.any(mask):
        return math.nan
    denom = max(_rms(r[mask]), float(floor))
    return _rms(d[mask]) / denom


def _transition_signature(result: Any) -> tuple[tuple[str, tuple[str, ...], str], ...]:
    return tuple(
        (
            str(record.previous_mode),
            tuple(record.fired_event_names),
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
    return float(sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys))


def _run_once(
    *,
    method: str,
    max_step_s: float,
    rtol: float,
    atol: float,
    report_times: np.ndarray,
    maximum_transitions: int,
) -> tuple[dict[str, Any], Any | None, Any | None]:
    setup = build_closed_loop_simulation_setup(initial_error_integral_rpm_s=0.0)
    t0 = time.perf_counter()
    try:
        with capture_solve_ivp_work() as work:
            result = integrate_ballew_case_to(
                setup,
                final_time_s=BALLEW_DURATION_S,
                relative_tolerance=rtol,
                absolute_tolerance=atol,
                max_step_s=max_step_s,
                method=method,
                maximum_transitions=maximum_transitions,
            )
        wall = time.perf_counter() - t0
        completed = bool(result.completed) and abs(result.final_time - BALLEW_DURATION_S) < 5e-9
        row: dict[str, Any] = {
            "method": method,
            "max_step_ms": max_step_s * 1e3,
            "rtol": rtol,
            "atol": atol,
            "wall_time_s": wall,
            "real_time_factor": BALLEW_DURATION_S / wall if wall > 0 else math.nan,
            "completed": completed,
            "final_time_s": float(result.final_time),
            "segment_count": len(result.segments),
            "transition_count": len(result.transitions),
            "termination_reason": str(result.termination_reason),
            **work.as_metrics(),
        }
        if not completed:
            return row, setup, result
        trace = sample_cinder_trace(setup, result, report_times)
        row["transition_signature"] = _transition_signature(result)
        row["mode_occupancy"] = _mode_occupancy(trace.mode)
        return row, setup, (result, trace)
    except Exception as exc:
        wall = time.perf_counter() - t0
        return {
            "method": method,
            "max_step_ms": max_step_s * 1e3,
            "rtol": rtol,
            "atol": atol,
            "wall_time_s": wall,
            "real_time_factor": BALLEW_DURATION_S / wall if wall > 0 else math.nan,
            "completed": False,
            "final_time_s": math.nan,
            "termination_reason": f"{type(exc).__name__}: {exc}",
        }, None, None


def _time_repeats(
    *, method: str, max_step_s: float, rtol: float, atol: float,
    repeats: int, report_times: np.ndarray, maximum_transitions: int,
) -> list[float]:
    values: list[float] = []
    for _ in range(max(0, repeats - 1)):
        row, _, _ = _run_once(
            method=method,
            max_step_s=max_step_s,
            rtol=rtol,
            atol=atol,
            report_times=report_times,
            maximum_transitions=maximum_transitions,
        )
        if row.get("completed"):
            values.append(float(row["wall_time_s"]))
    return values


def _attach_reference_errors(
    row: dict[str, Any], trace: Any, reference_trace: Any,
    reference_signature: tuple[Any, ...], reference_occupancy: dict[str, float],
    shift_scale_m: float,
) -> None:
    dp = np.asarray(trace.primary_rpm - reference_trace.primary_rpm, dtype=float)
    ds = np.asarray(trace.secondary_rpm - reference_trace.secondary_rpm, dtype=float)
    dr = np.asarray(trace.speed_ratio - reference_trace.speed_ratio, dtype=float)
    dx = np.asarray(trace.shift_m - reference_trace.shift_m, dtype=float)
    db = np.asarray(trace.belt_speed_m_per_s - reference_trace.belt_speed_m_per_s, dtype=float)

    row.update({
        "primary_rms_delta_rpm": _rms(dp),
        "primary_max_delta_rpm": _maxabs(dp),
        "secondary_rms_delta_rpm": _rms(ds),
        "secondary_max_delta_rpm": _maxabs(ds),
        "ratio_rms_delta": _rms(dr),
        "ratio_max_delta": _maxabs(dr),
        "shift_rms_delta_um": _rms(dx) * 1e6,
        "shift_max_delta_um": _maxabs(dx) * 1e6,
        "belt_speed_rms_delta_m_per_s": _rms(db),
    })

    rel_primary = _relative_rms(dp, reference_trace.primary_rpm, floor=100.0)
    rel_secondary = _relative_rms(ds, reference_trace.secondary_rpm, floor=100.0)
    rel_ratio = _relative_rms(dr, reference_trace.speed_ratio, floor=0.1)
    rel_shift = _rms(dx) / max(shift_scale_m, 1e-6)
    finite = [x for x in (rel_primary, rel_secondary, rel_ratio, rel_shift) if np.isfinite(x)]
    composite = max(finite) if finite else math.nan
    row.update({
        "rel_rms_primary": rel_primary,
        "rel_rms_secondary": rel_secondary,
        "rel_rms_ratio": rel_ratio,
        "rel_rms_shift": rel_shift,
        "composite_relative_error": composite,
        "composite_error_ppm": composite * 1e6 if np.isfinite(composite) else math.nan,
        "transition_signature_matches_reference": bool(row.get("transition_signature") == reference_signature),
        "mode_occupancy_l1_vs_reference": _occupancy_l1(row.get("mode_occupancy", {}), reference_occupancy),
    })


def _classification(row: dict[str, Any]) -> str:
    if not row.get("completed"):
        return "failed"
    ppm = float(row.get("composite_error_ppm", math.inf))
    if not np.isfinite(ppm):
        return "unscored"
    if ppm <= PPM_INDISTINGUISHABLE:
        return "<=1 ppm"
    if ppm <= PPM_STRONGLY_CONVERGED:
        return "<=100 ppm"
    if ppm <= PPM_ENGINEERING_AGREEMENT:
        return "<=1000 ppm"
    return ">1000 ppm"


def _case_key(method: str, max_step_ms: float, rtol: float) -> str:
    return f"{method}|{max_step_ms:.12g}|{rtol:.12g}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, tuple):
        return [_json_safe(x) for x in value]
    if isinstance(value, list):
        return [_json_safe(x) for x in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    # Keep bulky signatures/occupancies in JSONL; CSV stays analysis-friendly.
    ignored = {"transition_signature", "mode_occupancy"}
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in ignored and key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(_json_safe(row), sort_keys=True) + "\n")


def _load_resume(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = _case_key(str(row["method"]), float(row["max_step_ms"]), float(row["rtol"]))
        out[key] = row
    return out


def _nice_log_tick(v: float) -> str:
    if v >= 1.0:
        return f"{v:g}"
    return f"{v:.2g}"


def _grid_array(rows: list[dict[str, Any]], steps: Sequence[float], rtols: Sequence[float], field: str) -> np.ndarray:
    lookup = {(_case_key(str(r["method"]), float(r["max_step_ms"]), float(r["rtol"]))): r for r in rows}
    arr = np.full((len(rtols), len(steps)), np.nan, dtype=float)
    for iy, rtol in enumerate(rtols):
        for ix, step in enumerate(steps):
            row = lookup.get(_case_key(NOMINAL_METHOD, step, rtol))
            if row and row.get("completed"):
                value = row.get(field)
                if value is not None:
                    arr[iy, ix] = float(value)
    return arr


def _plot_stability_map(output: Path, rows: list[dict[str, Any]], steps: Sequence[float], rtols: Sequence[float]) -> None:
    ppm = _grid_array(rows, steps, rtols, "composite_error_ppm")
    # Floor at 1e-3 ppm only for logarithmic rendering; raw CSV is untouched.
    display = np.where(np.isfinite(ppm), np.maximum(ppm, 1e-3), np.nan)
    valid = display[np.isfinite(display)]
    vmin = max(1e-3, float(np.min(valid))) if valid.size else 1e-3
    vmax = max(vmin * 10, float(np.max(valid))) if valid.size else 1e3

    fig, ax = plt.subplots(figsize=(12.8, 7.6))
    image = ax.imshow(
        display,
        origin="lower",
        aspect="auto",
        norm=LogNorm(vmin=vmin, vmax=vmax),
        cmap="viridis",
    )
    ax.set_xticks(range(len(steps)), [_nice_log_tick(v) for v in steps])
    ax.set_yticks(range(len(rtols)), [f"{v:.0e}" for v in rtols])
    ax.set_xlabel("CINDER max_step upper bound [ms]")
    ax.set_ylabel("Relative tolerance (atol = 0.01 × rtol)")
    ax.set_title("CINDER numerical stability envelope — trajectory drift from tight reference")

    # Mark failed cells with ×; mark current nominal benchmark point with a star.
    for iy, rtol in enumerate(rtols):
        for ix, step in enumerate(steps):
            candidates = [r for r in rows if r["method"] == NOMINAL_METHOD and math.isclose(float(r["max_step_ms"]), step) and math.isclose(float(r["rtol"]), rtol)]
            if candidates and not candidates[0].get("completed"):
                ax.text(ix, iy, "×", ha="center", va="center", fontsize=15, fontweight="bold")
    if NOMINAL_MAX_STEP_S * 1e3 in steps and NOMINAL_RTOL in rtols:
        ax.scatter([steps.index(NOMINAL_MAX_STEP_S * 1e3)], [rtols.index(NOMINAL_RTOL)], marker="*", s=220, edgecolors="white", linewidths=0.8, label="Current benchmark nominal")
        ax.legend(loc="upper right")

    cbar = fig.colorbar(image, ax=ax, pad=0.015)
    cbar.set_label("Worst normalized trajectory RMS error [ppm]")

    # Ballew's fixed step can be left of the first column in quick mode, so keep it in a caption.
    fig.text(
        0.5, 0.012,
        f"Ballew reports fixed RK4 steps on the order of {BALLEW_FIXED_STEP_MS:g} ms. "
        "CINDER max_step is an adaptive upper bound; actual accepted dt is measured separately.",
        ha="center", va="bottom", fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    fig.savefig(output / "01_stability_envelope_heatmap.png", dpi=220)
    plt.close(fig)


def _pareto_frontier(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points = [r for r in rows if r.get("completed") and np.isfinite(float(r.get("wall_time_s", math.nan))) and np.isfinite(float(r.get("composite_error_ppm", math.nan))) and float(r["composite_error_ppm"]) > 0]
    points.sort(key=lambda r: float(r["wall_time_s"]))
    frontier: list[dict[str, Any]] = []
    best_error = math.inf
    for row in points:
        err = float(row["composite_error_ppm"])
        if err < best_error:
            frontier.append(row)
            best_error = err
    return frontier


def _plot_pareto(output: Path, rows: list[dict[str, Any]]) -> None:
    valid = [r for r in rows if r.get("completed") and float(r.get("composite_error_ppm", math.nan)) > 0 and np.isfinite(float(r.get("wall_time_s", math.nan)))]
    if not valid:
        return
    x = np.asarray([r["wall_time_s"] for r in valid], dtype=float)
    y = np.asarray([max(float(r["composite_error_ppm"]), 1e-4) for r in valid], dtype=float)
    c = np.asarray([math.log10(float(r["rtol"])) for r in valid], dtype=float)
    size = np.asarray([float(r["max_step_ms"]) for r in valid], dtype=float)
    size = 28 + 52 * (np.log10(size / np.min(size) + 1.0) / np.log10(np.max(size) / np.min(size) + 1.0))

    fig, ax = plt.subplots(figsize=(10.5, 7.2))
    sc = ax.scatter(x, y, c=c, s=size, cmap="viridis", alpha=0.82)
    frontier = _pareto_frontier(valid)
    if frontier:
        ax.plot([r["wall_time_s"] for r in frontier], [max(float(r["composite_error_ppm"]), 1e-4) for r in frontier], linewidth=1.4, label="Pareto frontier")
    ax.axhline(PPM_STRONGLY_CONVERGED, linestyle="--", linewidth=1.0, label="100 ppm (0.01%)")
    ax.axhline(PPM_ENGINEERING_AGREEMENT, linestyle=":", linewidth=1.0, label="1000 ppm (0.1%)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Wall-clock time for 5 s simulation [s]")
    ax.set_ylabel("Worst normalized trajectory RMS error [ppm]")
    ax.set_title("CINDER speed–accuracy trade space")
    ax.grid(True, which="both", alpha=0.22)
    ax.legend(loc="best")
    cb = fig.colorbar(sc, ax=ax, pad=0.015)
    cb.set_label("log10(rtol)")
    fig.tight_layout()
    fig.savefig(output / "02_speed_accuracy_pareto.png", dpi=220)
    plt.close(fig)


def _selected_tolerance_rows(rows: list[dict[str, Any]]) -> list[tuple[float, list[dict[str, Any]]]]:
    available = sorted({float(r["rtol"]) for r in rows if r["method"] == NOMINAL_METHOD})
    targets = [1e-10, 1e-8, 1e-7, 1e-5, 1e-3]
    selected: list[tuple[float, list[dict[str, Any]]]] = []
    for target in targets:
        if not available:
            continue
        rtol = min(available, key=lambda x: abs(math.log10(x) - math.log10(target)))
        if any(math.isclose(rtol, x[0]) for x in selected):
            continue
        subset = [r for r in rows if r["method"] == NOMINAL_METHOD and math.isclose(float(r["rtol"]), rtol) and r.get("completed")]
        subset.sort(key=lambda r: float(r["max_step_ms"]))
        selected.append((rtol, subset))
    return selected


def _plot_solver_work(output: Path, rows: list[dict[str, Any]]) -> None:
    selected = _selected_tolerance_rows(rows)
    if not selected:
        return
    fig, axes = plt.subplots(3, 1, figsize=(10.8, 10.5), sharex=True)
    for rtol, subset in selected:
        if not subset:
            continue
        x = [r["max_step_ms"] for r in subset]
        axes[0].plot(x, [r.get("accepted_steps", math.nan) for r in subset], marker="o", label=f"rtol={rtol:.0e}")
        axes[1].plot(x, [r.get("nfev", math.nan) for r in subset], marker="o")
        axes[2].plot(x, [r.get("real_time_factor", math.nan) for r in subset], marker="o")

    axes[0].axhline(BALLEW_FIXED_STEP_COUNT_SCALE, linestyle="--", linewidth=1.1, label="Ballew fixed-step count scale (~500k)")
    axes[1].axhline(BALLEW_RK4_STAGE_EVAL_SCALE, linestyle="--", linewidth=1.1, label="Ballew RK4 stage-eval scale (~2M)")
    axes[0].set_ylabel("Accepted adaptive steps")
    axes[1].set_ylabel("RHS evaluations (nfev)")
    axes[2].set_ylabel("Simulated / wall time")
    axes[2].set_xlabel("CINDER max_step upper bound [ms]")
    for ax in axes:
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.grid(True, which="both", alpha=0.22)
    axes[0].legend(fontsize=8, ncol=2)
    axes[1].legend(fontsize=8)
    fig.suptitle("Numerical work collapses as CINDER is allowed to adapt its time step")
    fig.tight_layout()
    fig.savefig(output / "03_solver_work_vs_max_step.png", dpi=220)
    plt.close(fig)


def _choose_story_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed = [r for r in rows if r.get("completed") and np.isfinite(float(r.get("composite_error_ppm", math.nan)))]
    if not completed:
        return []
    chosen: list[dict[str, Any]] = []

    def add(row: dict[str, Any] | None) -> None:
        if row is not None and row not in chosen:
            chosen.append(row)

    # Nominal.
    nominal = min(completed, key=lambda r: abs(math.log10(float(r["rtol"]) / NOMINAL_RTOL)) + abs(math.log10(float(r["max_step_ms"]) / (NOMINAL_MAX_STEP_S * 1e3))))
    add(nominal)
    # Fastest strongly converged.
    strong = [r for r in completed if float(r["composite_error_ppm"]) <= PPM_STRONGLY_CONVERGED]
    add(min(strong, key=lambda r: float(r["wall_time_s"])) if strong else None)
    # Fastest engineering-acceptable.
    eng = [r for r in completed if float(r["composite_error_ppm"]) <= PPM_ENGINEERING_AGREEMENT]
    add(min(eng, key=lambda r: float(r["wall_time_s"])) if eng else None)
    # Largest finite error to visibly show the onset of degradation.
    add(max(completed, key=lambda r: float(r["composite_error_ppm"])))
    return chosen[:4]


def _rerun_trace(row: dict[str, Any], report_times: np.ndarray, maximum_transitions: int) -> Any | None:
    run, _, payload = _run_once(
        method=str(row["method"]),
        max_step_s=float(row["max_step_ms"]) * 1e-3,
        rtol=float(row["rtol"]),
        atol=float(row["atol"]),
        report_times=report_times,
        maximum_transitions=maximum_transitions,
    )
    if not run.get("completed") or not isinstance(payload, tuple):
        return None
    return payload[1]


def _plot_trajectory_story(output: Path, rows: list[dict[str, Any]], reference_trace: Any, report_times: np.ndarray, maximum_transitions: int) -> None:
    cases = _choose_story_cases(rows)
    if not cases:
        return
    fig, axes = plt.subplots(3, 1, figsize=(11.2, 9.2), sharex=True)
    for row in cases:
        trace = _rerun_trace(row, report_times, maximum_transitions)
        if trace is None:
            continue
        label = f"{row['max_step_ms']:g} ms, rtol={float(row['rtol']):.0e}, {float(row['composite_error_ppm']):.2g} ppm"
        axes[0].plot(report_times, trace.primary_rpm - reference_trace.primary_rpm, label=label)
        axes[1].plot(report_times, trace.speed_ratio - reference_trace.speed_ratio)
        axes[2].plot(report_times, (trace.shift_m - reference_trace.shift_m) * 1e6)
    axes[0].set_ylabel("Δ primary [rpm]")
    axes[1].set_ylabel("Δ speed ratio")
    axes[2].set_ylabel("Δ shift [µm]")
    axes[2].set_xlabel("Time [s]")
    for ax in axes:
        ax.grid(True, alpha=0.22)
        ax.axhline(0.0, linewidth=0.8)
    axes[0].legend(fontsize=8, ncol=1)
    fig.suptitle("Where numerical degradation first becomes physically visible")
    fig.tight_layout()
    fig.savefig(output / "04_trajectory_stress_overlay.png", dpi=220)
    plt.close(fig)


def _plot_actual_dt(output: Path, rows: list[dict[str, Any]]) -> None:
    valid = [r for r in rows if r.get("completed") and np.isfinite(float(r.get("actual_dt_median_ms", math.nan)))]
    if not valid:
        return
    valid.sort(key=lambda r: float(r["max_step_ms"]))
    fig, ax = plt.subplots(figsize=(10.5, 6.7))
    for rtol, subset in _selected_tolerance_rows(valid):
        if not subset:
            continue
        x = np.asarray([r["max_step_ms"] for r in subset], dtype=float)
        med = np.asarray([r["actual_dt_median_ms"] for r in subset], dtype=float)
        p95 = np.asarray([r["actual_dt_p95_ms"] for r in subset], dtype=float)
        ax.plot(x, med, marker="o", label=f"median, rtol={rtol:.0e}")
        ax.plot(x, p95, linestyle="--", linewidth=1.0)
    ax.axhline(BALLEW_FIXED_STEP_MS, linestyle=":", linewidth=1.5, label="Ballew reported fixed-step scale (~0.01 ms)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Allowed CINDER max_step [ms]")
    ax.set_ylabel("Actual accepted internal dt [ms]")
    ax.set_title("Adaptive CINDER step sizes vs the Ballew fixed-step scale")
    ax.grid(True, which="both", alpha=0.22)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(output / "05_actual_internal_step_scale.png", dpi=220)
    plt.close(fig)


def _method_comparison(args: argparse.Namespace, report_times: np.ndarray, reference_trace: Any, reference_signature: tuple[Any, ...], reference_occupancy: dict[str, float], shift_scale_m: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for method in METHODS_FOR_COMPARISON:
        print(f"method comparison: {method}", flush=True)
        row, _, payload = _run_once(
            method=method,
            max_step_s=NOMINAL_MAX_STEP_S,
            rtol=NOMINAL_RTOL,
            atol=NOMINAL_ATOL,
            report_times=report_times,
            maximum_transitions=args.maximum_transitions,
        )
        if row.get("completed") and isinstance(payload, tuple):
            _attach_reference_errors(row, payload[1], reference_trace, reference_signature, reference_occupancy, shift_scale_m)
        row["classification"] = _classification(row)
        rows.append(row)
    return rows


def _plot_method_comparison(output: Path, rows: list[dict[str, Any]]) -> None:
    valid = [r for r in rows if r.get("completed") and np.isfinite(float(r.get("composite_error_ppm", math.nan)))]
    if not valid:
        return
    fig, ax = plt.subplots(figsize=(9.0, 6.6))
    for row in valid:
        ax.scatter(float(row["wall_time_s"]), max(float(row["composite_error_ppm"]), 1e-4), s=90)
        ax.annotate(str(row["method"]), (float(row["wall_time_s"]), max(float(row["composite_error_ppm"]), 1e-4)), xytext=(5, 5), textcoords="offset points")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Wall-clock time [s]")
    ax.set_ylabel("Trajectory error [ppm]")
    ax.set_title("Same CINDER equations, different solve_ivp methods")
    ax.grid(True, which="both", alpha=0.22)
    fig.tight_layout()
    fig.savefig(output / "06_method_comparison.png", dpi=220)
    plt.close(fig)


def _plot_hero(output: Path, rows: list[dict[str, Any]], steps: Sequence[float], rtols: Sequence[float]) -> None:
    """One dense 2x2 figure for papers/slides."""
    ppm = _grid_array(rows, steps, rtols, "composite_error_ppm")
    display = np.where(np.isfinite(ppm), np.maximum(ppm, 1e-3), np.nan)
    valid_ppm = display[np.isfinite(display)]
    if not valid_ppm.size:
        return
    fig, axes = plt.subplots(2, 2, figsize=(14.0, 10.0))

    ax = axes[0, 0]
    im = ax.imshow(display, origin="lower", aspect="auto", norm=LogNorm(vmin=max(1e-3, float(np.min(valid_ppm))), vmax=max(float(np.max(valid_ppm)), 1.0)), cmap="viridis")
    ax.set_xticks(range(len(steps)), [_nice_log_tick(v) for v in steps], rotation=45, ha="right")
    ax.set_yticks(range(len(rtols)), [f"{v:.0e}" for v in rtols])
    ax.set_title("A. Stability envelope")
    ax.set_xlabel("max_step [ms]")
    ax.set_ylabel("rtol")
    fig.colorbar(im, ax=ax, label="trajectory drift [ppm]")

    ax = axes[0, 1]
    valid = [r for r in rows if r.get("completed") and float(r.get("composite_error_ppm", math.nan)) > 0 and np.isfinite(float(r.get("wall_time_s", math.nan)))]
    if valid:
        x = [r["wall_time_s"] for r in valid]
        y = [max(float(r["composite_error_ppm"]), 1e-4) for r in valid]
        ax.scatter(x, y, s=32, alpha=0.75)
        frontier = _pareto_frontier(valid)
        if frontier:
            ax.plot([r["wall_time_s"] for r in frontier], [max(float(r["composite_error_ppm"]), 1e-4) for r in frontier], linewidth=1.4)
        ax.axhline(PPM_STRONGLY_CONVERGED, linestyle="--", linewidth=1.0)
        ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_title("B. Speed–accuracy frontier")
    ax.set_xlabel("wall time [s]")
    ax.set_ylabel("trajectory drift [ppm]")
    ax.grid(True, which="both", alpha=0.2)

    ax = axes[1, 0]
    for rtol, subset in _selected_tolerance_rows(rows):
        if subset:
            ax.plot([r["max_step_ms"] for r in subset], [r.get("nfev", math.nan) for r in subset], marker="o", label=f"{rtol:.0e}")
    ax.axhline(BALLEW_RK4_STAGE_EVAL_SCALE, linestyle="--", linewidth=1.1, label="Ballew RK4 stage scale")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_title("C. RHS work")
    ax.set_xlabel("max_step [ms]")
    ax.set_ylabel("nfev")
    ax.grid(True, which="both", alpha=0.2)
    ax.legend(fontsize=7, ncol=2)

    ax = axes[1, 1]
    for rtol, subset in _selected_tolerance_rows(rows):
        if subset:
            ax.plot([r["max_step_ms"] for r in subset], [r.get("actual_dt_p95_ms", math.nan) for r in subset], marker="o", label=f"{rtol:.0e}")
    ax.axhline(BALLEW_FIXED_STEP_MS, linestyle="--", linewidth=1.1, label="Ballew ~0.01 ms")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_title("D. Actual accepted step scale (95th percentile)")
    ax.set_xlabel("allowed max_step [ms]")
    ax.set_ylabel("actual dt p95 [ms]")
    ax.grid(True, which="both", alpha=0.2)
    ax.legend(fontsize=7, ncol=2)

    fig.suptitle("CINDER numerical stability and computational-efficiency envelope", fontsize=15)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output / "00_numerical_stability_story.png", dpi=240)
    plt.close(fig)


def _best_rows(rows: list[dict[str, Any]], ppm_limit: float) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("completed") and np.isfinite(float(r.get("composite_error_ppm", math.nan))) and float(r["composite_error_ppm"]) <= ppm_limit]


def _write_summary(output: Path, rows: list[dict[str, Any]], method_rows: list[dict[str, Any]]) -> None:
    completed = [r for r in rows if r.get("completed")]
    failed = [r for r in rows if not r.get("completed")]
    strong = _best_rows(rows, PPM_STRONGLY_CONVERGED)
    eng = _best_rows(rows, PPM_ENGINEERING_AGREEMENT)
    fastest_strong = min(strong, key=lambda r: float(r["wall_time_s"])) if strong else None
    fastest_eng = min(eng, key=lambda r: float(r["wall_time_s"])) if eng else None
    largest_step_strong = max(strong, key=lambda r: float(r["max_step_ms"])) if strong else None

    nominal_candidates = [r for r in completed if math.isclose(float(r["max_step_ms"]), NOMINAL_MAX_STEP_S * 1e3) and math.isclose(float(r["rtol"]), NOMINAL_RTOL)]
    nominal = nominal_candidates[0] if nominal_candidates else None

    lines = [
        "# CINDER numerical stability stress test",
        "",
        "## What this experiment answers",
        "",
        "This sweep separates four different questions that should not be conflated:",
        "",
        "1. **Accuracy:** how far does a run move from a tight CINDER numerical reference?",
        "2. **Hybrid robustness:** does it complete, and does the transition topology remain the same?",
        "3. **Numerical work:** how many accepted adaptive steps / RHS evaluations / LU factorizations are required?",
        "4. **Wall-clock usefulness:** how quickly does the five-second physical trajectory run on this machine?",
        "",
        "`max_step` is an upper bound, not the actual CINDER time step. The actual accepted step statistics are therefore reported separately.",
        "",
        "## Literature reference scale",
        "",
        f"Ballew reports fixed RK4 time steps on the order of **{BALLEW_FIXED_STEP_S:.0e} s = {BALLEW_FIXED_STEP_MS:g} ms** for numerical stability.",
        f"Across a {BALLEW_DURATION_S:g} s run, that corresponds to an order-of-magnitude fixed-step count of **{BALLEW_FIXED_STEP_COUNT_SCALE:,.0f} steps**.",
        f"A straightforward four-stage RK4 implementation is therefore on the order of **{BALLEW_RK4_STAGE_EVAL_SCALE:,.0f} RK stage evaluations**, before considering Ballew's per-step belt geometry/search work. This is a work-scale reference, not a measured runtime comparison.",
        "",
        "## Sweep result",
        "",
        f"- Completed cases: **{len(completed)} / {len(rows)}**",
        f"- Failed/incomplete cases: **{len(failed)}**",
    ]

    def describe(prefix: str, row: dict[str, Any] | None) -> None:
        if row is None:
            lines.append(f"- {prefix}: none")
            return
        lines.append(
            f"- {prefix}: max_step={float(row['max_step_ms']):g} ms, rtol={float(row['rtol']):.0e}, "
            f"error={float(row.get('composite_error_ppm', math.nan)):.4g} ppm, "
            f"wall={float(row['wall_time_s']):.4g} s, real-time factor={float(row['real_time_factor']):.3g}×, "
            f"nfev={int(row.get('nfev', 0)):,}, accepted steps={int(row.get('accepted_steps', 0)):,}."
        )

    describe("Fastest <=100 ppm case", fastest_strong)
    describe("Fastest <=1000 ppm case", fastest_eng)
    describe("Largest allowed max_step still <=100 ppm", largest_step_strong)
    describe("Current benchmark nominal point", nominal)

    if largest_step_strong is not None:
        ratio = float(largest_step_strong["max_step_ms"]) / BALLEW_FIXED_STEP_MS
        lines.extend([
            "",
            "## Step-scale comparison",
            "",
            f"The largest **allowed** CINDER max_step that remains within 100 ppm in this sweep is {float(largest_step_strong['max_step_ms']):g} ms, or **{ratio:,.0f}× ({math.log10(ratio):.2f} decades)** above Ballew's reported ~0.01 ms fixed-step scale.",
        ])
        actual = float(largest_step_strong.get("actual_dt_p95_ms", math.nan))
        if np.isfinite(actual):
            actual_ratio = actual / BALLEW_FIXED_STEP_MS
            lines.append(
                f"More importantly, that case's 95th-percentile **actual accepted adaptive step** is {actual:.4g} ms, **{actual_ratio:,.0f}×** the Ballew fixed-step scale. This is the cleaner numerical-efficiency comparison because it does not confuse max_step with the steps LSODA actually accepted."
            )

    if fastest_strong is not None and nominal is not None:
        speed = float(nominal["wall_time_s"]) / float(fastest_strong["wall_time_s"])
        lines.extend([
            "",
            "## Runtime comparison within CINDER",
            "",
            f"On this machine, the fastest <=100 ppm case is **{speed:.2f}×** faster than the current benchmark nominal setting. This is an apples-to-apples CINDER-vs-CINDER timing comparison.",
        ])

    if fastest_strong is not None and int(fastest_strong.get("accepted_steps", 0)) > 0:
        compression = BALLEW_FIXED_STEP_COUNT_SCALE / int(fastest_strong["accepted_steps"])
        lines.append(
            f"Its accepted-step count is about **{compression:,.0f}× smaller** than the ~500,000-step fixed-step scale implied by Ballew's reported 10 µs step over five seconds. This is a step-count comparison, not a wall-clock speedup claim."
        )

    if method_rows:
        lines.extend(["", "## Solver-method spot check", ""])
        for row in method_rows:
            if row.get("completed"):
                lines.append(
                    f"- {row['method']}: wall={float(row['wall_time_s']):.4g} s, "
                    f"error={float(row.get('composite_error_ppm', math.nan)):.4g} ppm, "
                    f"nfev={int(row.get('nfev', 0)):,}, nlu={int(row.get('nlu', 0)):,}."
                )
            else:
                lines.append(f"- {row['method']}: did not complete ({row.get('termination_reason')}).")

    lines.extend([
        "",
        "## Claims this supports",
        "",
        "- CINDER's macroscopic closed-loop trajectory can be mapped over several decades of solver controls instead of being demonstrated at only four already-converged points.",
        "- The plot can show where numerical error actually begins to grow and where hybrid integration eventually fails, if that boundary is reached by the chosen preset.",
        "- Actual adaptive step sizes, accepted-step counts, nfev/njev/nlu, and wall time can be reported directly.",
        "- Ballew's ~10 µs fixed-step requirement can be used as a published numerical-work scale.",
        "",
        "## Claims this does **not** support by itself",
        "",
        "- A direct wall-clock speedup of CINDER over Ballew. That requires running both implementations on controlled hardware.",
        "- That a larger CINDER `max_step` is itself an actual larger integration step. Use the recorded internal dt distribution for that statement.",
        "- Physical validation of CINDER merely because the numerical solution is converged.",
        "",
        "## Generated figures",
        "",
        "- `00_numerical_stability_story.png` — four-panel hero figure.",
        "- `01_stability_envelope_heatmap.png` — filled accuracy/failure map.",
        "- `02_speed_accuracy_pareto.png` — wall-time vs trajectory-error frontier.",
        "- `03_solver_work_vs_max_step.png` — accepted steps, nfev, and real-time factor.",
        "- `04_trajectory_stress_overlay.png` — where coarsening becomes visible in the physical trajectory.",
        "- `05_actual_internal_step_scale.png` — actual adaptive step sizes versus Ballew's fixed-step scale.",
        "- `06_method_comparison.png` — optional solver-method comparison.",
    ])
    (output / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.timing_repeats < 1:
        raise ValueError("--timing-repeats must be >= 1")
    if args.report_step <= 0:
        raise ValueError("--report-step must be > 0")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    raw_jsonl = output / "raw_results.jsonl"
    resume = _load_resume(raw_jsonl) if args.resume else {}

    report_times = np.arange(0.0, BALLEW_DURATION_S + 0.5 * args.report_step, args.report_step, dtype=float)
    if report_times[-1] < BALLEW_DURATION_S:
        report_times = np.append(report_times, BALLEW_DURATION_S)
    else:
        report_times[-1] = BALLEW_DURATION_S

    print("Running tight CINDER reference...", flush=True)
    ref_row, ref_setup, ref_payload = _run_once(
        method=REFERENCE_METHOD,
        max_step_s=REFERENCE_MAX_STEP_S,
        rtol=REFERENCE_RTOL,
        atol=REFERENCE_ATOL,
        report_times=report_times,
        maximum_transitions=args.maximum_transitions,
    )
    if not ref_row.get("completed") or not isinstance(ref_payload, tuple) or ref_setup is None:
        raise RuntimeError(f"Tight reference failed: {ref_row.get('termination_reason')}")
    ref_result, reference_trace = ref_payload
    reference_signature = _transition_signature(ref_result)
    reference_occupancy = _mode_occupancy(reference_trace.mode)
    shift_scale_m = float(ref_setup.system.cvt.model.geometry.spec.max_shift)

    preset = PRESETS[args.preset]
    steps = list(map(float, preset["max_step_ms"]))
    rtols = list(map(float, preset["rtol"]))
    rows: list[dict[str, Any]] = []
    total = len(steps) * len(rtols)
    index = 0

    for rtol in rtols:
        atol = rtol * 1e-2
        for step_ms in steps:
            index += 1
            key = _case_key(NOMINAL_METHOD, step_ms, rtol)
            if key in resume:
                row = dict(resume[key])
                rows.append(row)
                print(f"[{index:3d}/{total}] resume max_step={step_ms:g} ms rtol={rtol:.0e}", flush=True)
                continue
            print(f"[{index:3d}/{total}] max_step={step_ms:g} ms rtol={rtol:.0e}", flush=True)
            row, _, payload = _run_once(
                method=NOMINAL_METHOD,
                max_step_s=step_ms * 1e-3,
                rtol=rtol,
                atol=atol,
                report_times=report_times,
                maximum_transitions=args.maximum_transitions,
            )
            if row.get("completed") and isinstance(payload, tuple):
                _attach_reference_errors(
                    row, payload[1], reference_trace,
                    reference_signature, reference_occupancy, shift_scale_m,
                )
                extra_times = _time_repeats(
                    method=NOMINAL_METHOD,
                    max_step_s=step_ms * 1e-3,
                    rtol=rtol,
                    atol=atol,
                    repeats=args.timing_repeats,
                    report_times=report_times,
                    maximum_transitions=args.maximum_transitions,
                )
                timing = [float(row["wall_time_s"]), *extra_times]
                row["timing_samples"] = len(timing)
                row["wall_time_median_s"] = float(statistics.median(timing))
                row["wall_time_min_s"] = float(min(timing))
                row["wall_time_max_s"] = float(max(timing))
                row["wall_time_s"] = row["wall_time_median_s"]
                row["real_time_factor"] = BALLEW_DURATION_S / row["wall_time_s"]
            row["classification"] = _classification(row)
            rows.append(row)
            _write_jsonl(raw_jsonl, rows)

    _write_csv(output / "stress_sweep.csv", rows)
    _write_jsonl(raw_jsonl, rows)

    method_rows: list[dict[str, Any]] = []
    if args.compare_methods:
        method_rows = _method_comparison(
            args, report_times, reference_trace, reference_signature,
            reference_occupancy, shift_scale_m,
        )
        _write_csv(output / "method_comparison.csv", method_rows)
        _write_jsonl(output / "method_comparison.jsonl", method_rows)

    # Reference metadata is written separately so it is never mistaken for one
    # of the grid points.
    reference_metadata = {
        **{k: v for k, v in ref_row.items() if k not in {"transition_signature", "mode_occupancy"}},
        "reference_method": REFERENCE_METHOD,
        "reference_max_step_ms": REFERENCE_MAX_STEP_S * 1e3,
        "reference_rtol": REFERENCE_RTOL,
        "reference_atol": REFERENCE_ATOL,
        "Ballew_reported_fixed_step_s": BALLEW_FIXED_STEP_S,
        "Ballew_fixed_step_count_scale_for_5s": BALLEW_FIXED_STEP_COUNT_SCALE,
        "Ballew_RK4_stage_evaluation_scale_for_5s": BALLEW_RK4_STAGE_EVAL_SCALE,
    }
    (output / "reference_and_literature_scales.json").write_text(
        json.dumps(_json_safe(reference_metadata), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("Generating figures...", flush=True)
    _plot_stability_map(output, rows, steps, rtols)
    _plot_pareto(output, rows)
    _plot_solver_work(output, rows)
    _plot_trajectory_story(output, rows, reference_trace, report_times, args.maximum_transitions)
    _plot_actual_dt(output, rows)
    if method_rows:
        _plot_method_comparison(output, method_rows)
    _plot_hero(output, rows, steps, rtols)
    _write_summary(output, rows, method_rows)

    print(f"Done. Outputs: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
