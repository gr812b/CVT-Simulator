"""Domain-oriented mechanical invariant audit for CINDER 1.1.2.

This study is intentionally broader than a nominal-trajectory audit.  It combines
(a) the frozen Baja reference run, (b) deterministic bench initial-condition
searches that populate every engaged contact topology and slip-direction
quadrant, (c) static / structural-regime cases, (d) boundary-approach cases,
(e) geometry-domain checks, and (f) negative controls.

The checker does not add test-only CVT physics.  Bench cases attach CINDER's
existing FixedShaftBoundary objects to the frozen production plant, use NoHost,
and let the production initial-regime classifier and hybrid transition machinery
decide which branch is admissible.
"""
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
from typing import Any, Iterable, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import cinder
from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)
from cinder.execution.hybrid import HybridIntegratorSettings
from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
from cinder.execution.hybrid.cvt_regime import CVTEngagementState, CVTShiftConstraint
from cinder.hosts import NoHost
from cinder.model.boundaries.shaft import FixedShaftBoundary
from cinder.model.cvt.closure import ClosureUnknowns
from cinder.model.cvt.contact import (
    ContactInterface,
    EngagedContactMode,
    SlipDirection,
    evaluate_contact_relative_speed,
)
from cinder.model.cvt.geometry.belt_length import belt_length_residual
from cinder.model.system import CVTState
from cinder.results.fields import recover_belt_tension_boundaries
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
    case_id: str
    time: float
    full_state: np.ndarray
    composed_mode: Any
    sample_location: str


@dataclass(frozen=True)
class ContactRequest:
    case_id: str
    mode: EngagedContactMode
    primary_vrel_sign: int
    secondary_vrel_sign: int
    rotation_sign: int


@dataclass(frozen=True)
class FoundCase:
    case_id: str
    system: ComposedCVTHybridSystem
    initial_state: np.ndarray
    initial_mode: Any
    metadata: dict[str, Any]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any, *, allow_nan: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=allow_nan) + "\n", encoding="utf-8")


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_environment() -> None:
    subprocess.run([sys.executable, str(VERIFY)], check=True)
    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise RuntimeError(
            f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__} "
            f"at {Path(cinder.__file__).resolve()}."
        )


def validate_and_decode(document: dict):
    validation = validate_simulation_case_document(document)
    if not validation.is_valid:
        for finding in validation.findings:
            print(f"[{finding.severity}] {finding.document_path or '/'}: {finding.message}")
        raise RuntimeError("Invariant-study input failed CINDER document validation.")
    return decode_simulation_case_document(document)


def load_frozen_reference(spec: dict):
    base = (HERE / spec["base_document"]).resolve()
    if not base.is_file():
        raise FileNotFoundError(f"Frozen reference case missing: {base}")
    document = copy.deepcopy(load_json(base))
    nominal = spec["nominal_run"]
    document["scenario"]["time_span_s"] = list(nominal["time_span_s"])
    for key, value in nominal["integrator"].items():
        document["execution"]["integrator"][key] = value
    document["execution"]["integrator"]["retain_dense_output"] = True
    return validate_and_decode(document), base, document


def make_bench_system(decoded, *, primary_torque: float, secondary_torque: float,
                      primary_inertia: float, secondary_inertia: float) -> ComposedCVTHybridSystem:
    return ComposedCVTHybridSystem.from_plant(
        plant=decoded.plant,
        primary_boundary=FixedShaftBoundary(
            external_torque=float(primary_torque), equivalent_inertia=float(primary_inertia)
        ),
        secondary_boundary=FixedShaftBoundary(
            external_torque=float(secondary_torque), equivalent_inertia=float(secondary_inertia)
        ),
        host=NoHost(),
    )


def full_state(system: ComposedCVTHybridSystem, cvt_state: CVTState) -> np.ndarray:
    return np.asarray(
        system.initial_state(cvt_state=cvt_state, host_state=system.host.initial_state()),
        dtype=float,
    )


def cvt_state_from_full(system: ComposedCVTHybridSystem, state: np.ndarray) -> CVTState:
    return CVTState.from_vector(system.layout.view(state, "cvt"))


def boundaries_at(system: ComposedCVTHybridSystem, *, time_s: float, state: np.ndarray):
    return system._shaft_boundaries(time=float(time_s), state=np.asarray(state, dtype=float))


def reconstruct(system: ComposedCVTHybridSystem, sample: AuditSample, *, closure_audit: bool):
    vector = system.layout.view(sample.full_state, "cvt")
    return inspect_cvt_state(
        system=system.cvt,
        time=sample.time,
        vector=vector,
        mode=sample.composed_mode.cvt,
        shaft_boundaries=boundaries_at(system, time_s=sample.time, state=sample.full_state),
        include_closure_audit=closure_audit,
    )


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


def build_trace_samples(case_id: str, result, step_s: float) -> list[AuditSample]:
    samples: list[AuditSample] = []
    for segment in result.segments:
        times = uniform_segment_times(segment.start_time, segment.end_time, step_s)
        if segment.has_dense_output:
            states = segment.dense_state_at(times)
        else:
            times = segment.time
            states = segment.state
        for j, t in enumerate(times):
            location = "segment_start" if j == 0 else "segment_end" if j == len(times)-1 else "uniform"
            samples.append(AuditSample(
                case_id=case_id,
                time=float(t),
                full_state=np.asarray(states[:, j], dtype=float),
                composed_mode=segment.mode,
                sample_location=location,
            ))
    return samples


def finite_values(values: Iterable[Any]) -> list[float]:
    out: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            x = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x):
            out.append(x)
    return out


def finite_min(values: Iterable[Any]) -> float:
    vals = finite_values(values)
    return min(vals) if vals else float("nan")


def finite_max(values: Iterable[Any]) -> float:
    vals = finite_values(values)
    return max(vals) if vals else float("nan")


def finite_max_abs(values: Iterable[Any]) -> float:
    vals = finite_values(values)
    return max(abs(x) for x in vals) if vals else float("nan")


def lambda_at(utilization, interface: ContactInterface) -> float:
    return float(utilization.primary_lambda if interface is ContactInterface.PRIMARY else utilization.secondary_lambda)


def _weight_mean(z: float) -> float:
    """Mean of expm1(-z*u)/expm1(-z), u in [0,1], with stable zero limit."""
    if abs(z) < 1.0e-6:
        # 1/2 + z/12 - z^3/720 + O(z^5)
        return 0.5 + z / 12.0 - z**3 / 720.0
    den = math.expm1(-z)
    return -1.0 / z - 1.0 / den


def _wrap_field_metrics(*, snapshot, unknowns, radius, wrap_angle: float,
                        lambda_value: float, tension_in: float, tension_out: float) -> dict[str, float]:
    q = snapshot.belt_linear_density
    sin_beta = math.sin(snapshot.sheave_half_angle)
    state = snapshot.state
    rddot = (
        radius.d2_center_of_mass_ds2 * state.shift_speed**2
        + radius.d_center_of_mass_ds * unknowns.shift_acceleration
    )
    radial_offset = q * (state.belt_speed**2 - radius.center_of_mass * rddot)
    min_tension = min(float(tension_in), float(tension_out))
    min_dnormal_dtheta = (min_tension - radial_offset) / sin_beta
    z = float(lambda_value) * float(wrap_angle) / sin_beta
    integral_tension = float(wrap_angle) * (
        float(tension_in) + (float(tension_out) - float(tension_in)) * _weight_mean(z)
    )
    normal_from_field = (integral_tension - float(wrap_angle) * radial_offset) / sin_beta
    return {
        "radial_offset_N": float(radial_offset),
        "min_tension_N": float(min_tension),
        "min_dnormal_dtheta_N_per_rad": float(min_dnormal_dtheta),
        "normal_from_field_N": float(normal_from_field),
    }


def _deadzone_mechanism_margins(system, inspection) -> tuple[tuple[str, float], ...]:
    deadzone = inspection.deadzone
    if deadzone is None:
        return ()
    snapshot = deadzone.snapshot
    derivative = deadzone.state_derivative
    radius = snapshot.belt_secondary_lock_radius
    secondary_belt_torque = -snapshot.inertias.belt.mass * radius * derivative.belt_acceleration
    unknowns = ClosureUnknowns.from_components(
        primary_angular_acceleration=derivative.primary_angular_acceleration,
        secondary_angular_acceleration=derivative.secondary_angular_acceleration,
        belt_acceleration=derivative.belt_acceleration,
        shift_acceleration=derivative.shift_acceleration,
        primary_torque=0.0,
        secondary_torque=secondary_belt_torque,
    )
    pctx = system.cvt.model.primary_actuation_context(
        time=inspection.time, state=snapshot.state, geometry=snapshot.primary_geometry
    )
    sctx = system.cvt.model.secondary_actuation_context(
        time=inspection.time, state=snapshot.state, geometry=snapshot.locked_geometry
    )
    return tuple((f"primary/{k}", float(v)) for k, v in system.cvt.model.primary_actuator.compressive_contact_margins(pctx, unknowns)) + tuple(
        (f"secondary/{k}", float(v)) for k, v in system.cvt.model.secondary_actuator.compressive_contact_margins(sctx, unknowns)
    )


