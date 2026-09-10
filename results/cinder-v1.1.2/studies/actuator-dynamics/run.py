"""Run the complete official CINDER 1.1.2 actuator-dynamics study."""

from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys

STUDY_ROOT=Path(__file__).resolve().parent
if str(STUDY_ROOT) not in sys.path: sys.path.insert(0,str(STUDY_ROOT))
from study_support import ARTIFACTS, copy_provenance, materialize_tagged_upstream, reset_artifacts, verify_environment

def run(script):
    subprocess.run([sys.executable, str(STUDY_ROOT/"experiments"/script)], check=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--through",
        choices=("baseline","coupling","envelopes","transients","all"),
        default="all",
        help="Stop after a named stage. `all` runs the complete official study.",
    )
    args=parser.parse_args()

    verify_environment()
    materialize_tagged_upstream(clean=True)
    reset_artifacts()

    stages=[
        ("baseline","run_baseline_ablation.py"),
        ("coupling","run_coupling_energy.py"),
        ("envelopes","run_validity_envelopes.py"),
        ("transients","run_controlled_transients.py"),
    ]
    order={"baseline":0,"coupling":1,"envelopes":2,"transients":3,"all":3}
    for i,(_,script) in enumerate(stages):
        run(script)
        if i>=order[args.through]:
            break

    # Summary requires baseline+coupling; build whenever both exist.
    if (ARTIFACTS/"baseline-ablation").is_dir() and (ARTIFACTS/"coupling-energy").is_dir():
        run("build_summary.py")
    copy_provenance()
    print(f"Artifacts: {ARTIFACTS}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
