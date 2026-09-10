"""Audit local mechanical/admissibility invariants on the frozen v1.1.2 baseline."""

from __future__ import annotations

from dataclasses import dataclass
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Iterable

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
from cinder.execution.hybrid.cvt_regime import (
    CVTEngagementState,
    CVTShiftConstraint,
)
from cinder.model.cvt.contact import ContactInterface
from cinder.model.cvt.geometry.belt_length import belt_length_residual
from cinder.model.system import CVTState
from cinder.results.inspection import inspect_cvt_state

HERE = Path(__file__).resolve().parent
RELEASE_ROOT = HERE.parents[1]
VERIFY = RELEASE_ROOT / "verify_environment.py"
SPEC_FILE = HERE / "study.json"
ARTIFACTS = HERE / "artifacts"
EXPECTED_CINDER_VERSION = "1.1.2"
INTERFACES = (ContactInterface.PRIMARY, ContactInterface.SECONDARY)


@dataclass(frozen=True)
class AuditSample:
    time: float
    full_state: np.ndarray
    composed_mode: Any
    cvt_state: CVTState
    sample_location: str


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any, *, allow_nan: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, allow_nan=allow_nan) + "\n",
        encoding="utf-8",
    )


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def verify_environment() -> None:
    subprocess.run([sys.executable, str(VERIFY)], check=True)
    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise RuntimeError(
            f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__} "
            f"at {Path(cinder.__file__).resolve()}."
        )


def resolve_document(spec: dict) -> tuple[dict, Path]:
    base = (HERE / spec["base_document"]).resolve()
    if not base.is_file():
        raise FileNotFoundError(
            f"Frozen default is missing: {base}. "
            "This study intentionally depends only on the release defaults folder."
        )
    document = copy.deepcopy(load_json(base))
    overrides = spec["overrides"]
    document["scenario"]["time_span_s"] = list(overrides["time_span_s"])
    for key, value in overrides["integrator"].items():
        document["execution"]["integrator"][key] = value
    document["execution"]["integrator"]["retain_dense_output"] = True
    return document, base


def validate_and_decode(document: dict):
    validation = validate_simulation_case_document(document)
    if not validation.is_valid:
        for finding in validation.findings:
            print(
                f"[{finding.severity}] "
                f"{finding.document_path or '/'}: {finding.message}"
            )
        raise RuntimeError("Resolved invariant-study input failed CINDER validation.")
    return decode_simulation_case_document(document)


def uniform_segment_times(start: float, end: float, step: float) -> np.ndarray:
    if end <= start:
        return np.asarray([start], dtype=float)
    values = start + step * np.arange(int(math.floor((end - start) / step)) + 1)
    tol = 64.0 * np.finfo(float).eps * max(1.0, abs(start), abs(end))
    if end - values[-1] > tol:
        values = np.append(values, end)
    else:
        values[-1] = end
    return np.asarray(values, dtype=float)


def build_audit_samples(decoded, result, step_s: float) -> list[AuditSample]:
    """Sample each raw hybrid segment without interpolating across resets."""
    samples: list[AuditSample] = []
    for seg_index, segment in enumerate(result.segments):
        times = uniform_segment_times(segment.start_time, segment.end_time, step_s)
        if segment.has_dense_output:
            states = segment.dense_state_at(times)
        else:
            times = segment.time
            states = segment.state
        for j, t in enumerate(times):
            full_state = np.asarray(states[:, j], dtype=float)
            cvt_vector = decoded.system.layout.view(full_state, "cvt")
            location = (
                "segment_start"
                if j == 0
                else "segment_end"
                if j == len(times) - 1
                else "uniform"
            )
            samples.append(
                AuditSample(
                    time=float(t),
                    full_state=full_state,
                    composed_mode=segment.mode,
                    cvt_state=CVTState.from_vector(cvt_vector),
                    sample_location=location,
                )
            )
    return samples


def reconstruct(decoded, sample: AuditSample, *, closure_audit: bool):
    boundaries = decoded.system._shaft_boundaries(
        time=sample.time,
        state=sample.full_state,
    )
    cvt_vector = decoded.system.layout.view(sample.full_state, "cvt")
    return inspect_cvt_state(
        system=decoded.system.cvt,
        time=sample.time,
        vector=cvt_vector,
        mode=sample.composed_mode.cvt,
        shaft_boundaries=boundaries,
        include_closure_audit=closure_audit,
    )