def inspect_sample(system: ComposedCVTHybridSystem, sample: AuditSample):
    mode = sample.composed_mode.cvt
    engaged = mode.engagement is CVTEngagementState.ENGAGED
    inspection = reconstruct(system, sample, closure_audit=engaged)
    geometry_spec = system.cvt.model.geometry.spec
    geometry = inspection.geometry

    row: dict[str, Any] = {
        "case_id": sample.case_id,
        "time_s": sample.time,
        "sample_location": sample.sample_location,
        "engagement": mode.engagement.value,
        "shift_constraint": mode.shift_constraint.value,
        "contact_mode": mode.contact_regime.mode.value if mode.contact_regime is not None else "",
        "shift_m": inspection.state.shift_position,
        "shift_speed_m_s": inspection.state.shift_speed,
        "belt_length_residual_m": float("nan"),
        "closure_max_abs_residual": float("nan"),
        "closure_max_scaled_residual": float("nan"),
        "closure_rank": float("nan"),
        "lambda_primary": float("nan"),
        "lambda_secondary": float("nan"),
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
        "mechanism_min_margin": float("nan"),
        "belt_min_tension_N": float("nan"),
        "primary_min_dnormal_dtheta_N_per_rad": float("nan"),
        "secondary_min_dnormal_dtheta_N_per_rad": float("nan"),
        "primary_field_normal_residual_N": float("nan"),
        "secondary_field_normal_residual_N": float("nan"),
        "low_ratio_seat_reaction_N": float("nan"),
        "upper_stop_reaction_N": float("nan"),
        "deadzone_lower_stop_reaction_N": float("nan"),
        "fixed_shift_acceleration_m_s2": float("nan"),
        "deadzone_secondary_lock_speed_residual_m_s": float("nan"),
        "deadzone_secondary_lock_acceleration_residual_m_s2": float("nan"),
        "inspection_error": "",
    }
    equation_rows: list[dict[str, Any]] = []
    mechanism_rows: list[dict[str, Any]] = []

    if engaged:
        row["belt_length_residual_m"] = belt_length_residual(
            belt_length=geometry_spec.belt_outer_length,
            center_distance=geometry_spec.center_distance,
            primary_outer_radius=geometry.primary.outer,
            secondary_outer_radius=geometry.secondary.outer,
        )
        audit = inspection.closure_audit
        contact = inspection.contact
        if audit is None or contact is None:
            raise RuntimeError("Engaged inspection did not reconstruct closure/contact data.")
        zvec = np.asarray(audit.unknowns.as_tuple(), dtype=float)
        A = np.asarray(audit.matrix, dtype=float)
        b = np.asarray(audit.right_hand_side, dtype=float)
        residual = A @ zvec - b
        scale = np.maximum(1.0, np.maximum(np.abs(b), np.sum(np.abs(A) * np.abs(zvec)[None, :], axis=1)))
        scaled = residual / scale
        row.update({
            "closure_max_abs_residual": float(np.max(np.abs(residual))),
            "closure_max_scaled_residual": float(np.max(np.abs(scaled))),
            "closure_rank": int(audit.matrix_rank),
            "lambda_primary": float(contact.traction_utilization.primary_lambda),
            "lambda_secondary": float(contact.traction_utilization.secondary_lambda),
            "normal_primary_N": float(contact.normal_primary),
            "normal_secondary_N": float(contact.normal_secondary),
            "slip_direction_consistent": bool(contact.slipped_directions_are_consistent()),
            "mechanism_contacts_admissible": bool(contact.mechanism_contacts_are_admissible(tolerance=0.0)),
        })
        for idx, eq in enumerate(audit.equation_residuals):
            equation_rows.append({
                "case_id": sample.case_id, "time_s": sample.time,
                "shift_constraint": mode.shift_constraint.value,
                "contact_mode": contact.mode.value, "equation": eq.name,
                "residual": float(residual[idx]), "row_scale": float(scale[idx]),
                "scaled_residual": float(scaled[idx]),
            })

        law = system.cvt.traction_law
        motion = contact.relative_motion
        for interface in INTERFACES:
            prefix = interface.value
            vrel = float(motion.relative_speed_at(interface))
            arel = float(motion.relative_acceleration_at(interface))
            row[f"{prefix}_vrel_m_s"] = vrel
            row[f"{prefix}_arel_m_s2"] = arel
            lam = lambda_at(contact.traction_utilization, interface)
            normal = float(contact.normal_at(interface))
            if interface in contact.mode.sticking_interfaces:
                row[f"{prefix}_static_margin"] = float(law.static_margin_at(interface, lam))
            if interface in contact.mode.slipping_interfaces:
                row[f"{prefix}_slip_pair_power_W"] = float(lam * normal * vrel)

        margins = tuple((str(k), float(v)) for k, v in contact.mechanism_contact_margins)
        for key, value in margins:
            mechanism_rows.append({"case_id": sample.case_id, "time_s": sample.time, "key": key, "margin": value})
        row["mechanism_min_margin"] = finite_min(v for _, v in margins)

        tensions = recover_belt_tension_boundaries(inspection)
        if tensions is None:
            raise RuntimeError("Engaged state did not yield belt tension boundaries.")
        boundary_tensions = [tensions.primary_in, tensions.primary_out, tensions.secondary_in, tensions.secondary_out]
        row["belt_min_tension_N"] = min(float(x) for x in boundary_tensions)
        snap = contact.snapshot
        pfield = _wrap_field_metrics(
            snapshot=snap, unknowns=audit.unknowns, radius=snap.geometry.primary,
            wrap_angle=snap.geometry.primary_wrap_angle,
            lambda_value=contact.traction_utilization.primary_lambda,
            tension_in=tensions.primary_in, tension_out=tensions.primary_out,
        )
        sfield = _wrap_field_metrics(
            snapshot=snap, unknowns=audit.unknowns, radius=snap.geometry.secondary,
            wrap_angle=snap.geometry.secondary_wrap_angle,
            lambda_value=contact.traction_utilization.secondary_lambda,
            tension_in=tensions.secondary_in, tension_out=tensions.secondary_out,
        )
        row["primary_min_dnormal_dtheta_N_per_rad"] = pfield["min_dnormal_dtheta_N_per_rad"]
        row["secondary_min_dnormal_dtheta_N_per_rad"] = sfield["min_dnormal_dtheta_N_per_rad"]
        row["primary_field_normal_residual_N"] = pfield["normal_from_field_N"] - contact.normal_primary
        row["secondary_field_normal_residual_N"] = sfield["normal_from_field_N"] - contact.normal_secondary

        if mode.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
            row["low_ratio_seat_reaction_N"] = contact.low_ratio_seat_reaction
            row["fixed_shift_acceleration_m_s2"] = audit.unknowns.shift_acceleration
        elif mode.shift_constraint is CVTShiftConstraint.UPPER_STOP:
            row["upper_stop_reaction_N"] = contact.upper_stop_reaction
            row["fixed_shift_acceleration_m_s2"] = audit.unknowns.shift_acceleration
    else:
        deadzone = inspection.deadzone
        if deadzone is None:
            raise RuntimeError("Deadzone inspection did not reconstruct deadzone mechanics.")
        row["deadzone_secondary_lock_speed_residual_m_s"] = deadzone.belt_secondary_speed_residual
        row["deadzone_secondary_lock_acceleration_residual_m_s2"] = deadzone.belt_secondary_acceleration_residual
        if mode.shift_constraint is CVTShiftConstraint.LOWER_STOP:
            row["deadzone_lower_stop_reaction_N"] = deadzone.stop_reaction
            row["fixed_shift_acceleration_m_s2"] = deadzone.state_derivative.shift_acceleration
        margins = _deadzone_mechanism_margins(system, inspection)
        for key, value in margins:
            mechanism_rows.append({"case_id": sample.case_id, "time_s": sample.time, "key": key, "margin": value})
        row["mechanism_min_margin"] = finite_min(v for _, v in margins)
        row["mechanism_contacts_admissible"] = all(v >= 0.0 for _, v in margins)

    return row, equation_rows, mechanism_rows


def audit_sample_safe(system, sample):
    try:
        return inspect_sample(system, sample)
    except Exception as exc:
        row = {
            "case_id": sample.case_id, "time_s": sample.time,
            "sample_location": sample.sample_location,
            "inspection_error": f"{type(exc).__name__}: {exc}",
        }
        return row, [], []


def post_transition_rows(case_id: str, system, result):
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(result.transitions):
        next_mode = record.transition.next_mode
        base = {
            "case_id": case_id, "transition_index": index, "time_s": float(record.time),
            "fired_event_names": "|".join(record.fired_event_names),
            "transition_reason": record.transition.reason,
            "successor_exists": next_mode is not None,
        }
        if next_mode is None:
            rows.append({**base, "inspection_error": "terminal_no_successor"})
            continue
        sample = AuditSample(case_id, float(record.time), np.asarray(record.post_transition_state, dtype=float), next_mode, "post_transition_exact")
        row, _, _ = audit_sample_safe(system, sample)
        rows.append({**base, **row})
    return rows


