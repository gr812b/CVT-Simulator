"""E5.6: race dynamic helix lift-off against belt traction saturation.

E5.5 showed that moderate forward-power torque steps barely excited the
shift-acceleration helix term.  This stage deliberately increases transient
severity while keeping the scientific question narrow:

    can the full dynamic helix lose selected-flank admissibility BEFORE
    the belt leaves stick-stick contact, while M_h,QS remains positive?

The study reconditions each torsional preload from launch, restarts from
naturally reached interior ratios, and sweeps disturbance magnitude and ramp
rate.  It records both event clocks -- first full-M_h zero crossing and first
belt departure from stick-stick -- so the output directly reports whether the
helix or traction boundary is reached first.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import math
from math import radians
from pathlib import Path
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY_ROOT = HERE.parent
for path in (STUDY_ROOT, HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from metrics import contact_topology_metrics, deduplicate_by_time  # noqa: E402
from study_support import (  # noqa: E402
    ARTIFACTS,
    AddedTorqueBoundary,
    BlendToTorqueBoundary,
    BlendTorqueScaleBoundary,
    SmoothStep,
    build_reference_components,
    flat_programme,
    load_tagged_modules,
    run_custom_restart_case,
    run_flat_slotted_reference_with_constants,
    select_restart,
    verify_environment,
    write_reference_provenance,
    write_rows,
)
try:
    import run_liftoff_envelope as e5  # type: ignore  # noqa: E402
    import run_dynamic_only_liftoff as e55  # type: ignore  # noqa: E402
except ModuleNotFoundError:  # package import in tests
    from experiments import run_liftoff_envelope as e5  # type: ignore  # noqa: E402
    from experiments import run_dynamic_only_liftoff as e55  # type: ignore  # noqa: E402


@dataclass(frozen=True, slots=True)
class SeverityPerturbation:
    family: str
    value: float
    label: str
    role: str


@dataclass(frozen=True, slots=True)
class SeverityCase:
    preload_deg: float
    restart_key: str
    perturbation: SeverityPerturbation
    ramp_s: float

    @property
    def case_id(self) -> str:
        preload = str(int(round(self.preload_deg))).zfill(3)
        ramp_us = str(int(round(1.0e6 * self.ramp_s))).zfill(6)
        value = f"{abs(self.perturbation.value):06.2f}".replace(".", "p")
        sign = "m" if self.perturbation.value < 0.0 else "p"
        family = self.perturbation.family.replace("_", "-")
        return f"E56_p{preload}_{self.restart_key}_{family}_{sign}{value}_r{ramp_us}us"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Small plumbing matrix; not suitable for scientific interpretation.",
    )
    return parser.parse_args()


def _finite(value: Any) -> float | None:
    return e55._finite(value)


def _minimum(rows: list[dict[str, Any]], key: str) -> float | None:
    return e55._minimum(rows, key)


def _maximum_abs(rows: list[dict[str, Any]], key: str) -> float | None:
    return e55._maximum_abs(rows, key)


def contact_is_stick_stick(mode: Any) -> bool:
    """Return whether belt contact is stick-stick, ignoring shift constraint."""

    return "stick_stick" in str(mode).lower()


def first_contact_exit(rows: list[dict[str, Any]], *, onset_s: float) -> dict[str, Any] | None:
    """Return the first sampled departure from stick-stick after forcing onset."""

    unique = [
        row for row in deduplicate_by_time(rows)
        if (_finite(row.get("time_s")) is not None and float(row["time_s"]) >= onset_s)
    ]
    if not unique:
        return None
    previous = unique[0]
    if not contact_is_stick_stick(previous.get("cvt_mode")):
        return {
            "traction_exit_time_s": float(previous["time_s"]),
            "traction_exit_mode_before": str(previous.get("cvt_mode", "")),
            "traction_exit_mode_after": str(previous.get("cvt_mode", "")),
            "traction_exit_lambda_primary_before": _finite(previous.get("lambda_primary")),
            "traction_exit_lambda_secondary_before": _finite(previous.get("lambda_secondary")),
            "traction_exit_full_margin_before_Nm": _finite(previous.get("helix_reacted_torque_margin_Nm")),
            "traction_exit_qs_margin_before_Nm": _finite(previous.get("helix_quasi_static_margin_Nm")),
            "traction_exit_preexisting_at_onset": True,
        }
    for row in unique[1:]:
        if contact_is_stick_stick(previous.get("cvt_mode")) and not contact_is_stick_stick(row.get("cvt_mode")):
            return {
                "traction_exit_time_s": float(row["time_s"]),
                "traction_exit_mode_before": str(previous.get("cvt_mode", "")),
                "traction_exit_mode_after": str(row.get("cvt_mode", "")),
                "traction_exit_lambda_primary_before": _finite(previous.get("lambda_primary")),
                "traction_exit_lambda_secondary_before": _finite(previous.get("lambda_secondary")),
                "traction_exit_full_margin_before_Nm": _finite(previous.get("helix_reacted_torque_margin_Nm")),
                "traction_exit_qs_margin_before_Nm": _finite(previous.get("helix_quasi_static_margin_Nm")),
            }
        previous = row
    return None


def event_order(
    *,
    helix_crossing: dict[str, Any] | None,
    traction_exit: dict[str, Any] | None,
    simultaneous_tolerance_s: float,
) -> tuple[str, float | None]:
    """Classify which topology/contact boundary is encountered first."""

    th = None if helix_crossing is None else _finite(helix_crossing.get("crossing_time_s"))
    tt = None if traction_exit is None else _finite(traction_exit.get("traction_exit_time_s"))
    if th is None and tt is None:
        return "neither", None
    if th is not None and tt is None:
        return "helix_first", None
    if th is None and tt is not None:
        return "traction_first", None
    assert th is not None and tt is not None
    delta = th - tt
    if abs(delta) <= simultaneous_tolerance_s:
        return "simultaneous_or_unresolved", delta
    return ("helix_first" if delta < 0.0 else "traction_first"), delta


def pretraction_rows(
    rows: list[dict[str, Any]],
    *,
    onset_s: float,
    traction_exit: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    end = None if traction_exit is None else _finite(traction_exit.get("traction_exit_time_s"))
    out = []
    for row in deduplicate_by_time(rows):
        t = _finite(row.get("time_s"))
        if t is None or t < onset_s:
            continue
        if end is not None and t >= end:
            continue
        if contact_is_stick_stick(row.get("cvt_mode")):
            out.append(row)
    return out


def build_cases(cfg: dict[str, Any], *, quick: bool) -> list[SeverityCase]:
    if quick:
        preloads = [240.0, 180.0]
        restarts = [50.0]
        engine_targets = [-28.0]
        engine_ramps = [0.005, 0.05]
        output_steps = [-80.0]
        output_ramps = [0.005, 0.05]
        controls: list[SeverityPerturbation] = []
        control_ramps: list[float] = []
    else:
        preloads = [float(x) for x in cfg["core_preload_degrees"]]
        restarts = [float(x) for x in cfg["restart_shift_percents"]]
        engine_targets = [float(x) for x in cfg["engine_target_torques_Nm"]]
        engine_ramps = [float(x) for x in cfg["engine_ramp_times_s"]]
        output_steps = [float(x) for x in cfg["secondary_load_steps_Nm"]]
        output_ramps = [float(x) for x in cfg["secondary_load_ramp_times_s"]]
        controls = [
            *[
                SeverityPerturbation("throttle_raise", float(x), f"engine torque scale -> {x:g}", "sign_control")
                for x in cfg["sign_controls"]["throttle_raise_scales"]
            ],
            *[
                SeverityPerturbation("output_assist", float(x), f"secondary added torque {x:+g} N m", "sign_control")
                for x in cfg["sign_controls"]["secondary_assist_steps_Nm"]
            ],
        ]
        control_ramps = [float(x) for x in cfg["sign_controls"]["ramp_times_s"]]

    cases: list[SeverityCase] = []
    for preload in preloads:
        for restart in restarts:
            key = f"s{int(round(restart))}"
            for target in engine_targets:
                p = SeverityPerturbation(
                    "engine_target_torque",
                    target,
                    f"primary torque -> {target:+g} N m",
                    "target",
                )
                for ramp in engine_ramps:
                    cases.append(SeverityCase(preload, key, p, ramp))
            for step in output_steps:
                p = SeverityPerturbation(
                    "output_load_step",
                    step,
                    f"secondary added torque {step:+g} N m",
                    "target",
                )
                for ramp in output_ramps:
                    cases.append(SeverityCase(preload, key, p, ramp))

    if not quick:
        # Higher-preload reference controls use only the most severe target
        # disturbances at representative ramp rates.  This keeps the main
        # matrix focused on the region where dynamic-only reversal is plausible.
        ref_preloads = [float(x) for x in cfg["reference_preload_degrees"]]
        ref_ramps = [float(x) for x in cfg["reference_control_ramp_times_s"]]
        strongest_engine = min(engine_targets)
        strongest_output = min(output_steps)
        for preload in ref_preloads:
            for restart in restarts:
                key = f"s{int(round(restart))}"
                for family, value, label in (
                    ("engine_target_torque", strongest_engine, f"primary torque -> {strongest_engine:+g} N m"),
                    ("output_load_step", strongest_output, f"secondary added torque {strongest_output:+g} N m"),
                ):
                    p = SeverityPerturbation(family, value, label, "reference_control")
                    for ramp in ref_ramps:
                        cases.append(SeverityCase(preload, key, p, ramp))

        # Opposite-sign controls are intentionally sparse; their role is to
        # verify the sign logic, not map another boundary surface.
        control_preloads = [float(x) for x in cfg["sign_controls"]["preload_degrees"]]
        control_restarts = [float(x) for x in cfg["sign_controls"]["restart_shift_percents"]]
        for preload in control_preloads:
            for restart in control_restarts:
                key = f"s{int(round(restart))}"
                for p in controls:
                    for ramp in control_ramps:
                        cases.append(SeverityCase(preload, key, p, ramp))

    # Stable deterministic order for reproducible artifact diffs.
    cases.sort(key=lambda c: (c.preload_deg, c.restart_key, c.perturbation.family, c.perturbation.value, c.ramp_s))
    return cases


def evaluate_case(
    *,
    case: SeverityCase,
    restart,
    route,
    ab,
    assembly,
    engine,
    road_load,
    constants,
    cfg: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from cinder.model.boundaries.shaft import FullThrottleEngineBoundary

    onset_s = float(cfg["onset_s"])
    hold_s = float(cfg["hold_s"])
    duration_s = onset_s + case.ramp_s + hold_s
    programme = flat_programme(route, duration_s)
    primary_boundary = None
    secondary_boundary = None

    if case.perturbation.family == "engine_target_torque":
        base = FullThrottleEngineBoundary(
            engine,
            equivalent_rotational_inertia=constants.engine_rotational_inertia,
        )
        primary_boundary = BlendToTorqueBoundary(
            base,
            onset_s=onset_s,
            ramp_s=case.ramp_s,
            target_torque_Nm=case.perturbation.value,
            label="e56_engine_target",
        )
    elif case.perturbation.family == "throttle_raise":
        base = FullThrottleEngineBoundary(
            engine,
            equivalent_rotational_inertia=constants.engine_rotational_inertia,
        )
        primary_boundary = BlendTorqueScaleBoundary(
            base,
            onset_s=onset_s,
            ramp_s=case.ramp_s,
            target_scale=case.perturbation.value,
            label="e56_throttle_raise",
        )
    elif case.perturbation.family in {"output_load_step", "output_assist"}:
        base = route.TimeProgrammedLockedFinalDriveBoundary(
            road_load=road_load,
            programme=programme,
            direct_secondary_shaft_inertia=constants.gearbox_input_rotational_inertia,
        )
        signal = SmoothStep(
            onset_s=onset_s,
            ramp_s=case.ramp_s,
            target=case.perturbation.value,
        )
        secondary_boundary = AddedTorqueBoundary(
            base,
            signal,
            label=f"e56_{case.perturbation.family}",
        )
    else:  # pragma: no cover
        raise ValueError(case.perturbation.family)

    solver = cfg["solver"]
    max_step = max(
        float(solver["minimum_max_step_s"]),
        min(
            float(solver["maximum_step_cap_s"]),
            case.ramp_s / float(solver["ramp_step_divisor"]),
        ),
    )
    run, result, _ = run_custom_restart_case(
        route=route,
        ab=ab,
        restart=restart,
        assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        duration_s=duration_s,
        sample_step_s=float(solver["sample_step_s"]),
        rtol=float(solver["relative_tolerance"]),
        atol=float(solver["absolute_tolerance"]),
        max_step_s=max_step,
        primary_boundary=primary_boundary,
        secondary_boundary=secondary_boundary,
        reclassify_initial_mode=False,
        deadzone_lock_absolute_tolerance=float(
            solver.get("deadzone_lock_absolute_tolerance_m_s", 1.0e-6)
        ),
    )

    summary: dict[str, Any] = {
        "case_id": case.case_id,
        "status": "completed" if run is not None else "integration_failed",
        "preload_deg": case.preload_deg,
        "restart_key": case.restart_key,
        "restart_target_shift_percent": restart.target_shift_percent,
        "restart_actual_shift_percent": restart.actual_shift_percent,
        "perturbation_family": case.perturbation.family,
        "perturbation_value": case.perturbation.value,
        "perturbation_label": case.perturbation.label,
        "perturbation_role": case.perturbation.role,
        "ramp_s": case.ramp_s,
        "onset_s": onset_s,
        "duration_s": duration_s,
        "termination_reason": str(result.termination_reason),
    }
    if run is None:
        return summary, []

    rows = [sample.row for sample in run.samples]
    e5._augment_qs(rows)
    for row in rows:
        row.update(
            {
                "e56_case_id": case.case_id,
                "e56_preload_deg": case.preload_deg,
                "e56_restart_key": case.restart_key,
                "e56_perturbation_family": case.perturbation.family,
                "e56_perturbation_value": case.perturbation.value,
                "e56_ramp_s": case.ramp_s,
            }
        )

    post = [
        row for row in rows
        if (_finite(row.get("time_s")) is not None and float(row["time_s"]) >= onset_s)
    ]
    crossing = e55.first_full_crossing(rows, onset_s=onset_s)
    traction_exit = first_contact_exit(rows, onset_s=onset_s)
    race, delta = event_order(
        helix_crossing=crossing,
        traction_exit=traction_exit,
        simultaneous_tolerance_s=float(cfg["race"]["simultaneous_tolerance_s"]),
    )
    pretraction = pretraction_rows(rows, onset_s=onset_s, traction_exit=traction_exit)
    novelty = e5._novelty_metrics(post, start_s=onset_s, end_s=duration_s)
    topology = contact_topology_metrics(post, case_start_s=onset_s, case_end_s=duration_s)
    crossing_class = e55.classify_crossing(
        crossing,
        run=run,
        onset_s=onset_s,
        geometry_spec=run.system.cvt.model.geometry.spec,
        qs_guard_Nm=float(cfg["success_criteria"]["minimum_qs_margin_at_crossing_Nm"]),
        friction_guard=float(cfg["success_criteria"]["lambda_guard"]),
        interior_guard_percent=float(cfg["success_criteria"]["interior_shift_guard_percent"]),
    )

    summary.update(
        {
            "event_order": race,
            "helix_minus_traction_event_time_s": delta,
            "minimum_full_margin_Nm": _minimum(post, "helix_reacted_torque_margin_Nm"),
            "minimum_qs_margin_Nm": _minimum(post, "helix_quasi_static_margin_Nm"),
            "minimum_dynamic_correction_Nm": _minimum(post, "helix_dynamic_correction_Nm"),
            "minimum_shift_accel_term_Nm": _minimum(post, "helix_shift_accel_reaction_torque_Nm"),
            "minimum_shaft_accel_term_Nm": _minimum(post, "helix_shaft_accel_reaction_torque_Nm"),
            "minimum_curvature_term_Nm": _minimum(post, "helix_curvature_reaction_torque_Nm"),
            "maximum_abs_shift_acceleration_m_s2": _maximum_abs(post, "helix_shift_acceleration_m_s2"),
            "maximum_abs_lambda_primary": _maximum_abs(post, "lambda_primary"),
            "maximum_abs_lambda_secondary": _maximum_abs(post, "lambda_secondary"),
            "minimum_internal_secondary_power_W": _minimum(post, "helix_secondary_internal_power_W"),
            "pretraction_sample_count": len(pretraction),
            "pretraction_minimum_full_margin_Nm": _minimum(pretraction, "helix_reacted_torque_margin_Nm"),
            "pretraction_minimum_qs_margin_Nm": _minimum(pretraction, "helix_quasi_static_margin_Nm"),
            "pretraction_minimum_dynamic_correction_Nm": _minimum(pretraction, "helix_dynamic_correction_Nm"),
            "pretraction_minimum_shift_accel_term_Nm": _minimum(pretraction, "helix_shift_accel_reaction_torque_Nm"),
            "pretraction_minimum_shaft_accel_term_Nm": _minimum(pretraction, "helix_shaft_accel_reaction_torque_Nm"),
            "pretraction_maximum_abs_shift_acceleration_m_s2": _maximum_abs(pretraction, "helix_shift_acceleration_m_s2"),
            "pretraction_maximum_abs_lambda_primary": _maximum_abs(pretraction, "lambda_primary"),
            "pretraction_maximum_abs_lambda_secondary": _maximum_abs(pretraction, "lambda_secondary"),
            **topology,
            **novelty,
            **crossing_class,
        }
    )
    if crossing:
        summary.update(crossing)
    if traction_exit:
        summary.update(traction_exit)

    # Strongest result: helix boundary is reached first, under forward power,
    # with the torque+spring helix still admissible and the shift free/interior.
    summary["gold_helix_first_dynamic_only"] = bool(
        race == "helix_first"
        and summary.get("clean_forward_stick_dynamic_only_crossing")
        and summary.get("strict_dynamic_only_case")
    )
    return summary, rows


def candidate_score(row: dict[str, Any]) -> tuple:
    order = {
        "helix_first": 0,
        "simultaneous_or_unresolved": 1,
        "traction_first": 2,
        "neither": 3,
    }
    gold = 0 if row.get("gold_helix_first_dynamic_only") else 1
    pre_dyn = _finite(row.get("pretraction_minimum_dynamic_correction_Nm"))
    full = _finite(row.get("pretraction_minimum_full_margin_Nm"))
    return (
        gold,
        order.get(str(row.get("event_order")), 9),
        full if full is not None else 1.0e9,
        pre_dyn if pre_dyn is not None else 1.0e9,
    )


def make_plots(out: Path, rows: list[dict[str, Any]]) -> None:
    completed = [r for r in rows if r.get("status") == "completed"]
    targets = [r for r in completed if r.get("perturbation_role") == "target"]
    if not targets:
        return

    # Plot 1: how large the shift-inertia term gets while traction is still stuck.
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    for preload in sorted({float(r["preload_deg"]) for r in targets}):
        subset = [r for r in targets if float(r["preload_deg"]) == preload]
        xs = [
            max(
                _finite(r.get("pretraction_maximum_abs_lambda_primary")) or 0.0,
                _finite(r.get("pretraction_maximum_abs_lambda_secondary")) or 0.0,
            )
            for r in subset
        ]
        ys = [r.get("pretraction_minimum_shift_accel_term_Nm", np.nan) for r in subset]
        ax.scatter(xs, ys, s=20, label=f"{preload:.0f}° preload")
    ax.axhline(0.0, linewidth=1.0)
    ax.axvline(0.65, linestyle="--", linewidth=1.0, label="static friction coefficient")
    ax.set_xlabel("Largest |lambda| while belt remains stick-stick")
    ax.set_ylabel("Most negative shift-inertia helix term before slip [N m]")
    ax.set_title("Can stick-stick operation develop a large dynamic helix correction?")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "pretraction_shift_inertia_vs_lambda.png", dpi=170)
    plt.close(fig)

    # Plot 2: event-order counts by preload.
    preloads = sorted({float(r["preload_deg"]) for r in targets})
    labels = ["helix_first", "simultaneous_or_unresolved", "traction_first", "neither"]
    fig, ax = plt.subplots(figsize=(9.0, 5.5))
    x = np.arange(len(preloads))
    bottom = np.zeros(len(preloads))
    for label in labels:
        values = np.array([
            sum(1 for r in targets if float(r["preload_deg"]) == p and r.get("event_order") == label)
            for p in preloads
        ], dtype=float)
        ax.bar(x, values, bottom=bottom, label=label.replace("_", " "))
        bottom += values
    ax.set_xticks(x)
    ax.set_xticklabels([f"{p:.0f}°" for p in preloads])
    ax.set_xlabel("Secondary torsional preload")
    ax.set_ylabel("Completed target cases")
    ax.set_title("Which boundary is reached first as transient severity increases?")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "event_order_by_preload.png", dpi=170)
    plt.close(fig)

    # Plot 3: engine-drag boundary versus ramp time for each preload, using the
    # worst (lowest) pre-traction full margin across restart states/targets.
    engine = [r for r in targets if r.get("perturbation_family") == "engine_target_torque"]
    if engine:
        fig, ax = plt.subplots(figsize=(8.5, 5.5))
        for preload in sorted({float(r["preload_deg"]) for r in engine}):
            subset = [r for r in engine if float(r["preload_deg"]) == preload]
            grouped: dict[float, list[float]] = {}
            for r in subset:
                value = _finite(r.get("pretraction_minimum_full_margin_Nm"))
                if value is not None:
                    grouped.setdefault(float(r["ramp_s"]), []).append(value)
            if grouped:
                xs = sorted(grouped)
                ys = [min(grouped[x]) for x in xs]
                ax.plot([1000.0 * x for x in xs], ys, marker="o", label=f"{preload:.0f}° preload")
        ax.axhline(0.0, linewidth=1.0)
        ax.set_xscale("log")
        ax.set_xlabel("Engine torque ramp duration [ms]")
        ax.set_ylabel("Lowest full helix margin while belt is still stuck [N m]")
        ax.set_title("Forced sub-50 ms engine-torque refinement")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out / "engine_ramp_pretraction_margin.png", dpi=170)
        plt.close(fig)


def main() -> int:
    args = parse_args()
    verify_environment()
    study = json.loads((STUDY_ROOT / "study.json").read_text(encoding="utf-8"))
    cfg = study["experiments"]["transient_severity_race"]

    _, ab, route = load_tagged_modules()
    _, resolved, _, _, _ = build_reference_components(
        route, duration_s=float(cfg["conditioning_duration_s"])
    )
    base_constants = resolved.constants

    cases = build_cases(cfg, quick=bool(args.quick))
    required_preloads = sorted({case.preload_deg for case in cases})
    restart_targets = sorted({float(case.restart_key[1:]) for case in cases})

    out = ARTIFACTS / "transient-severity-race"
    out.mkdir(parents=True, exist_ok=True)

    conditioning_rows: list[dict[str, Any]] = []
    restart_rows: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    contexts: dict[float, dict[str, Any]] = {}

    for preload_deg in required_preloads:
        constants = replace(
            base_constants,
            secondary_torsional_initial_twist=radians(preload_deg),
        )
        outcome = run_flat_slotted_reference_with_constants(
            route=route,
            ab=ab,
            constants=constants,
            duration_s=float(cfg["conditioning_duration_s"]),
            sample_step_s=float(cfg["conditioning_solver"]["sample_step_s"]),
            rtol=float(cfg["conditioning_solver"]["relative_tolerance"]),
            atol=float(cfg["conditioning_solver"]["absolute_tolerance"]),
            max_step_s=float(cfg["conditioning_solver"]["max_step_s"]),
        )
        run, result, assembly, engine, road_load, topology = outcome
        csum = e55.conditioning_summary(preload_deg=preload_deg, run=run, result=result)
        conditioning_rows.append(csum)
        print(
            f"E5.6 preload {preload_deg:.0f} deg conditioning: {csum['status']}, "
            f"full={csum.get('minimum_full_margin_Nm')}, QS={csum.get('minimum_qs_margin_Nm')}"
        )
        if run is None:
            continue

        restarts = {}
        for target in restart_targets:
            try:
                restart = select_restart(
                    run,
                    target,
                    maximum_error_percent=float(cfg["restart_maximum_error_percent"]),
                )
            except RuntimeError as exc:
                restart_rows.append(
                    {
                        "preload_deg": preload_deg,
                        "target_shift_percent": target,
                        "status": "unavailable",
                        "detail": str(exc),
                    }
                )
                continue
            key = f"s{int(round(target))}"
            restarts[key] = restart
            restart_rows.append(
                {
                    "preload_deg": preload_deg,
                    "restart_key": key,
                    "target_shift_percent": target,
                    "actual_shift_percent": restart.actual_shift_percent,
                    "conditioning_time_s": restart.time_s,
                    "baseline_margin_Nm": restart.baseline_margin_Nm,
                    "status": "available",
                }
            )
        contexts[preload_deg] = {
            "constants": constants,
            "assembly": assembly,
            "engine": engine,
            "road_load": road_load,
            "restarts": restarts,
            "topology": topology,
        }

    for i, case in enumerate(cases, start=1):
        context = contexts.get(case.preload_deg)
        if context is None or case.restart_key not in context["restarts"]:
            case_rows.append(
                {
                    "case_id": case.case_id,
                    "status": "restart_unavailable",
                    "preload_deg": case.preload_deg,
                    "restart_key": case.restart_key,
                    "perturbation_family": case.perturbation.family,
                    "perturbation_value": case.perturbation.value,
                    "ramp_s": case.ramp_s,
                }
            )
            continue
        try:
            summary, rows = evaluate_case(
                case=case,
                restart=context["restarts"][case.restart_key],
                route=route,
                ab=ab,
                assembly=context["assembly"],
                engine=context["engine"],
                road_load=context["road_load"],
                constants=context["constants"],
                cfg=cfg,
            )
        except (ValueError, RuntimeError, FloatingPointError) as exc:
            summary = {
                "case_id": case.case_id,
                "status": "solver_exception",
                "preload_deg": case.preload_deg,
                "restart_key": case.restart_key,
                "perturbation_family": case.perturbation.family,
                "perturbation_value": case.perturbation.value,
                "perturbation_label": case.perturbation.label,
                "perturbation_role": case.perturbation.role,
                "ramp_s": case.ramp_s,
                "exception_type": type(exc).__name__,
                "exception_detail": str(exc),
            }
            rows = []
            print(
                f"E5.6 case {case.case_id} recorded solver_exception: "
                f"{type(exc).__name__}: {exc}"
            )
        case_rows.append(summary)
        pre_full = _finite(summary.get("pretraction_minimum_full_margin_Nm"))
        pre_shift = _finite(summary.get("pretraction_minimum_shift_accel_term_Nm"))
        if rows and (
            summary.get("event_order") != "neither"
            or (
                pre_full is not None
                and pre_full <= float(cfg["trace_retention"]["pretraction_full_margin_Nm"])
            )
            or (
                pre_shift is not None
                and pre_shift <= float(cfg["trace_retention"]["shift_accel_term_Nm"])
            )
        ):
            trace_rows.extend(rows)
        if i % 25 == 0 or i == len(cases):
            print(f"E5.6 completed {i}/{len(cases)} severity cases")

    completed = [r for r in case_rows if r.get("status") == "completed"]
    candidates = sorted(completed, key=candidate_score)
    first_events = [
        r for r in completed
        if r.get("event_order") != "neither"
    ]
    gold = [r for r in completed if r.get("gold_helix_first_dynamic_only")]

    write_rows(out / "conditioning_by_preload.csv", conditioning_rows)
    write_rows(out / "restart_states.csv", restart_rows)
    write_rows(out / "case_summary.csv", case_rows)
    write_rows(out / "first_events.csv", first_events)
    write_rows(out / "candidate_catalog.csv", candidates[: min(80, len(candidates))])
    write_rows(out / "gold_candidates.csv", gold)
    write_rows(out / "retained_trace.csv", trace_rows)

    counts = {}
    for label in ("helix_first", "simultaneous_or_unresolved", "traction_first", "neither"):
        counts[label] = sum(1 for r in completed if r.get("event_order") == label)
    summary_payload = {
        "stage": "E5.6",
        "quick": bool(args.quick),
        "planned_cases": len(cases),
        "completed_cases": len(completed),
        "failed_cases": sum(
            1
            for r in case_rows
            if r.get("status") in {"integration_failed", "solver_exception"}
        ),
        "restart_unavailable_cases": sum(1 for r in case_rows if r.get("status") == "restart_unavailable"),
        "event_order_counts": counts,
        "gold_case_count": len(gold),
        "minimum_pretraction_full_margin_Nm": _minimum(completed, "pretraction_minimum_full_margin_Nm"),
        "minimum_pretraction_dynamic_correction_Nm": _minimum(completed, "pretraction_minimum_dynamic_correction_Nm"),
        "minimum_pretraction_shift_accel_term_Nm": _minimum(completed, "pretraction_minimum_shift_accel_term_Nm"),
        "maximum_pretraction_abs_shift_acceleration_m_s2": _maximum_abs(completed, "pretraction_maximum_abs_shift_acceleration_m_s2"),
        "question": cfg["question"],
        "interpretation_guard": (
            "A gold result requires helix-first selected-flank inadmissibility under forward power "
            "while belt contact is still stick-stick and M_h,QS remains positive. If traction-first "
            "dominates the severity boundary, report that as a hardware/model result rather than "
            "forcing a dynamic-only claim."
        ),
    }
    (out / "summary.json").write_text(json.dumps(summary_payload, indent=2) + "\n", encoding="utf-8")

    make_plots(out, case_rows)
    write_reference_provenance(
        out,
        study_name="helix-topology/transient-severity-race",
        topology="bilateral_zero_clearance_slot",
    )
    print(json.dumps(summary_payload, indent=2))
    print(f"Wrote E5.6 transient-severity artifacts to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