def finite_max_abs(values: Iterable[Any]) -> float:
    vals = [
        abs(float(v))
        for v in values
        if v is not None and math.isfinite(float(v))
    ]
    return max(vals) if vals else float("nan")


def finite_min(values: Iterable[Any]) -> float:
    vals = [
        float(v)
        for v in values
        if v is not None and math.isfinite(float(v))
    ]
    return min(vals) if vals else float("nan")


def finite_max(values: Iterable[Any]) -> float:
    vals = [
        float(v)
        for v in values
        if v is not None and math.isfinite(float(v))
    ]
    return max(vals) if vals else float("nan")


def lambda_at(utilization, interface):
    return (
        utilization.primary_lambda
        if interface is ContactInterface.PRIMARY
        else utilization.secondary_lambda
    )


def inspect_sample(decoded, sample: AuditSample):
    mode = sample.composed_mode.cvt
    engaged = mode.engagement is CVTEngagementState.ENGAGED
    inspection = reconstruct(decoded, sample, closure_audit=engaged)
    model = decoded.system.cvt.model
    geometry = inspection.geometry
    geometry_spec = model.geometry.spec

    row: dict[str, Any] = {
        "time_s": sample.time,
        "sample_location": sample.sample_location,
        "mode": str(sample.composed_mode),
        "cvt_mode": str(mode),
        "engagement": mode.engagement.value,
        "shift_constraint": mode.shift_constraint.value,
        "shift_m": float(inspection.state.shift_position),
        "shift_speed_m_s": float(inspection.state.shift_speed),
        "belt_length_residual_m": (
            belt_length_residual(
                belt_length=geometry_spec.belt_outer_length,
                center_distance=geometry_spec.center_distance,
                primary_outer_radius=geometry.primary.outer,
                secondary_outer_radius=geometry.secondary.outer,
            )
            if engaged
            else float("nan")
        ),
        "closure_max_abs_residual": float("nan"),
        "closure_max_scaled_residual": float("nan"),
        "closure_condition_number": float("nan"),
        "closure_scaled_condition_number": float("nan"),
        "closure_rank": float("nan"),
        "lambda_primary": float("nan"),
        "lambda_secondary": float("nan"),
        "primary_static_lower": float("nan"),
        "primary_static_upper": float("nan"),
        "secondary_static_lower": float("nan"),
        "secondary_static_upper": float("nan"),
        "normal_primary_N": float("nan"),
        "normal_secondary_N": float("nan"),
        "primary_vrel_m_s": float("nan"),
        "secondary_vrel_m_s": float("nan"),
        "primary_arel_m_s2": float("nan"),
        "secondary_arel_m_s2": float("nan"),
        "primary_static_margin": float("nan"),
        "secondary_static_margin": float("nan"),
        "primary_slip_pair_power_W": float("nan"),
        "secondary_slip_pair_power_W": float("nan"),
        "slip_direction_consistent": True,
        "mechanism_contacts_admissible": True,
        "low_ratio_seat_reaction_N": float("nan"),
        "upper_stop_reaction_N": float("nan"),
        "deadzone_lower_stop_reaction_N": float("nan"),
        "fixed_shift_acceleration_m_s2": float("nan"),
        "deadzone_secondary_lock_speed_residual_m_s": float("nan"),
        "deadzone_secondary_lock_acceleration_residual_m_s2": float("nan"),
    }
    equation_rows: list[dict[str, Any]] = []

    if engaged:
        audit = inspection.closure_audit
        contact = inspection.contact
        if audit is None or contact is None:
            raise RuntimeError("Engaged audit sample did not reconstruct contact closure.")

        row["closure_max_abs_residual"] = audit.max_abs_equation_residual
        z = np.asarray(audit.unknowns.as_tuple(), dtype=float)
        A = np.asarray(audit.matrix, dtype=float)
        b = np.asarray(audit.right_hand_side, dtype=float)
        algebraic_residual = A @ z - b
        row_scale = np.maximum(
            1.0,
            np.maximum(
                np.abs(b),
                np.sum(np.abs(A) * np.abs(z)[None, :], axis=1),
            ),
        )
        scaled_residual = algebraic_residual / row_scale
        row["closure_max_scaled_residual"] = float(
            np.max(np.abs(scaled_residual))
        )
        row["closure_condition_number"] = audit.condition_number
        row["closure_scaled_condition_number"] = audit.scaled_condition_number
        row["closure_rank"] = audit.matrix_rank

        for eq_index, residual in enumerate(audit.equation_residuals):
            equation_rows.append(
                {
                    "time_s": sample.time,
                    "shift_constraint": mode.shift_constraint.value,
                    "contact_mode": contact.mode.value,
                    "equation": residual.name,
                    "residual": float(residual.value),
                    "row_scale": float(row_scale[eq_index]),
                    "scaled_residual": float(scaled_residual[eq_index]),
                }
            )

        traction = contact.traction_utilization
        motion = contact.relative_motion
        law = decoded.system.cvt.traction_law
        row.update(
            {
                "lambda_primary": traction.primary_lambda,
                "lambda_secondary": traction.secondary_lambda,
                "primary_static_lower": law.primary_static_interval.lower,
                "primary_static_upper": law.primary_static_interval.upper,
                "secondary_static_lower": law.secondary_static_interval.lower,
                "secondary_static_upper": law.secondary_static_interval.upper,
                "normal_primary_N": contact.normal_primary,
                "normal_secondary_N": contact.normal_secondary,
                "slip_direction_consistent": bool(
                    contact.slipped_directions_are_consistent()
                ),
                "mechanism_contacts_admissible": bool(
                    contact.mechanism_contacts_are_admissible(tolerance=0.0)
                ),
            }
        )

        for interface in INTERFACES:
            prefix = interface.value
            vrel = motion.relative_speed_at(interface)
            arel = motion.relative_acceleration_at(interface)
            row[f"{prefix}_vrel_m_s"] = vrel
            row[f"{prefix}_arel_m_s2"] = arel
            lam = lambda_at(traction, interface)
            normal = contact.normal_at(interface)

            if interface in contact.mode.sticking_interfaces:
                row[f"{prefix}_static_margin"] = law.static_margin_at(
                    interface, lam
                )
            if interface in contact.mode.slipping_interfaces:
                row[f"{prefix}_slip_pair_power_W"] = lam * normal * vrel

        if mode.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
            row["low_ratio_seat_reaction_N"] = contact.low_ratio_seat_reaction
            row["fixed_shift_acceleration_m_s2"] = audit.unknowns.shift_acceleration
        elif mode.shift_constraint is CVTShiftConstraint.UPPER_STOP:
            row["upper_stop_reaction_N"] = contact.upper_stop_reaction
            row["fixed_shift_acceleration_m_s2"] = audit.unknowns.shift_acceleration
    else:
        deadzone = inspection.deadzone
        if deadzone is None:
            raise RuntimeError("Deadzone audit sample did not reconstruct deadzone mechanics.")
        row["deadzone_secondary_lock_speed_residual_m_s"] = (
            deadzone.belt_secondary_speed_residual
        )
        row["deadzone_secondary_lock_acceleration_residual_m_s2"] = (
            deadzone.belt_secondary_acceleration_residual
        )
        if mode.shift_constraint is CVTShiftConstraint.LOWER_STOP:
            row["deadzone_lower_stop_reaction_N"] = deadzone.stop_reaction
            row["fixed_shift_acceleration_m_s2"] = (
                deadzone.state_derivative.shift_acceleration
            )

    return row, equation_rows