def hard_row_failures(row: dict[str, Any], guards: dict) -> list[str]:
    if row.get("inspection_error"):
        return ["inspection_error"]
    failures: list[str] = []
    def finite(key):
        try:
            return math.isfinite(float(row.get(key, float("nan"))))
        except Exception:
            return False

    if row.get("engagement") == "engaged":
        required_finite = (
            "belt_length_residual_m", "closure_max_scaled_residual", "normal_primary_N", "normal_secondary_N",
            "belt_min_tension_N", "primary_min_dnormal_dtheta_N_per_rad", "secondary_min_dnormal_dtheta_N_per_rad",
            "primary_field_normal_residual_N", "secondary_field_normal_residual_N",
        )
        for key in required_finite:
            if not finite(key):
                failures.append(f"nonfinite_{key}")
        if finite("belt_length_residual_m") and abs(float(row["belt_length_residual_m"])) > guards["belt_length_residual_m"]:
            failures.append("belt_length")
        if finite("closure_max_scaled_residual") and abs(float(row["closure_max_scaled_residual"])) > guards["closure_scaled_equation_residual"]:
            failures.append("closure_scaled")
        try:
            if int(row.get("closure_rank", -1)) != 8:
                failures.append("closure_rank")
        except Exception:
            failures.append("closure_rank")
        if finite("normal_primary_N") and float(row["normal_primary_N"]) < -guards["negative_normal_tolerance_N"]:
            failures.append("primary_normal")
        if finite("normal_secondary_N") and float(row["normal_secondary_N"]) < -guards["negative_normal_tolerance_N"]:
            failures.append("secondary_normal")
        if finite("belt_min_tension_N") and float(row["belt_min_tension_N"]) < -guards["negative_tension_tolerance_N"]:
            failures.append("belt_tension")
        if finite("primary_min_dnormal_dtheta_N_per_rad") and float(row["primary_min_dnormal_dtheta_N_per_rad"]) < -guards["negative_distributed_normal_tolerance_N_per_rad"]:
            failures.append("primary_local_normal")
        if finite("secondary_min_dnormal_dtheta_N_per_rad") and float(row["secondary_min_dnormal_dtheta_N_per_rad"]) < -guards["negative_distributed_normal_tolerance_N_per_rad"]:
            failures.append("secondary_local_normal")
        if finite("primary_field_normal_residual_N") and abs(float(row["primary_field_normal_residual_N"])) > guards["field_normal_integral_residual_N"]:
            failures.append("primary_normal_integral")
        if finite("secondary_field_normal_residual_N") and abs(float(row["secondary_field_normal_residual_N"])) > guards["field_normal_integral_residual_N"]:
            failures.append("secondary_normal_integral")
        if not bool(row.get("mechanism_contacts_admissible", False)):
            failures.append("mechanism_contact")

        mode = str(row.get("contact_mode", ""))
        sticking = {
            "stick_stick": ("primary", "secondary"),
            "primary_slip_secondary_stick": ("secondary",),
            "primary_stick_secondary_slip": ("primary",),
            "both_slip": (),
        }.get(mode)
        slipping = {
            "stick_stick": (),
            "primary_slip_secondary_stick": ("primary",),
            "primary_stick_secondary_slip": ("secondary",),
            "both_slip": ("primary", "secondary"),
        }.get(mode)
        if sticking is None or slipping is None:
            failures.append("unknown_contact_mode")
            sticking, slipping = (), ()

        for p in sticking:
            margin_key = f"{p}_static_margin"
            if not finite(margin_key):
                failures.append(f"nonfinite_{p}_static_margin")
            elif float(row[margin_key]) < -guards["static_margin_negative_tolerance"]:
                failures.append(f"{p}_static_margin")
            if not finite(f"{p}_vrel_m_s") or abs(float(row[f"{p}_vrel_m_s"])) > guards["stick_velocity_drift_m_s"]:
                failures.append(f"{p}_stick_velocity")
            if not finite(f"{p}_arel_m_s2") or abs(float(row[f"{p}_arel_m_s2"])) > guards["stick_acceleration_residual_m_s2"]:
                failures.append(f"{p}_stick_acceleration")

        for p in slipping:
            power_key = f"{p}_slip_pair_power_W"
            if not finite(power_key):
                failures.append(f"nonfinite_{p}_slip_power")
            elif float(row[power_key]) > guards["positive_slip_pair_power_W"]:
                failures.append(f"{p}_slip_power")
            if not finite(f"{p}_vrel_m_s"):
                failures.append(f"nonfinite_{p}_slip_velocity")

        # At an exact zero-crossing terminal endpoint the old kinetic branch may
        # deliberately cease to match the direction inferred from acceleration.
        # The successor is audited independently as post_transition_exact.
        if row.get("sample_location") != "segment_end" and not bool(row.get("slip_direction_consistent", True)):
            failures.append("slip_direction")
    else:
        for key in ("deadzone_secondary_lock_speed_residual_m_s", "deadzone_secondary_lock_acceleration_residual_m_s2"):
            if not finite(key):
                failures.append(f"nonfinite_{key}")
        if finite("deadzone_secondary_lock_speed_residual_m_s") and abs(float(row["deadzone_secondary_lock_speed_residual_m_s"])) > guards["deadzone_secondary_lock_speed_m_s"]:
            failures.append("deadzone_lock_speed")
        if finite("deadzone_secondary_lock_acceleration_residual_m_s2") and abs(float(row["deadzone_secondary_lock_acceleration_residual_m_s2"])) > guards["deadzone_secondary_lock_acceleration_m_s2"]:
            failures.append("deadzone_lock_accel")
        if not bool(row.get("mechanism_contacts_admissible", False)):
            failures.append("mechanism_contact")

    constraint = row.get("shift_constraint")
    if constraint in ("lower_stop", "low_ratio_seat", "upper_stop"):
        if not finite("shift_speed_m_s") or abs(float(row["shift_speed_m_s"])) > guards["fixed_shift_speed_m_s"]:
            failures.append("fixed_shift_speed")
        if not finite("fixed_shift_acceleration_m_s2"):
            failures.append("nonfinite_fixed_shift_acceleration")
        elif abs(float(row["fixed_shift_acceleration_m_s2"])) > guards["fixed_shift_acceleration_m_s2"]:
            failures.append("fixed_shift_accel")
    reaction_key = {
        "lower_stop":"deadzone_lower_stop_reaction_N",
        "low_ratio_seat":"low_ratio_seat_reaction_N",
        "upper_stop":"upper_stop_reaction_N",
    }.get(constraint)
    if reaction_key:
        if not finite(reaction_key):
            failures.append("nonfinite_stop_reaction")
        elif float(row[reaction_key]) < -guards["negative_stop_reaction_tolerance_N"]:
            failures.append("negative_stop_reaction")
    return sorted(set(failures))


def mode_and_directions_match(mode, request: ContactRequest) -> bool:
    cvt_mode = mode.cvt
    if cvt_mode.engagement is not CVTEngagementState.ENGAGED or cvt_mode.shift_constraint is not CVTShiftConstraint.FREE:
        return False
    regime = cvt_mode.contact_regime
    if regime is None or regime.mode is not request.mode:
        return False
    if request.primary_vrel_sign != 0:
        expected = SlipDirection.BELT_LEADS_PULLEY if request.primary_vrel_sign > 0 else SlipDirection.PULLEY_LEADS_BELT
        if regime.primary_slip_direction is not expected: return False
    if request.secondary_vrel_sign != 0:
        expected = SlipDirection.BELT_LEADS_PULLEY if request.secondary_vrel_sign > 0 else SlipDirection.PULLEY_LEADS_BELT
        if regime.secondary_slip_direction is not expected: return False
    return True


def contact_requests() -> list[ContactRequest]:
    return [
        ContactRequest("stick_stick_forward", EngagedContactMode.STICK_STICK, 0, 0, +1),
        ContactRequest("stick_stick_reverse", EngagedContactMode.STICK_STICK, 0, 0, -1),
        ContactRequest("primary_slip_plus", EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK, +1, 0, +1),
        ContactRequest("primary_slip_minus", EngagedContactMode.PRIMARY_SLIP_SECONDARY_STICK, -1, 0, +1),
        ContactRequest("secondary_slip_plus", EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP, 0, +1, +1),
        ContactRequest("secondary_slip_minus", EngagedContactMode.PRIMARY_STICK_SECONDARY_SLIP, 0, -1, +1),
        ContactRequest("both_slip_pp", EngagedContactMode.BOTH_SLIP, +1, +1, +1),
        ContactRequest("both_slip_pm", EngagedContactMode.BOTH_SLIP, +1, -1, +1),
        ContactRequest("both_slip_mp", EngagedContactMode.BOTH_SLIP, -1, +1, +1),
        ContactRequest("both_slip_mm", EngagedContactMode.BOTH_SLIP, -1, -1, +1),
    ]


def candidate_cvt_state(model, *, shift_fraction: float, belt_speed: float, slip_speed: float,
                        primary_sign: int, secondary_sign: int, shift_speed: float = 0.0) -> CVTState:
    spec = model.geometry.spec
    shift = spec.deadzone_shift + shift_fraction * (spec.max_shift - spec.deadzone_shift)
    g = model.geometry.evaluate_engaged(shift)
    vp = primary_sign * slip_speed
    vs = secondary_sign * slip_speed
    # Contact requests use s_dot=0, so representative pulley speed equals shaft speed.
    omega_p = (belt_speed - vp) / g.primary.effective
    omega_s = (belt_speed - vs) / g.secondary.effective
    return CVTState(omega_p, omega_s, belt_speed, shift, shift_speed)


def integration_settings(block: dict) -> HybridIntegratorSettings:
    return HybridIntegratorSettings(
        relative_tolerance=float(block["relative_tolerance"]),
        absolute_tolerance=float(block["absolute_tolerance"]),
        method=str(block.get("method", "LSODA")),
        max_step=float(block["max_step"]),
        maximum_transitions=int(block.get("maximum_transitions", 100)),
        event_time_tolerance=float(block.get("event_time_tolerance", 1e-10)),
        retain_dense_output=True,
    )


