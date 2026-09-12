"""Temporary targeted exploration for the two unresolved invariant-coverage classes.

This script is deliberately separate from the canonical mechanical-invariants study.
It changes no model physics, no tolerances, and no PASS/REVIEW logic.  It probes the
production CINDER 1.1.2 branch solvers and initial classifier more aggressively to
answer two narrow questions:

1. Can an admissible both-slip state exist with v_rel,p < 0 and v_rel,s > 0?
2. Can an admissible primary-stick / secondary-slip state exist with v_rel,s > 0?

The exploration is useful even if it finds nothing.  Every candidate is evaluated
*twice*: once by explicitly asking the production branch evaluator to solve the
requested branch, and once through the production initial-regime classifier.  This
separates "the branch is mechanically inadmissible" from "the branch is admissible
but the classifier selected a different topology".

Run from this directory with:

    python explore_missing_coverage.py

Optional:

    python explore_missing_coverage.py --budget 16000
    python explore_missing_coverage.py --target both_slip_mp --budget 8000

Outputs are written only to artifacts/missing-coverage-exploration/.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import run as audit
from cinder.execution.hybrid.composed import ComposedCVTMode
from cinder.execution.hybrid.cvt_regime import CVTOperatingRegime
from cinder.model.cvt.contact import ContactRegime, SlipDirection

HERE = Path(__file__).resolve().parent
OUT = HERE / "artifacts" / "missing-coverage-exploration"
ATTEMPT_JSONL = OUT / "attempts.jsonl"
TARGETS = ("both_slip_mp", "secondary_slip_plus")
SEED = 20260911


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Targeted temporary exploration of unresolved contact coverage."
    )
    parser.add_argument(
        "--target",
        choices=("all",) + TARGETS,
        default="all",
        help="Explore one unresolved class or both (default: all).",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=12000,
        help="Total candidate budget across selected targets (default: 12000).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help=f"Deterministic RNG seed (default: {SEED}).",
    )
    parser.add_argument(
        "--continue-after-found",
        action="store_true",
        help="Keep exploring a target after a fully validated candidate is found.",
    )
    return parser.parse_args()


def forced_contact_regime(target: str) -> ContactRegime:
    if target == "both_slip_mp":
        return ContactRegime.both_slip(
            primary_direction=SlipDirection.PULLEY_LEADS_BELT,
            secondary_direction=SlipDirection.BELT_LEADS_PULLEY,
        )
    if target == "secondary_slip_plus":
        return ContactRegime.primary_stick_secondary_slip(
            secondary_direction=SlipDirection.BELT_LEADS_PULLEY,
        )
    raise ValueError(target)


def forced_mode(target: str) -> ComposedCVTMode:
    return ComposedCVTMode(
        cvt=CVTOperatingRegime.engaged_free(
            contact_regime=forced_contact_regime(target)
        )
    )


def classifier_matches_target(mode: Any, target: str) -> bool:
    regime = getattr(mode.cvt, "contact_regime", None)
    if regime is None:
        return False
    if target == "both_slip_mp":
        return (
            regime.mode.value == "both_slip"
            and regime.primary_slip_direction is SlipDirection.PULLEY_LEADS_BELT
            and regime.secondary_slip_direction is SlipDirection.BELT_LEADS_PULLEY
        )
    if target == "secondary_slip_plus":
        return (
            regime.mode.value == "primary_stick_secondary_slip"
            and regime.secondary_slip_direction is SlipDirection.BELT_LEADS_PULLEY
        )
    return False


def _target_vrels(target: str, p_mag: float, s_mag: float) -> tuple[float, float]:
    if target == "both_slip_mp":
        return -abs(float(p_mag)), +abs(float(s_mag))
    if target == "secondary_slip_plus":
        return 0.0, +abs(float(s_mag))
    raise ValueError(target)


def _actual_vrels(system, cvt: audit.CVTState) -> np.ndarray:
    full = audit.full_state(system, cvt)
    boundaries = audit.boundaries_at(system, time_s=0.0, state=full)
    snapshot = system.cvt.evaluator.model.snapshot_at_time(
        time=0.0,
        state=cvt,
        shaft_boundaries=boundaries,
        geometry_side="engaged",
    )
    return np.asarray(
        [
            audit.evaluate_contact_relative_speed(
                snapshot=snapshot, interface=audit.ContactInterface.PRIMARY
            ),
            audit.evaluate_contact_relative_speed(
                snapshot=snapshot, interface=audit.ContactInterface.SECONDARY
            ),
        ],
        dtype=float,
    )


def state_with_target_vrels(
    system,
    *,
    shift_fraction: float,
    belt_speed: float,
    shift_speed: float,
    primary_vrel: float,
    secondary_vrel: float,
) -> audit.CVTState:
    """Construct a state whose production representative contact speeds hit targets.

    The simple radius relation is used only as an initial guess.  A numerical 2x2
    correction then uses CINDER's own ``evaluate_contact_relative_speed`` so nonzero
    shift speed and secondary helix representative motion are handled by production
    kinematics rather than duplicated test formulas.
    """
    model = system.cvt.evaluator.model
    spec = model.geometry.spec
    shift = spec.deadzone_shift + float(shift_fraction) * (
        spec.max_shift - spec.deadzone_shift
    )
    g = model.geometry.evaluate_engaged(shift)
    omega_p = (belt_speed - primary_vrel) / g.primary.effective
    omega_s = (belt_speed - secondary_vrel) / g.secondary.effective
    cvt = audit.CVTState(omega_p, omega_s, belt_speed, shift, shift_speed)
    target = np.asarray([primary_vrel, secondary_vrel], dtype=float)

    for _ in range(3):
        current = _actual_vrels(system, cvt)
        residual = target - current
        if float(np.max(np.abs(residual))) <= 1.0e-10:
            break
        base = np.asarray(
            [cvt.primary_angular_speed, cvt.secondary_angular_speed], dtype=float
        )
        J = np.zeros((2, 2), dtype=float)
        eps = 1.0e-3
        for j in range(2):
            pert = base.copy()
            pert[j] += eps
            trial = audit.CVTState(
                pert[0], pert[1], belt_speed, shift, shift_speed
            )
            J[:, j] = (_actual_vrels(system, trial) - current) / eps
        delta = np.linalg.solve(J, residual)
        base += delta
        cvt = audit.CVTState(base[0], base[1], belt_speed, shift, shift_speed)

    return cvt


def log_uniform(rng: np.random.Generator, lo: float, hi: float) -> float:
    return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))


def structured_candidates(target: str) -> Iterable[dict[str, float | str]]:
    """Small deterministic sweep aimed at the limitations seen in the v2 audit."""
    # Existing v2 used equal slip magnitudes and belt speed >= 3 m/s in its edge
    # fallback.  This sweep explicitly breaks those assumptions first.
    shift_fractions = (0.03, 0.08, 0.15, 0.25, 0.45, 0.70, 0.90, 0.97)
    belt_speeds = (-8.0, -3.0, -1.0, -0.3, 0.3, 1.0, 3.0, 8.0)
    p_slips = (0.03, 0.1, 0.3, 1.0, 3.0, 6.0)
    s_slips = (0.03, 0.1, 0.3, 1.0, 3.0, 6.0)
    secondary_torques = (0.0, 35.0, 60.0, 100.0, 160.0)

    count = 0
    for frac in shift_fractions:
        for vb in belt_speeds:
            if target == "both_slip_mp":
                # Independent slip magnitudes are the main new degree of freedom.
                for pmag in p_slips:
                    for smag in s_slips:
                        # Cycle torque rather than taking the full Cartesian product.
                        ts = secondary_torques[count % len(secondary_torques)]
                        count += 1
                        yield {
                            "stage": "structured_independent_slip",
                            "shift_fraction": frac,
                            "belt_speed_m_s": vb,
                            "shift_speed_m_s": 0.0,
                            "primary_slip_mag_m_s": pmag,
                            "secondary_slip_mag_m_s": smag,
                            "primary_torque_Nm": 0.0,
                            "secondary_torque_Nm": ts,
                            "primary_inertia_kg_m2": 0.03,
                            "secondary_inertia_kg_m2": 0.05,
                        }
            else:
                for smag in s_slips:
                    for tp in (-100.0, -35.0, 0.0, 35.0, 100.0):
                        ts = secondary_torques[count % len(secondary_torques)]
                        count += 1
                        yield {
                            "stage": "structured_mixed_branch",
                            "shift_fraction": frac,
                            "belt_speed_m_s": vb,
                            "shift_speed_m_s": 0.0,
                            "primary_slip_mag_m_s": 0.0,
                            "secondary_slip_mag_m_s": smag,
                            "primary_torque_Nm": tp,
                            "secondary_torque_Nm": ts,
                            "primary_inertia_kg_m2": 0.03,
                            "secondary_inertia_kg_m2": 0.05,
                        }


def random_candidate(
    rng: np.random.Generator, target: str, *, extended: bool
) -> dict[str, float | str]:
    if extended:
        torque_limit = 300.0
        inertia_lo, inertia_hi = 0.001, 0.50
        shift_speed_limit = 0.20
        belt_lo, belt_hi = 0.01, 30.0
        slip_lo, slip_hi = 0.003, 15.0
        stage = "extended_random"
    else:
        torque_limit = 120.0
        inertia_lo, inertia_hi = 0.008, 0.20
        shift_speed_limit = 0.08
        belt_lo, belt_hi = 0.03, 20.0
        slip_lo, slip_hi = 0.01, 10.0
        stage = "moderate_random"

    # Include edge regions but avoid the exact low-ratio and upper-stop surfaces.
    frac = float(rng.beta(0.85, 0.85))
    frac = min(0.985, max(0.015, frac))
    belt_mag = log_uniform(rng, belt_lo, belt_hi)
    belt_speed = belt_mag if rng.random() < 0.5 else -belt_mag
    shift_speed = 0.0 if rng.random() < 0.60 else float(
        rng.uniform(-shift_speed_limit, shift_speed_limit)
    )

    if target == "both_slip_mp":
        p_mag = log_uniform(rng, slip_lo, slip_hi)
    else:
        p_mag = 0.0
    s_mag = log_uniform(rng, slip_lo, slip_hi)

    # Prior results suggest positive secondary torque moves the primary local-normal
    # margin toward zero, so sample it more often without excluding the other sign.
    if rng.random() < 0.65:
        ts = float(rng.uniform(0.0, torque_limit))
    else:
        ts = float(rng.uniform(-torque_limit, 0.0))
    tp = float(rng.uniform(-torque_limit, torque_limit))

    return {
        "stage": stage,
        "shift_fraction": frac,
        "belt_speed_m_s": belt_speed,
        "shift_speed_m_s": shift_speed,
        "primary_slip_mag_m_s": p_mag,
        "secondary_slip_mag_m_s": s_mag,
        "primary_torque_Nm": tp,
        "secondary_torque_Nm": ts,
        "primary_inertia_kg_m2": log_uniform(rng, inertia_lo, inertia_hi),
        "secondary_inertia_kg_m2": log_uniform(rng, inertia_lo, inertia_hi),
    }


def candidate_stream(
    rng: np.random.Generator, target: str, budget: int
) -> Iterable[dict[str, float | str]]:
    emitted = 0
    for item in structured_candidates(target):
        if emitted >= budget:
            return
        emitted += 1
        yield item

    moderate_limit = max(emitted, int(0.65 * budget))
    while emitted < moderate_limit:
        emitted += 1
        yield random_candidate(rng, target, extended=False)
    while emitted < budget:
        emitted += 1
        yield random_candidate(rng, target, extended=True)


def forced_row(system, state: np.ndarray, target: str) -> dict[str, Any]:
    sample = audit.AuditSample(
        target,
        0.0,
        state,
        forced_mode(target),
        "forced_initial_exact",
    )
    row, _, _ = audit.audit_sample_safe(system, sample)
    return row


def classifier_row(system, state: np.ndarray) -> tuple[Any | None, dict[str, Any]]:
    try:
        mode = system.classify_initial_mode(state)
    except Exception as exc:
        return None, {
            "classifier_error": f"{type(exc).__name__}:{exc}",
            "classifier_matches_target": False,
        }
    sample = audit.AuditSample(
        "classifier", 0.0, state, mode, "classifier_initial_exact"
    )
    row, _, _ = audit.audit_sample_safe(system, sample)
    return mode, row


def _scalar(row: dict[str, Any], key: str) -> float:
    try:
        value = float(row.get(key, float("nan")))
    except Exception:
        return float("nan")
    return value


def evaluate_candidate(
    decoded,
    guards: dict[str, Any],
    target: str,
    params: dict[str, Any],
    *,
    integration_settings,
    integration_duration_s: float,
    audit_step_s: float,
) -> dict[str, Any]:
    system = audit.make_bench_system(
        decoded,
        primary_torque=float(params["primary_torque_Nm"]),
        secondary_torque=float(params["secondary_torque_Nm"]),
        primary_inertia=float(params["primary_inertia_kg_m2"]),
        secondary_inertia=float(params["secondary_inertia_kg_m2"]),
    )
    pv, sv = _target_vrels(
        target,
        float(params["primary_slip_mag_m_s"]),
        float(params["secondary_slip_mag_m_s"]),
    )
    result: dict[str, Any] = {"target": target, **params}

    try:
        cvt = state_with_target_vrels(
            system,
            shift_fraction=float(params["shift_fraction"]),
            belt_speed=float(params["belt_speed_m_s"]),
            shift_speed=float(params["shift_speed_m_s"]),
            primary_vrel=pv,
            secondary_vrel=sv,
        )
        state = audit.full_state(system, cvt)
        actual = _actual_vrels(system, cvt)
        result.update(
            {
                "primary_speed_rad_s": cvt.primary_angular_speed,
                "secondary_speed_rad_s": cvt.secondary_angular_speed,
                "shift_position_m": cvt.shift_position,
                "target_primary_vrel_m_s": pv,
                "target_secondary_vrel_m_s": sv,
                "constructed_primary_vrel_m_s": float(actual[0]),
                "constructed_secondary_vrel_m_s": float(actual[1]),
            }
        )
    except Exception as exc:
        result.update(
            {
                "forced_pass": False,
                "classifier_matches_target": False,
                "full_dynamic_pass": False,
                "reason": f"state_construction:{type(exc).__name__}:{exc}",
            }
        )
        return result

    frow = forced_row(system, state, target)
    ffail = audit.hard_row_failures(frow, guards)
    result.update(
        {
            "forced_pass": len(ffail) == 0,
            "forced_failures": "|".join(ffail),
            "forced_inspection_error": frow.get("inspection_error", ""),
            "forced_contact_mode": frow.get("contact_mode", ""),
            "forced_primary_static_margin": _scalar(frow, "primary_static_margin"),
            "forced_secondary_static_margin": _scalar(frow, "secondary_static_margin"),
            "forced_belt_min_tension_N": _scalar(frow, "belt_min_tension_N"),
            "forced_primary_min_dnormal_dtheta_N_per_rad": _scalar(
                frow, "primary_min_dnormal_dtheta_N_per_rad"
            ),
            "forced_secondary_min_dnormal_dtheta_N_per_rad": _scalar(
                frow, "secondary_min_dnormal_dtheta_N_per_rad"
            ),
            "forced_primary_normal_N": _scalar(frow, "normal_primary_N"),
            "forced_secondary_normal_N": _scalar(frow, "normal_secondary_N"),
            "forced_mechanism_min_margin": _scalar(frow, "mechanism_min_margin"),
            "forced_closure_scaled_residual": _scalar(
                frow, "closure_max_scaled_residual"
            ),
            "forced_primary_vrel_m_s": _scalar(frow, "primary_vrel_m_s"),
            "forced_secondary_vrel_m_s": _scalar(frow, "secondary_vrel_m_s"),
            "forced_primary_arel_m_s2": _scalar(frow, "primary_arel_m_s2"),
            "forced_secondary_arel_m_s2": _scalar(frow, "secondary_arel_m_s2"),
        }
    )

    cmode, crow = classifier_row(system, state)
    if cmode is None:
        result.update(
            {
                "classifier_matches_target": False,
                "classifier_mode": "",
                "classifier_error": crow.get("classifier_error", ""),
                "classifier_failures": "",
                "full_dynamic_pass": False,
            }
        )
        return result

    cregime = cmode.cvt.contact_regime
    result.update(
        {
            "classifier_matches_target": classifier_matches_target(cmode, target),
            "classifier_mode": cregime.mode.value if cregime is not None else "",
            "classifier_primary_direction": (
                getattr(cregime.primary_slip_direction, "value", "")
                if cregime is not None
                else ""
            ),
            "classifier_secondary_direction": (
                getattr(cregime.secondary_slip_direction, "value", "")
                if cregime is not None
                else ""
            ),
            "classifier_error": crow.get("inspection_error", ""),
            "classifier_failures": "|".join(
                audit.hard_row_failures(crow, guards)
            ),
        }
    )

    if not result["forced_pass"] or not result["classifier_matches_target"]:
        result["full_dynamic_pass"] = False
        return result

    try:
        trace = system.integrate_trace(
            time_span=(0.0, integration_duration_s),
            initial_state=state,
            initial_mode=cmode,
            settings=integration_settings,
        )
    except Exception as exc:
        result.update(
            {
                "full_dynamic_pass": False,
                "dynamic_reason": f"integration:{type(exc).__name__}:{exc}",
            }
        )
        return result

    bad: list[str] = []
    sampled = 0
    for sample in audit.build_trace_samples(target, trace, audit_step_s):
        row, _, _ = audit.audit_sample_safe(system, sample)
        sampled += 1
        bad.extend(audit.hard_row_failures(row, guards))
    post = audit.post_transition_rows(target, system, trace)
    for row in post:
        if row.get("successor_exists"):
            bad.extend(audit.hard_row_failures(row, guards))
        elif row.get("inspection_error") not in (None, ""):
            # A terminal no-successor is not a successful continuation for this search.
            bad.append("terminal_no_successor")

    first_dwell = (
        float(trace.segments[0].end_time - trace.segments[0].start_time)
        if trace.segments
        else 0.0
    )
    result.update(
        {
            "dynamic_samples": sampled,
            "dynamic_transitions": len(trace.transitions),
            "requested_branch_dwell_s": first_dwell,
            "trace_completed": bool(trace.completed),
            "trace_termination_reason": trace.termination_reason,
            "dynamic_failures": "|".join(sorted(set(bad))),
            "full_dynamic_pass": bool(trace.completed and not bad and first_dwell > 1.0e-8),
        }
    )
    return result


def write_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, allow_nan=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _finite(v: Any) -> float:
    try:
        x = float(v)
    except Exception:
        return float("nan")
    return x


def best_rows(rows: list[dict[str, Any]], target: str, n: int = 40) -> list[dict[str, Any]]:
    subset = [r for r in rows if r.get("target") == target]
    if target == "both_slip_mp":
        def key(r):
            pass_rank = 1 if r.get("forced_pass") else 0
            pnormal = _finite(r.get("forced_primary_min_dnormal_dtheta_N_per_rad"))
            tension = _finite(r.get("forced_belt_min_tension_N"))
            if not math.isfinite(pnormal): pnormal = -1e99
            if not math.isfinite(tension): tension = -1e99
            return (pass_rank, pnormal, tension)
    else:
        def key(r):
            pass_rank = 1 if r.get("forced_pass") else 0
            static = _finite(r.get("forced_primary_static_margin"))
            pnormal = _finite(r.get("forced_primary_min_dnormal_dtheta_N_per_rad"))
            tension = _finite(r.get("forced_belt_min_tension_N"))
            if not math.isfinite(static): static = -1e99
            if not math.isfinite(pnormal): pnormal = -1e99
            if not math.isfinite(tension): tension = -1e99
            return (pass_rank, static, pnormal, tension)
    return sorted(subset, key=key, reverse=True)[:n]


def summarize(rows: list[dict[str, Any]], targets: list[str], elapsed_s: float) -> dict[str, Any]:
    out: dict[str, Any] = {
        "study": "temporary missing-coverage exploration",
        "elapsed_s": elapsed_s,
        "attempts": len(rows),
        "targets": {},
        "interpretation": (
            "This exploration does not change the canonical invariant-study status. "
            "A full_dynamic_pass candidate is evidence that the missing class is reachable "
            "with production mechanics/classification under the logged boundary conditions."
        ),
    }
    for target in targets:
        rr = [r for r in rows if r.get("target") == target]
        forced = [r for r in rr if r.get("forced_pass")]
        classifier = [r for r in rr if r.get("classifier_matches_target")]
        dynamic = [r for r in rr if r.get("full_dynamic_pass")]
        best = best_rows(rr, target, 1)
        out["targets"][target] = {
            "attempts": len(rr),
            "forced_branch_passes": len(forced),
            "classifier_matches": len(classifier),
            "full_dynamic_passes": len(dynamic),
            "found": bool(dynamic),
            "best_candidate": best[0] if best else None,
        }
    return out


def make_plots(rows: list[dict[str, Any]], targets: list[str]) -> None:
    for target in targets:
        rr = [r for r in rows if r.get("target") == target]
        if not rr:
            continue
        if target == "both_slip_mp":
            x = np.asarray([_finite(r.get("forced_belt_min_tension_N")) for r in rr])
            y = np.asarray([
                _finite(r.get("forced_primary_min_dnormal_dtheta_N_per_rad"))
                for r in rr
            ])
            mask = np.isfinite(x) & np.isfinite(y)
            if np.any(mask):
                fig, ax = plt.subplots(figsize=(9, 6))
                ax.scatter(x[mask], y[mask], s=8, alpha=0.35)
                ax.axvline(0.0, linewidth=1.0)
                ax.axhline(0.0, linewidth=1.0)
                ax.set_xlabel("Minimum recovered belt tension [N]")
                ax.set_ylabel("Minimum primary dN/dθ [N/rad]")
                ax.set_title("both_slip_mp forced-branch feasibility map")
                fig.tight_layout()
                fig.savefig(OUT / "01_both_slip_mp_feasibility.png", dpi=180)
                plt.close(fig)
        else:
            x = np.asarray([_finite(r.get("forced_primary_static_margin")) for r in rr])
            y = np.asarray([
                _finite(r.get("forced_primary_min_dnormal_dtheta_N_per_rad"))
                for r in rr
            ])
            mask = np.isfinite(x) & np.isfinite(y)
            if np.any(mask):
                fig, ax = plt.subplots(figsize=(9, 6))
                ax.scatter(x[mask], y[mask], s=8, alpha=0.35)
                ax.axvline(0.0, linewidth=1.0)
                ax.axhline(0.0, linewidth=1.0)
                ax.set_xlabel("Primary static traction margin")
                ax.set_ylabel("Minimum primary dN/dθ [N/rad]")
                ax.set_title("secondary_slip_plus forced mixed-branch feasibility map")
                fig.tight_layout()
                fig.savefig(OUT / "02_secondary_slip_plus_feasibility.png", dpi=180)
                plt.close(fig)

    # Classifier outcome count, useful for seeing whether the search is failing in
    # mechanics or merely relaxing to another topology.
    labels: list[str] = []
    counts: list[int] = []
    for target in targets:
        rr = [r for r in rows if r.get("target") == target]
        modes: dict[str, int] = {}
        for r in rr:
            label = str(r.get("classifier_mode") or "classifier_error")
            modes[label] = modes.get(label, 0) + 1
        for mode, count in sorted(modes.items()):
            labels.append(f"{target}\n{mode}")
            counts.append(count)
    if labels:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(np.arange(len(labels)), counts)
        ax.set_xticks(np.arange(len(labels)), labels, rotation=30, ha="right")
        ax.set_ylabel("Candidate count")
        ax.set_title("Production classifier outcomes")
        fig.tight_layout()
        fig.savefig(OUT / "03_classifier_outcomes.png", dpi=180)
        plt.close(fig)


def write_summary_md(summary: dict[str, Any]) -> None:
    lines = [
        "# Missing-coverage exploration",
        "",
        "This is a temporary diagnostic search. It does **not** alter the canonical mechanical-invariants study or its PASS/REVIEW rules.",
        "",
        f"- Attempts: {summary['attempts']}",
        f"- Elapsed time: {summary['elapsed_s']:.1f} s",
        "",
    ]
    for target, block in summary["targets"].items():
        lines += [
            f"## {target}",
            "",
            f"- Forced requested branch passed all hard invariants: {block['forced_branch_passes']}",
            f"- Production classifier selected requested branch: {block['classifier_matches']}",
            f"- Full short continuation passed: {block['full_dynamic_passes']}",
            f"- **Found canonical-quality candidate in this exploration: {'YES' if block['found'] else 'NO'}**",
            "",
        ]
        best = block.get("best_candidate")
        if best:
            lines += [
                "Best/closest candidate is recorded in `best_candidates.csv` and `summary.json`.",
                "",
            ]
    lines += [
        "## How to interpret the result",
        "",
        "A `full_dynamic_pass` means the production classifier selected the requested topology, the exact initial state passed the same hard invariant checks as the main study, and the short hybrid continuation plus exact successor audits remained healthy.",
        "",
        "A forced-branch pass without a classifier match means the branch equations themselves can be mechanically admissible at that state, but the production classifier selected a different topology. No forced-branch pass means the search did not find a state satisfying the retained topology and all hard physical inequalities.",
        "",
    ]
    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.budget < 100:
        raise ValueError("--budget must be at least 100.")

    audit.verify_environment()
    raw_spec = audit.load_json(audit.SPEC_FILE)
    case_library, _case_library_path = audit.resolve_case_library(raw_spec)
    spec = audit.hydrate_case_recipes(raw_spec, case_library)
    decoded, _base, _doc = audit.load_frozen_reference(spec)
    guards = spec["review_guards"]
    bench = spec["bench_search"]
    dyn_settings = audit.integration_settings(bench["integrator"])
    duration = float(bench["contact_case_duration_s"])
    audit_step = float(bench["audit_time_step_s"])

    targets = list(TARGETS if args.target == "all" else (args.target,))
    per_target = max(1, args.budget // len(targets))
    OUT.mkdir(parents=True, exist_ok=True)
    if ATTEMPT_JSONL.exists():
        ATTEMPT_JSONL.unlink()

    start = time.time()
    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(args.seed)

    for target_index, target in enumerate(targets):
        print(f"\n=== Exploring {target} ({per_target} candidate budget) ===")
        found = False
        for i, params in enumerate(candidate_stream(rng, target, per_target), start=1):
            row = evaluate_candidate(
                decoded,
                guards,
                target,
                params,
                integration_settings=dyn_settings,
                integration_duration_s=duration,
                audit_step_s=audit_step,
            )
            row["attempt_index"] = i
            rows.append(row)
            write_jsonl(ATTEMPT_JSONL, row)

            if i % 250 == 0:
                best = best_rows(rows, target, 1)
                hint = ""
                if best:
                    b = best[0]
                    if target == "both_slip_mp":
                        hint = (
                            f" best dN_p/dθ={_finite(b.get('forced_primary_min_dnormal_dtheta_N_per_rad')):.6g},"
                            f" T_min={_finite(b.get('forced_belt_min_tension_N')):.6g}"
                        )
                    else:
                        hint = (
                            f" best primary static margin={_finite(b.get('forced_primary_static_margin')):.6g},"
                            f" dN_p/dθ={_finite(b.get('forced_primary_min_dnormal_dtheta_N_per_rad')):.6g}"
                        )
                print(f"  {i}/{per_target}{hint}")

            if row.get("full_dynamic_pass"):
                print(f"FOUND full dynamic candidate for {target} at attempt {i}.")
                found = True
                if not args.continue_after_found:
                    break
        if not found:
            print(f"No full dynamic candidate found for {target} in this budget.")

    elapsed = time.time() - start
    audit.write_rows(OUT / "attempts.csv", rows)
    best: list[dict[str, Any]] = []
    for target in targets:
        best.extend(best_rows(rows, target, 40))
    audit.write_rows(OUT / "best_candidates.csv", best)

    summary = summarize(rows, targets, elapsed)
    audit.write_json(OUT / "summary.json", summary, allow_nan=True)
    write_summary_md(summary)
    make_plots(rows, targets)

    print(f"\nWrote exploration artifacts to: {OUT}")
    for target, block in summary["targets"].items():
        print(
            f"{target}: forced_pass={block['forced_branch_passes']}, "
            f"classifier_match={block['classifier_matches']}, "
            f"full_dynamic_pass={block['full_dynamic_passes']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