def post_transition_rows(decoded, result):
    rows = []
    for index, record in enumerate(result.transitions):
        next_mode = record.transition.next_mode
        if next_mode is None:
            continue
        full_state = np.asarray(record.post_transition_state, dtype=float)
        sample = AuditSample(
            time=float(record.time),
            full_state=full_state,
            composed_mode=next_mode,
            cvt_state=CVTState.from_vector(
                decoded.system.layout.view(full_state, "cvt")
            ),
            sample_location="post_transition_exact",
        )
        try:
            row, _ = inspect_sample(decoded, sample)
            row = {
                "transition_index": index,
                "fired_event_names": "|".join(record.fired_event_names),
                "transition_reason": record.transition.reason,
                **row,
            }
        except Exception as exc:
            row = {
                "transition_index": index,
                "time_s": float(record.time),
                "fired_event_names": "|".join(record.fired_event_names),
                "transition_reason": record.transition.reason,
                "inspection_error": f"{type(exc).__name__}: {exc}",
            }
        rows.append(row)
    return rows


def summarize(rows, equation_rows, guards):
    engaged = [r for r in rows if r["engagement"] == "engaged"]
    stick_p = [r for r in engaged if math.isfinite(float(r["primary_static_margin"]))]
    stick_s = [r for r in engaged if math.isfinite(float(r["secondary_static_margin"]))]
    slip_p = [r for r in engaged if math.isfinite(float(r["primary_slip_pair_power_W"]))]
    slip_s = [r for r in engaged if math.isfinite(float(r["secondary_slip_pair_power_W"]))]
    fixed = [
        r for r in rows
        if r["shift_constraint"] in ("low_ratio_seat", "upper_stop", "lower_stop")
    ]

    metrics = [
        ("belt_length_residual", "Belt-length closure", finite_max_abs(r["belt_length_residual_m"] for r in rows), "m", guards["belt_length_residual_m"], "upper"),
        ("closure_residual", "8x8 equation residual", finite_max_abs(r["residual"] for r in equation_rows), "native row units", guards["closure_equation_residual"], "upper"),
        ("closure_scaled_residual", "8x8 scaled equation residual", finite_max_abs(r["scaled_residual"] for r in equation_rows), "dimensionless", guards["closure_scaled_equation_residual"], "upper"),
        ("primary_stick_velocity", "Primary stick |v_rel|", finite_max_abs(r["primary_vrel_m_s"] for r in stick_p), "m/s", guards["stick_velocity_drift_m_s"], "upper"),
        ("secondary_stick_velocity", "Secondary stick |v_rel|", finite_max_abs(r["secondary_vrel_m_s"] for r in stick_s), "m/s", guards["stick_velocity_drift_m_s"], "upper"),
        ("primary_stick_acceleration", "Primary stick |a_rel|", finite_max_abs(r["primary_arel_m_s2"] for r in stick_p), "m/s^2", guards["stick_acceleration_residual_m_s2"], "upper"),
        ("secondary_stick_acceleration", "Secondary stick |a_rel|", finite_max_abs(r["secondary_arel_m_s2"] for r in stick_s), "m/s^2", guards["stick_acceleration_residual_m_s2"], "upper"),
        ("primary_static_margin", "Minimum primary static margin", finite_min(r["primary_static_margin"] for r in stick_p), "lambda", -guards["static_margin_negative_tolerance"], "lower"),
        ("secondary_static_margin", "Minimum secondary static margin", finite_min(r["secondary_static_margin"] for r in stick_s), "lambda", -guards["static_margin_negative_tolerance"], "lower"),
        ("primary_slip_pair_power", "Worst positive primary slip-pair power", max(0.0, finite_max(r["primary_slip_pair_power_W"] for r in slip_p)) if slip_p else float("nan"), "W", guards["positive_slip_pair_power_W"], "upper"),
        ("secondary_slip_pair_power", "Worst positive secondary slip-pair power", max(0.0, finite_max(r["secondary_slip_pair_power_W"] for r in slip_s)) if slip_s else float("nan"), "W", guards["positive_slip_pair_power_W"], "upper"),
        ("primary_normal", "Minimum primary normal resultant", finite_min(r["normal_primary_N"] for r in engaged), "N", -guards["negative_normal_tolerance_N"], "lower"),
        ("secondary_normal", "Minimum secondary normal resultant", finite_min(r["normal_secondary_N"] for r in engaged), "N", -guards["negative_normal_tolerance_N"], "lower"),
        ("low_ratio_reaction", "Minimum low-ratio-seat reaction", finite_min(r["low_ratio_seat_reaction_N"] for r in engaged), "N", -guards["negative_stop_reaction_tolerance_N"], "lower"),
        ("upper_stop_reaction", "Minimum upper-stop reaction", finite_min(r["upper_stop_reaction_N"] for r in engaged), "N", -guards["negative_stop_reaction_tolerance_N"], "lower"),
        ("deadzone_lower_stop_reaction", "Minimum deadzone lower-stop reaction", finite_min(r["deadzone_lower_stop_reaction_N"] for r in rows), "N", -guards["negative_stop_reaction_tolerance_N"], "lower"),
        ("fixed_shift_speed", "Fixed-shift |s_dot|", finite_max_abs(r["shift_speed_m_s"] for r in fixed), "m/s", guards["fixed_shift_speed_m_s"], "upper"),
        ("fixed_shift_acceleration", "Fixed-shift |s_ddot|", finite_max_abs(r["fixed_shift_acceleration_m_s2"] for r in fixed), "m/s^2", guards["fixed_shift_acceleration_m_s2"], "upper"),
        ("deadzone_secondary_speed_lock", "Deadzone secondary-lock |v residual|", finite_max_abs(r["deadzone_secondary_lock_speed_residual_m_s"] for r in rows), "m/s", guards["deadzone_secondary_lock_speed_m_s"], "upper"),
        ("deadzone_secondary_accel_lock", "Deadzone secondary-lock |a residual|", finite_max_abs(r["deadzone_secondary_lock_acceleration_residual_m_s2"] for r in rows), "m/s^2", guards["deadzone_secondary_lock_acceleration_m_s2"], "upper"),
    ]

    out = []
    for key, label, value, unit, guard, direction in metrics:
        if not math.isfinite(float(value)):
            status = "NOT_APPLICABLE"
        elif direction == "upper":
            status = "PASS" if value <= guard else "REVIEW"
        else:
            status = "PASS" if value >= guard else "REVIEW"
        out.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "unit": unit,
                "guard": guard,
                "guard_direction": direction,
                "status": status,
            }
        )

    ranks = [
        int(r["closure_rank"])
        for r in engaged
        if math.isfinite(float(r["closure_rank"]))
    ]
    structural = {
        "total_samples": len(rows),
        "engaged_samples": len(engaged),
        "closure_rank_min": min(ranks) if ranks else None,
        "closure_rank_max": max(ranks) if ranks else None,
        "closure_rank_all_8": bool(ranks) and min(ranks) == max(ranks) == 8,
        "all_slip_directions_consistent": all(
            bool(r["slip_direction_consistent"]) for r in engaged
        ),
        "all_mechanism_contacts_admissible": all(
            bool(r["mechanism_contacts_admissible"]) for r in engaged
        ),
        "review_metric_count": sum(r["status"] == "REVIEW" for r in out),
    }
    return out, structural


