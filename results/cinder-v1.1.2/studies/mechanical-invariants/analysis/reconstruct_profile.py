"""Reconstruct the primary wrap fields on both exact sides of one reversal.

Replays only the accepted both_slip_mm recipe using CINDER 1.1.2 and the
archived 30 ms horizon/settings. It leaves study inputs and retained evidence
unchanged and writes verified spatial fields to data/. See README.md.
"""
from pathlib import Path
import argparse
import csv
import dataclasses
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import sys

import numpy as np
from scipy.integrate import quad
import matplotlib
matplotlib.use("Agg")

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--inputs", type=Path, default=HERE / "inputs")
parser.add_argument("--output", type=Path, default=HERE / "data")
args = parser.parse_args()
EVIDENCE = args.inputs.resolve()
OUTPUT = args.output.resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)
RELEASE = EVIDENCE / "execution_inputs/results/cinder-v1.1.2"
CORE_FILE = RELEASE / "studies/mechanical-invariants/infrastructure/core.py"

EXPECTED = {"cinder-cvt": "1.1.2", "numpy": "2.5.2", "scipy": "1.18.1", "matplotlib": "3.11.1"}
VERSIONS = {key: importlib.metadata.version(key) for key in EXPECTED}
assert VERSIONS == EXPECTED, VERSIONS
assert sys.version_info[:2] == (3, 12)

spec = importlib.util.spec_from_file_location("profile_mechanical_core", CORE_FILE)
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)

study_spec = core.load_json(core.SPEC_FILE)
library, library_path = core.resolve_case_library(study_spec)
hydrated = core.hydrate_case_recipes(study_spec, library)
decoded, base_path, document = core.load_frozen_reference(hydrated)
case = next(row for row in csv.DictReader((EVIDENCE / "case_definitions.csv").open()) if row["case_id"] == "both_slip_mm")
bench = hydrated["bench_search"]
system = core.make_bench_system(
    decoded, primary_torque=float(case["primary_torque_Nm"]),
    secondary_torque=float(case["secondary_torque_Nm"]),
    primary_inertia=bench["primary_inertia_kg_m2"],
    secondary_inertia=bench["secondary_inertia_kg_m2"],
)
cvt_initial = core.candidate_cvt_state(
    decoded.plant, shift_fraction=float(case["shift_fraction"]),
    belt_speed=float(case["belt_speed_m_s"]), slip_speed=float(case["slip_speed_m_s"]),
    primary_sign=int(case["requested_primary_vrel_sign"]),
    secondary_sign=int(case["requested_secondary_vrel_sign"]),
)
initial = core.full_state(system, cvt_initial)
initial_mode = system.classify_initial_mode(initial)
settings = core.integration_settings(bench["integrator"])
trace = system.integrate_trace(time_span=(0.0, bench["contact_case_duration_s"]), initial_state=initial, initial_mode=initial_mode, settings=settings)
assert trace.completed
event = trace.transitions[0]
assert event.transition.reason == "kinetic_slip_direction_updated_at_zero_crossing"
before_state = np.asarray(trace.segments[0].state[:, -1])
after_state = np.asarray(event.post_transition_state)
assert np.array_equal(before_state, after_state), "This reversal must have continuous state."
retained = [row for row in csv.DictReader((EVIDENCE / "sample_audit.csv").open()) if row["case_id"] == "both_slip_mm" and abs(float(row["time_s"]) - float(case["requested_mode_dwell_s"])) < 1e-11]
assert len(retained) == 2
assert abs(event.time - float(case["requested_mode_dwell_s"])) < 1e-11

