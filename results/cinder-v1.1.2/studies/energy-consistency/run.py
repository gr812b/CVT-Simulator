"""Run the CINDER 1.1.2 release-level mechanical-energy consistency study."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import cinder
from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)
from cinder.execution.hybrid import integrate_hybrid
from cinder.model.system import CVTState

from energy_accounting import (
    cumulative_trapezoid,
    cvt_mode,
    impact_loss_from_transition,
    impact_metadata,
    kinetic_slip_dissipation_power,
    segment_times,
    stick_pair_power,
    stored_energy,
    write_csv,
)


STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
VERIFY_ENVIRONMENT = RELEASE_ROOT / "verify_environment.py"
STUDY_FILE = STUDY_ROOT / "study.json"
ARTIFACTS = STUDY_ROOT / "artifacts"

EXPECTED_CINDER_VERSION = "1.1.2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Do not clear existing generated artifacts before running.",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Generate CSV/JSON/Markdown artifacts but skip PNG figures.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help=(
            "Smoke mode: use only the two coarsest audit grids and skip the "
            "tight ODE solve. The canonical published study is the default."
        ),
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mode_string(mode) -> str:
    return str(cvt_mode(mode))


def load_study() -> tuple[dict, dict, Path]:
    spec = json.loads(STUDY_FILE.read_text(encoding="utf-8"))
    base_path = (STUDY_ROOT / spec["base_document"]).resolve()
    document = json.loads(base_path.read_text(encoding="utf-8"))
    return spec, document, base_path


def resolved_document(
    base: dict,
    *,
    time_span_s: list[float],
    integrator: dict,
) -> dict:
    document = copy.deepcopy(base)
    document["scenario"]["time_span_s"] = list(time_span_s)
    target = document["execution"]["integrator"]
    target.update(
        {
            "relative_tolerance": float(integrator["relative_tolerance"]),
            "absolute_tolerance": float(integrator["absolute_tolerance"]),
            "method": str(integrator["method"]),
            "max_step": float(integrator["max_step_s"]),
            "maximum_transitions": int(integrator["maximum_transitions"]),
            "retain_dense_output": bool(integrator["retain_dense_output"]),
        }
    )
    return document


def validate_and_decode(document: dict):
    report = validate_simulation_case_document(document)
    if not report.is_valid:
        messages = [
            f"{finding.severity}: {finding.document_path or '/'}: {finding.message}"
            for finding in report.findings
        ]
        raise RuntimeError(
            "Resolved energy-study input failed CINDER validation:\n"
            + "\n".join(messages)
        )
    return decode_simulation_case_document(document)


def run_decoded(decoded):
    result = integrate_hybrid(
        system=decoded.system,
        time_span=decoded.time_span,
        initial_state=decoded.initial_state,
        initial_mode=decoded.initial_mode,
        settings=decoded.integrator_settings,
    )
    if not result.completed:
        raise RuntimeError(f"Hybrid integration did not complete: {result.termination_reason}")
    return result


def sampled_segment_quantities(system, segment, step: float):
    """Sample powers, stored energy, and stick drift on one continuous segment."""

    times = segment_times(segment.start_time, segment.end_time, step=step)
    if not segment.has_dense_output:
        raise RuntimeError("Energy study requires retained dense output.")
    states = segment.dense_state_at(times)

    primary_power = np.zeros(times.size, dtype=float)
    secondary_power = np.zeros(times.size, dtype=float)
    primary_slip = np.zeros(times.size, dtype=float)
    secondary_slip = np.zeros(times.size, dtype=float)
    p_stick_power = np.zeros(times.size, dtype=float)
    s_stick_power = np.zeros(times.size, dtype=float)

    kinetic = np.zeros(times.size, dtype=float)
    primary_axial = np.zeros(times.size, dtype=float)
    secondary_axial = np.zeros(times.size, dtype=float)
    primary_torsional = np.zeros(times.size, dtype=float)
    secondary_torsional = np.zeros(times.size, dtype=float)

    max_primary_stick_vrel = 0.0
    max_secondary_stick_vrel = 0.0

    for index, (time_s, full_state) in enumerate(zip(times, states.T, strict=True)):
        time_s = float(time_s)
        boundaries = system._shaft_boundaries(time=time_s, state=full_state)
        cvt_state = CVTState.from_vector(system.layout.view(full_state, "cvt"))

        primary_power[index] = (
            boundaries.primary.external_torque * cvt_state.primary_angular_speed
        )
        secondary_power[index] = (
            boundaries.secondary.external_torque * cvt_state.secondary_angular_speed
        )

        slip = kinetic_slip_dissipation_power(
            system=system,
            time=time_s,
            full_state=full_state,
            mode=segment.mode,
            boundaries=boundaries,
        )
        primary_slip[index] = slip.primary_W
        secondary_slip[index] = slip.secondary_W

        p_pair, s_pair, p_vrel, s_vrel = stick_pair_power(
            system=system,
            time=time_s,
            full_state=full_state,
            mode=segment.mode,
            boundaries=boundaries,
        )
        p_stick_power[index] = p_pair
        s_stick_power[index] = s_pair
        max_primary_stick_vrel = max(max_primary_stick_vrel, p_vrel)
        max_secondary_stick_vrel = max(max_secondary_stick_vrel, s_vrel)

        energy = stored_energy(
            system=system,
            time=time_s,
            full_state=full_state,
            mode=segment.mode,
            boundaries=boundaries,
        )
        kinetic[index] = energy.kinetic_J
        primary_axial[index] = energy.primary_axial_spring_J
        secondary_axial[index] = energy.secondary_axial_spring_J
        primary_torsional[index] = energy.primary_torsional_spring_J
        secondary_torsional[index] = energy.secondary_torsional_spring_J

    return {
        "time": times,
        "state": states,
        "primary_power": primary_power,
        "secondary_power": secondary_power,
        "external_power": primary_power + secondary_power,
        "primary_slip_power": primary_slip,
        "secondary_slip_power": secondary_slip,
        "slip_power": primary_slip + secondary_slip,
        "primary_stick_pair_power": p_stick_power,
        "secondary_stick_pair_power": s_stick_power,
        "stick_pair_power": p_stick_power + s_stick_power,
        "kinetic_energy": kinetic,
        "primary_axial_spring_energy": primary_axial,
        "secondary_axial_spring_energy": secondary_axial,
        "primary_torsional_spring_energy": primary_torsional,
        "secondary_torsional_spring_energy": secondary_torsional,
        "potential_energy": primary_axial
        + secondary_axial
        + primary_torsional
        + secondary_torsional,
        "stored_energy": kinetic
        + primary_axial
        + secondary_axial
        + primary_torsional
        + secondary_torsional,
        "max_primary_stick_vrel_m_s": max_primary_stick_vrel,
        "max_secondary_stick_vrel_m_s": max_secondary_stick_vrel,
    }


def continuous_segment_balance(system, result, audit_steps: tuple[float, ...]):
    """Evaluate W_ext - Delta E_stored - E_slip on each continuous segment."""

    rows: list[dict] = []
    for segment_index, segment in enumerate(result.segments):
        start_state = np.asarray(segment.state[:, 0], dtype=float)
        end_state = np.asarray(segment.state[:, -1], dtype=float)
        start_boundaries = system._shaft_boundaries(
            time=segment.start_time, state=start_state
        )
        end_boundaries = system._shaft_boundaries(
            time=segment.end_time, state=end_state
        )
        start_energy = stored_energy(
            system=system,
            time=segment.start_time,
            full_state=start_state,
            mode=segment.mode,
            boundaries=start_boundaries,
        )
        end_energy = stored_energy(
            system=system,
            time=segment.end_time,
            full_state=end_state,
            mode=segment.mode,
            boundaries=end_boundaries,
        )
        stored_delta = end_energy.total_J - start_energy.total_J

        row = {
            "segment_index": segment_index,
            "mode": mode_string(segment.mode),
            "start_time_s": float(segment.start_time),
            "end_time_s": float(segment.end_time),
            "duration_s": float(segment.end_time - segment.start_time),
            "stored_energy_start_J": start_energy.total_J,
            "stored_energy_end_J": end_energy.total_J,
            "stored_energy_delta_J": stored_delta,
        }

        for step in audit_steps:
            sampled = sampled_segment_quantities(system, segment, step)
            times = sampled["time"]
            external = float(cumulative_trapezoid(sampled["external_power"], times)[-1])
            primary_slip = float(
                cumulative_trapezoid(sampled["primary_slip_power"], times)[-1]
            )
            secondary_slip = float(
                cumulative_trapezoid(sampled["secondary_slip_power"], times)[-1]
            )
            slip = primary_slip + secondary_slip
            stick_pair = float(
                cumulative_trapezoid(sampled["stick_pair_power"], times)[-1]
            )
            tag = step_tag(step)
            row[f"external_work_h_{tag}_J"] = external
            row[f"primary_slip_h_{tag}_J"] = primary_slip
            row[f"secondary_slip_h_{tag}_J"] = secondary_slip
            row[f"slip_dissipation_h_{tag}_J"] = slip
            row[f"raw_defect_h_{tag}_J"] = external - stored_delta - slip
            row[f"stick_pair_work_h_{tag}_J"] = stick_pair
            row[f"max_primary_stick_vrel_h_{tag}_m_s"] = sampled[
                "max_primary_stick_vrel_m_s"
            ]
            row[f"max_secondary_stick_vrel_h_{tag}_m_s"] = sampled[
                "max_secondary_stick_vrel_m_s"
            ]
        rows.append(row)

    return rows


def event_balance(system, result):
    """Compare exact pre/post stored-energy jump with recorded impact loss."""

    rows: list[dict] = []
    for index, record in enumerate(result.transitions):
        meta = impact_metadata(record)
        if meta is None:
            continue

        pre_segment = result.segments[index]
        pre_state = np.asarray(pre_segment.state[:, -1], dtype=float)
        post_state = np.asarray(record.post_transition_state, dtype=float)
        pre_boundaries = system._shaft_boundaries(time=record.time, state=pre_state)
        post_boundaries = system._shaft_boundaries(time=record.time, state=post_state)

        pre = stored_energy(
            system=system,
            time=record.time,
            full_state=pre_state,
            mode=record.previous_mode,
            boundaries=pre_boundaries,
        )
        post = stored_energy(
            system=system,
            time=record.time,
            full_state=post_state,
            mode=record.transition.next_mode,
            boundaries=post_boundaries,
        )
        exact_drop = pre.total_J - post.total_J
        recorded_loss = float(meta["impact_dissipated_energy_J"])
        rows.append(
            {
                "transition_index": index,
                "time_s": float(record.time),
                "reason": str(record.transition.reason),
                "previous_mode": mode_string(record.previous_mode),
                "next_mode": mode_string(record.transition.next_mode),
                "pre_stored_energy_J": pre.total_J,
                "post_stored_energy_J": post.total_J,
                "exact_stored_energy_drop_J": exact_drop,
                "recorded_impact_loss_J": recorded_loss,
                "event_energy_defect_J": exact_drop - recorded_loss,
                "momentum_residual": float(meta["impact_momentum_residual"]),
                "constraint_residual": float(meta["impact_constraint_residual"]),
            }
        )
    return rows


def cumulative_energy_trace(system, result, initial_state, initial_mode, step: float):
    """Build the reader-facing cumulative energy balance on one dense grid."""

    initial = stored_energy(
        system=system,
        time=0.0,
        full_state=initial_state,
        mode=initial_mode,
    )
    transitions = sorted(result.transitions, key=lambda record: record.time)
    impact_times = np.asarray([record.time for record in transitions], dtype=float)
    impact_losses = np.asarray(
        [impact_loss_from_transition(record) for record in transitions], dtype=float
    )
    cumulative_impact = np.cumsum(impact_losses) if impact_losses.size else impact_losses

    rows: list[dict] = []
    cumulative_primary_work = 0.0
    cumulative_secondary_work = 0.0
    cumulative_primary_slip = 0.0
    cumulative_secondary_slip = 0.0

    for segment in result.segments:
        sampled = sampled_segment_quantities(system, segment, step)
        times = sampled["time"]

        primary_work_increment = cumulative_trapezoid(
            sampled["primary_power"], times
        )
        secondary_work_increment = cumulative_trapezoid(
            sampled["secondary_power"], times
        )
        primary_slip_increment = cumulative_trapezoid(
            sampled["primary_slip_power"], times
        )
        secondary_slip_increment = cumulative_trapezoid(
            sampled["secondary_slip_power"], times
        )

        for i, time_s in enumerate(times):
            time_s = float(time_s)
            if impact_times.size:
                j = np.searchsorted(
                    impact_times, time_s + 1.0e-12, side="right"
                ) - 1
                impact = float(cumulative_impact[j]) if j >= 0 else 0.0
            else:
                impact = 0.0

            primary_work = cumulative_primary_work + float(primary_work_increment[i])
            secondary_work = cumulative_secondary_work + float(secondary_work_increment[i])
            external_work = primary_work + secondary_work

            primary_slip = cumulative_primary_slip + float(primary_slip_increment[i])
            secondary_slip = cumulative_secondary_slip + float(
                secondary_slip_increment[i]
            )
            slip = primary_slip + secondary_slip

            kinetic_change = float(sampled["kinetic_energy"][i] - initial.kinetic_J)
            potential_change = float(
                sampled["potential_energy"][i] - initial.potential_J
            )
            stored_change = kinetic_change + potential_change
            residual = external_work - stored_change - slip - impact

            cvt_state = CVTState.from_vector(
                system.layout.view(sampled["state"][:, i], "cvt")
            )
            rows.append(
                {
                    "time_s": time_s,
                    "mode": mode_string(segment.mode),
                    "shift_position_m": float(cvt_state.shift_position),
                    "shift_speed_m_per_s": float(cvt_state.shift_speed),
                    "primary_boundary_work_J": primary_work,
                    "secondary_boundary_work_J": secondary_work,
                    "external_work_J": external_work,
                    "kinetic_energy_change_J": kinetic_change,
                    "potential_energy_change_J": potential_change,
                    "stored_energy_change_J": stored_change,
                    "primary_slip_dissipation_J": primary_slip,
                    "secondary_slip_dissipation_J": secondary_slip,
                    "slip_dissipation_J": slip,
                    "impact_capture_dissipation_J": impact,
                    "accounted_energy_J": stored_change + slip + impact,
                    "balance_residual_J": residual,
                }
            )

        cumulative_primary_work += float(primary_work_increment[-1])
        cumulative_secondary_work += float(secondary_work_increment[-1])
        cumulative_primary_slip += float(primary_slip_increment[-1])
        cumulative_secondary_slip += float(secondary_slip_increment[-1])

    # At a transition timestamp keep the successor-segment row so that the mode
    # label and cumulative impact accounting are post-transition.
    deduplicated: dict[float, dict] = {}
    for row in rows:
        deduplicated[round(float(row["time_s"]), 12)] = row
    return [deduplicated[key] for key in sorted(deduplicated)]


def step_tag(step: float) -> str:
    return f"{step:.9g}".replace(".", "p")


def quadrature_summary(segment_rows: list[dict], steps: tuple[float, ...]):
    rows = []
    for step in steps:
        key = f"raw_defect_h_{step_tag(step)}_J"
        total = float(sum(float(row[key]) for row in segment_rows))
        rows.append(
            {
                "audit_step_s": step,
                "sum_continuous_raw_defect_J": total,
            }
        )

    if len(rows) >= 2:
        coarse = rows[-2]
        fine = rows[-1]
        h_coarse = float(coarse["audit_step_s"])
        h_fine = float(fine["audit_step_s"])
        ratio = h_coarse / h_fine
        if ratio > 1.0:
            p = 2.0
            richardson = (
                ratio**p * float(fine["sum_continuous_raw_defect_J"])
                - float(coarse["sum_continuous_raw_defect_J"])
            ) / (ratio**p - 1.0)
        else:
            richardson = float(fine["sum_continuous_raw_defect_J"])
    else:
        richardson = float(rows[-1]["sum_continuous_raw_defect_J"])

    for row in rows:
        row["richardson_zero_step_estimate_J"] = richardson
    return rows, richardson


def stick_diagnostic_summary(segment_rows: list[dict], finest_step: float) -> dict:
    tag = step_tag(finest_step)
    work_key = f"stick_pair_work_h_{tag}_J"
    p_key = f"max_primary_stick_vrel_h_{tag}_m_s"
    s_key = f"max_secondary_stick_vrel_h_{tag}_m_s"
    return {
        "signed_stick_pair_work_J": float(sum(float(row[work_key]) for row in segment_rows)),
        "max_abs_primary_stick_relative_speed_m_s": float(
            max((float(row[p_key]) for row in segment_rows), default=0.0)
        ),
        "max_abs_secondary_stick_relative_speed_m_s": float(
            max((float(row[s_key]) for row in segment_rows), default=0.0)
        ),
    }


def solver_refinement(system, nominal, tight) -> dict:
    nominal_cvt = CVTState.from_vector(system.layout.view(nominal.final_state, "cvt"))
    tight_cvt = CVTState.from_vector(system.layout.view(tight.final_state, "cvt"))
    labels = (
        "omega_p_rad_s",
        "omega_s_rad_s",
        "belt_speed_m_s",
        "shift_position_m",
        "shift_speed_m_s",
    )
    a = np.asarray(nominal_cvt.as_vector(), dtype=float)
    b = np.asarray(tight_cvt.as_vector(), dtype=float)
    delta = b - a
    scales = np.maximum(
        np.maximum(np.abs(a), np.abs(b)),
        np.asarray([1.0, 1.0, 1.0, 1.0e-3, 1.0e-3]),
    )
    normalized = np.abs(delta) / scales
    return {
        "nominal_transition_count": len(nominal.transitions),
        "tight_transition_count": len(tight.transitions),
        "max_normalized_final_state_delta": float(np.max(normalized)),
        "final_state_deltas": {
            label: float(value)
            for label, value in zip(labels, delta, strict=True)
        },
    }


def event_summary(rows: list[dict]) -> dict:
    return {
        "impact_projection_count": len(rows),
        "total_recorded_impact_loss_J": float(
            sum(float(row["recorded_impact_loss_J"]) for row in rows)
        ),
        "min_recorded_impact_loss_J": float(
            min((float(row["recorded_impact_loss_J"]) for row in rows), default=0.0)
        ),
        "max_abs_event_energy_defect_J": float(
            max((abs(float(row["event_energy_defect_J"])) for row in rows), default=0.0)
        ),
        "max_abs_momentum_residual": float(
            max((abs(float(row["momentum_residual"])) for row in rows), default=0.0)
        ),
        "max_abs_constraint_residual": float(
            max((abs(float(row["constraint_residual"])) for row in rows), default=0.0)
        ),
    }


def trace_summary(rows: list[dict]) -> dict:
    final = rows[-1]
    external = float(final["external_work_J"])
    residual = float(final["balance_residual_J"])
    max_abs_residual = max(abs(float(row["balance_residual_J"])) for row in rows)
    active = [
        abs(float(row["balance_residual_J"]))
        for row in rows
        if abs(float(row["shift_speed_m_per_s"])) > 1.0e-6
    ]
    return {
        "final_external_work_J": external,
        "final_stored_energy_change_J": float(final["stored_energy_change_J"]),
        "final_kinetic_energy_change_J": float(final["kinetic_energy_change_J"]),
        "final_potential_energy_change_J": float(final["potential_energy_change_J"]),
        "final_primary_slip_dissipation_J": float(
            final["primary_slip_dissipation_J"]
        ),
        "final_secondary_slip_dissipation_J": float(
            final["secondary_slip_dissipation_J"]
        ),
        "final_slip_dissipation_J": float(final["slip_dissipation_J"]),
        "final_impact_capture_dissipation_J": float(
            final["impact_capture_dissipation_J"]
        ),
        "final_balance_residual_J": residual,
        "final_balance_fraction_of_abs_external_work": (
            abs(residual) / max(abs(external), 1.0)
        ),
        "max_abs_balance_residual_J": float(max_abs_residual),
        "max_abs_balance_residual_during_active_shift_J": (
            float(max(active)) if active else 0.0
        ),
    }


def evaluate_acceptance(
    *,
    spec: dict,
    nominal_trace: dict,
    tight_trace: dict | None,
    quadrature_rows: list[dict],
    event: dict,
    refinement: dict | None,
    completed_nominal: bool,
    completed_tight: bool | None,
) -> tuple[str, list[dict]]:
    limits = spec["acceptance_criteria"]
    checks: list[dict] = []

    def check(name: str, value, limit, relation: str = "<="):
        passed = value <= limit
        checks.append(
            {
                "name": name,
                "value": value,
                "limit": limit,
                "relation": relation,
                "passed": passed,
            }
        )

    checks.append(
        {
            "name": "nominal_integration_completed",
            "value": completed_nominal,
            "limit": True,
            "relation": "==",
            "passed": bool(completed_nominal),
        }
    )
    if completed_tight is not None:
        checks.append(
            {
                "name": "tight_integration_completed",
                "value": completed_tight,
                "limit": True,
                "relation": "==",
                "passed": bool(completed_tight),
            }
        )

    check(
        "final_balance_fraction_of_abs_external_work",
        nominal_trace["final_balance_fraction_of_abs_external_work"],
        limits["max_final_balance_fraction_of_abs_external_work"],
    )
    if tight_trace is not None:
        check(
            "tight_final_balance_fraction_of_abs_external_work",
            tight_trace["final_balance_fraction_of_abs_external_work"],
            limits["max_final_balance_fraction_of_abs_external_work"],
        )
    if len(quadrature_rows) >= 2:
        previous = abs(float(quadrature_rows[-2]["sum_continuous_raw_defect_J"]))
        finest = abs(float(quadrature_rows[-1]["sum_continuous_raw_defect_J"]))
        ratio = finest / max(previous, 1.0e-15)
        check(
            "finest_to_previous_abs_continuous_defect_ratio",
            ratio,
            limits["max_finest_to_previous_abs_continuous_defect_ratio"],
        )
    check(
        "max_abs_event_energy_defect_J",
        event["max_abs_event_energy_defect_J"],
        limits["max_abs_event_energy_defect_J"],
    )
    check(
        "max_abs_impact_momentum_residual",
        event["max_abs_momentum_residual"],
        limits["max_impact_momentum_residual"],
    )
    check(
        "max_abs_impact_constraint_residual",
        event["max_abs_constraint_residual"],
        limits["max_impact_constraint_residual"],
    )
    check(
        "negative_impact_loss",
        -event["min_recorded_impact_loss_J"],
        limits["negative_impact_loss_tolerance_J"],
    )
    if refinement is not None:
        check(
            "max_normalized_final_state_delta",
            refinement["max_normalized_final_state_delta"],
            limits["max_normalized_final_state_delta"],
        )
        checks.append(
            {
                "name": "transition_count_stable_under_refinement",
                "value": [
                    refinement["nominal_transition_count"],
                    refinement["tight_transition_count"],
                ],
                "limit": "equal",
                "relation": "==",
                "passed": (
                    refinement["nominal_transition_count"]
                    == refinement["tight_transition_count"]
                ),
            }
        )

    return ("PASS" if all(item["passed"] for item in checks) else "REVIEW"), checks


def save_plots(
    *,
    trace_rows: list[dict],
    quadrature_rows: list[dict],
    segment_rows: list[dict],
    event_rows: list[dict],
    finest_step: float,
) -> None:
    time = np.asarray([float(row["time_s"]) for row in trace_rows])
    external = np.asarray([float(row["external_work_J"]) for row in trace_rows])
    accounted = np.asarray([float(row["accounted_energy_J"]) for row in trace_rows])
    residual = np.asarray([float(row["balance_residual_J"]) for row in trace_rows])
    kinetic = np.asarray([float(row["kinetic_energy_change_J"]) for row in trace_rows])
    potential = np.asarray([float(row["potential_energy_change_J"]) for row in trace_rows])
    slip = np.asarray([float(row["slip_dissipation_J"]) for row in trace_rows])
    impact = np.asarray(
        [float(row["impact_capture_dissipation_J"]) for row in trace_rows]
    )

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(time, external / 1000.0, label="Net external work")
    ax.plot(time, accounted / 1000.0, label="Stored energy + modeled losses")
    ax.set(
        xlabel="Time (s)",
        ylabel="Cumulative energy (kJ)",
        title="Mechanical-energy balance",
    )
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "energy_balance_cumulative.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(time, kinetic / 1000.0, label="Kinetic energy change")
    ax.plot(time, potential / 1000.0, label="Conservative actuator energy change")
    ax.plot(time, slip / 1000.0, label="Kinetic-slip dissipation")
    ax.plot(time, impact / 1000.0, label="Impact/capture dissipation")
    ax.set(
        xlabel="Time (s)",
        ylabel="Energy (kJ)",
        title="Retained energy and dissipation channels",
    )
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "energy_channels.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(time, residual)
    ax.axhline(0.0, linewidth=1.0)
    ax.set(
        xlabel="Time (s)",
        ylabel="Balance residual (J)",
        title="Energy-balance residual",
    )
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "energy_balance_residual.png", dpi=180)
    plt.close(fig)

    h = np.asarray([float(row["audit_step_s"]) for row in quadrature_rows])
    r = np.asarray(
        [float(row["sum_continuous_raw_defect_J"]) for row in quadrature_rows]
    )
    richardson = float(quadrature_rows[-1]["richardson_zero_step_estimate_J"])
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(h**2, r, marker="o", label="Observed")
    ax.axhline(richardson, linewidth=1.0, label="Richardson estimate")
    ax.set(
        xlabel=r"Audit step squared, $h^2$ (s$^2$)",
        ylabel="Continuous energy defect (J)",
        title="Quadrature refinement",
    )
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "quadrature_convergence.png", dpi=180)
    plt.close(fig)

    tag = step_tag(finest_step)
    defect_key = f"raw_defect_h_{tag}_J"
    indices = np.asarray([int(row["segment_index"]) for row in segment_rows])
    defects = np.asarray([float(row[defect_key]) for row in segment_rows])
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.bar(indices, defects)
    ax.axhline(0.0, linewidth=1.0)
    ax.set(
        xlabel="Continuous segment index",
        ylabel="Energy defect (J)",
        title=f"Continuous-segment residuals at h={finest_step:g} s",
    )
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "continuous_segment_residuals.png", dpi=180)
    plt.close(fig)

    if event_rows:
        event_times = np.asarray([float(row["time_s"]) for row in event_rows])
        event_losses = np.asarray(
            [float(row["recorded_impact_loss_J"]) for row in event_rows]
        )
        fig, ax = plt.subplots(figsize=(9, 5.5))
        positive = event_losses > 0.0
        if np.any(positive):
            ax.scatter(event_times[positive], 1000.0 * event_losses[positive])
            ax.set_yscale("log")
        ax.set(
            xlabel="Time (s)",
            ylabel="Loss per event (mJ)",
            title="Discrete impact/capture losses",
        )
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(ARTIFACTS / "event_losses.png", dpi=180)
        plt.close(fig)


def write_summary_markdown(summary: dict) -> None:
    nominal = summary["nominal_energy_balance"]
    event = summary["event_balance"]
    quadrature = summary["quadrature"]
    refinement = summary.get("solver_refinement")
    stick = summary["stick_invariant_diagnostic"]

    lines = [
        "# CINDER 1.1.2 mechanical-energy consistency",
        "",
        f"**Result:** `{summary['status']}`",
        "",
        "The audited identity is",
        "",
        "`external work = stored-energy change + kinetic-slip dissipation + "
        "impact/capture dissipation + residual`.",
        "",
        "## Headline balance",
        "",
        "| Quantity | Value |",
        "|---|---:|",
        f"| Net external work | {nominal['final_external_work_J']:.9g} J |",
        f"| Stored-energy change | {nominal['final_stored_energy_change_J']:.9g} J |",
        f"| Kinetic-slip dissipation | {nominal['final_slip_dissipation_J']:.9g} J |",
        f"| Impact/capture dissipation | {nominal['final_impact_capture_dissipation_J']:.9g} J |",
        f"| Raw final balance residual | {nominal['final_balance_residual_J']:+.9g} J |",
        f"| Residual / |external work| | {nominal['final_balance_fraction_of_abs_external_work']:.6g} |",
        "",
        "## Numerical refinement",
        "",
        f"Finest audit grid: `{summary['finest_audit_step_s']:.9g} s`.",
        f"Richardson zero-step estimate of the summed continuous defect: "
        f"`{quadrature['richardson_zero_step_estimate_J']:+.9g} J`.",
    ]
    if refinement is not None:
        lines.extend(
            [
                f"Maximum normalized final-state change under the tighter ODE solve: "
                f"`{refinement['max_normalized_final_state_delta']:.6g}`.",
                f"Transition count: `{refinement['nominal_transition_count']}` nominal, "
                f"`{refinement['tight_transition_count']}` tight.",
                f"Tight-run raw balance residual at the same finest audit grid: "
                f"`{summary['tight_energy_balance']['final_balance_residual_J']:+.9g} J`.",
            ]
        )

    lines.extend(
        [
            "",
            "The signed work carried by velocity-level drift on contacts declared "
            "sticking is reported only as a numerical invariant diagnostic; it is "
            "**not** added to the physical dissipation budget.",
            "",
            f"- signed stick-pair work: `{stick['signed_stick_pair_work_J']:+.9g} J`",
            f"- maximum primary stick |v_rel|: "
            f"`{stick['max_abs_primary_stick_relative_speed_m_s']:.6g} m/s`",
            f"- maximum secondary stick |v_rel|: "
            f"`{stick['max_abs_secondary_stick_relative_speed_m_s']:.6g} m/s`",
            "",
            "## Discrete transitions",
            "",
            f"- impact/capture projections audited: `{event['impact_projection_count']}`",
            f"- maximum exact event-energy defect: "
            f"`{event['max_abs_event_energy_defect_J']:.6g} J`",
            f"- maximum momentum residual: `{event['max_abs_momentum_residual']:.6g}`",
            f"- maximum constraint residual: `{event['max_abs_constraint_residual']:.6g}`",
            "",
            "## Scope",
            "",
            summary["scope_boundary"],
            "",
        ]
    )
    (ARTIFACTS / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()

    subprocess.run([sys.executable, str(VERIFY_ENVIRONMENT)], check=True)
    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise SystemExit(
            f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__}."
        )

    spec, base, base_path = load_study()
    if spec["cinder_release"]["version"] != EXPECTED_CINDER_VERSION:
        raise SystemExit("study.json CINDER version does not match this release directory.")

    nominal_integrator = spec["intentional_changes_from_base"]["nominal_integrator"]
    tight_integrator = spec["intentional_changes_from_base"]["tight_integrator"]
    time_span = spec["intentional_changes_from_base"]["time_span_s"]
    audit_steps = tuple(float(v) for v in spec["audit_quadrature_steps_s"])
    if args.quick:
        audit_steps = audit_steps[:2]

    nominal_document = resolved_document(
        base,
        time_span_s=time_span,
        integrator=nominal_integrator,
    )
    nominal_decoded = validate_and_decode(nominal_document)

    if ARTIFACTS.exists() and not args.keep_artifacts:
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    (ARTIFACTS / "resolved_simulation_case_nominal.json").write_text(
        json.dumps(nominal_document, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Running nominal release trajectory...")
    nominal = run_decoded(nominal_decoded)
    system = nominal_decoded.system
    print(
        f"  completed: {nominal.completed}; transitions: {len(nominal.transitions)}; "
        f"final time: {nominal.final_time:.6g} s"
    )

    print("Evaluating continuous-segment quadrature refinement...")
    segment_rows = continuous_segment_balance(system, nominal, audit_steps)
    quadrature_rows, richardson = quadrature_summary(segment_rows, audit_steps)
    finest_step = audit_steps[-1]

    event_rows = event_balance(system, nominal)
    nominal_trace_rows = cumulative_energy_trace(
        system,
        nominal,
        nominal_decoded.initial_state,
        nominal_decoded.initial_mode,
        finest_step,
    )

    nominal_trace = trace_summary(nominal_trace_rows)
    event = event_summary(event_rows)
    stick = stick_diagnostic_summary(segment_rows, finest_step)

    tight = None
    tight_trace = None
    tight_trace_rows = None
    refinement = None
    if not args.quick:
        tight_document = resolved_document(
            base,
            time_span_s=time_span,
            integrator=tight_integrator,
        )
        (ARTIFACTS / "resolved_simulation_case_tight.json").write_text(
            json.dumps(tight_document, indent=2) + "\n",
            encoding="utf-8",
        )
        tight_decoded = validate_and_decode(tight_document)
        print("Running tighter ODE trajectory...")
        tight = run_decoded(tight_decoded)
        refinement = solver_refinement(system, nominal, tight)
        tight_trace_rows = cumulative_energy_trace(
            tight_decoded.system,
            tight,
            tight_decoded.initial_state,
            tight_decoded.initial_mode,
            finest_step,
        )
        tight_trace = trace_summary(tight_trace_rows)
        print(
            "  max normalized final-state delta: "
            f"{refinement['max_normalized_final_state_delta']:.6g}"
        )

    status, acceptance_checks = evaluate_acceptance(
        spec=spec,
        nominal_trace=nominal_trace,
        tight_trace=tight_trace,
        quadrature_rows=quadrature_rows,
        event=event,
        refinement=refinement,
        completed_nominal=nominal.completed,
        completed_tight=(tight.completed if tight is not None else None),
    )

    # Reader-facing artifacts.
    write_csv(ARTIFACTS / "energy_trace_finest.csv", nominal_trace_rows)
    write_csv(ARTIFACTS / "continuous_segment_balance.csv", segment_rows)
    write_csv(ARTIFACTS / "quadrature_convergence.csv", quadrature_rows)
    write_csv(ARTIFACTS / "event_energy_balance.csv", event_rows)
    if tight_trace_rows is not None:
        write_csv(ARTIFACTS / "energy_trace_tight_finest.csv", tight_trace_rows)

    summary = {
        "study": spec["name"],
        "status": status,
        "cinder_version": cinder.__version__,
        "cinder_module_path": str(Path(cinder.__file__).resolve()),
        "release_tag": spec["cinder_release"]["source_tag"],
        "release_commit_sha": spec["cinder_release"]["source_commit_sha"],
        "base_document": str(base_path),
        "base_document_sha256": sha256(base_path),
        "nominal_transition_count": len(nominal.transitions),
        "finest_audit_step_s": finest_step,
        "nominal_energy_balance": nominal_trace,
        "quadrature": {
            "rows": quadrature_rows,
            "richardson_zero_step_estimate_J": richardson,
        },
        "event_balance": event,
        "stick_invariant_diagnostic": stick,
        "solver_refinement": refinement,
        "tight_energy_balance": tight_trace,
        "acceptance_checks": acceptance_checks,
        "scope_boundary": spec["scope_boundary"],
    }
    (ARTIFACTS / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary_markdown(summary)

    if not args.no_plots:
        save_plots(
            trace_rows=nominal_trace_rows,
            quadrature_rows=quadrature_rows,
            segment_rows=segment_rows,
            event_rows=event_rows,
            finest_step=finest_step,
        )

    print("\n=== Energy-study summary ===")
    print(f"status: {status}")
    print(f"net external work: {nominal_trace['final_external_work_J']:.9g} J")
    print(
        "raw final residual: "
        f"{nominal_trace['final_balance_residual_J']:+.9g} J "
        f"({nominal_trace['final_balance_fraction_of_abs_external_work']:.6g} "
        "of |external work|)"
    )
    print(f"Richardson continuous-defect estimate: {richardson:+.9g} J")
    print(
        "max exact event-energy defect: "
        f"{event['max_abs_event_energy_defect_J']:.6g} J"
    )
    if refinement is not None and tight_trace is not None:
        print(
            "tight raw final residual: "
            f"{tight_trace['final_balance_residual_J']:+.9g} J"
        )
        print(
            "max normalized final-state delta: "
            f"{refinement['max_normalized_final_state_delta']:.6g}"
        )
    print(f"artifacts: {ARTIFACTS}")
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