def plots(rows, metrics):
    time_s = np.asarray([r["time_s"] for r in rows], dtype=float)

    def arr(key):
        return np.asarray([float(r[key]) for r in rows], dtype=float)

    fig, ax = plt.subplots(figsize=(10.5, 6.0))
    for key, label in (
        ("belt_length_residual_m", "Belt length [m]"),
        ("closure_max_scaled_residual", "8x8 closure, scaled"),
        ("primary_arel_m_s2", "Primary stick a_rel"),
        ("secondary_arel_m_s2", "Secondary stick a_rel"),
    ):
        y = np.abs(arr(key))
        y[~np.isfinite(y)] = np.nan
        ax.semilogy(time_s, np.maximum(y, 1e-16), label=label)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Absolute residual")
    ax.set_title("Local mechanical residuals")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "01_core_residuals.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    ax.plot(time_s, arr("lambda_primary"), label=r"$\lambda_p$")
    ax.plot(time_s, arr("lambda_secondary"), label=r"$\lambda_s$")
    for key, label, style in (
        ("primary_static_lower", "Primary static bounds", "--"),
        ("primary_static_upper", None, "--"),
        ("secondary_static_lower", "Secondary static bounds", ":"),
        ("secondary_static_upper", None, ":"),
    ):
        y = arr(key)
        good = np.isfinite(y)
        if np.any(good):
            ax.plot(time_s[good], y[good], linestyle=style, linewidth=1.0, label=label)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Traction utilization")
    ax.set_title("Solved traction requirements and static-capacity bounds")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "02_traction_utilization.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    ax.plot(time_s, arr("normal_primary_N"), label=r"$N_p$")
    ax.plot(time_s, arr("normal_secondary_N"), label=r"$N_s$")
    ax.axhline(0.0, linewidth=1.0)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Normal resultant [N]")
    ax.set_title("Unilateral contact normal resultants")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "03_contact_normals.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    plotted = False
    for key, label in (
        ("deadzone_lower_stop_reaction_N", "Deadzone lower stop"),
        ("low_ratio_seat_reaction_N", "Low-ratio seat"),
        ("upper_stop_reaction_N", "Upper stop"),
    ):
        y = arr(key)
        good = np.isfinite(y)
        if np.any(good):
            ax.plot(time_s[good], y[good], label=label)
            plotted = True
    ax.axhline(0.0, linewidth=1.0)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Recovered reaction [N]")
    ax.set_title("Unilateral stop reactions")
    ax.grid(True, alpha=0.25)
    if plotted:
        ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "04_stop_reactions.png", dpi=180)
    plt.close(fig)

    score = [
        m for m in metrics
        if m["status"] != "NOT_APPLICABLE"
        and m["guard_direction"] == "upper"
        and float(m["guard"]) > 0
        and math.isfinite(float(m["value"]))
    ]
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    y = np.arange(len(score))
    values = [
        math.log10(max(float(m["value"]) / float(m["guard"]), 1e-12))
        for m in score
    ]
    ax.barh(y, values)
    ax.axvline(0.0, linewidth=1.2)
    ax.set_yticks(y)
    ax.set_yticklabels([m["label"] for m in score], fontsize=8)
    ax.set_xlabel(r"$\log_{10}(\mathrm{observed}/\mathrm{review\ guard})$")
    ax.set_title("Invariant review-guard ratios (left of zero passes)")
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "05_review_guard_ratios.png", dpi=180)
    plt.close(fig)


