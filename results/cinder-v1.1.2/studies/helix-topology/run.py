"""Run the complete exploratory helix reaction-discovery programme.

Default usage performs E1-E5.8, writes provenance, and creates one ZIP that can
be sent back for interpretation:

    python results/cinder-v1.1.2/studies/helix-topology/run.py

Use ``--quick`` only as a smoke test.  It keeps E1/E2 unchanged and reduces
E3/E5 to representative cases.
"""
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


import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from infrastructure.study_support import (  # noqa: E402
    ARTIFACTS,
    copy_provenance,
    reset_artifacts,
    verify_environment,
)


def run_script(name: str, *extra: str) -> None:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(RELEASE_ROOT)
        if not existing
        else str(RELEASE_ROOT) + os.pathsep + existing
    )
    subprocess.run(
        [sys.executable, str(STUDY_ROOT / "experiments" / name), *extra],
        check=True,
        env=env,
    )


def make_bundle(*, quick: bool, through: str) -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    manifest = {
        "study": "helix-topology",
        "purpose": "exploratory helix reaction reversal / would-be unilateral lift-off discovery",
        "completed_through": through,
        "quick_smoke_mode": bool(quick),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "send_back_instruction": (
            "Zip contains the simulation artifacts needed to interpret where and why "
            "the selected-flank helix reaction approaches or crosses zero."
        ),
    }
    (ARTIFACTS / "RUN_COMPLETE.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    suffix = "_quick" if quick else ""
    base = STUDY_ROOT / f"helix_topology_discovery_artifacts{suffix}"
    zip_path = base.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    made = shutil.make_archive(
        str(base),
        "zip",
        root_dir=ARTIFACTS.parent,
        base_dir=ARTIFACTS.name,
    )
    return Path(made)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    stages = ("reaction-map", "forward-control", "stress-screen", "scenario-discovery", "liftoff-envelope", "dynamic-only-liftoff", "transient-severity-race", "coupled-event-chronology", "paired-helix-performance")
    parser.add_argument(
        "--through",
        choices=(*stages, "all"),
        default="all",
        help="Stop after a named exploration stage.",
    )
    parser.add_argument(
        "--start-at",
        choices=stages,
        default="reaction-map",
        help="Resume at a later stage without deleting existing earlier artifacts.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run small E3-E5 smoke matrices. Do not use quick mode for interpretation.",
    )
    parser.add_argument(
        "--no-bundle",
        action="store_true",
        help="Do not create the final artifacts ZIP.",
    )
    args = parser.parse_args()

    verify_environment()
    pass  # dependencies are release-local; no runtime materialization
    if args.start_at == "reaction-map":
        reset_artifacts()
    else:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)

    quick_arg = ("--quick",) if args.quick else ()
    actions = [
        ("reaction-map", lambda: run_script("run_reaction_map.py")),
        ("forward-control", lambda: run_script("run_forward_control.py")),
        ("stress-screen", lambda: run_script("run_stress_screen.py", *quick_arg)),
        (
            "scenario-discovery",
            lambda: run_script("run_scenario_discovery.py", *quick_arg),
        ),
        (
            "liftoff-envelope",
            lambda: run_script("run_liftoff_envelope.py", *quick_arg),
        ),
        (
            "dynamic-only-liftoff",
            lambda: run_script("run_dynamic_only_liftoff.py", *quick_arg),
        ),
        (
            "transient-severity-race",
            lambda: run_script("run_transient_severity_race.py", *quick_arg),
        ),
        (
            "coupled-event-chronology",
            lambda: run_script("run_coupled_event_chronology.py"),
        ),
        (
            "paired-helix-performance",
            lambda: run_script("run_paired_helix_performance.py", *quick_arg),
        ),
    ]
    order = {name: i for i, (name, _) in enumerate(actions)}
    order["all"] = len(actions) - 1
    start = order[args.start_at]
    end = order[args.through]
    if start > end:
        parser.error("--start-at must not come after --through")

    last_stage = actions[end][0]
    for index, (name, action) in enumerate(actions):
        if index < start:
            continue
        print(f"\n=== HELIX DISCOVERY: {name} ===", flush=True)
        action()
        if index >= end:
            break

    copy_provenance()
    print(f"\nExploration artifacts: {ARTIFACTS}")
    if not args.no_bundle:
        bundle = make_bundle(quick=bool(args.quick), through=last_stage)
        print(f"Artifacts ZIP: {bundle}")
        print("Send that ZIP back for interpretation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
