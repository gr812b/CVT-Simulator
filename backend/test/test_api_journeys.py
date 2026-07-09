"""High-value endpoint journeys using real FastAPI + real CINDER contracts."""

from __future__ import annotations

import copy
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def build_client() -> TestClient:
    app = create_app(
        Settings(
            preset_directory=ROOT / "presets",
            run_timeout_seconds=30.0,
            run_executor_mode="inline",
            cors_origins=(),
        )
    )
    return TestClient(app)


def baseline_document(client: TestClient) -> dict:
    response = client.get("/api/v1/presets/baja-launch-baseline")
    assert response.status_code == 200
    return response.json()["simulation_case"]


def test_metadata_and_preset_to_validation_journey() -> None:
    client = build_client()
    assert client.get("/api/v1/health").json() == {"status": "ok", "api_version": "v1"}

    conventions = client.get("/api/v1/metadata/conventions")
    catalog = client.get("/api/v1/metadata/catalog")
    editor_schema = client.get("/api/v1/metadata/editor-schema")
    document_schema = client.get("/api/v1/metadata/simulation-case-schema")
    assert conventions.status_code == 200
    assert catalog.status_code == 200
    assert editor_schema.status_code == 200
    assert document_schema.status_code == 200
    assert conventions.json()["document"]["canonical_unit_system"] == "SI"
    assert editor_schema.json()["document"]["target_document_type"] == "cinder_simulation_case"
    assert (
        document_schema.json()["document"]["properties"]["document_type"]["const"]
        == "cinder_simulation_case"
    )

    document = baseline_document(client)
    validated = client.post("/api/v1/simulation-cases/validate", json={"simulation_case": document})
    assert validated.status_code == 200
    assert validated.json()["validation"]["is_valid"] is True


def test_geometry_and_clamping_study_journeys() -> None:
    client = build_client()
    document = baseline_document(client)
    geometry = document["assembly"]["geometry"]
    context = {
        "belt": geometry["belt"],
        "belt_outer_length_m": geometry["belt_outer_length_m"],
        "sheave_half_angle_rad": geometry["sheave_half_angle_rad"],
        "deadzone_shift_m": geometry["deadzone_shift_m"],
        "max_shift_m": geometry["max_shift_m"],
    }
    geometry_response = client.post(
        "/api/v1/studies/geometry/endpoint-radii",
        json={
            "context": context,
            "primary_outer_radius_at_zero_shift_m": geometry[
                "primary_outer_radius_at_zero_shift_m"
            ],
            "secondary_outer_radius_at_zero_shift_m": geometry[
                "secondary_outer_radius_at_zero_shift_m"
            ],
            "sample_count": 11,
        },
    )
    assert geometry_response.status_code == 200
    study = geometry_response.json()["study"]
    assert study["kind"] == "geometry_design_response"
    assert study["path"]["shape"] == [11]
    assert "ratio_change_per_m_shift" in {column["key"] for column in study["path"]["columns"]}

    actuation_response = client.post(
        "/api/v1/studies/actuation/clamping-response",
        json={
            "assembly_document": document["assembly"],
            "pulley": "input",
            "shift_position_m": 0.0,
            "shaft_speed_rad_per_s": 0.0,
            "shift_speed_m_per_s": 0.0,
            "axes": [
                {"coordinate": "shift_position", "values": [0.0, 0.005]},
                {"coordinate": "shaft_speed", "values": [0.0, 200.0]},
            ],
        },
    )
    assert actuation_response.status_code == 200
    clamping = actuation_response.json()["study"]
    assert clamping["kind"] == "clamping_force_response"
    assert clamping["shape"] == [2, 2]
    assert "total_clamping_force_N" in {column["key"] for column in clamping["columns"]}


def test_run_lifecycle_journey_and_invalid_document() -> None:
    client = build_client()
    document = baseline_document(client)
    short_document = copy.deepcopy(document)
    short_document["scenario"]["time_span_s"] = [0.0, 0.05]

    created = client.post("/api/v1/runs", json={"simulation_case": short_document})
    assert created.status_code == 202
    status = created.json()
    assert status["status"] == "completed"

    fetched = client.get(f"/api/v1/runs/{status['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "completed"

    result = client.get(f"/api/v1/runs/{status['id']}/result")
    assert result.status_code == 200
    body = result.json()
    assert body["input_document_snapshot"] == short_document
    assert body["result"]["kind"] == "simulation_result"
    assert "report_table" in body["result"]
    assert "reported_segments" not in body["result"]

    invalid_document = copy.deepcopy(short_document)
    invalid_document["assembly"]["contact"]["friction_coefficient"] = "invalid"
    rejected = client.post("/api/v1/runs", json={"simulation_case": invalid_document})
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "simulation_case_invalid"


def test_direct_run_accepts_frozen_input_response_envelope() -> None:
    client = build_client()
    document = baseline_document(client)
    short_document = copy.deepcopy(document)
    short_document["scenario"]["time_span_s"] = [0.0, 0.03]

    created = client.post("/api/v1/runs", json={"simulation_case": short_document})
    assert created.status_code == 202
    run_id = created.json()["id"]

    input_response = client.get(f"/api/v1/runs/{run_id}/input")
    assert input_response.status_code == 200
    input_envelope = input_response.json()

    rerun_from_envelope = client.post("/api/v1/runs", json=input_envelope)
    assert rerun_from_envelope.status_code == 202
    rerun_status = rerun_from_envelope.json()
    assert rerun_status["status"] == "completed"

    rerun_from_raw_document = client.post(
        "/api/v1/runs", json=input_envelope["input_document_snapshot"]
    )
    assert rerun_from_raw_document.status_code == 202
    assert rerun_from_raw_document.json()["status"] == "completed"
