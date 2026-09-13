"""Render a full-run 4x2 closure-conditioning GIF from saved map files.

This script does NOT run CINDER solves. It reads an existing share bundle or a directory of
saved `map_*.npz` files and renders one composite frame per map with the panels:

  [R_p, R_s, |R|, kappa(A)]
  [sigma_min(J_R), kappa(J_R), det(J_R), inadmissibility]

Recommended usage from results/cinder-v1.1.2:

    python .\studies\closure-conditioning\render_full_4x2_share_bundle_gif.py ^
      --source-dir .\studies\closure-conditioning\artifacts\controlled-free-shift-animation\expanded_res641_frames120\share_bundle_161
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, SymLogNorm, TwoSlopeNorm, ListedColormap
from PIL import Image


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir', type=Path, required=True,
                   help='Directory containing downsampled_maps/ or frames/map_data/.')
    p.add_argument('--output-dir', type=Path, default=None)
    p.add_argument('--plot-limit', type=float, default=2.0,
                   help='Symmetric lambda-domain half-width shown in each panel.')
    p.add_argument('--duration-ms', type=int, default=120,
                   help='Per-frame GIF duration in milliseconds.')
    p.add_argument('--dpi', type=int, default=85,
                   help='Composite-frame raster DPI. Lower gives smaller PNG staging files.')
    return p.parse_args()


def discover_map_dir(source_dir: Path) -> Path:
    candidates = [
        source_dir / 'downsampled_maps',
        source_dir / 'frames' / 'map_data',
        source_dir,
    ]
    for c in candidates:
        if c.is_dir() and any(c.glob('map_*.npz')):
            return c
    raise FileNotFoundError(f'Could not find map_*.npz under {source_dir}')


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        return {k: np.asarray(data[k]) for k in data.files}


def robust_positive_limits(values: list[np.ndarray]) -> tuple[float, float]:
    a = np.concatenate(values) if values else np.array([1.0])
    a = a[np.isfinite(a) & (a > 0.0)]
    lo = max(float(np.percentile(a, 1.0)), 1.0e-12)
    hi = max(float(np.percentile(a, 99.5)), lo * 1.01)
    return lo, hi


def robust_signed_limit(values: list[np.ndarray]) -> float:
    a = np.concatenate(values) if values else np.array([1.0])
    a = np.abs(a[np.isfinite(a)])
    return max(float(np.percentile(a, 99.5)), 1.0e-9)


def compute_scales(files: list[Path]) -> dict[str, object]:
    buckets = {k: [] for k in ['R_p', 'R_s', 'R_norm', 'cond_A_scaled', 'sigma_min_J', 'kappa_J', 'det_J']}
    for path in files:
        z = load_npz(path)
        mask = np.asarray(z.get('topology_admissible', np.ones_like(z['R_p'], dtype=bool)), dtype=bool)
        for key in buckets:
            if key not in z:
                continue
            arr = np.asarray(z[key], dtype=float)
            arr = arr[np.isfinite(arr) & mask]
            if arr.size:
                buckets[key].append(arr)
    rp_lim = robust_signed_limit(buckets['R_p'])
    rs_lim = robust_signed_limit(buckets['R_s'])
    det_lim = robust_signed_limit(buckets['det_J'])
    rn_lo, rn_hi = robust_positive_limits(buckets['R_norm'])
    a_lo, a_hi = robust_positive_limits(buckets['cond_A_scaled'])
    sm_lo, sm_hi = robust_positive_limits(buckets['sigma_min_J'])
    jc_lo, jc_hi = robust_positive_limits(buckets['kappa_J'])
    return {
        'Rp': SymLogNorm(linthresh=1.0, vmin=-rp_lim, vmax=rp_lim),
        'Rs': SymLogNorm(linthresh=1.0, vmin=-rs_lim, vmax=rs_lim),
        'Rnorm': LogNorm(vmin=rn_lo, vmax=rn_hi),
        'Acond': LogNorm(vmin=a_lo, vmax=a_hi),
        'Jmin': LogNorm(vmin=sm_lo, vmax=sm_hi),
        'Jcond': LogNorm(vmin=jc_lo, vmax=jc_hi),
        'Jdet': TwoSlopeNorm(vcenter=0.0, vmin=-det_lim, vmax=det_lim),
    }


def render_panel(ax, z: dict[str, np.ndarray], panel: str, scales: dict[str, object], plot_limit: float):
    lambda_p = np.asarray(z['lambda_p'], dtype=float)
    lambda_s = np.asarray(z['lambda_s'], dtype=float)
    LP, LS = np.meshgrid(lambda_p, lambda_s)
    valid = np.asarray(z.get('topology_admissible', np.ones_like(z['R_p'], dtype=bool)), dtype=bool)
    if panel == 'inad':
        code = np.asarray(z['topology_failure_code'], dtype=int)
        disp = np.zeros_like(code, dtype=int)
        disp[(code & 2) != 0] = 1
        disp[(code & 4) != 0] = 2
        disp[(code & 8) != 0] = 3
        disp[(code & 1) != 0] = 4
        ax.pcolormesh(LP, LS, disp, shading='auto',
                      cmap=ListedColormap(['white', '#4c78a8', '#f58518', '#54a24b', '#e45756']),
                      vmin=0, vmax=4, rasterized=True)
    else:
        key = {
            'Rp': 'R_p', 'Rs': 'R_s', 'Rnorm': 'R_norm', 'Acond': 'cond_A_scaled',
            'Jmin': 'sigma_min_J', 'Jcond': 'kappa_J', 'Jdet': 'det_J'
        }[panel]
        arr = np.asarray(z[key], dtype=float)
        arr = np.ma.masked_where(~valid, arr)
        ax.pcolormesh(LP, LS, arr, shading='auto', norm=scales[panel], rasterized=True)
        if panel in ('Rp', 'Rs', 'Rnorm'):
            try:
                ax.contour(LP, LS, z['R_p'], levels=[0.0], colors='black', linewidths=0.8)
                ax.contour(LP, LS, z['R_s'], levels=[0.0], colors='cyan', linewidths=0.8, linestyles='--')
            except Exception:
                pass
    if 'actual__lambda_p' in z and 'actual__lambda_s' in z:
        ax.plot(float(z['actual__lambda_p']), float(z['actual__lambda_s']), 'rx', ms=4.5, mew=1.3)
    ax.set_xlim(-plot_limit, plot_limit)
    ax.set_ylim(-plot_limit, plot_limit)
    ax.tick_params(labelsize=6)


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    map_dir = discover_map_dir(source_dir)
    output_dir = (args.output_dir.resolve() if args.output_dir is not None else source_dir / 'full_4x2_gif')
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_dir = output_dir / 'frames'
    frame_dir.mkdir(exist_ok=True)

    files = sorted(map_dir.glob('map_*.npz'))
    if not files:
        raise SystemExit('No map_*.npz files found.')
    scales = compute_scales(files)
    panels = ['Rp', 'Rs', 'Rnorm', 'Acond', 'Jmin', 'Jcond', 'Jdet', 'inad']
    titles = {'Rp': 'R_p', 'Rs': 'R_s', 'Rnorm': '|R|', 'Acond': 'kappa(A)',
              'Jmin': 'sigma_min(J_R)', 'Jcond': 'kappa(J_R)', 'Jdet': 'det(J_R)', 'inad': 'inadmissibility'}

    rendered_paths: list[Path] = []
    for idx, path in enumerate(files, start=1):
        z = load_npz(path)
        fig, axes = plt.subplots(2, 4, figsize=(12.8, 6.8), constrained_layout=False)
        for ax, panel in zip(axes.ravel(), panels):
            render_panel(ax, z, panel, scales, args.plot_limit)
            ax.set_title(titles[panel], fontsize=8)
            ax.set_xlabel(r'$\lambda_p$', fontsize=7)
            ax.set_ylabel(r'$\lambda_s$', fontsize=7)
        frame_no = int(z['actual__frame_no']) if 'actual__frame_no' in z else idx - 1
        leg = str(z['actual__leg']) if 'actual__leg' in z else ''
        shift = float(z['actual__shift_fraction']) if 'actual__shift_fraction' in z else float('nan')
        prim = float(z['actual__primary_rpm']) if 'actual__primary_rpm' in z else float('nan')
        sec = float(z['actual__secondary_rpm']) if 'actual__secondary_rpm' in z else float('nan')
        fig.suptitle(
            f'Closure conditioning | frame {frame_no:03d} | {leg} | '
            f'shift={shift:.3f} | primary={prim:.0f} rpm | secondary={sec:.0f} rpm',
            fontsize=11,
        )
        fig.tight_layout(rect=[0, 0, 1, 0.94])
        out_png = frame_dir / f'composite_{frame_no:03d}.png'
        fig.savefig(out_png, dpi=args.dpi)
        plt.close(fig)
        rendered_paths.append(out_png)
        print(f'[{idx:03d}/{len(files):03d}] rendered {out_png.name}')

    gif_path = output_dir / 'closure_full_4x2.gif'
    frames = [Image.open(path).convert('P', palette=Image.ADAPTIVE) for path in rendered_paths]
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], optimize=False,
                   duration=args.duration_ms, loop=0, disposal=2)
    for frame in frames:
        frame.close()
    print(f'Wrote {gif_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
