r"""Pseudo-arclength continuation of the two stick-stick closure branches.

This is the final follow-on study for the multiple-root investigation.

It starts from already-verified two-root operating points produced by
`global_comfortable_multiroot_search.py`, freezes the mechanical state, and
continues each algebraic stick-stick root while varying one shaft boundary
torque.  The continuation is pseudo-arclength rather than simple torque
stepping, so it can pass through a fold where d(lambda)/dT becomes vertical.

The purpose is to distinguish three possibilities:

  1. the ordinary branch simply continues smoothly while the alternate branch
     lives near a physical-admissibility boundary;
  2. the two branches are pieces of one folded / hysteretic solution curve;
  3. the branches remain disconnected over the investigated torque interval.

For every accepted continuation point the script records the actual closure
solution and physical diagnostics:

    lambda_p, lambda_s,
    N_p, N_s,
    tau_p, tau_s,
    alpha_p, alpha_s, v_b_dot, s_ddot,
    static-friction margins,
    local wrap-normal margins,
    mechanism margin,
    minimum belt tension,
    topology failure code,
    det(J_R), kappa(J_R), contour crossing angle.

The branch is deliberately continued *through* loss of physical admissibility
when the algebraic closure still exists.  That lets the plots show whether the
mathematical branch runs directly into friction capacity, wrap lift-off, a
unilateral mechanism boundary, or a fold.

The state itself is frozen throughout each continuation.  Therefore any large
change in forces / accelerations along one smooth branch is an algebraic
response, not a velocity or position jump.  The output also includes simple
step-to-step closure-jump diagnostics which are useful prototypes for a future
runtime branch-hop detector.

Typical run from results/cinder-v1.1.2
--------------------------------------

    python .\studies\closure-conditioning\continue_multiroot_branches.py `
      --global-search-dir .\studies\closure-conditioning\artifacts\global-comfortable-multiroot-search `
      --reference-path-csv .\studies\closure-conditioning\artifacts\controlled-free-shift-animation\expanded_res641_locked_locked_path\preflight_path.csv `
      --reference-frame 60

By default three representative examples are selected automatically:
  * static-friction-limited alternate root,
  * local-wrap/contact-limited alternate root,
  * unilateral-mechanism-limited alternate root.

Both primary- and secondary-boundary-torque continuation are run by default.
Use `--vary primary` or `--vary secondary` to restrict the study.

This script expects the following helpers to already be present beside it:
  * search_multiroot_operating_point.py
  * global_comfortable_multiroot_search.py
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
from scipy.optimize import root as scipy_root
from scipy.spatial import cKDTree

import run as cc_run
import animate_controlled_free_shift_path as controlled
import search_multiroot_operating_point as base
import global_comfortable_multiroot_search as global_search

from cinder.model.cvt.contact import ContactInterface, ContactTractionUtilization


HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / 'artifacts' / 'multiroot-branch-continuation'


# ---------------------------------------------------------------------------
# CLI / I/O
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--global-search-dir', type=Path, required=True,
                   help='Directory containing comfort_audit_results.csv from the global search.')
    p.add_argument('--reference-path-csv', type=Path, required=True,
                   help='Known-good locked path, used only to obtain a FREE/STICK_STICK mode object.')
    p.add_argument('--reference-frame', type=int, default=60)
    p.add_argument('--output-dir', type=Path, default=None)

    p.add_argument('--candidate-rows', type=str, default='',
                   help='Optional comma-separated 1-based rows of comfort_audit_results.csv. '
                        'If omitted, three representative examples are selected automatically.')
    p.add_argument('--vary', choices=['primary', 'secondary', 'both'], default='both')

    # Pseudo-arclength controls.
    p.add_argument('--steps-per-direction', type=int, default=100)
    p.add_argument('--arclength-step', type=float, default=0.025,
                   help='Step in scaled (lambda_p, lambda_s, T/q_scale) space.')
    p.add_argument('--minimum-arclength-step', type=float, default=0.0015)
    p.add_argument('--torque-scale-Nm', type=float, default=50.0,
                   help='Scale used to nondimensionalize the continued torque coordinate.')
    p.add_argument('--torque-basis-step-Nm', type=float, default=1.0,
                   help='Finite torque increment used to identify the exact affine residual response.')
    p.add_argument('--torque-span-Nm', type=float, default=140.0,
                   help='Stop when the varied torque is this far from the initial candidate torque.')
    p.add_argument('--absolute-torque-limit-Nm', type=float, default=400.0)
    p.add_argument('--expanded-lambda-limit', type=float, default=2.0)
    p.add_argument('--residual-scale', type=float, default=100.0,
                   help='Residual scale used only inside the pseudo-arclength corrector.')
    p.add_argument('--root-residual-tolerance', type=float, default=1.0e-6)
    p.add_argument('--arc-tolerance', type=float, default=1.0e-7)
    p.add_argument('--max-corrector-evaluations', type=int, default=120)
    p.add_argument('--max-step-halvings', type=int, default=5)
    p.add_argument('--lambda-jacobian-step', type=float, default=1.0e-5)

    # Physical diagnostic thresholds; topology_failure_code carries the rest.
    p.add_argument('--minimum-normal-N', type=float, default=1.0)
    p.add_argument('--minimum-static-margin', type=float, default=0.0)

    # Curve comparison / reporting.
    p.add_argument('--curve-merge-tolerance', type=float, default=0.015,
                   help='Scaled 3D distance below which the two traced curves are reported as overlapping.')
    return p.parse_args()


def parse_int_list(text: str) -> list[int]:
    return [int(v.strip()) for v in text.split(',') if v.strip()]


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    for i, row in enumerate(rows, start=1):
        row['_source_row'] = i
    return rows


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


def num(row: dict[str, Any], key: str) -> float:
    return float(row[key])


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------

def auto_select_examples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pick three qualitatively different alternate-root failure examples."""
    if not rows:
        return []

    def get(r, key, default=np.nan):
        try:
            return float(r[key])
        except Exception:
            return float(default)

    eligible = [
        r for r in rows
        if str(r.get('both_roots_physical_exact', '')).lower() == 'true'
        and get(r, 'minimum_crossing_angle_deg', 0.0) >= 12.0
    ] or list(rows)

    # A: measured root-2 admissibility radius essentially equals root-2 static margin.
    static_case = min(
        eligible,
        key=lambda r: abs(
            get(r, 'root2_admissibility_radius', 1e9)
            - get(r, 'root2_static_margin_min', -1e9)
        ),
    )

    # B: static and mechanism margins are still comfortable, but local wrap normal is tiny.
    local_pool = [
        r for r in eligible
        if get(r, 'root2_static_margin_min', -1.0) > 0.08
        and get(r, 'root2_mechanism_margin', -1.0) > 0.2
        and get(r, 'root2_local_normal_min', 1e9) < 1.0
    ]
    if local_pool:
        local_case = min(
            local_pool,
            key=lambda r: (
                get(r, 'root2_local_normal_min', 1e9),
                -get(r, 'minimum_crossing_angle_deg', 0.0),
            ),
        )
    else:
        local_case = min(eligible, key=lambda r: get(r, 'root2_local_normal_min', 1e9))

    # C: local wrap normal is not itself almost zero, but unilateral mechanism margin is.
    mechanism_pool = [
        r for r in eligible
        if get(r, 'root2_static_margin_min', -1.0) > 0.02
        and get(r, 'root2_local_normal_min', -1.0) > 0.5
    ]
    if mechanism_pool:
        mechanism_case = min(mechanism_pool, key=lambda r: get(r, 'root2_mechanism_margin', 1e9))
    else:
        mechanism_case = min(eligible, key=lambda r: get(r, 'root2_mechanism_margin', 1e9))

    selected = []
    labels = [
        ('static_limited', static_case),
        ('local_wrap_limited', local_case),
        ('mechanism_limited', mechanism_case),
    ]
    seen = set()
    for label, row in labels:
        key = int(row['_source_row'])
        if key in seen:
            continue
        seen.add(key)
        copy = dict(row)
        copy['_example_label'] = label
        selected.append(copy)

    # Fill to three with best-radius near misses if heuristics collided.
    for row in sorted(rows, key=lambda r: get(r, 'minimum_admissibility_radius', -1.0), reverse=True):
        if len(selected) >= 3:
            break
        key = int(row['_source_row'])
        if key in seen:
            continue
        seen.add(key)
        copy = dict(row)
        copy['_example_label'] = 'additional_near_miss'
        selected.append(copy)
    return selected


