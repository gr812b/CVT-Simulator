r"""Search for a frozen operating point with multiple physical stick-stick roots.

Purpose
-------
The reversal maps show a folded R_s = 0 contour, but the existing controlled path
still has only one R_p = R_s = 0 intersection.  This study asks the stronger question:

    Can the SAME frozen CVT state and SAME shaft boundary torques admit two distinct,
    physically admissible stick-stick traction solutions?

The script is deliberately two-stage:

1. QUICK EXPLORATION
   Freeze one kinematic state from an existing locked path (default: frame 60).
   On a coarse physical lambda grid, infer the exact shaft torques required to make
   each trial lambda pair a stick-stick root.  The residual response is affine in the
   two external shaft torques for a frozen state, so three closure evaluations at each
   lambda point identify that 2x2 torque-response map.

   Pairs of well-separated lambda points that require nearly the same torque pair are
   cheap seeds for possible multiple roots.  Each seed is then tested in a small local
   torque neighborhood using two bounded nonlinear root solves, one started from each
   lambda seed.  Candidates are ranked primarily by the separation between the two
   physical roots, not merely by whether a barely split pair exists.

2. EXPENSIVE FINALIZATION
   ONLY if one or more good two-root candidates are found:
     * run a denser production multi-start root census;
     * build a high-resolution physical lambda map for the best candidate(s);
     * save a 4x2 diagnostic figure with all verified physical roots marked.

No high-resolution map is built when the exploration fails to find a good candidate.

Typical run from results/cinder-v1.1.2
--------------------------------------

    python .\studies\closure-conditioning\search_multiroot_operating_point.py `
      --path-csv .\studies\closure-conditioning\artifacts\controlled-free-shift-animation\expanded_res641_locked_locked_path\preflight_path.csv `
      --frame 60

Useful controls
---------------

    --explore-resolution 71      coarse lambda grid for the cheap stage
    --torque-limit 180           only consider required torques within +/- this [Nm]
    --torque-match-radius 6      seed points whose required torque vectors are this close [Nm]
    --minimum-root-separation .08
    --verify-candidates 30       number of distinct coarse torque seeds to investigate
    --local-torque-radius 8      local +/- torque refinement around each seed [Nm]
    --local-torque-step 2
    --final-resolution 401       expensive map; only used after a good candidate exists
    --highres-count 1            number of top candidates to map at high resolution

The script performs a direct mechanical closure study.  It is not a time simulation.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, SymLogNorm, TwoSlopeNorm, ListedColormap
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree

import run as cc_run
import animate_controlled_free_shift_path as controlled
from case_library import make_bench_system, full_state

from cinder.model.cvt.contact import ContactInterface, ContactTractionUtilization
from cinder.model.cvt.dynamics.engaged_contact import EngagedContactClosure
from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint


HERE = Path(__file__).resolve().parent
DEFAULT_ARTIFACTS = HERE / "artifacts" / "multiroot-operating-point-search"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--path-csv", type=Path, required=True,
                   help="Locked/preflight controlled-path CSV containing the frozen state recipe.")
    p.add_argument("--frame", type=int, default=60,
                   help="Frame used as the frozen kinematic state. Default: 60.")
    p.add_argument("--output-dir", type=Path, default=None)

    # Cheap exploration.
    p.add_argument("--explore-resolution", type=int, default=71,
                   help="Physical lambda grid points per axis for the cheap inverse-torque map.")
    p.add_argument("--torque-basis-step", type=float, default=1.0,
                   help="Torque increment [Nm] used to identify the exact affine residual response.")
    p.add_argument("--torque-limit", type=float, default=180.0,
                   help="Discard inverse-map points requiring |Tp| or |Ts| above this [Nm].")
    p.add_argument("--max-torque-gain-condition", type=float, default=1.0e7,
                   help="Discard lambda points where the 2x2 residual-vs-torque gain is too ill-conditioned.")
    p.add_argument("--torque-match-radius", type=float, default=6.0,
                   help="Maximum distance [Nm] between required-torque vectors for a coarse double-root seed.")
    p.add_argument("--nearest-neighbours", type=int, default=14,
                   help="Number of inverse-map neighbours considered per lambda grid point.")
    p.add_argument("--minimum-seed-lambda-separation", type=float, default=0.08,
                   help="Ignore near-identical lambda points when making coarse seeds.")
    p.add_argument("--verify-candidates", type=int, default=30,
                   help="Maximum number of distinct coarse torque seeds sent to local refinement.")
    p.add_argument("--candidate-torque-cluster-radius", type=float, default=5.0,
                   help="Greedy clustering radius [Nm] for nearly duplicate coarse torque seeds.")

    # Local candidate refinement.
    p.add_argument("--local-torque-radius", type=float, default=8.0,
                   help="Search +/- this radius around each coarse common-torque seed [Nm].")
    p.add_argument("--local-torque-step", type=float, default=2.0,
                   help="Torque grid spacing for local candidate refinement [Nm].")
    p.add_argument("--root-residual-tolerance", type=float, default=1.0e-6,
                   help="Maximum ||R|| accepted for a locally refined root [m/s^2].")
    p.add_argument("--minimum-root-separation", type=float, default=0.08,
                   help="Minimum Euclidean separation in (lambda_p, lambda_s) for a good two-root candidate.")
    p.add_argument("--minimum-static-margin", type=float, default=0.0,
                   help="Additional static-friction margin required at both roots.")
    p.add_argument("--minimum-normal-N", type=float, default=1.0,
                   help="Minimum integrated normal resultant at both contacts for a physical root.")

    # Final, expensive verification.
    p.add_argument("--final-multistart", type=int, default=13,
                   help="Starts per lambda axis for final production root census.")
    p.add_argument("--final-resolution", type=int, default=401,
                   help="High-resolution map size; used only if a good candidate exists.")
    p.add_argument("--highres-count", type=int, default=1,
                   help="Number of best candidates receiving expensive high-resolution maps.")
    p.add_argument("--root-cluster-tolerance", type=float, default=2.0e-4)
    return p.parse_args()


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


def frozen_recipe(path_csv: Path, frame_no: int) -> dict[str, Any]:
    rows = controlled.load_locked_path(path_csv.resolve())
    by_frame = {int(row["frame_no"]): dict(row) for row in rows}
    if frame_no not in by_frame:
        raise ValueError(
            f"Frame {frame_no} is not present in {path_csv}. "
            f"Available range: {min(by_frame)}..{max(by_frame)}."
        )
    return by_frame[frame_no]


def closure_bundle(decoded, library: dict, recipe: dict[str, Any], tp: float, ts: float,
                   *, reference_mode=None):
    local_recipe = dict(recipe)
    local_recipe["primary_torque_Nm"] = float(tp)
    local_recipe["secondary_torque_Nm"] = float(ts)
    system = make_bench_system(
        decoded, library,
        primary_torque=float(tp),
        secondary_torque=float(ts),
    )
    cvt = controlled.state_for_recipe(system, local_recipe)
    state = full_state(system, cvt)
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
    if reference_mode is None:
        mode = system.classify_initial_mode(state)
    else:
        mode = reference_mode
    ref = cc_run.ReferenceRun(
        name=f"multiroot_Tp{tp:+.4g}_Ts{ts:+.4g}",
        decoded=SimpleNamespace(system=system),
        result=None,
        samples=tuple(),
    )
    sample = cc_run.FrozenSample(
        time=0.0,
        full_state=np.asarray(state, dtype=float),
        composed_mode=mode,
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


def evaluate_residual(closure: EngagedContactClosure, lp: float, ls: float) -> np.ndarray:
    trial = closure.evaluate_trial(
        traction_utilization=ContactTractionUtilization(
            primary_lambda=float(lp),
            secondary_lambda=float(ls),
        ),
        maximum_closure_condition_number=None,
        capture_diagnostics=False,
    )
    return np.asarray([
        trial.relative_motion.primary_relative_acceleration,
        trial.relative_motion.secondary_relative_acceleration,
    ], dtype=float)


def identify_required_torque_map(decoded, library: dict, recipe: dict[str, Any], reference_mode,
                                 args: argparse.Namespace):
    dt = float(args.torque_basis_step)
    if dt <= 0.0:
        raise ValueError("--torque-basis-step must be positive.")

    # The state is frozen. External shaft torque only changes the rotational-row
    # biases, so these three closures identify R(lambda,T) = R0(lambda) + G(lambda)T.
    base = closure_bundle(decoded, library, recipe, 0.0, 0.0, reference_mode=reference_mode)
    tp_basis = closure_bundle(decoded, library, recipe, dt, 0.0, reference_mode=reference_mode)
    ts_basis = closure_bundle(decoded, library, recipe, 0.0, dt, reference_mode=reference_mode)

    law = base.system.cvt.traction_law
    p_interval = law.primary_static_interval
    s_interval = law.secondary_static_interval
    lp_axis = np.linspace(p_interval.lower, p_interval.upper, int(args.explore_resolution))
    ls_axis = np.linspace(s_interval.lower, s_interval.upper, int(args.explore_resolution))
    shape = (ls_axis.size, lp_axis.size)

    tp_req = np.full(shape, np.nan)
    ts_req = np.full(shape, np.nan)
    gain_cond = np.full(shape, np.nan)
    affine_check = np.full(shape, np.nan)

    total = shape[0] * shape[1]
    done = 0
    for i, ls in enumerate(ls_axis):
        for j, lp in enumerate(lp_axis):
            try:
                r0 = evaluate_residual(base.closure, lp, ls)
                rp = evaluate_residual(tp_basis.closure, lp, ls)
                rs = evaluate_residual(ts_basis.closure, lp, ls)
                G = np.column_stack(((rp - r0) / dt, (rs - r0) / dt))
                cond = float(np.linalg.cond(G))
                gain_cond[i, j] = cond
                if not np.isfinite(cond) or cond > float(args.max_torque_gain_condition):
                    continue
                T = -np.linalg.solve(G, r0)
                if not np.all(np.isfinite(T)):
                    continue
                if max(abs(float(T[0])), abs(float(T[1]))) > float(args.torque_limit):
                    continue
                tp_req[i, j] = float(T[0])
                ts_req[i, j] = float(T[1])

                # A cheap exactness check at a small subset would suffice, but evaluating
                # at every retained point also catches any hidden non-affine dependency.
                # To keep exploration cheap, do it only on every eighth grid index.
                if (i % 8 == 0) and (j % 8 == 0):
                    direct = closure_bundle(
                        decoded, library, recipe, float(T[0]), float(T[1]),
                        reference_mode=reference_mode,
                    )
                    affine_check[i, j] = float(np.linalg.norm(evaluate_residual(direct.closure, lp, ls)))
            except (ArithmeticError, ValueError, RuntimeError, np.linalg.LinAlgError):
                continue
            finally:
                done += 1
        if i % max(1, len(ls_axis) // 10) == 0:
            print(f"  inverse-torque map row {i + 1}/{len(ls_axis)}")

    return {
        "lambda_p": lp_axis,
        "lambda_s": ls_axis,
        "required_Tp": tp_req,
        "required_Ts": ts_req,
        "torque_gain_condition": gain_cond,
        "affine_check_residual": affine_check,
        "static_primary_lower": np.asarray(float(p_interval.lower)),
        "static_primary_upper": np.asarray(float(p_interval.upper)),
        "static_secondary_lower": np.asarray(float(s_interval.lower)),
        "static_secondary_upper": np.asarray(float(s_interval.upper)),
    }


def plot_required_torque_map(data: dict[str, np.ndarray], path: Path) -> None:
    lp = data["lambda_p"]
    ls = data["lambda_s"]
    LP, LS = np.meshgrid(lp, ls)
    tp = data["required_Tp"]
    ts = data["required_Ts"]
    cond = data["torque_gain_condition"]
    finite_cond = cond[np.isfinite(cond) & (cond > 0.0)]
    c0 = max(float(np.percentile(finite_cond, 1.0)), 1.0) if finite_cond.size else 1.0
    c1 = max(float(np.percentile(finite_cond, 99.5)), c0 * 1.01) if finite_cond.size else 10.0

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2), constrained_layout=True)
    for ax, values, title in (
        (axes[0], tp, r"Required $T_p$ [Nm]"),
        (axes[1], ts, r"Required $T_s$ [Nm]"),
    ):
        finite = values[np.isfinite(values)]
        if finite.size:
            lim = max(float(np.percentile(np.abs(finite), 99.0)), 1.0)
            im = ax.pcolormesh(
                LP, LS, values, shading="auto",
                norm=TwoSlopeNorm(vcenter=0.0, vmin=-lim, vmax=lim),
                rasterized=True,
            )
            fig.colorbar(im, ax=ax)
        ax.set_title(title)
        ax.set_xlabel(r"$\lambda_p$")
        ax.set_ylabel(r"$\lambda_s$")
    im = axes[2].pcolormesh(
        LP, LS, cond, shading="auto",
        norm=LogNorm(vmin=c0, vmax=c1), rasterized=True,
    )
    axes[2].set_title(r"$\kappa(\partial R/\partial T)$")
    axes[2].set_xlabel(r"$\lambda_p$")
    axes[2].set_ylabel(r"$\lambda_s$")
    fig.colorbar(im, ax=axes[2])
    fig.suptitle("Inverse torque map for the frozen state")
    fig.savefig(path, dpi=170)
    plt.close(fig)


def coarse_seed_pairs(data: dict[str, np.ndarray], args: argparse.Namespace) -> list[dict[str, float]]:
    lp_axis = data["lambda_p"]
    ls_axis = data["lambda_s"]
    tp = data["required_Tp"]
    ts = data["required_Ts"]

    rows = []
    torque_points = []
    lambda_points = []
    grid_indices = []
    for i, ls in enumerate(ls_axis):
        for j, lp in enumerate(lp_axis):
            if not (np.isfinite(tp[i, j]) and np.isfinite(ts[i, j])):
                continue
            torque_points.append((float(tp[i, j]), float(ts[i, j])))
            lambda_points.append((float(lp), float(ls)))
            grid_indices.append((i, j))
    if len(torque_points) < 2:
        return []

    torque_points_a = np.asarray(torque_points, dtype=float)
    lambda_points_a = np.asarray(lambda_points, dtype=float)
    tree = cKDTree(torque_points_a)
    k = min(max(2, int(args.nearest_neighbours)), len(torque_points))
    distances, neighbours = tree.query(torque_points_a, k=k)
    if k == 1:
        distances = distances[:, None]
        neighbours = neighbours[:, None]

    seen_pairs: set[tuple[int, int]] = set()
    for i in range(len(torque_points)):
        for n in range(1, k):
            j = int(neighbours[i, n])
            if j < 0 or j == i:
                continue
            a, b = sorted((i, j))
            if (a, b) in seen_pairs:
                continue
            seen_pairs.add((a, b))
            torque_distance = float(np.linalg.norm(torque_points_a[a] - torque_points_a[b]))
            if torque_distance > float(args.torque_match_radius):
                continue
            lambda_distance = float(np.linalg.norm(lambda_points_a[a] - lambda_points_a[b]))
            if lambda_distance < float(args.minimum_seed_lambda_separation):
                continue

            common_torque = 0.5 * (torque_points_a[a] + torque_points_a[b])
            score = lambda_distance / (1.0 + torque_distance / max(float(args.torque_match_radius), 1.0e-12))
            rows.append({
                "seed_lambda1_p": float(lambda_points_a[a, 0]),
                "seed_lambda1_s": float(lambda_points_a[a, 1]),
                "seed_lambda2_p": float(lambda_points_a[b, 0]),
                "seed_lambda2_s": float(lambda_points_a[b, 1]),
                "seed_lambda_separation": lambda_distance,
                "required_torque_distance_Nm": torque_distance,
                "seed_common_Tp_Nm": float(common_torque[0]),
                "seed_common_Ts_Nm": float(common_torque[1]),
                "seed_score": score,
            })

    rows.sort(key=lambda row: (-row["seed_score"], row["required_torque_distance_Nm"]))

    # Greedily keep distinct torque neighborhoods. This prevents one broad overlap
    # region from consuming all verification slots.
    selected: list[dict[str, float]] = []
    radius = float(args.candidate_torque_cluster_radius)
    for row in rows:
        t = np.asarray([row["seed_common_Tp_Nm"], row["seed_common_Ts_Nm"]], dtype=float)
        if any(
            np.linalg.norm(t - np.asarray([s["seed_common_Tp_Nm"], s["seed_common_Ts_Nm"]], dtype=float))
            < radius
            for s in selected
        ):
            continue
        selected.append(row)
        if len(selected) >= int(args.verify_candidates):
            break
    return selected


def local_root(closure: EngagedContactClosure, seed: tuple[float, float], law,
               args: argparse.Namespace):
    lower = np.asarray([law.primary_static_interval.lower, law.secondary_static_interval.lower], dtype=float)
    upper = np.asarray([law.primary_static_interval.upper, law.secondary_static_interval.upper], dtype=float)
    x0 = np.clip(np.asarray(seed, dtype=float), lower + 1.0e-10, upper - 1.0e-10)

    def fun(x):
        try:
            return evaluate_residual(closure, float(x[0]), float(x[1]))
        except Exception:
            return np.asarray([1.0e9, 1.0e9], dtype=float)

    result = least_squares(
        fun,
        x0,
        bounds=(lower, upper),
        xtol=1.0e-10,
        ftol=1.0e-10,
        gtol=1.0e-10,
        max_nfev=120,
    )
    residual = fun(result.x)
    norm = float(np.linalg.norm(residual))
    if not result.success or not np.all(np.isfinite(result.x)) or norm > float(args.root_residual_tolerance):
        return None
    return {
        "lambda_p": float(result.x[0]),
        "lambda_s": float(result.x[1]),
        "residual_norm": norm,
        "nfev": int(result.nfev),
    }


def physical_root_diagnostics(bundle, root: dict[str, float], args: argparse.Namespace) -> dict[str, Any]:
    utilization = ContactTractionUtilization(
        primary_lambda=float(root["lambda_p"]),
        secondary_lambda=float(root["lambda_s"]),
    )
    trial = bundle.closure.evaluate_trial(
        traction_utilization=utilization,
        maximum_closure_condition_number=None,
        capture_diagnostics=True,
    )
    code, extra = cc_run.topology_failure_code(
        bundle.ref,
        bundle.sample,
        trial,
        utilization,
        bundle.snapshot,
    )
    law = bundle.system.cvt.traction_law
    p_margin = float(law.static_margin_at(ContactInterface.PRIMARY, root["lambda_p"]))
    s_margin = float(law.static_margin_at(ContactInterface.SECONDARY, root["lambda_s"]))
    unknowns = trial.closure.unknowns

    search = {
        "minimum_normal_N": float(args.minimum_normal_N),
        "minimum_static_margin": float(args.minimum_static_margin),
    }
    physical = (
        code == 0
        and float(unknowns.primary_normal_resultant) >= search["minimum_normal_N"]
        and float(unknowns.secondary_normal_resultant) >= search["minimum_normal_N"]
        and p_margin >= search["minimum_static_margin"]
        and s_margin >= search["minimum_static_margin"]
    )
    return {
        **root,
        "physical": bool(physical),
        "topology_failure_code": int(code),
        "N_p": float(unknowns.primary_normal_resultant),
        "N_s": float(unknowns.secondary_normal_resultant),
        "primary_static_margin": p_margin,
        "secondary_static_margin": s_margin,
        "min_belt_tension": float(extra["min_belt_tension"]),
        "min_local_normal_p": float(extra["min_local_normal_p"]),
        "min_local_normal_s": float(extra["min_local_normal_s"]),
        "mechanism_margin": float(extra["mechanism_margin"]),
        "A_condition_scaled": float(trial.closure.scaled_condition_number),
    }


def deduplicate_roots(roots: list[dict[str, Any]], tolerance: float) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    for root in roots:
        x = np.asarray([root["lambda_p"], root["lambda_s"]], dtype=float)
        if any(
            np.linalg.norm(x - np.asarray([r["lambda_p"], r["lambda_s"]], dtype=float)) <= tolerance
            for r in unique
        ):
            continue
        unique.append(root)
    return unique


def local_torque_offsets(radius: float, step: float):
    if radius < 0.0 or step <= 0.0:
        raise ValueError("Local torque radius must be non-negative and step positive.")
    values = np.arange(-radius, radius + 0.5 * step, step)
    # Search center first, then expanding Manhattan rings.
    pairs = [(float(dp), float(ds)) for dp in values for ds in values]
    pairs.sort(key=lambda pair: (abs(pair[0]) + abs(pair[1]), pair[0] ** 2 + pair[1] ** 2))
    return pairs


def refine_seed_candidate(decoded, library, recipe, reference_mode,
                          seed: dict[str, float], args: argparse.Namespace):
    seed1 = (seed["seed_lambda1_p"], seed["seed_lambda1_s"])
    seed2 = (seed["seed_lambda2_p"], seed["seed_lambda2_s"])
    center_tp = float(seed["seed_common_Tp_Nm"])
    center_ts = float(seed["seed_common_Ts_Nm"])

    best = None
    offsets = local_torque_offsets(float(args.local_torque_radius), float(args.local_torque_step))
    for dp, ds in offsets:
        tp = center_tp + dp
        ts = center_ts + ds
        if max(abs(tp), abs(ts)) > float(args.torque_limit):
            continue
        try:
            bundle = closure_bundle(
                decoded, library, recipe, tp, ts,
                reference_mode=reference_mode,
            )
            law = bundle.system.cvt.traction_law
            r1 = local_root(bundle.closure, seed1, law, args)
            r2 = local_root(bundle.closure, seed2, law, args)
            if r1 is None or r2 is None:
                continue
            roots = deduplicate_roots([r1, r2], float(args.root_cluster_tolerance))
            if len(roots) < 2:
                continue
            d1 = physical_root_diagnostics(bundle, roots[0], args)
            d2 = physical_root_diagnostics(bundle, roots[1], args)
            separation = float(np.hypot(
                d1["lambda_p"] - d2["lambda_p"],
                d1["lambda_s"] - d2["lambda_s"],
            ))
            physical_count = int(d1["physical"]) + int(d2["physical"])
            min_static_margin = min(
                d1["primary_static_margin"], d1["secondary_static_margin"],
                d2["primary_static_margin"], d2["secondary_static_margin"],
            )
            min_normal = min(d1["N_p"], d1["N_s"], d2["N_p"], d2["N_s"])
            # Separation dominates. Physicality is a hard preference, then robust
            # margins and moderate torque magnitude break ties.
            score = (
                1000.0 * physical_count
                + 100.0 * separation
                + 3.0 * max(min_static_margin, -1.0)
                + 1.0e-3 * max(min_normal, 0.0)
                - 1.0e-3 * (abs(tp) + abs(ts))
            )
            row = {
                **seed,
                "refined_Tp_Nm": tp,
                "refined_Ts_Nm": ts,
                "root1_lambda_p": d1["lambda_p"],
                "root1_lambda_s": d1["lambda_s"],
                "root1_physical": d1["physical"],
                "root1_topology_failure_code": d1["topology_failure_code"],
                "root1_static_margin_min": min(d1["primary_static_margin"], d1["secondary_static_margin"]),
                "root1_N_min": min(d1["N_p"], d1["N_s"]),
                "root2_lambda_p": d2["lambda_p"],
                "root2_lambda_s": d2["lambda_s"],
                "root2_physical": d2["physical"],
                "root2_topology_failure_code": d2["topology_failure_code"],
                "root2_static_margin_min": min(d2["primary_static_margin"], d2["secondary_static_margin"]),
                "root2_N_min": min(d2["N_p"], d2["N_s"]),
                "physical_root_count": physical_count,
                "root_separation": separation,
                "minimum_static_margin": min_static_margin,
                "minimum_normal_N": min_normal,
                "candidate_score": score,
            }
            if best is None or row["candidate_score"] > best["candidate_score"]:
                best = row
        except (ArithmeticError, ValueError, RuntimeError, np.linalg.LinAlgError):
            continue
    return best


def production_multistart(bundle, samples_per_axis: int, cluster_tol: float):
    law = bundle.system.cvt.traction_law
    base = bundle.system.cvt.solve_settings
    p = np.linspace(law.primary_static_interval.lower, law.primary_static_interval.upper, samples_per_axis)
    s = np.linspace(law.secondary_static_interval.lower, law.secondary_static_interval.upper, samples_per_axis)
    roots: list[np.ndarray] = []
    rows: list[dict[str, Any]] = []

    for ls0 in s:
        for lp0 in p:
            row = {
                "start_lambda_p": float(lp0),
                "start_lambda_s": float(ls0),
                "accepted": False,
                "root_cluster": -1,
                "root_lambda_p": np.nan,
                "root_lambda_s": np.nan,
                "residual_norm": np.nan,
            }
            try:
                settings = replace(
                    base,
                    initial_guess=ContactTractionUtilization(
                        primary_lambda=float(lp0),
                        secondary_lambda=float(ls0),
                    ),
                )
                solved = bundle.closure.solve_stick_stick(settings=settings)
                root = np.asarray([
                    solved.traction_utilization.primary_lambda,
                    solved.traction_utilization.secondary_lambda,
                ], dtype=float)
                cluster = -1
                if solved.accepted:
                    for k, existing in enumerate(roots):
                        if np.linalg.norm(root - existing) <= cluster_tol:
                            cluster = k
                            break
                    if cluster < 0:
                        cluster = len(roots)
                        roots.append(root)
                row.update({
                    "accepted": bool(solved.accepted),
                    "root_cluster": cluster,
                    "root_lambda_p": float(root[0]),
                    "root_lambda_s": float(root[1]),
                    "residual_norm": float(np.linalg.norm(solved.sticking_residuals)),
                })
            except (ArithmeticError, ValueError, RuntimeError, np.linalg.LinAlgError):
                pass
            rows.append(row)

    root_diagnostics = []
    for k, root in enumerate(roots):
        diag = physical_root_diagnostics(
            bundle,
            {"lambda_p": float(root[0]), "lambda_s": float(root[1]), "residual_norm": 0.0, "nfev": 0},
            args=SimpleNamespace(minimum_normal_N=1.0, minimum_static_margin=0.0),
        )
        diag["root_cluster"] = k
        root_diagnostics.append(diag)
    return rows, root_diagnostics


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


def plot_highres_candidate(data, roots: list[dict[str, Any]], title: str, path: Path):
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
        for k, root in enumerate(roots):
            ax.plot(root["lambda_p"], root["lambda_s"], marker="o", ms=7,
                    markerfacecolor="none", markeredgecolor="red", mew=1.6)
            ax.text(root["lambda_p"], root["lambda_s"], f" {k+1}", color="red", fontsize=8)
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
    for k, root in enumerate(roots):
        ax.plot(root["lambda_p"], root["lambda_s"], marker="o", ms=7,
                markerfacecolor="none", markeredgecolor="black", mew=1.6)
        ax.text(root["lambda_p"], root["lambda_s"], f" {k+1}", color="black", fontsize=8)
    ax.set_title("inadmissibility")
    ax.set_xlabel(r"$\lambda_p$")
    ax.set_ylabel(r"$\lambda_s$")

    fig.suptitle(title, fontsize=14)
    fig.savefig(path, dpi=190)
    plt.close(fig)


def candidate_bundle(decoded, library, recipe, reference_mode, row):
    return closure_bundle(
        decoded, library, recipe,
        float(row["refined_Tp_Nm"]),
        float(row["refined_Ts_Nm"]),
        reference_mode=reference_mode,
    )


def main() -> int:
    args = parse_args()
    if args.explore_resolution < 21:
        raise ValueError("--explore-resolution must be at least 21.")
    if args.final_resolution < args.explore_resolution:
        raise ValueError("--final-resolution should be >= --explore-resolution.")

    cc_run.verify_environment()
    decoded, library = controlled.load_base()
    recipe = frozen_recipe(args.path_csv, int(args.frame))

    # Obtain a known-good mode object from the original locked-path torque pair.
    original_ref, original_sample = controlled.make_ref_and_sample(decoded, library, recipe)
    reference_mode = original_sample.composed_mode

    out = args.output_dir.resolve() if args.output_dir is not None else DEFAULT_ARTIFACTS / f"frame_{args.frame:03d}"
    out.mkdir(parents=True, exist_ok=True)

    print("=" * 88)
    print(f"Frozen frame: {args.frame}")
    print(
        f"shift_fraction={float(recipe['shift_fraction']):.6f}, "
        f"shift_speed={1000.0*float(recipe['shift_speed']):+.3f} mm/s, "
        f"locked torques=({float(recipe['primary_torque_Nm']):+.3f}, "
        f"{float(recipe['secondary_torque_Nm']):+.3f}) Nm"
    )
    print()
    print("Stage 1/3: coarse inverse-torque map...")
    inverse = identify_required_torque_map(decoded, library, recipe, reference_mode, args)
    np.savez_compressed(out / "required_torque_map.npz", **inverse)
    plot_required_torque_map(inverse, out / "required_torque_map.png")

    finite_affine = inverse["affine_check_residual"][np.isfinite(inverse["affine_check_residual"])]
    affine_max = float(np.max(finite_affine)) if finite_affine.size else float("nan")
    print(f"  maximum sampled affine reconstruction residual: {affine_max:.3e} m/s^2")

    print()
    print("Stage 2/3: finding repeated required-torque neighborhoods and refining candidates...")
    seeds = coarse_seed_pairs(inverse, args)
    write_rows(out / "coarse_seed_pairs.csv", seeds)
    print(f"  distinct coarse torque seeds retained: {len(seeds)}")

    refined = []
    for i, seed in enumerate(seeds, start=1):
        candidate = refine_seed_candidate(
            decoded, library, recipe, reference_mode,
            seed, args,
        )
        if candidate is not None:
            refined.append(candidate)
            print(
                f"  seed {i:02d}/{len(seeds):02d}: "
                f"T=({candidate['refined_Tp_Nm']:+.1f},{candidate['refined_Ts_Nm']:+.1f}) Nm, "
                f"physical roots={candidate['physical_root_count']}, "
                f"separation={candidate['root_separation']:.4f}"
            )
        else:
            print(f"  seed {i:02d}/{len(seeds):02d}: no distinct refined pair")

    refined.sort(key=lambda row: (
        -int(row["physical_root_count"]),
        -float(row["root_separation"]),
        -float(row["minimum_static_margin"]),
        abs(float(row["refined_Tp_Nm"])) + abs(float(row["refined_Ts_Nm"])),
    ))
    write_rows(out / "refined_candidates.csv", refined)

    good = [
        row for row in refined
        if int(row["physical_root_count"]) >= 2
        and float(row["root_separation"]) >= float(args.minimum_root_separation)
    ]
    write_rows(out / "good_candidates.csv", good)

    print()
    print(f"Good two-root candidates: {len(good)}")
    if good:
        for i, row in enumerate(good[:10], start=1):
            print(
                f"  #{i}: T=({row['refined_Tp_Nm']:+.2f},{row['refined_Ts_Nm']:+.2f}) Nm, "
                f"separation={row['root_separation']:.5f}, "
                f"roots=({row['root1_lambda_p']:+.4f},{row['root1_lambda_s']:+.4f}) and "
                f"({row['root2_lambda_p']:+.4f},{row['root2_lambda_s']:+.4f})"
            )

    if not good:
        (out / "summary.txt").write_text(
            "No good physically admissible two-root candidate was found in the configured search.\n"
            "No high-resolution map was generated.\n"
            f"Explore resolution: {args.explore_resolution}\n"
            f"Torque limit: +/-{args.torque_limit} Nm\n"
            f"Coarse seed count: {len(seeds)}\n"
            f"Refined candidate count: {len(refined)}\n"
            f"Maximum sampled affine reconstruction residual: {affine_max:.6e} m/s^2\n",
            encoding="utf-8",
        )
        print()
        print("No good candidate found. Stopping before the expensive stage, as requested.")
        print(f"Outputs: {out}")
        return 0

    print()
    print("Stage 3/3: production multi-start and high-resolution maps for the best candidate(s)...")
    finalists = good[:max(0, int(args.highres_count))]
    final_summary = []

    for rank, row in enumerate(finalists, start=1):
        candidate_dir = out / f"candidate_{rank:02d}"
        candidate_dir.mkdir(exist_ok=True)
        bundle = candidate_bundle(decoded, library, recipe, reference_mode, row)

        ms_rows, ms_roots = production_multistart(
            bundle,
            int(args.final_multistart),
            float(args.root_cluster_tolerance),
        )
        write_rows(candidate_dir / "final_multistart.csv", ms_rows)
        write_rows(candidate_dir / "final_root_diagnostics.csv", ms_roots)

        physical_roots = [r for r in ms_roots if bool(r["physical"])]
        if len(physical_roots) < 2:
            print(
                f"  candidate {rank}: dense multi-start found only {len(physical_roots)} "
                "physical root(s); skipping high-resolution map."
            )
            final_summary.append({
                "candidate_rank": rank,
                "Tp_Nm": row["refined_Tp_Nm"],
                "Ts_Nm": row["refined_Ts_Nm"],
                "dense_distinct_roots": len(ms_roots),
                "dense_physical_roots": len(physical_roots),
                "highres_generated": False,
            })
            continue

        # Re-rank using the largest physical-root pair separation from the dense census.
        largest_sep = 0.0
        for i in range(len(physical_roots)):
            for j in range(i + 1, len(physical_roots)):
                sep = float(np.hypot(
                    physical_roots[i]["lambda_p"] - physical_roots[j]["lambda_p"],
                    physical_roots[i]["lambda_s"] - physical_roots[j]["lambda_s"],
                ))
                largest_sep = max(largest_sep, sep)

        print(
            f"  candidate {rank}: dense multi-start -> {len(ms_roots)} root cluster(s), "
            f"{len(physical_roots)} physical, largest separation={largest_sep:.5f}"
        )
        print(f"  candidate {rank}: building {args.final_resolution}x{args.final_resolution} physical map...")

        data = cc_run.build_map(
            bundle.ref,
            bundle.sample,
            "physical",
            int(args.final_resolution),
        )
        np.savez_compressed(
            candidate_dir / "highres_physical_map.npz",
            **{k: v for k, v in data.items() if isinstance(v, np.ndarray)},
        )
        title = (
            f"Multiple physical stick-stick roots | frozen frame {args.frame} | "
            f"Tp={row['refined_Tp_Nm']:+.2f} Nm, Ts={row['refined_Ts_Nm']:+.2f} Nm | "
            f"{len(physical_roots)} physical root(s), max separation={largest_sep:.4f}"
        )
        plot_highres_candidate(
            data,
            physical_roots,
            title,
            candidate_dir / "highres_4x2.png",
        )
        final_summary.append({
            "candidate_rank": rank,
            "Tp_Nm": row["refined_Tp_Nm"],
            "Ts_Nm": row["refined_Ts_Nm"],
            "dense_distinct_roots": len(ms_roots),
            "dense_physical_roots": len(physical_roots),
            "largest_physical_root_separation": largest_sep,
            "highres_generated": True,
            "highres_resolution": int(args.final_resolution),
        })

    write_rows(out / "final_summary.csv", final_summary)
    (out / "summary.txt").write_text(
        f"Frozen frame: {args.frame}\n"
        f"Explore resolution: {args.explore_resolution}\n"
        f"Torque limit: +/-{args.torque_limit} Nm\n"
        f"Coarse seed count: {len(seeds)}\n"
        f"Refined candidate count: {len(refined)}\n"
        f"Good candidate count: {len(good)}\n"
        f"High-resolution finalist count requested: {args.highres_count}\n"
        f"Maximum sampled affine reconstruction residual: {affine_max:.6e} m/s^2\n",
        encoding="utf-8",
    )
    print()
    print(f"Complete. Outputs: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
