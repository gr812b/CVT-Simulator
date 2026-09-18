r"""Analyze folded R_s = 0 structure and search for possible multiple stick-stick roots.

This script does NOT run CINDER solves. It works from already-saved closure-map NPZ files
(full-resolution maps or share-bundle downsampled maps).

It focuses on the question:
    "Can the secondary residual fold create two intersections with R_p = 0?"

For each selected frame, it:
  1. finds row-wise zero crossings of R_s(lambda_p, lambda_s),
  2. tracks up to two visible R_s = 0 branches through lambda_s,
  3. interpolates R_p on each branch,
  4. checks whether R_p changes sign along either branch,
  5. reports candidate multi-root situations,
  6. produces explanatory plots.

Recommended usage from results/cinder-v1.1.2:

    python .\studies\closure-conditioning\analysis/analyze_secondary_fold_multiroot.py ^
      --source-dir .\studies\closure-conditioning\artifacts\controlled-free-shift-animation\expanded_res641_frames120

Or against a share bundle:

    python .\studies\closure-conditioning\analysis/analyze_secondary_fold_multiroot.py ^
      --source-dir .\studies\closure-conditioning\artifacts\controlled-free-shift-animation\expanded_res641_frames120\share_bundle_161

The script writes an output folder with:
  - branch_summary.csv
  - candidate_frames.csv
  - per-frame branch plots
  - per-frame local-focus maps
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import SymLogNorm


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir', type=Path, required=True,
                   help='Directory containing downsampled_maps/ or frames/map_data/.')
    p.add_argument('--output-dir', type=Path, default=None,
                   help='Where analysis artifacts are written. Default is inside source-dir.')
    p.add_argument('--frame-min', type=int, default=None)
    p.add_argument('--frame-max', type=int, default=None)
    p.add_argument('--frames', type=str, default='',
                   help='Optional comma-separated explicit frame list.')
    p.add_argument('--plot-limit', type=float, default=0.8,
                   help='Symmetric lambda view for local-focus figures.')
    p.add_argument('--max-branches', type=int, default=2,
                   help='Maximum number of R_s branches to track. Default 2.')
    p.add_argument('--rp-sign-tolerance', type=float, default=1.0,
                   help='Values with |R_p| below this count as near-zero for reports.')
    return p.parse_args()


def discover_map_dir(source_dir: Path) -> Path:
    candidates = [
        source_dir / 'downsampled_maps',
        source_dir / 'selected_full_resolution',
        source_dir / 'frames' / 'map_data',
        source_dir,
    ]
    for c in candidates:
        if c.is_dir() and any(c.glob('map_*.npz')):
            return c
    raise FileNotFoundError(f'Could not find map_*.npz under {source_dir}')


def parse_frame_list(text: str) -> set[int]:
    out: set[int] = set()
    text = text.strip()
    if not text:
        return out
    for token in text.split(','):
        token = token.strip()
        if token:
            out.add(int(token))
    return out


@dataclass
class BranchPoint:
    lambda_s: float
    lambda_p: float
    R_p: float


@dataclass
class BranchTrack:
    points: list[BranchPoint]

    def append(self, point: BranchPoint) -> None:
        self.points.append(point)

    @property
    def lambdas_s(self) -> np.ndarray:
        return np.asarray([p.lambda_s for p in self.points], dtype=float)

    @property
    def lambdas_p(self) -> np.ndarray:
        return np.asarray([p.lambda_p for p in self.points], dtype=float)

    @property
    def residuals_p(self) -> np.ndarray:
        return np.asarray([p.R_p for p in self.points], dtype=float)


def interp_zero_crossings(x: np.ndarray, y: np.ndarray) -> list[float]:
    roots: list[float] = []
    for i in range(len(x) - 1):
        y0 = y[i]
        y1 = y[i + 1]
        if not np.isfinite(y0) or not np.isfinite(y1):
            continue
        if y0 == 0.0:
            roots.append(float(x[i]))
            continue
        if y0 * y1 > 0.0:
            continue
        dx = x[i + 1] - x[i]
        if y1 == y0:
            roots.append(float(0.5 * (x[i] + x[i + 1])))
        else:
            alpha = -y0 / (y1 - y0)
            roots.append(float(x[i] + alpha * dx))
    # de-duplicate roots that can occur when a grid point is exactly zero.
    cleaned: list[float] = []
    for r in roots:
        if not cleaned or abs(r - cleaned[-1]) > 1.0e-10:
            cleaned.append(r)
    return cleaned


def interp_scalar_at(x: np.ndarray, y: np.ndarray, xq: float) -> float:
    if xq <= x[0]:
        return float(y[0])
    if xq >= x[-1]:
        return float(y[-1])
    idx = int(np.searchsorted(x, xq) - 1)
    idx = max(0, min(idx, len(x) - 2))
    x0 = x[idx]
    x1 = x[idx + 1]
    y0 = y[idx]
    y1 = y[idx + 1]
    if not np.isfinite(y0) or not np.isfinite(y1):
        return float('nan')
    if x1 == x0:
        return float(y0)
    alpha = (xq - x0) / (x1 - x0)
    return float((1.0 - alpha) * y0 + alpha * y1)


def track_rs_branches(lambda_p: np.ndarray, lambda_s: np.ndarray, R_s: np.ndarray, R_p: np.ndarray,
                      max_branches: int) -> list[BranchTrack]:
    pending: list[BranchTrack] = []
    active: list[BranchTrack] = []
    for row, ls in enumerate(lambda_s):
        rs_row = np.asarray(R_s[row, :], dtype=float)
        rp_row = np.asarray(R_p[row, :], dtype=float)
        roots = interp_zero_crossings(lambda_p, rs_row)
        points = [BranchPoint(lambda_s=float(ls), lambda_p=root,
                              R_p=interp_scalar_at(lambda_p, rp_row, root)) for root in roots]
        if row == 0 or not active:
            active = [BranchTrack([pt]) for pt in points[:max_branches]]
            continue
        # nearest-neighbour continuation from existing branch endpoints.
        unused = list(points)
        new_active: list[BranchTrack] = []
        for track in active:
            prev = track.points[-1]
            if not unused:
                new_active.append(track)
                continue
            distances = [abs(pt.lambda_p - prev.lambda_p) for pt in unused]
            best_idx = int(np.argmin(distances))
            if distances[best_idx] <= 0.15 or len(unused) == 1:
                track.append(unused.pop(best_idx))
            new_active.append(track)
        # Spawn missing visible branches if we currently see more branches.
        while unused and len(new_active) < max_branches:
            new_active.append(BranchTrack([unused.pop(0)]))
        active = new_active
    return active


def sign_change_intervals(x: np.ndarray, y: np.ndarray, tol: float) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for i in range(len(x) - 1):
        y0 = y[i]
        y1 = y[i + 1]
        if not np.isfinite(y0) or not np.isfinite(y1):
            continue
        if abs(y0) <= tol or abs(y1) <= tol or y0 * y1 < 0.0:
            out.append((float(x[i]), float(x[i + 1])))
    return out


def make_branch_plot(out_path: Path, z: dict[str, np.ndarray], tracks: list[BranchTrack], plot_limit: float,
                     rp_tol: float) -> None:
    lp = np.asarray(z['lambda_p'], dtype=float)
    ls = np.asarray(z['lambda_s'], dtype=float)
    LP, LS = np.meshgrid(lp, ls)
    R_s = np.asarray(z['R_s'], dtype=float)
    R_p = np.asarray(z['R_p'], dtype=float)
    valid = np.asarray(z['topology_admissible'], dtype=bool)
    masked = np.ma.masked_where(~valid, R_s)
    finite = R_s[np.isfinite(R_s) & valid]
    lim = float(np.percentile(np.abs(finite), 99.0)) if finite.size else 1.0
    lim = max(lim, 1.0)

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.6), constrained_layout=True)

    ax = axes[0]
    im = ax.pcolormesh(LP, LS, masked, shading='auto',
                       norm=SymLogNorm(linthresh=1.0, vmin=-lim, vmax=lim), rasterized=True)
    try:
        ax.contour(LP, LS, R_s, levels=[0.0], colors='black', linewidths=1.2)
        ax.contour(LP, LS, R_p, levels=[0.0], colors='cyan', linewidths=1.0, linestyles='--')
    except Exception:
        pass
    colors = ['tab:red', 'tab:orange', 'tab:purple', 'tab:green']
    for k, track in enumerate(tracks):
        ax.plot(track.lambdas_p, track.lambdas_s, '-', lw=2.0, color=colors[k % len(colors)],
                label=f'R_s branch {k + 1}')
    ax.plot(float(z['actual__lambda_p']), float(z['actual__lambda_s']), 'rx', ms=8, mew=2)
    ax.set_xlim(-plot_limit, plot_limit)
    ax.set_ylim(-plot_limit, plot_limit)
    ax.set_xlabel(r'$\lambda_p$')
    ax.set_ylabel(r'$\lambda_s$')
    ax.set_title(r'Secondary residual $R_s$ with tracked $R_s=0$ branches')
    ax.legend(loc='best', fontsize=8)
    fig.colorbar(im, ax=ax, label=r'$R_s$')

    ax = axes[1]
    for k, track in enumerate(tracks):
        ax.plot(track.lambdas_s, track.residuals_p, '-o', ms=3.0, lw=1.5,
                color=colors[k % len(colors)], label=f'branch {k + 1}')
        for a, b in sign_change_intervals(track.lambdas_s, track.residuals_p, rp_tol):
            ax.axvspan(a, b, color=colors[k % len(colors)], alpha=0.15)
    ax.axhline(0.0, color='black', lw=1.0)
    ax.axhline(rp_tol, color='0.5', lw=0.8, ls=':')
    ax.axhline(-rp_tol, color='0.5', lw=0.8, ls=':')
    ax.set_xlabel(r'$\lambda_s$ along each tracked $R_s=0$ branch')
    ax.set_ylabel(r'$R_p$ evaluated on the branch [m/s$^2$]')
    ax.set_title(r'Does $R_p$ cross zero on either $R_s=0$ branch?')
    ax.legend(loc='best', fontsize=8)

    frame = int(z['actual__frame_no'])
    fig.suptitle(
        f'Fold / multi-root diagnostic | frame {frame:03d} | '
        f'actual λ=({float(z["actual__lambda_p"]):+.3f}, {float(z["actual__lambda_s"]):+.3f})'
    )
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        return {k: np.asarray(data[k]) for k in data.files}


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    map_dir = discover_map_dir(source_dir)
    output_dir = (args.output_dir.resolve() if args.output_dir is not None else source_dir / 'multiroot_branch_analysis')
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / 'figures'
    figures_dir.mkdir(exist_ok=True)

    explicit_frames = parse_frame_list(args.frames)
    map_paths = sorted(map_dir.glob('map_*.npz'))
    selected: list[Path] = []
    for path in map_paths:
        frame = int(path.stem.split('_')[-1])
        if explicit_frames and frame not in explicit_frames:
            continue
        if args.frame_min is not None and frame < args.frame_min:
            continue
        if args.frame_max is not None and frame > args.frame_max:
            continue
        selected.append(path)
    if not selected:
        raise SystemExit('No map files matched the requested frame selection.')

    summary_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []

    for idx, path in enumerate(selected, start=1):
        z = load_npz(path)
        tracks = track_rs_branches(lambda_p=z['lambda_p'], lambda_s=z['lambda_s'],
                                   R_s=z['R_s'], R_p=z['R_p'], max_branches=args.max_branches)
        has_double = sum(len(track.points) > 1 for track in tracks) >= 2
        frame = int(z['actual__frame_no'])
        fig_path = figures_dir / f'frame_{frame:03d}_branch_analysis.png'
        make_branch_plot(fig_path, z, tracks, args.plot_limit, args.rp_sign_tolerance)

        min_abs_rp = []
        intervals_report = []
        roots_found = 0
        for b, track in enumerate(tracks, start=1):
            if not track.points:
                continue
            rp = track.residuals_p
            ls = track.lambdas_s
            min_abs = float(np.nanmin(np.abs(rp)))
            min_abs_rp.append(min_abs)
            sign_windows = sign_change_intervals(ls, rp, args.rp_sign_tolerance)
            if sign_windows:
                roots_found += 1
                for a, bnd in sign_windows:
                    candidate_rows.append({
                        'frame_no': frame,
                        'branch_index': b,
                        'lambda_s_window_min': a,
                        'lambda_s_window_max': bnd,
                        'local_min_abs_Rp': min_abs,
                        'figure': str(fig_path.relative_to(output_dir)),
                    })
                    intervals_report.append(f'branch {b}: [{a:+.4f}, {bnd:+.4f}]')

        summary_rows.append({
            'frame_no': frame,
            'leg': str(z['actual__leg']) if 'actual__leg' in z else '',
            'actual_lambda_p': float(z['actual__lambda_p']) if 'actual__lambda_p' in z else np.nan,
            'actual_lambda_s': float(z['actual__lambda_s']) if 'actual__lambda_s' in z else np.nan,
            'double_branch_visible': has_double,
            'tracked_branch_count': len(tracks),
            'branch_min_abs_Rp': '; '.join(f'{v:.6g}' for v in min_abs_rp),
            'candidate_intersections_found': roots_found,
            'candidate_windows': '; '.join(intervals_report),
            'figure': str(fig_path.relative_to(output_dir)),
        })
        print(f'[{idx:03d}/{len(selected):03d}] frame {frame:03d}: '
              f'branches={len(tracks)}, double_visible={has_double}, candidates={roots_found}')

    def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
        if not rows:
            path.write_text('', encoding='utf-8')
            return
        fieldnames = list(rows[0].keys())
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    write_csv(output_dir / 'branch_summary.csv', summary_rows)
    write_csv(output_dir / 'candidate_frames.csv', candidate_rows)

    readme = output_dir / 'README.txt'
    readme.write_text(
        'Interpretation:\n'
        '  - double_branch_visible = the R_s = 0 set visibly folded into two tracked branches.\n'
        '  - candidate_intersections_found > 0 = along at least one R_s branch, R_p crosses or nearly\n'
        '    crosses zero within the chosen tolerance, meaning a stick-stick intersection may lie there.\n'
        '  - branch_min_abs_Rp lists the closest approach of R_p to zero on each tracked branch.\n',
        encoding='utf-8'
    )
    print(f'Wrote analysis to {output_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