def select_candidates(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    requested = parse_int_list(args.candidate_rows)
    if requested:
        by_row = {int(r['_source_row']): r for r in rows}
        missing = [i for i in requested if i not in by_row]
        if missing:
            raise ValueError(f'Candidate row(s) not found: {missing}')
        out = []
        for i in requested:
            copy = dict(by_row[i])
            copy['_example_label'] = f'row_{i:03d}'
            out.append(copy)
        return out
    return auto_select_examples(rows)


# ---------------------------------------------------------------------------
# Frozen residual family R(lambda, q)
# ---------------------------------------------------------------------------

class FrozenTorqueContinuation:
    """One frozen state with one boundary torque used as continuation parameter."""

    def __init__(
        self,
        *,
        decoded,
        library,
        reference_mode,
        recipe: dict[str, Any],
        tp0: float,
        ts0: float,
        vary: str,
        q_scale: float,
        basis_step: float,
    ) -> None:
        self.decoded = decoded
        self.library = library
        self.reference_mode = reference_mode
        self.recipe = recipe
        self.tp0 = float(tp0)
        self.ts0 = float(ts0)
        self.vary = str(vary)
        self.q_scale = float(q_scale)
        self.basis_step = float(basis_step)

        if self.vary == 'primary':
            self.q0 = self.tp0
            self.fixed = self.ts0
            self.base_bundle = global_search.closure_bundle(
                decoded, library, recipe, self.q0, self.fixed, reference_mode
            )
            self.basis_bundle = global_search.closure_bundle(
                decoded, library, recipe, self.q0 + self.basis_step, self.fixed, reference_mode
            )
        elif self.vary == 'secondary':
            self.q0 = self.ts0
            self.fixed = self.tp0
            self.base_bundle = global_search.closure_bundle(
                decoded, library, recipe, self.fixed, self.q0, reference_mode
            )
            self.basis_bundle = global_search.closure_bundle(
                decoded, library, recipe, self.fixed, self.q0 + self.basis_step, reference_mode
            )
        else:
            raise ValueError(vary)

    @property
    def q_name(self) -> str:
        return 'T_p' if self.vary == 'primary' else 'T_s'

    def torques(self, q: float) -> tuple[float, float]:
        if self.vary == 'primary':
            return float(q), self.ts0
        return self.tp0, float(q)

    def bundle(self, q: float):
        tp, ts = self.torques(q)
        return global_search.closure_bundle(
            self.decoded, self.library, self.recipe, tp, ts, self.reference_mode
        )

    def _residual_at_bundle(self, bundle, lp: float, ls: float) -> np.ndarray:
        return base.evaluate_residual(bundle.closure, float(lp), float(ls))

    def torque_gain(self, lp: float, ls: float) -> np.ndarray:
        r0 = self._residual_at_bundle(self.base_bundle, lp, ls)
        r1 = self._residual_at_bundle(self.basis_bundle, lp, ls)
        return (r1 - r0) / self.basis_step

    def residual(self, lp: float, ls: float, q: float) -> np.ndarray:
        # External torque enters the rotational closure row additively, so this
        # interpolation is exact (to floating-point roundoff) for a frozen state.
        r0 = self._residual_at_bundle(self.base_bundle, lp, ls)
        return r0 + self.torque_gain(lp, ls) * (float(q) - self.q0)

    def u_from(self, lp: float, ls: float, q: float) -> np.ndarray:
        return np.asarray([float(lp), float(ls), float(q) / self.q_scale], dtype=float)

    def unpack_u(self, u: np.ndarray) -> tuple[float, float, float]:
        return float(u[0]), float(u[1]), float(u[2] * self.q_scale)

    def residual_u(self, u: np.ndarray) -> np.ndarray:
        lp, ls, q = self.unpack_u(u)
        return self.residual(lp, ls, q)

    def jacobian_u(self, u: np.ndarray, h_lambda: float) -> np.ndarray:
        lp, ls, q = self.unpack_u(u)
        h = float(h_lambda)
        dlp = (self.residual(lp + h, ls, q) - self.residual(lp - h, ls, q)) / (2.0 * h)
        dls = (self.residual(lp, ls + h, q) - self.residual(lp, ls - h, q)) / (2.0 * h)
        dq_scaled = self.q_scale * self.torque_gain(lp, ls)
        return np.column_stack((dlp, dls, dq_scaled))

    def tangent(self, u: np.ndarray, h_lambda: float) -> np.ndarray:
        J = self.jacobian_u(u, h_lambda)
        _U, _s, Vt = np.linalg.svd(J, full_matrices=True)
        t = np.asarray(Vt[-1, :], dtype=float)
        norm = float(np.linalg.norm(t))
        if norm <= 0.0 or not np.isfinite(norm):
            raise RuntimeError('Could not construct pseudo-arclength tangent.')
        return t / norm


# ---------------------------------------------------------------------------
# Point diagnostics / failure classification
# ---------------------------------------------------------------------------

def failure_label(code: int, p_static: float, s_static: float) -> str:
    failures: list[str] = []
    if p_static < 0.0:
        failures.append('primary_static_capacity')
    if s_static < 0.0:
        failures.append('secondary_static_capacity')
    if code & 1:
        failures.append('negative_integrated_normal')
    if code & 2:
        failures.append('negative_belt_tension')
    if code & 4:
        failures.append('local_wrap_liftoff')
    if code & 8:
        failures.append('unilateral_mechanism')
    if code & 16:
        failures.append('stop_support_pull')
    return 'physical' if not failures else '+'.join(failures)


def crossing_angle_deg(J: np.ndarray) -> float:
    g1 = np.asarray(J[0, :], dtype=float)
    g2 = np.asarray(J[1, :], dtype=float)
    denom = float(np.linalg.norm(g1) * np.linalg.norm(g2))
    if denom <= 0.0 or not np.isfinite(denom):
        return float('nan')
    s = abs(float(np.linalg.det(J))) / denom
    s = min(1.0, max(0.0, s))
    return float(math.degrees(math.asin(s)))


def root_jacobian(problem: FrozenTorqueContinuation, lp: float, ls: float, q: float, h: float) -> np.ndarray:
    h = float(h)
    col_p = (problem.residual(lp + h, ls, q) - problem.residual(lp - h, ls, q)) / (2.0 * h)
    col_s = (problem.residual(lp, ls + h, q) - problem.residual(lp, ls - h, q)) / (2.0 * h)
    return np.column_stack((col_p, col_s))


def diagnose_point(
    problem: FrozenTorqueContinuation,
    *,
    lp: float,
    ls: float,
    q: float,
    branch: str,
    signed_arclength: float,
    curve_index: int,
    args: argparse.Namespace,
) -> dict[str, Any]:
    tp, ts = problem.torques(q)
    row: dict[str, Any] = {
        'branch': branch,
        'curve_index': int(curve_index),
        'signed_arclength': float(signed_arclength),
        'varied_torque': problem.vary,
        'continued_torque_Nm': float(q),
        'primary_external_torque_Nm': float(tp),
        'secondary_external_torque_Nm': float(ts),
        'lambda_p': float(lp),
        'lambda_s': float(ls),
    }

    J = root_jacobian(problem, lp, ls, q, float(args.lambda_jacobian_step))
    row.update({
        'J_det': float(np.linalg.det(J)),
        'J_condition': float(np.linalg.cond(J)),
        'crossing_angle_deg': crossing_angle_deg(J),
        'stick_residual_norm': float(np.linalg.norm(problem.residual(lp, ls, q))),
    })

    try:
        bundle = problem.bundle(q)
        util = ContactTractionUtilization(primary_lambda=float(lp), secondary_lambda=float(ls))
        trial = bundle.closure.evaluate_trial(
            traction_utilization=util,
            maximum_closure_condition_number=None,
            capture_diagnostics=True,
        )
        code, extra = cc_run.topology_failure_code(
            bundle.ref, bundle.sample, trial, util, bundle.snapshot
        )
        unknowns = trial.closure.unknowns
        law = bundle.system.cvt.traction_law
        p_margin = float(law.static_margin_at(ContactInterface.PRIMARY, lp))
        s_margin = float(law.static_margin_at(ContactInterface.SECONDARY, ls))
        physical = bool(
            code == 0
            and p_margin >= float(args.minimum_static_margin)
            and s_margin >= float(args.minimum_static_margin)
            and float(unknowns.primary_normal_resultant) >= float(args.minimum_normal_N)
            and float(unknowns.secondary_normal_resultant) >= float(args.minimum_normal_N)
        )
        row.update({
            'closure_evaluation_ok': True,
            'physical': physical,
            'topology_failure_code': int(code),
            'failure_label': failure_label(int(code), p_margin, s_margin),
            'primary_static_margin': p_margin,
            'secondary_static_margin': s_margin,
            'minimum_static_margin': min(p_margin, s_margin),
            'primary_normal_N': float(unknowns.primary_normal_resultant),
            'secondary_normal_N': float(unknowns.secondary_normal_resultant),
            'primary_interface_torque_Nm': float(unknowns.primary_torque),
            'secondary_interface_torque_Nm': float(unknowns.secondary_torque),
            'primary_angular_acceleration_rad_s2': float(unknowns.primary_angular_acceleration),
            'secondary_angular_acceleration_rad_s2': float(unknowns.secondary_angular_acceleration),
            'belt_acceleration_m_s2': float(unknowns.belt_acceleration),
            'shift_acceleration_m_s2': float(unknowns.shift_acceleration),
            'minimum_belt_tension_N': float(extra['min_belt_tension']),
            'primary_min_local_normal': float(extra['min_local_normal_p']),
            'secondary_min_local_normal': float(extra['min_local_normal_s']),
            'minimum_local_normal': min(float(extra['min_local_normal_p']), float(extra['min_local_normal_s'])),
            'mechanism_margin': float(extra['mechanism_margin']),
            'A_condition_scaled': float(trial.closure.scaled_condition_number),
        })
    except Exception as exc:
        row.update({
            'closure_evaluation_ok': False,
            'physical': False,
            'topology_failure_code': -1,
            'failure_label': f'closure_eval_failure:{type(exc).__name__}',
            'primary_static_margin': np.nan,
            'secondary_static_margin': np.nan,
            'minimum_static_margin': np.nan,
            'primary_normal_N': np.nan,
            'secondary_normal_N': np.nan,
            'primary_interface_torque_Nm': np.nan,
            'secondary_interface_torque_Nm': np.nan,
            'primary_angular_acceleration_rad_s2': np.nan,
            'secondary_angular_acceleration_rad_s2': np.nan,
            'belt_acceleration_m_s2': np.nan,
            'shift_acceleration_m_s2': np.nan,
            'minimum_belt_tension_N': np.nan,
            'primary_min_local_normal': np.nan,
            'secondary_min_local_normal': np.nan,
            'minimum_local_normal': np.nan,
            'mechanism_margin': np.nan,
            'A_condition_scaled': np.nan,
        })
    return row


# ---------------------------------------------------------------------------
# Pseudo-arclength continuation
# ---------------------------------------------------------------------------

def corrector(
    problem: FrozenTorqueContinuation,
    u_pred: np.ndarray,
    tangent: np.ndarray,
    args: argparse.Namespace,
) -> tuple[bool, np.ndarray, float, int]:
    scale = float(args.residual_scale)

    def augmented(u: np.ndarray) -> np.ndarray:
        R = problem.residual_u(u) / scale
        arc = float(np.dot(u - u_pred, tangent))
        return np.asarray([R[0], R[1], arc], dtype=float)

    sol = scipy_root(
        augmented,
        np.asarray(u_pred, dtype=float),
        method='hybr',
        options={
            'xtol': 1.0e-10,
            'maxfev': int(args.max_corrector_evaluations),
        },
    )
    u = np.asarray(sol.x, dtype=float)
    raw_residual = float(np.linalg.norm(problem.residual_u(u)))
    arc_error = abs(float(np.dot(u - u_pred, tangent)))
    ok = bool(
        np.all(np.isfinite(u))
        and raw_residual <= float(args.root_residual_tolerance)
        and arc_error <= float(args.arc_tolerance)
    )
    return ok, u, raw_residual, int(getattr(sol, 'nfev', -1))


def trace_direction(
    problem: FrozenTorqueContinuation,
    *,
    lp0: float,
    ls0: float,
    direction: int,
    args: argparse.Namespace,
) -> list[dict[str, float]]:
    if direction not in (-1, +1):
        raise ValueError(direction)

    u = problem.u_from(lp0, ls0, problem.q0)
    t = problem.tangent(u, float(args.lambda_jacobian_step))
    # Initial orientation uses the torque coordinate whenever possible.
    if t[2] * direction < 0.0:
        t = -t

    points = [{
        'lp': float(lp0),
        'ls': float(ls0),
        'q': float(problem.q0),
        'signed_arclength': 0.0,
        'corrector_nfev': 0,
        'corrector_residual_norm': float(np.linalg.norm(problem.residual(lp0, ls0, problem.q0))),
        'step_size': 0.0,
    }]

    base_ds = float(args.arclength_step)
    ds_current = base_ds
    signed_arc = 0.0

    for _step in range(int(args.steps_per_direction)):
        success = False
        ds_try = ds_current
        corrected = None
        raw_res = float('nan')
        nfev = -1

        for _halve in range(int(args.max_step_halvings) + 1):
            u_pred = u + ds_try * t
            ok, u_new, raw_res, nfev = corrector(problem, u_pred, t, args)
            if ok:
                corrected = u_new
                success = True
                break
            ds_try *= 0.5
            if ds_try < float(args.minimum_arclength_step):
                break

        if not success or corrected is None:
            break

        lp, ls, q = problem.unpack_u(corrected)
        if abs(q - problem.q0) > float(args.torque_span_Nm):
            break
        if abs(q) > float(args.absolute_torque_limit_Nm):
            break
        if max(abs(lp), abs(ls)) > float(args.expanded_lambda_limit):
            break

        signed_arc += direction * ds_try
        points.append({
            'lp': lp,
            'ls': ls,
            'q': q,
            'signed_arclength': signed_arc,
            'corrector_nfev': nfev,
            'corrector_residual_norm': raw_res,
            'step_size': ds_try,
        })

        t_new = problem.tangent(corrected, float(args.lambda_jacobian_step))
        if float(np.dot(t_new, t)) < 0.0:
            t_new = -t_new
        u = corrected
        t = t_new
        ds_current = min(base_ds, ds_try * 1.25)

    return points


def combine_directions(negative: list[dict[str, float]], positive: list[dict[str, float]]) -> list[dict[str, float]]:
    # Both lists include the start. Reverse the negative trace so the combined
    # list is ordered by signed arclength from negative -> zero -> positive.
    left = list(reversed(negative))
    right = positive[1:]
    return left + right


def add_step_diagnostics(rows: list[dict[str, Any]]) -> None:
    previous = None
    for row in rows:
        if previous is None:
            row.update({
                'delta_lambda_norm': 0.0,
                'delta_force_norm': 0.0,
                'delta_acceleration_norm': 0.0,
            })
        else:
            row['delta_lambda_norm'] = float(np.hypot(
                float(row['lambda_p']) - float(previous['lambda_p']),
                float(row['lambda_s']) - float(previous['lambda_s']),
            ))
            if all(np.isfinite([
                row.get('primary_normal_N', np.nan), row.get('secondary_normal_N', np.nan),
                row.get('primary_interface_torque_Nm', np.nan), row.get('secondary_interface_torque_Nm', np.nan),
                previous.get('primary_normal_N', np.nan), previous.get('secondary_normal_N', np.nan),
                previous.get('primary_interface_torque_Nm', np.nan), previous.get('secondary_interface_torque_Nm', np.nan),
            ])):
                row['delta_force_norm'] = float(np.linalg.norm([
                    float(row['primary_normal_N']) - float(previous['primary_normal_N']),
                    float(row['secondary_normal_N']) - float(previous['secondary_normal_N']),
                    float(row['primary_interface_torque_Nm']) - float(previous['primary_interface_torque_Nm']),
                    float(row['secondary_interface_torque_Nm']) - float(previous['secondary_interface_torque_Nm']),
                ]))
            else:
                row['delta_force_norm'] = np.nan
            if all(np.isfinite([
                row.get('primary_angular_acceleration_rad_s2', np.nan),
                row.get('secondary_angular_acceleration_rad_s2', np.nan),
                row.get('belt_acceleration_m_s2', np.nan),
                row.get('shift_acceleration_m_s2', np.nan),
                previous.get('primary_angular_acceleration_rad_s2', np.nan),
                previous.get('secondary_angular_acceleration_rad_s2', np.nan),
                previous.get('belt_acceleration_m_s2', np.nan),
                previous.get('shift_acceleration_m_s2', np.nan),
            ])):
                row['delta_acceleration_norm'] = float(np.linalg.norm([
                    float(row['primary_angular_acceleration_rad_s2']) - float(previous['primary_angular_acceleration_rad_s2']),
                    float(row['secondary_angular_acceleration_rad_s2']) - float(previous['secondary_angular_acceleration_rad_s2']),
                    float(row['belt_acceleration_m_s2']) - float(previous['belt_acceleration_m_s2']),
                    float(row['shift_acceleration_m_s2']) - float(previous['shift_acceleration_m_s2']),
                ]))
            else:
                row['delta_acceleration_norm'] = np.nan
        previous = row


def trace_branch(
    problem: FrozenTorqueContinuation,
    *,
    branch: str,
    lp0: float,
    ls0: float,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    neg = trace_direction(problem, lp0=lp0, ls0=ls0, direction=-1, args=args)
    pos = trace_direction(problem, lp0=lp0, ls0=ls0, direction=+1, args=args)
    combined = combine_directions(neg, pos)
    rows = []
    for index, point in enumerate(combined):
        row = diagnose_point(
            problem,
            lp=point['lp'],
            ls=point['ls'],
            q=point['q'],
            branch=branch,
            signed_arclength=point['signed_arclength'],
            curve_index=index,
            args=args,
        )
        row.update({
            'corrector_nfev': int(point['corrector_nfev']),
            'corrector_residual_norm': float(point['corrector_residual_norm']),
            'arclength_step_used': float(point['step_size']),
        })
        rows.append(row)
    add_step_diagnostics(rows)
    return rows


# ---------------------------------------------------------------------------
# Curve summaries / plots
# ---------------------------------------------------------------------------

def count_folds(rows: list[dict[str, Any]]) -> int:
    q = np.asarray([float(r['continued_torque_Nm']) for r in rows], dtype=float)
    if q.size < 4:
        return 0
    dq = np.diff(q)
    # Ignore tiny numerical reversals.
    eps = max(1.0e-7, 1.0e-5 * max(1.0, float(np.nanmax(np.abs(q)))))
    signs = np.sign(np.where(np.abs(dq) < eps, 0.0, dq))
    signs = signs[signs != 0.0]
    if signs.size < 2:
        return 0
    return int(np.count_nonzero(signs[1:] * signs[:-1] < 0.0))


def curve_distance(rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]], q_scale: float) -> float:
    A = np.asarray([
        [float(r['lambda_p']), float(r['lambda_s']), float(r['continued_torque_Nm']) / q_scale]
        for r in rows_a
    ], dtype=float)
    B = np.asarray([
        [float(r['lambda_p']), float(r['lambda_s']), float(r['continued_torque_Nm']) / q_scale]
        for r in rows_b
    ], dtype=float)
    if not len(A) or not len(B):
        return float('nan')
    tree = cKDTree(B)
    d, _ = tree.query(A, k=1)
    return float(np.min(d))


