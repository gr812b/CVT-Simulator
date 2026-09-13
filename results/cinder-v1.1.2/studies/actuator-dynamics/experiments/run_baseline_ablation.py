from __future__ import annotations
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
STUDY_ROOT = HERE.parent
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))
from study_support import ARTIFACTS, load_json, materialize_tagged_upstream, run_tagged_tool, verify_environment

def main():
    verify_environment()
    materialize_tagged_upstream(clean=True)
    cfg = load_json(STUDY_ROOT/"study.json")["experiments"]["baseline_ablation"]
    s = cfg["solver"]
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
        ARTIFACTS/"baseline-ablation",
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
