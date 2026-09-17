"""Static/release checks for the exploratory helix-topology study."""
from __future__ import annotations

import json
from pathlib import Path
import sys

STUDY_ROOT = Path(__file__).resolve().parent
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from metrics import (
    contact_topology_metrics,
    integrate_negative_part,
    integrate_sign_partition,
)  # noqa: E402
from study_support import (  # noqa: E402
    RELEASE_ROOT,
    load_json,
    materialize_tagged_upstream,
    verify_environment,
)


def main() -> int:
    verify_environment()
    launch_tools = materialize_tagged_upstream(clean=True)

    required = (
        STUDY_ROOT / "README.md",
        STUDY_ROOT / "FORMULATION_LINKAGE.md",
        STUDY_ROOT / "study.json",
        STUDY_ROOT / "upstream_manifest.json",
        STUDY_ROOT / "metrics.py",
        STUDY_ROOT / "experiments" / "run_reaction_map.py",
        STUDY_ROOT / "experiments" / "run_forward_control.py",
        STUDY_ROOT / "experiments" / "run_stress_screen.py",
        STUDY_ROOT / "experiments" / "run_scenario_discovery.py",
        STUDY_ROOT / "experiments" / "run_liftoff_envelope.py",
        STUDY_ROOT / "experiments" / "run_dynamic_only_liftoff.py",
        STUDY_ROOT / "experiments" / "run_transient_severity_race.py",
        RELEASE_ROOT / "defaults" / "reference_model" / "slotted_helix.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Missing study files: " + ", ".join(missing))

    study = load_json(STUDY_ROOT / "study.json")
    if study["reference_topology"]["name"] != "bilateral_zero_clearance_slot":
        raise RuntimeError("Study reference topology is not the shared slotted policy")
    e5 = study["experiments"]["liftoff_envelope_refinement"]
    if e5["status"] != "implemented":
        raise RuntimeError("E5 lift-off envelope refinement must be implemented")
    e55 = study["experiments"]["dynamic_only_liftoff"]
    if e55["status"] != "implemented":
        raise RuntimeError("E5.5 dynamic-only lift-off study must be implemented")
    e56 = study["experiments"]["transient_severity_race"]
    if e56["status"] != "implemented":
        raise RuntimeError("E5.6 transient severity race must be implemented")
    e6 = study["experiments"]["selected_flank_comparator"]
    if e6["status"] != "not_implemented_until_detached_topology_is_derived":
        raise RuntimeError("E6 must remain gated until detached helix mechanics exist")

    # Pure metric smoke checks.
    neg = integrate_negative_part([0.0, 1.0, 2.0], [1.0, -1.0, 1.0])
    if abs(neg.duration_s - 1.0) > 1.0e-12:
        raise RuntimeError("Negative-part duration integration failed")
    metrics = contact_topology_metrics(
        [
            {"time_s": 0.0, "helix_reacted_torque_margin_Nm": 1.0, "helix_full_reaction_force_N": 10.0},
            {"time_s": 1.0, "helix_reacted_torque_margin_Nm": -1.0, "helix_full_reaction_force_N": -10.0},
            {"time_s": 2.0, "helix_reacted_torque_margin_Nm": 1.0, "helix_full_reaction_force_N": 10.0},
        ],
        case_start_s=0.0,
        case_end_s=2.0,
    )
    if metrics["zero_crossing_count"] != 2:
        raise RuntimeError("Topology crossing count smoke check failed")
    partition = integrate_sign_partition(
        [0.0, 1.0, 2.0],
        [1.0, -1.0, 1.0],
        [2.0, 1.0, 2.0],
    )
    if abs(partition.full_negative_qs_positive_s - 1.0) > 1.0e-12:
        raise RuntimeError("Dynamic-only sign partition smoke check failed")

    payload = {
        "status": "ok",
        "study": study["study"],
        "cinder_version": study["cinder_version"],
        "reference_topology": study["reference_topology"]["name"],
        "materialized_launch_tools": str(launch_tools),
        "implemented_stages": ["E1", "E2", "E3", "E4", "E5", "E5.5", "E5.6"],
        "gated_stages": ["E6", "E7"],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
