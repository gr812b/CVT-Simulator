"""Run the bundled CINDER reference simulation case.

Install CINDER first, then run from any checkout of this repository:

    python -m pip install cinder-cvt==1.0.0
    python cvtModel/examples/quickstart.py
    python cvtModel/examples/quickstart.py --run

Use --case to point at another public CINDER simulation-case document.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cinder
from cinder.contracts import (
    decode_simulation_case_document,
    project_simulation_result,
    validate_simulation_case_document,
)

HERE = Path(__file__).resolve().parent
DEFAULT_CASE = HERE / "baja_baseline_simulation_case.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        type=Path,
        default=DEFAULT_CASE,
        help="Public CINDER simulation-case JSON document to load.",
    )
    parser.add_argument("--run", action="store_true", help="Run the decoded case.")
    args = parser.parse_args()

    document_path = args.case.resolve()
    document = json.loads(document_path.read_text(encoding="utf-8"))

    validation = validate_simulation_case_document(document)
    print(f"CINDER: {cinder.__version__}")
    print(f"Document: {document_path}")
    print(f"Validation: {'valid' if validation.is_valid else 'invalid'}")
    for finding in validation.findings:
        print(
            f"  [{finding.severity}] "
            f"{finding.document_path or '/'}: {finding.message}"
        )
    if not validation.is_valid:
        raise SystemExit(1)

    decoded = decode_simulation_case_document(document)
    print("System:", type(decoded.system).__name__)
    print("Primary boundary:", type(decoded.system.primary_boundary).__name__)
    print("Secondary boundary:", type(decoded.system.secondary_boundary).__name__)
    print("Host:", type(decoded.system.host).__name__)
    print("Integrator:", decoded.integrator_settings.method)

    if not args.run:
        print("Use --run to integrate and print report columns.")
        return

    result = decoded.system.run(
        time_span=decoded.time_span,
        initial_state=decoded.initial_state,
        initial_mode=decoded.initial_mode,
        settings=decoded.integrator_settings,
        reporting_settings=decoded.reporting_settings,
    )
    payload = project_simulation_result(result)
    print("Termination:", payload["metrics"]["termination_reason"])
    print("Transitions:", len(payload["transitions"]))
    print("Report rows:", payload["report_table"]["row_count"])
    print("First report columns:")
    for column in payload["report_table"]["columns"][:8]:
        print(f"  {column['key']} [{column['canonical_unit']}]")


if __name__ == "__main__":
    main()
