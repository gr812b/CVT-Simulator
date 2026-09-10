from __future__ import annotations

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
STUDY_ROOT = HERE.parent
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from study_support import ARTIFACTS, load_json, materialize_tagged_upstream, run_tagged_tool, verify_environment  # noqa: E402

def main() -> int:
    verify_environment()
    materialize_tagged_upstream(clean=True)
    mode = "quick" if "--full" not in sys.argv else "full"
    args = ["--rtol", "0.0001", "--atol", "1e-7", "--no-show"]
    if mode == "quick":
        args.append("--quick")
    run_tagged_tool(
        "run_actuator_dynamics_stress_search.py",
        args,
        output_dir=ARTIFACTS / "exploration" / "stress-search",
    )

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
