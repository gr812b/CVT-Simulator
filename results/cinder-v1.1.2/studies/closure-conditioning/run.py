"""Map CINDER v1.1.2 8x8 closure conditioning and 2x2 stick-root geometry."""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace
import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, SymLogNorm, TwoSlopeNorm, ListedColormap
from matplotlib.patches import Rectangle
import numpy as np

import cinder
from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)
from cinder.execution.hybrid import integrate_hybrid
from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
from cinder.execution.hybrid.cvt_regime import (
    CVTEngagementState,
    CVTShiftConstraint,
)
from cinder.model.cvt.contact import (
    ContactInterface,
    ContactTractionUtilization,
    EngagedContactMode,
    evaluate_contact_relative_speed,
)
from cinder.model.cvt.dynamics.engaged_contact import EngagedContactClosure, LambdaSearchBounds
from cinder.model.cvt.dynamics.equation_context import TrialEquationContext
from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint
from cinder.model.system import CVTState
from cinder.model.boundaries.shaft import FixedShaftBoundary
from cinder.hosts import NoHost
from cinder.results.fields import recover_belt_tension_boundaries
from cinder.results.inspection import inspect_cvt_state

from conditioning_math import finite_difference_jacobian
from case_library import load_case_library, search_named_stick_case

HERE = Path(__file__).resolve().parent
RELEASE_ROOT = HERE.parents[1]
VERIFY = RELEASE_ROOT / "verify_environment.py"
SPEC_FILE = HERE / "study.json"
CASE_LIBRARY_FILE = RELEASE_ROOT / "defaults" / "verification_operating_cases.json"
ARTIFACTS = HERE / "artifacts"
EXPECTED_CINDER_VERSION = "1.1.2"


@dataclass(frozen=True)
class FrozenSample:
    time: float
    full_state: np.ndarray
    composed_mode: Any
    cvt_state: CVTState


@dataclass(frozen=True)
class ReferenceRun:
    name: str
    decoded: Any
    result: Any
    samples: tuple[FrozenSample, ...]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use reduced map and multi-start resolution for a fast structural preview.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any, *, allow_nan: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, allow_nan=allow_nan) + "\n",
        encoding="utf-8",
    )


