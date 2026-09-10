from __future__ import annotations
from pathlib import Path
import sys
import subprocess
STUDY_ROOT=Path(__file__).resolve().parent
if str(STUDY_ROOT) not in sys.path: sys.path.insert(0,str(STUDY_ROOT))
from study_support import EXPECTED_VERSION, materialize_tagged_upstream, verify_environment, verify_release_tag

def main():
    verify_environment()
    commit=verify_release_tag()
    tools=materialize_tagged_upstream(clean=True)
    required=[
        "run_dynamic_actuator_ablation.py",
        "run_coupling_energy_flow.py",
        "run_route_grade_response.py",
        "fixed_pivot_default_support.py",
        "cad_drivetrain_inertias.py",
        "presets/fixed_pivot_3200_reference.json",
    ]
    missing=[p for p in required if not (tools/p).is_file()]
    if missing: raise RuntimeError(f"Missing tagged support files: {missing}")
    subprocess.run([sys.executable, str(STUDY_ROOT/"tests"/"test_controlled_target_selection.py")], check=True)
    subprocess.run([sys.executable, str(STUDY_ROOT/"tests"/"test_validity_helix_derivatives.py")], check=True)
    print("PASS actuator-dynamics v3 study verification")
    print(f"  CINDER: {EXPECTED_VERSION}")
    print(f"  release commit: {commit}")
    print("  official experiments: baseline ablation, dimensionless components, coupling energy, validity envelopes, commercial secondary scaling, controlled transients")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