def start_to_other_curve_distance(
    rows: list[dict[str, Any]], target_lp: float, target_ls: float, q0: float, q_scale: float
) -> float:
    A = np.asarray([
        [float(r['lambda_p']), float(r['lambda_s']), float(r['continued_torque_Nm']) / q_scale]
        for r in rows
    ], dtype=float)
    target = np.asarray([target_lp, target_ls, q0 / q_scale], dtype=float)
    return float(np.min(np.linalg.norm(A - target, axis=1)))


def plot_continuation_4x2(rows_a, rows_b, problem, title, path: Path) -> None:
    panels = [
        ('lambda_p', r'$\lambda_p$'),
        ('lambda_s', r'$\lambda_s$'),
        ('primary_normal_N', r'$N_p$ [N]'),
        ('secondary_normal_N', r'$N_s$ [N]'),
        ('primary_interface_torque_Nm', r'$\tau_p$ [Nm]'),
        ('secondary_interface_torque_Nm', r'$\tau_s$ [Nm]'),
        ('shift_acceleration_m_s2', r'$\ddot{s}$ [m/s$^2$]'),
        ('minimum_static_margin', 'minimum static margin'),
    ]
    fig, axes = plt.subplots(2, 4, figsize=(18, 9.2), constrained_layout=True)
    for ax, (key, ylabel) in zip(axes.ravel(), panels):
        for branch_name, rows in [('A', rows_a), ('B', rows_b)]:
            q = np.asarray([r['continued_torque_Nm'] for r in rows], dtype=float)
            y = np.asarray([r.get(key, np.nan) for r in rows], dtype=float)
            ax.plot(q, y, marker='.', ms=2.5, linewidth=1.0, label=f'branch {branch_name}')
            bad = np.asarray([not bool(r.get('physical', False)) for r in rows], dtype=bool)
            if np.any(bad):
                ax.scatter(q[bad], y[bad], marker='x', s=18)
        if key == 'minimum_static_margin':
            ax.axhline(0.0, linestyle='--', linewidth=1.0)
        ax.axvline(problem.q0, linestyle=':', linewidth=1.0)
        ax.set_xlabel(f'{problem.q_name} [Nm]')
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25)
    axes.ravel()[0].legend()
    fig.suptitle(title + '\nX markers denote algebraic continuation points that are physically inadmissible.')
    fig.savefig(path, dpi=185)
    plt.close(fig)


