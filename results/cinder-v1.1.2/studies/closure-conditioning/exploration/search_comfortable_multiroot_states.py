r"""Search specifically for WELL-INSIDE, transversely crossing multiple stick roots.

Why this exists
---------------
The first multi-root search proved non-uniqueness, but its best-separation solutions
often placed the second root almost directly on a topology / lift-off boundary.
This study uses a different criterion:

    Find two roots which are BOTH
      * well separated from each other,
      * well separated from ALL physical-admissibility boundaries in lambda-space,
      * and formed by a clear transverse R_p=0 / R_s=0 crossing rather than a
        near-tangent double root.

It also fixes the previous "zoomed out" plotting mistake.  The expanded figure is
NOT the physical map with wider axis limits.  A separate expanded-domain closure map
is actually evaluated with `build_map(..., "expanded", ...)`.

Search strategy
---------------
Stage 0: audit any candidates already found by `exploration/search_multiroot_operating_point.py`.

For each root, measure:
  * exact topology/static admissibility,
  * an approximate Euclidean distance in (lambda_p,lambda_s) to the FIRST
    inadmissible point in many radial directions,
  * the acute crossing angle between grad(R_p) and grad(R_s).

A candidate only counts as "comfortable" if BOTH roots pass configurable thresholds.

Stage 1: if the existing candidate set does not provide enough comfortable examples,
search a small grid of nearby frozen mechanical states.  The search remains coarse:
  * low-resolution inverse torque maps,
  * only a few seed pairs per state,
  * no high-resolution maps.

Stage 2: ONLY for candidates which pass the comfort thresholds:
  * dense production multistart,
  * high-resolution PHYSICAL map,
  * separately evaluated high-resolution EXPANDED map,
  * one 4x2 figure for each map.

Typical run
-----------

From results/cinder-v1.1.2:

    python .\studies\closure-conditioning\exploration/search_comfortable_multiroot_states.py `
      --path-csv .\studies\closure-conditioning\artifacts\controlled-free-shift-animation\expanded_res641_locked_locked_path\preflight_path.csv `
      --frame 60 `
      --existing-search-dir .\studies\closure-conditioning\artifacts\multiroot-operating-point-search\frame_060

The default comfort criteria are intentionally much stricter than the previous study:
  * minimum root separation          = 0.15 lambda
  * minimum admissibility radius     = 0.05 lambda at BOTH roots
  * minimum contour crossing angle   = 15 deg at BOTH roots

If the existing candidates fail, a compact nearby-state search runs automatically.

Dependencies
------------
This helper expects the already-installed closure-conditioning study files, including
`exploration/search_multiroot_operating_point.py`.
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
from matplotlib.patches import Rectangle
import numpy as np

import run as cc_run
import animate_controlled_free_shift_path as controlled
import search_multiroot_operating_point as base

from cinder.model.cvt.contact import ContactInterface, ContactTractionUtilization
from cinder.model.cvt.dynamics.engaged_contact import EngagedContactClosure
from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint


HERE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = HERE / "artifacts" / "comfortable-multiroot-search"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--path-csv", type=Path, required=True)
    p.add_argument("--frame", type=int, default=60)
    p.add_argument("--existing-search-dir", type=Path, default=None,
                   help="Prior multiroot search output containing good_candidates.csv.")
    p.add_argument("--output-dir", type=Path, default=None)

    # Hard comfort criteria.
    p.add_argument("--minimum-root-separation", type=float, default=0.15)
    p.add_argument("--minimum-admissibility-radius", type=float, default=0.05,
                   help="Minimum Euclidean lambda-space distance from BOTH roots to the first physical-admissibility failure.")
    p.add_argument("--minimum-crossing-angle-deg", type=float, default=15.0,
                   help="Minimum acute angle between the R_p=0 and R_s=0 contours at BOTH roots.")
    p.add_argument("--minimum-normal-N", type=float, default=50.0)
    p.add_argument("--minimum-static-margin", type=float, default=0.0)

    # Exact geometric comfort-radius audit.
    p.add_argument("--radius-directions", type=int, default=32)
    p.add_argument("--radius-max", type=float, default=0.20)
    p.add_argument("--radius-steps", type=int, default=12)
    p.add_argument("--radius-bisection-steps", type=int, default=9)
    p.add_argument("--jacobian-step", type=float, default=1.0e-5)

    # Nearby frozen-state exploration, only used if existing candidates are insufficient.
    p.add_argument("--final-count", type=int, default=2,
                   help="Number of comfortable candidates desired before stopping.")
    p.add_argument("--shift-offsets", type=str, default="-0.20,-0.10,0.0,0.10,0.20",
                   help="Offsets applied to the base frame shift fraction.")
    p.add_argument("--shift-speeds-mm-s", type=str, default="0",
                   help="Comma-separated shift speeds searched. Example: -10,0,10")
    p.add_argument("--target-scales", type=str, default="0.80,1.00,1.20",
                   help="Multipliers on base belt-speed or primary-RPM target.")
    p.add_argument("--explore-resolution", type=int, default=41)
    p.add_argument("--torque-basis-step", type=float, default=1.0)
    p.add_argument("--torque-limit", type=float, default=260.0)
    p.add_argument("--max-torque-gain-condition", type=float, default=1.0e7)
    p.add_argument("--torque-match-radius", type=float, default=10.0)
    p.add_argument("--nearest-neighbours", type=int, default=12)
    p.add_argument("--minimum-seed-lambda-separation", type=float, default=0.10)
    p.add_argument("--seeds-per-state", type=int, default=4)
    p.add_argument("--candidate-torque-cluster-radius", type=float, default=6.0)
    p.add_argument("--local-torque-radius", type=float, default=8.0)
    p.add_argument("--local-torque-step", type=float, default=2.0)
    p.add_argument("--root-residual-tolerance", type=float, default=1.0e-6)
    p.add_argument("--root-cluster-tolerance", type=float, default=2.0e-4)
    p.add_argument("--comfort-audits", type=int, default=40,
                   help="Maximum globally promising new candidates receiving expensive radial comfort audits.")
    p.add_argument("--no-state-search", action="store_true",
                   help="Only audit the existing candidate set; do not explore nearby states.")

    # Finalization. These are only used after a candidate passes the comfort criteria.
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


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for i, row in enumerate(rows, start=1):
        row["_source_row"] = i
    return rows


def f(row: dict[str, Any], key: str) -> float:
    return float(row[key])


def clone_recipe(base_recipe: dict[str, Any], *, shift_fraction: float,
                 shift_speed_m_s: float, target_scale: float,
                 state_id: str) -> dict[str, Any]:
    recipe = dict(base_recipe)
    recipe["shift_fraction"] = float(np.clip(shift_fraction, 0.02, 0.98))
    recipe["shift_speed"] = float(shift_speed_m_s)
    recipe["state_id"] = state_id

    if recipe.get("target_primary_rpm") is not None:
        recipe["target_primary_rpm"] = float(recipe["target_primary_rpm"]) * float(target_scale)
    elif recipe.get("target_belt_speed") is not None:
        recipe["target_belt_speed"] = float(recipe["target_belt_speed"]) * float(target_scale)
    else:
        # Locked-path CSVs can sometimes omit the original target while retaining
        # the resolved value. Fall back to the resolved belt speed.
        resolved = recipe.get("resolved_belt_speed_m_s")
        if resolved in (None, "", "None"):
            raise ValueError("Recipe has neither a target nor resolved belt speed.")
        recipe["target_primary_rpm"] = None
        recipe["target_belt_speed"] = float(resolved) * float(target_scale)
    return recipe


def closure_bundle(decoded, library, recipe: dict[str, Any], tp: float, ts: float, reference_mode):
    local = dict(recipe)
    local["primary_torque_Nm"] = float(tp)
    local["secondary_torque_Nm"] = float(ts)
    system = base.make_bench_system(decoded, library, primary_torque=float(tp), secondary_torque=float(ts))
    cvt = controlled.state_for_recipe(system, local)
    state = base.full_state(system, cvt)
    boundaries = system._shaft_boundaries(time=0.0, state=state)
    snapshot = system.cvt.model.snapshot_at_time(
        time=0.0,
        state=cvt,
        shaft_boundaries=boundaries,
        geometry_side="engaged",
    )
    closure = EngagedContactClosure(snapshot=snapshot, shift_constraint=EngagedShiftConstraint.FREE)
    ref = cc_run.ReferenceRun(
        name=f"comfortable_multiroot_{local.get('state_id','state')}",
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


def residual(bundle, lp: float, ls: float) -> np.ndarray:
    return base.evaluate_residual(bundle.closure, float(lp), float(ls))


def point_admissible(bundle, lp: float, ls: float, args: argparse.Namespace) -> tuple[bool, dict[str, float]]:
    law = bundle.system.cvt.traction_law
    if not (
        law.primary_static_interval.lower <= lp <= law.primary_static_interval.upper
        and law.secondary_static_interval.lower <= ls <= law.secondary_static_interval.upper
    ):
        return False, {"reason_code": -10.0}

    utilization = ContactTractionUtilization(primary_lambda=float(lp), secondary_lambda=float(ls))
    try:
        trial = bundle.closure.evaluate_trial(
            traction_utilization=utilization,
            maximum_closure_condition_number=None,
            capture_diagnostics=True,
        )
        code, extra = cc_run.topology_failure_code(
            bundle.ref, bundle.sample, trial, utilization, bundle.snapshot
        )
    except Exception:
        return False, {"reason_code": -20.0}

    unknowns = trial.closure.unknowns
    p_margin = float(law.static_margin_at(ContactInterface.PRIMARY, lp))
    s_margin = float(law.static_margin_at(ContactInterface.SECONDARY, ls))
    ok = (
        code == 0
        and float(unknowns.primary_normal_resultant) >= float(args.minimum_normal_N)
        and float(unknowns.secondary_normal_resultant) >= float(args.minimum_normal_N)
        and p_margin >= float(args.minimum_static_margin)
        and s_margin >= float(args.minimum_static_margin)
    )
    return bool(ok), {
        "reason_code": float(code),
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


def admissibility_radius(bundle, lp: float, ls: float, args: argparse.Namespace) -> float:
    ok, _ = point_admissible(bundle, lp, ls, args)
    if not ok:
        return 0.0

    ndir = max(8, int(args.radius_directions))
    rmax = float(args.radius_max)
    nsteps = max(2, int(args.radius_steps))
    nbis = max(0, int(args.radius_bisection_steps))
    dr = rmax / nsteps
    minimum = rmax

    for theta in np.linspace(0.0, 2.0 * math.pi, ndir, endpoint=False):
        dx = math.cos(theta)
        dy = math.sin(theta)
        previous = 0.0
        boundary = rmax
        found = False
        for k in range(1, nsteps + 1):
            r = k * dr
            good, _ = point_admissible(bundle, lp + r * dx, ls + r * dy, args)
            if not good:
                lo, hi = previous, r
                for _ in range(nbis):
                    mid = 0.5 * (lo + hi)
                    good_mid, _ = point_admissible(bundle, lp + mid * dx, ls + mid * dy, args)
                    if good_mid:
                        lo = mid
                    else:
                        hi = mid
                boundary = lo
                found = True
                break
            previous = r
        if not found:
            boundary = rmax
        minimum = min(minimum, boundary)
        if minimum <= 0.0:
            return 0.0
    return float(minimum)


def root_jacobian(bundle, lp: float, ls: float, step: float) -> np.ndarray:
    rp = residual(bundle, lp + step, ls)
    rm = residual(bundle, lp - step, ls)
    sp = residual(bundle, lp, ls + step)
    sm = residual(bundle, lp, ls - step)
    return np.column_stack(((rp - rm) / (2.0 * step), (sp - sm) / (2.0 * step)))


def contour_crossing_angle_deg(J: np.ndarray) -> float:
    g1 = np.asarray(J[0, :], dtype=float)
    g2 = np.asarray(J[1, :], dtype=float)
    denom = float(np.linalg.norm(g1) * np.linalg.norm(g2))
    if denom <= 0.0 or not np.isfinite(denom):
        return 0.0
    s = abs(float(np.linalg.det(J))) / denom
    s = min(1.0, max(0.0, s))
    return float(math.degrees(math.asin(s)))


def candidate_exact_metrics(decoded, library, recipe, reference_mode,
                            row: dict[str, Any], args: argparse.Namespace,
                            *, run_radius: bool) -> dict[str, Any]:
    bundle = closure_bundle(
        decoded, library, recipe,
        f(row, "refined_Tp_Nm"), f(row, "refined_Ts_Nm"),
        reference_mode,
    )
    roots = [
        (f(row, "root1_lambda_p"), f(row, "root1_lambda_s")),
        (f(row, "root2_lambda_p"), f(row, "root2_lambda_s")),
    ]

    out = dict(row)
    root_metrics = []
    for k, (lp, ls) in enumerate(roots, start=1):
        ok, diag = point_admissible(bundle, lp, ls, args)
        J = root_jacobian(bundle, lp, ls, float(args.jacobian_step))
        angle = contour_crossing_angle_deg(J)
        radius = admissibility_radius(bundle, lp, ls, args) if run_radius else float("nan")
        root_metrics.append((ok, diag, angle, radius))
        out.update({
            f"root{k}_admissible_exact": bool(ok),
            f"root{k}_crossing_angle_deg": angle,
            f"root{k}_admissibility_radius": radius,
            f"root{k}_mechanism_margin": diag.get("mechanism_margin", float("nan")),
            f"root{k}_min_local_normal": min(
                diag.get("min_local_normal_p", float("nan")),
                diag.get("min_local_normal_s", float("nan")),
            ),
            f"root{k}_min_belt_tension": diag.get("min_belt_tension", float("nan")),
            f"root{k}_N_min": min(diag.get("N_p", float("nan")), diag.get("N_s", float("nan"))),
            f"root{k}_static_margin_min": min(
                diag.get("primary_static_margin", float("nan")),
                diag.get("secondary_static_margin", float("nan")),
            ),
            f"root{k}_A_condition_scaled": diag.get("A_condition_scaled", float("nan")),
            f"root{k}_J_condition": float(np.linalg.cond(J)),
            f"root{k}_J_det": float(np.linalg.det(J)),
        })

    separation = float(np.hypot(
        roots[0][0] - roots[1][0],
        roots[0][1] - roots[1][1],
    ))
    min_angle = min(metric[2] for metric in root_metrics)
    min_radius = min(metric[3] for metric in root_metrics) if run_radius else float("nan")
    both_admissible = all(metric[0] for metric in root_metrics)

    out.update({
        "verified_root_separation": separation,
        "minimum_crossing_angle_deg": min_angle,
        "minimum_admissibility_radius": min_radius,
        "both_roots_admissible_exact": bool(both_admissible),
    })
    comfortable = (
        both_admissible
        and separation >= float(args.minimum_root_separation)
        and min_angle >= float(args.minimum_crossing_angle_deg)
        and (not run_radius or min_radius >= float(args.minimum_admissibility_radius))
    )
    out["comfortable"] = bool(comfortable)
    return out


def inverse_torque_map_fast(decoded, library, recipe, reference_mode, args: argparse.Namespace):
    dt = float(args.torque_basis_step)
    b0 = closure_bundle(decoded, library, recipe, 0.0, 0.0, reference_mode)
    bp = closure_bundle(decoded, library, recipe, dt, 0.0, reference_mode)
    bs = closure_bundle(decoded, library, recipe, 0.0, dt, reference_mode)

    law = b0.system.cvt.traction_law
    lp_axis = np.linspace(
        law.primary_static_interval.lower,
        law.primary_static_interval.upper,
        int(args.explore_resolution),
    )
    ls_axis = np.linspace(
        law.secondary_static_interval.lower,
        law.secondary_static_interval.upper,
        int(args.explore_resolution),
    )
    shape = (len(ls_axis), len(lp_axis))
    tp_req = np.full(shape, np.nan)
    ts_req = np.full(shape, np.nan)
    gain_cond = np.full(shape, np.nan)

    for i, ls in enumerate(ls_axis):
        for j, lp in enumerate(lp_axis):
            try:
                r0 = residual(b0, lp, ls)
                rp = residual(bp, lp, ls)
                rs = residual(bs, lp, ls)
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
            except Exception:
                continue

    return {
        "lambda_p": lp_axis,
        "lambda_s": ls_axis,
        "required_Tp": tp_req,
        "required_Ts": ts_req,
        "torque_gain_condition": gain_cond,
    }


def state_recipes(base_recipe: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    base_shift = float(base_recipe["shift_fraction"])
    offsets = parse_float_list(args.shift_offsets)
    speeds = parse_float_list(args.shift_speeds_mm_s)
    scales = parse_float_list(args.target_scales)

    recipes = []
    seen = set()
    for offset in offsets:
        shift_fraction = float(np.clip(base_shift + offset, 0.02, 0.98))
        for speed_mm_s in speeds:
            for scale in scales:
                key = (round(shift_fraction, 8), round(speed_mm_s, 8), round(scale, 8))
                if key in seen:
                    continue
                seen.add(key)
                state_id = (
                    f"sf{shift_fraction:.3f}_sdot{speed_mm_s:+.0f}mmps_scale{scale:.2f}"
                    .replace("+", "p").replace("-", "m").replace(".", "p")
                )
                recipes.append(clone_recipe(
                    base_recipe,
                    shift_fraction=shift_fraction,
                    shift_speed_m_s=float(speed_mm_s) / 1000.0,
                    target_scale=scale,
                    state_id=state_id,
                ))
    return recipes


def refinement_args(args: argparse.Namespace):
    # Reuse the previous local two-seed refinement with this lightweight namespace.
    return SimpleNamespace(
        local_torque_radius=float(args.local_torque_radius),
        local_torque_step=float(args.local_torque_step),
        torque_limit=float(args.torque_limit),
        root_residual_tolerance=float(args.root_residual_tolerance),
        root_cluster_tolerance=float(args.root_cluster_tolerance),
        minimum_normal_N=float(args.minimum_normal_N),
        minimum_static_margin=float(args.minimum_static_margin),
    )


def seed_args(args: argparse.Namespace):
    return SimpleNamespace(
        nearest_neighbours=int(args.nearest_neighbours),
        torque_match_radius=float(args.torque_match_radius),
        minimum_seed_lambda_separation=float(args.minimum_seed_lambda_separation),
        candidate_torque_cluster_radius=float(args.candidate_torque_cluster_radius),
        verify_candidates=int(args.seeds_per_state),
    )


def preliminary_score(row: dict[str, Any]) -> tuple:
    # Used only to decide which newly found candidates deserve radial comfort audits.
    # Avoid combining unlike units into one arbitrary scalar.  Use a lexicographic
    # preference: two exact roots, then larger local-normal/mechanism/static margins,
    # then root separation.
    return (
        int(row.get("both_roots_admissible_exact", False)),
        min(float(row.get("root1_static_margin_min", -1.0)), float(row.get("root2_static_margin_min", -1.0))),
        min(float(row.get("root1_min_local_normal", -1.0)), float(row.get("root2_min_local_normal", -1.0))),
        min(float(row.get("root1_mechanism_margin", -1.0)), float(row.get("root2_mechanism_margin", -1.0))),
        float(row.get("verified_root_separation", 0.0)),
        float(row.get("minimum_crossing_angle_deg", 0.0)),
    )


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
                (p0, s0), p1 - p0, s1 - s0,
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
            (p0, s0), p1 - p0, s1 - s0,
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


def finalize_candidate(decoded, library, recipe, reference_mode,
                       row: dict[str, Any], outdir: Path, args: argparse.Namespace) -> dict[str, Any]:
    bundle = closure_bundle(
        decoded, library, recipe,
        f(row, "refined_Tp_Nm"), f(row, "refined_Ts_Nm"),
        reference_mode,
    )

    ms_rows, ms_roots = base.production_multistart(
        bundle,
        int(args.final_multistart),
        float(args.root_cluster_tolerance),
    )
    write_rows(outdir / "final_multistart.csv", ms_rows)
    write_rows(outdir / "final_root_diagnostics.csv", ms_roots)
    physical_roots = [root for root in ms_roots if bool(root["physical"])]
    if len(physical_roots) < 2:
        return {
            **row,
            "finalized": False,
            "reason": "dense_multistart_found_fewer_than_two_physical_roots",
            "dense_physical_root_count": len(physical_roots),
        }

    # Use the two most separated physical roots for the final comfort audit and plots.
    best_pair = None
    best_sep = -1.0
    for i in range(len(physical_roots)):
        for j in range(i + 1, len(physical_roots)):
            sep = float(np.hypot(
                physical_roots[i]["lambda_p"] - physical_roots[j]["lambda_p"],
                physical_roots[i]["lambda_s"] - physical_roots[j]["lambda_s"],
            ))
            if sep > best_sep:
                best_sep = sep
                best_pair = (physical_roots[i], physical_roots[j])
    assert best_pair is not None

    final_radii = [
        admissibility_radius(bundle, r["lambda_p"], r["lambda_s"], args)
        for r in best_pair
    ]
    final_angles = [
        contour_crossing_angle_deg(
            root_jacobian(bundle, r["lambda_p"], r["lambda_s"], float(args.jacobian_step))
        )
        for r in best_pair
    ]
    final_comfortable = (
        best_sep >= float(args.minimum_root_separation)
        and min(final_radii) >= float(args.minimum_admissibility_radius)
        and min(final_angles) >= float(args.minimum_crossing_angle_deg)
    )
    if not final_comfortable:
        return {
            **row,
            "finalized": False,
            "reason": "dense_roots_failed_final_comfort_recheck",
            "dense_physical_root_count": len(physical_roots),
            "final_pair_separation": best_sep,
            "final_min_admissibility_radius": min(final_radii),
            "final_min_crossing_angle_deg": min(final_angles),
        }

    # TRUE physical-domain map.
    physical = cc_run.build_map(
        bundle.ref, bundle.sample, "physical", int(args.physical_resolution)
    )
    np.savez_compressed(
        outdir / "highres_physical_map.npz",
        **{k: v for k, v in physical.items() if isinstance(v, np.ndarray)},
    )
    plot_4x2(
        physical,
        list(best_pair),
        (
            f"Comfortable multiple roots - PHYSICAL map | "
            f"sep={best_sep:.4f}, min admissibility radius={min(final_radii):.4f}, "
            f"min crossing angle={min(final_angles):.1f} deg"
        ),
        outdir / "highres_4x2_physical.png",
        ref=bundle.ref,
        show_static_box=False,
    )

    # TRUE expanded-domain map: this is a NEW closure-map evaluation over the
    # expanded lambda range, not a plot-axis change.
    expanded = cc_run.build_map(
        bundle.ref, bundle.sample, "expanded", int(args.expanded_resolution)
    )
    np.savez_compressed(
        outdir / "highres_expanded_map.npz",
        **{k: v for k, v in expanded.items() if isinstance(v, np.ndarray)},
    )
    plot_4x2(
        expanded,
        list(best_pair),
        (
            f"Comfortable multiple roots - EXPANDED map | "
            f"sep={best_sep:.4f}, min admissibility radius={min(final_radii):.4f}, "
            f"min crossing angle={min(final_angles):.1f} deg"
        ),
        outdir / "highres_4x2_expanded.png",
        ref=bundle.ref,
        show_static_box=True,
    )

    return {
        **row,
        "finalized": True,
        "dense_physical_root_count": len(physical_roots),
        "final_pair_separation": best_sep,
        "final_root1_lambda_p": best_pair[0]["lambda_p"],
        "final_root1_lambda_s": best_pair[0]["lambda_s"],
        "final_root2_lambda_p": best_pair[1]["lambda_p"],
        "final_root2_lambda_s": best_pair[1]["lambda_s"],
        "final_root1_admissibility_radius": final_radii[0],
        "final_root2_admissibility_radius": final_radii[1],
        "final_root1_crossing_angle_deg": final_angles[0],
        "final_root2_crossing_angle_deg": final_angles[1],
        "physical_resolution": int(args.physical_resolution),
        "expanded_resolution": int(args.expanded_resolution),
    }


def main() -> int:
    args = parse_args()
    cc_run.verify_environment()
    decoded, library = controlled.load_base()
    base_recipe = base.frozen_recipe(args.path_csv.resolve(), int(args.frame))
    _, base_sample = controlled.make_ref_and_sample(decoded, library, base_recipe)
    reference_mode = base_sample.composed_mode

    out = args.output_dir.resolve() if args.output_dir else DEFAULT_OUTPUT / f"frame_{args.frame:03d}"
    out.mkdir(parents=True, exist_ok=True)

    comfortable: list[dict[str, Any]] = []
    audited_existing: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Stage 0: audit every already-found candidate with geometric metrics.
    # ------------------------------------------------------------------
    if args.existing_search_dir is not None:
        candidate_file = args.existing_search_dir.resolve() / "good_candidates.csv"
        if candidate_file.exists():
            print("Stage 0: exact comfort audit of existing candidates...")
            existing = read_rows(candidate_file)
            for idx, row in enumerate(existing, start=1):
                row["state_id"] = f"existing_frame_{args.frame:03d}"
                metrics = candidate_exact_metrics(
                    decoded, library, base_recipe, reference_mode, row, args,
                    run_radius=True,
                )
                audited_existing.append(metrics)
                if metrics["comfortable"]:
                    comfortable.append(metrics)
                print(
                    f"  existing {idx:02d}/{len(existing):02d}: "
                    f"sep={metrics['verified_root_separation']:.4f}, "
                    f"min radius={metrics['minimum_admissibility_radius']:.4f}, "
                    f"min angle={metrics['minimum_crossing_angle_deg']:.1f} deg, "
                    f"comfortable={metrics['comfortable']}"
                )
            write_rows(out / "existing_candidate_comfort_audit.csv", audited_existing)

    # ------------------------------------------------------------------
    # Stage 1: search nearby frozen states only if needed.
    # ------------------------------------------------------------------
    explored_rows: list[dict[str, Any]] = []
    if len(comfortable) < int(args.final_count) and not args.no_state_search:
        recipes = state_recipes(base_recipe, args)
        print()
        print(
            f"Stage 1: nearby-state coarse exploration ({len(recipes)} frozen states, "
            f"{args.explore_resolution}x{args.explore_resolution} inverse maps)..."
        )

        found_preliminary: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for state_index, recipe in enumerate(recipes, start=1):
            print(
                f"  state {state_index:02d}/{len(recipes):02d}: "
                f"{recipe['state_id']} | shift={recipe['shift_fraction']:.3f}, "
                f"sdot={1000.0*recipe['shift_speed']:+.1f} mm/s"
            )
            try:
                inv = inverse_torque_map_fast(decoded, library, recipe, reference_mode, args)
                seeds = base.coarse_seed_pairs(inv, seed_args(args))
            except Exception as exc:
                print(f"    inverse-map failure: {type(exc).__name__}: {exc}")
                continue

            for seed in seeds[:int(args.seeds_per_state)]:
                refined = base.refine_seed_candidate(
                    decoded, library, recipe, reference_mode,
                    seed, refinement_args(args),
                )
                if refined is None or int(refined["physical_root_count"]) < 2:
                    continue
                refined["state_id"] = recipe["state_id"]
                refined["state_shift_fraction"] = float(recipe["shift_fraction"])
                refined["state_shift_speed_m_s"] = float(recipe["shift_speed"])
                refined["state_target_primary_rpm"] = recipe.get("target_primary_rpm")
                refined["state_target_belt_speed"] = recipe.get("target_belt_speed")

                # Exact root metrics, but defer radial radius search until we know
                # which candidates are globally promising.
                exact = candidate_exact_metrics(
                    decoded, library, recipe, reference_mode, refined, args,
                    run_radius=False,
                )
                found_preliminary.append((exact, recipe))

        # Select a diverse promising set for the more expensive radial audit.
        # Union several orderings so a candidate cannot be hidden merely because
        # one margin uses different physical units.
        pools: list[tuple[dict[str, Any], dict[str, Any]]] = []
        seen_keys = set()

        def add_ordered(items, keyfunc, count):
            for item in sorted(items, key=keyfunc, reverse=True)[:count]:
                row, recipe = item
                key = (
                    row["state_id"],
                    round(float(row["refined_Tp_Nm"]), 6),
                    round(float(row["refined_Ts_Nm"]), 6),
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    pools.append(item)

        n_each = max(5, int(args.comfort_audits) // 4)
        add_ordered(found_preliminary, lambda x: x[0]["verified_root_separation"], n_each)
        add_ordered(found_preliminary, lambda x: x[0]["minimum_crossing_angle_deg"], n_each)
        add_ordered(
            found_preliminary,
            lambda x: min(float(x[0]["root1_static_margin_min"]), float(x[0]["root2_static_margin_min"])),
            n_each,
        )
        add_ordered(
            found_preliminary,
            lambda x: min(float(x[0]["root1_mechanism_margin"]), float(x[0]["root2_mechanism_margin"])),
            n_each,
        )
        pools = pools[:int(args.comfort_audits)]

        print()
        print(f"  radial comfort audits for {len(pools)} promising new candidates...")
        for idx, (row, recipe) in enumerate(pools, start=1):
            exact = candidate_exact_metrics(
                decoded, library, recipe, reference_mode, row, args,
                run_radius=True,
            )
            explored_rows.append(exact)
            if exact["comfortable"]:
                comfortable.append(exact)
            print(
                f"    audit {idx:02d}/{len(pools):02d}: {exact['state_id']} | "
                f"sep={exact['verified_root_separation']:.4f}, "
                f"min radius={exact['minimum_admissibility_radius']:.4f}, "
                f"min angle={exact['minimum_crossing_angle_deg']:.1f} deg, "
                f"comfortable={exact['comfortable']}"
            )

        write_rows(out / "new_state_candidate_comfort_audit.csv", explored_rows)

    # ------------------------------------------------------------------
    # Rank and finalize only truly comfortable cases.
    # ------------------------------------------------------------------
    # Deduplicate identical operating points.
    unique = []
    seen = set()
    for row in comfortable:
        key = (
            row.get("state_id", ""),
            round(float(row["refined_Tp_Nm"]), 6),
            round(float(row["refined_Ts_Nm"]), 6),
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)

    # Lexicographic ranking: physical interior first, then clear line crossing,
    # then root separation. No arbitrary mixed-unit "robust score".
    unique.sort(
        key=lambda r: (
            float(r["minimum_admissibility_radius"]),
            float(r["minimum_crossing_angle_deg"]),
            float(r["verified_root_separation"]),
        ),
        reverse=True,
    )
    write_rows(out / "comfortable_candidates.csv", unique)

    if not unique:
        (out / "summary.txt").write_text(
            "No candidate satisfied the configured comfort criteria.\n"
            "No high-resolution map was generated.\n"
            f"minimum_root_separation={args.minimum_root_separation}\n"
            f"minimum_admissibility_radius={args.minimum_admissibility_radius}\n"
            f"minimum_crossing_angle_deg={args.minimum_crossing_angle_deg}\n",
            encoding="utf-8",
        )
        print()
        print("No comfortable two-root example found. No high-resolution maps generated.")
        print(f"Outputs: {out}")
        return 0

    finalists = unique[:int(args.final_count)]
    write_rows(out / "selected_finalists.csv", finalists)

    print()
    print(f"Stage 2: dense verification and TRUE physical + expanded high-resolution maps for {len(finalists)} finalist(s)...")
    final_rows = []
    for rank, row in enumerate(finalists, start=1):
        state_id = str(row["state_id"])
        if state_id.startswith("existing_frame_"):
            recipe = base_recipe
        else:
            # Reconstruct the searched recipe from metadata.
            recipe = clone_recipe(
                base_recipe,
                shift_fraction=float(row["state_shift_fraction"]),
                shift_speed_m_s=float(row["state_shift_speed_m_s"]),
                target_scale=1.0,
                state_id=state_id,
            )
            # Preserve the exact searched target rather than reapplying a scale.
            tpr = row.get("state_target_primary_rpm")
            tbs = row.get("state_target_belt_speed")
            if tpr not in (None, "", "None"):
                recipe["target_primary_rpm"] = float(tpr)
                recipe["target_belt_speed"] = None
            elif tbs not in (None, "", "None"):
                recipe["target_primary_rpm"] = None
                recipe["target_belt_speed"] = float(tbs)

        candidate_dir = out / f"finalist_{rank:02d}_{state_id}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        result = finalize_candidate(
            decoded, library, recipe, reference_mode,
            row, candidate_dir, args,
        )
        final_rows.append(result)
        print(
            f"  finalist {rank}: finalized={result.get('finalized')} | "
            f"state={state_id} | T=({float(row['refined_Tp_Nm']):+.2f}, "
            f"{float(row['refined_Ts_Nm']):+.2f}) Nm"
        )

    write_rows(out / "final_summary.csv", final_rows)
    (out / "summary.txt").write_text(
        f"comfortable_candidate_count={len(unique)}\n"
        f"finalist_count={len(finalists)}\n"
        f"minimum_root_separation={args.minimum_root_separation}\n"
        f"minimum_admissibility_radius={args.minimum_admissibility_radius}\n"
        f"minimum_crossing_angle_deg={args.minimum_crossing_angle_deg}\n"
        "Expanded maps were evaluated independently over the expanded lambda domain.\n",
        encoding="utf-8",
    )
    print()
    print(f"Complete. Outputs: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
