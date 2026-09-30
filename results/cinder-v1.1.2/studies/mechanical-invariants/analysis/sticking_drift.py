"""Explain the largest retained sticking-speed drift using one frozen case.

The canonical --check-stick-drift command replays the selected 30 ms case at
its archived settings, then tightens rtol and atol by ten with the step cap
unchanged. This is a local check of velocity-constraint drift, not a new
operating-domain sweep or a global convergence result.
"""
from __future__ import annotations

import csv
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from .execution_record import digest, verify_execution_record
from .reader_evidence import STICKING


def _read(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def _signature(trace):
    def mode(m):
        c = m.cvt
        r = c.contact_regime
        return [c.engagement.value, c.shift_constraint.value,
                r.mode.value if r else "",
                r.primary_slip_direction.value if r and r.primary_slip_direction else None,
                r.secondary_slip_direction.value if r and r.secondary_slip_direction else None]
    return [{"events": list(r.fired_event_names), "reason": r.transition.reason,
             "before": mode(r.previous_mode), "after": mode(r.transition.next_mode)}
            for r in trace.transitions]


def main(artifacts: Path, output: Path) -> dict:
    current_release = Path(__file__).resolve().parents[3]
    subprocess.run([sys.executable, str(current_release / "verify_environment.py")], check=True)
    identity = verify_execution_record(artifacts)
    release = artifacts / "execution_inputs/results/cinder-v1.1.2"
    entry_path = release / "studies/mechanical-invariants/run.py"
    spec = importlib.util.spec_from_file_location("archived_drift_entry", entry_path)
    entry = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = entry
    spec.loader.exec_module(entry)
    core = entry.core
    # The entry point imports the Results defaults before this archived core.
    # Confirm those modules still have the exact executed bytes.
    for name, expected in identity["input_sha256"].items():
        prefix = "results/cinder-v1.1.2/defaults/"
        if name.startswith(prefix):
            actual = current_release / "defaults" / name.removeprefix(prefix)
            if digest(actual) != expected:
                raise ValueError(f"Results default differs from archived input: {name}")

    saved = _read(artifacts / "sample_audit.csv")
    successors = _read(artifacts / "post_transition_audit.csv")
    applicable = [(abs(float(r[p + "_vrel_m_s"])), r, p)
                  for r in saved + successors if r["engagement"] == "engaged"
                  for p in STICKING[r["contact_mode"]]]
    value, largest, interface = max(applicable, key=lambda x: x[0])
    case_id = largest["case_id"]
    study = core.load_json(core.SPEC_FILE)
    library, _ = core.resolve_case_library(study)
    hydrated = core.hydrate_case_recipes(study, library)
    decoded, _, _ = core.load_frozen_reference(hydrated)
    definition = next(r for r in _read(artifacts / "case_definitions.csv")
                      if r["case_id"] == case_id)
    seeds = library["targeted_contact_states"].get(case_id, [])
    seed = next((s for s in seeds if s["id"] == definition["targeted_seed_id"]), None)
    if seed is None:
        raise ValueError("Largest drift no longer belongs to the reviewed targeted case")
    # The anchor search has its own finer sampling and step cap. The retained
    # audit reruns selected contact cases through core.run_found_case using
    # bench_search, then samples that trace with bench_search.audit_time_step_s.
    search = hydrated["bench_search"]
    cfg = {**search["integrator"],
           "duration_s": search["contact_case_duration_s"],
           "audit_time_step_s": search["audit_time_step_s"]}
    guards = study["review_guards"]
    request = next(r for r in core.contact_requests(library) if r.case_id == case_id)
    found, attempt = entry._try_targeted_state(decoded, request, guards, seed, library)
    if found is None:
        raise ValueError(f"Archived anchor selection failed: {attempt}")
    # The original wrapper first checks the anchor trajectory. That leaves
    # continuation guesses in the contact evaluator. Preserve that numerical
    # history, then give nominal and tighter runs identical independent copies.
    output.mkdir(parents=True, exist_ok=True)
    runs = {}
    for name, factor in (("nominal", 1.0), ("tighter", 0.1)):
        settings = {**cfg, "relative_tolerance": cfg["relative_tolerance"] * factor,
                    "absolute_tolerance": cfg["absolute_tolerance"] * factor}
        prepared = copy.deepcopy(found)
        system, initial, mode = prepared.system, prepared.initial_state, prepared.initial_mode
        trace = system.integrate_trace(time_span=(0.0, cfg["duration_s"]),
            initial_state=initial, initial_mode=mode, settings=core.integration_settings(settings))
        if not trace.completed:
            raise ValueError(f"{name} did not complete: {trace.termination_reason}")
        samples = core.build_trace_samples(case_id, trace, cfg["audit_time_step_s"])
        samples += [core.AuditSample(case_id, r.time, np.asarray(r.post_transition_state),
                     r.transition.next_mode, "post_transition_exact") for r in trace.transitions]
        records = []
        audit_rows = []
        for sample in samples:
            row, _, _ = core.inspect_sample(system, sample)
            failures = core.hard_row_failures(row, guards)
            if failures:
                raise ValueError(f"{name}/{sample.time}: {failures}")
            audit_rows.append(row)
            state = core.cvt_state_from_full(system, sample.full_state)
            for p in STICKING.get(row["contact_mode"], ()):
                slip = float(row[p + "_vrel_m_s"])
                belt = float(state.belt_speed)
                surface = belt - slip
                records.append({"case_id": case_id, "time_s": sample.time,
                    "location": sample.sample_location, "contact_mode": row["contact_mode"],
                    "shift_constraint": row["shift_constraint"], "interface": p,
                    "primary_angular_speed_rad_s": state.primary_angular_speed,
                    "secondary_angular_speed_rad_s": state.secondary_angular_speed,
                    "belt_speed_m_s": belt, "surface_speed_m_s": surface,
                    "shift_m": state.shift_position, "shift_speed_m_s": state.shift_speed,
                    "relative_speed_m_s": slip,
                    "relative_acceleration_m_s2": row[p + "_arel_m_s2"],
                    "speed_mismatch_fraction": abs(slip) / max(abs(belt), abs(surface))
                        if max(abs(belt), abs(surface)) > 0 else 0.0})
        peak = max(records, key=lambda r: abs(r["relative_speed_m_s"]))
        if name == "nominal":
            expected_rows = [r for r in saved + successors if r["case_id"] == case_id]
            replay_rows = audit_rows
            if len(expected_rows) != len(replay_rows):
                raise ValueError("Nominal replay does not reproduce the retained sampling")
            differences = {}
            for old, new in zip(expected_rows, replay_rows):
                for key in ("engagement", "shift_constraint", "contact_mode", "sample_location"):
                    if old[key] != new[key]:
                        raise ValueError(f"Nominal replay differs in {key}")
                for key in ("time_s", "shift_m", "shift_speed_m_s", "primary_vrel_m_s", "secondary_vrel_m_s"):
                    if not np.isclose(float(old[key]), new[key], atol=1e-10, rtol=1e-8, equal_nan=True):
                        raise ValueError(f"Nominal replay differs in {key}: {old[key]} / {new[key]}")
                    difference = abs(float(old[key]) - new[key])
                    if np.isfinite(difference):
                        differences[key] = max(differences.get(key, 0.0), difference)
            original_events = [r for r in successors if r["case_id"] == case_id]
            if len(original_events) != len(trace.transitions):
                raise ValueError("Nominal transition count differs from retained audit")
            for old, new in zip(original_events, trace.transitions):
                if old["fired_event_names"] != "|".join(new.fired_event_names) or old["transition_reason"] != new.transition.reason:
                    raise ValueError("Nominal transition differs from retained audit")
            if not np.isclose(abs(peak["relative_speed_m_s"]), value, atol=1e-10, rtol=1e-8):
                raise ValueError("Nominal peak differs from the complete retained audit")
        csv_path = output / f"sticking_drift_{name}.csv"
        core.write_rows(csv_path, records)
        runs[name] = {"settings": settings, "completed": True, "sampled_peak": peak,
                      "event_signature": _signature(trace), "guard_failures": [],
                      "csv_sha256": digest(csv_path), "csv": csv_path.name}
    report = {"case_id": case_id, "reference_run_id": identity["run_id"],
        "mechanics_commit": identity["mechanics_commit"], "packages": identity["packages"],
        "generator_sha256": digest(Path(__file__)),
        "input_identity_sha256": digest(artifacts / "execution_provenance.json"),
        "initial_case": seed, "audit_speed_limit_m_s": guards["stick_velocity_drift_m_s"],
        "anchor_preparation": {"settings": library["targeted_contact_state_integrator"],
                               "attempt": attempt,
                               "role": "Reproduce the archived selection stage and contact-solver continuation guesses before either comparison run."},
        "nominal_reproduces_retained_samples": True, "runs": runs,
        "retained_replay_comparison": {"sample_and_outgoing_rows": len(expected_rows),
                                       "maximum_absolute_differences": differences,
                                       "absolute_tolerance": 1e-10, "relative_tolerance": 1e-8},
        "same_event_signature": runs["nominal"]["event_signature"] == runs["tighter"]["event_signature"],
        "peak_drift_ratio_tighter_to_nominal": abs(runs["tighter"]["sampled_peak"]["relative_speed_m_s"]) / value,
        "scope": "One selected 30 ms case, sampled within native segments and at exact event sides. This is not a global refinement or an error bound on the ODE solution.",
        "threshold_meaning": "An audit reporting guard; not a friction-law parameter or a velocity-band definition of sticking."}
    (output / "sticking_drift_check.json").write_text(json.dumps(report, indent=2) + "\n")
    n, t = (runs[k]["sampled_peak"] for k in ("nominal", "tighter"))
    numbers = {"CinderDriftPeakBeltSpeed": abs(n["belt_speed_m_s"]),
               "CinderDriftPeakFraction": n["speed_mismatch_fraction"],
               "CinderDriftRefinedMM": abs(t["relative_speed_m_s"]) * 1000,
               "CinderDriftGuardPercent": 100 * guards["stick_velocity_drift_m_s"] / abs(n["belt_speed_m_s"])}
    lines = ["% Generated by mechanical-invariants/run.py --check-stick-drift."]
    lines += ["\\providecommand{\\" + k + "}{" + f"{v:.3g}" + "}" for k, v in numbers.items()]
    (output / "sticking_drift_values.tex").write_text("\n".join(lines) + "\n")
    return report
