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
    stage_names=("baseline","components","coupling","envelopes","commercial","transients")
    parser.add_argument(
        "--through",
        choices=(*stage_names,"all"),
        default="all",
        help="Stop after a named stage. `all` runs the complete official study.",
    )
    parser.add_argument(
        "--start-at",
        choices=stage_names,
        default="baseline",
        help=(
            "Resume at a later stage without deleting existing earlier artifacts. "
            "Use this only when those artifacts were produced by the same v1.1.2 study."
        ),
    )
    args=parser.parse_args()

    verify_environment()
    materialize_tagged_upstream(clean=True)
    if args.start_at == "baseline":
        reset_artifacts()
    else:
        ARTIFACTS.mkdir(parents=True,exist_ok=True)

    stages=[
        ("baseline", lambda: run("run_baseline_ablation.py")),
        ("components", lambda: run("run_dimensionless_components.py")),
        ("coupling", lambda: run("run_coupling_energy.py")),
        ("envelopes", lambda: run("run_validity_envelopes.py")),
        ("commercial", lambda: subprocess.run([sys.executable, str(STUDY_ROOT/"commercial-case"/"run.py")], check=True)),
        ("transients", lambda: run("run_controlled_transients.py")),
    ]
    order={name:i for i,(name,_) in enumerate(stages)}
    order["all"]=len(stages)-1
    start_index=order[args.start_at]
    end_index=order[args.through]
    if start_index>end_index:
        parser.error("--start-at must not come after --through")
    for i,(_,action) in enumerate(stages):
        if i<start_index:
            continue
        action()
        if i>=end_index:
            break

    # Summary requires baseline+coupling; build whenever both exist.
    if (ARTIFACTS/"baseline-ablation").is_dir() and (ARTIFACTS/"coupling-energy").is_dir():
        run("build_summary.py")
    copy_provenance()
    print(f"Artifacts: {ARTIFACTS}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
