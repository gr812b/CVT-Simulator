"""Animate nominal-run closure maps through the engaged stick-stick portion of the launch."""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.patches import Rectangle
import numpy as np
from PIL import Image

import run as cc_run

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts" / "nominal-animation"

_WORKER_LAUNCH = None
_WORKER_SAMPLES = None
_WORKER_SPEC = None


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=("physical", "expanded", "broad"), default="expanded",
                        help="Domain to compute. physical uses the static Coulomb box, expanded uses the study's [-2.6,2.6]^2 default, broad uses [-10,10]^2.")
    parser.add_argument("--resolution", type=int, default=None,
                        help="Grid points per axis. Defaults: physical=241, expanded=641, broad=1001.")
    parser.add_argument("--frame-count", type=int, default=24,
                        help="Number of uniformly sampled engaged stick-stick frames to animate.")
    parser.add_argument("--plot-limit", type=float, default=None,
                        help="Optional symmetric plotting limit. Useful to zoom a computed expanded/broad map to e.g. --plot-limit 2.0.")
    parser.add_argument("--fps", type=float, default=5.0, help="GIF frames per second.")
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                        help="Parallel worker count. Each worker builds the launch reference once and then processes multiple frames.")
    parser.add_argument("--keep-frames", action="store_true", help="Keep per-frame PNGs instead of deleting them after GIF assembly.")
    parser.add_argument("--no-open", action="store_true", help="Do not automatically open the finished GIFs.")
    return parser.parse_args()


def default_resolution(domain: str) -> int:
    return {"physical": 241, "expanded": 641, "broad": 1001}[domain]


def pick_frame_indices(total: int, count: int) -> list[int]:
    if total <= 0:
        return []
    count = max(1, min(int(count), total))
    idx = np.linspace(0, total - 1, count)
    idx = np.unique(np.round(idx).astype(int))
    if idx[0] != 0:
        idx = np.insert(idx, 0, 0)
    if idx[-1] != total - 1:
        idx = np.append(idx, total - 1)
    return [int(i) for i in idx]


def selected_engaged_samples(launch: cc_run.ReferenceRun):
    return [s for s in launch.samples if cc_run.is_stick_stick(s)]


def short_meta(ref: cc_run.ReferenceRun, sample: cc_run.FrozenSample):
    inspection = cc_run.reconstruct(ref, sample, closure_audit=True)
    contact = inspection.contact
    audit = inspection.closure_audit
    if contact is None or audit is None:
        raise RuntimeError("Selected sample is not an engaged contact state.")
    return {
        "time_s": float(sample.time),
        "shift_mm": 1000.0 * float(sample.cvt_state.shift_position),
        "shift_speed_mm_s": 1000.0 * float(sample.cvt_state.shift_speed),
        "lambda_p": float(contact.traction_utilization.primary_lambda),
        "lambda_s": float(contact.traction_utilization.secondary_lambda),
        "A_condition_scaled": float(audit.scaled_condition_number),
        "A_rank": int(audit.matrix_rank),
        "mode": str(contact.mode.value),
        "constraint": str(sample.composed_mode.cvt.shift_constraint.value),
    }


def _static_box(ref):
    law = ref.decoded.system.cvt.traction_law
    return (
        law.primary_static_interval.lower,
        law.primary_static_interval.upper,
        law.secondary_static_interval.lower,
        law.secondary_static_interval.upper,
    )


