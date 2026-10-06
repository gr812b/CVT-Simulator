"""Real contracts, authenticated run admission and the durable worker lifecycle.

The worker integration executes one 0.05-second CINDER simulation in its normal
child process. Queue, cancellation and recovery checks do not run simulations.
"""

from __future__ import annotations

import copy
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import delete

from app.application import cinder_gateway, jobs
from app.database.models import Run, RunArtifact
from app.main import create_app

BACKEND = Path(__file__).resolve().parents[1]


def baseline_document(client: TestClient) -> dict:
    response = client.get("/api/v1/presets/baja-launch-baseline")
    assert response.status_code == 200
    return response.json()["simulation_case"]


def test_metadata_and_preset_to_validation_journey(signed_in) -> None:
    client = signed_in
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
    assert editor_schema.json()["document"]["fields"]
    assert editor_schema.json()["document"]["component_catalog"] == catalog.json()["document"]
    assert (
        document_schema.json()["document"]["properties"]["document_type"]["const"]
        == "cinder_composed_simulation_case"
    )

    document = baseline_document(client)
    Draft202012Validator(document_schema.json()["document"]).validate(document)
    validated = client.post("/api/v1/simulation-cases/validate", json={"simulation_case": document})
    assert validated.status_code == 200
    assert validated.json()["validation"]["is_valid"] is True


def test_geometry_study_journey(signed_in) -> None:
    client = signed_in
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


@pytest.mark.parametrize("pulley, location", [("input", "primary"), ("output", "secondary")])
def test_clamping_study_maps_http_pulley_to_cinder(signed_in, monkeypatch, pulley, location):
    client = signed_in
    document = baseline_document(client)
    sample = cinder_gateway.sample_pulley_clamping_force

    def sample_selected_pulley(request):
        assert request.pulley.value == location
        return sample(request)

    monkeypatch.setattr(cinder_gateway, "sample_pulley_clamping_force", sample_selected_pulley)
    actuation_response = client.post(
        "/api/v1/studies/actuation/clamping-response",
        json={
            "assembly_document": document["assembly"],
            "pulley": pulley,
            "shift_position_m": 0.0,
            "shaft_speed_rad_per_s": 0.0,
            "shift_speed_m_per_s": 0.0,
            "axes": [
                {"coordinate": "shift_position", "values": [0.0, 0.005]},
                {"coordinate": "shaft_speed", "values": [0.0, 200.0]},
            ],
        },
    )
    assert actuation_response.status_code == 200, actuation_response.text
    clamping = actuation_response.json()["study"]
    assert clamping["kind"] == "clamping_force_response"
    assert clamping["shape"] == [2, 2]
    assert "total_clamping_force_N" in {column["key"] for column in clamping["columns"]}


def test_clamping_study_rejects_an_unknown_pulley(signed_in):
    payload = {
        "assembly_document": baseline_document(signed_in)["assembly"],
        "pulley": "neither",
        "shift_position_m": 0,
        "axes": [{"coordinate": "shaft_speed", "values": [0, 200]}],
    }
    rejected = signed_in.post("/api/v1/studies/actuation/clamping-response", json=payload)
    assert rejected.status_code == 422
    assert any(issue["loc"][-1] == "pulley" for issue in rejected.json()["detail"])
    with pytest.raises(ValueError, match="pulley must be 'input' or 'output'"):
        signed_in.app.state.container.gateway.clamping_response(payload)


def short_request(client):
    case = baseline_document(client)
    case["scenario"]["time_span_s"] = [0.0, 0.05]
    return {"request_key": str(uuid4()), "simulation_case": case}


def submit(client, payload):
    response = client.post("/api/v1/runs", json=payload)
    assert response.status_code == 202, response.text
    return response.json()


