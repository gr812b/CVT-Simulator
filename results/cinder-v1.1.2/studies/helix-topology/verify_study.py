#!/usr/bin/env python3
"""Static/release checks for the maintained helix-topology study."""
from __future__ import annotations

# --- results study-local import bootstrap ---
from pathlib import Path as _ResultsPath
import sys as _results_sys

_results_file = _ResultsPath(__file__).resolve()
_results_study_root = next(
    (parent for parent in _results_file.parents if (parent / "study.json").is_file()),
    None,
)
if _results_study_root is None:
    raise RuntimeError(f"Could not locate study root for {_results_file}")
_results_release_root = _results_study_root.parents[1]
for _results_path in (str(_results_study_root), str(_results_release_root)):
    while _results_path in _results_sys.path:
        _results_sys.path.remove(_results_path)
_results_sys.path.insert(0, str(_results_release_root))
_results_sys.path.insert(0, str(_results_study_root))
# --- end results study-local import bootstrap ---


import json
from pathlib import Path
import sys

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
for _path in (str(STUDY_ROOT), str(RELEASE_ROOT)):
    while _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, str(RELEASE_ROOT))
sys.path.insert(0, str(STUDY_ROOT))

from infrastructure.metrics import (
    contact_topology_metrics,
    integrate_negative_part,
    integrate_sign_partition,
)
from infrastructure.study_support import load_json, verify_environment


def main() -> int:
    verify_environment()
    required = (
        STUDY_ROOT / "README.md",
        STUDY_ROOT / "FORMULATION_LINKAGE.md",
        STUDY_ROOT / "study.json",
        STUDY_ROOT / "infrastructure" / "study_support.py",
        STUDY_ROOT / "infrastructure" / "metrics.py",
        STUDY_ROOT / "infrastructure" / "ablation_core.py",
        STUDY_ROOT / "experiments" / "run_reaction_map.py",
        STUDY_ROOT / "experiments" / "run_forward_control.py",
        STUDY_ROOT / "experiments" / "run_stress_screen.py",
        STUDY_ROOT / "experiments" / "run_scenario_discovery.py",
        STUDY_ROOT / "experiments" / "run_liftoff_envelope.py",
        STUDY_ROOT / "experiments" / "run_dynamic_only_liftoff.py",
        STUDY_ROOT / "experiments" / "run_transient_severity_race.py",
        STUDY_ROOT / "experiments" / "run_coupled_event_chronology.py",
        STUDY_ROOT / "experiments" / "run_paired_helix_performance.py",
        RELEASE_ROOT / "defaults" / "baja" / "reference.py",
        RELEASE_ROOT / "defaults" / "reference_model" / "slotted_helix.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Missing helix study files: " + ", ".join(missing))

    study = load_json(STUDY_ROOT / "study.json")
    if study["reference_topology"]["name"] != "bilateral_zero_clearance_slot":
        raise RuntimeError("Study reference topology is not the shared slotted policy")
    for key in ("liftoff_envelope_refinement", "dynamic_only_liftoff", "transient_severity_race"):
        if study["experiments"][key]["status"] != "implemented":
            raise RuntimeError(f"{key} must remain implemented")
    if study["experiments"]["selected_flank_comparator"]["status"] != "not_implemented_until_detached_topology_is_derived":
        raise RuntimeError("E6 must remain gated until detached helix mechanics exist")

    neg = integrate_negative_part([0.0, 1.0, 2.0], [1.0, -1.0, 1.0])
    if abs(neg.duration_s - 1.0) > 1.0e-12:
        raise RuntimeError("Negative-part duration integration failed")
    topology = contact_topology_metrics(
        [
            {"time_s": 0.0, "helix_reacted_torque_margin_Nm": 1.0, "helix_full_reaction_force_N": 10.0},
            {"time_s": 1.0, "helix_reacted_torque_margin_Nm": -1.0, "helix_full_reaction_force_N": -10.0},
            {"time_s": 2.0, "helix_reacted_torque_margin_Nm": 1.0, "helix_full_reaction_force_N": 10.0},
        ],
        case_start_s=0.0,
        case_end_s=2.0,
    )
    if topology["zero_crossing_count"] != 2:
        raise RuntimeError("Topology crossing count smoke check failed")
    partition = integrate_sign_partition(
        [0.0, 1.0, 2.0],
        [1.0, -1.0, 1.0],
        [2.0, 1.0, 2.0],
    )
    if abs(partition.full_negative_qs_positive_s - 1.0) > 1.0e-12:
        raise RuntimeError("Dynamic-only sign partition smoke check failed")

    print(json.dumps({
        "status": "ok",
        "study": study.get("study", study.get("study_id", "helix-topology")),
        "reference_topology": study["reference_topology"]["name"],
        "dependency_scope": "release-local",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
