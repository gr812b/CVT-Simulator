#!/usr/bin/env python3
"""Repository/release checks for the maintained actuator-dynamics study."""
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
import subprocess
import sys

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
for _path in (str(STUDY_ROOT), str(RELEASE_ROOT)):
    while _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, str(RELEASE_ROOT))
sys.path.insert(0, str(STUDY_ROOT))

from infrastructure.study_support import EXPECTED_VERSION, verify_environment


def main() -> int:
    verify_environment()
    spec = json.loads((STUDY_ROOT / "study.json").read_text(encoding="utf-8"))
    release = spec.get("cinder_release", {})
    if release.get("version") != EXPECTED_VERSION:
        raise RuntimeError(
            f"study.json CINDER version {release.get('version')!r} != {EXPECTED_VERSION!r}"
        )

    required = (
        STUDY_ROOT / "run.py",
        STUDY_ROOT / "infrastructure" / "study_support.py",
        STUDY_ROOT / "infrastructure" / "ablation_core.py",
        STUDY_ROOT / "infrastructure" / "coupling_energy_core.py",
        STUDY_ROOT / "experiments" / "run_baseline_ablation.py",
        STUDY_ROOT / "experiments" / "run_dimensionless_components.py",
        STUDY_ROOT / "experiments" / "run_coupling_energy.py",
        STUDY_ROOT / "experiments" / "run_validity_envelopes.py",
        STUDY_ROOT / "experiments" / "run_controlled_transients.py",
        STUDY_ROOT / "analysis" / "build_summary.py",
        STUDY_ROOT / "commercial-case" / "run.py",
        STUDY_ROOT / "commercial-case" / "run_trajectory_demo.py",
        RELEASE_ROOT / "defaults" / "baja" / "simulation_case.json",
        RELEASE_ROOT / "defaults" / "baja" / "reference.py",
        RELEASE_ROOT / "defaults" / "reference_model" / "policy.json",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Missing actuator study files: " + ", ".join(missing))

    tests = (
        "test_controlled_target_selection.py",
        "test_validity_helix_derivatives.py",
        "test_commercial_trajectory_selection.py",
    )
    for name in tests:
        subprocess.run([sys.executable, str(STUDY_ROOT / "tests" / name)], check=True)

    print("PASS actuator-dynamics maintained-study verification")
    print(f"  CINDER: {EXPECTED_VERSION}")
    print("  runtime dependencies: release defaults + study-local infrastructure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