def main() -> int:
    verify_environment()
    spec = load_json(SPEC_FILE)
    document, base_path = resolve_document(spec)
    decoded = validate_and_decode(document)

    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)
    write_json(ARTIFACTS / "resolved_simulation_case.json", document)

    print("Integrating frozen default with invariant-study numerical overrides...")
    started = time.perf_counter()
    result = integrate_hybrid(
        system=decoded.system,
        time_span=decoded.time_span,
        initial_state=decoded.initial_state,
        initial_mode=decoded.initial_mode,
        settings=decoded.integrator_settings,
    )
    elapsed = time.perf_counter() - started

    step_s = float(spec["overrides"]["audit_time_step_s"])
    samples = build_audit_samples(decoded, result, step_s)
    rows: list[dict[str, Any]] = []
    equation_rows: list[dict[str, Any]] = []
    for i, sample in enumerate(samples, 1):
        if i % 1000 == 0:
            print(f"  audit sample {i}/{len(samples)}")
        row, eq = inspect_sample(decoded, sample)
        rows.append(row)
        equation_rows.extend(eq)

    transition_rows = post_transition_rows(decoded, result)
    write_rows(ARTIFACTS / "sample_audit.csv", rows)
    write_rows(ARTIFACTS / "closure_equation_residuals.csv", equation_rows)
    write_rows(ARTIFACTS / "post_transition_audit.csv", transition_rows)

    metrics, structural = summarize(
        rows,
        equation_rows,
        spec["review_guards"],
    )
    write_rows(ARTIFACTS / "headline_invariant_table.csv", metrics)
    plots(rows, metrics)

    overall = (
        "PASS"
        if structural["closure_rank_all_8"]
        and structural["all_slip_directions_consistent"]
        and structural["all_mechanism_contacts_admissible"]
        and structural["review_metric_count"] == 0
        else "REVIEW"
    )
    summary = {
        "study": spec,
        "cinder_version": cinder.__version__,
        "cinder_module_path": str(Path(cinder.__file__).resolve()),
        "base_document": str(base_path),
        "base_document_sha256": sha256(base_path),
        "completed": result.completed,
        "termination_reason": result.termination_reason,
        "transition_count": len(result.transitions),
        "wall_time_s": elapsed,
        "headline_metrics": metrics,
        "structural_checks": structural,
        "overall_status": overall,
    }
    write_json(ARTIFACTS / "summary.json", summary, allow_nan=True)

    lines = [
        "# CINDER v1.1.2 mechanical-invariants audit",
        "",
        f"Overall status: **{overall}**",
        "",
        f"Audited samples: `{structural['total_samples']}`; engaged samples: `{structural['engaged_samples']}`.",
        f"Hybrid transitions: `{len(result.transitions)}`.",
        "",
        "| Check | Worst observed | Review guard | Status |",
        "|---|---:|---:|---|",
    ]
    for m in metrics:
        value = (
            "n/a"
            if not math.isfinite(float(m["value"]))
            else f"{float(m['value']):.6g} {m['unit']}"
        )
        lines.append(
            f"| {m['label']} | {value} | {float(m['guard']):.6g} | {m['status']} |"
        )
    lines += [
        "",
        f"- 8×8 closure rank stayed 8: **{structural['closure_rank_all_8']}**",
        f"- kinetic slip directions stayed consistent: **{structural['all_slip_directions_consistent']}**",
        f"- mechanism unilateral contacts stayed admissible: **{structural['all_mechanism_contacts_admissible']}**",
        "",
        "Review guards are diagnostics only. Raw time histories and exact post-transition checks are retained alongside this summary.",
    ]
    (ARTIFACTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Mechanical invariants complete: {ARTIFACTS}")
    print(f"Overall status: {overall}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