def plot_admissibility(rows_a, rows_b, problem, title, path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    for branch_name, rows in [('A', rows_a), ('B', rows_b)]:
        q = np.asarray([r['continued_torque_Nm'] for r in rows], dtype=float)
        axes[0,0].plot(q, [r.get('primary_static_margin', np.nan) for r in rows], label=f'{branch_name}: primary')
        axes[0,0].plot(q, [r.get('secondary_static_margin', np.nan) for r in rows], linestyle='--', label=f'{branch_name}: secondary')
        axes[0,1].plot(q, [r.get('primary_min_local_normal', np.nan) for r in rows], label=f'{branch_name}: primary')
        axes[0,1].plot(q, [r.get('secondary_min_local_normal', np.nan) for r in rows], linestyle='--', label=f'{branch_name}: secondary')
        axes[1,0].plot(q, [r.get('mechanism_margin', np.nan) for r in rows], label=f'branch {branch_name}')
        axes[1,1].plot(q, [r.get('minimum_belt_tension_N', np.nan) for r in rows], label=f'branch {branch_name}')

    titles = [
        'Static-friction margins',
        'Minimum local wrap normal',
        'Unilateral mechanism margin',
        'Minimum belt tension',
    ]
    ylabels = ['margin', 'local normal', 'mechanism margin', 'tension [N]']
    for ax, panel_title, ylabel in zip(axes.ravel(), titles, ylabels):
        ax.axhline(0.0, linestyle='--', linewidth=1.0)
        ax.axvline(problem.q0, linestyle=':', linewidth=1.0)
        ax.set_title(panel_title)
        ax.set_xlabel(f'{problem.q_name} [Nm]')
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle(title)
    fig.savefig(path, dpi=185)
    plt.close(fig)


def plot_lambda_plane(rows_a, rows_b, problem, title, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 7.5))
    law = problem.base_bundle.system.cvt.traction_law
    p0, p1 = law.primary_static_interval.lower, law.primary_static_interval.upper
    s0, s1 = law.secondary_static_interval.lower, law.secondary_static_interval.upper
    ax.add_patch(Rectangle((p0, s0), p1-p0, s1-s0, fill=False, linestyle='--', linewidth=1.3))

    for branch_name, rows in [('A', rows_a), ('B', rows_b)]:
        lp = np.asarray([r['lambda_p'] for r in rows], dtype=float)
        ls = np.asarray([r['lambda_s'] for r in rows], dtype=float)
        ax.plot(lp, ls, marker='.', ms=2.5, linewidth=1.0, label=f'branch {branch_name}')
        physical = np.asarray([bool(r.get('physical', False)) for r in rows], dtype=bool)
        if np.any(~physical):
            ax.scatter(lp[~physical], ls[~physical], marker='x', s=20)
        zero_i = int(np.argmin(np.abs(np.asarray([r['signed_arclength'] for r in rows], dtype=float))))
        ax.scatter([lp[zero_i]], [ls[zero_i]], marker='s', s=75)
        ax.annotate(f'{branch_name} start', (lp[zero_i], ls[zero_i]), xytext=(5,5), textcoords='offset points')

    ax.set_xlabel(r'$\lambda_p$')
    ax.set_ylabel(r'$\lambda_s$')
    ax.set_title(title + '\nDashed rectangle = physical static-friction box; X = inadmissible algebraic continuation.')
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.savefig(path, dpi=190, bbox_inches='tight')
    plt.close(fig)


