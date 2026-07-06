"""Phase-1 public-contract walkthrough for CINDER.

Run from the cvtModel repository root after an editable install:

    python examples/quickstart.py
    python examples/quickstart.py --run

The default path reads, validates, and decodes a full simulation document.  It
performs no frontend/unit-conversion math.  ``--run`` uses the document's own
scenario and execution settings, then prints keys from CINDER's flattened
report table.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cinder.contracts import (
    decode_simulation_case_document,
    editable_simulation_case_schema,
    project_simulation_result,
    validate_simulation_case_document,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the baseline simulation after validation.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    document_path = root / "examples" / "baja_baseline_simulation_case.json"
    document = json.loads(document_path.read_text())

    schema = editable_simulation_case_schema()
    report = validate_simulation_case_document(document)
    print(f"Document: {document_path.name}")
    print(f"Schema fields: {len(schema['fields'])}")
    print(f"Validation: {'valid' if report.is_valid else 'invalid'}")
    for finding in report.findings:
        target = finding.document_path or "/"
        print(f"  [{finding.severity}] {target}: {finding.message}")
    if not report.is_valid:
        raise SystemExit(1)

    decoded = decode_simulation_case_document(document)
    print("Input boundary:", type(decoded.case.input_boundary).__name__)
    print("Output boundary:", type(decoded.case.output_boundary).__name__)
    print("Integrator:", decoded.integrator_settings.method)
    print("Report grid:", decoded.reporting_settings.grid.kind)

    if not args.run:
        print("Use --run to integrate and inspect the flattened report table.")
        return

    system = decoded.build_system()
    scenario = decoded.case.scenario
    result = system.run(
        time_span=scenario.time_span,
        initial_state=scenario.initial_state,
        initial_regime=scenario.initial_mode,
        settings=decoded.integrator_settings,
        reporting_settings=decoded.reporting_settings,
    )
    payload = project_simulation_result(result)
    report_table = payload["report_table"]
    print("Termination:", payload["metrics"]["termination_reason"])
    print("Transitions:", len(payload["transitions"]))
    print("Report rows:", report_table["row_count"])
    print("First report columns:")
    for column in report_table["columns"][:8]:
        print(f"  {column['key']} [{column['canonical_unit']}]")


if __name__ == "__main__":
    main()
