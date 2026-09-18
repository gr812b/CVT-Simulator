"""Search the true one-contact (mixed slip/stick) CINDER closures for multiple roots.

This is deliberately NOT a post-processing view of the two-contact STICK_STICK
fold.  It studies the actual 1D mixed branches:

    PRIMARY_SLIP_SECONDARY_STICK:
        lambda_p = +/- mu_k,p is fixed kinetically
        solve R_s(lambda_s) = 0

    PRIMARY_STICK_SECONDARY_SLIP:
        lambda_s = +/- mu_k,s is fixed kinetically
        solve R_p(lambda_p) = 0

For each frozen state, each kinetic slip direction, and each chosen fixed shaft
torque, the script constructs the scalar residual family and asks whether one
horizontal torque slice produces two physically admissible sticking roots.

The expensive mechanical response still comes from the same fixed-lambda
8x8 closure used everywhere else.  The speedup comes from exploiting the
exact affine dependence of the sticking residual on external shaft torques:

    R(lambda; Tp, Ts) = R0(lambda) + Gp(lambda) Tp + Gs(lambda) Ts.

Therefore, after three mechanical evaluations per lambda sample, many torque
slices can be explored cheaply.

The script searches for folds of the 1D closure and ranks them by:
  * two physically admissible roots on one torque slice,
  * root separation in lambda,
  * distance from the double-root fold to the selected two-root slice,
  * static-capacity clearance of the sticking contact,
  * local-wrap / mechanism margins,
  * transversality of the two simple roots.

It renders the clearest case as:
  * required_torque_fold.png
  * scalar_residual_two_roots.png
  * branch_physics.png
  * one_contact_fold_birth.gif
  * one_contact_fold_interactive.html
  * best_candidate.json
  * curve.csv / branch_physics.csv

Dependencies
------------
This study uses the existing closure-conditioning helpers already present beside
it in the user's results tree:

    run.py
    exploration/animate_controlled_free_shift_path.py
    exploration/search_multiroot_operating_point.py
    exploration/global_comfortable_multiroot_search.py

Typical run from results/cinder-v1.1.2
--------------------------------------

    python .\\studies\\closure-conditioning\\analysis/search_one_contact_multiroot_folds.py `
      --global-search-dir .\\studies\\closure-conditioning\\artifacts\\global-comfortable-multiroot-search `
      --reference-path-csv .\\studies\\closure-conditioning\\artifacts\\controlled-free-shift-animation\\expanded_res641_locked_locked_path\\preflight_path.csv `
      --reference-frame 60 `
      --workers -1 `
      --lambda-samples 241 `
      --fixed-torque-samples 41 `
      --gif-frames 84

By default the state set is the union of unique frozen states represented in
all_two_root_candidates_precomfort.csv and comfort_audit_results.csv.  These
rows carry the resolved frozen-state data needed by
global_comfortable_multiroot_search.rebuild_recipe_from_candidate().

The search is intentionally broad over both mixed modes, both kinetic signs,
both possible choices of continued shaft torque, and a wide fixed-torque grid.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.optimize import brentq, minimize_scalar

import run as cc_run
import animate_controlled_free_shift_path as controlled
import search_multiroot_operating_point as base
import global_comfortable_multiroot_search as global_search

from cinder.model.cvt.contact import (
    ContactInterface,
    ContactKinematicTolerances,
    ContactTractionUtilization,
    SlipDirection,
)


HERE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = HERE / "artifacts" / "one-contact-multiroot-fold-search"


@dataclass(frozen=True)
class BranchSpec:
    branch_name: str
    sliding_interface: ContactInterface
    sticking_interface: ContactInterface
    kinetic_sign: int
    residual_index: int

    @property
    def direction(self) -> SlipDirection:
        return (
            SlipDirection.PULLEY_LEADS_BELT
            if self.kinetic_sign > 0
            else SlipDirection.BELT_LEADS_PULLEY
        )

    @property
    def short_name(self) -> str:
        slip = "p" if self.sliding_interface is ContactInterface.PRIMARY else "s"
        stick = "s" if self.sticking_interface is ContactInterface.SECONDARY else "p"
        sign = "plus" if self.kinetic_sign > 0 else "minus"
        return f"{slip}_slip_{sign}_{stick}_stick"


BRANCHES = (
    BranchSpec(
        branch_name="primary slip (+mu_k), secondary stick",
        sliding_interface=ContactInterface.PRIMARY,
        sticking_interface=ContactInterface.SECONDARY,
        kinetic_sign=+1,
        residual_index=1,
    ),
    BranchSpec(
        branch_name="primary slip (-mu_k), secondary stick",
        sliding_interface=ContactInterface.PRIMARY,
        sticking_interface=ContactInterface.SECONDARY,
        kinetic_sign=-1,
        residual_index=1,
    ),
    BranchSpec(
        branch_name="primary stick, secondary slip (+mu_k)",
        sliding_interface=ContactInterface.SECONDARY,
        sticking_interface=ContactInterface.PRIMARY,
        kinetic_sign=+1,
        residual_index=0,
    ),
    BranchSpec(
        branch_name="primary stick, secondary slip (-mu_k)",
        sliding_interface=ContactInterface.SECONDARY,
        sticking_interface=ContactInterface.PRIMARY,
        kinetic_sign=-1,
        residual_index=0,
    ),
)


# Worker globals.
_W_DECODED = None
_W_LIBRARY = None
_W_REFERENCE_MODE = None
_W_CFG: dict[str, Any] | None = None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--global-search-dir", type=Path, required=True)
    p.add_argument("--reference-path-csv", type=Path, required=True)
    p.add_argument("--reference-frame", type=int, default=60)
    p.add_argument("--output-dir", type=Path, default=None)

    p.add_argument("--workers", type=int, default=-1,
                   help="-1 uses all CPUs; 0/1 disables multiprocessing.")
    p.add_argument("--lambda-samples", type=int, default=241)
    p.add_argument("--fixed-torque-samples", type=int, default=41)
    p.add_argument("--torque-limit-Nm", type=float, default=260.0)
    p.add_argument("--torque-basis-step-Nm", type=float, default=1.0)
    p.add_argument("--required-torque-limit-Nm", type=float, default=360.0)
    p.add_argument("--gain-epsilon", type=float, default=1.0e-8)
    p.add_argument("--minimum-root-separation", type=float, default=0.06)
    p.add_argument("--minimum-static-margin", type=float, default=0.01)
    p.add_argument("--minimum-local-normal", type=float, default=-1.0e-6)
    p.add_argument("--minimum-mechanism-margin", type=float, default=-1.0e-6)
    p.add_argument("--minimum-normal-N", type=float, default=1.0)
    p.add_argument("--levels-per-fold", type=int, default=18)
    p.add_argument("--max-states", type=int, default=0,
                   help="0 scans every unique state in the source CSVs.")
    p.add_argument("--top-candidates", type=int, default=30)
    p.add_argument("--gif-frames", type=int, default=84)
    p.add_argument("--gif-fps", type=int, default=12)
    p.add_argument("--render-dpi", type=int, default=175)
    return p.parse_args()


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


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


def finite_float(row: dict[str, Any], key: str, default: float = float("nan")) -> float:
    try:
        value = float(row[key])
        return value if math.isfinite(value) else default
    except Exception:
        return default


def collect_unique_states(search_dir: Path, max_states: int) -> list[dict[str, Any]]:
    sources = [
        search_dir / "all_two_root_candidates_precomfort.csv",
        search_dir / "comfort_audit_results.csv",
        search_dir / "best_near_misses.csv",
    ]
    rows: list[dict[str, Any]] = []
    for source in sources:
        rows.extend(read_rows(source))

    by_state: dict[str, dict[str, Any]] = {}
    for row in rows:
        state_id = str(row.get("state_id", "")).strip()
        if not state_id:
            continue
        required = (
            "shift_fraction",
            "shift_speed_mm_s",
            "target_primary_rpm",
            "resolved_primary_rpm",
            "resolved_secondary_rpm",
            "resolved_belt_speed_m_s",
        )
        if not all(k in row and str(row[k]).strip() for k in required):
            continue
        if state_id not in by_state:
            by_state[state_id] = dict(row)

    ordered = sorted(
        by_state.values(),
        key=lambda r: (
            finite_float(r, "shift_fraction", 0.0),
            finite_float(r, "shift_speed_mm_s", 0.0),
            finite_float(r, "target_primary_rpm", 0.0),
        ),
    )
    if max_states > 0:
        ordered = ordered[:max_states]
    return ordered


def _worker_init(reference_path: str, reference_frame: int, cfg: dict[str, Any]) -> None:
    global _W_DECODED, _W_LIBRARY, _W_REFERENCE_MODE, _W_CFG
    _W_DECODED, _W_LIBRARY = controlled.load_base()
    _W_REFERENCE_MODE = global_search.reference_mode_from_path(
        _W_DECODED,
        _W_LIBRARY,
        Path(reference_path),
        int(reference_frame),
    )
    _W_CFG = dict(cfg)


def utilization_for(
    branch: BranchSpec,
    kinetic_lambda: float,
    stick_lambda: float,
) -> ContactTractionUtilization:
    if branch.sliding_interface is ContactInterface.PRIMARY:
        return ContactTractionUtilization(
            primary_lambda=float(kinetic_lambda),
            secondary_lambda=float(stick_lambda),
        )
    return ContactTractionUtilization(
        primary_lambda=float(stick_lambda),
        secondary_lambda=float(kinetic_lambda),
    )


def residual_component(bundle, branch: BranchSpec, kinetic_lambda: float, stick_lambda: float) -> float:
    util = utilization_for(branch, kinetic_lambda, stick_lambda)
    rr = base.evaluate_residual(
        bundle.closure,
        util.primary_lambda,
        util.secondary_lambda,
    )
    return float(rr[branch.residual_index])


class AffineScalarFamily:
    def __init__(
        self,
        *,
        decoded,
        library,
        reference_mode,
        recipe: dict[str, Any],
        branch: BranchSpec,
        basis_step: float,
    ) -> None:
        self.decoded = decoded
        self.library = library
        self.reference_mode = reference_mode
        self.recipe = recipe
        self.branch = branch
        self.basis_step = float(basis_step)

        self.b00 = global_search.closure_bundle(
            decoded, library, recipe, 0.0, 0.0, reference_mode
        )
        self.bp = global_search.closure_bundle(
            decoded, library, recipe, self.basis_step, 0.0, reference_mode
        )
        self.bs = global_search.closure_bundle(
            decoded, library, recipe, 0.0, self.basis_step, reference_mode
        )
        self.law = self.b00.system.cvt.traction_law
        self.kinetic_magnitude = float(
            self.law.kinetic_lambda_magnitude_at(branch.sliding_interface)
        )
        self.kinetic_lambda = float(branch.kinetic_sign * self.kinetic_magnitude)
        self.static_interval = self.law.static_interval_at(branch.sticking_interface)

    def coefficients_at(self, stick_lambda: float) -> tuple[float, float, float]:
        r0 = residual_component(
            self.b00, self.branch, self.kinetic_lambda, stick_lambda
        )
        rp = residual_component(
            self.bp, self.branch, self.kinetic_lambda, stick_lambda
        )
        rs = residual_component(
            self.bs, self.branch, self.kinetic_lambda, stick_lambda
        )
        gp = (rp - r0) / self.basis_step
        gs = (rs - r0) / self.basis_step
        return float(r0), float(gp), float(gs)

    def sample_coefficients(self, lambdas: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        r0 = np.empty_like(lambdas, dtype=float)
        gp = np.empty_like(lambdas, dtype=float)
        gs = np.empty_like(lambdas, dtype=float)
        for i, lam in enumerate(lambdas):
            r0[i], gp[i], gs[i] = self.coefficients_at(float(lam))
        return r0, gp, gs

    def required_varied_torque(
        self,
        *,
        stick_lambda: float,
        varied: str,
        fixed_torque: float,
    ) -> float:
        r0, gp, gs = self.coefficients_at(stick_lambda)
        if varied == "secondary":
            if abs(gs) <= 1.0e-14:
                return float("nan")
            return float(-(r0 + gp * fixed_torque) / gs)
        if abs(gp) <= 1.0e-14:
            return float("nan")
        return float(-(r0 + gs * fixed_torque) / gp)

    def residual_at(
        self,
        *,
        stick_lambda: float,
        primary_torque: float,
        secondary_torque: float,
    ) -> float:
        r0, gp, gs = self.coefficients_at(stick_lambda)
        return float(r0 + gp * primary_torque + gs * secondary_torque)

    def bundle(self, tp: float, ts: float):
        return global_search.closure_bundle(
            self.decoded,
            self.library,
            self.recipe,
            float(tp),
            float(ts),
            self.reference_mode,
        )


def required_curve_from_coefficients(
    *,
    r0: np.ndarray,
    gp: np.ndarray,
    gs: np.ndarray,
    varied: str,
    fixed_torque: float,
    gain_epsilon: float,
    q_limit: float,
) -> np.ndarray:
    if varied == "secondary":
        den = gs
        num = -(r0 + gp * fixed_torque)
    else:
        den = gp
        num = -(r0 + gs * fixed_torque)
    out = np.full_like(r0, np.nan, dtype=float)
    good = np.isfinite(num) & np.isfinite(den) & (np.abs(den) > gain_epsilon)
    out[good] = num[good] / den[good]
    out[np.abs(out) > q_limit] = np.nan
    return out


def local_extrema_indices(values: np.ndarray) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for i in range(1, len(values) - 1):
        a, b, c = values[i - 1], values[i], values[i + 1]
        if not (np.isfinite(a) and np.isfinite(b) and np.isfinite(c)):
            continue
        if b > a and b >= c:
            out.append((i, "max"))
        elif b < a and b <= c:
            out.append((i, "min"))
    return out


def crossing_brackets(x: np.ndarray, y: np.ndarray, level: float) -> list[tuple[float, float]]:
    brackets: list[tuple[float, float]] = []
    f = y - level
    for i in range(len(x) - 1):
        a, b = f[i], f[i + 1]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        if a == 0.0:
            eps = max(1.0e-10, 0.1 * abs(x[i + 1] - x[i]))
            brackets.append((max(x[0], x[i] - eps), min(x[-1], x[i] + eps)))
            continue
        if a * b < 0.0 or b == 0.0:
            brackets.append((float(x[i]), float(x[i + 1])))
    return brackets


def refine_root_on_required_curve(
    family: AffineScalarFamily,
    *,
    varied: str,
    fixed_torque: float,
    q_level: float,
    bracket: tuple[float, float],
) -> float | None:
    def f(lam: float) -> float:
        return family.required_varied_torque(
            stick_lambda=float(lam),
            varied=varied,
            fixed_torque=float(fixed_torque),
        ) - q_level

    a, b = bracket
    try:
        fa = f(a)
        fb = f(b)
        if not (math.isfinite(fa) and math.isfinite(fb)):
            return None
        if fa == 0.0:
            return float(a)
        if fb == 0.0:
            return float(b)
        if fa * fb > 0.0:
            return None
        return float(brentq(f, a, b, xtol=1.0e-11, rtol=1.0e-11, maxiter=100))
    except Exception:
        return None


def diagnose_point(
    family: AffineScalarFamily,
    *,
    stick_lambda: float,
    varied: str,
    fixed_torque: float,
    varied_torque: float,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    if varied == "secondary":
        tp, ts = fixed_torque, varied_torque
    else:
        tp, ts = varied_torque, fixed_torque

    util = utilization_for(
        family.branch,
        family.kinetic_lambda,
        float(stick_lambda),
    )
    row: dict[str, Any] = {
        "stick_lambda": float(stick_lambda),
        "lambda_p": float(util.primary_lambda),
        "lambda_s": float(util.secondary_lambda),
        "primary_external_torque_Nm": float(tp),
        "secondary_external_torque_Nm": float(ts),
    }

    try:
        bundle = family.bundle(tp, ts)
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
        stick_margin = float(
            law.static_margin_at(
                family.branch.sticking_interface,
                float(stick_lambda),
            )
        )
        spec = law.kinetic_slip_specification(
            interface=family.branch.sliding_interface,
            direction=family.branch.direction,
        )
        try:
            direction_ok = bool(
                spec.direction_is_consistent(
                    trial.relative_motion,
                    tolerances=ContactKinematicTolerances(),
                )
            )
        except Exception:
            # Old helper snapshots can lack the richer relative-motion object.
            direction_ok = True

        physical = bool(
            int(code) == 0
            and stick_margin >= float(cfg["minimum_static_margin"])
            and float(extra["min_local_normal_p"]) >= float(cfg["minimum_local_normal"])
            and float(extra["min_local_normal_s"]) >= float(cfg["minimum_local_normal"])
            and float(extra["mechanism_margin"]) >= float(cfg["minimum_mechanism_margin"])
            and float(unknowns.primary_normal_resultant) >= float(cfg["minimum_normal_N"])
            and float(unknowns.secondary_normal_resultant) >= float(cfg["minimum_normal_N"])
            and direction_ok
        )
        row.update({
            "physical": physical,
            "topology_failure_code": int(code),
            "slip_direction_consistent": direction_ok,
            "stick_static_margin": stick_margin,
            "primary_normal_N": float(unknowns.primary_normal_resultant),
            "secondary_normal_N": float(unknowns.secondary_normal_resultant),
            "primary_interface_torque_Nm": float(unknowns.primary_torque),
            "secondary_interface_torque_Nm": float(unknowns.secondary_torque),
            "primary_angular_acceleration_rad_s2": float(unknowns.primary_angular_acceleration),
            "secondary_angular_acceleration_rad_s2": float(unknowns.secondary_angular_acceleration),
            "belt_acceleration_m_s2": float(unknowns.belt_acceleration),
            "shift_acceleration_m_s2": float(unknowns.shift_acceleration),
            "minimum_belt_tension_N": float(extra["min_belt_tension"]),
            "primary_min_local_normal": float(extra["min_local_normal_p"]),
            "secondary_min_local_normal": float(extra["min_local_normal_s"]),
            "minimum_local_normal": min(
                float(extra["min_local_normal_p"]),
                float(extra["min_local_normal_s"]),
            ),
            "mechanism_margin": float(extra["mechanism_margin"]),
            "A_condition_scaled": float(trial.closure.scaled_condition_number),
        })
    except Exception as exc:
        row.update({
            "physical": False,
            "topology_failure_code": -1,
            "slip_direction_consistent": False,
            "stick_static_margin": float("nan"),
            "primary_normal_N": float("nan"),
            "secondary_normal_N": float("nan"),
            "primary_interface_torque_Nm": float("nan"),
            "secondary_interface_torque_Nm": float("nan"),
            "primary_angular_acceleration_rad_s2": float("nan"),
            "secondary_angular_acceleration_rad_s2": float("nan"),
            "belt_acceleration_m_s2": float("nan"),
            "shift_acceleration_m_s2": float("nan"),
            "minimum_belt_tension_N": float("nan"),
            "primary_min_local_normal": float("nan"),
            "secondary_min_local_normal": float("nan"),
            "minimum_local_normal": float("nan"),
            "mechanism_margin": float("nan"),
            "A_condition_scaled": float("nan"),
            "diagnostic_error": f"{type(exc).__name__}: {exc}",
        })
    return row


def derivative_of_scalar_residual(
    family: AffineScalarFamily,
    *,
    lam: float,
    tp: float,
    ts: float,
) -> float:
    h = 1.0e-5
    lo = family.static_interval.lower
    hi = family.static_interval.upper
    a = max(lo, lam - h)
    b = min(hi, lam + h)
    if not b > a:
        return float("nan")
    fa = family.residual_at(
        stick_lambda=a,
        primary_torque=tp,
        secondary_torque=ts,
    )
    fb = family.residual_at(
        stick_lambda=b,
        primary_torque=tp,
        secondary_torque=ts,
    )
    return float((fb - fa) / (b - a))


def candidate_score(
    *,
    fold_excursion: float,
    root_sep: float,
    d1: dict[str, Any],
    d2: dict[str, Any],
    slope1: float,
    slope2: float,
) -> float:
    static_margin = min(float(d1["stick_static_margin"]), float(d2["stick_static_margin"]))
    local_normal = min(float(d1["minimum_local_normal"]), float(d2["minimum_local_normal"]))
    mechanism = min(float(d1["mechanism_margin"]), float(d2["mechanism_margin"]))
    transversality = min(abs(slope1), abs(slope2))
    return float(
        5.0 * root_sep
        + 0.10 * min(80.0, fold_excursion)
        + 2.5 * max(0.0, static_margin)
        + 0.10 * max(0.0, min(10.0, local_normal))
        + 0.10 * max(0.0, min(10.0, mechanism))
        + 0.002 * min(500.0, transversality)
    )


def best_pair_around_extremum(
    family: AffineScalarFamily,
    *,
    lambdas: np.ndarray,
    q_curve: np.ndarray,
    extremum_index: int,
    extremum_kind: str,
    varied: str,
    fixed_torque: float,
    cfg: dict[str, Any],
) -> dict[str, Any] | None:
    i = int(extremum_index)
    q_fold_seed = float(q_curve[i])
    if not math.isfinite(q_fold_seed):
        return None

    # Refine the fold location from the exact inverse scalar map.
    a = float(lambdas[max(0, i - 1)])
    b = float(lambdas[min(len(lambdas) - 1, i + 1)])
    if not b > a:
        return None

    def objective(lam: float) -> float:
        q = family.required_varied_torque(
            stick_lambda=float(lam),
            varied=varied,
            fixed_torque=float(fixed_torque),
        )
        if not math.isfinite(q):
            return 1.0e30
        return -q if extremum_kind == "max" else q

    try:
        opt = minimize_scalar(objective, bounds=(a, b), method="bounded",
                              options={"xatol": 1.0e-10, "maxiter": 100})
        if not opt.success:
            return None
        lam_fold = float(opt.x)
        q_fold = float(
            family.required_varied_torque(
                stick_lambda=lam_fold,
                varied=varied,
                fixed_torque=float(fixed_torque),
            )
        )
    except Exception:
        return None

    left = q_curve[: i + 1]
    right = q_curve[i:]
    if extremum_kind == "max":
        if not (np.any(np.isfinite(left)) and np.any(np.isfinite(right))):
            return None
        q_deep = max(float(np.nanmin(left)), float(np.nanmin(right)))
        if not q_fold > q_deep:
            return None
        levels = np.linspace(q_fold - 0.04 * (q_fold - q_deep),
                             q_deep + 0.08 * (q_fold - q_deep),
                             int(cfg["levels_per_fold"]))
    else:
        if not (np.any(np.isfinite(left)) and np.any(np.isfinite(right))):
            return None
        q_deep = min(float(np.nanmax(left)), float(np.nanmax(right)))
        if not q_fold < q_deep:
            return None
        levels = np.linspace(q_fold + 0.04 * (q_deep - q_fold),
                             q_deep - 0.08 * (q_deep - q_fold),
                             int(cfg["levels_per_fold"]))

    q_limit = float(cfg["torque_limit_Nm"])
    best: dict[str, Any] | None = None
    best_score = -float("inf")

    for q_level in levels:
        if abs(float(q_level)) > q_limit:
            continue

        brackets = crossing_brackets(lambdas, q_curve, float(q_level))
        roots: list[float] = []
        for bracket in brackets:
            root = refine_root_on_required_curve(
                family,
                varied=varied,
                fixed_torque=float(fixed_torque),
                q_level=float(q_level),
                bracket=bracket,
            )
            if root is not None:
                if not roots or min(abs(root - rr) for rr in roots) > 1.0e-5:
                    roots.append(root)
        roots.sort()

        left_roots = [r for r in roots if r < lam_fold]
        right_roots = [r for r in roots if r > lam_fold]
        if not left_roots or not right_roots:
            continue
        root1 = max(left_roots)
        root2 = min(right_roots)
        sep = abs(root2 - root1)
        if sep < float(cfg["minimum_root_separation"]):
            continue

        d1 = diagnose_point(
            family,
            stick_lambda=root1,
            varied=varied,
            fixed_torque=float(fixed_torque),
            varied_torque=float(q_level),
            cfg=cfg,
        )
        d2 = diagnose_point(
            family,
            stick_lambda=root2,
            varied=varied,
            fixed_torque=float(fixed_torque),
            varied_torque=float(q_level),
            cfg=cfg,
        )
        if not (d1["physical"] and d2["physical"]):
            continue

        if varied == "secondary":
            tp, ts = float(fixed_torque), float(q_level)
        else:
            tp, ts = float(q_level), float(fixed_torque)
        slope1 = derivative_of_scalar_residual(family, lam=root1, tp=tp, ts=ts)
        slope2 = derivative_of_scalar_residual(family, lam=root2, tp=tp, ts=ts)

        fold_diag = diagnose_point(
            family,
            stick_lambda=lam_fold,
            varied=varied,
            fixed_torque=float(fixed_torque),
            varied_torque=float(q_fold),
            cfg=cfg,
        )

        score = candidate_score(
            fold_excursion=abs(q_fold - q_level),
            root_sep=sep,
            d1=d1,
            d2=d2,
            slope1=slope1,
            slope2=slope2,
        )
        if score > best_score:
            best_score = score
            best = {
                "varied_torque": varied,
                "fixed_torque_Nm": float(fixed_torque),
                "two_root_varied_torque_Nm": float(q_level),
                "fold_varied_torque_Nm": float(q_fold),
                "fold_lambda": float(lam_fold),
                "fold_kind": extremum_kind,
                "fold_excursion_Nm": abs(float(q_fold - q_level)),
                "root1_lambda": float(root1),
                "root2_lambda": float(root2),
                "root_separation": float(sep),
                "root1_slope": float(slope1),
                "root2_slope": float(slope2),
                "score": float(score),
                "root1_physical": bool(d1["physical"]),
                "root2_physical": bool(d2["physical"]),
                "fold_physical": bool(fold_diag["physical"]),
                "root1_static_margin": float(d1["stick_static_margin"]),
                "root2_static_margin": float(d2["stick_static_margin"]),
                "root1_local_normal_min": float(d1["minimum_local_normal"]),
                "root2_local_normal_min": float(d2["minimum_local_normal"]),
                "root1_mechanism_margin": float(d1["mechanism_margin"]),
                "root2_mechanism_margin": float(d2["mechanism_margin"]),
                "root1_slip_direction_consistent": bool(d1["slip_direction_consistent"]),
                "root2_slip_direction_consistent": bool(d2["slip_direction_consistent"]),
                "fold_static_margin": float(fold_diag["stick_static_margin"]),
                "fold_local_normal_min": float(fold_diag["minimum_local_normal"]),
                "fold_mechanism_margin": float(fold_diag["mechanism_margin"]),
            }
    return best


def scan_one_state(row: dict[str, Any], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    global _W_DECODED, _W_LIBRARY, _W_REFERENCE_MODE
    recipe = global_search.rebuild_recipe_from_candidate(row)
    candidates: list[dict[str, Any]] = []
    fixed_values = np.linspace(
        -float(cfg["torque_limit_Nm"]),
        +float(cfg["torque_limit_Nm"]),
        int(cfg["fixed_torque_samples"]),
    )

    for branch in BRANCHES:
        try:
            family = AffineScalarFamily(
                decoded=_W_DECODED,
                library=_W_LIBRARY,
                reference_mode=_W_REFERENCE_MODE,
                recipe=recipe,
                branch=branch,
                basis_step=float(cfg["torque_basis_step_Nm"]),
            )
        except Exception:
            continue

        lambdas = np.linspace(
            float(family.static_interval.lower),
            float(family.static_interval.upper),
            int(cfg["lambda_samples"]),
        )
        try:
            r0, gp, gs = family.sample_coefficients(lambdas)
        except Exception:
            continue

        for varied in ("secondary", "primary"):
            for fixed_torque in fixed_values:
                q_curve = required_curve_from_coefficients(
                    r0=r0,
                    gp=gp,
                    gs=gs,
                    varied=varied,
                    fixed_torque=float(fixed_torque),
                    gain_epsilon=float(cfg["gain_epsilon"]),
                    q_limit=float(cfg["required_torque_limit_Nm"]),
                )
                extrema = local_extrema_indices(q_curve)
                for idx, kind in extrema:
                    candidate = best_pair_around_extremum(
                        family,
                        lambdas=lambdas,
                        q_curve=q_curve,
                        extremum_index=idx,
                        extremum_kind=kind,
                        varied=varied,
                        fixed_torque=float(fixed_torque),
                        cfg=cfg,
                    )
                    if candidate is None:
                        continue
                    candidate.update({
                        "state_id": str(row.get("state_id", "")),
                        "shift_fraction": finite_float(row, "shift_fraction"),
                        "shift_speed_mm_s": finite_float(row, "shift_speed_mm_s"),
                        "target_primary_rpm": finite_float(row, "target_primary_rpm"),
                        "resolved_primary_rpm": finite_float(row, "resolved_primary_rpm"),
                        "resolved_secondary_rpm": finite_float(row, "resolved_secondary_rpm"),
                        "resolved_belt_speed_m_s": finite_float(row, "resolved_belt_speed_m_s"),
                        "branch": branch.short_name,
                        "branch_label": branch.branch_name,
                        "sliding_interface": branch.sliding_interface.value,
                        "sticking_interface": branch.sticking_interface.value,
                        "kinetic_sign": int(branch.kinetic_sign),
                        "kinetic_lambda": float(family.kinetic_lambda),
                        "stick_static_lower": float(family.static_interval.lower),
                        "stick_static_upper": float(family.static_interval.upper),
                    })
                    candidates.append(candidate)
    return candidates


def worker_scan(row: dict[str, Any]) -> list[dict[str, Any]]:
    assert _W_CFG is not None
    return scan_one_state(row, _W_CFG)


def branch_from_short_name(name: str) -> BranchSpec:
    for branch in BRANCHES:
        if branch.short_name == name:
            return branch
    raise KeyError(name)


def reconstruct_best_family(
    candidate: dict[str, Any],
    source_states: dict[str, dict[str, Any]],
    decoded,
    library,
    reference_mode,
    basis_step: float,
) -> AffineScalarFamily:
    state = source_states[str(candidate["state_id"])]
    recipe = global_search.rebuild_recipe_from_candidate(state)
    branch = branch_from_short_name(str(candidate["branch"]))
    return AffineScalarFamily(
        decoded=decoded,
        library=library,
        reference_mode=reference_mode,
        recipe=recipe,
        branch=branch,
        basis_step=basis_step,
    )


def exact_curve(
    family: AffineScalarFamily,
    candidate: dict[str, Any],
    points: int = 801,
) -> tuple[np.ndarray, np.ndarray]:
    lambdas = np.linspace(
        float(family.static_interval.lower),
        float(family.static_interval.upper),
        int(points),
    )
    varied = str(candidate["varied_torque"])
    fixed = float(candidate["fixed_torque_Nm"])
    q = np.asarray([
        family.required_varied_torque(
            stick_lambda=float(lam),
            varied=varied,
            fixed_torque=fixed,
        )
        for lam in lambdas
    ], dtype=float)
    q[np.abs(q) > 2.0 * max(
        1.0,
        abs(float(candidate["fold_varied_torque_Nm"])),
        abs(float(candidate["two_root_varied_torque_Nm"])),
    ) + 500.0] = np.nan
    return lambdas, q


def save_gif(frame_paths: list[Path], output: Path, fps: int) -> None:
    images = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in frame_paths]
    if not images:
        return
    images[0].save(
        output,
        save_all=True,
        append_images=images[1:],
        duration=int(round(1000 / max(1, fps))),
        loop=0,
        optimize=False,
        disposal=2,
    )


def render_best(
    *,
    out: Path,
    candidate: dict[str, Any],
    family: AffineScalarFamily,
    cfg: dict[str, Any],
) -> None:
    best_dir = out / "best"
    frames = best_dir / "frames"
    frames.mkdir(parents=True, exist_ok=True)

    varied = str(candidate["varied_torque"])
    fixed = float(candidate["fixed_torque_Nm"])
    q_two = float(candidate["two_root_varied_torque_Nm"])
    q_fold = float(candidate["fold_varied_torque_Nm"])
    lam_fold = float(candidate["fold_lambda"])
    root1 = float(candidate["root1_lambda"])
    root2 = float(candidate["root2_lambda"])
    q_name = "T_s" if varied == "secondary" else "T_p"
    fixed_name = "T_p" if varied == "secondary" else "T_s"
    lam_name = (
        r"$\lambda_s$"
        if family.branch.sticking_interface is ContactInterface.SECONDARY
        else r"$\lambda_p$"
    )

    lambdas, q_curve = exact_curve(family, candidate, points=801)

    # curve CSV
    curve_rows = [
        {
            "stick_lambda": float(lam),
            "required_varied_torque_Nm": float(q) if np.isfinite(q) else "",
        }
        for lam, q in zip(lambdas, q_curve)
    ]
    write_rows(best_dir / "curve.csv", curve_rows)

    # Required-torque fold plot.
    fig, ax = plt.subplots(figsize=(8.3, 5.8), constrained_layout=True)
    ax.plot(lambdas, q_curve, linewidth=2.5)
    ax.axhline(q_two, linestyle="--", linewidth=2.0, label=f"two-root {q_name}")
    ax.axhline(q_fold, linestyle=":", linewidth=1.8, label=f"fold {q_name}")
    ax.scatter([root1, root2], [q_two, q_two], s=80, zorder=5)
    ax.scatter([lam_fold], [q_fold], marker="^", s=100, zorder=6)
    ax.set_xlabel(lam_name)
    ax.set_ylabel(f"required {q_name} [Nm]")
    ax.set_title(
        f"True 1D mixed branch: {candidate['branch_label']}\n"
        f"fixed {fixed_name} = {fixed:.3f} Nm"
    )
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.savefig(best_dir / "required_torque_fold.png", dpi=int(cfg["render_dpi"]))
    plt.close(fig)

    # Scalar residual at the two-root torque.
    if varied == "secondary":
        tp_two, ts_two = fixed, q_two
    else:
        tp_two, ts_two = q_two, fixed
    residual = np.asarray([
        family.residual_at(
            stick_lambda=float(lam),
            primary_torque=tp_two,
            secondary_torque=ts_two,
        )
        for lam in lambdas
    ])
    fig, ax = plt.subplots(figsize=(8.3, 5.4), constrained_layout=True)
    ax.plot(lambdas, residual, linewidth=2.4)
    ax.axhline(0.0, linestyle="--", linewidth=1.8)
    ax.scatter([root1, root2], [0.0, 0.0], s=80, zorder=5)
    ax.set_xlabel(lam_name)
    ax.set_ylabel("sticking acceleration residual [m/s$^2$]")
    ax.set_title("The actual 1D closure residual crosses zero twice")
    ax.grid(True, alpha=0.25)
    fig.savefig(best_dir / "scalar_residual_two_roots.png", dpi=int(cfg["render_dpi"]))
    plt.close(fig)

    # Physical diagnostics sampled along the inverse branch.
    physics_rows: list[dict[str, Any]] = []
    sample_lams = np.linspace(
        max(family.static_interval.lower, min(root1, root2) - 0.20),
        min(family.static_interval.upper, max(root1, root2) + 0.20),
        101,
    )
    for lam in sample_lams:
        q = family.required_varied_torque(
            stick_lambda=float(lam),
            varied=varied,
            fixed_torque=fixed,
        )
        if not math.isfinite(q) or abs(q) > float(cfg["required_torque_limit_Nm"]):
            continue
        d = diagnose_point(
            family,
            stick_lambda=float(lam),
            varied=varied,
            fixed_torque=fixed,
            varied_torque=float(q),
            cfg=cfg,
        )
        physics_rows.append({
            "stick_lambda": float(lam),
            "required_varied_torque_Nm": float(q),
            **d,
        })
    write_rows(best_dir / "branch_physics.csv", physics_rows)

    if physics_rows:
        x = np.asarray([float(r["stick_lambda"]) for r in physics_rows])
        fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.0), constrained_layout=True)
        fields = (
            ("stick_static_margin", "sticking static margin"),
            ("minimum_local_normal", "minimum local wrap normal"),
            ("mechanism_margin", "mechanism margin"),
            ("A_condition_scaled", "scaled cond(A)"),
        )
        for ax, (key, label) in zip(axes.ravel(), fields):
            y = np.asarray([float(r.get(key, np.nan)) for r in physics_rows])
            ax.plot(x, y, linewidth=1.8)
            if key != "A_condition_scaled":
                ax.axhline(0.0, linestyle="--", linewidth=1.0)
            ax.axvline(root1, linestyle=":", linewidth=1.0)
            ax.axvline(root2, linestyle=":", linewidth=1.0)
            ax.set_xlabel(lam_name)
            ax.set_ylabel(label)
            ax.grid(True, alpha=0.25)
        fig.suptitle("Physical margins along the one-contact solution branch")
        fig.savefig(best_dir / "branch_physics.png", dpi=int(cfg["render_dpi"]))
        plt.close(fig)

    # Animated fold birth: required torque curve + actual residual.
    exc = abs(q_fold - q_two)
    pad = max(0.5, 0.30 * max(exc, 1.0))
    if str(candidate["fold_kind"]) == "max":
        levels = np.linspace(q_fold + pad, q_two - pad, int(cfg["gif_frames"]))
    else:
        levels = np.linspace(q_fold - pad, q_two + pad, int(cfg["gif_frames"]))

    frame_paths: list[Path] = []
    for k, q_level in enumerate(levels):
        if varied == "secondary":
            tp, ts = fixed, float(q_level)
        else:
            tp, ts = float(q_level), fixed
        rr = np.asarray([
            family.residual_at(
                stick_lambda=float(lam),
                primary_torque=tp,
                secondary_torque=ts,
            )
            for lam in lambdas
        ])
        brackets = crossing_brackets(lambdas, q_curve, float(q_level))
        hits: list[float] = []
        for br in brackets:
            hit = refine_root_on_required_curve(
                family,
                varied=varied,
                fixed_torque=fixed,
                q_level=float(q_level),
                bracket=br,
            )
            if hit is not None and (not hits or min(abs(hit-h) for h in hits) > 1e-5):
                hits.append(hit)

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.0, 5.1), constrained_layout=True)
        ax1.plot(lambdas, q_curve, linewidth=2.4)
        ax1.axhline(q_level, linestyle="--", linewidth=2.0)
        ax1.scatter([lam_fold], [q_fold], marker="^", s=90, zorder=6)
        if hits:
            ax1.scatter(hits, [q_level] * len(hits), s=70, zorder=7)
        ax1.set_xlabel(lam_name)
        ax1.set_ylabel(f"required {q_name} [Nm]")
        ax1.set_title(f"Inverse 1D branch: {len(hits)} root(s)")
        ax1.grid(True, alpha=0.25)

        ax2.plot(lambdas, rr, linewidth=2.4)
        ax2.axhline(0.0, linestyle="--", linewidth=1.7)
        if hits:
            ax2.scatter(hits, [0.0] * len(hits), s=70, zorder=7)
        ax2.set_xlabel(lam_name)
        ax2.set_ylabel("sticking residual [m/s$^2$]")
        ax2.set_title("Actual scalar closure residual")
        ax2.grid(True, alpha=0.25)

        fig.suptitle(
            f"{candidate['branch_label']} | fixed {fixed_name}={fixed:.2f} Nm | "
            f"{q_name}={q_level:.2f} Nm | fold={q_fold:.2f} Nm"
        )
        path = frames / f"frame_{k:03d}.png"
        fig.savefig(path, dpi=int(cfg["render_dpi"]))
        plt.close(fig)
        frame_paths.append(path)

    save_gif(frame_paths, best_dir / "one_contact_fold_birth.gif", int(cfg["gif_fps"]))

    # Standalone interactive HTML via Plotly CDN.
    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<script src='https://cdn.plot.ly/plotly-2.35.2.min.js'></script>
<title>One-contact fold</title></head><body>
<div id='plot' style='width:100%;height:94vh;'></div>
<script>
const x = {lambdas.tolist()};
const q = {np.where(np.isfinite(q_curve), q_curve, None).tolist()};
const data = [
  {{type:'scatter', mode:'lines', x:x, y:q, line:{{width:4}}, name:'required {q_name}'}},
  {{type:'scatter', mode:'markers+text', x:[{root1},{root2}], y:[{q_two},{q_two}],
    text:['root 1','root 2'], textposition:'top center', marker:{{size:10}}, name:'two roots'}},
  {{type:'scatter', mode:'markers+text', x:[{lam_fold}], y:[{q_fold}],
    text:['double-root fold'], textposition:'top center', marker:{{size:11,symbol:'triangle-up'}}, name:'fold'}},
  {{type:'scatter', mode:'lines', x:[{float(lambdas[0])},{float(lambdas[-1])}], y:[{q_two},{q_two}],
    line:{{dash:'dash'}}, name:'two-root torque'}}
];
Plotly.newPlot('plot', data, {{
  title:'True one-contact mixed closure: {candidate["branch_label"]}',
  xaxis:{{title:'sticking lambda'}},
  yaxis:{{title:'required {q_name} [Nm]'}}
}}, {{responsive:true}});
</script></body></html>"""
    (best_dir / "one_contact_fold_interactive.html").write_text(html, encoding="utf-8")

    (best_dir / "best_candidate.json").write_text(
        json.dumps(candidate, indent=2), encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    cc_run.verify_environment()

    search_dir = args.global_search_dir.resolve()
    out = args.output_dir.resolve() if args.output_dir else DEFAULT_OUTPUT
    out.mkdir(parents=True, exist_ok=True)

    states = collect_unique_states(search_dir, int(args.max_states))
    if not states:
        raise SystemExit(
            "No usable frozen states found. Expected all_two_root_candidates_precomfort.csv "
            "or comfort_audit_results.csv with resolved state columns."
        )
    write_rows(out / "states_scanned.csv", states)

    cfg = {
        "lambda_samples": int(args.lambda_samples),
        "fixed_torque_samples": int(args.fixed_torque_samples),
        "torque_limit_Nm": float(args.torque_limit_Nm),
        "torque_basis_step_Nm": float(args.torque_basis_step_Nm),
        "required_torque_limit_Nm": float(args.required_torque_limit_Nm),
        "gain_epsilon": float(args.gain_epsilon),
        "minimum_root_separation": float(args.minimum_root_separation),
        "minimum_static_margin": float(args.minimum_static_margin),
        "minimum_local_normal": float(args.minimum_local_normal),
        "minimum_mechanism_margin": float(args.minimum_mechanism_margin),
        "minimum_normal_N": float(args.minimum_normal_N),
        "levels_per_fold": int(args.levels_per_fold),
        "gif_frames": int(args.gif_frames),
        "gif_fps": int(args.gif_fps),
        "render_dpi": int(args.render_dpi),
    }

    workers = int(args.workers)
    if workers < 0:
        workers = max(1, os.cpu_count() or 1)

    print("=" * 96)
    print("TRUE ONE-CONTACT MULTIROOT / FOLD SEARCH")
    print(f"Frozen states: {len(states)}")
    print(f"Mixed branch policies per state: {len(BRANCHES)}")
    print("Each branch checks both choices of varied shaft torque.")
    print(f"Workers: {workers}")
    print()

    all_candidates: list[dict[str, Any]] = []
    reference_path = str(args.reference_path_csv.resolve())

    if workers <= 1:
        _worker_init(reference_path, int(args.reference_frame), cfg)
        for i, state in enumerate(states, start=1):
            found = worker_scan(state)
            all_candidates.extend(found)
            print(f"[{i:03d}/{len(states):03d}] {state.get('state_id')}: {len(found)} candidate fold(s)")
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_worker_init,
            initargs=(reference_path, int(args.reference_frame), cfg),
        ) as pool:
            futures = {
                pool.submit(worker_scan, state): state
                for state in states
            }
            done = 0
            for future in as_completed(futures):
                state = futures[future]
                done += 1
                try:
                    found = future.result()
                    all_candidates.extend(found)
                    print(
                        f"[{done:03d}/{len(states):03d}] {state.get('state_id')}: "
                        f"{len(found)} candidate fold(s)"
                    )
                except Exception as exc:
                    print(
                        f"[{done:03d}/{len(states):03d}] {state.get('state_id')}: "
                        f"FAILED {type(exc).__name__}: {exc}"
                    )

    all_candidates.sort(key=lambda r: float(r.get("score", -np.inf)), reverse=True)
    write_rows(out / "all_one_contact_fold_candidates.csv", all_candidates)

    if not all_candidates:
        (out / "README.txt").write_text(
            "No two-physical-root one-contact folds were found in the searched envelope.\n",
            encoding="utf-8",
        )
        print("No physically admissible two-root mixed-contact folds found.")
        return 0

    top = all_candidates[: int(args.top_candidates)]
    write_rows(out / "top_candidates.csv", top)

    best_by_branch: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in all_candidates:
        branch = str(row["branch"])
        if branch in seen:
            continue
        seen.add(branch)
        best_by_branch.append(row)
    write_rows(out / "best_by_branch.csv", best_by_branch)

    # Reconstruct best in the parent process and render high-resolution artifacts.
    decoded, library = controlled.load_base()
    reference_mode = global_search.reference_mode_from_path(
        decoded,
        library,
        args.reference_path_csv.resolve(),
        int(args.reference_frame),
    )
    source_states = {str(r["state_id"]): r for r in states}
    best = all_candidates[0]
    family = reconstruct_best_family(
        best,
        source_states,
        decoded,
        library,
        reference_mode,
        float(args.torque_basis_step_Nm),
    )
    render_best(out=out, candidate=best, family=family, cfg=cfg)

    summary = {
        "states_scanned": len(states),
        "candidate_fold_count": len(all_candidates),
        "best_candidate": best,
        "best_by_branch": best_by_branch,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "README.txt").write_text(
        "This is a true one-contact mixed-branch search.\n\n"
        "For primary-slip/secondary-stick, primary lambda is fixed at +/-mu_k and "
        "the scalar secondary sticking residual is searched for multiple roots.\n"
        "For primary-stick/secondary-slip, the roles are reversed.\n\n"
        "Best visual outputs are under ./best/.\n",
        encoding="utf-8",
    )

    print()
    print("BEST CASE")
    print(json.dumps(best, indent=2))
    print(f"Artifacts: {out / 'best'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