def test_authenticated_admission_idempotency_and_queued_cancel(api, register):
    payload = short_request(api)
    assert api.post("/api/v1/runs", json=payload).status_code == 401
    register(api)
    missing_csrf = api.post("/api/v1/runs", json=payload, headers={"X-CSRF-Token": ""})
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["error"]["code"] == "csrf_invalid"
    first = submit(api, payload)
    assert first["status"] == "queued"
    assert first["started_at"] is None
    assert first["has_result"] is False
    assert submit(api, payload)["id"] == first["id"]
    conflict = copy.deepcopy(payload)
    conflict["simulation_case"]["scenario"]["time_span_s"][1] = 0.04
    response = api.post("/api/v1/runs", json=conflict)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"
    active = api.post("/api/v1/runs", json={**payload, "request_key": str(uuid4())})
    assert active.status_code == 409
    assert active.json()["error"]["code"] == "run_already_active"

    path = f"/api/v1/runs/{first['id']}"
    assert api.get(f"{path}/result").status_code == 409
    cancelled = api.post(f"{path}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["completed_at"] is not None
    assert api.post(f"{path}/cancel").json()["status"] == "cancelled"
    with api.app.state.database_session_factory.begin() as session:
        assert jobs.claim(session, api.app.state.settings) is None
    assert len(api.get("/api/v1/runs").json()["items"]) == 1
    assert api.get("/api/v1/runs/activity").json()["active"] is None


def test_invalid_run_contract_and_resource_limits_never_enter_queue(signed_in):
    client = signed_in
    payload = short_request(client)
    missing_key = client.post("/api/v1/runs", json={"simulation_case": payload["simulation_case"]})
    assert missing_key.status_code == 422
    too_long = copy.deepcopy(payload)
    too_long["simulation_case"]["scenario"]["time_span_s"] = [0, 301]
    limited = client.post("/api/v1/runs", json=too_long)
    assert limited.status_code == 422
    assert limited.json()["error"]["code"] == "run_limits"
    invalid = copy.deepcopy(payload)
    invalid["simulation_case"]["assembly"]["geometry"]["belt_outer_length_m"] = "invalid"
    rejected = client.post("/api/v1/runs", json=invalid)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "invalid_simulation_case"
    assert client.get("/api/v1/runs").json()["items"] == []


def test_worker_claim_token_and_running_cancellation_hold_the_slot(signed_in):
    client = signed_in
    payload = short_request(client)
    queued = submit(client, payload)
    factory, settings = client.app.state.database_session_factory, client.app.state.settings
    with factory.begin() as session:
        claimed = jobs.claim(session, settings)
        assert claimed.id == queued["id"]
        assert claimed.status == "running"
        assert claimed.worker_token
        token = claimed.worker_token
    with factory.begin() as session:
        assert jobs.claim(session, settings) is None
        assert jobs.finish(session, claimed.id, "stale-worker-token", terminal="completed") is False
    path = f"/api/v1/runs/{claimed.id}"
    cancellation = client.post(f"{path}/cancel").json()
    assert cancellation["status"] == "running"
    assert cancellation["cancel_requested_at"]
    blocked = client.post("/api/v1/runs", json={**payload, "request_key": str(uuid4())})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "run_already_active"
    with factory.begin() as session:
        assert jobs.finish(session, claimed.id, token, terminal="cancelled") is True
        assert jobs.finish(session, claimed.id, token, terminal="completed") is False
    assert client.get(path).json()["status"] == "cancelled"
    next_run = submit(client, {**payload, "request_key": str(uuid4())})
    assert next_run["status"] == "queued"
    assert client.post(f"/api/v1/runs/{next_run['id']}/cancel").json()["status"] == "cancelled"


def test_abandoned_worker_recovers_only_after_deadline_and_grace(signed_in):
    client = signed_in
    queued = submit(client, short_request(client))
    factory, settings = client.app.state.database_session_factory, client.app.state.settings
    with factory.begin() as session:
        claimed = jobs.claim(session, settings)
        token = claimed.worker_token
    with factory.begin() as session:
        jobs.recover(session, settings)
        assert session.get(Run, queued["id"]).status == "running"
        session.get(Run, queued["id"]).deadline_at = jobs.database_now(session) - timedelta(
            seconds=settings.run_recovery_grace_seconds + 1
        )
    with factory.begin() as session:
        jobs.recover(session, settings)
        run = session.get(Run, queued["id"])
        assert run.status == "failed"
        assert run.error["code"] == "worker_interrupted"
        assert run.worker_token is None
        assert jobs.finish(session, run.id, token, terminal="completed") is False
    assert client.get("/api/v1/runs/activity").json()["active"] is None


@pytest.mark.skipif(os.name != "posix", reason="The production worker requires POSIX deadlines.")
def test_durable_worker_result_frozen_rerun_and_artifact_retention(signed_in, register):
    client = signed_in
    payload = short_request(client)
    queued = submit(client, payload)
    path = f"/api/v1/runs/{queued['id']}"
    settings = client.app.state.settings

    # Another application instance sees the queued job before any worker runs.
    restarted_app = create_app(settings)
    try:
        with TestClient(restarted_app) as restarted:
            restarted.cookies.update(client.cookies)
            assert restarted.get(path).json()["status"] == "queued"
            assert (
                restarted.get(f"{path}/input").json()["input_document_snapshot"]
                == payload["simulation_case"]
            )
    finally:
        restarted_app.state.database_engine.dispose()

    completed_worker = subprocess.run(
        [sys.executable, "-m", "app.scripts.run_worker", "--once"],
        cwd=BACKEND,
        env={
            **{key: value for key, value in os.environ.items() if not key.startswith("CVT_")},
            "CVT_DATABASE_URL": settings.database_url,
            "CVT_RUN_TIMEOUT_SECONDS": str(settings.run_timeout_seconds),
            "CVT_WORKER_POLL_SECONDS": str(settings.worker_poll_seconds),
            "CVT_ENVIRONMENT": "development",
            "CVT_WEB_URL": settings.web_url,
            "CVT_MAIL_MODE": "outbox",
            "CVT_MAIL_OUTBOX": str(settings.mail_outbox),
        },
        capture_output=True,
        text=True,
        timeout=settings.run_timeout_seconds + 15,
    )
    assert completed_worker.returncode == 0, completed_worker.stderr
    finished = client.get(path).json()
    assert finished["status"] == "completed", (finished, completed_worker.stderr)
    assert finished["started_at"] and finished["completed_at"]
    assert finished["has_result"] is True
    response = client.get(f"{path}/result")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["input_document_snapshot"] == payload["simulation_case"]
    assert result["result"]["kind"] == "simulation_result"
    assert result["result"]["report_table"]["row_count"] >= 2
    assert "reported_segments" not in result["result"]
    preview = client.get(f"{path}/preview")
    assert preview.status_code == 200
    assert preview.json()["preview"]["preview_row_count"] >= 2
    activity = client.get("/api/v1/runs/activity").json()
    assert activity["active"] is None
    assert len(activity["unread"]) == 1
    notice_id = activity["unread"][0]["id"]
    assert client.post(f"/api/v1/runs/notices/{notice_id}/read").status_code == 204
    assert client.get("/api/v1/runs/activity").json()["unread_count"] == 0

    # Runs are public to read, while control and account activity remain owned.
    with TestClient(client.app) as other:
        assert other.get(f"{path}/input").status_code == 200
        assert other.get(f"{path}/preview").status_code == 200
        assert other.get(f"{path}/result").status_code == 200
        register(other, email="observer@example.com", name="Observer")
        assert other.get(path).status_code == 404
        assert other.post(f"{path}/cancel").status_code == 404
        assert other.post(f"{path}/rerun", json={"request_key": str(uuid4())}).status_code == 404

    rerun = client.post(f"{path}/rerun", json={"request_key": str(uuid4())})
    assert rerun.status_code == 202, rerun.text
    assert rerun.json()["status"] == "queued"
    assert rerun.json()["parent_run_id"] == queued["id"]
    rerun_path = f"/api/v1/runs/{rerun.json()['id']}"
    assert (
        client.get(f"{rerun_path}/input").json()["input_document_snapshot"]
        == payload["simulation_case"]
    )
    assert client.post(f"{rerun_path}/cancel").json()["status"] == "cancelled"

    with client.app.state.database_session_factory.begin() as session:
        session.execute(
            delete(RunArtifact).where(
                RunArtifact.run_id == queued["id"], RunArtifact.artifact_kind == "full_result"
            )
        )
    missing = client.get(f"{path}/result")
    assert missing.status_code == 410
    assert missing.json()["error"]["code"] == "run_result_artifact_missing"
    assert client.get(f"{path}/preview").json()["preview"] == preview.json()["preview"]
    assert (
        client.get(f"{path}/input").json()["input_document_snapshot"] == payload["simulation_case"]
    )
    after_eviction = client.post(f"{path}/rerun", json={"request_key": str(uuid4())})
    assert after_eviction.status_code == 202
    assert (
        client.post(f"/api/v1/runs/{after_eviction.json()['id']}/cancel").json()["status"]
        == "cancelled"
    )


def test_direct_run_still_accepts_frozen_input_envelopes(signed_in):
    client = signed_in
    queued = submit(client, short_request(client))
    path = f"/api/v1/runs/{queued['id']}"
    envelope = client.get(f"{path}/input").json()
    client.post(f"{path}/cancel")
    from_envelope = submit(client, {**envelope, "request_key": str(uuid4())})
    assert from_envelope["status"] == "queued"
    assert (
        client.get(f"/api/v1/runs/{from_envelope['id']}/input").json()["input_document_snapshot"]
        == envelope["input_document_snapshot"]
    )
    assert client.post(f"/api/v1/runs/{from_envelope['id']}/cancel").json()["status"] == "cancelled"
