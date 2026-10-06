"""Stored outcomes distinguish model stops, execution errors and valid evidence."""

from __future__ import annotations

import copy
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cinder.contracts import SIMULATION_RESULT_CONTRACT_VERSION
from sqlalchemy import delete, select

from app.application import jobs, run_outcomes
from app.database import runs as artifacts
from app.database.hashing import canonical_json_hash
from app.database.models import Run, RunArtifact


def sample_result(*, reason="checkpoint", completed=False):
    columns = [
        {
            "key": key,
            "label": label,
            "canonical_unit": unit,
            "dimension": dimension,
            "group": "state",
            "description": "",
            "values": values,
        }
        for key, label, unit, dimension, values in (
            ("time_s", "Time", "s", "time", [0.0, 0.25, 0.5]),
            ("vehicle.distance", "Distance", "m", "length", [0.0, 0.5, 1.5]),
            ("vehicle.speed", "Speed", "m/s", "velocity", [0.0, 2.0, 4.0]),
        )
    ]
    return {
        "contract_version": SIMULATION_RESULT_CONTRACT_VERSION,
        "kind": "simulation_result",
        "metrics": {
            "completed": completed,
            "termination_reason": reason,
            "duration_s": 0.5,
            "vehicle_distance_final_m": 1.5,
        },
        "summary": {},
        "warnings": [],
        "transitions": [],
        "report_table": {"axis_key": "time_s", "row_count": 3, "columns": columns},
    }


def stored_run(*, status="failed", reason=None, error=None, data=True, completed=False):
    result = sample_result(reason=reason, completed=completed)
    return SimpleNamespace(
        id="support-run-id",
        status=status,
        error=error,
        summary_scalars=artifacts.summary_scalars(result),
        summary_series=artifacts.build_preview_from_result(result) if data else {},
    )


@pytest.mark.parametrize(
    "status,reason,error_code,completed,category",
    [
        ("queued", None, None, False, "pending"),
        ("running", "checkpoint", None, False, "pending"),
        ("completed", "course_finish", None, True, "success"),
        ("completed", "duration_reached", None, True, "success"),
        ("completed", "time_limit", None, False, "vehicle_stopped"),
        ("completed", "rollback_limit", None, False, "vehicle_stopped"),
        ("completed", "no_forward_progress", None, False, "vehicle_stopped"),
        ("failed", "checkpoint", "mechanism_contact_unsupported", False, "model_limit"),
        ("completed", "contact_loss_normal_resultant_floor", None, False, "model_limit"),
        ("completed", "maximum_transitions", None, False, "numerical_error"),
        ("failed", "checkpoint", "numerical_failure", False, "numerical_error"),
        ("failed", None, "invalid_simulation_case", False, "configuration_error"),
        ("failed", "checkpoint", "simulation_failed", False, "internal_error"),
        ("failed", "checkpoint", "new_unknown_error", False, "internal_error"),
        ("failed", "checkpoint", "result_persistence_failed", False, "service_error"),
        ("failed", "checkpoint", "checkpoint_persistence_failed", False, "service_error"),
        ("failed", "checkpoint", "child_protocol_error", False, "service_error"),
        ("failed", None, "queue_timeout", False, "service_error"),
        ("timed_out", "checkpoint", "run_timeout", False, "resource_limit"),
        ("failed", "checkpoint", "run_memory_limit", False, "resource_limit"),
        ("failed", "checkpoint", "run_result_size_limit", False, "resource_limit"),
        ("cancelled", "checkpoint", "simulation_failed", False, "cancelled"),
    ],
)
def test_outcome_uses_confirmed_reason_and_keeps_unclassified_errors_internal(
    status, reason, error_code, completed, category
):
    raw_error = "Traceback: ValueError('/private/server/path token=do-not-display')"
    run = stored_run(
        status=status,
        reason=reason,
        error={"code": error_code, "message": raw_error} if error_code else None,
        completed=completed,
    )
    outcome = run_outcomes.outcome(run)
    assert outcome.category == category
    assert raw_error not in outcome.model_dump_json()
    assert outcome.support_run_id == run.id
    assert outcome.reached_time_s == 0.5
    assert outcome.reached_distance_m == 1.5
    assert outcome.partial is (category != "success")


def test_initial_failure_is_not_partial_data_and_empty_or_invalid_previews_do_not_count():
    run = stored_run(error={"code": "simulation_failed"}, data=False)
    for preview in (
        {},
        {"preview_row_count": 10, "columns": []},
        {"columns": [{"key": "time_s", "values": [0.0, 1.0]}]},
        {
            "columns": [
                {"key": "time_s", "values": [None, float("nan")]},
                {"key": "vehicle.distance", "values": [0.0, 1.0]},
            ]
        },
    ):
        run.summary_series = preview
        outcome = run_outcomes.outcome(run)
        assert outcome.has_data is False
        assert outcome.partial is False
        assert outcome.reached_time_s is None
        assert outcome.reached_distance_m is None


