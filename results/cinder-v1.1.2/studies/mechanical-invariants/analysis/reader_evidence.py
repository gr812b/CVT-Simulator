"""Reader-facing evidence for the rebuilt 4.2.1, without reintegration.

The cases, saved evaluation rows and overlapping coverage tags are distinct
objects. Quantities are reduced only over the physical modes where they apply.
Keep signed roundoff values: passing a tolerance is not exact nonnegativity.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .execution_record import digest, verify_execution_record
from .publication_plots import read_rows

# Every selected case appears in the manuscript case table. These are NOT the
# 25 coverage tags, and the missing bench upper-stop search is NOT a case.
CASE_GROUPS = {
    "Rest": ["static_rest_lower_stop"],
    "Primary disengaged": ["deadzone_free_static_snapshot"],
    "Both contacts sticking": ["stick_stick_forward", "stick_stick_reverse"],
    "One contact sliding": ["primary_slip_plus", "primary_slip_minus",
                            "secondary_slip_plus", "secondary_slip_minus"],
    "Both contacts sliding": ["both_slip_pp", "both_slip_pm", "both_slip_mp", "both_slip_mm"],
    "Free shifting": ["free_shift_closing", "free_shift_opening"],
    "Boundary arrivals": ["boundary_lower_stop_arrival", "boundary_engagement_arrival",
                          "boundary_low_ratio_arrival"],
    "Vehicle acceleration": ["nominal_baja_reference"],
}
STICKING = {
    "stick_stick": ("primary", "secondary"),
    "primary_slip_secondary_stick": ("secondary",),
    "primary_stick_secondary_slip": ("primary",),
    "both_slip": (),
}
SLIDING = {
    mode: tuple(p for p in ("primary", "secondary") if p not in sticks)
    for mode, sticks in STICKING.items()
}
EQUATION_UNITS = {
    "primary_rotation": "N m", "secondary_rotation": "N m",
    "belt_transport": "N", "primary_axial": "N", "secondary_axial": "N",
    "primary_traction": "N", "secondary_traction": "N", "tension_loop": "N",
    "low_ratio_seat_constraint": "m/s^2", "upper_shift_stop_constraint": "m/s^2",
}


def numbers(rows, fields, *, interfaces=None):
    """Yield finite applicable values; a missing required value is an error."""
    for row in rows:
        if interfaces is not None:
            if row["engagement"] != "engaged":
                continue
            keys = [f"{p}_{f}" for p in interfaces[row["contact_mode"]] for f in fields]
        else:
            keys = fields
        for key in keys:
            value = float(row[key])
            if not math.isfinite(value):
                raise ValueError(f"Missing applicable value: {row['case_id']}/{key}")
            yield value, row, key


def extremum(values, kind="max_abs"):
    values = list(values)
    if not values:
        raise ValueError("Empty physical selection")
    key = (lambda v: abs(v[0])) if kind == "max_abs" else (lambda v: v[0])
    value, row, field = (min if kind == "min" else max)(values, key=key)
    return {"value": value, "field": field, "case_id": row["case_id"],
            "time_s": float(row["time_s"]), "sample_location": row["sample_location"],
            "applicable_values": len(values)}


def collect(artifacts: Path, core) -> dict:
    provenance = verify_execution_record(artifacts)
    samples = read_rows(artifacts / "sample_audit.csv")
    events = read_rows(artifacts / "post_transition_audit.csv")
    summary = json.loads((artifacts / "summary.json").read_text())
    if summary["overall_status"] != "PASS" or summary["cinder_version"] != "1.1.2":
        raise ValueError("The selected publication evidence requires a passing 1.1.2 audit")
    saved_spec = artifacts / "execution_inputs/results/cinder-v1.1.2/studies/mechanical-invariants/study.json"
    guards = json.loads(saved_spec.read_text())["review_guards"]
    expected = [cid for ids in CASE_GROUPS.values() for cid in ids]
    if len(set(expected)) != len(expected) or set(expected) != {r["case_id"] for r in samples}:
        raise ValueError("Manuscript case table does not enumerate the selected audit")
    if len(samples) != summary["audited_samples"] or len(events) != summary["transitions"]:
        raise ValueError("Evidence/summary counts disagree")
    for row in samples + events:
        if "successor_exists" in row and not row["successor_exists"]:
            raise ValueError("Missing exact successor")
        failures = core.hard_row_failures(row, guards)
        if failures:
            raise ValueError(f"{row['case_id']}: {failures}")
    for filename in ("coverage_matrix.csv", "negative_controls.csv", "classifier_controls.csv"):
        rr = read_rows(artifacts / filename)
        key = "covered" if filename == "coverage_matrix.csv" else "pass"
        if not rr or not all(r[key] for r in rr):
            raise ValueError(f"Failed {filename}")
    definitions = read_rows(artifacts / "case_definitions.csv")
    selected_definitions = {r["case_id"]: r for r in definitions if r["case_id"] in expected}
    for cid, row in selected_definitions.items():
        if row.get("completed") not in ("", "True", None):
            raise ValueError(f"Incomplete case: {cid}")
    if summary["static_rest_max_state_drift"] != 0:
        raise ValueError("Update the stationary-case interpretation")

    rows = samples + events  # No interpolation, endpoint deduplication or thinning.
    engaged = [r for r in rows if r["engagement"] == "engaged"]
    deadzone = [r for r in rows if r["engagement"] != "engaged"]
    supported = [r for r in rows if r["shift_constraint"] in ("lower_stop", "low_ratio_seat", "upper_stop")]
    metrics = {}
    for name, fields, subset, kind, mask in (
        ("sticking_speed", ["vrel_m_s"], rows, "max_abs", STICKING),
        ("sticking_acceleration", ["arel_m_s2"], rows, "max_abs", STICKING),
        ("static_margin", ["static_margin"], rows, "min", STICKING),
        ("sliding_pair_power", ["slip_pair_power_W"], rows, "max", SLIDING),
        ("belt_tension", ["belt_min_tension_N"], engaged, "min", None),
        ("primary_local_normal", ["primary_min_dnormal_dtheta_N_per_rad"], engaged, "min", None),
        ("secondary_local_normal", ["secondary_min_dnormal_dtheta_N_per_rad"], engaged, "min", None),
        ("belt_length", ["belt_length_residual_m"], engaged, "max_abs", None),
        ("raw_equation_component_bound", ["closure_max_abs_residual"], engaged, "max_abs", None),
        ("scaled_equations", ["closure_max_scaled_residual"], engaged, "max_abs", None),
        ("field_integral", ["primary_field_normal_residual_N", "secondary_field_normal_residual_N"], engaged, "max_abs", None),
        ("supported_speed", ["shift_speed_m_s"], supported, "max_abs", None),
        ("supported_acceleration", ["fixed_shift_acceleration_m_s2"], supported, "max_abs", None),
        ("deadzone_lock_speed", ["deadzone_secondary_lock_speed_residual_m_s"], deadzone, "max_abs", None),
        ("deadzone_lock_acceleration", ["deadzone_secondary_lock_acceleration_residual_m_s2"], deadzone, "max_abs", None),
    ):
        metrics[name] = extremum(numbers(subset, fields, interfaces=mask), kind)
    reaction_fields = {"lower_stop": "deadzone_lower_stop_reaction_N",
                       "low_ratio_seat": "low_ratio_seat_reaction_N", "upper_stop": "upper_stop_reaction_N"}
    metrics["stop_reaction"] = extremum(
        ((float(r[reaction_fields[r["shift_constraint"]]]), r, reaction_fields[r["shift_constraint"]])
         for r in supported), "min")

    # The saved exact-successor table retains a maximum over matrix rows, not
    # individual row residuals. Do not mislabel that mixed-unit maximum as a
    # force. A conservative bound of 4e-11 applies separately to EVERY raw
    # component, hence to force rows in N and torque rows in N m. It is not
    # claimed to be either unit-specific maximum. The sampled per-equation
    # residuals below retain their actual maxima and explicit physical units.
    equation_rows = read_rows(artifacts / "closure_equation_residuals.csv")
    if {r["equation"] for r in equation_rows} != set(EQUATION_UNITS):
        raise ValueError("Recheck units for the changed equation set")
    equation_extrema = {}
    for eq, unit in EQUATION_UNITS.items():
        rr = [r for r in equation_rows if r["equation"] == eq]
        r = max(rr, key=lambda r: abs(float(r["residual"])))
        equation_extrema[eq] = {"value": float(r["residual"]), "unit": unit,
                                "case_id": r["case_id"], "time_s": float(r["time_s"])}
    if abs(metrics["raw_equation_component_bound"]["value"]) >= 4e-11:
        raise ValueError("Manuscript force/torque upper bound is no longer valid")

    cases = []
    for group, ids in CASE_GROUPS.items():
        for cid in ids:
            mine = [r for r in samples if r["case_id"] == cid]
            cases.append({"group": group, "case_id": cid,
                          "duration_s": max(float(r["time_s"]) for r in mine),
                          "saved_evaluations": len(mine),
                          "events": sum(r["case_id"] == cid for r in events)})
    # These windows are displayed in the case table, not arbitrary plot horizons.
    windows = {"Rest": .05, "Primary disengaged": 0, "Both contacts sticking": .03,
               "One contact sliding": .03, "Both contacts sliding": .03,
               "Free shifting": .02, "Boundary arrivals": .03, "Vehicle acceleration": 10}
    if any(not math.isclose(c["duration_s"], windows[c["group"]], abs_tol=1e-13) for c in cases):
        raise ValueError("Update the manuscript case windows")
    geometry = read_rows(artifacts / "geometry_domain_audit.csv")
    if len(geometry) != summary["geometry_points"] or not all(
        r["finite_geometry"] and r["positive_geometry"] for r in geometry
    ):
        raise ValueError("Geometry census is incomplete or inadmissible")
    for fields, limit in (
        (["belt_length_residual_m"], guards["belt_length_residual_m"]),
        (["primary_d1_fd_residual", "secondary_d1_fd_residual"], guards["geometry_first_derivative_fd_residual"]),
        (["primary_d2_fd_residual", "secondary_d2_fd_residual"], guards["geometry_second_derivative_fd_residual_per_m"]),
    ):
        values = [float(r[f]) for r in geometry for f in fields if math.isfinite(float(r[f]))]
        if not values or max(abs(v) for v in values) > limit:
            raise ValueError(f"Geometry check failed: {fields}")
    for r in geometry:
        if r["region"] == "deadzone" and max(abs(float(r[f])) for f in (
            "primary_d_effective_ds", "primary_d2_effective_ds2", "secondary_d_effective_ds", "secondary_d2_effective_ds2"
        )) > guards["deadzone_radius_derivative_abs"]:
            raise ValueError("Deadzone radius derivative check failed")
    return {
        "run_id": provenance["run_id"], "mechanics_commit": provenance["mechanics_commit"],
        "cases": cases, "metrics": metrics, "sampled_equation_extrema": equation_extrema,
        "counts_for_reproduction_only": {"selected_cases": len(cases), "saved_evaluations": len(samples),
             "exact_outgoing_states": len(events), "overlapping_coverage_tags": len(read_rows(artifacts / "coverage_matrix.csv")),
             "geometry_evaluations": len(geometry)},
        "guards": guards,
        "scope": "Selected admissible continuations; not a rate over attempted inputs or an all-time proof.",
        "masks": {"contact_fields": "engaged only", "sticking": STICKING, "sliding": SLIDING,
             "slip_direction": "old segment_end sign test not applied; exact outgoing state is checked",
             "extrema": "all applicable saved segment states plus exact outgoing states; signed values retained"},
    }


def tex_number(x: float) -> str:
    return f"{x:.3g}"


def main(artifacts: Path, output: Path, core) -> dict:
    evidence = collect(artifacts, core)
    output.mkdir(parents=True, exist_ok=True)
    m = evidence["metrics"]
    fields = {
        "CinderStickSpeedMM": ("sticking_speed", 1000, True),
        "CinderStickAcceleration": ("sticking_acceleration", 1, True),
        "CinderStaticMargin": ("static_margin", 1, False),
        "CinderSlidingPower": ("sliding_pair_power", 1, False),
        "CinderBeltTension": ("belt_tension", 1, False),
        "CinderPrimaryLocal": ("primary_local_normal", 1, False),
        "CinderSecondaryLocal": ("secondary_local_normal", 1, False),
        "CinderStopReaction": ("stop_reaction", 1, False),
        "CinderBeltLength": ("belt_length", 1, True),
        "CinderDeadzoneSpeed": ("deadzone_lock_speed", 1, True),
        "CinderSupportedSpeed": ("supported_speed", 1, True),
    }
    lines = ["% Generated by mechanical-invariants/run.py; see reader_evidence.json."]
    for name, (key, factor, absolute) in fields.items():
        value = m[key]["value"] * factor
        value = abs(value) if absolute else value
        lines.append("\\providecommand{\\" + name + "}{" + tex_number(value) + "}")
    (output / "verification_values.tex").write_text("\n".join(lines) + "\n")
    (output / "reader_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    record = {"run_id": evidence["run_id"], "generator_sha256": digest(Path(__file__)),
              "audit_identity_sha256": digest(artifacts / "execution_provenance.json"),
              "outputs": {p: digest(output / p) for p in ("verification_values.tex", "reader_evidence.json")}}
    (output / "reader_evidence_provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    return evidence
