"""Create focused fixed-torque slice visuals from a multiroot manifold directory.

This is a cleaned-up version of the earlier post-processor. The important fix
is that the selected fixed-torque solution curve is treated as an *open* curve
segment; the script does not wrap the first and last points together.

Required input directory
------------------------
A manifold directory produced by visualize_multiroot_manifold.py, containing:

    candidate.csv
    fixed_other_torque_solution_curve.csv
    inverse_torque_surface.npz

Typical usage from results/cinder-v1.1.2
----------------------------------------

    python .\studies\closure-conditioning\make_fixed_torque_slice_visuals.py `
      --manifold-dir .\studies\closure-conditioning\artifacts\multiroot-manifold-visualization\candidate_01_row_061_static_limited\vary_secondary_torque
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifold-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, default=None)
    p.add_argument('--dpi', type=int, default=190)
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
    if not rows:
        raise RuntimeError(f'No curve rows found in {path}')
    data = np.asarray([
        [float(r['lambda_p']), float(r['lambda_s']), float(r['continued_torque_Nm']), int(r['segment_id']), int(r['point_order'])]
        for r in rows
    ], dtype=float)
    return data


def pick_segment(curve: np.ndarray, root1: np.ndarray, root2: np.ndarray) -> np.ndarray:
    best_seg = None
    best_score = float('inf')
    for seg_id in np.unique(curve[:, 3].astype(int)):
        seg = curve[curve[:, 3].astype(int) == int(seg_id)]
        seg = seg[np.argsort(seg[:, 4])]
        d1 = float(np.min(np.linalg.norm(seg[:, :2] - root1[None, :], axis=1)))
        d2 = float(np.min(np.linalg.norm(seg[:, :2] - root2[None, :], axis=1)))
        score = d1 + d2
        if score < best_score:
            best_score = score
            best_seg = seg
    if best_seg is None:
        raise RuntimeError('Could not select a fixed-torque curve segment.')
    return best_seg


def root_indices(seg: np.ndarray, root1: np.ndarray, root2: np.ndarray) -> tuple[int, int]:
    i1 = int(np.argmin(np.linalg.norm(seg[:, :2] - root1[None, :], axis=1)))
    i2 = int(np.argmin(np.linalg.norm(seg[:, :2] - root2[None, :], axis=1)))
    return (i1, i2) if i1 <= i2 else (i2, i1)


def cumulative_arclength(points: np.ndarray) -> np.ndarray:
    ds = np.linalg.norm(np.diff(points[:, :2], axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(ds)])


def extract_contour_paths(X: np.ndarray, Y: np.ndarray, Z: np.ndarray, level: float) -> list[np.ndarray]:
    fig, ax = plt.subplots()
    cs = ax.contour(X, Y, Z, levels=[level])
    paths: list[np.ndarray] = []
    for seg in cs.allsegs[0]:
        seg = np.asarray(seg, dtype=float)
        if seg.ndim == 2 and len(seg) >= 2:
            paths.append(seg)
    plt.close(fig)
    return paths


def main() -> int:
    args = parse_args()
    mdir = args.manifold_dir.resolve()
    out = args.output_dir.resolve() if args.output_dir else (mdir / 'focused-slice-visuals')
    out.mkdir(parents=True, exist_ok=True)

    cand = read_one_csv(mdir / 'candidate.csv')
    curve = read_curve(mdir / 'fixed_other_torque_solution_curve.csv')
    inv = np.load(mdir / 'inverse_torque_surface.npz')
    lambda_p = inv['lambda_p'].astype(float)
    lambda_s = inv['lambda_s'].astype(float)
    required_Tp = inv['required_Tp'].astype(float)
    required_Ts = inv['required_Ts'].astype(float)
    X, Y = np.meshgrid(lambda_p, lambda_s)

    tp0 = float(cand['refined_Tp_Nm'])
    ts0 = float(cand['refined_Ts_Nm'])
    root1 = np.asarray([float(cand['root1_lambda_p']), float(cand['root1_lambda_s'])], dtype=float)
    root2 = np.asarray([float(cand['root2_lambda_p']), float(cand['root2_lambda_s'])], dtype=float)

    seg = pick_segment(curve, root1, root2)
    i1, i2 = root_indices(seg, root1, root2)
    s = cumulative_arclength(seg)
    s1 = float(s[i1])
    s2 = float(s[i2])
    seg_between = seg[i1:i2+1]
    s_between = s[i1:i2+1] - s[i1]
    ts_between = seg_between[:, 2]
    # Most relevant fold is the extremum between the two roots.
    k_local_max = int(np.argmax(ts_between))
    k_local_min = int(np.argmin(ts_between))
    dmax = abs(float(ts_between[k_local_max]) - ts0)
    dmin = abs(float(ts_between[k_local_min]) - ts0)
    k_local = k_local_max if dmax >= dmin else k_local_min
    fold_point = seg_between[k_local]
    s_fold = float(s_between[k_local] + s[i1])

    fixed_tp_paths = extract_contour_paths(X, Y, required_Tp, tp0)

    # 1) lambda-plane view
    fig, ax = plt.subplots(figsize=(8.4, 7.2), constrained_layout=True)
    pcm = ax.pcolormesh(X, Y, np.ma.masked_invalid(required_Ts), shading='auto', rasterized=True)
    cbar = fig.colorbar(pcm, ax=ax)
    cbar.set_label('Required $T_s$ [Nm]')
    for pth in fixed_tp_paths:
        ax.plot(pth[:, 0], pth[:, 1], color='tab:blue', alpha=0.15, linewidth=1.0)
    ax.plot(seg[:, 0], seg[:, 1], color='tab:blue', linewidth=2.8, label=f'$T_p={tp0:.3f}$ Nm')
    ax.contour(X, Y, required_Ts, levels=[ts0], colors=['tab:orange'], linewidths=2.2, linestyles='--')
    ax.scatter([root1[0], root2[0]], [root1[1], root2[1]], c=['tab:green', 'tab:red'], s=85, zorder=5)
    ax.scatter([fold_point[0]], [fold_point[1]], c=['tab:purple'], marker='^', s=95, zorder=6)
    ax.text(root1[0], root1[1], '  root 1', fontsize=10)
    ax.text(root2[0], root2[1], '  root 2', fontsize=10)
    ax.text(fold_point[0], fold_point[1], '  fold', fontsize=10)
    ax.set_xlabel('$\\lambda_p$')
    ax.set_ylabel('$\\lambda_s$')
    ax.set_title('Two roots as contour intersections in the $\\lambda$-plane')
    ax.grid(True, alpha=0.25)
    ax.legend(loc='upper left')
    fig.savefig(out / 'focused_slice_lambda_plane.png', dpi=args.dpi)
    plt.close(fig)

    # 2) 1D crossing view
    fig, ax = plt.subplots(figsize=(9.0, 4.9), constrained_layout=True)
    ax.plot(s, seg[:, 2], color='tab:blue', linewidth=2.4, label='fixed-$T_p$ solution curve')
    ax.axhline(ts0, color='tab:orange', linestyle='--', linewidth=2.0, label=f'$T_s={ts0:.3f}$ Nm')
    ax.scatter([s1, s2], [ts0, ts0], c=['tab:green', 'tab:red'], s=70)
    ax.scatter([s_fold], [float(fold_point[2])], c=['tab:purple'], marker='^', s=85)
    ax.text(s1, ts0, ' root 1')
    ax.text(s2, ts0, ' root 2')
    ax.text(s_fold, float(fold_point[2]), ' fold')
    ax.set_xlabel('distance along the open fixed-$T_p$ curve')
    ax.set_ylabel('$T_s$ along the curve [Nm]')
    ax.set_title('Why two roots appear: a single folded curve is cut twice by $T_s=T_s^*$')
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.savefig(out / 'focused_slice_1d_crossing.png', dpi=args.dpi)
    plt.close(fig)

    # 3) 3D curve + plane
    fig = plt.figure(figsize=(9.0, 7.8))
    ax = fig.add_subplot(111, projection='3d')
    ax.plot(seg[:, 0], seg[:, 1], seg[:, 2], color='tab:blue', linewidth=3.0)
    ax.scatter([root1[0], root2[0]], [root1[1], root2[1]], [ts0, ts0], c=['tab:green', 'tab:red'], s=90)
    ax.scatter([fold_point[0]], [fold_point[1]], [float(fold_point[2])], c=['tab:purple'], marker='^', s=95)
    xx = np.linspace(float(np.min(seg[:, 0])), float(np.max(seg[:, 0])), 2)
    yy = np.linspace(float(np.min(seg[:, 1])), float(np.max(seg[:, 1])), 2)
    XX, YY = np.meshgrid(xx, yy)
    ZZ = np.full_like(XX, ts0)
    ax.plot_surface(XX, YY, ZZ, alpha=0.16, color='orange')
    ax.set_xlabel('$\\lambda_p$')
    ax.set_ylabel('$\\lambda_s$')
    ax.set_zlabel('$T_s$ [Nm]')
    ax.set_title('Open fixed-$T_p$ slice of the manifold; the plane $T_s=T_s^*$ cuts it twice')
    fig.savefig(out / 'focused_slice_curve_3d.png', dpi=args.dpi, bbox_inches='tight')
    plt.close(fig)

    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<script src='https://cdn.plot.ly/plotly-2.35.2.min.js'></script>
<title>Focused multiroot slice</title></head><body>
<div id='plot' style='width:100%;height:96vh;'></div>
<script>
const curve = {{x:{seg[:,0].tolist()}, y:{seg[:,1].tolist()}, z:{seg[:,2].tolist()}}};
const roots = {{x:[{float(root1[0])},{float(root2[0])}], y:[{float(root1[1])},{float(root2[1])}], z:[{ts0},{ts0}]}};
const fold = {{x:[{float(fold_point[0])}], y:[{float(fold_point[1])}], z:[{float(fold_point[2])}]}};
const xmin = {float(np.min(seg[:,0]))}, xmax = {float(np.max(seg[:,0]))};
const ymin = {float(np.min(seg[:,1]))}, ymax = {float(np.max(seg[:,1]))};
const zplane = {ts0};
const data = [
  {{type:'scatter3d', mode:'lines', x:curve.x, y:curve.y, z:curve.z, line:{{width:7,color:'#1f77b4'}}, name:'fixed T_p curve'}},
  {{type:'scatter3d', mode:'markers+text', x:roots.x, y:roots.y, z:roots.z,
    text:['root 1','root 2'], textposition:'top center', marker:{{size:6,color:['#2ca02c','#d62728']}}, name:'roots'}},
  {{type:'scatter3d', mode:'markers+text', x:fold.x, y:fold.y, z:fold.z,
    text:['fold'], textposition:'bottom center', marker:{{size:7,color:'#9467bd'}}, name:'fold'}},
  {{type:'mesh3d', x:[xmin,xmax,xmax,xmin], y:[ymin,ymin,ymax,ymax], z:[zplane,zplane,zplane,zplane],
    i:[0,0], j:[1,2], k:[2,3], opacity:0.18, color:'#ffbf80', name:'T_s = {ts0:.3f} Nm'}}
];
Plotly.newPlot('plot', data, {{title:'Fix T_p = {tp0:.3f} Nm; the plane T_s = {ts0:.3f} Nm cuts the open curve twice',
scene:{{xaxis:{{title:'lambda_p'}}, yaxis:{{title:'lambda_s'}}, zaxis:{{title:'T_s [Nm]'}}}}}}, {{responsive:true}});
</script></body></html>"""
    (out / 'focused_slice_curve_3d.html').write_text(html, encoding='utf-8')

    manifest = {
        'source_manifold_dir': str(mdir),
        'fixed_torque_name': 'T_p',
        'fixed_torque_value_Nm': tp0,
        'other_torque_name': 'T_s',
        'other_torque_value_Nm': ts0,
        'root1_index': i1,
        'root2_index': i2,
        'fold_index_between_roots': int(i1 + k_local),
        'root1': root1.tolist(),
        'root2': root2.tolist(),
        'fold_point': [float(fold_point[0]), float(fold_point[1]), float(fold_point[2])],
        'files': [
            'focused_slice_lambda_plane.png',
            'focused_slice_1d_crossing.png',
            'focused_slice_curve_3d.png',
            'focused_slice_curve_3d.html',
        ],
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
