"""Run the promoted CINDER 1.1.2 actuator-dynamics study.

Default behavior runs only the two canonical baseline experiments:
  1. four-model dynamic-vs-quasi-static actuator ablation;
  2. full-model flyweight/helix coupling-energy decomposition.

The tagged stress-search and helix-scaling tools are preserved as exploratory
infrastructure and run only when explicitly requested.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

STUDY_ROOT = Path(__file__).resolve().parent
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from study_support import (  # noqa: E402
    ARTIFACTS,
    clean_artifacts,
    copy_provenance,
    load_json,
    materialize_tagged_upstream,
    run_tagged_tool,
    summarize_canonical_outputs,
    verify_environment,
    write_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exploration",
        choices=("none", "quick", "full"),
        default="none",
        help=(
            "Optional tagged off-baseline exploratory infrastructure. "
            "`quick` uses the upstream quick grids; `full` runs the original "
            "large grids. These outputs are not frozen final claims."
        ),
    )
    parser.add_argument(
        "--skip-baseline",
        action="store_true",
        help="Skip the canonical four-model baseline ablation.",
    )
    parser.add_argument(
        "--skip-coupling",
        action="store_true",
        help="Skip the canonical coupling-energy decomposition.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    verify_environment()
    materialize_tagged_upstream(clean=True)
    clean_artifacts()
    spec = load_json(STUDY_ROOT / "study.json")
    commands = []

    if not args.skip_baseline:
        cfg = spec["canonical_experiments"]["baseline_ablation"]
        s = cfg["solver"]
        commands.append(
            run_tagged_tool(
                "run_dynamic_actuator_ablation.py",
                [
                    "--scenario", cfg["scenario"],
                    "--duration-s", str(cfg["duration_s"]),
                    "--sample-step-s", str(cfg["sample_step_s"]),
                    "--rtol", str(s["relative_tolerance"]),
                    "--atol", str(s["absolute_tolerance"]),
                    "--max-step-s", str(s["max_step_s"]),
                    "--no-show",
                ],
                output_dir=ARTIFACTS / "baseline-ablation",
            )
        )

    if not args.skip_coupling:
        cfg = spec["canonical_experiments"]["coupling_energy"]
        s = cfg["solver"]
        commands.append(
            run_tagged_tool(
                "run_coupling_energy_flow.py",
                [
                    "--duration-s", str(cfg["duration_s"]),
                    "--report-step-s", str(cfg["report_step_s"]),
                    "--rtol", str(s["relative_tolerance"]),
                    "--atol", str(s["absolute_tolerance"]),
                    "--max-step-s", str(s["max_step_s"]),
                    "--no-show",
                ],
                output_dir=ARTIFACTS / "coupling-energy",
            )
        )

    if args.exploration != "none":
        common = ["--rtol", "0.0001", "--atol", "1e-7", "--no-show"]
        quick = ["--quick"] if args.exploration == "quick" else []

        commands.append(
            run_tagged_tool(
                "run_actuator_dynamics_stress_search.py",
                [*common, *quick],
                output_dir=ARTIFACTS / "exploration" / "stress-search",
            )
        )
        commands.append(
            run_tagged_tool(
                "run_helix_inertia_torque_scaling_sweep.py",
                [*common, *quick],
                output_dir=ARTIFACTS / "exploration" / "helix-scaling",
            )
        )

    copy_provenance()
    payload = summarize_canonical_outputs(commands)
    write_summary(payload)

    print()
    print("Actuator-dynamics study complete.")
    print(f"Artifacts: {ARTIFACTS}")
    if args.exploration == "none":
        print(
            "Off-baseline stress/scaling tools were not run. "
            "They remain available as explicitly exploratory experiments."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
