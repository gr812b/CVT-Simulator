r"""Render high-resolution 4x2 maps for selected multiroot candidates,
including standard and zoomed-out views.

This is a follow-on helper for `search_multiroot_operating_point.py`.
It revisits already-found candidate operating points and renders high-resolution
4x2 figures for selected candidates.

Compared with the earlier helper, this version also renders a second 4x2 figure
with a larger lambda-domain window, so you can inspect how the two roots sit in
the broader residual / inadmissibility landscape.

Typical usage from `results/cinder-v1.1.2`:

    python .\studies\closure-conditioning\render_selected_multiroot_candidates.py `
      --search-output-dir .\studies\closure-conditioning\artifacts\multiroot-operating-point-search\frame_060 `
      --path-csv .\studies\closure-conditioning\artifacts\controlled-free-shift-animation\expanded_res641_locked_locked_path\preflight_path.csv `
      --frame 60 `
      --selection robust-top --count 3

Outputs:
  robust_candidate_ranking.csv
  selected_candidates.csv
  candidate_XX_row_YYY/
      highres_4x2.png
      highres_4x2_zoomed_out.png
      highres_physical_map.npz
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, SymLogNorm, TwoSlopeNorm, ListedColormap
import numpy as np

import run as cc_run
import animate_controlled_free_shift_path as controlled
import search_multiroot_operating_point as base


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--search-output-dir', type=Path, required=True,
                   help='Directory containing good_candidates.csv / refined_candidates.csv from the prior search.')
    p.add_argument('--path-csv', type=Path, required=True,
                   help='Locked/preflight path CSV used to define the frozen state.')
    p.add_argument('--frame', type=int, default=60)
    p.add_argument('--candidate-file', type=str, default='good_candidates.csv',
                   choices=['good_candidates.csv', 'refined_candidates.csv'])
    p.add_argument('--selection', type=str, default='robust-top',
                   choices=['robust-top', 'separation-top', 'explicit'])
    p.add_argument('--count', type=int, default=3)
    p.add_argument('--rows', type=str, default='',
                   help='Comma-separated 1-based candidate row numbers for --selection explicit.')
    p.add_argument('--output-dir', type=Path, default=None)

    p.add_argument('--resolution', type=int, default=401,
                   help='High-resolution physical map size.')
    p.add_argument('--plot-limit', type=float, default=0.8,
                   help='Half-width of the standard close-up lambda window.')
    p.add_argument('--zoomed-out-limit', type=float, default=2.0,
                   help='Half-width of the zoomed-out lambda window.')
    p.add_argument('--rerun-multistart', action='store_true')
    p.add_argument('--final-multistart', type=int, default=13)
    p.add_argument('--root-cluster-tolerance', type=float, default=2.0e-4)

    p.add_argument('--minimum-normal-N', type=float, default=1.0)
    p.add_argument('--minimum-static-margin', type=float, default=0.0)
    p.add_argument('--write-all-ranked', action='store_true')
    return p.parse_args()


def parse_rows(text: str) -> list[int]:
    out: list[int] = []
    for token in text.split(','):
        token = token.strip()
        if token:
            out.append(int(token))
    return out


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    for i, row in enumerate(rows, start=1):
        row['_row_number'] = i
    return rows


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def numeric(row: dict[str, Any], key: str) -> float:
    value = row.get(key, '')
    if value in ('', None):
        return float('nan')
    return float(value)


def robustify_candidate(decoded, library, recipe, reference_mode,
                        row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    bundle = base.candidate_bundle(decoded, library, recipe, reference_mode, row)
    root1 = {
        'lambda_p': numeric(row, 'root1_lambda_p'),
        'lambda_s': numeric(row, 'root1_lambda_s'),
        'residual_norm': 0.0,
        'nfev': 0,
    }
    root2 = {
        'lambda_p': numeric(row, 'root2_lambda_p'),
        'lambda_s': numeric(row, 'root2_lambda_s'),
        'residual_norm': 0.0,
        'nfev': 0,
    }
    diag1 = base.physical_root_diagnostics(bundle, root1, args)
    diag2 = base.physical_root_diagnostics(bundle, root2, args)

    row_out = dict(row)
    row_out.update({
        'evaluated_Tp_Nm': float(bundle.torque_p),
        'evaluated_Ts_Nm': float(bundle.torque_s),
        'root1_mechanism_margin': float(diag1['mechanism_margin']),
        'root1_min_belt_tension': float(diag1['min_belt_tension']),
        'root1_min_local_normal_p': float(diag1['min_local_normal_p']),
        'root1_min_local_normal_s': float(diag1['min_local_normal_s']),
        'root1_A_condition_scaled': float(diag1['A_condition_scaled']),
        'root2_mechanism_margin': float(diag2['mechanism_margin']),
        'root2_min_belt_tension': float(diag2['min_belt_tension']),
        'root2_min_local_normal_p': float(diag2['min_local_normal_p']),
        'root2_min_local_normal_s': float(diag2['min_local_normal_s']),
        'root2_A_condition_scaled': float(diag2['A_condition_scaled']),
    })

    physical_count = int(bool(diag1['physical'])) + int(bool(diag2['physical']))
    min_static = min(
        float(diag1['primary_static_margin']), float(diag1['secondary_static_margin']),
        float(diag2['primary_static_margin']), float(diag2['secondary_static_margin']),
    )
    min_normal = min(float(diag1['N_p']), float(diag1['N_s']), float(diag2['N_p']), float(diag2['N_s']))
    min_local_wrap_normal = min(
        float(diag1['min_local_normal_p']), float(diag1['min_local_normal_s']),
        float(diag2['min_local_normal_p']), float(diag2['min_local_normal_s']),
    )
    min_belt_tension = min(float(diag1['min_belt_tension']), float(diag2['min_belt_tension']))
    min_mechanism_margin = min(float(diag1['mechanism_margin']), float(diag2['mechanism_margin']))
    max_Acond = max(float(diag1['A_condition_scaled']), float(diag2['A_condition_scaled']))
    separation = float(row_out.get('root_separation', np.hypot(
        root1['lambda_p'] - root2['lambda_p'], root1['lambda_s'] - root2['lambda_s']
    )))

    robust_score = (
        2000.0 * physical_count
        + 220.0 * separation
        + 45.0 * max(min_static, -1.0)
        + 0.015 * max(min_normal, 0.0)
        + 0.30 * max(min_local_wrap_normal, 0.0)
        + 0.020 * max(min_belt_tension, 0.0)
        + 18.0 * max(min_mechanism_margin, -1.0)
        - 0.001 * max_Acond
    )

    row_out.update({
        'physical_root_count_verified': physical_count,
        'verified_root_separation': separation,
        'minimum_static_margin_verified': min_static,
        'minimum_normal_N_verified': min_normal,
        'minimum_local_wrap_normal_verified': min_local_wrap_normal,
        'minimum_belt_tension_verified': min_belt_tension,
        'minimum_mechanism_margin_verified': min_mechanism_margin,
        'maximum_A_condition_scaled_verified': max_Acond,
        'robust_score': robust_score,
    })
    return row_out


def choose_rows(ranked: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.write_all_ranked:
        return list(ranked)
    if args.selection == 'explicit':
        wanted = set(parse_rows(args.rows))
        if not wanted:
            raise ValueError('--selection explicit requires --rows.')
        chosen = [row for row in ranked if int(row['_row_number']) in wanted]
        missing = sorted(wanted - {int(row['_row_number']) for row in chosen})
        if missing:
            raise ValueError(f'Requested row(s) not found: {missing}')
        return chosen
    if args.selection == 'separation-top':
        ordered = sorted(
            ranked,
            key=lambda row: (
                -int(row['physical_root_count_verified']),
                -float(row['verified_root_separation']),
                -float(row['minimum_static_margin_verified']),
                -float(row['minimum_mechanism_margin_verified']),
            ),
        )
        return ordered[:max(0, int(args.count))]
    ordered = sorted(
        ranked,
        key=lambda row: (
            -int(row['physical_root_count_verified']),
            -float(row['robust_score']),
            -float(row['verified_root_separation']),
        ),
    )
    return ordered[:max(0, int(args.count))]


def signed_limit(values):
    a = np.abs(np.asarray(values, dtype=float))
    a = a[np.isfinite(a)]
    return max(float(np.percentile(a, 99.5)) if a.size else 1.0, 1.0e-12)


def positive_limits(values):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a) & (a > 0.0)]
    if not a.size:
        return 1.0e-12, 1.0
    lo = max(float(np.percentile(a, 1.0)), 1.0e-12)
    hi = max(float(np.percentile(a, 99.5)), lo * 1.01)
    return lo, hi


def plot_candidate_4x2(data, roots: list[dict[str, Any]], title: str, path: Path, plot_limit: float):
    lp, ls = data['lambda_p'], data['lambda_s']
    LP, LS = np.meshgrid(lp, ls)
    invalid = ~np.asarray(data['topology_admissible'], dtype=bool)
    rp_lim = signed_limit(data['R_p'])
    rs_lim = signed_limit(data['R_s'])
    rn_lo, rn_hi = positive_limits(data['R_norm'])
    ca_lo, ca_hi = positive_limits(data['cond_A_scaled'])
    jm_lo, jm_hi = positive_limits(data['sigma_min_J'])
    jc_lo, jc_hi = positive_limits(data['kappa_J'])
    det_lim = signed_limit(data['det_J'])

    panels = [
        ('Rp', data['R_p'], SymLogNorm(linthresh=1.0, vmin=-rp_lim, vmax=rp_lim)),
        ('Rs', data['R_s'], SymLogNorm(linthresh=1.0, vmin=-rs_lim, vmax=rs_lim)),
        ('|R|', data['R_norm'], LogNorm(vmin=rn_lo, vmax=rn_hi)),
        ('kappa(A)', data['cond_A_scaled'], LogNorm(vmin=ca_lo, vmax=ca_hi)),
        ('sigma_min(J_R)', data['sigma_min_J'], LogNorm(vmin=jm_lo, vmax=jm_hi)),
        ('kappa(J_R)', data['kappa_J'], LogNorm(vmin=jc_lo, vmax=jc_hi)),
        ('det(J_R)', data['det_J'], TwoSlopeNorm(vcenter=0.0, vmin=-det_lim, vmax=det_lim)),
    ]

    fig, axes = plt.subplots(2, 4, figsize=(18, 9.4), constrained_layout=True)
    for ax, (name, source, norm) in zip(axes.ravel()[:7], panels):
        values = np.ma.masked_where(invalid, np.asarray(source, dtype=float))
        im = ax.pcolormesh(LP, LS, values, shading='auto', norm=norm, rasterized=True)
        try:
            ax.contour(LP, LS, data['R_p'], levels=[0.0], colors='black', linewidths=1.0)
            ax.contour(LP, LS, data['R_s'], levels=[0.0], colors='cyan', linewidths=1.0, linestyles='--')
        except ValueError:
            pass
        for k, root in enumerate(roots):
            ax.plot(root['lambda_p'], root['lambda_s'], marker='o', ms=7,
                    markerfacecolor='none', markeredgecolor='red', mew=1.6)
            ax.text(root['lambda_p'], root['lambda_s'], f' {k+1}', color='red', fontsize=8)
        ax.set_title(name)
        ax.set_xlabel(r'$\lambda_p$')
        ax.set_ylabel(r'$\lambda_s$')
        ax.set_xlim(-plot_limit, plot_limit)
        ax.set_ylim(-plot_limit, plot_limit)
        fig.colorbar(im, ax=ax, shrink=0.82)

    ax = axes.ravel()[7]
    code = np.asarray(data['topology_failure_code'], dtype=int)
    disp = np.zeros_like(code, dtype=int)
    disp[(code & 2) != 0] = 1
    disp[(code & 4) != 0] = 2
    disp[(code & 8) != 0] = 3
    disp[(code & 1) != 0] = 4
    cmap = ListedColormap(['white', '#4c78a8', '#f58518', '#54a24b', '#e45756'])
    ax.pcolormesh(LP, LS, disp, shading='auto', cmap=cmap, vmin=0, vmax=4, rasterized=True)
    for k, root in enumerate(roots):
        ax.plot(root['lambda_p'], root['lambda_s'], marker='o', ms=7,
                markerfacecolor='none', markeredgecolor='black', mew=1.6)
        ax.text(root['lambda_p'], root['lambda_s'], f' {k+1}', color='black', fontsize=8)
    ax.set_title('inadmissibility')
    ax.set_xlabel(r'$\lambda_p$')
    ax.set_ylabel(r'$\lambda_s$')
    ax.set_xlim(-plot_limit, plot_limit)
    ax.set_ylim(-plot_limit, plot_limit)

    fig.suptitle(title, fontsize=14)
    fig.savefig(path, dpi=190)
    plt.close(fig)


def render_candidate(decoded, library, recipe, reference_mode,
                     row: dict[str, Any], outdir: Path, args: argparse.Namespace) -> dict[str, Any]:
    bundle = base.candidate_bundle(decoded, library, recipe, reference_mode, row)

    if args.rerun_multistart:
        ms_rows, ms_roots = base.production_multistart(
            bundle,
            int(args.final_multistart),
            float(args.root_cluster_tolerance),
        )
        write_rows(outdir / 'final_multistart.csv', ms_rows)
        write_rows(outdir / 'final_root_diagnostics.csv', ms_roots)
        roots_for_plot = [root for root in ms_roots if bool(root['physical'])]
        if len(roots_for_plot) < 2:
            roots_for_plot = ms_roots
    else:
        root1 = {
            'lambda_p': numeric(row, 'root1_lambda_p'),
            'lambda_s': numeric(row, 'root1_lambda_s'),
            'residual_norm': 0.0,
            'nfev': 0,
        }
        root2 = {
            'lambda_p': numeric(row, 'root2_lambda_p'),
            'lambda_s': numeric(row, 'root2_lambda_s'),
            'residual_norm': 0.0,
            'nfev': 0,
        }
        roots_for_plot = [
            base.physical_root_diagnostics(bundle, root1, args),
            base.physical_root_diagnostics(bundle, root2, args),
        ]

    data = cc_run.build_map(
        bundle.ref,
        bundle.sample,
        'physical',
        int(args.resolution),
    )
    np.savez_compressed(
        outdir / 'highres_physical_map.npz',
        **{k: v for k, v in data.items() if isinstance(v, np.ndarray)},
    )
    base_title = (
        f'Selected multiroot candidate | frozen frame {args.frame} | '
        f'row {int(row["_row_number"]):03d} | '
        f'Tp={float(row["refined_Tp_Nm"]):+.2f} Nm, '
        f'Ts={float(row["refined_Ts_Nm"]):+.2f} Nm | '
        f'sep={float(row["verified_root_separation"]):.4f} | '
        f'min static={float(row["minimum_static_margin_verified"]):.4f} | '
        f'min mech={float(row["minimum_mechanism_margin_verified"]):.4f}'
    )
    plot_candidate_4x2(
        data,
        roots_for_plot,
        base_title + f' | window=±{float(args.plot_limit):.2f}',
        outdir / 'highres_4x2.png',
        float(args.plot_limit),
    )
    plot_candidate_4x2(
        data,
        roots_for_plot,
        base_title + f' | zoomed out window=±{float(args.zoomed_out_limit):.2f}',
        outdir / 'highres_4x2_zoomed_out.png',
        float(args.zoomed_out_limit),
    )

    summary = dict(row)
    summary['rendered_resolution'] = int(args.resolution)
    summary['reran_multistart'] = bool(args.rerun_multistart)
    summary['closeup_plot_limit'] = float(args.plot_limit)
    summary['zoomed_out_plot_limit'] = float(args.zoomed_out_limit)
    write_rows(outdir / 'candidate_summary.csv', [summary])
    return summary


def main() -> int:
    args = parse_args()
    if float(args.zoomed_out_limit) < float(args.plot_limit):
        raise ValueError('--zoomed-out-limit should be >= --plot-limit.')
    search_dir = args.search_output_dir.resolve()
    candidate_path = search_dir / args.candidate_file
    if not candidate_path.exists():
        raise FileNotFoundError(f'Could not find {candidate_path}')

    cc_run.verify_environment()
    decoded, library = controlled.load_base()
    recipe = base.frozen_recipe(args.path_csv.resolve(), int(args.frame))
    _, sample = controlled.make_ref_and_sample(decoded, library, recipe)
    reference_mode = sample.composed_mode

    raw_rows = read_rows(candidate_path)
    if not raw_rows:
        raise SystemExit(f'No candidate rows found in {candidate_path}')

    print('=' * 88)
    print(f'Search directory: {search_dir}')
    print(f'Candidate source: {candidate_path.name}')
    print(f'Candidate rows loaded: {len(raw_rows)}')
    print()
    print('Evaluating candidate robustness...')
    ranked: list[dict[str, Any]] = []
    for i, row in enumerate(raw_rows, start=1):
        robust = robustify_candidate(decoded, library, recipe, reference_mode, row, args)
        ranked.append(robust)
        print(
            f'  row {int(robust["_row_number"]):03d}/{len(raw_rows):03d}: '
            f'sep={float(robust["verified_root_separation"]):.4f}, '
            f'min static={float(robust["minimum_static_margin_verified"]):.4f}, '
            f'min mech={float(robust["minimum_mechanism_margin_verified"]):.4f}, '
            f'robust score={float(robust["robust_score"]):.2f}'
        )

    ranking = sorted(
        ranked,
        key=lambda row: (
            -int(row['physical_root_count_verified']),
            -float(row['robust_score']),
            -float(row['verified_root_separation']),
        ),
    )

    out = args.output_dir.resolve() if args.output_dir else search_dir / 'selected_highres_candidates'
    out.mkdir(parents=True, exist_ok=True)
    write_rows(out / 'robust_candidate_ranking.csv', ranking)

    selected = choose_rows(ranking, args)
    write_rows(out / 'selected_candidates.csv', selected)

    print()
    print(f'Rendering {len(selected)} candidate(s)...')
    rendered = []
    for rank, row in enumerate(selected, start=1):
        candidate_out = out / f'candidate_{rank:02d}_row_{int(row["_row_number"]):03d}'
        candidate_out.mkdir(exist_ok=True)
        summary = render_candidate(decoded, library, recipe, reference_mode, row, candidate_out, args)
        rendered.append(summary)
        print(
            f'  rendered row {int(row["_row_number"]):03d} -> '
            f'Tp={float(row["refined_Tp_Nm"]):+.2f}, '
            f'Ts={float(row["refined_Ts_Nm"]):+.2f}, '
            f'sep={float(row["verified_root_separation"]):.4f}, '
            f'min mech={float(row["minimum_mechanism_margin_verified"]):.4f}'
        )

    write_rows(out / 'rendered_candidates_summary.csv', rendered)
    (out / 'README.txt').write_text(
        'This helper writes two 4x2 figures per rendered candidate:\n'
        '  - highres_4x2.png              : close-up window (default ±0.8)\n'
        '  - highres_4x2_zoomed_out.png   : broader window (default ±2.0)\n\n'
        'Use --plot-limit and --zoomed-out-limit to change those windows.\n',
        encoding='utf-8',
    )
    print()
    print(f'Outputs written to {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
