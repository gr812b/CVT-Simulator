r"""Visualize the multiroot stick-stick closure manifold in 3D / projected 4D.

Purpose
-------
The continuation study showed that, for a frozen engaged state, the two apparent
stick-stick roots at a fixed torque can be understood geometrically as a folded
solution manifold.  This script generates the actual data and plots needed to
see that geometry.

For a selected continuation case (for example the `vary_secondary_torque`
results from `analysis/continue_multiroot_branches.py`), it reconstructs the same frozen
state and then:

1. builds a 3D scalar volume over

       (lambda_p, lambda_s, q)

   where q is the varied boundary torque (Tp or Ts),
   and stores the fields

       R_p(lambda_p, lambda_s, q)
       R_s(lambda_p, lambda_s, q)

   so the zero-isosurfaces can be visualized directly;

2. overlays the two continued root branches from the continuation study,
   showing how they lie on the common zero-surface intersection curve;

3. saves several 2D slices at representative torque levels;

4. builds a 4D-like projection of the frozen-state solution manifold parameterized by

       (lambda_p, lambda_s) -> (T_p_required, T_s_required),

   and saves both raw arrays and projection plots.

The resulting files are deliberately redundant: NPZ arrays, CSV metadata, HTML
interactive plots (when Plotly is available), and plain PNG/PDF figures.  That
way the outputs can be inspected locally and can also be re-used later to make
cleaner figures.

Typical usage
-------------
From results/cinder-v1.1.2:

    python .\studies\closure-conditioning\analysis/visualize_multiroot_manifold.py `
      --continuation-dir .\studies\closure-conditioning\artifacts\multiroot-branch-continuation\candidate_01_row_061_static_limited\vary_secondary_torque `
      --reference-path-csv .\studies\closure-conditioning\artifacts\controlled-free-shift-animation\expanded_res641_locked_locked_path\preflight_path.csv `
      --reference-frame 60

The continuation directory must contain:

    branch_A.csv
    branch_B.csv

and its parent directory must contain:

    candidate.csv

The script automatically infers whether the continuation parameter is primary or
secondary torque from the directory name.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.patches import Rectangle
import numpy as np
from scipy.interpolate import RegularGridInterpolator

import run as cc_run
import animate_controlled_free_shift_path as controlled
import global_comfortable_multiroot_search as global_search
import continue_multiroot_branches as cont


HERE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = HERE / 'artifacts' / 'multiroot-manifold-visualization'


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--continuation-dir', type=Path, required=True,
                   help='Directory containing branch_A.csv and branch_B.csv from analysis/continue_multiroot_branches.py.')
    p.add_argument('--reference-path-csv', type=Path, required=True,
                   help='Known-good locked path, used only to obtain a FREE/STICK_STICK mode object.')
    p.add_argument('--reference-frame', type=int, default=60)
    p.add_argument('--output-dir', type=Path, default=None)
    p.add_argument('--recompute', action='store_true',
                   help='Recompute cached NPZ fields even if they already exist in the output directory.')

    # 3D volume around the continuation curve.
    p.add_argument('--lambda-grid', type=int, default=101)
    p.add_argument('--torque-grid', type=int, default=121)
    p.add_argument('--lambda-padding', type=float, default=0.08,
                   help='Padding added around the branch-extrema box in both lambda directions.')
    p.add_argument('--torque-padding-Nm', type=float, default=5.0,
                   help='Padding added around the branch torque span.')
    p.add_argument('--torque-limit-Nm', type=float, default=999.0,
                   help='Additional hard clamp on torque extent, centered about the initial continuation torque.')

    # Optional inverse-torque surface (2D manifold in 4D) settings.
    p.add_argument('--inverse-resolution', type=int, default=161,
                   help='Grid resolution in the physical static lambda box for the inverse torque manifold.')
    p.add_argument('--concept-html-max-points', type=int, default=1200,
                   help='Maximum points retained per extracted solution-curve segment in the standalone interactive HTML.')
    p.add_argument('--torque-basis-step', type=float, default=1.0)
    p.add_argument('--torque-limit-for-inverse', type=float, default=400.0)
    p.add_argument('--max-torque-gain-condition', type=float, default=1.0e7)
    return p.parse_args()


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def vary_from_dir(path: Path) -> str:
    name = path.name.lower()
    if 'primary' in name:
        return 'primary'
    if 'secondary' in name:
        return 'secondary'
    raise ValueError(f'Could not infer varied torque from directory name: {path}')


def to_float_array(rows: list[dict[str, Any]], key: str) -> np.ndarray:
    return np.asarray([float(r[key]) for r in rows], dtype=float)


def load_case(args: argparse.Namespace):
    cont_dir = args.continuation_dir.resolve()
    parent = cont_dir.parent
    a_path = cont_dir / 'branch_A.csv'
    b_path = cont_dir / 'branch_B.csv'
    candidate_path = parent / 'candidate.csv'
    if not a_path.exists() or not b_path.exists() or not candidate_path.exists():
        raise FileNotFoundError(
            'Expected branch_A.csv, branch_B.csv in continuation-dir and candidate.csv in its parent.'
        )

    rows_a = read_csv_rows(a_path)
    rows_b = read_csv_rows(b_path)
    candidate_rows = read_csv_rows(candidate_path)
    if len(candidate_rows) != 1:
        raise ValueError(f'Expected exactly one candidate row in {candidate_path}')
    candidate = candidate_rows[0]
    vary = vary_from_dir(cont_dir)
    return cont_dir, parent, candidate, rows_a, rows_b, vary


def build_problem(candidate: dict[str, Any], vary: str, args: argparse.Namespace):
    decoded, library = controlled.load_base()
    reference_mode = global_search.reference_mode_from_path(
        decoded, library, args.reference_path_csv.resolve(), int(args.reference_frame)
    )
    recipe = global_search.rebuild_recipe_from_candidate(candidate)
    problem = cont.FrozenTorqueContinuation(
        decoded=decoded,
        library=library,
        reference_mode=reference_mode,
        recipe=recipe,
        tp0=float(candidate['refined_Tp_Nm']),
        ts0=float(candidate['refined_Ts_Nm']),
        vary=vary,
        q_scale=50.0,
        basis_step=float(args.torque_basis_step),
    )
    return decoded, library, reference_mode, recipe, problem


def compute_volume(problem: cont.FrozenTorqueContinuation, rows_a, rows_b, args: argparse.Namespace):
    lp_all = np.concatenate((to_float_array(rows_a, 'lambda_p'), to_float_array(rows_b, 'lambda_p')))
    ls_all = np.concatenate((to_float_array(rows_a, 'lambda_s'), to_float_array(rows_b, 'lambda_s')))
    q_all = np.concatenate((to_float_array(rows_a, 'continued_torque_Nm'), to_float_array(rows_b, 'continued_torque_Nm')))

    lp_min = float(np.min(lp_all) - args.lambda_padding)
    lp_max = float(np.max(lp_all) + args.lambda_padding)
    ls_min = float(np.min(ls_all) - args.lambda_padding)
    ls_max = float(np.max(ls_all) + args.lambda_padding)
    q_min = float(np.min(q_all) - args.torque_padding_Nm)
    q_max = float(np.max(q_all) + args.torque_padding_Nm)

    if math.isfinite(args.torque_limit_Nm) and args.torque_limit_Nm > 0.0:
        q_min = max(q_min, problem.q0 - float(args.torque_limit_Nm))
        q_max = min(q_max, problem.q0 + float(args.torque_limit_Nm))

    lp_axis = np.linspace(lp_min, lp_max, int(args.lambda_grid))
    ls_axis = np.linspace(ls_min, ls_max, int(args.lambda_grid))
    q_axis = np.linspace(q_min, q_max, int(args.torque_grid))

    Rp = np.empty((len(q_axis), len(ls_axis), len(lp_axis)), dtype=float)
    Rs = np.empty_like(Rp)
    Rn = np.empty_like(Rp)

    for iq, q in enumerate(q_axis):
        for is_, ls in enumerate(ls_axis):
            for ip, lp in enumerate(lp_axis):
                r = problem.residual(float(lp), float(ls), float(q))
                Rp[iq, is_, ip] = float(r[0])
                Rs[iq, is_, ip] = float(r[1])
                Rn[iq, is_, ip] = float(np.linalg.norm(r))

    return {
        'lambda_p': lp_axis,
        'lambda_s': ls_axis,
        'q_axis': q_axis,
        'R_p': Rp,
        'R_s': Rs,
        'R_norm': Rn,
        'q_name': problem.q_name,
        'q0': float(problem.q0),
        'vary': problem.vary,
    }


def save_volume_npz(path: Path, volume: dict[str, Any]) -> None:
    arrays = {k: v for k, v in volume.items() if isinstance(v, np.ndarray)}
    arrays['q0'] = np.asarray(volume['q0'])
    arrays['vary'] = np.asarray(volume['vary'])
    arrays['q_name'] = np.asarray(volume['q_name'])
    np.savez_compressed(path, **arrays)


def load_volume_npz(path: Path) -> dict[str, Any]:
    with np.load(path, allow_pickle=False) as data:
        out = {key: np.asarray(data[key]) for key in data.files}
    out['q0'] = float(np.asarray(out['q0']).item())
    out['vary'] = str(np.asarray(out['vary']).item())
    out['q_name'] = str(np.asarray(out['q_name']).item())
    return out


def representative_q_values(rows_a, rows_b, q0: float) -> list[tuple[str, float]]:
    qa = to_float_array(rows_a, 'continued_torque_Nm')
    qb = to_float_array(rows_b, 'continued_torque_Nm')
    out = [('initial', float(q0))]
    # common high-torque turning point approx = maximum of combined curve.
    q_fold = float(max(np.max(qa), np.max(qb)))
    out.append(('near_fold', q_fold))

    # First point where branch B becomes inadmissible.
    for label_rows, lbl in [(rows_b, 'branchB_first_inadmissible'), (rows_a, 'branchA_first_inadmissible')]:
        for r in label_rows:
            if str(r.get('physical', 'False')).lower() != 'true':
                out.append((lbl, float(r['continued_torque_Nm'])))
                break
    # remove duplicates within tolerance
    unique: list[tuple[str, float]] = []
    for name, q in out:
        if not any(abs(q - q2) < 1.0e-8 for _, q2 in unique):
            unique.append((name, q))
    return unique


def nearest_index(values: np.ndarray, target: float) -> int:
    return int(np.argmin(np.abs(np.asarray(values, dtype=float) - float(target))))


def branch_points_near_q(rows: list[dict[str, Any]], q_target: float, tol: float) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if abs(float(r['continued_torque_Nm']) - q_target) <= tol:
            out.append(r)
    return out


def contour_slice_plot(volume: dict[str, Any], rows_a, rows_b, q_label: str, q_target: float, path: Path) -> None:
    lp = volume['lambda_p']
    ls = volume['lambda_s']
    iq = nearest_index(volume['q_axis'], q_target)
    q_used = float(volume['q_axis'][iq])
    Rp = volume['R_p'][iq]
    Rs = volume['R_s'][iq]
    Rn = volume['R_norm'][iq]

    LP, LS = np.meshgrid(lp, ls)
    fig, ax = plt.subplots(figsize=(8.0, 7.0), constrained_layout=True)
    vmin = max(float(np.nanpercentile(Rn[Rn > 0], 2)) if np.any(Rn > 0) else 1.0e-8, 1.0e-8)
    vmax = max(float(np.nanpercentile(Rn, 99.5)), vmin * 1.01)
    pcm = ax.pcolormesh(LP, LS, Rn, shading='auto', norm=LogNorm(vmin=vmin, vmax=vmax), rasterized=True)
    fig.colorbar(pcm, ax=ax, shrink=0.84, label='||R||')
    try:
        ax.contour(LP, LS, Rp, levels=[0.0], colors='black', linewidths=1.4)
    except ValueError:
        pass
    try:
        ax.contour(LP, LS, Rs, levels=[0.0], colors='cyan', linewidths=1.4, linestyles='--')
    except ValueError:
        pass

    law = problem.base_bundle.system.cvt.traction_law  # type: ignore[name-defined]
    p0, p1 = law.primary_static_interval.lower, law.primary_static_interval.upper
    s0, s1 = law.secondary_static_interval.lower, law.secondary_static_interval.upper
    ax.add_patch(Rectangle((p0, s0), p1-p0, s1-s0, fill=False, linestyle=':', linewidth=1.2))

    tol = 0.35 * (volume['q_axis'][1] - volume['q_axis'][0]) if len(volume['q_axis']) > 1 else 1.0e-6
    for label, rows, color in [('A', rows_a, 'tab:green'), ('B', rows_b, 'tab:orange')]:
        pts = branch_points_near_q(rows, q_used, tol)
        if pts:
            xs = [float(r['lambda_p']) for r in pts]
            ys = [float(r['lambda_s']) for r in pts]
            marker = ['o' if str(r.get('physical', 'False')).lower() == 'true' else 'x' for r in pts]
            for x, y, m in zip(xs, ys, marker):
                ax.scatter([x], [y], c=color, s=55, marker=m)
                ax.text(x, y, f' {label}', color=color, fontsize=8)

    ax.set_xlabel(r'$\lambda_p$')
    ax.set_ylabel(r'$\lambda_s$')
    ax.set_title(
        f"Slice: {problem.q_name} = {q_used:.3f} Nm ({q_label})\n"  # type: ignore[name-defined]
        'Black: $R_p=0$, cyan dashed: $R_s=0$, dotted box: static-friction box'
    )
    ax.grid(True, alpha=0.25)
    fig.savefig(path, dpi=190)
    plt.close(fig)


def save_slice_bundle(volume: dict[str, Any], rows_a, rows_b, outdir: Path) -> list[dict[str, Any]]:
    info = []
    for label, q in representative_q_values(rows_a, rows_b, volume['q0']):
        png_path = outdir / f'slice_{label}.png'
        contour_slice_plot(volume, rows_a, rows_b, label, q, png_path)
        info.append({'label': label, 'requested_q': q, 'file': png_path.name})
    return info


def maybe_make_plotly_zero_surface(volume: dict[str, Any], rows_a, rows_b, outpath: Path) -> dict[str, Any]:
    try:
        import plotly.graph_objects as go
    except Exception as exc:
        return {'made_plotly_zero_surface': False, 'reason': f'{type(exc).__name__}: {exc}'}

    # The stored residual volume is ordered (q, lambda_s, lambda_p).  Build
    # coordinates in exactly that order so every scalar value lands at the
    # correct 3D location.
    QQ, LS, LP = np.meshgrid(
        volume['q_axis'], volume['lambda_s'], volume['lambda_p'], indexing='ij'
    )
    x = LP.ravel()
    y = LS.ravel()
    z = QQ.ravel()
    val_p = volume['R_p'].ravel()
    val_s = volume['R_s'].ravel()

    fig = go.Figure()
    fig.add_trace(go.Isosurface(
        x=x, y=y, z=z, value=val_p,
        isomin=0.0, isomax=0.0, surface_count=1,
        opacity=0.25, caps=dict(x_show=False, y_show=False, z_show=False),
        colorscale='Reds', name='R_p = 0', showscale=False,
    ))
    fig.add_trace(go.Isosurface(
        x=x, y=y, z=z, value=val_s,
        isomin=0.0, isomax=0.0, surface_count=1,
        opacity=0.25, caps=dict(x_show=False, y_show=False, z_show=False),
        colorscale='Blues', name='R_s = 0', showscale=False,
    ))

    for label, rows, color in [('A', rows_a, 'green'), ('B', rows_b, 'orange')]:
        fig.add_trace(go.Scatter3d(
            x=[float(r['lambda_p']) for r in rows],
            y=[float(r['lambda_s']) for r in rows],
            z=[float(r['continued_torque_Nm']) for r in rows],
            mode='lines+markers',
            marker=dict(size=3, color=color),
            line=dict(color=color, width=6),
            name=f'branch {label}',
        ))

    # Constant-torque plane at q0.
    lp0, lp1 = float(np.min(volume['lambda_p'])), float(np.max(volume['lambda_p']))
    ls0, ls1 = float(np.min(volume['lambda_s'])), float(np.max(volume['lambda_s']))
    fig.add_trace(go.Mesh3d(
        x=[lp0, lp1, lp1, lp0],
        y=[ls0, ls0, ls1, ls1],
        z=[float(volume['q0'])] * 4,
        i=[0, 0], j=[1, 2], k=[2, 3],
        opacity=0.10,
        color='gray',
        name=f"{volume['q_name']} = {float(volume['q0']):.3f} Nm",
        showscale=False,
    ))

    fig.update_layout(
        title=(
            '3D closure geometry: two zero-surfaces and their common intersection curve'
            f"<br>x=λ_p, y=λ_s, z={volume['q_name']}"
        ),
        scene=dict(
            xaxis_title='lambda_p',
            yaxis_title='lambda_s',
            zaxis_title=volume['q_name'] + ' [Nm]',
        ),
        legend=dict(itemsizing='constant'),
    )
    fig.write_html(str(outpath), include_plotlyjs='cdn')
    return {'made_plotly_zero_surface': True, 'file': outpath.name}


def inverse_surface_data(decoded, library, reference_mode, candidate, args):
    recipe = global_search.rebuild_recipe_from_candidate(candidate)
    cfg = {
        'explore_resolution': int(args.inverse_resolution),
        'torque_basis_step': float(args.torque_basis_step),
        'torque_limit': float(args.torque_limit_for_inverse),
        'max_torque_gain_condition': float(args.max_torque_gain_condition),
        'max_secondary_rpm': 1.0e9,
        'max_belt_speed_m_s': 1.0e9,
    }
    inv, _ = global_search.inverse_map(decoded, library, recipe, reference_mode, cfg)
    if inv is None:
        raise RuntimeError('Inverse-torque map construction returned None.')
    return inv


def save_inverse_npz(path: Path, inv: dict[str, Any]) -> None:
    np.savez_compressed(path, **{k: v for k, v in inv.items() if isinstance(v, np.ndarray)})


def load_inverse_npz(path: Path) -> dict[str, Any]:
    with np.load(path, allow_pickle=False) as data:
        return {key: np.asarray(data[key]) for key in data.files}


def volume_matches_requested_grid(volume: dict[str, Any], args: argparse.Namespace) -> bool:
    return bool(
        len(np.asarray(volume['lambda_p'])) == int(args.lambda_grid)
        and len(np.asarray(volume['lambda_s'])) == int(args.lambda_grid)
        and len(np.asarray(volume['q_axis'])) == int(args.torque_grid)
    )


def inverse_matches_requested_grid(inv: dict[str, Any], args: argparse.Namespace) -> bool:
    return bool(
        len(np.asarray(inv['lambda_p'])) == int(args.inverse_resolution)
        and len(np.asarray(inv['lambda_s'])) == int(args.inverse_resolution)
    )


def plot_inverse_projections(inv: dict[str, Any], outdir: Path, candidate: dict[str, Any], vary: str) -> list[str]:
    lp = inv['lambda_p']
    ls = inv['lambda_s']
    Tp = np.asarray(inv['required_Tp'], dtype=float)
    Ts = np.asarray(inv['required_Ts'], dtype=float)
    valid = np.isfinite(Tp) & np.isfinite(Ts)
    LP, LS = np.meshgrid(lp, ls)
    Tp0 = float(candidate['refined_Tp_Nm'])
    Ts0 = float(candidate['refined_Ts_Nm'])
    root1 = (float(candidate['root1_lambda_p']), float(candidate['root1_lambda_s']))
    root2 = (float(candidate['root2_lambda_p']), float(candidate['root2_lambda_s']))

    outputs: list[str] = []

    def scatter3d(x, y, z, c, xlabel, ylabel, zlabel, cbar_label, title, fname,
                  reference_plane_z=None, reference_roots=None):
        fig = plt.figure(figsize=(9.2, 7.8))
        ax = fig.add_subplot(111, projection='3d')
        sc = ax.scatter(x, y, z, c=c, s=8, alpha=0.82)
        if reference_plane_z is not None:
            xx = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), 2)
            yy = np.linspace(float(np.nanmin(y)), float(np.nanmax(y)), 2)
            XX, YY = np.meshgrid(xx, yy)
            ZZ = np.full_like(XX, float(reference_plane_z))
            ax.plot_surface(XX, YY, ZZ, alpha=0.16, linewidth=0.0)
        if reference_roots:
            for label, rx, ry, rz in reference_roots:
                ax.scatter([rx], [ry], [rz], s=85, marker='o')
                ax.text(rx, ry, rz, f' {label}')
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_zlabel(zlabel)
        ax.set_title(title)
        cbar = fig.colorbar(sc, ax=ax, shrink=0.7)
        cbar.set_label(cbar_label)
        path = outdir / fname
        fig.savefig(path, dpi=190, bbox_inches='tight')
        plt.close(fig)
        outputs.append(fname)

    scatter3d(
        LP[valid], LS[valid], Ts[valid], Tp[valid],
        r'$\lambda_p$', r'$\lambda_s$', r'$T_s$ [Nm]',
        r'$T_p$ [Nm]',
        'Projected 4D manifold: (lambda_p, lambda_s, T_s) colored by T_p',
        'inverse_projection_lambda_lambda_Ts_colored_Tp.png',
        reference_plane_z=Ts0 if vary == 'secondary' else None,
        reference_roots=[
            ('root 1', root1[0], root1[1], Ts0),
            ('root 2', root2[0], root2[1], Ts0),
        ] if vary == 'secondary' else None,
    )
    scatter3d(
        Tp[valid], Ts[valid], LS[valid], LP[valid],
        r'$T_p$ [Nm]', r'$T_s$ [Nm]', r'$\lambda_s$',
        r'$\lambda_p$',
        'Projected 4D manifold: (T_p, T_s, lambda_s) colored by lambda_p',
        'inverse_projection_Tp_Ts_lambdas_colored_lambdap.png',
    )
    scatter3d(
        Tp[valid], Ts[valid], LP[valid], LS[valid],
        r'$T_p$ [Nm]', r'$T_s$ [Nm]', r'$\lambda_p$',
        r'$\lambda_s$',
        'Projected 4D manifold: (T_p, T_s, lambda_p) colored by lambda_s',
        'inverse_projection_Tp_Ts_lambdap_colored_lambdas.png',
    )

    # Heatmaps of the two required torques over lambda-space.
    for field, title, fname in [
        ('required_Tp', 'Required T_p over the lambda grid', 'inverse_required_Tp_heatmap.png'),
        ('required_Ts', 'Required T_s over the lambda grid', 'inverse_required_Ts_heatmap.png'),
    ]:
        values = np.asarray(inv[field], dtype=float)
        fig, ax = plt.subplots(figsize=(7.6, 6.8), constrained_layout=True)
        pcm = ax.pcolormesh(LP, LS, np.ma.masked_invalid(values), shading='auto', rasterized=True)
        fig.colorbar(pcm, ax=ax)
        ax.set_xlabel(r'$\lambda_p$')
        ax.set_ylabel(r'$\lambda_s$')
        ax.set_title(title)
        fig.savefig(outdir / fname, dpi=185)
        plt.close(fig)
        outputs.append(fname)

    return outputs


def plot_continuation_reference_plane_3d(
    rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]],
    candidate: dict[str, Any], vary: str, outpath: Path
) -> None:
    """Plot the exact pseudo-arclength traces with the original torque slice plane."""
    fig = plt.figure(figsize=(9.6, 8.4))
    ax = fig.add_subplot(111, projection='3d')
    for label, rows in [('A', rows_a), ('B', rows_b)]:
        lp = np.asarray([float(r['lambda_p']) for r in rows])
        ls = np.asarray([float(r['lambda_s']) for r in rows])
        q = np.asarray([float(r['continued_torque_Nm']) for r in rows])
        ax.plot(lp, ls, q, linewidth=2.4, label=f'continuation from root {label}')
        bad = np.asarray([str(r.get('physical', 'False')).lower() != 'true' for r in rows])
        if np.any(bad):
            ax.scatter(lp[bad], ls[bad], q[bad], s=11, marker='x', alpha=0.65)

    q0 = float(candidate['refined_Ts_Nm'] if vary == 'secondary' else candidate['refined_Tp_Nm'])
    lp_all = np.concatenate([
        np.asarray([float(r['lambda_p']) for r in rows_a]),
        np.asarray([float(r['lambda_p']) for r in rows_b]),
    ])
    ls_all = np.concatenate([
        np.asarray([float(r['lambda_s']) for r in rows_a]),
        np.asarray([float(r['lambda_s']) for r in rows_b]),
    ])
    padp = max(0.01, 0.05 * (float(np.max(lp_all)) - float(np.min(lp_all))))
    pads = max(0.01, 0.05 * (float(np.max(ls_all)) - float(np.min(ls_all))))
    xx = np.linspace(float(np.min(lp_all))-padp, float(np.max(lp_all))+padp, 2)
    yy = np.linspace(float(np.min(ls_all))-pads, float(np.max(ls_all))+pads, 2)
    XX, YY = np.meshgrid(xx, yy)
    ZZ = np.full_like(XX, q0)
    ax.plot_surface(XX, YY, ZZ, alpha=0.18, linewidth=0.0)

    for label, rp, rs in [
        ('root 1', float(candidate['root1_lambda_p']), float(candidate['root1_lambda_s'])),
        ('root 2', float(candidate['root2_lambda_p']), float(candidate['root2_lambda_s'])),
    ]:
        ax.scatter([rp], [rs], [q0], s=100, marker='o')
        ax.text(rp, rs, q0, f' {label}')

    all_rows = rows_a + rows_b
    fold = max(all_rows, key=lambda r: float(r['continued_torque_Nm']))
    ax.scatter([float(fold['lambda_p'])], [float(fold['lambda_s'])],
               [float(fold['continued_torque_Nm'])], s=115, marker='^')
    ax.text(float(fold['lambda_p']), float(fold['lambda_s']),
            float(fold['continued_torque_Nm']), ' fold / turning point')

    fixed_text = (
        rf"$T_p={float(candidate['refined_Tp_Nm']):.3f}$ Nm fixed"
        if vary == 'secondary'
        else rf"$T_s={float(candidate['refined_Ts_Nm']):.3f}$ Nm fixed"
    )
    ax.set_xlabel(r'$\lambda_p$')
    ax.set_ylabel(r'$\lambda_s$')
    ax.set_zlabel(r'$T_s$ [Nm]' if vary == 'secondary' else r'$T_p$ [Nm]')
    ax.set_title(
        'Exact pseudo-arclength solution curve with the original torque slice\n'
        + fixed_text + '; plane intersects the curve at the original two roots'
    )
    ax.legend(loc='best')
    ax.grid(True, alpha=0.25)
    fig.savefig(outpath, dpi=210, bbox_inches='tight')
    plt.close(fig)


def write_standalone_continuation_html(
    rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]],
    candidate: dict[str, Any], vary: str, outpath: Path
) -> dict[str, Any]:
    """Always write the main interactive 3D conceptual figure via Plotly.js CDN."""
    traces = []
    for label, rows in [('A', rows_a), ('B', rows_b)]:
        traces.append({
            'type': 'scatter3d', 'mode': 'lines',
            'x': [float(r['lambda_p']) for r in rows],
            'y': [float(r['lambda_s']) for r in rows],
            'z': [float(r['continued_torque_Nm']) for r in rows],
            'line': {'width': 7}, 'name': f'continuation from root {label}',
        })
        bad = [r for r in rows if str(r.get('physical', 'False')).lower() != 'true']
        if bad:
            traces.append({
                'type': 'scatter3d', 'mode': 'markers',
                'x': [float(r['lambda_p']) for r in bad],
                'y': [float(r['lambda_s']) for r in bad],
                'z': [float(r['continued_torque_Nm']) for r in bad],
                'marker': {'size': 3, 'symbol': 'x'},
                'name': f'branch {label} inadmissible points',
            })

    q0 = float(candidate['refined_Ts_Nm'] if vary == 'secondary' else candidate['refined_Tp_Nm'])
    lp_all = np.asarray([float(r['lambda_p']) for r in rows_a + rows_b])
    ls_all = np.asarray([float(r['lambda_s']) for r in rows_a + rows_b])
    lp0, lp1 = float(np.min(lp_all)), float(np.max(lp_all))
    ls0, ls1 = float(np.min(ls_all)), float(np.max(ls_all))
    traces.append({
        'type': 'mesh3d',
        'x': [lp0, lp1, lp1, lp0], 'y': [ls0, ls0, ls1, ls1],
        'z': [q0, q0, q0, q0], 'i': [0, 0], 'j': [1, 2], 'k': [2, 3],
        'opacity': 0.20, 'color': 'gray',
        'name': f'original torque plane: q={q0:.3f} Nm',
    })
    traces.append({
        'type': 'scatter3d', 'mode': 'markers+text',
        'x': [float(candidate['root1_lambda_p']), float(candidate['root2_lambda_p'])],
        'y': [float(candidate['root1_lambda_s']), float(candidate['root2_lambda_s'])],
        'z': [q0, q0], 'text': ['root 1', 'root 2'], 'textposition': 'top center',
        'marker': {'size': 8}, 'name': 'original two roots',
    })
    fold = max(rows_a + rows_b, key=lambda r: float(r['continued_torque_Nm']))
    traces.append({
        'type': 'scatter3d', 'mode': 'markers+text',
        'x': [float(fold['lambda_p'])], 'y': [float(fold['lambda_s'])],
        'z': [float(fold['continued_torque_Nm'])],
        'text': ['fold / turning point'], 'textposition': 'top center',
        'marker': {'size': 9, 'symbol': 'diamond'}, 'name': 'fold',
    })
    layout = {
        'title': 'Exact folded stick-stick continuation curve + original fixed-torque plane',
        'scene': {
            'xaxis': {'title': 'lambda_p'}, 'yaxis': {'title': 'lambda_s'},
            'zaxis': {'title': ('T_s [Nm]' if vary == 'secondary' else 'T_p [Nm]')},
            'aspectmode': 'data',
        },
        'margin': {'l': 0, 'r': 0, 'b': 0, 't': 55},
    }
    import json as _json
    html = f'''<!doctype html>
<html><head><meta charset="utf-8"><title>CINDER continuation + plane</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script></head>
<body style="margin:0"><div id="plot" style="width:100vw;height:100vh"></div>
<script>const traces={_json.dumps(traces)}; const layout={_json.dumps(layout)};
Plotly.newPlot('plot', traces, layout, {{responsive:true}});</script></body></html>'''
    outpath.write_text(html, encoding='utf-8')
    return {'made': True, 'file': outpath.name,
            'note': 'No Python plotly package required; browser loads Plotly.js from CDN.'}


def extract_fixed_other_torque_solution_curve(
    inv: dict[str, Any], candidate: dict[str, Any], vary: str
) -> tuple[list[dict[str, Any]], str, float, float]:
    """Extract the 1-D stick-stick curve for the fixed other boundary torque."""
    lp = np.asarray(inv['lambda_p'], dtype=float)
    ls = np.asarray(inv['lambda_s'], dtype=float)
    Tp = np.asarray(inv['required_Tp'], dtype=float)
    Ts = np.asarray(inv['required_Ts'], dtype=float)
    if vary == 'secondary':
        fixed_field, lifted_field = Tp, Ts
        fixed_name = 'T_p'
        fixed_value = float(candidate['refined_Tp_Nm'])
        q0 = float(candidate['refined_Ts_Nm'])
    else:
        fixed_field, lifted_field = Ts, Tp
        fixed_name = 'T_s'
        fixed_value = float(candidate['refined_Ts_Nm'])
        q0 = float(candidate['refined_Tp_Nm'])

    LP, LS = np.meshgrid(lp, ls)
    fig, ax = plt.subplots()
    cs = ax.contour(LP, LS, np.ma.masked_invalid(fixed_field), levels=[fixed_value])
    segments = cs.allsegs[0] if cs.allsegs else []
    plt.close(fig)

    interp = RegularGridInterpolator((ls, lp), lifted_field, bounds_error=False, fill_value=np.nan)
    rows: list[dict[str, Any]] = []
    for sid, seg in enumerate(segments):
        if len(seg) < 2:
            continue
        query = np.column_stack((seg[:, 1], seg[:, 0]))
        qvals = interp(query)
        for order, ((lpi, lsi), qi) in enumerate(zip(seg, qvals)):
            if not np.isfinite(qi):
                continue
            rows.append({
                'segment_id': sid,
                'point_order': order,
                'lambda_p': float(lpi),
                'lambda_s': float(lsi),
                'continued_torque_Nm': float(qi),
                'fixed_other_torque_name': fixed_name,
                'fixed_other_torque_Nm': fixed_value,
            })
    return rows, fixed_name, fixed_value, q0


def plot_solution_curve_reference_plane(
    curve_rows: list[dict[str, Any]], candidate: dict[str, Any], vary: str, outpath: Path
) -> None:
    if not curve_rows:
        return
    fig = plt.figure(figsize=(9.4, 8.2))
    ax = fig.add_subplot(111, projection='3d')
    by_segment: dict[int, list[dict[str, Any]]] = {}
    for r in curve_rows:
        by_segment.setdefault(int(r['segment_id']), []).append(r)
    first_sid = min(by_segment)
    for sid, rows in by_segment.items():
        rows = sorted(rows, key=lambda r: int(r['point_order']))
        ax.plot(
            [float(r['lambda_p']) for r in rows],
            [float(r['lambda_s']) for r in rows],
            [float(r['continued_torque_Nm']) for r in rows],
            linewidth=2.2,
            label='stick-stick solution curve' if sid == first_sid else None,
        )

    q0 = float(candidate['refined_Ts_Nm'] if vary == 'secondary' else candidate['refined_Tp_Nm'])
    all_lp = np.asarray([float(r['lambda_p']) for r in curve_rows])
    all_ls = np.asarray([float(r['lambda_s']) for r in curve_rows])
    xx = np.linspace(float(np.min(all_lp)), float(np.max(all_lp)), 2)
    yy = np.linspace(float(np.min(all_ls)), float(np.max(all_ls)), 2)
    XX, YY = np.meshgrid(xx, yy)
    ZZ = np.full_like(XX, q0)
    ax.plot_surface(XX, YY, ZZ, alpha=0.20, linewidth=0.0)

    for label, rp, rs in [
        ('root 1', float(candidate['root1_lambda_p']), float(candidate['root1_lambda_s'])),
        ('root 2', float(candidate['root2_lambda_p']), float(candidate['root2_lambda_s'])),
    ]:
        ax.scatter([rp], [rs], [q0], s=95, marker='o')
        ax.text(rp, rs, q0, f' {label}')

    zlabel = r'$T_s$ [Nm]' if vary == 'secondary' else r'$T_p$ [Nm]'
    fixed_text = (
        rf"$T_p={float(candidate['refined_Tp_Nm']):.3f}$ Nm"
        if vary == 'secondary'
        else rf"$T_s={float(candidate['refined_Ts_Nm']):.3f}$ Nm"
    )
    ax.set_xlabel(r'$\lambda_p$')
    ax.set_ylabel(r'$\lambda_s$')
    ax.set_zlabel(zlabel)
    ax.set_title(
        'The two 2-D roots are intersections of one 3-D solution curve\n'
        + fixed_text + '; translucent plane = original fixed continued torque'
    )
    ax.legend(loc='best')
    ax.grid(True, alpha=0.25)
    fig.savefig(outpath, dpi=200, bbox_inches='tight')
    plt.close(fig)


def write_standalone_solution_curve_html(
    curve_rows: list[dict[str, Any]], candidate: dict[str, Any], vary: str,
    outpath: Path, max_points: int
) -> dict[str, Any]:
    """Interactive HTML with no Python plotly dependency; browser loads Plotly.js CDN."""
    if not curve_rows:
        return {'made_standalone_solution_curve_html': False, 'reason': 'no curve rows'}
    by_segment: dict[int, list[dict[str, Any]]] = {}
    for r in curve_rows:
        by_segment.setdefault(int(r['segment_id']), []).append(r)

    traces = []
    for sid, rows in sorted(by_segment.items()):
        rows = sorted(rows, key=lambda r: int(r['point_order']))
        if len(rows) > max_points:
            take = np.linspace(0, len(rows)-1, max_points).astype(int)
            rows = [rows[i] for i in take]
        traces.append({
            'type': 'scatter3d', 'mode': 'lines',
            'x': [float(r['lambda_p']) for r in rows],
            'y': [float(r['lambda_s']) for r in rows],
            'z': [float(r['continued_torque_Nm']) for r in rows],
            'line': {'width': 7},
            'name': f'solution curve segment {sid}',
        })

    q0 = float(candidate['refined_Ts_Nm'] if vary == 'secondary' else candidate['refined_Tp_Nm'])
    lp_vals = np.asarray([float(r['lambda_p']) for r in curve_rows])
    ls_vals = np.asarray([float(r['lambda_s']) for r in curve_rows])
    lp0, lp1 = float(np.min(lp_vals)), float(np.max(lp_vals))
    ls0, ls1 = float(np.min(ls_vals)), float(np.max(ls_vals))
    traces.append({
        'type': 'mesh3d',
        'x': [lp0, lp1, lp1, lp0], 'y': [ls0, ls0, ls1, ls1],
        'z': [q0, q0, q0, q0], 'i': [0, 0], 'j': [1, 2], 'k': [2, 3],
        'opacity': 0.20, 'name': f'reference plane q={q0:.3f} Nm', 'color': 'gray',
    })
    traces.append({
        'type': 'scatter3d', 'mode': 'markers+text',
        'x': [float(candidate['root1_lambda_p']), float(candidate['root2_lambda_p'])],
        'y': [float(candidate['root1_lambda_s']), float(candidate['root2_lambda_s'])],
        'z': [q0, q0], 'text': ['root 1', 'root 2'], 'textposition': 'top center',
        'marker': {'size': 7}, 'name': 'original two roots',
    })
    layout = {
        'title': 'Folded stick-stick solution curve and the fixed-torque slice',
        'scene': {
            'xaxis': {'title': 'lambda_p'}, 'yaxis': {'title': 'lambda_s'},
            'zaxis': {'title': ('T_s [Nm]' if vary == 'secondary' else 'T_p [Nm]')},
            'aspectmode': 'data',
        },
        'legend': {'itemsizing': 'constant'}, 'margin': {'l': 0, 'r': 0, 'b': 0, 't': 55},
    }
    import json as _json
    html = f'''<!doctype html>
<html><head><meta charset="utf-8"><title>CINDER folded solution curve</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script></head>
<body style="margin:0"><div id="plot" style="width:100vw;height:100vh"></div>
<script>
const traces = {_json.dumps(traces)};
const layout = {_json.dumps(layout)};
Plotly.newPlot('plot', traces, layout, {{responsive:true}});
</script></body></html>'''
    outpath.write_text(html, encoding='utf-8')
    return {'made_standalone_solution_curve_html': True, 'file': outpath.name,
            'note': 'Uses Plotly.js CDN in the browser; no Python plotly package required.'}


def maybe_make_plotly_inverse(inv: dict[str, Any], outpath: Path) -> dict[str, Any]:
    try:
        import plotly.graph_objects as go
    except Exception as exc:
        return {'made_plotly_inverse': False, 'reason': f'{type(exc).__name__}: {exc}'}

    lp = inv['lambda_p']
    ls = inv['lambda_s']
    Tp = np.asarray(inv['required_Tp'], dtype=float)
    Ts = np.asarray(inv['required_Ts'], dtype=float)
    valid = np.isfinite(Tp) & np.isfinite(Ts)
    LP, LS = np.meshgrid(lp, ls)

    fig = go.Figure()
    fig.add_trace(go.Scatter3d(
        x=LP[valid].ravel(),
        y=LS[valid].ravel(),
        z=Ts[valid].ravel(),
        mode='markers',
        marker=dict(size=2.5, color=Tp[valid].ravel(), colorscale='Viridis', colorbar=dict(title='T_p [Nm]')),
        name='(lambda_p, lambda_s, T_s) colored by T_p',
    ))
    fig.update_layout(
        title='Projected 4D inverse-torque manifold',
        scene=dict(xaxis_title='lambda_p', yaxis_title='lambda_s', zaxis_title='T_s [Nm]')
    )
    fig.write_html(str(outpath), include_plotlyjs='cdn')
    return {'made_plotly_inverse': True, 'file': outpath.name}


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def main() -> int:
    global problem  # used by contour_slice_plot for static box and q_name labels.
    args = parse_args()
    cc_run.verify_environment()

    cont_dir, parent, candidate, rows_a, rows_b, vary = load_case(args)
    decoded, library, reference_mode, recipe, problem = build_problem(candidate, vary, args)

    out = args.output_dir.resolve() if args.output_dir else (
        DEFAULT_OUTPUT / parent.name / cont_dir.name
    )
    out.mkdir(parents=True, exist_ok=True)

    # Persist the selected inputs so downstream inspection is easy.
    write_rows(out / 'candidate.csv', [candidate])
    write_rows(out / 'branch_A.csv', rows_a)
    write_rows(out / 'branch_B.csv', rows_b)

    # Primary conceptual 3-D view: use the exact pseudo-arclength traces, not a coarse grid.
    plot_continuation_reference_plane_3d(
        rows_a, rows_b, candidate, vary, out / 'continuation_reference_plane_3d.png'
    )
    continuation_html = write_standalone_continuation_html(
        rows_a, rows_b, candidate, vary, out / 'continuation_reference_plane_3d.html'
    )

    volume_path = out / 'zero_surface_volume.npz'
    volume = None
    if volume_path.exists() and not args.recompute:
        cached = load_volume_npz(volume_path)
        if volume_matches_requested_grid(cached, args):
            print(f'Reusing cached 3D residual volume: {volume_path}')
            volume = cached
        else:
            print('Cached 3D volume has the old/coarser grid; rebuilding at requested density...')
    if volume is None:
        print(f'Building 3D residual volume ({args.torque_grid} x {args.lambda_grid} x {args.lambda_grid})...')
        volume = compute_volume(problem, rows_a, rows_b, args)
        save_volume_npz(volume_path, volume)
    slice_info = save_slice_bundle(volume, rows_a, rows_b, out)
    zero_plotly = maybe_make_plotly_zero_surface(volume, rows_a, rows_b, out / 'zero_surface_intersection_3d.html')

    inverse_path = out / 'inverse_torque_surface.npz'
    inv = None
    if inverse_path.exists() and not args.recompute:
        cached = load_inverse_npz(inverse_path)
        if inverse_matches_requested_grid(cached, args):
            print(f'Reusing cached inverse-torque surface: {inverse_path}')
            inv = cached
        else:
            print('Cached inverse-torque surface has the old/coarser grid; rebuilding at requested density...')
    if inv is None:
        print(f'Building inverse-torque surface ({args.inverse_resolution} x {args.inverse_resolution})...')
        inv = inverse_surface_data(decoded, library, reference_mode, candidate, args)
        save_inverse_npz(inverse_path, inv)
    projection_pngs = plot_inverse_projections(inv, out, candidate, vary)

    curve_rows, fixed_name, fixed_value, q0 = extract_fixed_other_torque_solution_curve(inv, candidate, vary)
    write_rows(out / 'fixed_other_torque_solution_curve.csv', curve_rows)
    plot_solution_curve_reference_plane(curve_rows, candidate, vary, out / 'solution_curve_reference_plane_3d.png')
    standalone_curve_html = write_standalone_solution_curve_html(
        curve_rows, candidate, vary, out / 'solution_curve_reference_plane_3d.html',
        int(args.concept_html_max_points)
    )
    inverse_plotly = maybe_make_plotly_inverse(inv, out / 'inverse_torque_projection_3d.html')

    manifest = {
        'source_continuation_dir': str(cont_dir),
        'source_candidate_parent_dir': str(parent),
        'varied_torque': vary,
        'initial_primary_external_torque_Nm': float(candidate['refined_Tp_Nm']),
        'initial_secondary_external_torque_Nm': float(candidate['refined_Ts_Nm']),
        'initial_root1': [float(candidate['root1_lambda_p']), float(candidate['root1_lambda_s'])],
        'initial_root2': [float(candidate['root2_lambda_p']), float(candidate['root2_lambda_s'])],
        'volume_grid_shape': list(np.asarray(volume['R_p']).shape),
        'inverse_grid_shape': list(np.asarray(inv['required_Tp']).shape),
        'slice_files': slice_info,
        'continuation_reference_plane_html': continuation_html,
        'projection_pngs': projection_pngs,
        'fixed_other_torque_solution_curve_points': len(curve_rows),
        'fixed_other_torque_name': fixed_name,
        'fixed_other_torque_Nm': fixed_value,
        'reference_plane_continued_torque_Nm': q0,
        'standalone_solution_curve_html': standalone_curve_html,
        'zero_surface_plotly': zero_plotly,
        'inverse_plotly': inverse_plotly,
    }
    write_manifest(out / 'manifest.json', manifest)

    (out / 'README.txt').write_text(
        'Main outputs:\n'
        '  continuation_reference_plane_3d.png / .html\n'
        '      START HERE. Exact pseudo-arclength branch traces in (lambda_p, lambda_s, q),\n'
        '      with the original fixed-q plane, both roots, fold marker, and inadmissible points.\n'
        '      This does NOT depend on inverse-grid sampling. The HTML is always produced and only\n'
        '      needs internet access in the browser to load Plotly.js.\n\n'
        '  zero_surface_volume.npz\n'
        '      Dense 3D arrays for Rp(lambda_p, lambda_s, q) and Rs(lambda_p, lambda_s, q).\n'
        '      This is the raw material for plotting the two zero-isosurfaces.\n\n'
        '  zero_surface_intersection_3d.html\n'
        '      Interactive Plotly figure (if Plotly is installed) showing the two isosurfaces,\n'
        '      the continued branch-A / branch-B curves, and the constant-q0 plane.\n\n'
        '  slice_*.png\n'
        '      2D contour slices at representative torque levels (initial, near fold, first inadmissibility).\n\n'
        '  inverse_torque_surface.npz\n'
        '      The 2D manifold in 4D parameterized over the lambda grid via\n'
        '          (lambda_p, lambda_s) -> (T_p_required, T_s_required).\n\n'
        '  solution_curve_reference_plane_3d.png / .html\n'
        '      PRIMARY CONCEPTUAL FIGURE. The dense fixed-other-torque solution curve is shown in\n'
        '      (lambda_p, lambda_s, continued torque), together with the original fixed-torque\n'
        '      reference plane and both roots. The HTML is always written and does not require\n'
        '      the Python plotly package (it loads Plotly.js in the browser).\n\n'
        '  fixed_other_torque_solution_curve.csv\n'
        '      Raw extracted 3D solution-curve points for replotting.\n\n'
        '  inverse_projection_*.png / inverse_torque_projection_3d.html\n'
        '      Visualizations of that projected 4D manifold. The Python-generated interactive\n'
        '      HTML files still require the optional plotly package.\n',
        encoding='utf-8',
    )

    print(f'Complete. Outputs: {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