field_rows = []
side_records = {}
profiles = {}
for side, full_state, mode, location in [
    ("before", before_state, event.previous_mode, "segment_end"),
    ("after", after_state, event.transition.next_mode, "segment_start"),
]:
    sample = core.AuditSample("both_slip_mm", event.time, full_state, mode, location)
    row, _, _ = core.inspect_sample(system, sample)
    assert not core.hard_row_failures(row, hydrated["review_guards"])
    inspection = core.reconstruct(system, sample, closure_audit=True)
    contact = inspection.contact
    snap = contact.snapshot
    unknowns = inspection.closure_unknowns
    tensions = core.recover_belt_tension_boundaries(inspection)
    r = snap.geometry.primary
    phi = float(snap.geometry.primary_wrap_angle)
    sin_beta = math.sin(snap.sheave_half_angle)
    lam = float(contact.traction_utilization.primary_lambda)
    radial_acceleration = r.d2_center_of_mass_ds2 * snap.state.shift_speed**2 + r.d_center_of_mass_ds * unknowns.shift_acceleration
    radial_offset = snap.belt_linear_density * (snap.state.belt_speed**2 - r.center_of_mass * radial_acceleration)
    z = lam * phi / sin_beta

    # Same analytical endpoint field used by cinder.results.fields.belt,
    # evaluated on exact pre/post inspections, not interpolated through event.
    def tension(theta):
        u = theta / phi
        weight = u if abs(z) < 1e-10 else np.expm1(-z * u) / np.expm1(-z)
        return tensions.primary_in + (tensions.primary_out - tensions.primary_in) * weight

    def normal(theta):
        return (tension(theta) - radial_offset) / sin_beta

    theta = np.linspace(0.0, phi, 1001)
    t_values = tension(theta)
    n_values = normal(theta)
    normal_integral, quadrature_bound = quad(normal, 0.0, phi, epsabs=1e-10, epsrel=1e-12)
    n_min = min(float(normal(0)), float(normal(phi)))
    assert np.isclose(n_min, row["primary_min_dnormal_dtheta_N_per_rad"], atol=1e-10, rtol=1e-10)
    assert np.isclose(normal_integral, row["normal_primary_N"], atol=1e-7, rtol=1e-10)
    old = next(r for r in retained if r["sample_location"] == location)
    compared = {}
    for key in ["normal_primary_N", "primary_min_dnormal_dtheta_N_per_rad", "lambda_primary", "primary_vrel_m_s", "shift_m", "shift_speed_m_s"]:
        compared[key] = {"retained": float(old[key]), "reconstructed": float(row[key]), "difference": float(row[key]) - float(old[key])}
        assert np.isclose(float(row[key]), float(old[key]), atol=1e-8, rtol=1e-10), (side, key, compared[key])
    side_records[side] = {
        "cvt_state": dataclasses.asdict(core.cvt_state_from_full(system, full_state)),
        "mode": repr(mode), "lambda_primary": lam,
        "primary_wrap_angle_rad": phi,
        "sheave_half_angle_rad": float(snap.sheave_half_angle),
        "exponential_parameter_z": z,
        "primary_tension_in_N": tensions.primary_in,
        "primary_tension_out_N": tensions.primary_out,
        "primary_radial_inertial_offset_N": radial_offset,
        "integrated_primary_normal_N": row["normal_primary_N"],
        "profile_integral_N": normal_integral,
        "integral_error_N": normal_integral - row["normal_primary_N"],
        "quadrature_error_estimate_N": quadrature_bound,
        "minimum_local_normal_N_per_rad": n_min,
        "minimum_theta_rad": float(theta[np.argmin(n_values)]),
        "audit_failures": [], "retained_comparison": compared,
    }
    profiles[side] = (theta, n_values)
    field_rows.extend({"side": side, "event_time_s": event.time, "theta_rad": float(th), "tension_N": float(tv), "normal_N_per_rad": float(nv)} for th, tv, nv in zip(theta, t_values, n_values))

# Check every regenerated spatial row against the retained figure data when
# present, in addition to comparisons against the original study above.
retained_spatial = OUTPUT / "primary_wrap_profiles.csv"
spatial_comparison = {"compared_rows": 0, "maximum_absolute_difference": {}}
if retained_spatial.exists():
    with retained_spatial.open(newline="") as stream:
        baseline = list(csv.DictReader(stream))
    assert len(baseline) == len(field_rows)
    for old, new in zip(baseline, field_rows):
        assert old["side"] == new["side"]
        for key in ("event_time_s", "theta_rad", "tension_N", "normal_N_per_rad"):
            difference = abs(float(old[key]) - new[key])
            spatial_comparison["maximum_absolute_difference"][key] = max(
                spatial_comparison["maximum_absolute_difference"].get(key, 0.0), difference)
            assert np.isclose(float(old[key]), new[key], atol=1e-8, rtol=1e-10), (key, difference)
    spatial_comparison["compared_rows"] = len(field_rows)

with retained_spatial.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(field_rows[0]))
    writer.writeheader()
    writer.writerows(field_rows)

# Bind imported helpers/configuration as well as the selected retained rows.
# The archived execution snapshot contains no generated fields; caches are
# deliberately excluded from this portable source identity.
sources = sorted({
    path for path in (EVIDENCE / "execution_inputs").rglob("*")
    if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
} | {EVIDENCE / "sample_audit.csv", EVIDENCE / "case_definitions.csv", CORE_FILE,
     core.SPEC_FILE, library_path, base_path})
summary = {
    "status": "Verified event-side reconstruction for the Section 4.2.1 publication figure",
    "case_id": "both_slip_mm", "frozen_source_commit": "7637a38b4fb9ec21dfb953c1c80a27ec5f389654",
    "versions": VERSIONS, "python_version": sys.version,
    "simulator_source": "Published cinder-cvt==1.1.2 distribution; no modifications",
    "spatial_comparison": spatial_comparison,
    "case_recipe": {k: v for k, v in case.items() if v},
    "bench_primary_inertia_kg_m2": bench["primary_inertia_kg_m2"],
    "bench_secondary_inertia_kg_m2": bench["secondary_inertia_kg_m2"],
    "initial_cvt_state": dataclasses.asdict(cvt_initial), "integrator": bench["integrator"],
    "duration_s": bench["contact_case_duration_s"], "completed": bool(trace.completed),
    "transition_count": len(trace.transitions), "event_time_s": event.time,
    "retained_event_time_s": float(case["requested_mode_dwell_s"]),
    "event_reason": event.transition.reason, "state_continuous_exactly": bool(np.array_equal(before_state, after_state)),
    "sides": side_records,
    "input_sha256": {str(p.relative_to(EVIDENCE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    "output_csv_sha256": hashlib.sha256(retained_spatial.read_bytes()).hexdigest(),
}
(OUTPUT / "profile_verification.json").write_text(json.dumps(summary, indent=2) + "\n")

print(json.dumps({"event_time_s": event.time, "spatial_comparison": spatial_comparison, "sides": {k: {m: v[m] for m in ["integrated_primary_normal_N", "minimum_local_normal_N_per_rad", "minimum_theta_rad", "integral_error_N"]} for k,v in side_records.items()}}, indent=2))
