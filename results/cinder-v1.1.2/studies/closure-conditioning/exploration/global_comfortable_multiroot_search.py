r"""Global coarse search for comfortably physical multiple stick-stick roots.

This is intentionally NOT centered on frame 60.

The previous comfortable-root helper only sampled a small neighborhood of the
turnaround state.  This study scans a broad user-defined envelope of the three
independent kinematic coordinates of a fully engaged stick-stick state:

    shift position s,
    shift speed s_dot,
    primary shaft speed omega_p.

For each state, CINDER's production representative-contact kinematics construct
the unique omega_s and belt speed v_b consistent with v_rel,p = v_rel,s = 0.
The shaft boundary torques are NOT gridded.  They are eliminated by the same
inverse-torque construction used in the earlier multiroot study:

    R(lambda, T) = R0(lambda) + G(lambda) T
    T_required(lambda) = -G(lambda)^(-1) R0(lambda).

Thus the search covers:
    state space  (s, s_dot, omega_p)
    x
    the complete physical static-friction lambda box,

while solving directly for the boundary torque pair that would make a trial
lambda point a stick root.

A candidate is only considered "comfortable" when BOTH roots:
  * are exact topology/static admissible,
  * are separated from each other,
  * have a clear transverse R_p=0 / R_s=0 crossing,
  * and have a finite lambda-space buffer to the nearest physical
    inadmissibility boundary.

High-resolution maps are created ONLY after a candidate passes those tests.

The final "expanded" plot is a true expanded-domain closure calculation:
`build_map(..., "expanded", ...)`. It is not an axis-limit change.

Typical run from results/cinder-v1.1.2:

    python .\studies\closure-conditioning\exploration/global_comfortable_multiroot_search.py `
      --reference-path-csv .\studies\closure-conditioning\artifacts\controlled-free-shift-animation\expanded_res641_locked_locked_path\preflight_path.csv `
      --reference-frame 60

Default global envelope:
  shift fractions: 0.05 ... 0.95
  shift speeds:   -40,-20,0,+20,+40 mm/s
  primary RPM:     1000,1500,2000,2500,3000,3500,4000
  lambda map:      25 x 25 physical static box per frozen state
  torque limit:    +/-300 Nm

That is 350 frozen states.  Use --jobs to parallelize the coarse scan.

This is a finite operating-envelope search, not a proof over an unbounded
continuous state space.  Widen the CLI ranges if you want a larger envelope.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, SymLogNorm, TwoSlopeNorm, ListedColormap
from matplotlib.patches import Rectangle
import numpy as np

import run as cc_run
import animate_controlled_free_shift_path as controlled
import search_multiroot_operating_point as base

from cinder.model.cvt.contact import ContactInterface, ContactTractionUtilization
from cinder.model.cvt.dynamics.engaged_contact import EngagedContactClosure
from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint


HERE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = HERE / "artifacts" / "global-comfortable-multiroot-search"

_WORKER_DECODED = None
_WORKER_LIBRARY = None
_WORKER_REFERENCE_MODE = None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference-path-csv", type=Path, required=True,
                   help="Any known-good locked path CSV, used only to supply a FREE/STICK_STICK mode object.")
    p.add_argument("--reference-frame", type=int, default=60)
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))

    # Global state-space envelope.
    p.add_argument("--shift-fractions", type=str,
                   default="0.05,0.15,0.25,0.35,0.45,0.55,0.65,0.75,0.85,0.95")
    p.add_argument("--shift-speeds-mm-s", type=str, default="-40,-20,0,20,40")
    p.add_argument("--primary-rpms", type=str, default="1000,1500,2000,2500,3000,3500,4000")
    p.add_argument("--max-secondary-rpm", type=float, default=7000.0,
                   help="Skip frozen kinematic states whose zero-relative-speed secondary RPM exceeds this magnitude.")
    p.add_argument("--max-belt-speed-m-s", type=float, default=50.0,
                   help="Skip frozen states whose belt speed exceeds this magnitude.")

    # Cheap inverse-torque / pair search.
    p.add_argument("--explore-resolution", type=int, default=25)
    p.add_argument("--torque-basis-step", type=float, default=1.0)
    p.add_argument("--torque-limit", type=float, default=300.0)
    p.add_argument("--max-torque-gain-condition", type=float, default=1.0e7)
    p.add_argument("--torque-match-radius", type=float, default=14.0)
    p.add_argument("--nearest-neighbours", type=int, default=16)
    p.add_argument("--minimum-seed-lambda-separation", type=float, default=0.10)
    p.add_argument("--seeds-per-state", type=int, default=5)
    p.add_argument("--candidate-torque-cluster-radius", type=float, default=8.0)
    p.add_argument("--local-torque-radius", type=float, default=12.0)
    p.add_argument("--local-torque-step", type=float, default=3.0)
    p.add_argument("--root-residual-tolerance", type=float, default=1.0e-6)
    p.add_argument("--root-cluster-tolerance", type=float, default=2.0e-4)

    # Comfort definition.
    p.add_argument("--minimum-root-separation", type=float, default=0.15)
    p.add_argument("--minimum-crossing-angle-deg", type=float, default=15.0)
    p.add_argument("--minimum-admissibility-radius", type=float, default=0.05)
    p.add_argument("--minimum-normal-N", type=float, default=50.0)
    p.add_argument("--minimum-static-margin", type=float, default=0.0)
    p.add_argument("--jacobian-step", type=float, default=1.0e-5)

    # Expensive radial audits are only run on a diverse global shortlist.
    p.add_argument("--comfort-audits", type=int, default=100)
    p.add_argument("--radius-directions", type=int, default=32)
    p.add_argument("--radius-max", type=float, default=0.20)
    p.add_argument("--radius-steps", type=int, default=12)
    p.add_argument("--radius-bisection-steps", type=int, default=9)

    # Finalization only after comfort tests pass.
    p.add_argument("--final-count", type=int, default=2)
    p.add_argument("--final-multistart", type=int, default=13)
    p.add_argument("--physical-resolution", type=int, default=401)
    p.add_argument("--expanded-resolution", type=int, default=401)
    return p.parse_args()


def parse_float_list(text: str) -> list[float]:
    return [float(token.strip()) for token in text.split(",") if token.strip()]


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def reference_mode_from_path(decoded, library, path: Path, frame: int):
    recipe = base.frozen_recipe(path.resolve(), int(frame))
    _, sample = controlled.make_ref_and_sample(decoded, library, recipe)
    return sample.composed_mode


def global_recipe(shift_fraction: float, shift_speed_mm_s: float, primary_rpm: float, state_index: int):
    return {
        "frame_no": int(state_index),
        "leg": "global_scan",
        "shift_fraction": float(shift_fraction),
        "shift_speed": float(shift_speed_mm_s) / 1000.0,
        "target_primary_rpm": float(primary_rpm),
        "target_belt_speed": None,
        "primary_torque_Nm": 0.0,
        "secondary_torque_Nm": 0.0,
        "state_id": (
            f"sf{shift_fraction:.3f}_sdot{shift_speed_mm_s:+.0f}_rpm{primary_rpm:.0f}"
            .replace("+", "p").replace("-", "m").replace(".", "p")
        ),
    }


def all_state_recipes(args: argparse.Namespace) -> list[dict[str, Any]]:
    shifts = parse_float_list(args.shift_fractions)
    speeds = parse_float_list(args.shift_speeds_mm_s)
    rpms = parse_float_list(args.primary_rpms)
    rows = []
    idx = 0
    for sf in shifts:
        if not 0.0 < sf < 1.0:
            raise ValueError(f"Shift fraction must be strictly inside (0,1): {sf}")
        for sdot in speeds:
            for rpm in rpms:
                if rpm == 0.0:
                    continue
                rows.append(global_recipe(sf, sdot, rpm, idx))
                idx += 1
    return rows


def closure_bundle(decoded, library, recipe: dict[str, Any], tp: float, ts: float, reference_mode):
    local = dict(recipe)
    local["primary_torque_Nm"] = float(tp)
    local["secondary_torque_Nm"] = float(ts)
    system = base.make_bench_system(
        decoded, library,
        primary_torque=float(tp),
        secondary_torque=float(ts),
    )
    cvt = controlled.state_for_recipe(system, local)
    state = base.full_state(system, cvt)
    boundaries = system._shaft_boundaries(time=0.0, state=state)
    snapshot = system.cvt.model.snapshot_at_time(
        time=0.0,
        state=cvt,
        shaft_boundaries=boundaries,
        geometry_side="engaged",
    )
    closure = EngagedContactClosure(
        snapshot=snapshot,
        shift_constraint=EngagedShiftConstraint.FREE,
    )
    ref = cc_run.ReferenceRun(
        name=f"global_{local['state_id']}",
        decoded=SimpleNamespace(system=system),
        result=None,
        samples=tuple(),
    )
    sample = cc_run.FrozenSample(
        time=0.0,
        full_state=np.asarray(state, dtype=float),
        composed_mode=reference_mode,
        cvt_state=cvt,
    )
    return SimpleNamespace(
        system=system,
        cvt=cvt,
        full_state=state,
        snapshot=snapshot,
        closure=closure,
        ref=ref,
        sample=sample,
        torque_p=float(tp),
        torque_s=float(ts),
    )


def evaluate_residual(bundle, lp: float, ls: float) -> np.ndarray:
    return base.evaluate_residual(bundle.closure, float(lp), float(ls))


def state_kinematics_valid(bundle, args_dict: dict[str, Any]) -> bool:
    rpm_s = abs(float(bundle.cvt.secondary_angular_speed) * 60.0 / (2.0 * math.pi))
    vb = abs(float(bundle.cvt.belt_speed))
    return rpm_s <= float(args_dict["max_secondary_rpm"]) and vb <= float(args_dict["max_belt_speed_m_s"])


def inverse_map(decoded, library, recipe, reference_mode, cfg: dict[str, Any]):
    dt = float(cfg["torque_basis_step"])
    b0 = closure_bundle(decoded, library, recipe, 0.0, 0.0, reference_mode)
    if not state_kinematics_valid(b0, cfg):
        return None, b0
    bp = closure_bundle(decoded, library, recipe, dt, 0.0, reference_mode)
    bs = closure_bundle(decoded, library, recipe, 0.0, dt, reference_mode)

    law = b0.system.cvt.traction_law
    lp_axis = np.linspace(
        law.primary_static_interval.lower,
        law.primary_static_interval.upper,
        int(cfg["explore_resolution"]),
    )
    ls_axis = np.linspace(
        law.secondary_static_interval.lower,
        law.secondary_static_interval.upper,
        int(cfg["explore_resolution"]),
    )
    shape = (len(ls_axis), len(lp_axis))
    tp_req = np.full(shape, np.nan)
    ts_req = np.full(shape, np.nan)
    gain_cond = np.full(shape, np.nan)

    for i, ls in enumerate(ls_axis):
        for j, lp in enumerate(lp_axis):
            try:
                r0 = evaluate_residual(b0, lp, ls)
                rp = evaluate_residual(bp, lp, ls)
                rs = evaluate_residual(bs, lp, ls)
                G = np.column_stack(((rp - r0) / dt, (rs - r0) / dt))
                cond = float(np.linalg.cond(G))
                gain_cond[i, j] = cond
                if not np.isfinite(cond) or cond > float(cfg["max_torque_gain_condition"]):
                    continue
                T = -np.linalg.solve(G, r0)
                if not np.all(np.isfinite(T)):
                    continue
                if max(abs(float(T[0])), abs(float(T[1]))) > float(cfg["torque_limit"]):
                    continue
                tp_req[i, j] = float(T[0])
                ts_req[i, j] = float(T[1])
            except Exception:
                continue

    return {
        "lambda_p": lp_axis,
        "lambda_s": ls_axis,
        "required_Tp": tp_req,
        "required_Ts": ts_req,
        "torque_gain_condition": gain_cond,
    }, b0


def seed_namespace(cfg: dict[str, Any]):
    return SimpleNamespace(
        nearest_neighbours=int(cfg["nearest_neighbours"]),
        torque_match_radius=float(cfg["torque_match_radius"]),
        minimum_seed_lambda_separation=float(cfg["minimum_seed_lambda_separation"]),
        candidate_torque_cluster_radius=float(cfg["candidate_torque_cluster_radius"]),
        verify_candidates=int(cfg["seeds_per_state"]),
    )


def refinement_namespace(cfg: dict[str, Any]):
    return SimpleNamespace(
        local_torque_radius=float(cfg["local_torque_radius"]),
        local_torque_step=float(cfg["local_torque_step"]),
        torque_limit=float(cfg["torque_limit"]),
        root_residual_tolerance=float(cfg["root_residual_tolerance"]),
        root_cluster_tolerance=float(cfg["root_cluster_tolerance"]),
        minimum_normal_N=float(cfg["minimum_normal_N"]),
        minimum_static_margin=float(cfg["minimum_static_margin"]),
    )


def root_jacobian(bundle, lp: float, ls: float, step: float) -> np.ndarray:
    rp = evaluate_residual(bundle, lp + step, ls)
    rm = evaluate_residual(bundle, lp - step, ls)
    sp = evaluate_residual(bundle, lp, ls + step)
    sm = evaluate_residual(bundle, lp, ls - step)
    return np.column_stack(((rp - rm) / (2.0 * step), (sp - sm) / (2.0 * step)))


def crossing_angle_deg(J: np.ndarray) -> float:
    g1 = np.asarray(J[0], dtype=float)
    g2 = np.asarray(J[1], dtype=float)
    denom = float(np.linalg.norm(g1) * np.linalg.norm(g2))
    if denom <= 0.0 or not np.isfinite(denom):
        return 0.0
    s = abs(float(np.linalg.det(J))) / denom
    s = min(1.0, max(0.0, s))
    return float(math.degrees(math.asin(s)))


def exact_root_metrics(bundle, row: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    roots = [
        (float(row["root1_lambda_p"]), float(row["root1_lambda_s"])),
        (float(row["root2_lambda_p"]), float(row["root2_lambda_s"])),
    ]
    min_angle = float("inf")
    min_static = float("inf")
    min_local = float("inf")
    min_mech = float("inf")
    both_physical = True

    for k, (lp, ls) in enumerate(roots, start=1):
        diag = base.physical_root_diagnostics(
            bundle,
            {"lambda_p": lp, "lambda_s": ls, "residual_norm": 0.0, "nfev": 0},
            SimpleNamespace(
                minimum_normal_N=float(cfg["minimum_normal_N"]),
                minimum_static_margin=float(cfg["minimum_static_margin"]),
            ),
        )
        J = root_jacobian(bundle, lp, ls, float(cfg["jacobian_step"]))
        angle = crossing_angle_deg(J)
        local = min(float(diag["min_local_normal_p"]), float(diag["min_local_normal_s"]))
        stat = min(float(diag["primary_static_margin"]), float(diag["secondary_static_margin"]))
        mech = float(diag["mechanism_margin"])
        min_angle = min(min_angle, angle)
        min_static = min(min_static, stat)
        min_local = min(min_local, local)
        min_mech = min(min_mech, mech)
        both_physical = both_physical and bool(diag["physical"])
        out.update({
            f"root{k}_crossing_angle_deg": angle,
            f"root{k}_static_margin_min": stat,
            f"root{k}_local_normal_min": local,
            f"root{k}_mechanism_margin": mech,
            f"root{k}_N_min": min(float(diag["N_p"]), float(diag["N_s"])),
            f"root{k}_A_condition_scaled": float(diag["A_condition_scaled"]),
            f"root{k}_J_condition": float(np.linalg.cond(J)),
        })

    out.update({
        "both_roots_physical_exact": bool(both_physical),
        "minimum_crossing_angle_deg": float(min_angle),
        "minimum_static_margin_exact": float(min_static),
        "minimum_local_normal_exact": float(min_local),
        "minimum_mechanism_margin_exact": float(min_mech),
    })
    return out


def worker_init(reference_path_csv: str, reference_frame: int):
    global _WORKER_DECODED, _WORKER_LIBRARY, _WORKER_REFERENCE_MODE
    _WORKER_DECODED, _WORKER_LIBRARY = controlled.load_base()
    _WORKER_REFERENCE_MODE = reference_mode_from_path(
        _WORKER_DECODED, _WORKER_LIBRARY, Path(reference_path_csv), int(reference_frame)
    )


def worker_state(recipe: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    try:
        inv, zero_bundle = inverse_map(
            _WORKER_DECODED, _WORKER_LIBRARY, recipe, _WORKER_REFERENCE_MODE, cfg
        )
        if inv is None:
            return {
                "state_id": recipe["state_id"],
                "status": "kinematic_envelope_rejected",
                "candidates": [],
            }

        seeds = base.coarse_seed_pairs(inv, seed_namespace(cfg))
        candidates = []
        for seed in seeds[:int(cfg["seeds_per_state"])]:
            refined = base.refine_seed_candidate(
                _WORKER_DECODED, _WORKER_LIBRARY, recipe, _WORKER_REFERENCE_MODE,
                seed, refinement_namespace(cfg),
            )
            if refined is None or int(refined["physical_root_count"]) < 2:
                continue

            bundle = closure_bundle(
                _WORKER_DECODED, _WORKER_LIBRARY, recipe,
                float(refined["refined_Tp_Nm"]), float(refined["refined_Ts_Nm"]),
                _WORKER_REFERENCE_MODE,
            )
            exact = exact_root_metrics(bundle, refined, cfg)
            exact.update({
                "state_id": recipe["state_id"],
                "shift_fraction": float(recipe["shift_fraction"]),
                "shift_speed_mm_s": 1000.0 * float(recipe["shift_speed"]),
                "target_primary_rpm": float(recipe["target_primary_rpm"]),
                "resolved_primary_rpm": float(bundle.cvt.primary_angular_speed) * 60.0 / (2.0 * math.pi),
                "resolved_secondary_rpm": float(bundle.cvt.secondary_angular_speed) * 60.0 / (2.0 * math.pi),
                "resolved_belt_speed_m_s": float(bundle.cvt.belt_speed),
            })
            candidates.append(exact)

        return {
            "state_id": recipe["state_id"],
            "status": "ok",
            "shift_fraction": float(recipe["shift_fraction"]),
            "shift_speed_mm_s": 1000.0 * float(recipe["shift_speed"]),
            "target_primary_rpm": float(recipe["target_primary_rpm"]),
            "candidate_count": len(candidates),
            "candidates": candidates,
        }
    except Exception as exc:
        return {
            "state_id": recipe["state_id"],
            "status": f"error:{type(exc).__name__}:{exc}",
            "candidates": [],
        }


def point_admissible(bundle, lp: float, ls: float, args: argparse.Namespace) -> bool:
    law = bundle.system.cvt.traction_law
    if not (
        law.primary_static_interval.lower <= lp <= law.primary_static_interval.upper
        and law.secondary_static_interval.lower <= ls <= law.secondary_static_interval.upper
    ):
        return False
    util = ContactTractionUtilization(primary_lambda=float(lp), secondary_lambda=float(ls))
    try:
        trial = bundle.closure.evaluate_trial(
            traction_utilization=util,
            maximum_closure_condition_number=None,
            capture_diagnostics=True,
        )
        code, _ = cc_run.topology_failure_code(
            bundle.ref, bundle.sample, trial, util, bundle.snapshot
        )
    except Exception:
        return False

    unknowns = trial.closure.unknowns
    return bool(
        code == 0
        and float(unknowns.primary_normal_resultant) >= float(args.minimum_normal_N)
        and float(unknowns.secondary_normal_resultant) >= float(args.minimum_normal_N)
        and float(law.static_margin_at(ContactInterface.PRIMARY, lp)) >= float(args.minimum_static_margin)
        and float(law.static_margin_at(ContactInterface.SECONDARY, ls)) >= float(args.minimum_static_margin)
    )


def admissibility_radius(bundle, lp: float, ls: float, args: argparse.Namespace) -> float:
    if not point_admissible(bundle, lp, ls, args):
        return 0.0
    ndir = max(8, int(args.radius_directions))
    rmax = float(args.radius_max)
    nsteps = max(2, int(args.radius_steps))
    nbis = max(0, int(args.radius_bisection_steps))
    dr = rmax / nsteps
    minimum = rmax

    for theta in np.linspace(0.0, 2.0 * math.pi, ndir, endpoint=False):
        dx, dy = math.cos(theta), math.sin(theta)
        prev = 0.0
        boundary = rmax
        for k in range(1, nsteps + 1):
            r = k * dr
            if not point_admissible(bundle, lp + r * dx, ls + r * dy, args):
                lo, hi = prev, r
                for _ in range(nbis):
                    mid = 0.5 * (lo + hi)
                    if point_admissible(bundle, lp + mid * dx, ls + mid * dy, args):
                        lo = mid
                    else:
                        hi = mid
                boundary = lo
                break
            prev = r
        minimum = min(minimum, boundary)
    return float(minimum)


def rebuild_recipe_from_candidate(row: dict[str, Any]) -> dict[str, Any]:
    return global_recipe(
        float(row["shift_fraction"]),
        float(row["shift_speed_mm_s"]),
        float(row["target_primary_rpm"]),
        0,
    )


def diverse_shortlist(candidates: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """Union several rankings so no single unit/margin dominates the shortlist."""
    selected = []
    seen = set()

    def add(sort_key, n):
        for row in sorted(candidates, key=sort_key, reverse=True)[:n]:
            key = (
                row["state_id"],
                round(float(row["refined_Tp_Nm"]), 5),
                round(float(row["refined_Ts_Nm"]), 5),
            )
            if key not in seen:
                seen.add(key)
                selected.append(row)

    n = max(10, count // 5)
    add(lambda r: float(r["minimum_crossing_angle_deg"]), n)
    add(lambda r: float(r["root_separation"]), n)
    add(lambda r: float(r["minimum_static_margin_exact"]), n)
    add(lambda r: float(r["minimum_local_normal_exact"]), n)
    add(lambda r: float(r["minimum_mechanism_margin_exact"]), n)

    # Fill remaining slots with lexicographically healthy rows.
    ordered = sorted(
        candidates,
        key=lambda r: (
            int(r["both_roots_physical_exact"]),
            float(r["minimum_crossing_angle_deg"]),
            float(r["minimum_static_margin_exact"]),
            float(r["root_separation"]),
        ),
        reverse=True,
    )
    for row in ordered:
        if len(selected) >= count:
            break
        key = (
            row["state_id"],
            round(float(row["refined_Tp_Nm"]), 5),
            round(float(row["refined_Ts_Nm"]), 5),
        )
        if key not in seen:
            seen.add(key)
            selected.append(row)
    return selected[:count]


def physical_static_box(ref):
    law = ref.decoded.system.cvt.traction_law
    return (
        law.primary_static_interval.lower,
        law.primary_static_interval.upper,
        law.secondary_static_interval.lower,
        law.secondary_static_interval.upper,
    )


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


def plot_4x2(data, roots, title: str, path: Path, *, ref, show_static_box: bool):
    lp, ls = data["lambda_p"], data["lambda_s"]
    LP, LS = np.meshgrid(lp, ls)
    invalid = ~np.asarray(data["topology_admissible"], dtype=bool)
    rp_lim = signed_limit(data["R_p"])
    rs_lim = signed_limit(data["R_s"])
    rn_lo, rn_hi = positive_limits(data["R_norm"])
    ca_lo, ca_hi = positive_limits(data["cond_A_scaled"])
    jm_lo, jm_hi = positive_limits(data["sigma_min_J"])
    jc_lo, jc_hi = positive_limits(data["kappa_J"])
    det_lim = signed_limit(data["det_J"])

    panels = [
        ("Rp", data["R_p"], SymLogNorm(linthresh=1.0, vmin=-rp_lim, vmax=rp_lim)),
        ("Rs", data["R_s"], SymLogNorm(linthresh=1.0, vmin=-rs_lim, vmax=rs_lim)),
        ("|R|", data["R_norm"], LogNorm(vmin=rn_lo, vmax=rn_hi)),
        ("kappa(A)", data["cond_A_scaled"], LogNorm(vmin=ca_lo, vmax=ca_hi)),
        ("sigma_min(J_R)", data["sigma_min_J"], LogNorm(vmin=jm_lo, vmax=jm_hi)),
        ("kappa(J_R)", data["kappa_J"], LogNorm(vmin=jc_lo, vmax=jc_hi)),
        ("det(J_R)", data["det_J"], TwoSlopeNorm(vcenter=0.0, vmin=-det_lim, vmax=det_lim)),
    ]

    fig, axes = plt.subplots(2, 4, figsize=(18, 9.4), constrained_layout=True)
    for ax, (name, source, norm) in zip(axes.ravel()[:7], panels):
        values = np.ma.masked_where(invalid, np.asarray(source, dtype=float))
        im = ax.pcolormesh(LP, LS, values, shading="auto", norm=norm, rasterized=True)
        try:
            ax.contour(LP, LS, data["R_p"], levels=[0.0], colors="black", linewidths=1.0)
            ax.contour(LP, LS, data["R_s"], levels=[0.0], colors="cyan", linewidths=1.0, linestyles="--")
        except ValueError:
            pass
        if show_static_box:
            p0, p1, s0, s1 = physical_static_box(ref)
            ax.add_patch(Rectangle(
                (p0, s0), p1-p0, s1-s0,
                fill=False, linestyle=":", linewidth=1.2, edgecolor="tab:blue"
            ))
        for k, root in enumerate(roots, start=1):
            ax.plot(root["lambda_p"], root["lambda_s"], "o", ms=7,
                    markerfacecolor="none", markeredgecolor="red", mew=1.6)
            ax.text(root["lambda_p"], root["lambda_s"], f" {k}", color="red", fontsize=8)
        ax.set_title(name)
        ax.set_xlabel(r"$\lambda_p$")
        ax.set_ylabel(r"$\lambda_s$")
        fig.colorbar(im, ax=ax, shrink=0.82)

    ax = axes.ravel()[7]
    code = np.asarray(data["topology_failure_code"], dtype=int)
    disp = np.zeros_like(code, dtype=int)
    disp[(code & 2) != 0] = 1
    disp[(code & 4) != 0] = 2
    disp[(code & 8) != 0] = 3
    disp[(code & 1) != 0] = 4
    cmap = ListedColormap(["white", "#4c78a8", "#f58518", "#54a24b", "#e45756"])
    ax.pcolormesh(LP, LS, disp, shading="auto", cmap=cmap, vmin=0, vmax=4, rasterized=True)
    if show_static_box:
        p0, p1, s0, s1 = physical_static_box(ref)
        ax.add_patch(Rectangle(
            (p0, s0), p1-p0, s1-s0,
            fill=False, linestyle=":", linewidth=1.2, edgecolor="tab:blue"
        ))
    for k, root in enumerate(roots, start=1):
        ax.plot(root["lambda_p"], root["lambda_s"], "o", ms=7,
                markerfacecolor="none", markeredgecolor="black", mew=1.6)
        ax.text(root["lambda_p"], root["lambda_s"], f" {k}", color="black", fontsize=8)
    ax.set_title("inadmissibility")
    ax.set_xlabel(r"$\lambda_p$")
    ax.set_ylabel(r"$\lambda_s$")

    fig.suptitle(title, fontsize=13)
    fig.savefig(path, dpi=190)
    plt.close(fig)


def finalize(decoded, library, reference_mode, row, outdir: Path, args: argparse.Namespace):
    recipe = rebuild_recipe_from_candidate(row)
    bundle = closure_bundle(
        decoded, library, recipe,
        float(row["refined_Tp_Nm"]), float(row["refined_Ts_Nm"]),
        reference_mode,
    )
    ms_rows, ms_roots = base.production_multistart(
        bundle,
        int(args.final_multistart),
        float(args.root_cluster_tolerance),
    )
    write_rows(outdir / "final_multistart.csv", ms_rows)
    write_rows(outdir / "final_root_diagnostics.csv", ms_roots)
    physical_roots = [r for r in ms_roots if bool(r["physical"])]
    if len(physical_roots) < 2:
        return {**row, "finalized": False, "reason": "multistart_less_than_two_physical"}

    # Use the widest separated pair from production multistart.
    pair = None
    separation = -1.0
    for i in range(len(physical_roots)):
        for j in range(i + 1, len(physical_roots)):
            d = float(np.hypot(
                physical_roots[i]["lambda_p"] - physical_roots[j]["lambda_p"],
                physical_roots[i]["lambda_s"] - physical_roots[j]["lambda_s"],
            ))
            if d > separation:
                separation = d
                pair = (physical_roots[i], physical_roots[j])
    assert pair is not None

    radii = [admissibility_radius(bundle, r["lambda_p"], r["lambda_s"], args) for r in pair]
    angles = [
        crossing_angle_deg(root_jacobian(bundle, r["lambda_p"], r["lambda_s"], float(args.jacobian_step)))
        for r in pair
    ]
    comfortable = (
        separation >= float(args.minimum_root_separation)
        and min(radii) >= float(args.minimum_admissibility_radius)
        and min(angles) >= float(args.minimum_crossing_angle_deg)
    )
    if not comfortable:
        return {
            **row,
            "finalized": False,
            "reason": "dense_root_comfort_recheck_failed",
            "final_separation": separation,
            "final_min_radius": min(radii),
            "final_min_angle_deg": min(angles),
        }

    physical = cc_run.build_map(bundle.ref, bundle.sample, "physical", int(args.physical_resolution))
    np.savez_compressed(
        outdir / "highres_physical_map.npz",
        **{k: v for k, v in physical.items() if isinstance(v, np.ndarray)},
    )
    plot_4x2(
        physical, list(pair),
        (
            f"GLOBAL comfortable multiroot - PHYSICAL | "
            f"state={row['state_id']} | T=({float(row['refined_Tp_Nm']):+.1f},"
            f"{float(row['refined_Ts_Nm']):+.1f}) Nm | sep={separation:.3f} | "
            f"min radius={min(radii):.3f} | min angle={min(angles):.1f} deg"
        ),
        outdir / "highres_4x2_physical.png",
        ref=bundle.ref, show_static_box=False,
    )

    expanded = cc_run.build_map(bundle.ref, bundle.sample, "expanded", int(args.expanded_resolution))
    np.savez_compressed(
        outdir / "highres_expanded_map.npz",
        **{k: v for k, v in expanded.items() if isinstance(v, np.ndarray)},
    )
    plot_4x2(
        expanded, list(pair),
        (
            f"GLOBAL comfortable multiroot - EXPANDED | "
            f"state={row['state_id']} | T=({float(row['refined_Tp_Nm']):+.1f},"
            f"{float(row['refined_Ts_Nm']):+.1f}) Nm | sep={separation:.3f} | "
            f"min radius={min(radii):.3f} | min angle={min(angles):.1f} deg"
        ),
        outdir / "highres_4x2_expanded.png",
        ref=bundle.ref, show_static_box=True,
    )

    return {
        **row,
        "finalized": True,
        "final_separation": separation,
        "final_root1_lambda_p": pair[0]["lambda_p"],
        "final_root1_lambda_s": pair[0]["lambda_s"],
        "final_root2_lambda_p": pair[1]["lambda_p"],
        "final_root2_lambda_s": pair[1]["lambda_s"],
        "final_root1_radius": radii[0],
        "final_root2_radius": radii[1],
        "final_root1_crossing_angle_deg": angles[0],
        "final_root2_crossing_angle_deg": angles[1],
    }


def main() -> int:
    args = parse_args()
    cc_run.verify_environment()

    recipes = all_state_recipes(args)
    out = args.output_dir.resolve() if args.output_dir else DEFAULT_OUTPUT
    out.mkdir(parents=True, exist_ok=True)

    cfg = {
        "explore_resolution": int(args.explore_resolution),
        "torque_basis_step": float(args.torque_basis_step),
        "torque_limit": float(args.torque_limit),
        "max_torque_gain_condition": float(args.max_torque_gain_condition),
        "torque_match_radius": float(args.torque_match_radius),
        "nearest_neighbours": int(args.nearest_neighbours),
        "minimum_seed_lambda_separation": float(args.minimum_seed_lambda_separation),
        "seeds_per_state": int(args.seeds_per_state),
        "candidate_torque_cluster_radius": float(args.candidate_torque_cluster_radius),
        "local_torque_radius": float(args.local_torque_radius),
        "local_torque_step": float(args.local_torque_step),
        "root_residual_tolerance": float(args.root_residual_tolerance),
        "root_cluster_tolerance": float(args.root_cluster_tolerance),
        "minimum_normal_N": float(args.minimum_normal_N),
        "minimum_static_margin": float(args.minimum_static_margin),
        "jacobian_step": float(args.jacobian_step),
        "max_secondary_rpm": float(args.max_secondary_rpm),
        "max_belt_speed_m_s": float(args.max_belt_speed_m_s),
    }

    print("=" * 92)
    print("GLOBAL COMFORTABLE MULTIROOT SEARCH")
    print(f"Frozen state count: {len(recipes)}")
    print(f"Coarse lambda map per state: {args.explore_resolution} x {args.explore_resolution}")
    print(f"Worker processes: {args.jobs}")
    print("State envelope:")
    print(f"  shift fractions: {args.shift_fractions}")
    print(f"  shift speeds [mm/s]: {args.shift_speeds_mm_s}")
    print(f"  primary RPM: {args.primary_rpms}")
    print(f"  torque limit: +/-{args.torque_limit} Nm")
    print()

    state_rows = []
    candidates = []
    with ProcessPoolExecutor(
        max_workers=max(1, int(args.jobs)),
        initializer=worker_init,
        initargs=(str(args.reference_path_csv.resolve()), int(args.reference_frame)),
    ) as ex:
        future_map = {ex.submit(worker_state, recipe, cfg): recipe for recipe in recipes}
        completed = 0
        for fut in as_completed(future_map):
            result = fut.result()
            completed += 1
            state_rows.append({
                "state_id": result["state_id"],
                "status": result["status"],
                "shift_fraction": result.get("shift_fraction", ""),
                "shift_speed_mm_s": result.get("shift_speed_mm_s", ""),
                "target_primary_rpm": result.get("target_primary_rpm", ""),
                "candidate_count": len(result.get("candidates", [])),
            })
            candidates.extend(result.get("candidates", []))
            if completed % 10 == 0 or result.get("candidates"):
                print(
                    f"  {completed:03d}/{len(recipes):03d} states complete | "
                    f"latest={result['state_id']} | candidates={len(result.get('candidates', []))} | "
                    f"global candidates={len(candidates)}"
                )

    write_rows(out / "state_scan_summary.csv", state_rows)
    write_rows(out / "all_two_root_candidates_precomfort.csv", candidates)

    if not candidates:
        print("No two-root candidates found anywhere in the configured global envelope.")
        return 0

    # Only exact physical, reasonably separated roots with some crossing angle are
    # worth an expensive geometric radius audit.
    filtered = [
        r for r in candidates
        if bool(r["both_roots_physical_exact"])
        and float(r["root_separation"]) >= 0.75 * float(args.minimum_root_separation)
        and float(r["minimum_crossing_angle_deg"]) >= 0.40 * float(args.minimum_crossing_angle_deg)
    ]
    shortlist = diverse_shortlist(filtered, int(args.comfort_audits))
    write_rows(out / "comfort_audit_shortlist.csv", shortlist)

    print()
    print(f"Coarse two-root candidates: {len(candidates)}")
    print(f"Geometric comfort audits selected: {len(shortlist)}")

    decoded, library = controlled.load_base()
    reference_mode = reference_mode_from_path(
        decoded, library, args.reference_path_csv.resolve(), int(args.reference_frame)
    )

    audited = []
    comfortable = []
    for i, row in enumerate(shortlist, start=1):
        recipe = rebuild_recipe_from_candidate(row)
        bundle = closure_bundle(
            decoded, library, recipe,
            float(row["refined_Tp_Nm"]), float(row["refined_Ts_Nm"]),
            reference_mode,
        )
        roots = [
            (float(row["root1_lambda_p"]), float(row["root1_lambda_s"])),
            (float(row["root2_lambda_p"]), float(row["root2_lambda_s"])),
        ]
        radii = [admissibility_radius(bundle, lp, ls, args) for lp, ls in roots]
        exact = dict(row)
        exact["root1_admissibility_radius"] = radii[0]
        exact["root2_admissibility_radius"] = radii[1]
        exact["minimum_admissibility_radius"] = min(radii)
        exact["comfortable"] = bool(
            float(row["root_separation"]) >= float(args.minimum_root_separation)
            and float(row["minimum_crossing_angle_deg"]) >= float(args.minimum_crossing_angle_deg)
            and min(radii) >= float(args.minimum_admissibility_radius)
        )
        audited.append(exact)
        if exact["comfortable"]:
            comfortable.append(exact)
        print(
            f"  audit {i:03d}/{len(shortlist):03d} | {row['state_id']} | "
            f"sep={float(row['root_separation']):.3f} | "
            f"angle={float(row['minimum_crossing_angle_deg']):.1f} deg | "
            f"radius={min(radii):.4f} | comfortable={exact['comfortable']}"
        )

    write_rows(out / "comfort_audit_results.csv", audited)

    comfortable.sort(
        key=lambda r: (
            float(r["minimum_admissibility_radius"]),
            float(r["minimum_crossing_angle_deg"]),
            float(r["root_separation"]),
        ),
        reverse=True,
    )
    write_rows(out / "comfortable_candidates.csv", comfortable)

    if not comfortable:
        best = sorted(
            audited,
            key=lambda r: (
                float(r["minimum_admissibility_radius"]),
                float(r["minimum_crossing_angle_deg"]),
                float(r["root_separation"]),
            ),
            reverse=True,
        )[:10]
        write_rows(out / "best_near_misses.csv", best)
        print()
        print("No candidate met all comfort thresholds in the configured global envelope.")
        if best:
            b = best[0]
            print(
                "Best near miss: "
                f"{b['state_id']} | radius={float(b['minimum_admissibility_radius']):.4f} | "
                f"angle={float(b['minimum_crossing_angle_deg']):.1f} deg | "
                f"sep={float(b['root_separation']):.3f}"
            )
        print("No high-resolution maps generated.")
        return 0

    finalists = comfortable[:int(args.final_count)]
    write_rows(out / "selected_finalists.csv", finalists)

    print()
    print(f"Finalizing {len(finalists)} comfortable candidate(s)...")
    final_rows = []
    for i, row in enumerate(finalists, start=1):
        cdir = out / f"finalist_{i:02d}_{row['state_id']}"
        cdir.mkdir(parents=True, exist_ok=True)
        result = finalize(decoded, library, reference_mode, row, cdir, args)
        final_rows.append(result)
        print(
            f"  finalist {i}: finalized={result.get('finalized')} | "
            f"{row['state_id']} | radius={float(row['minimum_admissibility_radius']):.4f}"
        )

    write_rows(out / "final_summary.csv", final_rows)
    print()
    print(f"Complete. Outputs: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
