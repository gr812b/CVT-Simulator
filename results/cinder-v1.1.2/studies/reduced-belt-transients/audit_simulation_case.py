"""Run one unchanged CINDER simulation case and build its final-equation belt atlas."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
VERIFY = RELEASE_ROOT / "verify_environment.py"
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from study_support import ARTIFACTS, write_json
from trajectory_audit import write_atlas

EXPECTED_CINDER_VERSION = "1.1.2"


def run_case(*, case_path: Path, name: str, max_samples: int, skip_environment_check: bool = False):
    if not skip_environment_check:
        subprocess.run([sys.executable, str(VERIFY)], check=True)
    import cinder
    from cinder.contracts import decode_simulation_case_document, validate_simulation_case_document

    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise RuntimeError(f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__}.")
    document = json.loads(case_path.read_text(encoding="utf-8"))
    validation = validate_simulation_case_document(document)
    if not validation.is_valid:
        raise RuntimeError("Simulation case failed CINDER validation: " + "; ".join(f.message for f in validation.findings))
    decoded = decode_simulation_case_document(document)
    result = decoded.system.run(
        time_span=decoded.time_span,
        initial_state=decoded.initial_state,
        initial_mode=decoded.initial_mode,
        settings=decoded.integrator_settings,
        reporting_settings=decoded.reporting_settings,
    )
    output = ARTIFACTS / name
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / "simulation_case.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    summary = write_atlas(
        system=decoded.system,
        trace=result.trace,
        output_dir=output,
        protocol={"name": name, "title": name.replace("_", " ").title(), "source": str(case_path)},
        maximum_samples=max_samples,
    )
    write_json(output / "run_summary.json", {
        "completed": bool(result.completed),
        "termination_reason": result.termination_reason,
        "transition_count": len(result.transitions),
        "final_time_s": float(result.final_time),
        "engaged_sample_count": summary["overall"]["engaged_sample_count"],
    })
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--max-samples", type=int, default=6000)
    parser.add_argument("--skip-environment-check", action="store_true")
    args = parser.parse_args()
    run_case(case_path=args.case.resolve(), name=args.name, max_samples=args.max_samples, skip_environment_check=args.skip_environment_check)
    print(f"Artifacts: {ARTIFACTS / args.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