def positive_limits(values):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a) & (a > 0)]
    if a.size == 0:
        return 1e-12, 1.0
    lo = max(float(np.percentile(a, 1)), 1e-16)
    hi = max(float(np.percentile(a, 99.8)), lo * 1.01)
    return lo, hi


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
    try:
        ax.contour(LP, LS, data["R_p"], levels=[0.0], colors="black", linewidths=1.35)
        ax.contour(LP, LS, data["R_s"], levels=[0.0], colors="black", linewidths=1.35, linestyles="--")
    except ValueError:
        pass
    if domain != "physical":
        p0, p1, s0, s1 = _static_box(ref)
        ax.add_patch(Rectangle((p0, s0), p1-p0, s1-s0, fill=False, linestyle=":", linewidth=1.4, edgecolor="tab:blue"))
    ax.plot(actual["lambda_p"], actual["lambda_s"], "x", markersize=10, mew=2.4, color="tab:red")
    subtitle = (
        f"t={actual['time_s']:.3f} s, s={actual['shift_mm']:.2f} mm, sdot={actual['shift_speed_mm_s']:.2f} mm/s\n"
        f"root=({actual['lambda_p']:.3f}, {actual['lambda_s']:.3f}), scaled kappa(A)={actual['A_condition_scaled']:.3g}, {actual['constraint']}"
    )
    ax.set_title(f"{label}\n{subtitle}")
    ax.set_xlabel(r"$\lambda_p$")
    ax.set_ylabel(r"$\lambda_s$")
    if plot_limit is not None:
        ax.set_xlim(-plot_limit, plot_limit)
        ax.set_ylim(-plot_limit, plot_limit)
    fig.colorbar(im, ax=ax, label=r"equilibrated $\kappa(A)$")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def inadmissibility_plot(data, actual, label: str, path: Path, *, ref, domain: str, plot_limit: float | None):
    lp, ls = data["lambda_p"], data["lambda_s"]
    LP, LS = np.meshgrid(lp, ls)
    code = np.asarray(data["topology_failure_code"], dtype=int)
    masks = [
        ("Admissible", code == 0),
        ("Neg. integrated normal", (code & 1) != 0),
        ("Neg. belt tension", (code & 2) != 0),
        ("Local wrap lift-off", (code & 4) != 0),
        ("Mechanism violation", (code & 8) != 0),
        ("Support would pull", (code & 16) != 0),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 8.8), constrained_layout=True)
    for ax, (title, mask) in zip(axes.ravel(), masks):
        ax.pcolormesh(LP, LS, mask.astype(int), shading="auto", cmap="Greys", vmin=0, vmax=1, rasterized=True)
        if domain != "physical":
            p0, p1, s0, s1 = _static_box(ref)
            ax.add_patch(Rectangle((p0, s0), p1-p0, s1-s0, fill=False, linestyle=":", linewidth=1.2, edgecolor="tab:blue"))
        ax.plot(actual["lambda_p"], actual["lambda_s"], "x", markersize=8, mew=2, color="tab:red")
        ax.set_title(title)
        ax.set_xlabel(r"$\lambda_p$")
        ax.set_ylabel(r"$\lambda_s$")
        if plot_limit is not None:
            ax.set_xlim(-plot_limit, plot_limit)
            ax.set_ylim(-plot_limit, plot_limit)
    fig.suptitle(label)
    fig.savefig(path, dpi=170)
    plt.close(fig)


def _init_worker():
    global _WORKER_LAUNCH, _WORKER_SAMPLES, _WORKER_SPEC
    cc_run.verify_environment()
    _WORKER_SPEC = cc_run.load_json(cc_run.SPEC_FILE)
    _WORKER_LAUNCH = cc_run.build_reference(_WORKER_SPEC, "launch")
    _WORKER_SAMPLES = selected_engaged_samples(_WORKER_LAUNCH)


def _frame_worker(frame_no: int, sample_index: int, domain: str, resolution: int, plot_limit: float | None, outdir: str):
    ref = _WORKER_LAUNCH
    sample = _WORKER_SAMPLES[sample_index]
    label = f"mid_shift-style nominal evolution — frame {frame_no+1:03d}"
    actual = short_meta(ref, sample)
    data = cc_run.build_map(ref, sample, domain, resolution)
    root = Path(outdir)
    masked = root / f"masked_{frame_no:03d}.png"
    raw = root / f"raw_{frame_no:03d}.png"
    inad = root / f"inadmissibility_{frame_no:03d}.png"
    overlay_plot(data, actual, label, masked, ref=ref, domain=domain, mask_overlay=True, plot_limit=plot_limit)
    overlay_plot(data, actual, label, raw, ref=ref, domain=domain, mask_overlay=False, plot_limit=plot_limit)
    inadmissibility_plot(data, actual, label, inad, ref=ref, domain=domain, plot_limit=plot_limit)
    return {
        "frame_no": frame_no,
        "sample_index": sample_index,
        "masked": str(masked),
        "raw": str(raw),
        "inadmissibility": str(inad),
        **actual,
    }