def plot_jump_diagnostics(rows_a, rows_b, problem, title, path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), constrained_layout=True)
    specs = [
        ('delta_lambda_norm', r'$\|\Delta\lambda\|$'),
        ('delta_force_norm', 'closure force/torque step norm'),
        ('delta_acceleration_norm', 'acceleration step norm'),
    ]
    for ax, (key, ylabel) in zip(axes, specs):
        for branch_name, rows in [('A', rows_a), ('B', rows_b)]:
            q = np.asarray([r['continued_torque_Nm'] for r in rows], dtype=float)
            y = np.asarray([r.get(key, np.nan) for r in rows], dtype=float)
            ax.plot(q, y, marker='.', ms=2.5, linewidth=1.0, label=f'branch {branch_name}')
        ax.axvline(problem.q0, linestyle=':', linewidth=1.0)
        ax.set_xlabel(f'{problem.q_name} [Nm]')
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25)
        ax.legend()
    fig.suptitle(title + '\nPrototype diagnostics for detecting a nonlocal algebraic branch hop.')
    fig.savefig(path, dpi=185)
    plt.close(fig)


def summarize_failure_transitions(rows: list[dict[str, Any]], branch: str) -> list[dict[str, Any]]:
    events = []
    previous = None
    for row in rows:
        label = str(row.get('failure_label', ''))
        if previous is None or label != previous:
            events.append({
                'branch': branch,
                'curve_index': row['curve_index'],
                'continued_torque_Nm': row['continued_torque_Nm'],
                'lambda_p': row['lambda_p'],
                'lambda_s': row['lambda_s'],
                'failure_label': label,
                'topology_failure_code': row.get('topology_failure_code', ''),
                'minimum_static_margin': row.get('minimum_static_margin', ''),
                'minimum_local_normal': row.get('minimum_local_normal', ''),
                'mechanism_margin': row.get('mechanism_margin', ''),
                'minimum_belt_tension_N': row.get('minimum_belt_tension_N', ''),
            })
            previous = label
    return events


