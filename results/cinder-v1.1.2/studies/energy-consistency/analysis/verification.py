"""Check publication quantities against the complete retained energy evidence.

This is a postprocessing audit, not an independent implementation of mechanics.
No event-side averaging, clipping, drift-work correction or regime filtering is
allowed. The native transition ledger is checked against both trace endpoints.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

STATE = ("omega_p_rad_s", "omega_s_rad_s", "belt_speed_m_s",
         "shift_position_m", "shift_speed_m_per_s")
STRINGS = {"mode", "reason", "previous_mode", "next_mode", "sample_location"}


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"No evidence rows: {path.name}")
    for row in rows:
        for key, value in row.items():
            if key in STRINGS or value == "":
                continue
            if key == "has_capture_projection":
                if value not in ("True", "False"):
                    raise ValueError("Unrecognized projection flag")
                row[key] = value == "True"
            else:
                row[key] = float(value)
                if not np.isfinite(row[key]):
                    raise ValueError(f"Nonfinite value: {path.name}/{key}")
    return rows


def close(actual, expected, name, *, atol=1e-8, rtol=2e-12):
    if not np.allclose(actual, expected, atol=atol, rtol=rtol):
        raise ValueError(f"Evidence mismatch ({name}): {actual} != {expected}")


def trace_checks(trace, transitions, events, headline):
    groups = {}
    for row in trace:
        groups.setdefault(int(row["segment_index"]), []).append(row)
        close(row["external_work_J"], row["primary_boundary_work_J"] + row["secondary_boundary_work_J"], "signed work")
        close(row["stored_energy_change_J"], row["kinetic_energy_change_J"] + row["potential_energy_change_J"], "stored energy")
        close(row["slip_dissipation_J"], row["primary_slip_dissipation_J"] + row["secondary_slip_dissipation_J"], "slip channels")
        accounted = row["stored_energy_change_J"] + row["slip_dissipation_J"] + row["impact_capture_dissipation_J"]
        close(row["accounted_energy_J"], accounted, "accounted energy")
        close(row["balance_residual_J"], row["external_work_J"] - accounted, "signed residual")
    if list(groups) != list(range(len(transitions) + 1)):
        raise ValueError("Missing or unordered continuous segments")
    close([trace[0]["time_s"], trace[-1]["time_s"]], [0, 10], "audit interval", atol=0)
    continuous = 0.0
    for rows in groups.values():
        if rows[0]["sample_location"] != "segment_start" or rows[-1]["sample_location"] != "segment_end":
            raise ValueError("Missing one-sided native endpoints")
        if not np.all(np.diff([r["time_s"] for r in rows]) > 0):
            raise ValueError("Non-increasing time within a segment")
        if len({r["mode"] for r in rows}) != 1:
            raise ValueError("Mode changes inside a continuous segment")
        if len({r["impact_capture_dissipation_J"] for r in rows}) != 1:
            raise ValueError("Discrete capture treated as continuous loss")
        for key in ("primary_slip_dissipation_J", "secondary_slip_dissipation_J"):
            if np.min(np.diff([r[key] for r in rows])) < -1e-9:
                raise ValueError("Negative kinetic-slip increment")
        a, b = rows[0], rows[-1]
        continuous += (b["external_work_J"] - a["external_work_J"]
                       - b["stored_energy_change_J"] + a["stored_energy_change_J"]
                       - b["slip_dissipation_J"] + a["slip_dissipation_J"])
    for i, event in enumerate(transitions):
        if int(event["transition_index"]) != i:
            raise ValueError("Unordered native transition records")
        a, b = groups[i][-1], groups[i+1][0]
        close([a["time_s"], b["time_s"]], event["time_s"], "equal-time native sides", atol=0, rtol=0)
        if (a["mode"], b["mode"]) != (event["previous_mode"], event["next_mode"]):
            raise ValueError("Event-side mode mismatch")
        for key in STATE:
            close([a[key], b[key]], [event[f"pre_{key}"], event[f"post_{key}"]], "native " + key, atol=0, rtol=0)
        for key in ("primary_boundary_work_J", "secondary_boundary_work_J",
                    "primary_slip_dissipation_J", "secondary_slip_dissipation_J"):
            close(a[key], b[key], "no quadrature across reset: " + key, atol=0, rtol=0)
        drop = event["pre_stored_energy_J"] - event["post_stored_energy_J"]
        close(drop, event["exact_stored_energy_drop_J"], "native energy drop")
        close(a["stored_energy_change_J"] - b["stored_energy_change_J"], drop, "trace/event drop")
        loss = event["recorded_impact_loss_J"]
        close(b["impact_capture_dissipation_J"] - a["impact_capture_dissipation_J"], loss, "capture increment")
        close(drop - loss, event["event_energy_defect_J"], "capture energy identity", atol=1e-10)
        close(b["balance_residual_J"] - a["balance_residual_J"], drop - loss, "residual at reset")
    projected = [r for r in transitions if r["has_capture_projection"]]
    if projected != events:
        raise ValueError("Capture subset does not match complete native ledger")
    close(sum(r["recorded_impact_loss_J"] for r in transitions), trace[-1]["impact_capture_dissipation_J"], "total capture loss")
    close(continuous + sum(r["event_energy_defect_J"] for r in transitions), trace[-1]["balance_residual_J"], "continuous + discrete closure")
    for key in ("external_work_J", "stored_energy_change_J", "kinetic_energy_change_J",
                "potential_energy_change_J", "primary_slip_dissipation_J", "secondary_slip_dissipation_J",
                "slip_dissipation_J", "impact_capture_dissipation_J", "balance_residual_J"):
        close(trace[-1][key], headline["final_" + key], "summary " + key)
    fraction = abs(trace[-1]["balance_residual_J"]) / max(abs(trace[-1]["external_work_J"]), 1.0)
    close(fraction, headline["final_balance_fraction_of_abs_external_work"], "residual fraction", atol=1e-15)
    close(max(abs(r["balance_residual_J"]) for r in trace),
          headline["max_abs_balance_residual_J"], "maximum sampled residual", atol=1e-12)
    return groups, continuous, fraction


def verify(artifacts: Path, spec: dict) -> tuple[dict, dict]:
    summary = json.loads((artifacts / "summary.json").read_text())
    if summary["status"] != "PASS" or summary["cinder_version"] != "1.1.2":
        raise ValueError("Canonical frozen study did not pass")
    traces, transitions, captures, groups, continuous, fractions = {}, {}, {}, {}, {}, {}
    for label, suffix in (("nominal", ""), ("tight", "_tight")):
        traces[label] = read_rows(artifacts / f"energy_trace{suffix}_finest.csv")
        transitions[label] = read_rows(artifacts / f"native_transitions{suffix}.csv")
        captures[label] = read_rows(artifacts / f"event_energy_balance{suffix}.csv")
        groups[label], continuous[label], fractions[label] = trace_checks(
            traces[label], transitions[label], captures[label], summary[label + "_energy_balance"])
    segments = read_rows(artifacts / "continuous_segment_balance.csv")
    quadrature = read_rows(artifacts / "quadrature_convergence.csv")
    if len(segments) != len(groups["nominal"]):
        raise ValueError("Continuous ledger has a different segment count")
    close([r["audit_step_s"] for r in quadrature], spec["audit_quadrature_steps_s"], "four audit grids", atol=0)
    for q in quadrature:
        tag = f'{q["audit_step_s"]:.9g}'.replace(".", "p")
        total = 0.0
        for i, segment in enumerate(segments):
            a, b = groups["nominal"][i][0], groups["nominal"][i][-1]
            close([segment["start_time_s"], segment["end_time_s"]], [a["time_s"], b["time_s"]], "segment interval", atol=0)
            if segment["mode"] != a["mode"] or int(segment["segment_index"]) != i:
                raise ValueError("Segment identity mismatch")
            delta = segment["stored_energy_end_J"] - segment["stored_energy_start_J"]
            close(delta, segment["stored_energy_delta_J"], "exact segment storage")
            close(delta, b["stored_energy_change_J"] - a["stored_energy_change_J"], "native segment energy")
            w, slip = segment[f"external_work_h_{tag}_J"], segment[f"slip_dissipation_h_{tag}_J"]
            defect = w - delta - slip
            close(defect, segment[f"raw_defect_h_{tag}_J"], "segment defect")
            total += defect
            if q is quadrature[-1]:
                close(w, b["external_work_J"] - a["external_work_J"], "finest trace quadrature")
                close(slip, b["slip_dissipation_J"] - a["slip_dissipation_J"], "finest slip quadrature")
        close(total, q["sum_continuous_raw_defect_J"], "summed continuous defect")
    close(continuous["nominal"], quadrature[-1]["sum_continuous_raw_defect_J"], "global continuous defect")
    coarse, fine = quadrature[-2:]
    ratio = coarse["audit_step_s"] / fine["audit_step_s"]
    extrapolate = (ratio**2 * fine["sum_continuous_raw_defect_J"] - coarse["sum_continuous_raw_defect_J"]) / (ratio**2 - 1)
    for row in quadrature:
        close(extrapolate, row["richardson_zero_step_estimate_J"], "two-finest-grid extrapolate", atol=1e-12)
    final = {k: np.array([rows[-1][name] for name in STATE]) for k, rows in traces.items()}
    delta = final["tight"] - final["nominal"]
    scale = np.maximum(np.maximum(np.abs(final["nominal"]), np.abs(final["tight"])), [1, 1, 1, .001, .001])
    state_error = float(np.max(np.abs(delta) / scale))
    close(state_error, summary["solver_refinement"]["max_normalized_final_state_delta"], "final-state comparison", atol=1e-15)
    close(delta, list(summary["solver_refinement"]["final_state_deltas"].values()), "signed state differences", atol=1e-15)
    tag = f'{fine["audit_step_s"]:.9g}'.replace(".", "p")
    stick_work = sum(r[f"stick_pair_work_h_{tag}_J"] for r in segments)
    close(stick_work, summary["stick_invariant_diagnostic"]["signed_stick_pair_work_J"], "separate sticking drift")
    guards = {}
    stop_checks = {}
    for label in traces:
        stops = [r for r in captures[label]
                 if r["reason"] == "upper_stop_reached_perfectly_inelastic_impact"]
        if len(stops) != 1:
            raise ValueError("Expected one actual upper-stop capture for the detail view")
        event = stops[0]
        if event["post_shift_speed_m_per_s"] != 0 or event["pre_shift_speed_m_per_s"] <= 0:
            raise ValueError("Upper-stop detail does not describe arrival and arrest")
        i = int(event["transition_index"])
        a, b = groups[label][i][-1], groups[label][i+1][0]
        stop_checks[label] = {
            "time_s": event["time_s"],
            "recorded_loss_J": event["recorded_impact_loss_J"],
            "native_residual_jump_J": b["balance_residual_J"] - a["balance_residual_J"],
            "detail_window_from_native_event_ms": [-20, 40],
        }
    limits = spec["acceptance_criteria"]
    for label in traces:
        events = captures[label]
        guards[label] = {
            "ten_seconds": traces[label][-1]["time_s"] == 10,
            "balance_fraction": fractions[label] <= limits["max_final_balance_fraction_of_abs_external_work"],
            "event_energy": max(abs(r["event_energy_defect_J"]) for r in events) <= limits["max_abs_event_energy_defect_J"],
            "momentum": max(abs(r["momentum_residual"]) for r in events) <= limits["max_impact_momentum_residual"],
            "constraint": max(abs(r["constraint_residual"]) for r in events) <= limits["max_impact_constraint_residual"],
            "nonnegative_capture": min(r["recorded_impact_loss_J"] for r in events) >= -limits["negative_impact_loss_tolerance_J"],
        }
    guards["refinement"] = {
        "final_state": state_error <= limits["max_normalized_final_state_delta"],
        "transition_count": len(transitions["nominal"]) == len(transitions["tight"]),
        "continuous_defect_ratio": abs(fine["sum_continuous_raw_defect_J"]) / max(abs(coarse["sum_continuous_raw_defect_J"]), 1e-15) <= limits["max_finest_to_previous_abs_continuous_defect_ratio"],
    }
    if not all(v for family in guards.values() for v in family.values()):
        raise ValueError(f"Recomputed energy guards failed: {guards}")
    if not all(row["passed"] for row in summary["acceptance_checks"]):
        raise ValueError("Recorded canonical guard failed")
    checks = {
        "trace_rows": {k: len(v) for k, v in traces.items()},
        "native_transitions": {k: len(v) for k, v in transitions.items()},
        "capture_projections": {k: len(v) for k, v in captures.items()},
        "all_native_sides_checked": True,
        "energy_identity_at_every_row_checked": True,
        "quadrature_and_event_ledgers_checked": True,
        "guards_recomputed": guards,
        "nominal_continuous_defect_J": continuous["nominal"],
        "richardson_zero_spacing_estimate_J": extrapolate,
        "max_normalized_final_state_delta": state_error,
        "signed_stick_pair_work_J_diagnostic_only": stick_work,
        "upper_stop_detail": stop_checks,
    }
    data = {"traces": traces, "transitions": transitions, "captures": captures,
            "groups": groups, "segments": segments, "quadrature": quadrature, "summary": summary}
    return data, checks
