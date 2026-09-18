"""Render a compact multiroot story GIF from one manifold directory.

The GIF has three panels:
  1) the lambda-plane fixed-Tp contour and moving Ts contour,
  2) the 1D folded-curve view with a moving horizontal line,
  3) the 3D open curve with a moving reference plane.

The sweep is chosen around the extremum between the two roots, so the GIF
shows the appearance or disappearance of the second root cleanly.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifold-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, default=None)
    p.add_argument('--frames', type=int, default=72)
    p.add_argument('--fps', type=int, default=12)
    p.add_argument('--jobs', type=int, default=1)
    p.add_argument('--dpi', type=int, default=130)
    p.add_argument('--sweep-padding-Nm', type=float, default=1.0,
                   help='Extra torque padding above/below the local fold and root level.')
    return p.parse_args()


def read_one_csv(path: Path) -> dict[str, Any]:
    with path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError(f'No rows found in {path}')
    return rows[0]


def read_curve(path: Path) -> np.ndarray:
    with path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    return np.asarray([
        [float(r['lambda_p']), float(r['lambda_s']), float(r['continued_torque_Nm']), int(r['segment_id']), int(r['point_order'])]
        for r in rows
    ], dtype=float)


def load_story_data(mdir: Path) -> dict[str, Any]:
    cand = read_one_csv(mdir / 'candidate.csv')
    curve = read_curve(mdir / 'fixed_other_torque_solution_curve.csv')
    inv = np.load(mdir / 'inverse_torque_surface.npz')
    X, Y = np.meshgrid(inv['lambda_p'].astype(float), inv['lambda_s'].astype(float))
    required_Tp = inv['required_Tp'].astype(float)
    required_Ts = inv['required_Ts'].astype(float)
    tp0 = float(cand['refined_Tp_Nm'])
    ts0 = float(cand['refined_Ts_Nm'])
    root1 = np.asarray([float(cand['root1_lambda_p']), float(cand['root1_lambda_s'])], dtype=float)
    root2 = np.asarray([float(cand['root2_lambda_p']), float(cand['root2_lambda_s'])], dtype=float)

    # Pick the segment nearest both roots.
    best_seg = None
    best_score = float('inf')
    for seg_id in np.unique(curve[:, 3].astype(int)):
        seg = curve[curve[:, 3].astype(int) == int(seg_id)]
        seg = seg[np.argsort(seg[:, 4])]
        score = float(np.min(np.linalg.norm(seg[:, :2] - root1[None, :], axis=1))
                      + np.min(np.linalg.norm(seg[:, :2] - root2[None, :], axis=1)))
        if score < best_score:
            best_score = score
            best_seg = seg
    if best_seg is None:
        raise RuntimeError('Could not choose curve segment.')
    seg = best_seg
    i1 = int(np.argmin(np.linalg.norm(seg[:, :2] - root1[None, :], axis=1)))
    i2 = int(np.argmin(np.linalg.norm(seg[:, :2] - root2[None, :], axis=1)))
    if i1 > i2:
        i1, i2 = i2, i1
        root1, root2 = root2, root1
    ds = np.linalg.norm(np.diff(seg[:, :2], axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(ds)])
    between = seg[i1:i2+1]
    ts_between = between[:, 2]
    kmax = int(np.argmax(ts_between))
    kmin = int(np.argmin(ts_between))
    use_max = abs(float(ts_between[kmax]) - ts0) >= abs(float(ts_between[kmin]) - ts0)
    k_local = (i1 + kmax) if use_max else (i1 + kmin)
    local_kind = 'max' if use_max else 'min'
    fold_ts = float(seg[k_local, 2])
    # sweep around the local turning point, with actual root level included.
    lo = min(ts0, fold_ts) - 1.0
    hi = max(ts0, fold_ts) + 1.0
    # contour paths for fixed Tp
    fig, ax = plt.subplots()
    cs = ax.contour(X, Y, required_Tp, levels=[tp0])
    paths = [np.asarray(ss, dtype=float) for ss in cs.allsegs[0] if len(ss) >= 2]
    plt.close(fig)
    # pick path nearest chosen segment just for faint background if needed.
    return {
        'tp0': tp0, 'ts0': ts0,
        'root1': root1, 'root2': root2,
        'seg': seg, 's': s,
        'i1': i1, 'i2': i2,
        'k_local': k_local, 'fold_ts': fold_ts, 'local_kind': local_kind,
        'X': X, 'Y': Y, 'required_Tp': required_Tp, 'required_Ts': required_Ts,
        'fixed_tp_paths': paths, 'sweep_lo': lo, 'sweep_hi': hi,
    }


def intersections_along_curve(seg: np.ndarray, target: float) -> list[np.ndarray]:
    z = seg[:, 2] - float(target)
    hits: list[np.ndarray] = []
    for i in range(len(seg) - 1):
        z0 = float(z[i]); z1 = float(z[i+1])
        if z0 == 0.0:
            hits.append(seg[i, :3].copy())
        if z0 == 0.0 and z1 == 0.0:
            continue
        if z0 == 0.0 or z1 == 0.0 or (z0 < 0.0 and z1 > 0.0) or (z0 > 0.0 and z1 < 0.0):
            denom = (z1 - z0)
            t = 0.0 if denom == 0.0 else (-z0 / denom)
            t = float(np.clip(t, 0.0, 1.0))
            p = seg[i, :3] + t * (seg[i+1, :3] - seg[i, :3])
            hits.append(p)
    # deduplicate nearby hits.
    unique: list[np.ndarray] = []
    for p in hits:
        if not unique or min(float(np.linalg.norm(p[:2] - q[:2])) for q in unique) > 1.0e-6:
            unique.append(p)
    return unique


def frame_values(lo: float, hi: float, n: int) -> np.ndarray:
    half = max(2, n // 2)
    up = np.linspace(hi, lo, half, endpoint=False)
    down = np.linspace(lo, hi, n - half)
    return np.concatenate([up, down])


def render_one_frame(idx: int, q: float, data: dict[str, Any], outpath: Path, dpi: int) -> None:
    seg = data['seg']
    s = data['s']
    root1, root2 = data['root1'], data['root2']
    tp0, ts0 = data['tp0'], data['ts0']
    X, Y = data['X'], data['Y']
    required_Ts = data['required_Ts']
    hits = intersections_along_curve(seg, q)
    # parameter positions for hits (nearest on polyline)
    hit_s = []
    for h in hits:
        j = int(np.argmin(np.linalg.norm(seg[:, :2] - h[:2][None, :], axis=1)))
        hit_s.append(float(s[j]))

    fig = plt.figure(figsize=(14.5, 4.8), constrained_layout=True)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.1, 1.0, 1.15])

    # Panel 1: lambda-plane
    ax1 = fig.add_subplot(gs[0, 0])
    pcm = ax1.pcolormesh(X, Y, np.ma.masked_invalid(required_Ts), shading='auto', rasterized=True)
    for pth in data['fixed_tp_paths']:
        ax1.plot(pth[:, 0], pth[:, 1], color='tab:blue', alpha=0.12, linewidth=1.0)
    ax1.plot(seg[:, 0], seg[:, 1], color='tab:blue', linewidth=2.6)
    ax1.contour(X, Y, required_Ts, levels=[q], colors=['tab:orange'], linewidths=2.0, linestyles='--')
    ax1.scatter([root1[0], root2[0]], [root1[1], root2[1]], c=['tab:green', 'tab:red'], s=40, alpha=0.45)
    if hits:
        ax1.scatter([h[0] for h in hits], [h[1] for h in hits], c='black', s=85, marker='o', zorder=6)
    ax1.set_title(f'$\\lambda$-plane\ncurrent $T_s={q:.2f}$ Nm')
    ax1.set_xlabel('$\\lambda_p$'); ax1.set_ylabel('$\\lambda_s$'); ax1.grid(True, alpha=0.25)

    # Panel 2: 1D curve
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(s, seg[:, 2], color='tab:blue', linewidth=2.3)
    ax2.axhline(q, color='tab:orange', linestyle='--', linewidth=2.0)
    ax2.axhline(ts0, color='0.55', linestyle=':', linewidth=1.5)
    if hit_s:
        ax2.scatter(hit_s, [q]*len(hit_s), c='black', s=70, zorder=5)
    ax2.set_title('1D folded-curve view')
    ax2.set_xlabel('distance along open fixed-$T_p$ curve')
    ax2.set_ylabel('$T_s$ [Nm]')
    ax2.grid(True, alpha=0.25)
    ax2.text(0.02, 0.97,
             f'black dots = current roots\ngray dotted = original $T_s^*$ = {ts0:.2f} Nm\n# roots now = {len(hit_s)}',
             transform=ax2.transAxes, va='top', ha='left', fontsize=9,
             bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='0.85', alpha=0.92))

    # Panel 3: 3D
    ax3 = fig.add_subplot(gs[0, 2], projection='3d')
    ax3.plot(seg[:, 0], seg[:, 1], seg[:, 2], color='tab:blue', linewidth=2.4)
    if hits:
        ax3.scatter([h[0] for h in hits], [h[1] for h in hits], [h[2] for h in hits], c='black', s=35)
    xx = np.linspace(float(np.min(seg[:, 0])), float(np.max(seg[:, 0])), 2)
    yy = np.linspace(float(np.min(seg[:, 1])), float(np.max(seg[:, 1])), 2)
    XX, YY = np.meshgrid(xx, yy)
    ZZ = np.full_like(XX, q)
    ax3.plot_surface(XX, YY, ZZ, alpha=0.18, color='orange')
    ax3.set_title('3D open curve + moving $T_s$ plane')
    ax3.set_xlabel('$\\lambda_p$'); ax3.set_ylabel('$\\lambda_s$'); ax3.set_zlabel('$T_s$ [Nm]')
    ax3.view_init(elev=24, azim=-58)

    fig.suptitle(f'Multiroot story sweep | fixed $T_p={tp0:.2f}$ Nm | frame {idx+1}', fontsize=14)
    fig.savefig(outpath, dpi=dpi)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    mdir = args.manifold_dir.resolve()
    out = args.output_dir.resolve() if args.output_dir else (mdir / 'story-gif')
    out.mkdir(parents=True, exist_ok=True)
    data = load_story_data(mdir)
    values = frame_values(float(data['sweep_lo']), float(data['sweep_hi']), int(args.frames))
    frame_dir = out / 'frames'
    frame_dir.mkdir(parents=True, exist_ok=True)

    tasks = [(i, float(q), data, frame_dir / f'frame_{i:03d}.png', int(args.dpi)) for i, q in enumerate(values)]
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=int(args.jobs)) as ex:
            futures = [ex.submit(render_one_frame, *t) for t in tasks]
            for fut in futures:
                fut.result()
    else:
        for t in tasks:
            render_one_frame(*t)

    images = [Image.open(frame_dir / f'frame_{i:03d}.png').convert('P', palette=Image.ADAPTIVE) for i in range(len(tasks))]
    gif_path = out / 'multiroot_story.gif'
    images[0].save(gif_path, save_all=True, append_images=images[1:], duration=int(1000 / max(1, args.fps)), loop=0, disposal=2)

    manifest = {
        'source_manifold_dir': str(mdir),
        'frames': int(args.frames),
        'fps': int(args.fps),
        'sweep_lo': float(data['sweep_lo']),
        'sweep_hi': float(data['sweep_hi']),
        'fold_ts': float(data['fold_ts']),
        'original_ts': float(data['ts0']),
        'root_count_at_original_ts': 2,
        'gif': str(gif_path),
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
