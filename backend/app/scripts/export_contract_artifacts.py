"""Write backend OpenAPI plus CINDER's public document schema for type generation.

Run from the backend root after installing the local CINDER package:

    python -m app.scripts.export_contract_artifacts --output-dir generated

Frontend tooling can feed `generated/openapi.json` to `openapi-typescript` and
`generated/cinder_simulation_case.schema.json` to `json-schema-to-typescript`.
The generated types complement each other: OpenAPI types API envelopes; the
CINDER schema types the nested canonical simulation document.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.application.cinder_gateway import CinderGateway
from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="generated")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    (output / "openapi.json").write_text(
        json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "cinder_simulation_case.schema.json").write_text(
        json.dumps(CinderGateway().simulation_case_json_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
