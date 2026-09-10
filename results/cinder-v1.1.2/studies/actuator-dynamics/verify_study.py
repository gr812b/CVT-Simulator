from __future__ import annotations

from pathlib import Path
import sys

STUDY_ROOT = Path(__file__).resolve().parent
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from study_support import (  # noqa: E402
    EXPECTED_VERSION,
    MANIFEST_FILE,
    materialize_tagged_upstream,
    verify_environment,
    verify_release_tag,
)


def main() -> int:
    verify_environment()
    commit = verify_release_tag()
    launch_tools = materialize_tagged_upstream(clean=True)

    required = (
        "run_dynamic_actuator_ablation.py",
        "run_coupling_energy_flow.py",
        "run_actuator_dynamics_stress_search.py",
        "run_helix_inertia_torque_scaling_sweep.py",
        "run_route_grade_response.py",
        "fixed_pivot_default_support.py",
        "cad_drivetrain_inertias.py",
        "presets/fixed_pivot_3200_reference.json",
    )
    missing = [name for name in required if not (launch_tools / name).is_file()]
    if missing:
        raise RuntimeError(f"Materialized tagged source is incomplete: {missing}")

    print("PASS actuator-dynamics study verification")
    print(f"  CINDER version: {EXPECTED_VERSION}")
    print(f"  release commit: {commit}")
    print(f"  source lock:    {MANIFEST_FILE}")
    print(f"  materialized:   {launch_tools}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