def assemble_gif(paths: Iterable[Path], outpath: Path, fps: float):
    frames = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in paths]
    if not frames:
        raise RuntimeError("No frames were generated.")
    duration = max(1, int(round(1000.0 / max(fps, 1e-6))))
    frames[0].save(
        outpath,
        save_all=True,
        append_images=frames[1:],
        optimize=False,
        duration=duration,
        loop=0,
        disposal=2,
    )
    for im in frames:
        im.close()


def maybe_open(path: Path):
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass


def write_rows(path: Path, rows: list[dict]):
    import csv
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


def main():
    args = parse_args()
    cc_run.verify_environment()
    spec = cc_run.load_json(cc_run.SPEC_FILE)
    launch = cc_run.build_reference(spec, "launch")
    engaged = selected_engaged_samples(launch)
    if not engaged:
        raise RuntimeError("No engaged stick-stick samples were found in the nominal launch.")

    resolution = int(args.resolution or default_resolution(args.domain))
    frame_indices = pick_frame_indices(len(engaged), args.frame_count)
    tag_limit = f"limit{args.plot_limit:g}" if args.plot_limit is not None else "full"
    outdir = ARTIFACTS / f"{args.domain}_res{resolution}_frames{len(frame_indices)}_{tag_limit}"
    frame_dir = outdir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    print(f"Nominal engaged stick-stick samples available: {len(engaged)}")
    print(f"Selected frames: {len(frame_indices)}")
    print(f"Domain: {args.domain}; resolution: {resolution}x{resolution}; jobs: {args.jobs}")
    if args.plot_limit is not None:
        print(f"Plotting zoom: [-{args.plot_limit}, {args.plot_limit}]^2")

    rows = []
    with ProcessPoolExecutor(max_workers=max(1, int(args.jobs)), initializer=_init_worker) as ex:
        futures = [
            ex.submit(_frame_worker, k, idx, args.domain, resolution, args.plot_limit, str(frame_dir))
            for k, idx in enumerate(frame_indices)
        ]
        for fut in as_completed(futures):
            row = fut.result()
            rows.append(row)
            print(f"  finished frame {row['frame_no']+1}/{len(frame_indices)} at t={row['time_s']:.3f} s")
    rows.sort(key=lambda r: r["frame_no"])
    write_rows(outdir / "frame_summary.csv", rows)

    masked_paths = [Path(r["masked"]) for r in rows]
    raw_paths = [Path(r["raw"]) for r in rows]
    inad_paths = [Path(r["inadmissibility"]) for r in rows]
    masked_gif = outdir / f"nominal_{args.domain}_masked.gif"
    raw_gif = outdir / f"nominal_{args.domain}_raw.gif"
    inad_gif = outdir / f"nominal_{args.domain}_inadmissibility.gif"
    assemble_gif(masked_paths, masked_gif, args.fps)
    assemble_gif(raw_paths, raw_gif, args.fps)
    assemble_gif(inad_paths, inad_gif, args.fps)

    print("\nOutputs:")
    print(masked_gif)
    print(raw_gif)
    print(inad_gif)
    print(outdir / "frame_summary.csv")
    if not args.keep_frames:
        for p in masked_paths + raw_paths + inad_paths:
            try:
                p.unlink()
            except FileNotFoundError:
                pass
    if not args.no_open:
        maybe_open(masked_gif)
        maybe_open(raw_gif)
        maybe_open(inad_gif)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