# ---------------------------------------------------------------------------
# One candidate / one continued torque
# ---------------------------------------------------------------------------

def run_one_continuation(decoded, library, reference_mode, candidate, vary, outdir, args):
    recipe = global_search.rebuild_recipe_from_candidate(candidate)
    tp0 = num(candidate, 'refined_Tp_Nm')
    ts0 = num(candidate, 'refined_Ts_Nm')
    problem = FrozenTorqueContinuation(
        decoded=decoded,
        library=library,
        reference_mode=reference_mode,
        recipe=recipe,
        tp0=tp0,
        ts0=ts0,
        vary=vary,
        q_scale=float(args.torque_scale_Nm),
        basis_step=float(args.torque_basis_step_Nm),
    )

    roots = {
        'A': (num(candidate, 'root1_lambda_p'), num(candidate, 'root1_lambda_s')),
        'B': (num(candidate, 'root2_lambda_p'), num(candidate, 'root2_lambda_s')),
    }
    rows_a = trace_branch(problem, branch='A', lp0=roots['A'][0], ls0=roots['A'][1], args=args)
    rows_b = trace_branch(problem, branch='B', lp0=roots['B'][0], ls0=roots['B'][1], args=args)

    write_rows(outdir / 'branch_A.csv', rows_a)
    write_rows(outdir / 'branch_B.csv', rows_b)
    write_rows(outdir / 'failure_transitions.csv',
               summarize_failure_transitions(rows_a, 'A') + summarize_failure_transitions(rows_b, 'B'))

    min_curve_dist = curve_distance(rows_a, rows_b, float(args.torque_scale_Nm))
    a_to_b = start_to_other_curve_distance(
        rows_a, roots['B'][0], roots['B'][1], problem.q0, float(args.torque_scale_Nm)
    )
    b_to_a = start_to_other_curve_distance(
        rows_b, roots['A'][0], roots['A'][1], problem.q0, float(args.torque_scale_Nm)
    )
    summary = {
        'example_label': candidate.get('_example_label', ''),
        'source_row': candidate.get('_source_row', ''),
        'state_id': candidate.get('state_id', ''),
        'varied_torque': vary,
        'initial_primary_external_torque_Nm': tp0,
        'initial_secondary_external_torque_Nm': ts0,
        'initial_root_separation': float(candidate.get('root_separation', np.nan)),
        'branch_A_point_count': len(rows_a),
        'branch_B_point_count': len(rows_b),
        'branch_A_fold_count': count_folds(rows_a),
        'branch_B_fold_count': count_folds(rows_b),
        'minimum_scaled_curve_distance': min_curve_dist,
        'branch_A_distance_to_B_start_scaled': a_to_b,
        'branch_B_distance_to_A_start_scaled': b_to_a,
        'curves_overlap_within_tolerance': bool(min_curve_dist <= float(args.curve_merge_tolerance)),
        'branch_A_q_min_Nm': min(float(r['continued_torque_Nm']) for r in rows_a),
        'branch_A_q_max_Nm': max(float(r['continued_torque_Nm']) for r in rows_a),
        'branch_B_q_min_Nm': min(float(r['continued_torque_Nm']) for r in rows_b),
        'branch_B_q_max_Nm': max(float(r['continued_torque_Nm']) for r in rows_b),
        'branch_A_physical_fraction': float(np.mean([bool(r['physical']) for r in rows_a])),
        'branch_B_physical_fraction': float(np.mean([bool(r['physical']) for r in rows_b])),
    }
    write_rows(outdir / 'continuation_summary.csv', [summary])

    title = (
        f"{candidate.get('_example_label','candidate')} | {candidate.get('state_id','')} | "
        f"continue {problem.q_name}; other boundary torque fixed"
    )
    plot_continuation_4x2(rows_a, rows_b, problem, title, outdir / 'continuation_4x2.png')
    plot_admissibility(rows_a, rows_b, problem, title, outdir / 'admissibility_2x2.png')
    plot_lambda_plane(rows_a, rows_b, problem, title, outdir / 'lambda_plane.png')
    plot_jump_diagnostics(rows_a, rows_b, problem, title, outdir / 'jump_diagnostics.png')
    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()
    cc_run.verify_environment()

    search_dir = args.global_search_dir.resolve()
    candidate_path = search_dir / 'comfort_audit_results.csv'
    if not candidate_path.exists():
        raise FileNotFoundError(f'Could not find {candidate_path}')

    candidates = read_rows(candidate_path)
    selected = select_candidates(candidates, args)
    if not selected:
        raise SystemExit('No candidate rows selected.')

    decoded, library = controlled.load_base()
    reference_mode = global_search.reference_mode_from_path(
        decoded, library, args.reference_path_csv.resolve(), int(args.reference_frame)
    )

    out = args.output_dir.resolve() if args.output_dir else DEFAULT_OUTPUT
    out.mkdir(parents=True, exist_ok=True)
    write_rows(out / 'selected_candidates.csv', selected)

    vary_list = ['primary', 'secondary'] if args.vary == 'both' else [args.vary]
    print('=' * 92)
    print('MULTIROOT BRANCH CONTINUATION')
    print(f'Selected candidates: {len(selected)}')
    for row in selected:
        print(
            f"  row {int(row['_source_row']):03d}: {row.get('_example_label')} | "
            f"{row.get('state_id')} | T=({float(row['refined_Tp_Nm']):+.2f}, "
            f"{float(row['refined_Ts_Nm']):+.2f}) Nm | "
            f"roots sep={float(row['root_separation']):.3f}"
        )
    print(f'Continuation parameters: {", ".join(vary_list)}')
    print()

    all_summaries = []
    for i, candidate in enumerate(selected, start=1):
        label = str(candidate.get('_example_label', f'candidate_{i:02d}'))
        cdir = out / f"candidate_{i:02d}_row_{int(candidate['_source_row']):03d}_{label}"
        cdir.mkdir(parents=True, exist_ok=True)
        write_rows(cdir / 'candidate.csv', [candidate])

        for vary in vary_list:
            vdir = cdir / f'vary_{vary}_torque'
            vdir.mkdir(parents=True, exist_ok=True)
            print(f'Candidate {i}/{len(selected)} ({label}), varying {vary} torque...')
            summary = run_one_continuation(
                decoded, library, reference_mode, candidate, vary, vdir, args
            )
            all_summaries.append(summary)
            print(
                f"  A points={summary['branch_A_point_count']}, folds={summary['branch_A_fold_count']}; "
                f"B points={summary['branch_B_point_count']}, folds={summary['branch_B_fold_count']}; "
                f"min curve distance={summary['minimum_scaled_curve_distance']:.4g}; "
                f"overlap={summary['curves_overlap_within_tolerance']}"
            )

    write_rows(out / 'all_continuation_summaries.csv', all_summaries)
    (out / 'README.txt').write_text(
        'Interpretation guide:\n'
        '  branch A = ordinary / root-1 solution from the global search candidate\n'
        '  branch B = alternate / root-2 solution\n'
        '  X markers in plots = algebraic closure still solved but physical admissibility failed\n'
        '  a torque turning point in a trace = fold with respect to that torque parameter\n'
        '  minimum_scaled_curve_distance near zero = the two root traces overlap / join in the '\
        'scaled (lambda_p, lambda_s, torque) continuation space\n'
        '\n'
        'The frozen mechanical state does not jump anywhere in this study. Force / acceleration '\
        'changes are therefore algebraic closure changes. The jump_diagnostics plot is a prototype '\
        'for detecting an unintended nonlocal root switch in a time simulation.\n',
        encoding='utf-8',
    )
    print()
    print(f'Complete. Outputs: {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