def test_progress_is_last_valid_saved_sample_not_unsaved_metrics_or_invalid_tail():
    run = stored_run(error={"code": "simulation_failed"})
    run.summary_scalars["metrics"].update(duration_s=99, vehicle_distance_final_m=1000)
    for column in run.summary_series["columns"]:
        column["values"].append(None if column["key"] != "time_s" else 1.0)
    outcome = run_outcomes.outcome(run)
    assert outcome.has_data is True
    assert outcome.reached_time_s == 0.5
    assert outcome.reached_distance_m == 1.5


def claim_run(client):
    case = client.get("/api/v1/presets/baja-launch-baseline").json()["simulation_case"]
    case["scenario"]["time_span_s"] = [0.0, 1.0]
    response = client.post(
        "/api/v1/runs", json={"request_key": str(uuid4()), "simulation_case": case}
    )
    assert response.status_code == 202, response.text
    queued = response.json()
    assert queued["outcome"]["category"] == "pending"
    assert queued["outcome"]["has_data"] is False
    factory = client.app.state.database_session_factory
    with factory.begin() as session:
        run = jobs.claim(session, client.app.state.settings)
        return run.id, run.worker_token, factory


def assert_saved_checkpoint(client, run_id, *, reason, category, status="failed"):
    path = f"/api/v1/runs/{run_id}"
    response = client.get(path).json()
    assert response["status"] == status
    assert response["has_result"] is True
    assert response["outcome"]["category"] == category
    assert response["outcome"]["partial"] is True
    assert response["outcome"]["reached_time_s"] == 0.5
    assert response["outcome"]["reached_distance_m"] == 1.5
    preview = client.get(f"{path}/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["preview"]["original_row_count"] == 3
    inspection = client.get(f"{path}/inspection")
    assert inspection.status_code == 200, inspection.text
    assert inspection.json()["availability"]["partial"] is True
    assert inspection.json()["termination_reason"] == reason
    activity = client.get("/api/v1/runs/activity").json()
    assert activity["active"] is None
    assert len(activity["unread"]) == 1
    assert activity["unread"][0]["run"]["outcome"] == response["outcome"]
    with client.app.state.database_session_factory() as session:
        result = artifacts.get_database_run_result(session, run_id)
        assert result["report_table"] == sample_result()["report_table"]
        assert result["metrics"]["completed"] is False
        assert result["metrics"]["termination_reason"] == reason
        full = session.scalar(
            select(RunArtifact).where(
                RunArtifact.run_id == run_id, RunArtifact.artifact_kind == "full_result"
            )
        )
        assert full.content_hash == canonical_json_hash(result)
        assert preview.json()["preview"]["source_result_hash"] == full.content_hash


def test_failure_after_checkpoint_retains_valid_data_and_notifies_with_model_limit(signed_in):
    run_id, token, factory = claim_run(signed_in)
    with factory.begin() as session:
        assert jobs.checkpoint(session, run_id, token, sample_result())
    with factory.begin() as session:
        assert jobs.finish(
            session,
            run_id,
            token,
            error={"code": "mechanism_contact_unsupported", "message": "Model contact limit."},
        )
    assert_saved_checkpoint(
        signed_in, run_id, reason="mechanism_contact_unsupported", category="model_limit"
    )


def test_historical_run_uses_durable_preview_without_rewriting_saved_evidence(signed_in):
    run_id, token, factory = claim_run(signed_in)
    with factory.begin() as session:
        jobs.checkpoint(session, run_id, token, sample_result())
        jobs.finish(
            session,
            run_id,
            token,
            error={"code": "mechanism_contact_unsupported", "message": "Model contact limit."},
        )
        session.get(Run, run_id).summary_series = {}
        before = {
            item.artifact_kind: (
                item.content_hash,
                item.byte_size,
                copy.deepcopy(item.inline_payload),
            )
            for item in session.scalars(select(RunArtifact).where(RunArtifact.run_id == run_id))
        }
    assert_saved_checkpoint(
        signed_in, run_id, reason="mechanism_contact_unsupported", category="model_limit"
    )
    with factory() as session:
        assert session.get(Run, run_id).summary_series == {}
        assert {
            item.artifact_kind: (item.content_hash, item.byte_size, item.inline_payload)
            for item in session.scalars(select(RunArtifact).where(RunArtifact.run_id == run_id))
        } == before


def test_failure_before_any_checkpoint_has_no_partial_result(signed_in):
    run_id, token, factory = claim_run(signed_in)
    with factory.begin() as session:
        assert jobs.finish(
            session, run_id, token, error={"code": "simulation_failed", "message": "Failed."}
        )
    path = f"/api/v1/runs/{run_id}"
    response = signed_in.get(path).json()
    assert response["outcome"]["category"] == "internal_error"
    assert response["has_result"] is False
    assert response["outcome"]["partial"] is False
    assert response["outcome"]["reached_time_s"] is None
    inspection = signed_in.get(f"{path}/inspection").json()
    assert inspection["availability"] == {
        "full_result": False,
        "preview": False,
        "partial": False,
        "original_row_count": None,
        "full_result_hash": None,
    }
    assert signed_in.get(f"{path}/preview").status_code == 410
    assert signed_in.get("/api/v1/runs/activity").json()["unread_count"] == 1


def test_final_storage_failure_preserves_prior_checkpoint_without_retrying_failed_builder(
    signed_in, monkeypatch
):
    run_id, token, factory = claim_run(signed_in)
    with factory.begin() as session:
        jobs.checkpoint(session, run_id, token, sample_result())

    def fail_to_save(*args, **kwargs):
        raise RuntimeError("Result projection/storage failed")

    monkeypatch.setattr(jobs, "_save_result", fail_to_save)
    final = sample_result(reason="duration_reached", completed=True)
    final["report_table"]["columns"][0]["values"] = [0, 0.5, 1.0]
    with pytest.raises(RuntimeError, match="Result projection/storage failed"):
        with factory.begin() as session:
            jobs.finish(session, run_id, token, result=final)
    with factory.begin() as session:
        assert session.get(Run, run_id).status == "running"
        assert jobs.finish(
            session,
            run_id,
            token,
            error={"code": "result_persistence_failed", "message": "Could not save final output."},
        )
    assert_saved_checkpoint(
        signed_in, run_id, reason="result_persistence_failed", category="service_error"
    )


def test_cancellation_preserves_checkpoint_and_wins_over_a_late_worker_error(signed_in):
    run_id, token, factory = claim_run(signed_in)
    with factory.begin() as session:
        jobs.checkpoint(session, run_id, token, sample_result())
    cancelled = signed_in.post(f"/api/v1/runs/{run_id}/cancel").json()
    assert cancelled["status"] == "running"
    with factory.begin() as session:
        assert jobs.finish(
            session, run_id, token, error={"code": "simulation_failed", "message": "Late error."}
        )
    assert_saved_checkpoint(
        signed_in, run_id, reason="cancelled", category="cancelled", status="cancelled"
    )
    assert signed_in.get(f"/api/v1/runs/{run_id}").json()["error"] is None


@pytest.mark.parametrize(
    "reason,completed,status,category,error_code",
    [
        ("duration_reached", True, "completed", "success", None),
        ("time_limit", False, "completed", "vehicle_stopped", None),
        ("maximum_transitions", False, "failed", "numerical_error", "maximum_transitions"),
        (
            "contact_loss_normal_resultant_floor",
            False,
            "failed",
            "model_limit",
            "contact_loss_normal_resultant_floor",
        ),
        ("checkpoint", False, "failed", "internal_error", "incomplete_result"),
        ("unknown_incomplete_reason", False, "failed", "internal_error", "incomplete_result"),
    ],
)
def test_result_presence_does_not_turn_every_stop_into_success(
    signed_in, reason, completed, status, category, error_code
):
    run_id, token, factory = claim_run(signed_in)
    with factory.begin() as session:
        assert jobs.finish(
            session, run_id, token, result=sample_result(reason=reason, completed=completed)
        )
    response = signed_in.get(f"/api/v1/runs/{run_id}").json()
    assert response["status"] == status
    assert response["outcome"]["category"] == category
    assert (response["error"] or {}).get("code") == error_code
    assert response["outcome"]["partial"] is (category != "success")


def test_worker_recovery_keeps_preview_even_when_full_checkpoint_was_evicted(signed_in):
    run_id, token, factory = claim_run(signed_in)
    settings = signed_in.app.state.settings
    with factory.begin() as session:
        jobs.checkpoint(session, run_id, token, sample_result())
        session.get(Run, run_id).deadline_at = jobs.database_now(session) - timedelta(
            seconds=settings.run_recovery_grace_seconds + 1
        )
        session.execute(
            delete(RunArtifact).where(
                RunArtifact.run_id == run_id, RunArtifact.artifact_kind == "full_result"
            )
        )
    with factory.begin() as session:
        jobs.recover(session, settings)
        run = session.get(Run, run_id)
        assert run.status == "failed"
        assert run.summary_scalars["metrics"]["termination_reason"] == "worker_interrupted"
        assert jobs.finish(session, run_id, token, result=sample_result()) is False
    path = f"/api/v1/runs/{run_id}"
    response = signed_in.get(f"{path}/inspection").json()
    assert response["availability"]["full_result"] is False
    assert response["availability"]["preview"] is True
    assert response["availability"]["partial"] is True
    assert response["run"]["outcome"]["category"] == "service_error"
    assert signed_in.get(f"{path}/preview").status_code == 200
    assert signed_in.get("/api/v1/runs/activity").json()["unread_count"] == 1


def test_stale_worker_cannot_replace_a_retained_checkpoint(signed_in):
    run_id, token, factory = claim_run(signed_in)
    with factory.begin() as session:
        jobs.checkpoint(session, run_id, token, sample_result())
    altered = copy.deepcopy(sample_result())
    altered["report_table"]["columns"][0]["values"][-1] = 99
    with factory.begin() as session:
        assert jobs.checkpoint(session, run_id, "stale", altered) is False
        assert jobs.finish(session, run_id, "stale", result=altered) is False
        saved = artifacts.get_database_run_result(session, run_id)
        assert saved["report_table"] == sample_result()["report_table"]
