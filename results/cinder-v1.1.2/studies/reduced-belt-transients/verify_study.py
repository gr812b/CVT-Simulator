"""Repository/release checks for the maintained reduced-belt transient study."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]


def main() -> int:
    subprocess.run([sys.executable, str(RELEASE_ROOT / "verify_environment.py")], check=True)
    required = (
        STUDY_ROOT / "run.py",
        STUDY_ROOT / "infrastructure" / "audit_simulation_case.py",
        STUDY_ROOT / "infrastructure" / "belt_terms.py",
        STUDY_ROOT / "infrastructure" / "protocol_support.py",
        STUDY_ROOT / "infrastructure" / "study_support.py",
        STUDY_ROOT / "infrastructure" / "trajectory_audit.py",
        STUDY_ROOT / "experiments" / "closure_design.py",
        STUDY_ROOT / "experiments" / "envelope_design.py",
        STUDY_ROOT / "analysis" / "closure_synthesis.py",
        STUDY_ROOT / "analysis" / "equation_sensitivity.py",
        STUDY_ROOT / "analysis" / "sensitivity_synthesis.py",
        RELEASE_ROOT / "defaults" / "baja" / "simulation_case.json",
        RELEASE_ROOT / "defaults" / "reference_model" / "reference_case.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Missing reduced-belt study files: " + ", ".join(missing))

    run_text = (STUDY_ROOT / "run.py").read_text(encoding="utf-8")
    if 'defaults" / "baja" / "simulation_case.json"' not in run_text:
        raise RuntimeError("run.py does not use the frozen release-local Baja input")
    for forbidden in ("cvtModel/examples", "cvtModel\\examples", "REPO_EXAMPLE_CASE"):
        if forbidden in run_text:
            raise RuntimeError(f"run.py still contains forbidden fallback {forbidden!r}")

    for test in sorted((STUDY_ROOT / "tests").glob("test_*.py")):
        subprocess.run([sys.executable, str(test)], check=True)

    print("PASS reduced-belt-transients maintained-study verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
