"""Animate a contact-transition clip for a flat-launch-into-hill scenario.

This uses the vehicle/road boundary so the run can naturally upshift and then react to a hill.
The clip is sampled around the first engaged contact-regime transition after the disturbance.
"""
from __future__ import annotations

import argparse
import csv
import copy
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.patches import Rectangle
import numpy as np
from PIL import Image

import run as cc_run
from cinder.execution.hybrid.cvt_regime import CVTEngagementState
from cinder.model.cvt.contact import EngagedContactMode

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts" / "hill-transition-animation"

_WORKER_REF = None
_WORKER_SAMPLES = None


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--domain", choices=("physical", "expanded", "broad"), default="physical")
    p.add_argument("--resolution", type=int, default=None, help="Grid points per axis. Defaults: physical=241, expanded=641, broad=501.")
    p.add_argument("--plot-limit", type=float, default=None)
    p.add_argument("--frames", type=int, default=36)
    p.add_argument("--fps", type=float, default=5.0)
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--grade-start-distance-m", type=float, default=15.0)
    p.add_argument("--grade-angle-deg", type=float, default=20.0)
    p.add_argument("--time-span-s", type=float, default=12.0)
    p.add_argument("--keep-frames", action="store_true")
    p.add_argument("--no-open", action="store_true")
    return p.parse_args()


def default_resolution(domain: str) -> int:
    return {"physical": 241, "expanded": 641, "broad": 501}[domain]


def maybe_open(path: Path):
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass


def write_rows(path: Path, rows: list[dict]):
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


def _static_box(ref):
    law = ref.decoded.system.cvt.traction_law
    return (law.primary_static_interval.lower, law.primary_static_interval.upper,
            law.secondary_static_interval.lower, law.secondary_static_interval.upper)


def positive_limits(values):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a) & (a > 0)]
    if a.size == 0:
        return 1e-12, 1.0
    lo = max(float(np.percentile(a, 1)), 1e-16)
    hi = max(float(np.percentile(a, 99.8)), lo * 1.01)
    return lo, hi


def build_hill_reference(grade_start_distance_m: float, grade_angle_deg: float, time_span_s: float):
    spec = cc_run.load_json(cc_run.SPEC_FILE)
    temp = copy.deepcopy(spec)
    temp["reference_runs"] = {
        "hill_transition": {
            "time_span_s": [0.0, float(time_span_s)],
            "sample_step_s": 0.002,
            "integrator": {"relative_tolerance": 1e-4, "absolute_tolerance": 1e-7, "max_step": 0.01},
            "road_grade_segments": [
                {"start_distance_m": 0.0, "grade_angle_deg": 0.0},
                {"start_distance_m": float(grade_start_distance_m), "grade_angle_deg": float(grade_angle_deg)},
            ],
        }
    }
    return cc_run.build_reference(temp, "hill_transition")


def engaged_label(sample):
    mode = sample.composed_mode.cvt
    if mode.engagement is not CVTEngagementState.ENGAGED:
        return "not_engaged"
    if mode.contact_regime is None:
        return "engaged_no_contact"
    return mode.contact_regime.mode.value