def _attach_initial_diagnostics(attempt: dict[str, Any], row: dict[str, Any], mode: Any) -> None:
    """Retain enough physics from rejected candidates to diagnose coverage gaps."""
    regime = getattr(mode.cvt, "contact_regime", None)
    attempt.update({
        "observed_engagement": getattr(mode.cvt.engagement, "value", str(mode.cvt.engagement)),
        "observed_shift_constraint": getattr(mode.cvt.shift_constraint, "value", str(mode.cvt.shift_constraint)),
        "observed_contact_mode": (regime.mode.value if regime is not None else ""),
        "actual_primary_vrel_m_s": row.get("primary_vrel_m_s"),
        "actual_secondary_vrel_m_s": row.get("secondary_vrel_m_s"),
        "normal_primary_N": row.get("normal_primary_N"),
        "normal_secondary_N": row.get("normal_secondary_N"),
        "belt_min_tension_N": row.get("belt_min_tension_N"),
        "primary_min_dnormal_dtheta_N_per_rad": row.get("primary_min_dnormal_dtheta_N_per_rad"),
        "secondary_min_dnormal_dtheta_N_per_rad": row.get("secondary_min_dnormal_dtheta_N_per_rad"),
        "primary_static_margin": row.get("primary_static_margin"),
        "secondary_static_margin": row.get("secondary_static_margin"),
        "mechanism_min_margin": row.get("mechanism_min_margin"),
        "closure_max_scaled_residual": row.get("closure_max_scaled_residual"),
    })


def _contact_search_blocks(spec: dict) -> list[dict[str, Any]]:
    """Return the ordinary search followed by a small deterministic edge-domain fallback."""
    blocks = [spec["bench_search"]]
    fallback = spec.get("extended_contact_search")
    if fallback:
        merged = dict(spec["bench_search"])
        merged.update(fallback)
        blocks.append(merged)
    return blocks


