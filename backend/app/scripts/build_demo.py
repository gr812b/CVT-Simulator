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
from app.application.demo_labels import DEMO_COURSE_NAME, DEMO_PLAYBACK_DESCRIPTION
from app.application.physical_contracts import template_document, validate_physical
from app.application.roads import apply_scenario, demo_scenario
from app.core.settings import Settings
from app.database.hashing import canonical_json_hash
from app.database.runs import verify_result_contract
from app.schemas.demo import DemoArtifact


def main():
    setup = template_document("setups")
    setup.data.vehicle.mass_kg = 500 * 0.45359237
    validation, case = validate_physical(setup)
    if not validation["is_valid"] or case is None:
        raise RuntimeError("The example demo setup must pass input validation")
    scenario = demo_scenario()
    road = apply_scenario(case, scenario, Settings.from_environment())
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
                    "worker_pid": os.getpid(),
                    "options": {},
                    "course_policy": {
                        "finish_m": road.length_m,
                        "rollback_m": scenario.stops.rollback_m,
                        "no_progress_s": scenario.stops.no_progress_s,
                    },
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
    verify_result_contract(result, expected_version=identity["simulation_result_contract_version"])
    if result["metrics"]["completed"] is not True:
        raise RuntimeError("A partial simulation cannot replace the public demo")
    distance = next(
        column["values"]
        for column in result["report_table"]["columns"]
        if column["key"] == "vehicle.distance"
    )
    if max(value for value in distance if value is not None) < road.length_m - 0.01:
        raise RuntimeError("The demo did not reach the course finish")
    demo = DemoArtifact(
        name=DEMO_COURSE_NAME,
        description=DEMO_PLAYBACK_DESCRIPTION,
        generated_at=datetime.now(UTC),
        runtime_identity=identity,
        input_hash=canonical_json_hash(case),
        result_hash=canonical_json_hash(result),
        input_document_snapshot=case,
        result=result,
    )
    DEMO_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = DEMO_PATH.with_suffix(".tmp")
    temporary.write_bytes(gzip.compress(demo.model_dump_json().encode("utf-8"), mtime=0))
    temporary.replace(DEMO_PATH)
    from app.scripts.build_scenes import main as build_scenes

    build_scenes()
    print(
        f"Saved {DEMO_PATH}: {result['report_table']['row_count']} rows, "
        f"CINDER {identity['package_version']}, result {demo.result_hash}"
    )


if __name__ == "__main__":
    main()