def select_transition_indices(samples, frames: int):
    engaged = [s for s in samples if s.composed_mode.cvt.engagement is CVTEngagementState.ENGAGED]
    if not engaged:
        raise RuntimeError("No engaged samples found in hill scenario.")
    labels = [engaged_label(s) for s in engaged]
    event = None
    for i in range(1, len(engaged)):
        if labels[i] != labels[i-1]:
            event = i
            break
    if event is None:
        # fallback: first sign change to opening/backshift behavior if present
        for i in range(1, len(engaged)):
            if engaged[i-1].cvt_state.shift_speed >= 0.0 and engaged[i].cvt_state.shift_speed < 0.0:
                event = i
                break
    if event is None:
        event = len(engaged) // 2
    half = max(1, frames // 2)
    lo = max(0, event - half)
    hi = min(len(engaged) - 1, event + half)
    idx = np.linspace(lo, hi, frames)
    idx = np.unique(np.round(idx).astype(int))
    selected = [engaged[int(i)] for i in idx]
    return selected, int(event), labels[event]


def overlay_plot(data, actual, label: str, path: Path, *, ref, domain: str, mask_overlay: bool, plot_limit: float | None):
    lp, ls = data["lambda_p"], data["lambda_s"]
    LP, LS = np.meshgrid(lp, ls)
    cond = np.asarray(data["cond_A_scaled"], float)
    invalid = ~np.asarray(data["topology_admissible"], bool)
    fig, ax = plt.subplots(figsize=(9.2, 7.6))
    lo, hi = positive_limits(cond)
    im = ax.pcolormesh(LP, LS, cond, shading="auto", norm=LogNorm(vmin=lo, vmax=hi), rasterized=True)
    if mask_overlay:
        ax.contourf(LP, LS, invalid.astype(float), levels=[0.5, 1.5], colors=["0.7"], alpha=0.34)
    mode = actual["contact_mode"]
    try:
        if mode == EngagedContactMode.STICK_STICK.value:
            ax.contour(LP, LS, data["R_p"], levels=[0.0], colors="black", linewidths=1.2)
            ax.contour(LP, LS, data["R_s"], levels=[0.0], colors="black", linewidths=1.2, linestyles="--")
        elif mode == EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK.value:
            ax.contour(LP, LS, data["R_s"], levels=[0.0], colors="black", linewidths=1.3)
            ax.axvline(actual["lambda_p"], color="tab:orange", linewidth=1.8)
        elif mode == EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP.value:
            ax.contour(LP, LS, data["R_p"], levels=[0.0], colors="black", linewidths=1.3)
            ax.axhline(actual["lambda_s"], color="tab:orange", linewidth=1.8)
        else:
            ax.axvline(actual["lambda_p"], color="tab:orange", linewidth=1.8)
            ax.axhline(actual["lambda_s"], color="tab:orange", linewidth=1.8)
    except ValueError:
        pass
    if domain != "physical":
        p0, p1, s0, s1 = _static_box(ref)
        ax.add_patch(Rectangle((p0, s0), p1-p0, s1-s0, fill=False, linestyle=":", linewidth=1.2, edgecolor="tab:blue"))
    ax.plot(actual["lambda_p"], actual["lambda_s"], "x", markersize=10, mew=2.4, color="tab:red")
    subtitle = (
        f"t={actual['time_s']:.3f} s | mode={actual['contact_mode']} | shift={actual['shift_mm']:.2f} mm | sdot={actual['shift_speed_mm_s']:.1f} mm/s\n"
        f"root/point=({actual['lambda_p']:.3f}, {actual['lambda_s']:.3f}) | scaled kappa(A)={actual['A_condition_scaled']:.3g} | {actual['shift_constraint']}"
    )
    ax.set_title(f"{label}\n{subtitle}")
    ax.set_xlabel(r"$\lambda_p$")
    ax.set_ylabel(r"$\lambda_s$")
    if plot_limit is not None:
        ax.set_xlim(-plot_limit, plot_limit)
        ax.set_ylim(-plot_limit, plot_limit)
    fig.colorbar(im, ax=ax, label=r"equilibrated $\kappa(A)$")
    fig.tight_layout()
    fig.savefig(path, dpi=190)
    plt.close(fig)


def assemble_gif(paths, outpath: Path, fps: float):
    frames = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in paths]
    if not frames:
        raise RuntimeError("No frames were generated.")
    duration = max(1, int(round(1000.0 / max(fps, 1e-6))))
    frames[0].save(outpath, save_all=True, append_images=frames[1:], optimize=False, duration=duration, loop=0, disposal=2)
    for f in frames:
        f.close()