def find_contact_case(decoded, request: ContactRequest, spec: dict, guards: dict) -> tuple[FoundCase | None, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    # Slip-direction coverage is independent of the sign of overall rotation.
    # Search the requested sign first, then the opposite sign if necessary.
    rotation_signs = (
        (request.rotation_sign,)
        if request.case_id in ("stick_stick_forward", "stick_stick_reverse")
        else (request.rotation_sign, -request.rotation_sign)
    )
    for search_stage, search in enumerate(_contact_search_blocks(spec), start=1):
        dyn_settings = integration_settings(search["integrator"])
        duration = float(search["contact_case_duration_s"])
        minimum_branch_time = float(search.get("minimum_branch_time_s", 1.0e-8))
        for rotation_sign in rotation_signs:
            for frac in search["shift_fractions"]:
                for speed_mag in search["belt_speeds_m_s"]:
                    belt_speed = rotation_sign * float(speed_mag)
                    for slip_speed in search["slip_speeds_m_s"]:
                        cvt = candidate_cvt_state(
                            decoded.plant, shift_fraction=float(frac), belt_speed=belt_speed,
                            slip_speed=float(slip_speed), primary_sign=request.primary_vrel_sign,
                            secondary_sign=request.secondary_vrel_sign,
                        )
                        for tp in search["primary_torques_Nm"]:
                            for ts in search["secondary_torques_Nm"]:
                                system = make_bench_system(
                                    decoded, primary_torque=tp, secondary_torque=ts,
                                    primary_inertia=search["primary_inertia_kg_m2"],
                                    secondary_inertia=search["secondary_inertia_kg_m2"],
                                )
                                state = full_state(system, cvt)
                                attempt = {
                                    "case_id": request.case_id,
                                    "search_stage": search_stage,
                                    "rotation_sign": rotation_sign,
                                    "shift_fraction": frac,
                                    "belt_speed_m_s": belt_speed,
                                    "slip_speed_m_s": slip_speed,
                                    "primary_torque_Nm": tp,
                                    "secondary_torque_Nm": ts,
                                }
                                try:
                                    mode = system.classify_initial_mode(state)
                                except Exception as exc:
                                    attempt.update({
                                        "accepted": False,
                                        "reason": f"classification:{type(exc).__name__}:{exc}",
                                    })
                                    attempts.append(attempt)
                                    continue

                                row, _, _ = audit_sample_safe(
                                    system,
                                    AuditSample(request.case_id, 0.0, state, mode, "initial_exact"),
                                )
                                _attach_initial_diagnostics(attempt, row, mode)

                                if not mode_and_directions_match(mode, request):
                                    attempt.update({
                                        "accepted": False,
                                        "reason": f"mode:{mode.cvt.contact_regime.mode.value if mode.cvt.contact_regime else 'none'}",
                                    })
                                    attempts.append(attempt)
                                    continue

                                failures = hard_row_failures(row, guards)
                                if failures:
                                    attempt.update({
                                        "accepted": False,
                                        "reason": "initial_invariant:" + "|".join(failures),
                                    })
                                    attempts.append(attempt)
                                    continue

                                try:
                                    trace = system.integrate_trace(
                                        time_span=(0.0, duration),
                                        initial_state=state,
                                        initial_mode=mode,
                                        settings=dyn_settings,
                                    )
                                except Exception as exc:
                                    attempt.update({
                                        "accepted": False,
                                        "reason": f"integration:{type(exc).__name__}:{exc}",
                                    })
                                    attempts.append(attempt)
                                    continue

                                first = trace.segments[0]
                                dwell = first.end_time - first.start_time
                                attempt["requested_mode_dwell_s"] = dwell
                                # A valid branch is not required to be dynamically long-lived.
                                # It must persist for a nonzero interval comfortably above the
                                # event-time numerical scale, then all successor states are audited.
                                if dwell < minimum_branch_time:
                                    attempt.update({"accepted": False, "reason": f"dwell:{dwell:.3e}"})
                                    attempts.append(attempt)
                                    continue

                                sample_rows = []
                                bad: list[str] = []
                                for sample in build_trace_samples(
                                    request.case_id, trace, float(search["audit_time_step_s"])
                                ):
                                    rr, _, _ = audit_sample_safe(system, sample)
                                    sample_rows.append(rr)
                                    bad.extend(hard_row_failures(rr, guards))
                                if bad:
                                    attempt.update({
                                        "accepted": False,
                                        "reason": "dynamic_invariant:" + "|".join(sorted(set(bad))),
                                    })
                                    attempts.append(attempt)
                                    continue
                                if not trace.completed:
                                    attempt.update({
                                        "accepted": False,
                                        "reason": "terminated:" + trace.termination_reason,
                                    })
                                    attempts.append(attempt)
                                    continue

                                attempt.update({"accepted": True, "reason": "accepted"})
                                attempts.append(attempt)
                                return FoundCase(
                                    request.case_id,
                                    system,
                                    state,
                                    mode,
                                    {
                                        **attempt,
                                        "requested_contact_mode": request.mode.value,
                                        "requested_primary_vrel_sign": request.primary_vrel_sign,
                                        "requested_secondary_vrel_sign": request.secondary_vrel_sign,
                                        "rotation_sign": rotation_sign,
                                    },
                                ), attempts
    return None, attempts


def contact_locked_engaged_state(
    system: ComposedCVTHybridSystem,
    *,
    shift: float,
    shift_speed: float,
    belt_speed: float,
) -> CVTState:
    """Construct an engaged state with both represented tangential contacts at zero v_rel.

    This uses the production representative-contact-speed definition, including
    secondary helical member motion when s_dot is nonzero.  The correction is
    linear in shaft speed, so two fixed-point corrections are ample and avoid
    embedding a test-only kinematic approximation.
    """
    g = system.cvt.model.geometry.evaluate_engaged(shift)
    omega_p = belt_speed / g.primary.effective
    omega_s = belt_speed / g.secondary.effective
    for _ in range(2):
        cvt = CVTState(omega_p, omega_s, belt_speed, shift, shift_speed)
        state = full_state(system, cvt)
        boundaries = system._shaft_boundaries(time=0.0, state=state)
        snapshot = system.cvt.model.snapshot_at_time(
            time=0.0,
            state=cvt,
            shaft_boundaries=boundaries,
            geometry_side="engaged",
        )
        vp = evaluate_contact_relative_speed(snapshot=snapshot, interface=ContactInterface.PRIMARY)
        vs = evaluate_contact_relative_speed(snapshot=snapshot, interface=ContactInterface.SECONDARY)
        omega_p += vp / g.primary.effective
        omega_s += vs / g.secondary.effective
    return CVTState(omega_p, omega_s, belt_speed, shift, shift_speed)


def find_free_shift_direction_case(decoded, *, case_id: str, direction: int, spec: dict, guards: dict) -> tuple[FoundCase | None, Any | None, list[dict[str, Any]]]:
    """Find an admissible interior engaged IC with prescribed sign of free shift speed."""
    search = spec["bench_search"]
    cfg = spec["free_shift_cases"]
    attempts: list[dict[str, Any]] = []
    settings = integration_settings(cfg["integrator"])
    for frac in cfg["shift_fractions"]:
        shift = (
            decoded.plant.geometry.spec.deadzone_shift
            + float(frac)
            * (decoded.plant.geometry.spec.max_shift - decoded.plant.geometry.spec.deadzone_shift)
        )
        for speed_mag in cfg["belt_speeds_m_s"]:
            vb = float(speed_mag)
            for sdot_mag in cfg["shift_speeds_m_s"]:
                sdot = float(direction) * float(sdot_mag)
                for tp in search["primary_torques_Nm"]:
                    for ts in search["secondary_torques_Nm"]:
                        system = make_bench_system(
                            decoded,
                            primary_torque=tp,
                            secondary_torque=ts,
                            primary_inertia=search["primary_inertia_kg_m2"],
                            secondary_inertia=search["secondary_inertia_kg_m2"],
                        )
                        cvt = contact_locked_engaged_state(
                            system,
                            shift=shift,
                            shift_speed=sdot,
                            belt_speed=vb,
                        )
                        st = full_state(system, cvt)
                        attempt = {
                            "case_id": case_id,
                            "shift_fraction": frac,
                            "belt_speed_m_s": vb,
                            "shift_speed_m_s": sdot,
                            "primary_torque_Nm": tp,
                            "secondary_torque_Nm": ts,
                        }
                        try:
                            mode = system.classify_initial_mode(st)
                        except Exception as exc:
                            attempt.update({"accepted": False, "reason": f"classification:{type(exc).__name__}:{exc}"})
                            attempts.append(attempt)
                            continue
                        rr, _, _ = audit_sample_safe(system, AuditSample(case_id, 0.0, st, mode, "initial_exact"))
                        _attach_initial_diagnostics(attempt, rr, mode)
                        if mode.cvt.engagement is not CVTEngagementState.ENGAGED or mode.cvt.shift_constraint is not CVTShiftConstraint.FREE:
                            attempt.update({"accepted": False, "reason": "not_engaged_free"})
                            attempts.append(attempt)
                            continue
                        bad = hard_row_failures(rr, guards)
                        if bad:
                            attempt.update({"accepted": False, "reason": "initial_invariant:" + "|".join(bad)})
                            attempts.append(attempt)
                            continue
                        try:
                            trace = system.integrate_trace(
                                time_span=(0.0, float(cfg["duration_s"])),
                                initial_state=st,
                                initial_mode=mode,
                                settings=settings,
                            )
                        except Exception as exc:
                            attempt.update({"accepted": False, "reason": f"integration:{type(exc).__name__}:{exc}"})
                            attempts.append(attempt)
                            continue
                        bad = []
                        for sample in build_trace_samples(case_id, trace, float(cfg["audit_time_step_s"])):
                            r, _, _ = audit_sample_safe(system, sample)
                            bad.extend(hard_row_failures(r, guards))
                        if bad or not trace.completed:
                            attempt.update({
                                "accepted": False,
                                "reason": (
                                    "dynamic_invariant:" + "|".join(sorted(set(bad)))
                                    if bad
                                    else "terminated:" + trace.termination_reason
                                ),
                            })
                            attempts.append(attempt)
                            continue
                        attempt.update({"accepted": True, "reason": "accepted"})
                        attempts.append(attempt)
                        return FoundCase(
                            case_id,
                            system,
                            st,
                            mode,
                            {**attempt, "shift_direction": "closing" if direction > 0 else "opening"},
                        ), trace, attempts
    return None, None, attempts


def run_found_case(found: FoundCase, spec: dict):
    search = spec["bench_search"]
    settings = integration_settings(search["integrator"])
    duration = float(search["contact_case_duration_s"])
    trace = found.system.integrate_trace(time_span=(0.0, duration), initial_state=found.initial_state,
                                         initial_mode=found.initial_mode, settings=settings)
    return trace


def static_rest_case(decoded, spec: dict) -> FoundCase:
    bench = spec["static_rest"]
    system = make_bench_system(decoded, primary_torque=0.0, secondary_torque=0.0,
                               primary_inertia=bench["primary_inertia_kg_m2"], secondary_inertia=bench["secondary_inertia_kg_m2"])
    s0 = system.cvt.operating_limits.lower_stop_shift
    state = full_state(system, CVTState(0.0, 0.0, 0.0, s0, 0.0))
    mode = system.classify_initial_mode(state)
    return FoundCase("static_rest_lower_stop", system, state, mode, {"zero_speed": True, "zero_external_torque": True})


def deadzone_free_case(decoded, spec: dict) -> FoundCase:
    bench = spec["static_rest"]
    system = make_bench_system(decoded, primary_torque=0.0, secondary_torque=0.0,
                               primary_inertia=bench["primary_inertia_kg_m2"], secondary_inertia=bench["secondary_inertia_kg_m2"])
    limits = system.cvt.operating_limits
    s = 0.5 * (limits.lower_stop_shift + limits.engagement_shift)
    g = decoded.plant.geometry.evaluate_deadzone(s)
    locked = decoded.plant.geometry.evaluate_deadzone(limits.engagement_shift)
    omega_s = 25.0
    vb = locked.secondary.effective * omega_s
    state = full_state(system, CVTState(50.0, omega_s, vb, s, 0.0))
    mode = system.classify_initial_mode(state)
    return FoundCase("deadzone_free_static_snapshot", system, state, mode, {"shift_m": s})


def find_boundary_case(decoded, *, case_id: str, target_event: str, side: str, spec: dict, guards: dict) -> tuple[FoundCase | None, Any | None, list[dict[str, Any]]]:
    cfg = spec["boundary_cases"]
    search = spec["bench_search"]
    attempts: list[dict[str, Any]] = []
    settings = integration_settings(cfg["integrator"])
    limits = decoded.system.cvt.operating_limits
    eps = float(cfg["distance_from_boundary_m"])
    duration = float(cfg["duration_s"])

    if side == "lower":
        speed_pairs = [
            (float(op), float(os))
            for op in cfg.get("lower_primary_speeds_rad_s", [0.0, cfg["deadzone_primary_speed_rad_s"]])
            for os in cfg.get("lower_secondary_speeds_rad_s", [0.0, cfg["deadzone_secondary_speed_rad_s"]])
        ]
    elif side == "engagement":
        speed_pairs = [(float(cfg["deadzone_primary_speed_rad_s"]), float(cfg["deadzone_secondary_speed_rad_s"]))]
    else:
        speed_pairs = [(float("nan"), float("nan"))]

    for shift_speed_mag in cfg["shift_speeds_m_s"]:
        sdot = float(shift_speed_mag) if side in ("engagement", "upper") else -float(shift_speed_mag)
        for omega_p_dead, omega_s_dead in speed_pairs:
            for tp in search["primary_torques_Nm"]:
                for ts in search["secondary_torques_Nm"]:
                    system = make_bench_system(
                        decoded,
                        primary_torque=tp,
                        secondary_torque=ts,
                        primary_inertia=search["primary_inertia_kg_m2"],
                        secondary_inertia=search["secondary_inertia_kg_m2"],
                    )
                    if side in ("lower", "engagement"):
                        shift = limits.lower_stop_shift + eps if side == "lower" else limits.engagement_shift - eps
                        locked = decoded.plant.geometry.evaluate_deadzone(limits.engagement_shift)
                        omega_s = omega_s_dead
                        vb = locked.secondary.effective * omega_s
                        omega_p = omega_p_dead
                        cvt = CVTState(omega_p, omega_s, vb, shift, sdot)
                    else:
                        shift = limits.engagement_shift + eps if side == "low_ratio" else limits.upper_stop_shift - eps
                        vb = float(cfg["engaged_belt_speed_m_s"])
                        cvt = contact_locked_engaged_state(
                            system,
                            shift=shift,
                            shift_speed=sdot,
                            belt_speed=vb,
                        )
                    state = full_state(system, cvt)
                    attempt = {
                        "case_id": case_id,
                        "primary_torque_Nm": tp,
                        "secondary_torque_Nm": ts,
                        "shift_speed_m_s": sdot,
                        "initial_primary_speed_rad_s": cvt.primary_angular_speed,
                        "initial_secondary_speed_rad_s": cvt.secondary_angular_speed,
                        "initial_belt_speed_m_s": cvt.belt_speed,
                    }
                    try:
                        mode = system.classify_initial_mode(state)
                    except Exception as exc:
                        attempt.update({"accepted": False, "reason": f"classification:{type(exc).__name__}:{exc}"})
                        attempts.append(attempt)
                        continue
                    rr, _, _ = audit_sample_safe(system, AuditSample(case_id, 0.0, state, mode, "initial_exact"))
                    _attach_initial_diagnostics(attempt, rr, mode)
                    initial_fail = hard_row_failures(rr, guards)
                    if initial_fail:
                        attempt.update({"accepted": False, "reason": "initial_invariant:" + "|".join(initial_fail)})
                        attempts.append(attempt)
                        continue
                    try:
                        trace = system.integrate_trace(
                            time_span=(0.0, duration),
                            initial_state=state,
                            initial_mode=mode,
                            settings=settings,
                        )
                    except Exception as exc:
                        attempt.update({"accepted": False, "reason": f"integration:{type(exc).__name__}:{exc}"})
                        attempts.append(attempt)
                        continue
                    events = [name for rec in trace.transitions for name in rec.fired_event_names]
                    if target_event not in events:
                        attempt.update({"accepted": False, "reason": "target_event_not_reached", "events": "|".join(events)})
                        attempts.append(attempt)
                        continue
                    if not trace.completed:
                        attempt.update({"accepted": False, "reason": "terminated_after_target:" + trace.termination_reason, "events": "|".join(events)})
                        attempts.append(attempt)
                        continue
                    bad = []
                    for sample in build_trace_samples(case_id, trace, float(cfg["audit_time_step_s"])):
                        r, _, _ = audit_sample_safe(system, sample)
                        bad.extend(hard_row_failures(r, guards))
                    if bad:
                        attempt.update({"accepted": False, "reason": "dynamic_invariant:" + "|".join(sorted(set(bad)))})
                        attempts.append(attempt)
                        continue
                    attempt.update({"accepted": True, "reason": "accepted", "events": "|".join(events)})
                    attempts.append(attempt)
                    found = FoundCase(case_id, system, state, mode, {**attempt, "target_event": target_event})
                    return found, trace, attempts
    return None, None, attempts


def geometry_domain_audit(decoded, spec: dict) -> list[dict[str, Any]]:
    model = decoded.plant
    gs = model.geometry.spec
    cfg = spec["geometry_sweep"]
    n = int(cfg["points"])
    rows: list[dict[str, Any]] = []
    # Deadzone: secondary/belt radius is locked; primary belt-contact radius tangent must be flat.
    if gs.deadzone_shift > 0.0:
        for s in np.linspace(0.0, gs.deadzone_shift, max(3, n//4)):
            g = model.geometry.evaluate_deadzone(float(s))
            rows.append({
                "region":"deadzone", "shift_m":float(s),
                "belt_length_residual_m":float("nan"),
                "primary_d_effective_ds":g.primary.d_effective_ds,
                "primary_d2_effective_ds2":g.primary.d2_effective_ds2,
                "secondary_d_effective_ds":g.secondary.d_effective_ds,
                "secondary_d2_effective_ds2":g.secondary.d2_effective_ds2,
                "primary_d1_fd_residual":float("nan"), "primary_d2_fd_residual":float("nan"),
                "secondary_d1_fd_residual":float("nan"), "secondary_d2_fd_residual":float("nan"),
                "finite_geometry": all(math.isfinite(float(x)) for x in (
                    g.primary.effective,g.secondary.effective,g.primary_wrap_angle,g.secondary_wrap_angle)),
                "positive_geometry": (g.primary.effective > 0.0 and g.secondary.effective > 0.0 and g.primary_wrap_angle > 0.0 and g.secondary_wrap_angle > 0.0),
            })
    for s in np.linspace(gs.deadzone_shift, gs.max_shift, n):
        g = model.geometry.evaluate_engaged(float(s))
        residual = belt_length_residual(
            belt_length=gs.belt_outer_length, center_distance=gs.center_distance,
            primary_outer_radius=g.primary.outer, secondary_outer_radius=g.secondary.outer,
        )
        h = min(float(cfg["finite_difference_step_m"]), 0.2 * (gs.max_shift - gs.deadzone_shift) / max(2,n-1))
        derivative_checks = {"primary_d1_fd_residual":float("nan"),"primary_d2_fd_residual":float("nan"),"secondary_d1_fd_residual":float("nan"),"secondary_d2_fd_residual":float("nan")}
        if s > gs.deadzone_shift + h and s < gs.max_shift - h:
            gm=model.geometry.evaluate_engaged(float(s-h)); gp=model.geometry.evaluate_engaged(float(s+h))
            p_d1=(gp.primary.effective-gm.primary.effective)/(2*h); s_d1=(gp.secondary.effective-gm.secondary.effective)/(2*h)
            p_d2=(gp.primary.effective-2*g.primary.effective+gm.primary.effective)/(h*h); s_d2=(gp.secondary.effective-2*g.secondary.effective+gm.secondary.effective)/(h*h)
            derivative_checks={
                "primary_d1_fd_residual":p_d1-g.primary.d_effective_ds,
                "primary_d2_fd_residual":p_d2-g.primary.d2_effective_ds2,
                "secondary_d1_fd_residual":s_d1-g.secondary.d_effective_ds,
                "secondary_d2_fd_residual":s_d2-g.secondary.d2_effective_ds2,
            }
        rows.append({
            "region":"engaged", "shift_m":float(s), "belt_length_residual_m":residual,
            "primary_d_effective_ds":g.primary.d_effective_ds,
            "primary_d2_effective_ds2":g.primary.d2_effective_ds2,
            "secondary_d_effective_ds":g.secondary.d_effective_ds,
            "secondary_d2_effective_ds2":g.secondary.d2_effective_ds2,
            **derivative_checks,
            "finite_geometry": all(math.isfinite(float(x)) for x in (
                g.primary.effective,g.secondary.effective,g.primary_wrap_angle,g.secondary_wrap_angle)),
            "positive_geometry": (g.primary.effective > 0.0 and g.secondary.effective > 0.0 and g.primary_wrap_angle > 0.0 and g.secondary_wrap_angle > 0.0),
        })
    return rows


def negative_controls(decoded, spec: dict) -> list[dict[str, Any]]:
    cfg = spec["negative_controls"]
    system = make_bench_system(decoded, primary_torque=0.0, secondary_torque=0.0,
                               primary_inertia=0.0, secondary_inertia=0.0)
    limits = system.cvt.operating_limits
    rows: list[dict[str, Any]] = []
    controls = [
        ("shift_below_lower_limit", CVTState(0,0,0,limits.lower_stop_shift-cfg["shift_violation_m"],0), True),
        ("shift_above_upper_limit", CVTState(0,0,0,limits.upper_stop_shift+cfg["shift_violation_m"],0), True),
    ]
    locked = decoded.plant.geometry.evaluate_deadzone(limits.engagement_shift)
    omega_s = 20.0
    broken = CVTState(50.0, omega_s, locked.secondary.effective*omega_s + cfg["deadzone_lock_violation_m_s"],
                      0.5*(limits.lower_stop_shift+limits.engagement_shift), 0.0)
    controls.append(("deadzone_secondary_lock_violation", broken, True))
    for name, cvt, should_reject in controls:
        rejected=False; error=""
        try:
            st=full_state(system,cvt); mode=system.classify_initial_mode(st)
            # Force an RHS evaluation as some constraints are intentionally checked there.
            system.rhs(0.0,st,mode)
        except Exception as exc:
            rejected=True; error=f"{type(exc).__name__}: {exc}"
        rows.append({"control":name,"should_reject":should_reject,"rejected":rejected,"pass":rejected==should_reject,"error":error})
    return rows


def classifier_boundary_controls(decoded, spec: dict) -> list[dict[str, Any]]:
    cfg=spec["classifier_controls"]
    search=spec["bench_search"]
    system=make_bench_system(decoded,primary_torque=0.0,secondary_torque=0.0,
                             primary_inertia=search["primary_inertia_kg_m2"],secondary_inertia=search["secondary_inertia_kg_m2"])
    limits=system.cvt.operating_limits
    locked=decoded.plant.geometry.evaluate_deadzone(limits.engagement_shift)
    omega_s=float(cfg["secondary_speed_rad_s"]); vb=locked.secondary.effective*omega_s
    rows=[]
    for name,sdot,expected in [
        ("engagement_opening_is_deadzone",-abs(cfg["shift_speed_m_s"]),"deadzone"),
        ("engagement_closing_is_engaged",+abs(cfg["shift_speed_m_s"]),"engaged"),
    ]:
        state=full_state(system,CVTState(cfg["primary_speed_rad_s"],omega_s,vb,limits.engagement_shift,sdot))
        try:
            mode=system.classify_initial_mode(state)
            observed=mode.cvt.engagement.value; err=""
        except Exception as exc:
            observed="error"; err=f"{type(exc).__name__}: {exc}"
        rows.append({"control":name,"expected":expected,"observed":observed,"pass":observed==expected,"error":err})
    return rows


def accumulate_case(case_id: str, system, trace, audit_step: float,
                    sample_rows, equation_rows, mechanism_rows, transition_rows):
    for sample in build_trace_samples(case_id, trace, audit_step):
        row, eq, mech = audit_sample_safe(system, sample)
        sample_rows.append(row); equation_rows.extend(eq); mechanism_rows.extend(mech)
    transition_rows.extend(post_transition_rows(case_id, system, trace))


def summarize_case(case_id: str, rows: list[dict[str, Any]], guards: dict) -> dict[str, Any]:
    mine=[r for r in rows if r.get("case_id")==case_id]
    failures=sorted({f for r in mine for f in hard_row_failures(r,guards)})
    modes=sorted({str(r.get("contact_mode")) for r in mine if r.get("contact_mode")})
    constraints=sorted({str(r.get("shift_constraint")) for r in mine if r.get("shift_constraint")})
    return {
        "case_id":case_id,"samples":len(mine),"status":"PASS" if not failures else "FAIL",
        "failures":"|".join(failures),"contact_modes":"|".join(modes),"shift_constraints":"|".join(constraints),
        "min_belt_tension_N":finite_min(r.get("belt_min_tension_N") for r in mine),
        "min_primary_local_normal_N_per_rad":finite_min(r.get("primary_min_dnormal_dtheta_N_per_rad") for r in mine),
        "min_secondary_local_normal_N_per_rad":finite_min(r.get("secondary_min_dnormal_dtheta_N_per_rad") for r in mine),
        "min_primary_normal_N":finite_min(r.get("normal_primary_N") for r in mine),
        "min_secondary_normal_N":finite_min(r.get("normal_secondary_N") for r in mine),
        "max_scaled_closure_residual":finite_max_abs(r.get("closure_max_scaled_residual") for r in mine),
    }


def plot_coverage(coverage_rows: list[dict[str, Any]]) -> None:
    labels=[r["requirement"] for r in coverage_rows]
    vals=[1 if r["covered"] else 0 for r in coverage_rows]
    fig,ax=plt.subplots(figsize=(10,max(5,0.34*len(labels))))
    y=np.arange(len(labels)); ax.barh(y,vals)
    ax.set_yticks(y,labels); ax.set_xlim(0,1.05); ax.set_xlabel("Covered (1=yes)"); ax.set_title("Mechanical invariant domain coverage")
    ax.invert_yaxis(); fig.tight_layout(); fig.savefig(ARTIFACTS/"01_coverage_matrix.png",dpi=180); plt.close(fig)


def plot_case_margins(case_rows: list[dict[str, Any]]) -> None:
    usable=[r for r in case_rows if math.isfinite(float(r.get("min_belt_tension_N",float("nan"))))]
    if not usable: return
    labels=[r["case_id"] for r in usable]; vals=[r["min_belt_tension_N"] for r in usable]
    fig,ax=plt.subplots(figsize=(11,max(5,0.32*len(labels))))
    y=np.arange(len(labels)); ax.barh(y,vals); ax.axvline(0.0,linestyle="--")
    ax.set_yticks(y,labels); ax.set_xlabel("Minimum recovered belt tension [N]"); ax.set_title("Minimum tensile margin by engaged test case")
    ax.invert_yaxis(); fig.tight_layout(); fig.savefig(ARTIFACTS/"02_minimum_belt_tension.png",dpi=180); plt.close(fig)


def build_coverage(found_ids: set[str], sample_rows: list[dict[str, Any]], transition_rows: list[dict[str, Any]],
                   static_ok: bool, negative_ok: bool, classifier_ok: bool,
                   free_shift_epsilon: float) -> list[dict[str, Any]]:
    observed_modes={r.get("contact_mode") for r in sample_rows if r.get("contact_mode")}
    observed_constraints={r.get("shift_constraint") for r in sample_rows if r.get("shift_constraint")}
    fired={name for r in transition_rows for name in str(r.get("fired_event_names","")).split("|") if name}
    requirements=[
        ("static_zero_speed_zero_torque_lower_stop",static_ok,"true rest equilibrium/support check"),
        ("deadzone_free",any(r.get("engagement")=="deadzone" and r.get("shift_constraint")=="free" for r in sample_rows),"deadzone reduced mechanics"),
        ("engaged_stick_stick","stick_stick" in observed_modes,"both contacts sticking"),
        ("engaged_primary_slip_secondary_stick","primary_slip_secondary_stick" in observed_modes,"mixed contact branch"),
        ("engaged_primary_stick_secondary_slip","primary_stick_secondary_slip" in observed_modes,"mixed contact branch"),
        ("engaged_both_slip","both_slip" in observed_modes,"both-slip branch"),
        ("both_slip_quadrant_pp","both_slip_pp" in found_ids,"vrel,p>0, vrel,s>0"),
        ("both_slip_quadrant_pm","both_slip_pm" in found_ids,"vrel,p>0, vrel,s<0"),
        ("both_slip_quadrant_mp","both_slip_mp" in found_ids,"vrel,p<0, vrel,s>0"),
        ("both_slip_quadrant_mm","both_slip_mm" in found_ids,"vrel,p<0, vrel,s<0"),
        ("primary_slip_both_directions",{"primary_slip_plus","primary_slip_minus"}.issubset(found_ids),"kinetic direction sign symmetry"),
        ("secondary_slip_both_directions",{"secondary_slip_plus","secondary_slip_minus"}.issubset(found_ids),"kinetic direction sign symmetry"),
        ("forward_and_reverse_rotation",{"stick_stick_forward","stick_stick_reverse"}.issubset(found_ids),"overall rotation sign"),
        (
            "free_shift_closing",
            any(
                r.get("engagement") == "engaged"
                and r.get("shift_constraint") == "free"
                and math.isfinite(float(r.get("shift_speed_m_s", float("nan"))))
                and float(r.get("shift_speed_m_s")) > free_shift_epsilon
                for r in sample_rows
            ),
            "observed engaged-free sdot > 0 in any audited case",
        ),
        (
            "free_shift_opening",
            any(
                r.get("engagement") == "engaged"
                and r.get("shift_constraint") == "free"
                and math.isfinite(float(r.get("shift_speed_m_s", float("nan"))))
                and float(r.get("shift_speed_m_s")) < -free_shift_epsilon
                for r in sample_rows
            ),
            "observed engaged-free sdot < 0 in any audited case",
        ),
        ("low_ratio_seat","low_ratio_seat" in observed_constraints,"engaged unilateral low-ratio support"),
        ("upper_stop","upper_stop" in observed_constraints,"engaged upper travel stop"),
        ("deadzone_lower_stop","lower_stop" in observed_constraints,"deadzone lower travel stop"),
        ("engagement_transition","cvt:engagement_reached" in fired,"deadzone -> engaged"),
        ("low_ratio_arrival","cvt:low_ratio_seat_reached" in fired,"engaged free -> low-ratio seat"),
        ("upper_stop_arrival","cvt:upper_stop_reached" in fired,"engaged free -> upper stop"),
        ("lower_stop_arrival","cvt:lower_stop_reached" in fired,"deadzone free -> lower stop"),
        ("negative_controls",negative_ok,"invalid state classes rejected"),
        ("engagement_side_classifier",classifier_ok,"opening/closing one-sided engagement classification"),
        ("nominal_baja_reference","nominal_baja_reference" in found_ids,"realistic 10 s trajectory"),
    ]
    return [{"requirement":k,"covered":bool(v),"evidence":e} for k,v,e in requirements]


def main() -> int:
    started=time.time(); verify_environment(); spec=load_json(SPEC_FILE); guards=spec["review_guards"]
    decoded, base_path, resolved_doc = load_frozen_reference(spec)
    if ARTIFACTS.exists(): shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)
    write_json(ARTIFACTS/"resolved_nominal_simulation_case.json",resolved_doc)

    sample_rows=[]; equation_rows=[]; mechanism_rows=[]; transition_rows=[]; attempts=[]; case_meta=[]; found_ids=set()

    # 1) Geometry domain.
    geometry_rows=geometry_domain_audit(decoded,spec); write_rows(ARTIFACTS/"geometry_domain_audit.csv",geometry_rows)

    # 2) True static rest and deadzone-free snapshot.
    static=static_rest_case(decoded,spec); found_ids.add(static.case_id); case_meta.append({"case_id":static.case_id,**static.metadata})
    static_cfg=spec["static_rest"]
    static_trace=static.system.integrate_trace(time_span=(0.0,float(static_cfg["duration_s"])), initial_state=static.initial_state, initial_mode=static.initial_mode, settings=integration_settings(static_cfg["integrator"]))
    accumulate_case(static.case_id,static.system,static_trace,float(static_cfg["audit_time_step_s"]),sample_rows,equation_rows,mechanism_rows,transition_rows)
    static_final=np.asarray(static_trace.final_state,dtype=float)
    static_drift=float(np.max(np.abs(static_final-static.initial_state)))
    case_meta[-1].update({"completed":static_trace.completed,"max_state_drift":static_drift})
    sr=next(r for r in sample_rows if r.get("case_id")==static.case_id)
    dead=deadzone_free_case(decoded,spec); found_ids.add(dead.case_id); case_meta.append({"case_id":dead.case_id,**dead.metadata})
    dr,eq,mech=audit_sample_safe(dead.system,AuditSample(dead.case_id,0.0,dead.initial_state,dead.initial_mode,"initial_exact")); sample_rows.append(dr); equation_rows+=eq; mechanism_rows+=mech

    # 3) Deliberately populate contact modes and slip quadrants.
    found_contact: dict[str,FoundCase]={}
    for request in contact_requests():
        print(f"Searching admissible IC: {request.case_id}")
        found, tried=find_contact_case(decoded,request,spec,guards); attempts.extend(tried)
        if found is None:
            case_meta.append({"case_id":request.case_id,"status":"MISSING","requested_contact_mode":request.mode.value})
            continue
        found_contact[request.case_id]=found; found_ids.add(request.case_id); case_meta.append({"case_id":request.case_id,"status":"FOUND",**found.metadata})
        trace=run_found_case(found,spec)
        accumulate_case(found.case_id,found.system,trace,float(spec["bench_search"]["audit_time_step_s"]),sample_rows,equation_rows,mechanism_rows,transition_rows)

    # 4) Interior free-shift motion in both coordinate directions.
    for cid,direction in (("free_shift_closing",+1),("free_shift_opening",-1)):
        print(f"Searching free-shift case: {cid}")
        found,trace,tried=find_free_shift_direction_case(decoded,case_id=cid,direction=direction,spec=spec,guards=guards); attempts.extend(tried)
        if found is None:
            case_meta.append({"case_id":cid,"status":"MISSING","direction":direction})
            continue
        found_ids.add(cid); case_meta.append({"case_id":cid,"status":"FOUND",**found.metadata})
        accumulate_case(cid,found.system,trace,float(spec["free_shift_cases"]["audit_time_step_s"]),sample_rows,equation_rows,mechanism_rows,transition_rows)

    # 5) Directed structural-boundary arrivals.
    boundary_specs=[
        ("boundary_lower_stop_arrival","cvt:lower_stop_reached","lower"),
        ("boundary_engagement_arrival","cvt:engagement_reached","engagement"),
        ("boundary_low_ratio_arrival","cvt:low_ratio_seat_reached","low_ratio"),
        ("boundary_upper_stop_arrival","cvt:upper_stop_reached","upper"),
    ]
    for cid,event,side in boundary_specs:
        print(f"Searching boundary case: {cid}")
        found,trace,tried=find_boundary_case(decoded,case_id=cid,target_event=event,side=side,spec=spec,guards=guards); attempts.extend(tried)
        if found is None:
            case_meta.append({"case_id":cid,"status":"MISSING","target_event":event}); continue
        found_ids.add(cid); case_meta.append({"case_id":cid,"status":"FOUND",**found.metadata})
        accumulate_case(cid,found.system,trace,float(spec["boundary_cases"]["audit_time_step_s"]),sample_rows,equation_rows,mechanism_rows,transition_rows)

    # 6) Frozen realistic nominal trajectory.
    nominal_result=decoded.system.integrate_trace(
        time_span=tuple(spec["nominal_run"]["time_span_s"]), initial_state=decoded.initial_state,
        initial_mode=decoded.initial_mode, settings=integration_settings(spec["nominal_run"]["integrator"]),
    )
    nominal_id="nominal_baja_reference"; found_ids.add(nominal_id); case_meta.append({"case_id":nominal_id,"status":"FOUND","completed":nominal_result.completed,"termination_reason":nominal_result.termination_reason})
    accumulate_case(nominal_id,decoded.system,nominal_result,float(spec["nominal_run"]["audit_time_step_s"]),sample_rows,equation_rows,mechanism_rows,transition_rows)

    # 7) Invalid-state and one-sided classification controls.
    neg=negative_controls(decoded,spec); cls=classifier_boundary_controls(decoded,spec)
    write_rows(ARTIFACTS/"negative_controls.csv",neg); write_rows(ARTIFACTS/"classifier_controls.csv",cls)

    write_rows(ARTIFACTS/"sample_audit.csv",sample_rows)
    write_rows(ARTIFACTS/"closure_equation_residuals.csv",equation_rows)
    write_rows(ARTIFACTS/"mechanism_contact_margins.csv",mechanism_rows)
    write_rows(ARTIFACTS/"post_transition_audit.csv",transition_rows)
    write_rows(ARTIFACTS/"candidate_search_log.csv",attempts)
    write_rows(ARTIFACTS/"case_definitions.csv",case_meta)

    case_ids=sorted({str(r.get("case_id")) for r in sample_rows if r.get("case_id")})
    case_rows=[summarize_case(cid,sample_rows,guards) for cid in case_ids]
    write_rows(ARTIFACTS/"case_summary.csv",case_rows)

    static_fail=[f for r in sample_rows if r.get("case_id")==static.case_id for f in hard_row_failures(r,guards)]
    static_ok=(not static_fail and sr.get("shift_constraint")=="lower_stop" and static_trace.completed and static_drift <= guards["static_rest_state_drift"] )
    negative_ok=all(bool(r["pass"]) for r in neg); classifier_ok=all(bool(r["pass"]) for r in cls)
    coverage=build_coverage(
        found_ids, sample_rows, transition_rows, static_ok, negative_ok, classifier_ok,
        float(spec.get("coverage_speed_epsilon_m_s", 1.0e-6)),
    )
    write_rows(ARTIFACTS/"coverage_matrix.csv",coverage)

    geometry_fail = any((not bool(r["finite_geometry"])) or (not bool(r.get("positive_geometry",False))) for r in geometry_rows)
    geometry_resid = finite_max_abs(r.get("belt_length_residual_m") for r in geometry_rows)
    if math.isfinite(geometry_resid) and geometry_resid > guards["belt_length_residual_m"]: geometry_fail=True
    deadzone_derivative_max=finite_max_abs(
        value for r in geometry_rows if r.get("region")=="deadzone"
        for value in (r.get("primary_d_effective_ds"),r.get("primary_d2_effective_ds2"),r.get("secondary_d_effective_ds"),r.get("secondary_d2_effective_ds2"))
    )
    geometry_d1_fd=finite_max_abs(r.get(k) for r in geometry_rows for k in ("primary_d1_fd_residual","secondary_d1_fd_residual"))
    geometry_d2_fd=finite_max_abs(r.get(k) for r in geometry_rows for k in ("primary_d2_fd_residual","secondary_d2_fd_residual"))
    if math.isfinite(deadzone_derivative_max) and deadzone_derivative_max > guards["deadzone_radius_derivative_abs"]: geometry_fail=True
    if math.isfinite(geometry_d1_fd) and geometry_d1_fd > guards["geometry_first_derivative_fd_residual"]: geometry_fail=True
    if math.isfinite(geometry_d2_fd) and geometry_d2_fd > guards["geometry_second_derivative_fd_residual_per_m"]: geometry_fail=True
    sample_failures=[{"case_id":r.get("case_id"),"time_s":r.get("time_s"),"failures":"|".join(hard_row_failures(r,guards))} for r in sample_rows if hard_row_failures(r,guards)]
    # Exact post-transition inspection is a hard criterion. terminal_no_successor is allowed only when integration itself intentionally terminated;
    # ordinary successful cases should have no such row.
    post_fail=[]
    for r in transition_rows:
        if r.get("inspection_error") and r.get("inspection_error")!="terminal_no_successor":
            post_fail.append({**r,"post_failures":"inspection_error"})
            continue
        if r.get("successor_exists"):
            failures=hard_row_failures(r,guards)
            if failures:
                post_fail.append({**r,"post_failures":"|".join(failures)})
    case_fail=any(r["status"]=="FAIL" for r in case_rows)
    missing=[r["requirement"] for r in coverage if not r["covered"]]
    hard_fail=(geometry_fail or bool(sample_failures) or bool(post_fail) or case_fail
               or not negative_ok or not classifier_ok or not nominal_result.completed
               or not static_trace.completed or static_drift > guards["static_rest_state_drift"])
    overall="FAIL" if hard_fail else "REVIEW" if missing else "PASS"

    summary={
        "study":"Mechanical invariants — operating-domain audit",
        "cinder_version":cinder.__version__, "overall_status":overall,
        "elapsed_s":time.time()-started, "base_document":str(base_path), "base_sha256":sha256(base_path),
        "geometry_points":len(geometry_rows), "audited_samples":len(sample_rows), "transitions":len(transition_rows),
        "candidate_attempts":len(attempts), "found_case_ids":sorted(found_ids),
        "missing_coverage":missing, "sample_failure_count":len(sample_failures), "post_transition_failure_count":len(post_fail),
        "max_abs_belt_length_residual_m":geometry_resid,
        "deadzone_max_abs_radius_derivative":deadzone_derivative_max,
        "engaged_max_first_derivative_fd_residual":geometry_d1_fd,
        "engaged_max_second_derivative_fd_residual_per_m":geometry_d2_fd,
        "static_rest_max_state_drift":static_drift,
        "min_belt_tension_N":finite_min(r.get("belt_min_tension_N") for r in sample_rows),
        "min_primary_distributed_normal_N_per_rad":finite_min(r.get("primary_min_dnormal_dtheta_N_per_rad") for r in sample_rows),
        "min_secondary_distributed_normal_N_per_rad":finite_min(r.get("secondary_min_dnormal_dtheta_N_per_rad") for r in sample_rows),
        "min_primary_normal_N":finite_min(r.get("normal_primary_N") for r in sample_rows),
        "min_secondary_normal_N":finite_min(r.get("normal_secondary_N") for r in sample_rows),
        "max_scaled_closure_residual":finite_max_abs(r.get("closure_max_scaled_residual") for r in sample_rows),
        "all_closure_ranks_eight":all(int(r.get("closure_rank",8))==8 for r in sample_rows if r.get("engagement")=="engaged" and not r.get("inspection_error")),
        "negative_controls_pass":negative_ok, "classifier_controls_pass":classifier_ok,
        "interpretation": (
            "PASS means all required deterministic coverage classes were found and every audited accepted state satisfied the configured numerical guards. "
            "It is broad operating-domain evidence, not a mathematical proof over the continuum of all admissible initial states. REVIEW means a requested coverage class was not found without a hard invariant violation."
        ),
    }
    write_json(ARTIFACTS/"summary.json",summary,allow_nan=True)
    write_rows(ARTIFACTS/"sample_failures.csv",sample_failures)
    plot_coverage(coverage); plot_case_margins(case_rows)

    md=[
        "# Mechanical invariants — operating-domain audit", "", f"**Overall status: {overall}**", "",
        f"- CINDER: `{cinder.__version__}`", f"- Audited samples: {len(sample_rows)}", f"- Hybrid transitions audited: {len(transition_rows)}",
        f"- Deterministic IC/search attempts: {len(attempts)}", f"- Geometry-domain samples: {len(geometry_rows)}",
        f"- Missing coverage: {', '.join(missing) if missing else 'none'}", f"- Hard sample failures: {len(sample_failures)}", "",
        "## Headline extrema", "",
        f"- Minimum recovered belt tension: `{summary['min_belt_tension_N']:.9g} N`",
        f"- Minimum primary distributed normal loading: `{summary['min_primary_distributed_normal_N_per_rad']:.9g} N/rad`",
        f"- Minimum secondary distributed normal loading: `{summary['min_secondary_distributed_normal_N_per_rad']:.9g} N/rad`",
        f"- Minimum integrated primary normal resultant: `{summary['min_primary_normal_N']:.9g} N`",
        f"- Minimum integrated secondary normal resultant: `{summary['min_secondary_normal_N']:.9g} N`",
        f"- Maximum row-scaled 8x8 residual: `{summary['max_scaled_closure_residual']:.9g}`", "",
        "## Interpretation", "",
        summary["interpretation"], "",
        "See `coverage_matrix.csv`, `case_summary.csv`, `sample_audit.csv`, `post_transition_audit.csv`, and `candidate_search_log.csv` before treating this study as closed.",
    ]
    (ARTIFACTS/"summary.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    print(f"{overall}: mechanical invariant domain audit")
    return 0 if overall=="PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
