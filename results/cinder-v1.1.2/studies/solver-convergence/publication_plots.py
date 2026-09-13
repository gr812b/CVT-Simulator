#!/usr/bin/env python3
r"""Generate polished paper-facing figures from the frozen solver-convergence artifacts.

This script DOES NOT run CINDER and DOES NOT change the numerical dataset.
It reads the existing formal artifacts and writes publication-oriented figures to:

    studies/solver-convergence/artifacts/publication/

Run from results/cinder-v1.1.2:

    python .\studies\solver-convergence\publication_plots.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.patches import Rectangle
import numpy as np

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
OUT = ARTIFACTS / "publication"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--artifacts",
        type=Path,
        default=ARTIFACTS,
        help="Formal solver-convergence artifact directory.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: <artifacts>/publication).",
    )
    return p.parse_args()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key, value in list(row.items()):
            if value in ("", None):
                continue
            if value == "True":
                row[key] = True
            elif value == "False":
                row[key] = False
            else:
                try:
                    row[key] = float(value)
                except (TypeError, ValueError):
                    pass
    return rows


def finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def sorted_axes(rows):
    rtols = sorted({float(r["relative_tolerance"]) for r in rows}, reverse=True)
    steps = sorted({float(r["max_step"]) for r in rows})
    return rtols, steps


def lookup_rows(rows):
    return {
        (float(r["relative_tolerance"]), float(r["max_step"])): r
        for r in rows
    }


def robust_plateau_threshold(rows, rtols, steps):
    lookup = lookup_rows(rows)
    # Require the entire column to complete and pass the existing diagnostic guards.
    # Then require every tighter sampled column to do the same. This rejects isolated
    # non-monotonic pass/fail cells and identifies a contiguous robust region.
    column_ok = {}
    for rtol in rtols:
        vals = [lookup[(rtol, step)] for step in steps]
        column_ok[rtol] = all(
            r.get("run_status", "completed") == "completed"
            and bool(r.get("passes_review_guards", False))
            for r in vals
        )
    candidates = []
    for i, rtol in enumerate(rtols):
        tighter = rtols[i:]
        if all(column_ok[x] for x in tighter):
            candidates.append(rtol)
    return max(candidates) if candidates else None


def canonical_indices(rtols, steps, canonical):
    cr = float(canonical["relative_tolerance"])
    cs = float(canonical["max_step"])
    ix = min(range(len(rtols)), key=lambda i: abs(math.log(rtols[i]) - math.log(cr)))
    iy = min(range(len(steps)), key=lambda i: abs(math.log(steps[i]) - math.log(cs)))
    return ix, iy


def add_canonical_marker(ax, rtols, steps, canonical):
    ix, iy = canonical_indices(rtols, steps, canonical)
    ax.scatter([ix], [iy], marker="*", s=190, linewidths=1.2, zorder=8)
    ax.annotate(
        "canonical",
        (ix, iy),
        xytext=(8, 8),
        textcoords="offset points",
        fontsize=8,
        zorder=9,
    )


def add_plateau_box(ax, rtols, steps, threshold):
    if threshold is None:
        return
    indices = [i for i, x in enumerate(rtols) if x <= threshold]
    if not indices:
        return
    left = min(indices) - 0.5
    right = max(indices) + 0.5
    rect = Rectangle(
        (left, -0.5),
        right - left,
        len(steps),
        fill=False,
        linewidth=2.0,
        linestyle="--",
        zorder=7,
    )
    ax.add_patch(rect)
    ax.text(
        left + 0.12,
        len(steps) - 0.72,
        f"robust sampled plateau\n$rtol \\leq {threshold:.0e}$",
        fontsize=8,
        va="top",
        zorder=8,
    )


def annotate_failures(ax, rtols, steps, lookup):
    for iy, step in enumerate(steps):
        for ix, rtol in enumerate(rtols):
            row = lookup[(rtol, step)]
            if row.get("run_status", "completed") != "completed":
                ax.text(ix, iy, "FAIL", ha="center", va="center", fontsize=8, zorder=10)


def matrix(rows, rtols, steps, key, floor=None):
    lookup = lookup_rows(rows)
    out = np.full((len(steps), len(rtols)), np.nan, dtype=float)
    for iy, step in enumerate(steps):
        for ix, rtol in enumerate(rtols):
            value = lookup[(rtol, step)].get(key, float("nan"))
            if finite(value):
                val = float(value)
                if floor is not None:
                    val = max(val, floor)
                out[iy, ix] = val
    return out


def heatmap(
    rows,
    rtols,
    steps,
    key,
    title,
    cbar_label,
    filename,
    canonical,
    plateau,
    out_dir,
    *,
    contour=True,
    floor=1e-12,
):
    lookup = lookup_rows(rows)
    z = matrix(rows, rtols, steps, key, floor=floor)
    valid = z[np.isfinite(z) & (z > 0)]
    vmin = max(float(np.min(valid)) if valid.size else floor, floor)
    vmax = max(float(np.max(valid)) if valid.size else 1.0, vmin * 1.01)

    fig, ax = plt.subplots(figsize=(10.8, 6.7))
    im = ax.imshow(
        np.ma.masked_invalid(z),
        origin="lower",
        aspect="auto",
        norm=LogNorm(vmin=vmin, vmax=vmax),
    )

    if contour and np.count_nonzero(np.isfinite(z)) >= 8:
        logz = np.where(np.isfinite(z) & (z > 0), np.log10(z), np.nan)
        finite_log = logz[np.isfinite(logz)]
        if finite_log.size and float(np.ptp(finite_log)) > 0.35:
            levels = np.linspace(float(np.min(finite_log)), float(np.max(finite_log)), 7)
            X, Y = np.meshgrid(np.arange(len(rtols)), np.arange(len(steps)))
            ax.contour(X, Y, logz, levels=levels, linewidths=0.75, alpha=0.65)

    ax.set_xticks(range(len(rtols)), [f"{x:.0e}" for x in rtols], rotation=45)
    ax.set_yticks(range(len(steps)), [f"{1000*x:g}" for x in steps])
    ax.set_xlabel("Relative tolerance")
    ax.set_ylabel("Maximum step [ms]")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, label=cbar_label)
    annotate_failures(ax, rtols, steps, lookup)
    add_plateau_box(ax, rtols, steps, plateau)
    add_canonical_marker(ax, rtols, steps, canonical)
    fig.tight_layout()
    fig.savefig(out_dir / filename, dpi=220)
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
    if (
        math.isfinite(event)
        and event <= float(guards["maximum_event_time_error_s"])
        and math.isfinite(regime)
        and regime <= float(guards["regime_mismatch_fraction"])
    ):
        return 0
    return 1


def plot_hybrid(rows, rtols, steps, guards, canonical, plateau, out_dir):
    lookup = lookup_rows(rows)
    codes = np.array(
        [[hybrid_code(lookup[(rtol, step)], guards) for rtol in rtols] for step in steps],
        dtype=float,
    )
    fig, ax = plt.subplots(figsize=(10.8, 6.7))
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
    add_plateau_box(ax, rtols, steps, plateau)
    add_canonical_marker(ax, rtols, steps, canonical)
    fig.tight_layout()
    fig.savefig(out_dir / "04_hybrid_stability_map.png", dpi=220)
    plt.close(fig)


def canonical_row(rows, canonical):
    cr = float(canonical["relative_tolerance"])
    ca = float(canonical["absolute_tolerance"])
    cs = float(canonical["max_step"])
    return min(
        rows,
        key=lambda r: (
            abs(math.log(float(r["relative_tolerance"])) - math.log(cr))
            + abs(math.log(float(r["absolute_tolerance"])) - math.log(ca))
            + abs(math.log(float(r["max_step"])) - math.log(cs))
        ),
    )


def plot_cost_dashboard(rows, canonical, out_dir):
    completed = [
        r for r in rows
        if r.get("run_status", "completed") == "completed"
        and finite(r.get("wall_time_s"))
    ]
    can = canonical_row(completed, canonical)
    metrics = [
        ("trajectory_rms_normalized", "Event-aligned trajectory RMS", "Normalized RMS error"),
        ("maximum_event_time_error_s", "Maximum event-time error", "Event-time error [s]"),
        ("regime_mismatch_fraction", "Exact regime-history mismatch", "Fraction of trajectory"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.2))
    for ax, (key, title, ylabel) in zip(axes, metrics, strict=True):
        subset = [r for r in completed if finite(r.get(key)) and float(r[key]) > 0]
        ax.scatter(
            [float(r["wall_time_s"]) for r in subset],
            [float(r[key]) for r in subset],
            s=28,
            alpha=0.78,
        )
        if finite(can.get(key)) and float(can[key]) > 0:
            ax.scatter(
                [float(can["wall_time_s"])],
                [float(can[key])],
                marker="*",
                s=220,
                linewidths=1.2,
                zorder=8,
                label="Canonical",
            )
            ax.legend()
        ax.set_yscale("log")
        ax.set_xlabel("Pure hybrid-integration wall time [s]")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, which="both", alpha=0.25)
    fig.suptitle("Numerical accuracy versus computational cost")
    fig.tight_layout()
    fig.savefig(out_dir / "05_cost_vs_convergence_dashboard.png", dpi=220)
    plt.close(fig)


def plot_atol(rows, canonical, out_dir):
    completed = [
        r for r in rows
        if r.get("run_status", "completed") == "completed"
        and finite(r.get("trajectory_rms_normalized"))
    ]
    completed.sort(key=lambda r: float(r["absolute_tolerance"]), reverse=True)
    if not completed:
        return
    x = [float(r["absolute_tolerance"]) for r in completed]
    fig, ax = plt.subplots(figsize=(9.6, 5.8))
    ax.plot(x, [float(r["trajectory_rms_normalized"]) for r in completed], marker="o", label="Combined trajectory")
    ax.plot(x, [float(r["shift_m_rms_normalized"]) for r in completed], marker="o", label="Shift position")
    ax.plot(x, [float(r["shift_speed_m_s_rms_normalized"]) for r in completed], marker="o", label="Shift speed")
    ca = float(canonical["absolute_tolerance"])
    ax.axvline(ca, linestyle="--", linewidth=1.2, label=f"Canonical atol = {ca:.0e}")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.invert_xaxis()
    ax.set_xlabel("Absolute tolerance")
    ax.set_ylabel("Event-aligned normalized RMS error")
    ax.set_title("Absolute-tolerance sensitivity")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "06_absolute_tolerance_sensitivity.png", dpi=220)
    plt.close(fig)


def build_summary(rows, atol_rows, summary, plateau, out_dir):
    canonical = summary["study"]["canonical"]
    can = canonical_row(rows, canonical)
    completed = [r for r in rows if r.get("run_status", "completed") == "completed"]
    exact = [r for r in completed if bool(r.get("transition_signature_match", False))]
    failures = [r for r in rows if r.get("run_status", "completed") != "completed"]

    lines = [
        "# Solver-convergence freeze summary",
        "",
        "This file is generated from the frozen formal numerical sweep. The publication",
        "figures do not alter or rerun the underlying CINDER integrations.",
        "",
        "## Formal sweep",
        "",
        f"- completed integrations: **{len(completed)}/{len(rows)}**",
        f"- exact reference transition signature among completed runs: **{len(exact)}/{len(completed)}**",
        f"- integration/domain failures: **{len(failures)}**",
    ]
    if plateau is not None:
        lines.append(
            f"- contiguous sampled plateau across every tested max-step value: **rtol <= {plateau:.0e}**"
        )
    lines += [
        "",
        "## Canonical point",
        "",
        f"- rtol: `{float(can['relative_tolerance']):.3g}`",
        f"- atol: `{float(can['absolute_tolerance']):.3g}`",
        f"- max step: `{1000*float(can['max_step']):.3g} ms`",
        f"- event-aligned normalized trajectory RMS: `{float(can['trajectory_rms_normalized']):.6g}`",
        f"- maximum normalized trajectory error: `{float(can['trajectory_max_abs_normalized']):.6g}`",
        f"- maximum event-time error: `{float(can['maximum_event_time_error_s']):.6g} s`",
        f"- exact regime mismatch fraction: `{float(can['regime_mismatch_fraction']):.6g}`",
        f"- exact transition signature match: **{bool(can['transition_signature_match'])}**",
        "",
        "## Interpretation",
        "",
        "The review guards are diagnostics, not a mathematically sharp convergence boundary.",
        "The robust conclusion is the existence of a contiguous region in which the full",
        "hybrid sequence is stable and continuous/event errors are already small, with the",
        "canonical settings comfortably inside that region. Isolated non-monotonic pointwise",
        "max-error cells are retained transparently rather than used to redefine the plateau.",
        "",
        "The separate overnight dense explorer is intentionally exploratory and does not",
        "replace or mutate this frozen formal sweep.",
    ]
    (out_dir / "FREEZE_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    args = parse_args()
    artifacts = args.artifacts.resolve()
    out_dir = (args.out or (artifacts / "publication")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(artifacts / "main_sweep.csv")
    atol_rows = load_rows(artifacts / "absolute_tolerance_sweep.csv")
    summary = load_json(artifacts / "summary.json")
    canonical = summary["study"]["canonical"]
    guards = summary["study"]["review_guards"]
    rtols, steps = sorted_axes(rows)
    plateau = robust_plateau_threshold(rows, rtols, steps)

    heatmap(
        rows, rtols, steps,
        "trajectory_rms_normalized",
        "Event-aligned normalized RMS trajectory error",
        "Normalized RMS error",
        "01_accuracy_heatmap.png",
        canonical, plateau, out_dir,
    )
    heatmap(
        rows, rtols, steps,
        "maximum_event_time_error_s",
        "Maximum corresponding event-time error",
        "Event-time error [s]",
        "02_event_time_heatmap.png",
        canonical, plateau, out_dir,
    )
    heatmap(
        rows, rtols, steps,
        "regime_mismatch_fraction",
        "Exact hybrid-regime mismatch fraction",
        "Fraction of trajectory in different mode",
        "03_regime_mismatch_heatmap.png",
        canonical, plateau, out_dir,
    )
    plot_hybrid(rows, rtols, steps, guards, canonical, plateau, out_dir)
    plot_cost_dashboard(rows, canonical, out_dir)
    plot_atol(atol_rows, canonical, out_dir)
    build_summary(rows, atol_rows, summary, plateau, out_dir)

    print(f"Publication figures written to: {out_dir}")
    if plateau is not None:
        print(f"Robust sampled plateau: rtol <= {plateau:.0e} across all tested max steps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