def _init_worker(grade_start_distance_m: float, grade_angle_deg: float, time_span_s: float, frames: int):
    global _WORKER_REF, _WORKER_SAMPLES
    cc_run.verify_environment()
    _WORKER_REF = build_hill_reference(grade_start_distance_m, grade_angle_deg, time_span_s)
    _WORKER_SAMPLES, _, _ = select_transition_indices(_WORKER_REF.samples, frames)


def _frame_worker(frame_no: int, domain: str, resolution: int, plot_limit: float | None, outdir: str):
    ref = _WORKER_REF
    sample = _WORKER_SAMPLES[frame_no]
    inspection = cc_run.reconstruct(ref, sample, closure_audit=True)
    contact = inspection.contact
    audit = inspection.closure_audit
    if contact is None or audit is None:
        raise RuntimeError("Expected engaged contact frame.")
    actual = {
        "time_s": float(sample.time),
        "shift_mm": 1000.0 * sample.cvt_state.shift_position,
        "shift_speed_mm_s": 1000.0 * sample.cvt_state.shift_speed,
        "lambda_p": float(contact.traction_utilization.primary_lambda),
        "lambda_s": float(contact.traction_utilization.secondary_lambda),
        "A_condition_scaled": float(audit.scaled_condition_number),
        "shift_constraint": str(sample.composed_mode.cvt.shift_constraint.value),
        "contact_mode": str(contact.mode.value),
    }
    data = cc_run.build_map(ref, sample, domain, resolution)
    root = Path(outdir)
    masked = root / f"masked_{frame_no:03d}.png"
    raw = root / f"raw_{frame_no:03d}.png"
    overlay_plot(data, actual, "Flat launch into hill — contact-transition clip", masked, ref=ref, domain=domain, mask_overlay=True, plot_limit=plot_limit)
    overlay_plot(data, actual, "Flat launch into hill — contact-transition clip", raw, ref=ref, domain=domain, mask_overlay=False, plot_limit=plot_limit)
    return {"frame_no": frame_no, "masked": str(masked), "raw": str(raw), **actual}


def main():
    args = parse_args()
    cc_run.verify_environment()
    resolution = int(args.resolution or default_resolution(args.domain))
    outdir = ARTIFACTS / f"{args.domain}_res{resolution}_frames{args.frames}_hill{int(args.grade_angle_deg)}deg"
    frame_dir = outdir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    # Build once to report selected event.
    ref = build_hill_reference(args.grade_start_distance_m, args.grade_angle_deg, args.time_span_s)
    selected, event_idx, event_label = select_transition_indices(ref.samples, args.frames)
    print(f"Selected {len(selected)} frames around event index {event_idx} ({event_label}).")
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, int(args.jobs)), initializer=_init_worker, initargs=(args.grade_start_distance_m, args.grade_angle_deg, args.time_span_s, args.frames)) as ex:
        futures = [ex.submit(_frame_worker, i, args.domain, resolution, args.plot_limit, str(frame_dir)) for i in range(len(selected))]
        for fut in as_completed(futures):
            row = fut.result()
            rows.append(row)
            print(f"  finished frame {row['frame_no']+1}/{len(selected)} at t={row['time_s']:.3f} s | mode={row['contact_mode']}")
    rows.sort(key=lambda r: r["frame_no"])
    write_rows(outdir / "frame_summary.csv", rows)
    masked_paths = [Path(r["masked"]) for r in rows]
    raw_paths = [Path(r["raw"]) for r in rows]
    masked_gif = outdir / f"hill_transition_{args.domain}_masked.gif"
    raw_gif = outdir / f"hill_transition_{args.domain}_raw.gif"
    assemble_gif(masked_paths, masked_gif, args.fps)
    assemble_gif(raw_paths, raw_gif, args.fps)
    print("\nOutputs:")
    print(masked_gif)
    print(raw_gif)
    print(outdir / "frame_summary.csv")
    if not args.keep_frames:
        for p in masked_paths + raw_paths:
            try:
                p.unlink()
            except FileNotFoundError:
                pass
    if not args.no_open:
        maybe_open(masked_gif)
        maybe_open(raw_gif)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
