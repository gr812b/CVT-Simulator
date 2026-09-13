"""Canonical results entry point for the v1.1.2 mechanical-invariants audit.

The large ``run.py`` remains the core audit implementation.  This wrapper keeps
results-only reference-model policy local to this study process:

1. public simulation documents are decoded with the shared results helper, which
   converts only the secondary helix force law to the zero-clearance bilateral
   slot topology;
2. the two rare-contact reproduction anchors are tried before the ordinary
   deterministic contact search; and
3. reference-model provenance is written beside the generated artifacts.

There is no interpreter-startup hook, environment variable, package patch, or
installation step.  Other studies are unaffected unless they explicitly use the
shared results decoder.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
RELEASE_ROOT = HERE.parents[1]
if str(RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(RELEASE_ROOT))

from support.reference_model import (
    decode_results_simulation_case_document,
    reference_model_status,
    write_reference_model_provenance,
)

CORE_PATH = HERE / "run.py"
spec = importlib.util.spec_from_file_location("mechanical_invariants_core", CORE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load mechanical-invariants core: {CORE_PATH}")
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)
_ORIGINAL_FIND_CONTACT_CASE = core.find_contact_case


def _validate_and_decode_results(document: dict):
    validation = core.validate_simulation_case_document(document)
    if not validation.is_valid:
        for finding in validation.findings:
            print(f"[{finding.severity}] {finding.document_path or '/'}: {finding.message}")
        raise RuntimeError("Invariant-study input failed CINDER document validation.")
    return decode_results_simulation_case_document(document)


# Only this study process sees the results reference topology.
core.validate_and_decode = _validate_and_decode_results


def _load_case_library(spec_dict: dict) -> dict:
    path = (HERE / spec_dict["shared_case_library"]).resolve()
    return json.loads(path.read_text(encoding="utf-8"))


def _try_targeted_state(decoded, request, guards, seed, library):
    cfg = library["targeted_contact_state_integrator"]
    system = core.make_bench_system(
        decoded,
        primary_torque=float(seed["primary_torque_Nm"]),
        secondary_torque=float(seed["secondary_torque_Nm"]),
        primary_inertia=float(seed["primary_inertia_kg_m2"]),
        secondary_inertia=float(seed["secondary_inertia_kg_m2"]),
    )
    cvt = core.CVTState(
        float(seed["primary_speed_rad_s"]),
        float(seed["secondary_speed_rad_s"]),
        float(seed["belt_speed_m_s"]),
        float(seed["shift_position_m"]),
        float(seed["shift_speed_m_s"]),
    )
    state = core.full_state(system, cvt)
    attempt: dict[str, Any] = {
        "case_id": request.case_id,
        "search_stage": "targeted_seed",
        "targeted_seed_id": seed["id"],
        "primary_torque_Nm": seed["primary_torque_Nm"],
        "secondary_torque_Nm": seed["secondary_torque_Nm"],
        "primary_inertia_kg_m2": seed["primary_inertia_kg_m2"],
        "secondary_inertia_kg_m2": seed["secondary_inertia_kg_m2"],
        "belt_speed_m_s": seed["belt_speed_m_s"],
        "shift_speed_m_s": seed["shift_speed_m_s"],
    }
    try:
        mode = system.classify_initial_mode(state)
    except Exception as exc:
        attempt.update(accepted=False, reason=f"classification:{type(exc).__name__}:{exc}")
        return None, attempt

    row, _, _ = core.audit_sample_safe(
        system, core.AuditSample(request.case_id, 0.0, state, mode, "initial_exact")
    )
    core._attach_initial_diagnostics(attempt, row, mode)
    if not core.mode_and_directions_match(mode, request):
        observed = mode.cvt.contact_regime.mode.value if mode.cvt.contact_regime else "none"
        attempt.update(accepted=False, reason=f"mode:{observed}")
        return None, attempt
    failures = core.hard_row_failures(row, guards)
    if failures:
        attempt.update(accepted=False, reason="initial_invariant:" + "|".join(failures))
        return None, attempt

    settings = core.integration_settings(cfg)
    try:
        trace = system.integrate_trace(
            time_span=(0.0, float(cfg["duration_s"])),
            initial_state=state,
            initial_mode=mode,
            settings=settings,
        )
    except Exception as exc:
        attempt.update(accepted=False, reason=f"integration:{type(exc).__name__}:{exc}")
        return None, attempt

    dwell = float(trace.segments[0].end_time - trace.segments[0].start_time)
    attempt["requested_mode_dwell_s"] = dwell
    if dwell < float(cfg["minimum_branch_time_s"]):
        attempt.update(accepted=False, reason=f"dwell:{dwell:.3e}")
        return None, attempt

    bad: list[str] = []
    for sample in core.build_trace_samples(request.case_id, trace, float(cfg["audit_time_step_s"])):
        rr, _, _ = core.audit_sample_safe(system, sample)
        bad.extend(core.hard_row_failures(rr, guards))
    for rr in core.post_transition_rows(request.case_id, system, trace):
        if rr.get("successor_exists"):
            bad.extend(core.hard_row_failures(rr, guards))
    if bad:
        attempt.update(accepted=False, reason="dynamic_invariant:" + "|".join(sorted(set(bad))))
        return None, attempt
    if not trace.completed:
        attempt.update(accepted=False, reason="terminated:" + str(trace.termination_reason))
        return None, attempt

    attempt.update(accepted=True, reason="accepted")
    found = core.FoundCase(
        request.case_id,
        system,
        state,
        mode,
        {
            **attempt,
            "requested_contact_mode": request.mode.value,
            "requested_primary_vrel_sign": request.primary_vrel_sign,
            "requested_secondary_vrel_sign": request.secondary_vrel_sign,
            "targeted_seed_role": seed.get("role", ""),
            "targeted_seed_source": seed.get("source", ""),
        },
    )
    return found, attempt


def _find_contact_case_with_shared_anchors(decoded, request, spec_dict, guards):
    library = _load_case_library(spec_dict)
    attempts = []
    for seed in library.get("targeted_contact_states", {}).get(request.case_id, []):
        found, attempt = _try_targeted_state(decoded, request, guards, seed, library)
        attempts.append(attempt)
        if found is not None:
            return found, attempts
    found, ordinary = _ORIGINAL_FIND_CONTACT_CASE(decoded, request, spec_dict, guards)
    return found, attempts + ordinary


core.find_contact_case = _find_contact_case_with_shared_anchors


def _stamp_summary() -> None:
    decoded, _, _ = core.load_frozen_reference(
        core.hydrate_case_recipes(
            core.load_json(core.SPEC_FILE),
            _load_case_library(core.load_json(core.SPEC_FILE)),
        )
    )
    write_reference_model_provenance(
        core.ARTIFACTS,
        plant=decoded.plant,
        extra={
            "mechanical_invariants_entry_point": str(Path(__file__).name),
            "targeted_contact_states_enabled": True,
        },
    )
    summary_path = core.ARTIFACTS / "summary.json"
    if summary_path.is_file():
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        status = reference_model_status(decoded.plant)
        payload["results_reference_model"] = {
            "secondary_helix_topology": status.secondary_helix_topology,
            "policy_path": status.policy_path,
        }
        summary_path.write_text(json.dumps(payload, indent=2, allow_nan=True) + "\n", encoding="utf-8")


def main() -> int:
    code = int(core.main())
    _stamp_summary()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
