"""Robust connected-contour audit for possible multiple stick-stick roots.

This script performs NO CINDER solves. It analyzes already-saved closure maps.

Unlike the earlier branch tracker, it does not connect row-wise zero crossings across
disconnected contour pieces. Instead it extracts the actual connected R_s = 0 contour
components using contourpy, evaluates R_p continuously along each component, and
reports each genuine R_p = R_s = 0 intersection.

Typical usage from results/cinder-v1.1.2:

    python .\studies\closure-conditioning\analyze_connected_multiroot_contours.py `
      --source-dir .\studies\closure-conditioning\artifacts\controlled-free-shift-animation\expanded_res641_frames120\share_bundle_161 `
      --frame-min 56 --frame-max 65 --analysis-limit 0.8

Outputs:
  connected_contour_summary.csv
  intersections.csv
  figures/frame_XXX_connected_contours.png

A frame has a genuine multi-root candidate only if `additional_intersections > 0`.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import contourpy
import matplotlib.pyplot as plt
from matplotlib.colors import SymLogNorm
import numpy as np
from scipy.interpolate import RegularGridInterpolator


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument("--frame-min", type=int, default=None)
    p.add_argument("--frame-max", type=int, default=None)
    p.add_argument("--frames", type=str, default="")
    p.add_argument("--analysis-limit", type=float, default=0.8,
                   help="Only count contour/intersection geometry inside ±this lambda box.")
    p.add_argument("--actual-root-distance", type=float, default=0.03,
                   help="Intersection within this Euclidean lambda-distance of the saved actual root is classified as the actual root.")
    return p.parse_args()


def discover_map_dir(source: Path) -> Path:
    candidates = [
        source / "selected_full_resolution",
        source / "downsampled_maps",
        source / "frames" / "map_data",
        source,
    ]
    for c in candidates:
        if c.is_dir() and any(c.glob("map_*.npz")):
            return c
    raise FileNotFoundError(f"No map_*.npz found under {source}")


def preferred_map_paths(source: Path) -> dict[int, Path]:
    """Prefer selected full-resolution maps, then downsampled/full archive."""
    result: dict[int, Path] = {}
    candidates = [
        source / "downsampled_maps",
        source / "frames" / "map_data",
        source,
        source / "selected_full_resolution",
    ]
    for directory in candidates:
        if not directory.is_dir():
            continue
        for path in directory.glob("map_*.npz"):
            frame = int(path.stem.split("_")[-1])
            result[frame] = path
    return result


def parse_frames(text: str) -> set[int]:
    if not text.strip():
        return set()
    return {int(x.strip()) for x in text.split(",") if x.strip()}


def load(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        return {k: np.asarray(z[k]) for k in z.files}


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def extract_rs_components(z: dict[str, np.ndarray]) -> list[np.ndarray]:
    lp = np.asarray(z["lambda_p"], dtype=float)
    ls = np.asarray(z["lambda_s"], dtype=float)
    rs = np.asarray(z["R_s"], dtype=float)
    valid = np.asarray(z.get("topology_admissible", np.ones_like(rs, dtype=bool)), dtype=bool)
    masked = np.ma.masked_where(~valid | ~np.isfinite(rs), rs)
    cg = contourpy.contour_generator(x=lp, y=ls, z=masked, name="serial")
    return [np.asarray(line, dtype=float) for line in cg.lines(0.0)]


def interpolate_values(z: dict[str, np.ndarray], points: np.ndarray) -> np.ndarray:
    lp = np.asarray(z["lambda_p"], dtype=float)
    ls = np.asarray(z["lambda_s"], dtype=float)
    rp = np.asarray(z["R_p"], dtype=float)
    interp = RegularGridInterpolator((ls, lp), rp, bounds_error=False, fill_value=np.nan)
    return np.asarray([float(interp((y, x))) for x, y in points], dtype=float)


def clip_component_to_box(line: np.ndarray, limit: float) -> list[np.ndarray]:
    """Return contiguous vertex runs lying inside the analysis box."""
    inside = (np.abs(line[:, 0]) <= limit) & (np.abs(line[:, 1]) <= limit)
    runs: list[np.ndarray] = []
    start = None
    for i, flag in enumerate(inside):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            if i - start >= 2:
                runs.append(line[start:i])
            start = None
    if start is not None and len(line) - start >= 2:
        runs.append(line[start:])
    return runs


def segment_intersections(points: np.ndarray, rp_values: np.ndarray) -> list[tuple[float, float]]:
    roots: list[tuple[float, float]] = []
    for i in range(len(points) - 1):
        r0 = rp_values[i]
        r1 = rp_values[i + 1]
        if not np.isfinite(r0) or not np.isfinite(r1):
            continue
        if r0 == 0.0:
            roots.append(tuple(points[i]))
            continue
        if r0 * r1 > 0.0:
            continue
        denom = r1 - r0
        alpha = 0.5 if denom == 0.0 else -r0 / denom
        alpha = min(1.0, max(0.0, float(alpha)))
        p = (1.0 - alpha) * points[i] + alpha * points[i + 1]
        roots.append((float(p[0]), float(p[1])))
    # de-duplicate near-identical intersections
    unique: list[tuple[float, float]] = []
    for root in roots:
        if not any(np.hypot(root[0] - q[0], root[1] - q[1]) < 1.0e-4 for q in unique):
            unique.append(root)
    return unique


def render_figure(path: Path, z: dict[str, np.ndarray], local_components: list[tuple[int, np.ndarray, np.ndarray]],
                  intersections: list[dict], limit: float) -> None:
    lp = np.asarray(z["lambda_p"], dtype=float)
    ls = np.asarray(z["lambda_s"], dtype=float)
    LP, LS = np.meshgrid(lp, ls)
    rs = np.asarray(z["R_s"], dtype=float)
    rp = np.asarray(z["R_p"], dtype=float)
    valid = np.asarray(z.get("topology_admissible", np.ones_like(rs, dtype=bool)), dtype=bool)
    masked = np.ma.masked_where(~valid, rs)
    finite = rs[valid & np.isfinite(rs)]
    color_lim = max(float(np.percentile(np.abs(finite), 99.0)) if finite.size else 1.0, 1.0)

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.7), constrained_layout=True)

    ax = axes[0]
    im = ax.pcolormesh(LP, LS, masked, shading="auto",
                       norm=SymLogNorm(linthresh=1.0, vmin=-color_lim, vmax=color_lim),
                       rasterized=True)
    try:
        ax.contour(LP, LS, rp, levels=[0.0], colors="cyan", linestyles="--", linewidths=1.2)
    except Exception:
        pass
    colors = ["tab:red", "tab:orange", "tab:purple", "tab:green", "tab:brown"]
    for component_index, run, rp_on_run in local_components:
        ax.plot(run[:, 0], run[:, 1], lw=2.0,
                color=colors[component_index % len(colors)],
                label=f"connected R_s=0 component {component_index}")
    if "actual__lambda_p" in z:
        ax.plot(float(z["actual__lambda_p"]), float(z["actual__lambda_s"]), "rx", ms=8, mew=2,
                label="saved actual root")
    for item in intersections:
        marker = "o" if item["classification"] == "actual_root" else "*"
        ax.plot(item["lambda_p"], item["lambda_s"], marker=marker, ms=10,
                markerfacecolor="none" if marker == "o" else "yellow",
                markeredgecolor="black", mew=1.2)
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-limit, limit)
    ax.set_xlabel(r"$\lambda_p$")
    ax.set_ylabel(r"$\lambda_s$")
    ax.set_title(r"Connected $R_s=0$ components; cyan dashed is $R_p=0$")
    ax.legend(fontsize=8, loc="best")
    fig.colorbar(im, ax=ax, label=r"$R_s$")

    ax = axes[1]
    for component_index, run, rp_on_run in local_components:
        distance = np.arange(len(run))
        ax.plot(distance, rp_on_run, lw=1.8,
                color=colors[component_index % len(colors)],
                label=f"component {component_index}")
    ax.axhline(0.0, color="black", lw=1.0)
    ax.set_xlabel("ordered contour vertex")
    ax.set_ylabel(r"$R_p$ evaluated on connected $R_s=0$ contour")
    ax.set_title(r"A genuine intersection requires $R_p$ to cross zero")
    ax.legend(fontsize=8, loc="best")

    frame = int(z["actual__frame_no"]) if "actual__frame_no" in z else -1
    fig.suptitle(f"Connected-contour multi-root audit | frame {frame:03d}")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    source = args.source_dir.resolve()
    maps = preferred_map_paths(source)
    explicit = parse_frames(args.frames)
    frames = sorted(maps)
    if explicit:
        frames = [f for f in frames if f in explicit]
    if args.frame_min is not None:
        frames = [f for f in frames if f >= args.frame_min]
    if args.frame_max is not None:
        frames = [f for f in frames if f <= args.frame_max]
    if not frames:
        raise SystemExit("No requested frames found.")

    out = args.output_dir.resolve() if args.output_dir else source / "connected_multiroot_analysis"
    figs = out / "figures"
    figs.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict] = []
    root_rows: list[dict] = []

    for frame in frames:
        z = load(maps[frame])
        components = extract_rs_components(z)
        actual = None
        if "actual__lambda_p" in z:
            actual = np.array([float(z["actual__lambda_p"]), float(z["actual__lambda_s"])], dtype=float)

        local_components: list[tuple[int, np.ndarray, np.ndarray]] = []
        intersections: list[dict] = []
        component_stats: list[str] = []

        local_index = 0
        for global_index, component in enumerate(components):
            runs = clip_component_to_box(component, args.analysis_limit)
            for run in runs:
                rp_on_run = interpolate_values(z, run)
                if not np.any(np.isfinite(rp_on_run)):
                    continue
                min_rp = float(np.nanmin(rp_on_run))
                max_rp = float(np.nanmax(rp_on_run))
                min_abs = float(np.nanmin(np.abs(rp_on_run)))
                roots = segment_intersections(run, rp_on_run)
                local_components.append((local_index, run, rp_on_run))
                component_stats.append(
                    f"{local_index}: Rp=[{min_rp:+.3g},{max_rp:+.3g}], min|Rp|={min_abs:.3g}, intersections={len(roots)}"
                )
                for p, s in roots:
                    if actual is not None and np.hypot(p - actual[0], s - actual[1]) <= args.actual_root_distance:
                        classification = "actual_root"
                    else:
                        classification = "additional_root_candidate"
                    row = {
                        "frame_no": frame,
                        "component_index": local_index,
                        "lambda_p": p,
                        "lambda_s": s,
                        "classification": classification,
                        "distance_from_actual_root": (
                            float(np.hypot(p - actual[0], s - actual[1])) if actual is not None else np.nan
                        ),
                    }
                    intersections.append(row)
                    root_rows.append(row)
                local_index += 1

        actual_count = sum(x["classification"] == "actual_root" for x in intersections)
        additional_count = sum(x["classification"] == "additional_root_candidate" for x in intersections)
        summary_rows.append({
            "frame_no": frame,
            "leg": str(z["actual__leg"]) if "actual__leg" in z else "",
            "actual_lambda_p": float(z["actual__lambda_p"]) if "actual__lambda_p" in z else np.nan,
            "actual_lambda_s": float(z["actual__lambda_s"]) if "actual__lambda_s" in z else np.nan,
            "connected_Rs_components_in_box": local_index,
            "actual_root_intersections": actual_count,
            "additional_intersections": additional_count,
            "component_stats": " | ".join(component_stats),
        })

        render_figure(figs / f"frame_{frame:03d}_connected_contours.png",
                      z, local_components, intersections, args.analysis_limit)
        print(f"frame {frame:03d}: local components={local_index}, actual={actual_count}, additional={additional_count}")

    write_csv(out / "connected_contour_summary.csv", summary_rows)
    write_csv(out / "intersections.csv", root_rows)
    (out / "README.txt").write_text(
        "Trust criterion: only intersections reported from a connected R_s=0 contour component are counted.\n"
        "additional_intersections > 0 is the actual multi-root flag.\n"
        "The earlier row-wise branch tracker could connect disconnected contour pieces and should not be used for root counts.\n",
        encoding="utf-8",
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
