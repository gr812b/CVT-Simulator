"""Write ephemeral backend/CINDER contract artifacts for frontend type generation.

Run from the backend root after installing backend dependencies:

    python -m app.scripts.export_contract_artifacts --output-dir generated

The output directory is a build artifact, not source. OpenAPI describes backend
transport envelopes; CINDER's schemas describe the nested assembly, simulation
case, and simulation result contracts without the backend duplicating them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.application.cinder_gateway import CinderGateway
from app.main import create_app


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="generated")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    gateway = CinderGateway()
    _write_json(output / "openapi.json", create_app().openapi())
    _write_json(output / "cinder_assembly.schema.json", gateway.assembly_json_schema())
    _write_json(
        output / "cinder_simulation_case.schema.json",
        gateway.simulation_case_json_schema(),
    )
    _write_json(
        output / "cinder_simulation_result.schema.json",
        gateway.simulation_result_json_schema(),
    )


if __name__ == "__main__":
    main()