def write_rows(path: Path, rows: list[dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields, seen = [], set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def verify_environment():
    subprocess.run([sys.executable, str(VERIFY)], check=True)
    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise RuntimeError(
            f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__} "
            f"at {Path(cinder.__file__).resolve()}."
        )


def validate_and_decode(document):
    report = validate_simulation_case_document(document)
    if not report.is_valid:
        for finding in report.findings:
            print(
                f"[{finding.severity}] "
                f"{finding.document_path or '/'}: {finding.message}"
            )
        raise RuntimeError("Resolved conditioning-study input failed validation.")
    return decode_simulation_case_document(document)


def uniform_times(start, end, step):
    if end <= start:
        return np.asarray([start], dtype=float)
    values = start + step * np.arange(int(math.floor((end - start) / step)) + 1)
    if end - values[-1] > 1e-12:
        values = np.append(values, end)
    else:
        values[-1] = end
    return values


def build_reference(spec, run_name: str) -> ReferenceRun:
    base = (HERE / spec["base_document"]).resolve()
    if not base.is_file():
        raise FileNotFoundError(
            f"Frozen default is missing: {base}. "
            "This study intentionally depends only on the release defaults folder."
        )
    document = copy.deepcopy(load_json(base))
    cfg = spec["reference_runs"][run_name]
    document["scenario"]["time_span_s"] = list(cfg["time_span_s"])
    for key, value in cfg["integrator"].items():
        document["execution"]["integrator"][key] = value
    document["execution"]["integrator"]["retain_dense_output"] = True

    if "road_grade_segments" in cfg:
        document["shaft_boundaries"]["secondary"]["road_profile"] = {
            "kind": "piecewise_constant_grade",
            "segments": [
                {
                    "start_distance_m": float(row["start_distance_m"]),
                    "grade_angle_rad": math.radians(float(row["grade_angle_deg"])),
                }
                for row in cfg["road_grade_segments"]
            ],
        }

    decoded = validate_and_decode(document)
    result = integrate_hybrid(
        system=decoded.system,
        time_span=decoded.time_span,
        initial_state=decoded.initial_state,
        initial_mode=decoded.initial_mode,
        settings=decoded.integrator_settings,
    )

    samples = []
    step = float(cfg["sample_step_s"])
    for segment in result.segments:
        times = uniform_times(segment.start_time, segment.end_time, step)
        states = (
            segment.dense_state_at(times)
            if segment.has_dense_output
            else segment.state
        )
        if not segment.has_dense_output:
            times = segment.time
        for j, t in enumerate(times):
            full = np.asarray(states[:, j], dtype=float)
            cvt = CVTState.from_vector(decoded.system.layout.view(full, "cvt"))
            samples.append(
                FrozenSample(
                    time=float(t),
                    full_state=full,
                    composed_mode=segment.mode,
                    cvt_state=cvt,
                )
            )
    return ReferenceRun(
        name=run_name,
        decoded=decoded,
        result=result,
        samples=tuple(samples),
    )


def reconstruct(ref: ReferenceRun, sample: FrozenSample, *, closure_audit: bool):
    boundaries = ref.decoded.system._shaft_boundaries(
        time=sample.time,
        state=sample.full_state,
    )
    return inspect_cvt_state(
        system=ref.decoded.system.cvt,
        time=sample.time,
        vector=ref.decoded.system.layout.view(sample.full_state, "cvt"),
        mode=sample.composed_mode.cvt,
        shaft_boundaries=boundaries,
        include_closure_audit=closure_audit,
    )


def is_stick_stick(sample: FrozenSample) -> bool:
    mode = sample.composed_mode.cvt
    return (
        mode.engagement is CVTEngagementState.ENGAGED
        and mode.contact_regime is not None
        and mode.contact_regime.mode is EngagedContactMode.STICK_STICK
    )


def shift_fraction(ref: ReferenceRun, sample: FrozenSample) -> float:
    spec = ref.decoded.system.cvt.model.geometry.spec
    span = spec.max_shift - spec.deadzone_shift
    return (sample.cvt_state.shift_position - spec.deadzone_shift) / span


def select_nominal_states(launch: ReferenceRun):
    candidates = [s for s in launch.samples if is_stick_stick(s)]
    selected = []
    low = [s for s in candidates if s.composed_mode.cvt.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT]
    if low:
        selected.append(("low_ratio_seat", launch, max(low, key=lambda s: s.time)))
    free = [s for s in candidates if s.composed_mode.cvt.shift_constraint is CVTShiftConstraint.FREE]
    if free:
        selected.append(("mid_shift", launch, min(free, key=lambda s: abs(shift_fraction(launch, s) - 0.50))))
        late = min(free, key=lambda s: abs(shift_fraction(launch, s) - 0.85))
        selected.append(("late_shift", launch, late))
    upper = [s for s in candidates if s.composed_mode.cvt.shift_constraint is CVTShiftConstraint.UPPER_STOP]
    if upper:
        selected.append(("upper_stop", launch, upper[len(upper)//2]))
    out, seen = [], set()
    for label, ref, sample in selected:
        key = (ref.name, round(sample.time, 12))
        if key not in seen:
            seen.add(key)
            out.append((label, ref, sample))
    return out


def searched_case_as_reference(found):
    decoded_like = SimpleNamespace(system=found.system, plant=found.system.cvt.model)
    sample = FrozenSample(
        time=0.0,
        full_state=np.asarray(found.full_state, dtype=float),
        composed_mode=found.mode,
        cvt_state=found.cvt_state,
    )
    return ReferenceRun(name=found.case_id, decoded=decoded_like, result=None, samples=(sample,)), sample


def build_controlled_states(base_decoded, library: dict):
    selected = []
    search_rows = []
    recipes = list(library.get("stick_cases", [])) + list(library.get("free_shift_cases", []))
    for recipe in recipes:
        print(f"Searching shared operating case: {recipe['id']}")
        found, attempts = search_named_stick_case(base_decoded, library, recipe)
        for row in attempts:
            row = dict(row)
            row["case_id"] = recipe["id"]
            search_rows.append(row)
        if found is None:
            print(f"  unavailable: {recipe['id']}")
            continue
        ref, sample = searched_case_as_reference(found)
        selected.append((found.case_id, ref, sample))
        print(
            f"  accepted at shift={1000*found.cvt_state.shift_position:.3f} mm, "
            f"sdot={1000*found.cvt_state.shift_speed:.3f} mm/s, "
            f"Tp={found.metadata['primary_torque_Nm']:.3g} Nm, "
            f"Ts={found.metadata['secondary_torque_Nm']:.3g} Nm"
        )
    return selected, search_rows


def engaged_constraint(sample: FrozenSample):
    value = sample.composed_mode.cvt.shift_constraint
    if value is CVTShiftConstraint.FREE:
        return EngagedShiftConstraint.FREE
    if value is CVTShiftConstraint.LOW_RATIO_SEAT:
        return EngagedShiftConstraint.LOW_RATIO_SEAT
    if value is CVTShiftConstraint.UPPER_STOP:
        return EngagedShiftConstraint.UPPER_STOP
    raise ValueError(value)


def domain_bounds(ref: ReferenceRun, domain: str):
    law = ref.decoded.system.cvt.traction_law
    p = law.primary_static_interval
    s = law.secondary_static_interval
    if domain == "physical":
        return p.lower, p.upper, s.lower, s.upper
    physical = max(abs(p.lower), abs(p.upper), abs(s.lower), abs(s.upper))
    if domain == "expanded":
        half = max(2.5, 4.0 * physical)
        return -half, half, -half, half
    if domain == "broad":
        return -10.0, 10.0, -10.0, 10.0
    raise ValueError(domain)


def reconstructed_root_jacobian(ref, sample, lambda_p: float, lambda_s: float, step: float = 1.0e-5):
    inspection = reconstruct(ref, sample, closure_audit=False)
    contact = inspection.contact
    if contact is None:
        raise RuntimeError("Root Jacobian reconstruction requires engaged contact.")
    closure = EngagedContactClosure(snapshot=contact.snapshot, shift_constraint=engaged_constraint(sample))

    def residual(lp, ls):
        trial = closure.evaluate_trial(
            traction_utilization=ContactTractionUtilization(primary_lambda=float(lp), secondary_lambda=float(ls)),
            maximum_closure_condition_number=None,
            capture_diagnostics=False,
        )
        return np.asarray([
            trial.relative_motion.primary_relative_acceleration,
            trial.relative_motion.secondary_relative_acceleration,
        ], dtype=float)

    rp = residual(lambda_p + step, lambda_s)
    rm = residual(lambda_p - step, lambda_s)
    sp = residual(lambda_p, lambda_s + step)
    sm = residual(lambda_p, lambda_s - step)
    J = np.column_stack(((rp - rm) / (2.0 * step), (sp - sm) / (2.0 * step)))
    singular = np.linalg.svd(J, compute_uv=False)
    return J, float(singular[-1]), float(singular[0]), float(singular[0] / singular[-1]), float(np.linalg.det(J))


ROOT_JACOBIAN_STEPS = (1.0e-2, 3.0e-3, 1.0e-3, 3.0e-4, 1.0e-4, 3.0e-5, 1.0e-5, 3.0e-6, 1.0e-6, 3.0e-7)


def root_jacobian_step_rows(label, ref, sample):
    """Return a controlled finite-difference convergence sweep for the physical J_R.

    Important: ``EngagedContactSolveResult.jacobian`` is intentionally *not* used
    as a reference value here.  In production it is solver working state: a
    terminal least-squares Jacobian on a fresh solve, or a Broyden-updated
    continuation Jacobian after an accepted continuation step.  That object is
    useful to the nonlinear solver, but it is path-dependent and is not the
    canonical derivative of the frozen residual map at the reported root.

    Closure conditioning therefore defines J_R directly as the derivative of
    [R_p, R_s] with respect to [lambda_p, lambda_s] at the frozen state/root and
    verifies that derivative by a central-difference step sweep.
    """
    inspection = reconstruct(ref, sample, closure_audit=False)
    contact = inspection.contact
    if contact is None:
        return []
    u = contact.traction_utilization
    rows = []
    for step in ROOT_JACOBIAN_STEPS:
        try:
            J, smin, smax, kappa, det = reconstructed_root_jacobian(
                ref, sample, u.primary_lambda, u.secondary_lambda, step=step
            )
            error = ""
        except Exception as exc:
            smin = smax = kappa = det = float("nan")
            J = np.full((2, 2), np.nan)
            error = f"{type(exc).__name__}: {exc}"
        rows.append({
            "state": label,
            "step": float(step),
            "lambda_p": float(u.primary_lambda),
            "lambda_s": float(u.secondary_lambda),
            "J00": float(J[0,0]), "J01": float(J[0,1]),
            "J10": float(J[1,0]), "J11": float(J[1,1]),
            "sigma_min": float(smin), "sigma_max": float(smax),
            "kappa": float(kappa), "determinant": float(det),
            "error": error,
        })
    return rows


def jacobian_convergence_rows(step_rows):
    """Summarize whether the canonical 1e-5 Jacobian lies on a stable plateau."""
    by_state = {}
    for row in step_rows:
        by_state.setdefault(row["state"], []).append(row)
    out=[]
    canonical_step=1.0e-5
    # Avoid the very coarsest truncation-error points and the very smallest
    # roundoff-sensitive endpoint.  This window is deliberately much wider
    # than needed for the observed v1.1.2 states.
    stable_lower=1.0e-6
    stable_upper=3.0e-4
    for state, rows in sorted(by_state.items()):
        finite=[r for r in rows if not r.get("error") and math.isfinite(float(r["kappa"]))]
        canonical=min(finite, key=lambda r: abs(float(r["step"])-canonical_step)) if finite else None
        plateau=[r for r in finite if stable_lower <= float(r["step"]) <= stable_upper]
        if canonical is None or not plateau:
            out.append({
                "state":state,"canonical_step":canonical_step,"canonical_kappa":float("nan"),
                "plateau_min_kappa":float("nan"),"plateau_max_kappa":float("nan"),
                "plateau_relative_span":float("nan"),"converged":False,
            })
            continue
        vals=[float(r["kappa"]) for r in plateau]
        k0=float(canonical["kappa"])
        span=(max(vals)-min(vals))/max(abs(k0),1.0)
        out.append({
            "state":state,
            "canonical_step":canonical_step,
            "canonical_kappa":k0,
            "plateau_min_kappa":min(vals),
            "plateau_max_kappa":max(vals),
            "plateau_relative_span":span,
            "converged":bool(span <= 1.0e-5),
        })
    return out


def actual_root_metrics(label, ref, sample):
    inspection = reconstruct(ref, sample, closure_audit=True)
    contact = inspection.contact
    audit = inspection.closure_audit
    if contact is None or audit is None:
        raise RuntimeError("Selected state did not reconstruct an engaged closure.")

    # Canonical physical stick-root Jacobian: state-frozen central derivative of
    # the actual residual map.  Do not substitute branch_result.jacobian here;
    # that is solver working state and may be a Broyden continuation estimate.
    u = contact.traction_utilization
    _J, sigma_min, sigma_max, kappa, determinant = reconstructed_root_jacobian(
        ref, sample, u.primary_lambda, u.secondary_lambda, step=1.0e-5
    )
    law = ref.decoded.system.cvt.traction_law
    return {
        "label": label,
        "source_run": ref.name,
        "time_s": sample.time,
        "shift_mm": 1000.0 * sample.cvt_state.shift_position,
        "shift_speed_mm_s": 1000.0 * sample.cvt_state.shift_speed,
        "shift_constraint": sample.composed_mode.cvt.shift_constraint.value,
        "contact_mode": contact.mode.value,
        "lambda_p": u.primary_lambda,
        "lambda_s": u.secondary_lambda,
        "primary_static_margin": law.static_margin_at(ContactInterface.PRIMARY, u.primary_lambda),
        "secondary_static_margin": law.static_margin_at(ContactInterface.SECONDARY, u.secondary_lambda),
        "A_condition_raw": audit.condition_number,
        "A_condition_scaled": audit.scaled_condition_number,
        "A_rank": audit.matrix_rank,
        "A_max_abs_equation_residual": audit.max_abs_equation_residual,
        "J_sigma_min": sigma_min,
        "J_sigma_max": sigma_max,
        "J_condition": kappa,
        "J_determinant": determinant,
        "J_definition": "central_difference_of_frozen_R_at_root",
        "J_step": 1.0e-5,
        "N_p": contact.normal_primary,
        "N_s": contact.normal_secondary,
    }


def equilibrated_matrix_singulars(matrix, right_hand_side):
    matrix = np.asarray(matrix, dtype=float)
    rhs = np.asarray(right_hand_side, dtype=float)
    row_norm = np.maximum(np.max(np.abs(matrix), axis=1), np.abs(rhs))
    row_scale = np.where(row_norm > 0.0, 1.0 / row_norm, 1.0)
    row_matrix = row_scale[:, None] * matrix
    column_norm = np.max(np.abs(row_matrix), axis=0)
    column_scale = np.where(column_norm > 0.0, 1.0 / column_norm, 1.0)
    scaled = row_matrix * column_scale[None, :]
    singular = np.linalg.svd(scaled, compute_uv=False)
    return float(singular[-1]), float(singular[0]), float(np.linalg.det(scaled))


def trial_belt_metrics(snapshot, unknowns, utilization):
    terms = TrialEquationContext(snapshot=snapshot, traction_utilization=utilization).contact_terms
    geometry = snapshot.geometry
    state = snapshot.state
    q = snapshot.belt_linear_density
    sin_beta = math.sin(snapshot.sheave_half_angle)

    def offsets(radius):
        rddot = radius.d2_center_of_mass_ds2 * state.shift_speed**2 + radius.d_center_of_mass_ds * unknowns.shift_acceleration
        c = q * (state.belt_speed**2 - radius.center_of_mass * rddot)
        a = q * (radius.center_of_mass * unknowns.belt_acceleration + radius.d_center_of_mass_ds * state.shift_speed * state.belt_speed)
        return c, a

    pc, pa = offsets(geometry.primary)
    sc, sa = offsets(geometry.secondary)
    pp = geometry.primary_wrap_angle
    sp = geometry.secondary_wrap_angle

    p_in = pc + unknowns.primary_normal_resultant * sin_beta / (pp * terms.primary_phi_minus) - pa * pp * terms.primary_psi_minus / terms.primary_phi_minus
    p_out = pc + terms.primary_exp_neg * (p_in - pc) + pa * pp * terms.primary_phi_minus
    s_in = sc + unknowns.secondary_normal_resultant * sin_beta / (sp * terms.secondary_phi_minus) - sa * sp * terms.secondary_psi_minus / terms.secondary_phi_minus
    s_out = sc + terms.secondary_exp_neg * (s_in - sc) + sa * sp * terms.secondary_phi_minus

    p_min_t = min(p_in, p_out)
    s_min_t = min(s_in, s_out)
    p_local = (p_min_t - pc) / sin_beta
    s_local = (s_min_t - sc) / sin_beta
    return {
        "T_p_in": float(p_in), "T_p_out": float(p_out),
        "T_s_in": float(s_in), "T_s_out": float(s_out),
        "min_tension": float(min(p_min_t, s_min_t)),
        "min_local_normal_p": float(p_local),
        "min_local_normal_s": float(s_local),
    }


def trial_mechanism_margin(ref, sample, snapshot, unknowns):
    model = ref.decoded.system.cvt.model
    pctx = model.primary_actuation_context(time=sample.time, state=snapshot.state, geometry=snapshot.geometry)
    sctx = model.secondary_actuation_context(time=sample.time, state=snapshot.state, geometry=snapshot.geometry)
    margins = tuple(float(v) for _k, v in model.primary_actuator.compressive_contact_margins(pctx, unknowns)) + tuple(
        float(v) for _k, v in model.secondary_actuator.compressive_contact_margins(sctx, unknowns)
    )
    return min(margins) if margins else float("inf")


def topology_failure_code(ref, sample, trial, utilization, snapshot):
    """Bit mask: 1 resultant normal, 2 tension, 4 local lift-off, 8 mechanism, 16 support."""
    audit = trial.closure
    belt = trial_belt_metrics(snapshot, audit.unknowns, utilization)
    code = 0
    if audit.unknowns.primary_normal_resultant < 0.0 or audit.unknowns.secondary_normal_resultant < 0.0:
        code |= 1
    if belt["min_tension"] < 0.0:
        code |= 2
    if belt["min_local_normal_p"] < 0.0 or belt["min_local_normal_s"] < 0.0:
        code |= 4
    mechanism = trial_mechanism_margin(ref, sample, snapshot, audit.unknowns)
    if mechanism < 0.0:
        code |= 8
    support = float("inf")
    if engaged_constraint(sample) is EngagedShiftConstraint.LOW_RATIO_SEAT:
        support = float(trial.low_ratio_seat_reaction)
    elif engaged_constraint(sample) is EngagedShiftConstraint.UPPER_STOP:
        support = float(trial.upper_stop_reaction)
    if support < 0.0:
        code |= 16
    return code, {
        **belt,
        "min_belt_tension": float(belt["min_tension"]),
        "mechanism_margin": float(mechanism),
        "support_reaction": float(support),
    }


def build_map(ref, sample, domain, samples):
    inspection = reconstruct(ref, sample, closure_audit=True)
    contact = inspection.contact
    if contact is None:
        raise RuntimeError("Conditioning map requires engaged contact.")
    snapshot = contact.snapshot
    closure = EngagedContactClosure(snapshot=snapshot, shift_constraint=engaged_constraint(sample))

    p0, p1, s0, s1 = domain_bounds(ref, domain)
    lp = np.linspace(p0, p1, samples)
    ls = np.linspace(s0, s1, samples)
    shape = (samples, samples)
    float_keys = (
        "R_p", "R_s", "cond_A_raw", "cond_A_scaled", "rank_A", "N_p", "N_s", "tau_p", "tau_s",
        "sigma_min_A_scaled", "sigma_max_A_scaled", "det_A_scaled", "min_belt_tension",
        "min_local_normal_p", "min_local_normal_s", "mechanism_margin", "support_reaction",
    )
    arrays = {key: np.full(shape, np.nan) for key in float_keys}
    arrays["topology_failure_code"] = np.full(shape, -1, dtype=np.int16)
    arrays["static_capacity_admissible"] = np.zeros(shape, dtype=bool)
    arrays["topology_admissible"] = np.zeros(shape, dtype=bool)
    arrays["full_static_admissible"] = np.zeros(shape, dtype=bool)

    law = ref.decoded.system.cvt.traction_law
    p_static = law.primary_static_interval
    s_static = law.secondary_static_interval
    solved = 0
    for i, lam_s in enumerate(ls):
        if i % max(1, samples // 10) == 0:
            print(f"      row {i+1}/{samples}")
        for j, lam_p in enumerate(lp):
            utilization = ContactTractionUtilization(primary_lambda=float(lam_p), secondary_lambda=float(lam_s))
            try:
                trial = closure.evaluate_trial(
                    traction_utilization=utilization,
                    maximum_closure_condition_number=None,
                    capture_diagnostics=True,
                )
            except (ArithmeticError, ValueError, RuntimeError, np.linalg.LinAlgError):
                continue
            audit = trial.closure
            motion = trial.relative_motion
            arrays["R_p"][i, j] = motion.primary_relative_acceleration
            arrays["R_s"][i, j] = motion.secondary_relative_acceleration
            arrays["cond_A_raw"][i, j] = audit.condition_number
            arrays["cond_A_scaled"][i, j] = audit.scaled_condition_number
            arrays["rank_A"][i, j] = audit.matrix_rank
            arrays["N_p"][i, j] = audit.unknowns.primary_normal_resultant
            arrays["N_s"][i, j] = audit.unknowns.secondary_normal_resultant
            arrays["tau_p"][i, j] = audit.unknowns.primary_torque
            arrays["tau_s"][i, j] = audit.unknowns.secondary_torque
            amin, amax, adet = equilibrated_matrix_singulars(audit.matrix, audit.right_hand_side)
            arrays["sigma_min_A_scaled"][i, j] = amin
            arrays["sigma_max_A_scaled"][i, j] = amax
            arrays["det_A_scaled"][i, j] = adet
            try:
                code, extra = topology_failure_code(ref, sample, trial, utilization, snapshot)
            except Exception as exc:
                raise RuntimeError(
                    f"Topology-admissibility evaluation failed at "
                    f"lambda_p={lam_p:.9g}, lambda_s={lam_s:.9g}."
                ) from exc
            arrays["topology_failure_code"][i, j] = code
            arrays["topology_admissible"][i, j] = code == 0
            for key in ("min_belt_tension", "min_local_normal_p", "min_local_normal_s", "mechanism_margin", "support_reaction"):
                arrays[key][i, j] = extra[key]
            static_ok = p_static.lower <= lam_p <= p_static.upper and s_static.lower <= lam_s <= s_static.upper
            arrays["static_capacity_admissible"][i, j] = static_ok
            arrays["full_static_admissible"][i, j] = static_ok and arrays["topology_admissible"][i, j]
            solved += 1

    arrays["R_norm"] = np.hypot(arrays["R_p"], arrays["R_s"])
    smin, smax, kappa, det = finite_difference_jacobian(lp, ls, arrays["R_p"], arrays["R_s"])
    arrays["sigma_min_J"] = smin
    arrays["sigma_max_J"] = smax
    arrays["kappa_J"] = kappa
    arrays["det_J"] = det
    arrays["lambda_p"] = lp
    arrays["lambda_s"] = ls
    arrays["solved_count"] = solved
    arrays["total_count"] = samples * samples
    return arrays


def multistart(ref, sample, n, cluster_tol, *, domain="physical"):
    inspection = reconstruct(ref, sample, closure_audit=False)
    contact = inspection.contact
    if contact is None:
        return [], []
    closure = EngagedContactClosure(
        snapshot=contact.snapshot,
        shift_constraint=engaged_constraint(sample),
    )
    law = ref.decoded.system.cvt.traction_law
    base = ref.decoded.system.cvt.solve_settings
    if domain == "physical":
        p0,p1 = law.primary_static_interval.lower, law.primary_static_interval.upper
        s0,s1 = law.secondary_static_interval.lower, law.secondary_static_interval.upper
        search_bounds = base.lambda_search_bounds
    else:
        p0,p1,s0,s1 = domain_bounds(ref, domain)
        search_bounds = LambdaSearchBounds(
            primary_lower=float(p0), primary_upper=float(p1),
            secondary_lower=float(s0), secondary_upper=float(s1),
        )
    p = np.linspace(p0, p1, n)
    s = np.linspace(s0, s1, n)

    roots = []
    rows = []
    for lam_s in s:
        for lam_p in p:
            row = {
                "start_lambda_p": float(lam_p),
                "start_lambda_s": float(lam_s),
                "optimizer_success": False,
                "accepted": False,
                "statically_admissible": False,
                "root_lambda_p": float("nan"),
                "root_lambda_s": float("nan"),
                "root_cluster": -1,
                "residual_norm": float("nan"),
                "jacobian_condition": float("nan"),
                "function_evaluations": -1,
            }
            try:
                settings = replace(
                    base,
                    lambda_search_bounds=search_bounds,
                    initial_guess=ContactTractionUtilization(
                        primary_lambda=float(lam_p),
                        secondary_lambda=float(lam_s),
                    ),
                )
                solved = closure.solve_stick_stick(settings=settings)
                root = np.asarray(
                    [
                        solved.traction_utilization.primary_lambda,
                        solved.traction_utilization.secondary_lambda,
                    ],
                    dtype=float,
                )
                cluster = -1
                if solved.accepted:
                    for idx, existing in enumerate(roots):
                        if np.linalg.norm(root - existing) <= cluster_tol:
                            cluster = idx
                            break
                    if cluster < 0:
                        cluster = len(roots)
                        roots.append(root)
                row.update(
                    {
                        "optimizer_success": bool(solved.optimizer_success),
                        "accepted": bool(solved.accepted),
                        "statically_admissible": bool(
                            solved.sticking_interfaces_are_statically_admissible(
                                traction_law=law
                            )
                        ),
                        "root_lambda_p": float(root[0]),
                        "root_lambda_s": float(root[1]),
                        "root_cluster": cluster,
                        "residual_norm": float(np.linalg.norm(solved.sticking_residuals)),
                        "jacobian_condition": float(solved.jacobian_condition_number),
                        "function_evaluations": int(solved.function_evaluations),
                    }
                )
            except (ArithmeticError, ValueError, RuntimeError, np.linalg.LinAlgError):
                pass
            rows.append(row)
    return rows, roots


def positive_limits(values):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a) & (a > 0)]
    if a.size == 0:
        return 1e-12, 1.0
    lo = max(float(np.percentile(a, 1)), 1e-16)
    hi = max(float(np.percentile(a, 99)), lo * 1.01)
    return lo, hi


def signed_limit(values):
    a = np.abs(np.asarray(values, dtype=float))
    a = a[np.isfinite(a)]
    return max(float(np.percentile(a, 99)) if a.size else 1.0, 1e-12)


def _static_box(ref):
    law = ref.decoded.system.cvt.traction_law
    return (
        law.primary_static_interval.lower,
        law.primary_static_interval.upper,
        law.secondary_static_interval.lower,
        law.secondary_static_interval.upper,
    )


def plot_map(data, actual, label, domain, path, *, ref, mask_topology: bool = False):
    lp, ls = data["lambda_p"], data["lambda_s"]
    LP, LS = np.meshgrid(lp, ls)
    normal = np.maximum(np.abs(data["N_p"]), np.abs(data["N_s"]))
    rp_lim = signed_limit(data["R_p"]); rs_lim = signed_limit(data["R_s"])
    rn_lo, rn_hi = positive_limits(data["R_norm"])
    ca_lo, ca_hi = positive_limits(data["cond_A_scaled"])
    sm_lo, sm_hi = positive_limits(data["sigma_min_J"])
    kj_lo, kj_hi = positive_limits(data["kappa_J"])
    det_lim = signed_limit(data["det_J"]); n_lo, n_hi = positive_limits(normal)

    panels = [
        (r"Primary stick residual $R_p$", SymLogNorm(linthresh=1.0, vmin=-rp_lim, vmax=rp_lim), data["R_p"], "Rp"),
        (r"Secondary stick residual $R_s$", SymLogNorm(linthresh=1.0, vmin=-rs_lim, vmax=rs_lim), data["R_s"], "Rs"),
        (r"Residual norm $\|R\|_2$", LogNorm(vmin=rn_lo, vmax=rn_hi), data["R_norm"], "Rnorm"),
        (r"Equilibrated 8×8 $\kappa(A)$", LogNorm(vmin=ca_lo, vmax=ca_hi), data["cond_A_scaled"], "Acond"),
        (r"$\sigma_{\min}(J_R)$", LogNorm(vmin=sm_lo, vmax=sm_hi), data["sigma_min_J"], "Jmin"),
        (r"$\kappa(J_R)$", LogNorm(vmin=kj_lo, vmax=kj_hi), data["kappa_J"], "Jcond"),
        (r"Signed $\det(J_R)$", TwoSlopeNorm(vcenter=0.0, vmin=-det_lim, vmax=det_lim), data["det_J"], "Jdet"),
        (r"max$(|N_p|,|N_s|)$", LogNorm(vmin=n_lo, vmax=n_hi), normal, "N"),
    ]
    invalid = ~np.asarray(data["topology_admissible"], dtype=bool)
    fig, axes = plt.subplots(2, 4, figsize=(22, 11.5), constrained_layout=True)
    for ax, (title, norm, source, key) in zip(axes.ravel(), panels):
        values = np.asarray(source, dtype=float)
        if mask_topology:
            values = np.ma.masked_where(invalid, values)
        im = ax.pcolormesh(LP, LS, values, shading="auto", norm=norm, rasterized=True)
        if key in ("Rp", "Rs", "Rnorm"):
            try:
                if key == "Rp":
                    ax.contour(LP, LS, data["R_p"], levels=[0.0], colors="black", linewidths=1.2)
                elif key == "Rs":
                    ax.contour(LP, LS, data["R_s"], levels=[0.0], colors="black", linewidths=1.2, linestyles="--")
                else:
                    ax.contour(LP, LS, data["R_p"], levels=[0.0], colors="black", linewidths=1.2)
                    ax.contour(LP, LS, data["R_s"], levels=[0.0], colors="black", linewidths=1.2, linestyles="--")
            except ValueError:
                pass
        # For expanded/broad views show the actual static-capacity box without
        # deleting the mathematical continuation outside it.
        if domain != "physical":
            p0,p1,s0,s1 = _static_box(ref)
            ax.add_patch(Rectangle((p0,s0),p1-p0,s1-s0,fill=False,linestyle=":",linewidth=1.2,edgecolor="black"))
        ax.plot(actual["lambda_p"], actual["lambda_s"], marker="x", markersize=9, mew=2.2, color="tab:blue")
        ax.set_xlabel(r"$\lambda_p$"); ax.set_ylabel(r"$\lambda_s$"); ax.set_title(title)
        fig.colorbar(im, ax=ax, shrink=0.84)
    suffix = "topology-admissible only" if mask_topology else "all computed points"
    fig.suptitle(f"{label}: {domain} lambda domain — {suffix}", fontsize=15)
    fig.savefig(path, dpi=240)
    plt.close(fig)


def plot_inadmissibility(data, actual, label, domain, path, *, ref):
    lp, ls = data["lambda_p"], data["lambda_s"]
    LP, LS = np.meshgrid(lp, ls)
    code = np.asarray(data["topology_failure_code"], dtype=int)
    masks = [
        ("Fully topology-admissible", code == 0),
        ("Negative integrated normal", (code & 1) != 0),
        ("Negative belt tension", (code & 2) != 0),
        ("Local wrap lift-off", (code & 4) != 0),
        ("Unilateral mechanism violation", (code & 8) != 0),
        ("Active stop/support would pull", (code & 16) != 0),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(15, 9.5), constrained_layout=True)
    cmap = ListedColormap(["white", "black"])
    for ax,(title,mask) in zip(axes.ravel(),masks):
        ax.pcolormesh(LP,LS,mask.astype(int),shading="auto",cmap=cmap,vmin=0,vmax=1,rasterized=True)
        if domain != "physical":
            p0,p1,s0,s1=_static_box(ref)
            ax.add_patch(Rectangle((p0,s0),p1-p0,s1-s0,fill=False,linestyle=":",linewidth=1.2,edgecolor="tab:blue"))
        ax.plot(actual["lambda_p"],actual["lambda_s"],marker="x",markersize=8,mew=2,color="tab:red")
        ax.set_xlabel(r"$\lambda_p$"); ax.set_ylabel(r"$\lambda_s$"); ax.set_title(title)
    fig.suptitle(f"{label}: mechanical topology admissibility ({domain})")
    fig.savefig(path,dpi=240); plt.close(fig)


def plot_feature_overlay(data, actual, label, path, *, ref):
    lp,ls=data["lambda_p"],data["lambda_s"]; LP,LS=np.meshgrid(lp,ls)
    cond=np.asarray(data["cond_A_scaled"],float)
    invalid=~np.asarray(data["topology_admissible"],bool)
    fig,ax=plt.subplots(figsize=(9.2,7.6))
    finite=cond[np.isfinite(cond)&(cond>0)]
    lo=max(np.nanpercentile(finite,1),1.0); hi=max(np.nanpercentile(finite,99.8),lo*1.01)
    im=ax.pcolormesh(LP,LS,cond,shading="auto",norm=LogNorm(vmin=lo,vmax=hi),rasterized=True)
    # gray transparent overlay = topology inadmissible but still computed underneath
    ax.contourf(LP,LS,invalid.astype(float),levels=[0.5,1.5],colors=["0.7"],alpha=0.32)
    ax.contour(LP,LS,data["R_p"],levels=[0.0],colors="black",linewidths=1.5)
    ax.contour(LP,LS,data["R_s"],levels=[0.0],colors="black",linewidths=1.5,linestyles="--")
    p0,p1,s0,s1=_static_box(ref)
    ax.add_patch(Rectangle((p0,s0),p1-p0,s1-s0,fill=False,linestyle=":",linewidth=1.6,edgecolor="tab:blue"))
    ax.plot(actual["lambda_p"],actual["lambda_s"],"x",markersize=10,mew=2.5,color="tab:red",label="actual root")
    ax.set_xlabel(r"$\lambda_p$");ax.set_ylabel(r"$\lambda_s$")
    ax.set_title(f"{label}: closure ridges, zero contours, and admissibility")
    ax.legend(loc="best");fig.colorbar(im,ax=ax,label=r"equilibrated $\kappa(A)$")
    fig.tight_layout();fig.savefig(path,dpi=260);plt.close(fig)


def plot_slices(data, actual, label, path):
    lp, ls = data["lambda_p"], data["lambda_s"]
    i = int(np.argmin(np.abs(ls - actual["lambda_s"])))
    j = int(np.argmin(np.abs(lp - actual["lambda_p"])))
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), constrained_layout=True)

    axes[0,0].plot(lp, data["R_p"][i,:], label=r"$R_p$")
    axes[0,0].plot(lp, data["R_s"][i,:], label=r"$R_s$")
    axes[0,0].axhline(0.0, linewidth=1.0)
    axes[0,0].axvline(actual["lambda_p"], linewidth=1.0)
    axes[0,0].set_xlabel(r"$\lambda_p$")
    axes[0,0].set_ylabel("Residual [m/s²]")
    axes[0,0].set_title(rf"Residual slice at $\lambda_s\approx{ls[i]:.3g}$")
    axes[0,0].grid(True, alpha=0.25)
    axes[0,0].legend()

    axes[0,1].plot(lp, data["N_p"][i,:], label=r"$N_p$")
    axes[0,1].plot(lp, data["N_s"][i,:], label=r"$N_s$")
    axes[0,1].axhline(0.0, linewidth=1.0)
    axes[0,1].axvline(actual["lambda_p"], linewidth=1.0)
    axes[0,1].set_xlabel(r"$\lambda_p$")
    axes[0,1].set_ylabel("Normal resultant [N]")
    axes[0,1].set_title("Normal-force response on same slice")
    axes[0,1].grid(True, alpha=0.25)
    axes[0,1].legend()

    axes[1,0].plot(ls, data["R_p"][:,j], label=r"$R_p$")
    axes[1,0].plot(ls, data["R_s"][:,j], label=r"$R_s$")
    axes[1,0].axhline(0.0, linewidth=1.0)
    axes[1,0].axvline(actual["lambda_s"], linewidth=1.0)
    axes[1,0].set_xlabel(r"$\lambda_s$")
    axes[1,0].set_ylabel("Residual [m/s²]")
    axes[1,0].set_title(rf"Residual slice at $\lambda_p\approx{lp[j]:.3g}$")
    axes[1,0].grid(True, alpha=0.25)
    axes[1,0].legend()

    axes[1,1].plot(ls, data["N_p"][:,j], label=r"$N_p$")
    axes[1,1].plot(ls, data["N_s"][:,j], label=r"$N_s$")
    axes[1,1].axhline(0.0, linewidth=1.0)
    axes[1,1].axvline(actual["lambda_s"], linewidth=1.0)
    axes[1,1].set_xlabel(r"$\lambda_s$")
    axes[1,1].set_ylabel("Normal resultant [N]")
    axes[1,1].set_title("Normal-force response on same slice")
    axes[1,1].grid(True, alpha=0.25)
    axes[1,1].legend()

    fig.suptitle(f"{label}: lambda-domain slices through the actual root")
    fig.savefig(path, dpi=175)
    plt.close(fig)


def plot_multistart(rows, roots, label, path):
    fig, ax = plt.subplots(figsize=(7.3, 6.2))
    failed = [r for r in rows if not r["accepted"]]
    accepted = [r for r in rows if r["accepted"]]
    if failed:
        ax.scatter(
            [r["start_lambda_p"] for r in failed],
            [r["start_lambda_s"] for r in failed],
            marker="x",
            label="Not accepted",
        )
    if accepted:
        for cluster in sorted(set(int(r["root_cluster"]) for r in accepted)):
            group = [r for r in accepted if int(r["root_cluster"]) == cluster]
            ax.scatter(
                [r["start_lambda_p"] for r in group],
                [r["start_lambda_s"] for r in group],
                label=f"Accepted root {cluster+1}",
            )
    for root in roots:
        ax.plot(root[0], root[1], marker="*", markersize=14)
    ax.set_xlabel(r"Initial $\lambda_p$")
    ax.set_ylabel(r"Initial $\lambda_s$")
    ax.set_title(f"{label}: stick-root multi-start basin")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def ridge_candidate_rows(data, label, domain, *, percentile=99.5, max_rows=600):
    cond = np.asarray(data["cond_A_scaled"], dtype=float)
    finite = np.isfinite(cond)
    if not np.any(finite):
        return []
    threshold = float(np.percentile(cond[finite], percentile))
    idx = np.argwhere(finite & (cond >= threshold))
    if idx.shape[0] > max_rows:
        # retain the strongest candidates while keeping the raw NPZ complete
        scores = cond[idx[:,0], idx[:,1]]
        idx = idx[np.argsort(scores)[-max_rows:]]
    lp,ls=data["lambda_p"],data["lambda_s"]
    rows=[]
    for i,j in idx:
        rows.append({
            "state":label,"domain":domain,"lambda_p":float(lp[j]),"lambda_s":float(ls[i]),
            "cond_A_scaled":float(cond[i,j]),
            "sigma_min_A_scaled":float(data["sigma_min_A_scaled"][i,j]),
            "det_A_scaled":float(data["det_A_scaled"][i,j]),
            "R_p":float(data["R_p"][i,j]),"R_s":float(data["R_s"][i,j]),
            "N_p":float(data["N_p"][i,j]),"N_s":float(data["N_s"][i,j]),
            "topology_failure_code":int(data["topology_failure_code"][i,j]),
            "topology_admissible":bool(data["topology_admissible"][i,j]),
        })
    return rows


def feature_rows(data, label):
    rows = []
    lp, ls = data["lambda_p"], data["lambda_s"]

    def point(feature, score, choose="max"):
        score = np.asarray(score, dtype=float)
        finite = np.isfinite(score)
        if not np.any(finite):
            return
        ranked = np.where(
            finite,
            score,
            np.inf if choose == "min" else -np.inf,
        )
        flat = int(np.argmin(ranked) if choose == "min" else np.argmax(ranked))
        i, j = np.unravel_index(flat, ranked.shape)
        row = {
            "state": label,
            "feature": feature,
            "lambda_p": float(lp[j]),
            "lambda_s": float(ls[i]),
        }
        for key in (
            "R_p", "R_s", "R_norm",
            "cond_A_raw", "cond_A_scaled", "rank_A",
            "sigma_min_A_scaled", "sigma_max_A_scaled", "det_A_scaled",
            "sigma_min_J", "sigma_max_J", "kappa_J", "det_J",
            "N_p", "N_s", "tau_p", "tau_s",
            "min_belt_tension", "min_local_normal_p", "min_local_normal_s",
            "mechanism_margin", "support_reaction",
        ):
            row[key] = float(data[key][i,j])
        row["topology_failure_code"] = int(data["topology_failure_code"][i,j])
        row["topology_admissible"] = bool(data["topology_admissible"][i,j])
        row["static_capacity_admissible"] = bool(data["static_capacity_admissible"][i,j])
        row["full_static_admissible"] = bool(data["full_static_admissible"][i,j])
        rows.append(row)

    point("maximum_scaled_8x8_condition", data["cond_A_scaled"])
    point("maximum_stick_jacobian_condition", data["kappa_J"])
    point("minimum_stick_jacobian_sigma_min", data["sigma_min_J"], choose="min")
    point("maximum_abs_primary_normal", np.abs(data["N_p"]))
    point("maximum_abs_secondary_normal", np.abs(data["N_s"]))
    return rows


def main():
    args = parse_args()
    verify_environment()
    spec = load_json(SPEC_FILE)
    case_library = load_case_library(CASE_LIBRARY_FILE)
    base_path = (HERE / spec["base_document"]).resolve()

    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)

    print("Running frozen baseline launch reference...")
    launch = build_reference(spec, "launch")
    nominal_states = select_nominal_states(launch)

    print("\nSearching controlled shared operating cases...")
    controlled_states, search_rows = build_controlled_states(launch.decoded, case_library)
    write_rows(ARTIFACTS / "shared_case_search.csv", search_rows)

    states = nominal_states + controlled_states
    if len(states) < 5:
        raise RuntimeError(f"Only {len(states)} usable stick-stick states found; need at least five.")

    # One actual-root conditioning scan over every mechanically distinct state.
    actual_rows = [actual_root_metrics(label, ref, sample) for label, ref, sample in states]
    write_rows(ARTIFACTS / "actual_root_state_scan.csv", actual_rows)
    jacobian_step_rows = [
        row
        for label, ref, sample in states
        for row in root_jacobian_step_rows(label, ref, sample)
    ]
    write_rows(ARTIFACTS / "root_jacobian_step_sweep.csv", jacobian_step_rows)
    jacobian_convergence = jacobian_convergence_rows(jacobian_step_rows)
    write_rows(ARTIFACTS / "root_jacobian_convergence_summary.csv", jacobian_convergence)

    # Choose the smaller subset that deserves the expensive lambda-plane maps.
    by_label = {label: (label, ref, sample, actual) for (label, ref, sample), actual in zip(states, actual_rows)}
    requested = list(spec["map_selection"]["named_cases"])
    if spec["map_selection"].get("include_worst_actual_A", True):
        worst_a = max(actual_rows, key=lambda r: float(r["A_condition_scaled"]))
        requested.append(worst_a["label"])
    if spec["map_selection"].get("include_worst_actual_J", True):
        finite_j = [r for r in actual_rows if math.isfinite(float(r["J_condition"]))]
        if finite_j:
            requested.append(max(finite_j, key=lambda r: float(r["J_condition"]))["label"])
    map_labels = []
    for label in requested:
        if label in by_label and label not in map_labels:
            map_labels.append(label)
    write_rows(
        ARTIFACTS / "mapped_state_selection.csv",
        [{"label": label, "mapped": label in map_labels, "reason": "configured_or_worst_actual" if label in map_labels else "actual_root_scan_only"} for label in by_label],
    )

    multistart_all = []
    multistart_summary = []
    # Multi-start remains cheap enough to run for every actual stick state.
    for label, ref, sample in states:
        n_start = int(spec["multistart"]["samples_per_axis"])
        if args.quick:
            n_start = min(5, n_start)
        rows, roots = multistart(ref, sample, n_start, float(spec["multistart"]["root_cluster_tolerance"]))
        for row in rows:
            row["state"] = label
        multistart_all.extend(rows)
        multistart_summary.append({
            "state": label,
            "start_count": len(rows),
            "accepted_count": sum(bool(r["accepted"]) for r in rows),
            "statically_admissible_accepted_count": sum(bool(r["accepted"]) and bool(r["statically_admissible"]) for r in rows),
            "distinct_accepted_roots": len(roots),
            "all_accepted_one_root": len(roots) == 1,
        })
        state_dir = ARTIFACTS / "states" / label
        state_dir.mkdir(parents=True, exist_ok=True)
        plot_multistart(rows, roots, label, state_dir / "multistart_basin.png")

    # Expanded-domain root census: mathematical roots outside static capacity
    # are catalogued separately so they cannot be confused with the physical root.
    expanded_multistart_all = []
    expanded_multistart_summary = []
    n_expanded = int(spec["multistart"].get("expanded_samples_per_axis", 9))
    if args.quick:
        n_expanded = min(5, n_expanded)
    for label in map_labels:
        _label, ref, sample, _actual = by_label[label]
        rows, roots = multistart(
            ref, sample, n_expanded,
            float(spec["multistart"]["root_cluster_tolerance"]),
            domain="expanded",
        )
        for row in rows:
            row["state"] = label
            row["search_domain"] = "expanded"
        expanded_multistart_all.extend(rows)
        expanded_multistart_summary.append({
            "state": label,
            "start_count": len(rows),
            "accepted_count": sum(bool(r["accepted"]) for r in rows),
            "statically_admissible_accepted_count": sum(bool(r["accepted"]) and bool(r["statically_admissible"]) for r in rows),
            "distinct_mathematical_root_clusters": len(roots),
        })
    write_rows(ARTIFACTS / "expanded_multistart_results.csv", expanded_multistart_all)
    write_rows(ARTIFACTS / "expanded_multistart_summary.csv", expanded_multistart_summary)

    domain_summary = []
    feature_table = []
    ridge_table = []
    broad_showcase = str(spec["map_selection"]["broad_showcase_case"])

    for label in map_labels:
        _label, ref, sample, actual = by_label[label]
        state_dir = ARTIFACTS / "states" / label
        state_dir.mkdir(parents=True, exist_ok=True)
        print(f"\nHigh-resolution maps: {label}")

        domains = ["physical", "expanded"]
        if label == broad_showcase:
            domains.append("broad")
        for domain in domains:
            n = int(spec["lambda_domains"][domain]["samples"])
            if args.quick:
                n = int(spec["lambda_domains"][domain].get("quick_samples", max(61, (n + 3)//4)))
                if n % 2 == 0:
                    n += 1
            print(f"  {domain}: {n}×{n}")
            data = build_map(ref, sample, domain, n)
            np.savez_compressed(
                state_dir / f"{domain}_map.npz",
                **{k: v for k, v in data.items() if isinstance(v, np.ndarray)},
            )
            plot_map(data, actual, label, domain, state_dir / f"{domain}_conditioning_map.png", ref=ref, mask_topology=False)
            plot_map(data, actual, label, domain, state_dir / f"{domain}_conditioning_map_topology_masked.png", ref=ref, mask_topology=True)
            plot_inadmissibility(data, actual, label, domain, state_dir / f"{domain}_inadmissibility_map.png", ref=ref)
            if domain == "expanded":
                plot_feature_overlay(data, actual, label, state_dir / "expanded_feature_overlay.png", ref=ref)
                plot_slices(data, actual, label, state_dir / "expanded_root_slices.png")
            if domain == "broad":
                plot_feature_overlay(data, actual, label, state_dir / "broad_feature_overlay.png", ref=ref)
                plot_slices(data, actual, label, state_dir / "broad_root_slices.png")

            finite_A = data["cond_A_scaled"][np.isfinite(data["cond_A_scaled"])]
            finite_J = data["kappa_J"][np.isfinite(data["kappa_J"])]
            finite_s = data["sigma_min_J"][np.isfinite(data["sigma_min_J"])]
            topo = np.asarray(data["topology_admissible"], dtype=bool)
            static = np.asarray(data["full_static_admissible"], dtype=bool)
            domain_summary.append({
                "state": label,
                "domain": domain,
                "samples_per_axis": n,
                "solved_fraction": data["solved_count"] / data["total_count"],
                "topology_admissible_fraction": float(np.mean(topo)),
                "full_static_admissible_fraction": float(np.mean(static)),
                "A_scaled_condition_max": float(np.max(finite_A)) if finite_A.size else float("nan"),
                "A_scaled_condition_p99": float(np.percentile(finite_A, 99)) if finite_A.size else float("nan"),
                "J_condition_max": float(np.max(finite_J)) if finite_J.size else float("nan"),
                "J_condition_p99": float(np.percentile(finite_J, 99)) if finite_J.size else float("nan"),
                "J_sigma_min_min": float(np.min(finite_s)) if finite_s.size else float("nan"),
                "rank_deficient_grid_points": int(np.count_nonzero(np.isfinite(data["rank_A"]) & (data["rank_A"] < 8))),
                "topology_inadmissible_grid_points": int(np.count_nonzero(~topo)),
            })
            if domain in ("expanded", "broad"):
                rows = feature_rows(data, label)
                for row in rows:
                    row["domain"] = domain
                feature_table.extend(rows)
                ridge_table.extend(ridge_candidate_rows(data, label, domain))

    write_rows(ARTIFACTS / "multistart_results.csv", multistart_all)
    write_rows(ARTIFACTS / "multistart_summary.csv", multistart_summary)
    write_rows(ARTIFACTS / "domain_conditioning_summary.csv", domain_summary)
    write_rows(ARTIFACTS / "feature_peaks.csv", feature_table)
    write_rows(ARTIFACTS / "closure_singularity_ridge_candidates.csv", ridge_table)

    physical = [r for r in domain_summary if r["domain"] == "physical"]
    overall = {
        "actual_state_count": len(actual_rows),
        "mapped_state_count": len(map_labels),
        "all_actual_A_rank_8": all(int(r["A_rank"]) == 8 for r in actual_rows),
        "all_multistart_states_single_accepted_root": all(bool(r["all_accepted_one_root"]) for r in multistart_summary),
        "physical_domain_rank_deficient_points": sum(int(r["rank_deficient_grid_points"]) for r in physical),
        "physical_domain_topology_inadmissible_points": sum(int(r["topology_inadmissible_grid_points"]) for r in physical),
        "physical_domain_max_scaled_A_condition": max(float(r["A_scaled_condition_max"]) for r in physical) if physical else float("nan"),
        "physical_domain_max_J_condition": max(float(r["J_condition_max"]) for r in physical) if physical else float("nan"),
        "physical_domain_min_J_sigma_min": min(float(r["J_sigma_min_min"]) for r in physical) if physical else float("nan"),
        "all_root_J_step_sweeps_converged": all(bool(r["converged"]) for r in jacobian_convergence),
        "max_root_J_plateau_relative_span": max(float(r["plateau_relative_span"]) for r in jacobian_convergence if math.isfinite(float(r["plateau_relative_span"]))),
    }

    summary = {
        "study": spec,
        "shared_case_library": case_library,
        "cinder_version": cinder.__version__,
        "base_document": str(base_path),
        "base_document_sha256": sha256(base_path),
        "actual_root_states": actual_rows,
        "root_jacobian_step_sweep": jacobian_step_rows,
        "root_jacobian_convergence": jacobian_convergence,
        "mapped_states": map_labels,
        "multistart_summary": multistart_summary,
        "domain_summary": domain_summary,
        "feature_peaks": feature_table,
        "ridge_candidates": ridge_table,
        "expanded_multistart_summary": expanded_multistart_summary,
        "overall": overall,
    }
    write_json(ARTIFACTS / "summary.json", summary, allow_nan=True)

    lines = [
        "# CINDER v1.1.2 closure-conditioning study — operating-domain upgrade",
        "",
        "The actual-root scan uses the frozen nominal launch plus reusable controlled cases from `defaults/verification_operating_cases.json`. Full lambda-plane maps are generated only for the configured representative/worst states.",
        "",
        "## Actual solved roots",
        "",
        "| State | shift [mm] | sdot [mm/s] | λp | λs | scaled κ(A) | κ(J_R), reconstructed |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in actual_rows:
        lines.append(
            f"| {row['label']} | {row['shift_mm']:.4g} | {row['shift_speed_mm_s']:.4g} | {row['lambda_p']:.5g} | {row['lambda_s']:.5g} | {row['A_condition_scaled']:.4g} | {row['J_condition']:.4g} |"
        )
    lines += [
        "",
        f"- actual stick states scanned: **{len(actual_rows)}**",
        f"- states receiving full maps: **{len(map_labels)}** ({', '.join(map_labels)})",
        f"- all actual 8×8 closures rank 8: **{overall['all_actual_A_rank_8']}**",
        f"- all multi-start state tests found one accepted root cluster: **{overall['all_multistart_states_single_accepted_root']}**",
        f"- Coulomb-box topology-inadmissible grid points across mapped states: **{overall['physical_domain_topology_inadmissible_points']}**",
        "",
        "## Map interpretation",
        "",
        "Every NPZ stores the complete unmasked calculation. The ordinary conditioning map shows all computed points. The `_topology_masked` version hides trial points that violate integrated normal compression, belt tension, local wrap compression, actuator unilateral contact, or an active shift support. The separate inadmissibility figure shows which test rejected each point.",
        "",
        "The expanded and broad domains are mathematical continuations, not friction-admissible operating regions. The dotted rectangle on those plots is the actual static Coulomb-capacity box.",
    ]
    (ARTIFACTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nClosure-conditioning complete: {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
