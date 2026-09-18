"""Search for a visually clear multiroot/fold example and build a story GIF.

This script is an orchestrator around the studies you already have:

  1) it reads global-comfortable-multiroot-search/comfort_audit_results.csv,
  2) pre-ranks promising two-root operating points,
  3) runs continuation on the top shortlist,
  4) builds the manifold and focused fixed-torque slice for each,
  5) scores which one has the clearest fold *between the two roots*,
  6) renders a compact GIF for the best one.

The goal is not to prove uniqueness.  The goal is to quickly find the most
*explainable* example: a state where the second root and the fold are both
visible in a simple diagram.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parents[1]
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--global-search-dir', type=Path, required=True,
                   help='Directory containing comfort_audit_results.csv')
    p.add_argument('--reference-path-csv', type=Path, required=True)
    p.add_argument('--reference-frame', type=int, default=60)
    p.add_argument('--output-dir', type=Path, default=HERE / 'artifacts' / 'best-visual-multiroot-story')
    p.add_argument('--top-k', type=int, default=8,
                   help='How many promising candidates to fully continue and score.')
    p.add_argument('--vary', choices=['primary', 'secondary'], default='secondary')
    p.add_argument('--jobs', type=int, default=1,
                   help='Passed through to the GIF renderer.')
    p.add_argument('--frames', type=int, default=72,
                   help='Passed through to the GIF renderer.')
    p.add_argument('--force', action='store_true',
                   help='Recompute even if outputs already exist.')
    return p.parse_args()


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    for i, row in enumerate(rows, start=1):
        row['_source_row'] = i
    return rows


def truthy(v: Any) -> bool:
    return str(v).strip().lower() in {'1', 'true', 'yes', 'y'}


def f(row: dict[str, Any], key: str, default: float = float('nan')) -> float:
    try:
        return float(row[key])
    except Exception:
        return float(default)


def pre_score(row: dict[str, Any]) -> float:
    root_sep = f(row, 'root_separation', 0.0)
    min_radius = f(row, 'minimum_admissibility_radius', 0.0)
    cross = f(row, 'minimum_crossing_angle_deg', 0.0)
    static_margin = f(row, 'minimum_static_margin_exact', f(row, 'minimum_static_margin', 0.0))
    mech_margin = f(row, 'minimum_mechanism_margin_exact', 0.0)
    local_norm = f(row, 'minimum_local_normal_exact', 0.0)
    # Heuristic: prefer well-separated roots with non-tiny admissibility radius,
    # decent crossing angle, and some room away from mechanism/local-normal limits.
    return (
        6.0 * root_sep
        + 18.0 * max(0.0, min_radius)
        + 0.08 * max(0.0, cross)
        + 2.5 * max(0.0, static_margin)
        + 0.5 * max(0.0, mech_margin)
        + 0.15 * max(0.0, local_norm)
    )


def shortlist_rows(rows: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    eligible = [r for r in rows if truthy(r.get('both_roots_physical_exact', False))]
    if not eligible:
        eligible = list(rows)
    eligible.sort(key=pre_score, reverse=True)
    selected: list[dict[str, Any]] = []
    seen_states: set[str] = set()
    for r in eligible:
        sid = str(r.get('state_id', ''))
        if sid in seen_states:
            continue
        selected.append(r)
        seen_states.add(sid)
        if len(selected) >= int(top_k):
            break
    return selected


def run_cmd(cmd: list[str]) -> None:
    print('RUN:', ' '.join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def analyze_manifold(manifold_dir: Path) -> dict[str, Any]:
    # Read the focused-slice manifest if present; otherwise compute directly from files.
    cand_path = manifold_dir / 'candidate.csv'
    curve_path = manifold_dir / 'fixed_other_torque_solution_curve.csv'
    with cand_path.open(newline='', encoding='utf-8') as handle:
        cand = list(csv.DictReader(handle))[0]
    with curve_path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    curve = np.asarray([
        [float(r['lambda_p']), float(r['lambda_s']), float(r['continued_torque_Nm']), int(r['segment_id']), int(r['point_order'])]
        for r in rows
    ], dtype=float)
    root1 = np.asarray([float(cand['root1_lambda_p']), float(cand['root1_lambda_s'])], dtype=float)
    root2 = np.asarray([float(cand['root2_lambda_p']), float(cand['root2_lambda_s'])], dtype=float)
    ts0 = float(cand['refined_Ts_Nm'])
    # choose the segment nearest both roots
    best_seg = None
    best_score = float('inf')
    for sid in np.unique(curve[:, 3].astype(int)):
        seg = curve[curve[:, 3].astype(int) == int(sid)]
        seg = seg[np.argsort(seg[:, 4])]
        score = float(np.min(np.linalg.norm(seg[:, :2] - root1[None, :], axis=1))
                      + np.min(np.linalg.norm(seg[:, :2] - root2[None, :], axis=1)))
        if score < best_score:
            best_score = score
            best_seg = seg
    if best_seg is None:
        raise RuntimeError('No segment selected while scoring manifold.')
    seg = best_seg
    i1 = int(np.argmin(np.linalg.norm(seg[:, :2] - root1[None, :], axis=1)))
    i2 = int(np.argmin(np.linalg.norm(seg[:, :2] - root2[None, :], axis=1)))
    if i1 > i2:
        i1, i2 = i2, i1
    between = seg[i1:i2+1]
    if len(between) < 3:
        fold_prominence = 0.0
        fold_ts = ts0
    else:
        vals = between[:, 2]
        # The "visual" fold is the most extreme departure from the root level *between* the roots.
        fold_ts = float(vals[np.argmax(np.abs(vals - ts0))])
        fold_prominence = abs(fold_ts - ts0)
    root_sep = float(cand['root_separation'])
    min_radius = min(f(cand, 'root1_admissibility_radius', 0.0), f(cand, 'root2_admissibility_radius', 0.0))
    min_cross = min(f(cand, 'root1_crossing_angle_deg', 0.0), f(cand, 'root2_crossing_angle_deg', 0.0))
    static_margin = min(f(cand, 'root1_static_margin_min', 0.0), f(cand, 'root2_static_margin_min', 0.0))
    score = fold_prominence + 14.0 * min_radius + 4.0 * root_sep + 0.05 * min_cross + 2.0 * max(0.0, static_margin)
    return {
        'fold_prominence_Nm': float(fold_prominence),
        'fold_ts_Nm': float(fold_ts),
        'root_level_Ts_Nm': float(ts0),
        'root_separation': float(root_sep),
        'minimum_admissibility_radius': float(min_radius),
        'minimum_crossing_angle_deg': float(min_cross),
        'minimum_static_margin': float(static_margin),
        'visual_score': float(score),
    }


def locate_candidate_dir(parent: Path) -> Path:
    matches = sorted(p for p in parent.glob('candidate_*') if p.is_dir())
    if not matches:
        raise FileNotFoundError(f'No candidate_* directory found in {parent}')
    return matches[0]


def main() -> int:
    args = parse_args()
    gdir = args.global_search_dir.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = read_rows(gdir / 'comfort_audit_results.csv')
    shortlist = shortlist_rows(rows, int(args.top_k))
    with (out / 'shortlist.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(shortlist[0].keys()))
        writer.writeheader(); writer.writerows(shortlist)

    evaluations: list[dict[str, Any]] = []
    for rank, row in enumerate(shortlist, start=1):
        rownum = int(row['_source_row'])
        state_id = str(row.get('state_id', f'row_{rownum:03d}'))
        label = f'{rank:02d}_row_{rownum:03d}_{state_id}'.replace('/', '_').replace('\\', '_')
        candidate_root = out / label
        continuation_root = candidate_root / 'continuation'
        candidate_dir = None
        manifold_dir = candidate_root / 'manifold'
        vary_dir = None

        if args.force or not continuation_root.exists():
            cmd = [sys.executable, str(HERE / 'analysis/continue_multiroot_branches.py'),
                   '--global-search-dir', str(gdir),
                   '--reference-path-csv', str(args.reference_path_csv.resolve()),
                   '--reference-frame', str(int(args.reference_frame)),
                   '--candidate-rows', str(rownum),
                   '--vary', str(args.vary),
                   '--output-dir', str(continuation_root)]
            run_cmd(cmd)
        candidate_dir = locate_candidate_dir(continuation_root)
        vary_dir = candidate_dir / f'vary_{args.vary}_torque'
        if not vary_dir.exists():
            raise FileNotFoundError(f'Missing {vary_dir}')

        if args.force or not manifold_dir.exists() or not (manifold_dir / 'candidate.csv').exists():
            cmd = [sys.executable, str(HERE / 'analysis/visualize_multiroot_manifold.py'),
                   '--continuation-dir', str(vary_dir),
                   '--reference-path-csv', str(args.reference_path_csv.resolve()),
                   '--reference-frame', str(int(args.reference_frame)),
                   '--output-dir', str(manifold_dir)]
            run_cmd(cmd)

        slice_dir = manifold_dir / 'focused-slice-visuals'
        if args.force or not slice_dir.exists() or not (slice_dir / 'manifest.json').exists():
            cmd = [sys.executable, str(HERE / 'analysis/make_fixed_torque_slice_visuals.py'),
                   '--manifold-dir', str(manifold_dir)]
            run_cmd(cmd)

        metrics = analyze_manifold(manifold_dir)
        record = dict(metrics)
        record.update({
            'rank': rank,
            'source_row': rownum,
            'state_id': state_id,
            'candidate_root': str(candidate_root),
            'candidate_dir': str(candidate_dir),
            'vary_dir': str(vary_dir),
            'manifold_dir': str(manifold_dir),
        })
        evaluations.append(record)
        print(f"Candidate {rank}/{len(shortlist)} | row {rownum:03d} | {state_id} | score={record['visual_score']:.3f}")

    evaluations.sort(key=lambda r: float(r['visual_score']), reverse=True)
    if not evaluations:
        raise SystemExit('No candidates evaluated.')
    with (out / 'evaluation_summary.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(evaluations[0].keys()))
        writer.writeheader(); writer.writerows(evaluations)

    best = evaluations[0]
    best_dir = Path(best['manifold_dir'])
    gif_out = Path(best['candidate_root']) / 'story-gif'
    if args.force or not (gif_out / 'multiroot_story.gif').exists():
        cmd = [sys.executable, str(HERE / 'exploration/render_multiroot_story_gif.py'),
               '--manifold-dir', str(best_dir),
               '--output-dir', str(gif_out),
               '--frames', str(int(args.frames)),
               '--jobs', str(int(args.jobs))]
        run_cmd(cmd)

    summary = {
        'best_candidate': best,
        'top5': evaluations[:5],
        'notes': [
            'visual_score rewards a large turning of the fixed-Tp curve between the two roots,',
            'plus root separation, admissibility radius, crossing angle, and static margin.',
            'The selected example is intended to be easy to explain, not necessarily the globally most extreme mathematical branch.'
        ],
    }
    (out / 'best_candidate_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    (out / 'README.txt').write_text(
        'Run complete.\n\n'
        f"Best manifold directory:\n{best_dir}\n\n"
        f"Best GIF:\n{gif_out / 'multiroot_story.gif'}\n",
        encoding='utf-8',
    )
    print('\nBEST CANDIDATE')
    print(json.dumps(best, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
