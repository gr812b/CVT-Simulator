"""Deep local smoke test for database-backed library lifecycle routes.

This script is intentionally heavier than unit tests. It creates a temporary
SQLite database, boots the FastAPI app, seeds baseline data, and drives the API
through the important library lifecycle paths:

* CORS preflight for PATCH-heavy browser flows
* list/get seeded public official/default objects
* create -> explicit-null draft update -> release
* fork -> release for engine, CVT design, output system, and vehicle assembly
* tune/load-case/execution-preset create and update
* version deprecation/supersession and object archival
* DB-resolved simulation run persistence
* direct-vs-library result equality
* versioned downsampled preview artifacts
* full-result eviction with preview/input still available
* rerun after full-result eviction

Usage:
    PYTHONPATH=.:../cvtModel/src python -m app.scripts.smoke_library_database
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.database.base import Base
from app.database.seed import seed_database
from app.database.models import Run, RunArtifact, RunCacheEntry
from app.main import create_app


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cvt-db-library-smoke-") as temp_dir:
        db_path = Path(temp_dir) / "smoke.db"
        app = create_app(
            Settings(
                preset_directory=Path(__file__).resolve().parents[2] / "presets",
                run_executor_mode="inline",
                database_url=f"sqlite:///{db_path}",
            )
        )
        try:
            Base.metadata.create_all(app.state.database_engine)
            with app.state.database_session_factory() as session:
                seed_database(session)
                session.commit()

            with TestClient(app) as client:
                _exercise_smoke_flow(client, app)
        finally:
            app.state.database_engine.dispose()

    print("library database smoke test passed")


def _exercise_smoke_flow(client: TestClient, app: Any) -> None:
    _assert_ok(client.get("/api/v1/health"))
    _assert_cors_preflight_supports_patch(client)

    institutions = _assert_ok(client.get("/api/v1/library/institutions"))["items"]
    assert any(item["slug"] == "mcmaster-university" for item in institutions)

    engines = _assert_ok(client.get("/api/v1/library/engines?public_only=true"))["items"]
    assert engines and engines[0]["released_version_id"]
    assert engines[0]["is_default"] is True
    account_id = engines[0]["account_id"]

    engine_version = _assert_ok(
        client.get(f"/api/v1/library/engines/versions/{engines[0]['released_version_id']}")
    )
    assert engine_version["validation_status"] == "valid"

    forked_engine = _assert_ok(
        client.post(
            f"/api/v1/library/engines/versions/{engine_version['id']}/fork",
            json={
                "account_id": account_id,
                "name": "Smoke Fork Engine",
                "description": "will be cleared",
                "visibility": "private",
            },
        )
    )
    cleared_engine = _assert_ok(
        client.patch(
            f"/api/v1/library/engines/{forked_engine['id']}/draft",
            json={
                "description": None,
                "source_url": "https://example.invalid/source",
                "draft_payload": {**engine_version["payload"], "smoke_marker": True},
            },
        )
    )
    assert cleared_engine["description"] is None
    assert cleared_engine["source_url"] == "https://example.invalid/source"
    cleared_engine = _assert_ok(
        client.patch(
            f"/api/v1/library/engines/{forked_engine['id']}/draft",
            json={"source_url": None},
        )
    )
    assert cleared_engine["source_url"] is None

    released_engine = _assert_ok(
        client.post(
            f"/api/v1/library/engines/{forked_engine['id']}/release",
            json={
                "payload_schema_name": "cinder.input_boundary.smoke",
                "release_notes": "Smoke release",
            },
        )
    )
    assert released_engine["version_number"] == 1
    assert released_engine["payload"]["smoke_marker"] is True

    cvt = _assert_ok(client.get("/api/v1/library/cvt-designs?public_only=true"))["items"][0]
    cvt_version = _assert_ok(
        client.get(f"/api/v1/library/cvt-designs/versions/{cvt['released_version_id']}")
    )
    assert cvt_version["payload"].get("document_type") == "cinder_cvt_assembly"
    forked_cvt = _assert_ok(
        client.post(
            f"/api/v1/library/cvt-designs/versions/{cvt_version['id']}/fork",
            json={"account_id": account_id, "name": "Smoke Fork CVT"},
        )
    )
    assert "cinder_assembly" in forked_cvt["draft_payload"]
    released_cvt = _assert_ok(
        client.post(
            f"/api/v1/library/cvt-designs/{forked_cvt['id']}/release",
            json={"release_notes": "Release forked CVT without reconstructing payload"},
        )
    )
    assert "cinder_assembly" not in released_cvt["payload"]
    assert released_cvt["payload"].get("document_type") == "cinder_cvt_assembly"
    assert released_cvt["cinder_assembly"] == released_cvt["payload"]
    assert released_cvt["tuning_schema"] == (cvt_version["tuning_schema"] or {})

    output = _assert_ok(client.get("/api/v1/library/output-systems?public_only=true"))["items"][0]
    output_version = _assert_ok(
        client.get(f"/api/v1/library/output-systems/versions/{output['released_version_id']}")
    )
    forked_output = _assert_ok(
        client.post(
            f"/api/v1/library/output-systems/versions/{output_version['id']}/fork",
            json={"account_id": account_id, "name": "Smoke Fork Output"},
        )
    )
    released_output = _assert_ok(
        client.post(f"/api/v1/library/output-systems/{forked_output['id']}/release", json={})
    )
    assert released_output["payload"]["kind"] == output_version["payload"]["kind"]
    assert "direct_secondary_shaft_inertia_kg_m2" in released_output["payload"]

    assembly = _assert_ok(
        client.post(
            "/api/v1/library/vehicle-assemblies",
            json={
                "account_id": account_id,
                "name": "Smoke Assembly",
                "visibility": "private",
                "draft_payload": {
                    "engine_version_id": released_engine["id"],
                    "cvt_design_version_id": released_cvt["id"],
                    "output_system_version_id": released_output["id"],
                    "assembly_payload": {"notes": "smoke"},
                },
            },
        )
    )
    assembly_version = _assert_ok(
        client.post(
            f"/api/v1/library/vehicle-assemblies/{assembly['id']}/release",
            json={"payload_schema_name": "cvt_simulator.vehicle_assembly.smoke"},
        )
    )
    assert assembly_version["engine_version_id"] == released_engine["id"]
    assert assembly_version["cvt_design_version_id"] == released_cvt["id"]
    assert assembly_version["output_system_version_id"] == released_output["id"]

    forked_assembly = _assert_ok(
        client.post(
            f"/api/v1/library/vehicle-assemblies/versions/{assembly_version['id']}/fork",
            json={"account_id": account_id, "name": "Smoke Fork Assembly"},
        )
    )
    released_forked_assembly = _assert_ok(
        client.post(
            f"/api/v1/library/vehicle-assemblies/{forked_assembly['id']}/release",
            json={},
        )
    )
    assert released_forked_assembly["engine_version_id"] == released_engine["id"]

    tune = _assert_ok(
        client.post(
            "/api/v1/library/tunes",
            json={
                "account_id": account_id,
                "vehicle_assembly_id": assembly["id"],
                "cvt_design_id": cvt["id"],
                "name": "Smoke Tune",
                "values": {"flyweight_mass_kg": 0.75},
                "notes": "will clear",
            },
        )
    )
    assert _assert_ok(client.get(f"/api/v1/library/tunes?account_id={account_id}"))["items"]
    updated_tune = _assert_ok(
        client.patch(
            f"/api/v1/library/tunes/{tune['id']}",
            json={"values": {"flyweight_mass_kg": 0.8}, "notes": None},
        )
    )
    assert updated_tune["values"]["flyweight_mass_kg"] == 0.8
    assert updated_tune["notes"] is None

    load_case = _assert_ok(
        client.post(
            "/api/v1/library/load-cases",
            json={
                "account_id": account_id,
                "name": "Smoke Launch",
                "kind": "launch",
                "payload": {"scenario": {"time_span_s": [0.0, 1.0]}},
            },
        )
    )
    assert load_case["kind"] == "launch"
    updated_load_case = _assert_ok(
        client.patch(
            f"/api/v1/library/load-cases/{load_case['id']}",
            json={"payload": {"scenario": {"time_span_s": [0.0, 2.0]}}},
        )
    )
    assert updated_load_case["payload"]["scenario"]["time_span_s"] == [0.0, 2.0]

    preset = _assert_ok(
        client.post(
            "/api/v1/library/execution-presets",
            json={
                "account_id": account_id,
                "name": "Smoke Fast",
                "payload": {"integrator": {"method": "LSODA"}},
            },
        )
    )
    assert preset["payload"]["integrator"]["method"] == "LSODA"
    updated_preset = _assert_ok(
        client.patch(
            f"/api/v1/library/execution-presets/{preset['id']}",
            json={"is_system_default": True},
        )
    )
    assert updated_preset["is_system_default"] is True

    deprecated = _assert_ok(
        client.post(
            f"/api/v1/library/engines/versions/{engine_version['id']}/deprecate",
            json={
                "validation_status": "deprecated",
                "superseded_by_version_id": released_engine["id"],
                "message": "Smoke deprecation",
            },
        )
    )
    assert deprecated["validation_status"] == "deprecated"
    assert deprecated["superseded_by_version_id"] == released_engine["id"]
    assert deprecated["deprecated_at"] is not None
    assert deprecated["validation_messages"]

    archived = _assert_ok(client.post(f"/api/v1/library/engines/{forked_engine['id']}/archive"))
    assert archived["lifecycle_status"] == "archived"
    visible_engines = _assert_ok(client.get(f"/api/v1/library/engines?account_id={account_id}"))[
        "items"
    ]
    assert all(item["id"] != forked_engine["id"] for item in visible_engines)
    all_engines = _assert_ok(
        client.get(f"/api/v1/library/engines?account_id={account_id}&include_archived=true")
    )["items"]
    assert any(item["id"] == forked_engine["id"] for item in all_engines)

    _exercise_library_run_flow(client, app, account_id=account_id)


def _assert_cors_preflight_supports_patch(client: TestClient) -> None:
    response = client.options(
        "/api/v1/library/engines/smoke/draft",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PATCH",
        },
    )
    if response.status_code >= 400:
        raise AssertionError(f"CORS preflight failed {response.status_code}: {response.text}")
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "PATCH" in allow_methods


def _assert_ok(response: Any) -> dict[str, Any]:
    if response.status_code >= 400:
        raise AssertionError(f"{response.status_code}: {response.text}")
    body = response.json()
    if not isinstance(body, dict):
        raise AssertionError(f"Expected JSON object response, got {type(body).__name__}.")
    return body


def _exercise_library_run_flow(client: TestClient, app: Any, *, account_id: str) -> None:
    """Run the full DB object -> CINDER -> persisted result flow.

    This intentionally compares against the existing direct-contract endpoint so
    future resolver changes cannot silently alter simulation results.
    """

    assemblies = _assert_ok(client.get("/api/v1/library/vehicle-assemblies?public_only=true"))[
        "items"
    ]
    assembly = next(item for item in assemblies if item["released_version_id"])

    tunes = _assert_ok(client.get(f"/api/v1/library/tunes?account_id={account_id}"))["items"]
    tune = next(item for item in tunes if item["name"] == "Baseline tune")

    load_cases = _assert_ok(client.get(f"/api/v1/library/load-cases?account_id={account_id}"))[
        "items"
    ]
    seeded_load_case = next(item for item in load_cases if item["name"] == "Flat launch")
    short_payload = _deep_copy(seeded_load_case["payload"])
    short_payload["scenario"]["time_span_s"] = [0.0, 0.06]
    short_load_case = _assert_ok(
        client.post(
            "/api/v1/library/load-cases",
            json={
                "account_id": account_id,
                "name": "Smoke DB run short launch",
                "kind": "launch",
                "payload": short_payload,
            },
        )
    )

    presets = _assert_ok(client.get(f"/api/v1/library/execution-presets?account_id={account_id}"))[
        "items"
    ]
    execution_preset = next(
        item for item in presets if item["name"] == "Default accurate simulation"
    )
    dense_execution_payload = _deep_copy(execution_preset["payload"])
    dense_execution_payload.setdefault("reporting", {}).setdefault("grid", {})[
        "step_seconds"
    ] = 0.00005
    dense_execution_payload["reporting"]["grid"]["count"] = None
    dense_execution = _assert_ok(
        client.post(
            "/api/v1/library/execution-presets",
            json={
                "account_id": account_id,
                "name": "Smoke Dense Preview Execution",
                "payload": dense_execution_payload,
            },
        )
    )

    library_status = _assert_ok(
        client.post(
            "/api/v1/runs/from-library",
            json={
                "account_id": account_id,
                "vehicle_assembly_version_id": assembly["released_version_id"],
                "tune_id": tune["id"],
                "load_case_id": short_load_case["id"],
                "execution_preset_id": dense_execution["id"],
            },
        )
    )
    assert library_status["source"] == "library"
    assert library_status["status"] == "completed"
    assert library_status["cache_hit"] is False
    assert library_status["contract_hash"]
    assert library_status["cache_entry_id"]
    assert library_status["summary_scalars"]["metrics"]["duration_s"] == 0.06

    fetched_status = _assert_ok(client.get(f"/api/v1/runs/{library_status['id']}"))
    assert fetched_status["source"] == "library"
    assert fetched_status["status"] == "completed"
    assert fetched_status["contract_hash"] == library_status["contract_hash"]

    library_result = _assert_ok(client.get(f"/api/v1/runs/{library_status['id']}/result"))
    assert library_result["input_document_snapshot"]["document_type"] == "cinder_simulation_case"
    assert library_result["input_document_snapshot"]["database_resolution"]["version_warnings"]
    assert library_result["result"]["kind"] == "simulation_result"
    assert library_result["result"]["metrics"]["completed"] is True

    library_input = _assert_ok(client.get(f"/api/v1/runs/{library_status['id']}/input"))
    assert library_input["input_document_snapshot"] == library_result["input_document_snapshot"]

    stored_rerun_status = _assert_ok(client.post(f"/api/v1/runs/{library_status['id']}/rerun"))
    assert stored_rerun_status["source"] == "library"
    assert stored_rerun_status["status"] == "completed"
    assert stored_rerun_status["cache_hit"] is True
    assert stored_rerun_status["contract_hash"] == library_status["contract_hash"]
    stored_rerun_result = _assert_ok(client.get(f"/api/v1/runs/{stored_rerun_status['id']}/result"))
    _assert_results_close(library_result["result"], stored_rerun_result["result"])

    library_preview = _assert_ok(client.get(f"/api/v1/runs/{library_status['id']}/preview"))
    stored_rerun_preview = _assert_ok(
        client.get(f"/api/v1/runs/{stored_rerun_status['id']}/preview")
    )
    _assert_results_close(
        library_preview["preview"], stored_rerun_preview["preview"], path="preview"
    )
    _assert_preview_matches_result(library_preview["preview"], library_result["result"])

    second_status = _assert_ok(
        client.post(
            "/api/v1/runs/from-library",
            json={
                "account_id": account_id,
                "vehicle_assembly_version_id": assembly["released_version_id"],
                "tune_id": tune["id"],
                "load_case_id": short_load_case["id"],
                "execution_preset_id": dense_execution["id"],
            },
        )
    )
    assert second_status["source"] == "library"
    assert second_status["status"] == "completed"
    assert second_status["cache_hit"] is True
    assert second_status["contract_hash"] == library_status["contract_hash"]
    assert second_status["cache_entry_id"] == library_status["cache_entry_id"]
    second_result = _assert_ok(client.get(f"/api/v1/runs/{second_status['id']}/result"))
    _assert_results_close(library_result["result"], second_result["result"])
    second_preview = _assert_ok(client.get(f"/api/v1/runs/{second_status['id']}/preview"))
    _assert_results_close(
        library_preview["preview"], second_preview["preview"], path="cached_preview"
    )

    _simulate_full_result_eviction(app)
    evicted_result_response = client.get(f"/api/v1/runs/{library_status['id']}/result")
    assert evicted_result_response.status_code == 410
    preview_after_eviction = _assert_ok(client.get(f"/api/v1/runs/{library_status['id']}/preview"))
    _assert_results_close(
        library_preview["preview"], preview_after_eviction["preview"], path="evicted_preview"
    )
    input_after_eviction = _assert_ok(client.get(f"/api/v1/runs/{library_status['id']}/input"))
    assert (
        input_after_eviction["input_document_snapshot"] == library_result["input_document_snapshot"]
    )

    rerun_status = _assert_ok(client.post(f"/api/v1/runs/{library_status['id']}/rerun"))
    assert rerun_status["source"] == "library"
    assert rerun_status["status"] == "completed"
    assert rerun_status["cache_hit"] is False
    assert rerun_status["contract_hash"] == library_status["contract_hash"]
    rerun_result = _assert_ok(client.get(f"/api/v1/runs/{rerun_status['id']}/result"))
    _assert_results_close(library_result["result"], rerun_result["result"])
    rerun_preview = _assert_ok(client.get(f"/api/v1/runs/{rerun_status['id']}/preview"))
    _assert_results_close(
        library_preview["preview"], rerun_preview["preview"], path="rerun_preview"
    )

    listed_runs = _assert_ok(client.get(f"/api/v1/runs?account_id={account_id}"))["items"]
    listed_ids = {item["id"] for item in listed_runs}
    assert library_status["id"] in listed_ids
    assert second_status["id"] in listed_ids
    assert rerun_status["id"] in listed_ids
    assert stored_rerun_status["id"] in listed_ids

    with app.state.database_session_factory() as session:
        runs = session.query(Run).filter(Run.account_id == account_id).all()
        cache_entries = session.query(RunCacheEntry).all()
        artifacts = session.query(RunArtifact).all()
        full_artifacts = [
            artifact for artifact in artifacts if artifact.artifact_kind == "full_result"
        ]
        preview_artifacts = [
            artifact for artifact in artifacts if artifact.artifact_kind == "preview_series"
        ]
        assert len(runs) >= 3
        assert len(cache_entries) == 1
        assert len(full_artifacts) >= 3
        assert len(preview_artifacts) >= 3
        assert all(run.input_contract.get("contract_hash") == run.contract_hash for run in runs)
        assert any(artifact.inline_payload for artifact in full_artifacts)
        assert all(artifact.inline_payload for artifact in preview_artifacts)
        assert all(artifact.evictable is True for artifact in full_artifacts)
        assert all(artifact.evictable is False for artifact in preview_artifacts)
        assert all(
            (run.summary_series or {}).get("profile_name") == "default_run_preview" for run in runs
        )


def _simulate_full_result_eviction(app: Any) -> None:
    with app.state.database_session_factory() as session:
        for artifact in session.query(RunArtifact).filter(
            RunArtifact.artifact_kind == "full_result"
        ):
            assert artifact.evictable is True
            artifact.inline_payload = None
        session.commit()


def _assert_preview_matches_result(preview: dict[str, Any], result: dict[str, Any]) -> None:
    assert preview["artifact_kind"] == "preview_series"
    assert preview["profile_name"] == "default_run_preview"
    assert preview["profile_version"] == 1
    assert preview["downsample_method"] == "uniform_stride_include_endpoints"
    assert preview["preview_row_count"] <= preview["max_points"]
    assert preview["original_row_count"] >= preview["preview_row_count"]
    assert preview["original_row_count"] > preview["max_points"]
    assert preview["sampled_indices"][0] == 0
    assert preview["sampled_indices"][-1] == preview["original_row_count"] - 1

    table = result["report_table"]
    table_columns = {column["key"]: column for column in table["columns"]}
    assert preview["axis_key"] == table["axis_key"]
    assert preview["original_row_count"] == table["row_count"]
    for preview_column in preview["columns"]:
        key = preview_column["key"]
        source_values = table_columns[key]["values"]
        expected_values = [source_values[index] for index in preview["sampled_indices"]]
        _assert_results_close(preview_column["values"], expected_values, path=f"preview.{key}")


def _assert_results_close(left: Any, right: Any, *, path: str = "result") -> None:
    if isinstance(left, dict):
        assert isinstance(right, dict), f"{path}: expected dict"
        assert set(left) == set(right), f"{path}: key mismatch {set(left) ^ set(right)}"
        for key in left:
            _assert_results_close(left[key], right[key], path=f"{path}.{key}")
        return
    if isinstance(left, list):
        assert isinstance(right, list), f"{path}: expected list"
        assert len(left) == len(right), f"{path}: length mismatch"
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            _assert_results_close(left_item, right_item, path=f"{path}[{index}]")
        return
    if isinstance(left, float):
        assert isinstance(right, (float, int)), f"{path}: expected float-like"
        assert abs(left - float(right)) <= 1e-9 * max(1.0, abs(left)), f"{path}: {left} != {right}"
        return
    assert left == right, f"{path}: {left!r} != {right!r}"


def _deep_copy(value: Any) -> Any:
    import copy

    return copy.deepcopy(value)


if __name__ == "__main__":
    main()
