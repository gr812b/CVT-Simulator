"""Explicitly regenerate the retained public demo with the pinned CINDER runtime.

Run from backend/: python -m app.scripts.build_demo
This is a development operation, never part of API startup, seeding or a request.
"""

import gzip
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from app.application.cinder_gateway import CinderGateway
from app.application.demo import DEMO_PATH
from app.application.physical_contracts import baseline_case
from app.database.hashing import canonical_json_hash
from app.database.runs import verify_result_contract
from app.schemas.demo import DemoPlaybackResponse


def main():
    case = baseline_case()
    # Keep baseline mechanics/tune intact; retain ten seconds at a 20 ms report grid.
    case["scenario"]["time_span_s"] = [0.0, 10.0]
    case["execution"]["reporting"]["grid"] = {
        "kind": "uniform_time_step",
        "count": None,
        "step_seconds": 0.02,
    }
    identity = CinderGateway().runtime_identity()
    with tempfile.TemporaryDirectory(prefix="cinder-demo-") as directory:
        source, destination = (
            Path(directory) / "input.json",
            Path(directory) / "output.json",
        )
        source.write_text(
            json.dumps(
                {
                    "input": case,
                    "options": {},
                    "runtime_identity": identity,
                    "deadline_monotonic": time.monotonic() + 120,
                    "memory_bytes": 4096 * 1024 * 1024,
                    "result_bytes": 64_000_000,
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "app.scripts.run_child",
                str(source),
                str(destination),
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
            timeout=130,
            env={
                **os.environ,
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            },
        )
        payload = json.loads(destination.read_text(encoding="utf-8"))
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    result = payload["result"]
    verify_result_contract(
        result, expected_version=identity["simulation_result_contract_version"]
    )
    if result["metrics"]["completed"] is not True:
        raise RuntimeError("A partial simulation cannot replace the public demo")
    demo = DemoPlaybackResponse(
        name="Baja launch demo",
        description="A recorded ten-second launch using the project's default Baja setup on flat ground.",
        generated_at=datetime.now(UTC),
        runtime_identity=identity,
        input_hash=canonical_json_hash(case),
        result_hash=canonical_json_hash(result),
        input_document_snapshot=case,
        result=result,
    )
    DEMO_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = DEMO_PATH.with_suffix(".tmp")
    temporary.write_bytes(
        gzip.compress(demo.model_dump_json().encode("utf-8"), mtime=0)
    )
    temporary.replace(DEMO_PATH)
    print(
        f"Saved {DEMO_PATH}: {result['report_table']['row_count']} rows, CINDER {identity['package_version']}, result {demo.result_hash}"
    )


if __name__ == "__main__":
    main()
