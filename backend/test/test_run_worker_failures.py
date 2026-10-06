"""Failures cross the child/worker boundary without losing accepted checkpoints."""

from __future__ import annotations

import json
import os
import sys
import time
from uuid import uuid4

import pytest

pytest.importorskip("resource", reason="The production child requires POSIX limits.")

from cinder.model.cvt.dynamics import TrialClosureSolveError  # noqa: E402

from app.application import cinder_gateway, jobs  # noqa: E402
from app.application.run_failures import RunFailure  # noqa: E402
from app.scripts import run_child, run_worker  # noqa: E402
from test_run_outcomes import sample_result  # noqa: E402


@pytest.mark.parametrize(
    "exception,code",
    [
        (
            RuntimeError(
                "Unilateral pulley-mechanism contact became inadmissible: "
                "secondary/1:HelicalTorqueReactionForce=-0.178025776. "
                "A lift-off/opposite-flank topology is not modeled."
            ),
            "mechanism_contact_unsupported",
        ),
        (
            RuntimeError(
                "Unilateral pulley-mechanism contact became inadmissible in deadzone: "
                "secondary/1:HelicalTorqueReactionForce=-46.2465014. "
                "The missing contact topology is not modeled."
            ),
            "mechanism_contact_unsupported",
        ),
        (TrialClosureSolveError("singular closure"), "numerical_failure"),
        (FloatingPointError("invalid floating-point state"), "numerical_failure"),
        (RuntimeError("solve_ivp failed: step size became too small"), "numerical_failure"),
        (
            RuntimeError(
                "Hybrid integration exceeded maximum_transitions without reaching final time."
            ),
            "maximum_transitions",
        ),
        (ValueError("an internal value could not be calculated"), None),
        (RuntimeError("unexpected implementation error"), None),
    ],
)
def test_only_confirmed_solver_failures_are_classified(exception, code):
    failure = cinder_gateway._known_integration_failure(exception)
    assert (failure.code if failure else None) == code


@pytest.fixture
def child_call(tmp_path, monkeypatch):
    input_path, output_path = tmp_path / "input.json", tmp_path / "output.json"
    identity = cinder_gateway.CinderGateway().runtime_identity()
    input_path.write_text(
        json.dumps(
            {
                "run_id": "diagnostic-run-id",
                "input": {},
                "options": {},
                "runtime_identity": identity,
                "worker_pid": os.getpid(),
                "deadline_monotonic": time.monotonic() + 60,
                "memory_bytes": 1024**3,
                "result_bytes": 100_000,
            }
        )
    )
    # Exercise the real envelope/error/checkpoint code without limiting pytest.
    monkeypatch.setattr(run_child, "apply_limits", lambda _: None)
    monkeypatch.setattr(run_child, "monitor_worker_parent", lambda _: True)
    monkeypatch.setattr(run_child.signal, "signal", lambda *_: None)
    monkeypatch.setattr(run_child.signal, "setitimer", lambda *_: None)
    monkeypatch.setattr(sys, "argv", ["run_child", str(input_path), str(output_path)])

    def invoke(compute):
        monkeypatch.setattr(
            cinder_gateway.CinderGateway,
            "run_checkpointed",
            lambda _, document, **options: compute(**options),
        )
        exit_code = run_child.main()
        return exit_code, json.loads(output_path.read_text()), output_path

    return invoke


@pytest.mark.parametrize("save_first", [False, True])
def test_child_handles_internal_error_without_blame_and_preserves_prior_data(
    child_call, save_first, caplog
):
    checkpoint_result = sample_result()

    def compute(*, checkpoint, **_):
        if save_first:
            checkpoint(checkpoint_result)
        raise ValueError("private diagnostic: /server/internal/path")

    code, payload, output_path = child_call(compute)
    assert code == 1
    assert payload["error"]["code"] == "simulation_failed"
    assert "internal error" in payload["error"]["message"]
    assert "Review the tune" not in payload["error"]["message"]
    assert "private diagnostic" not in json.dumps(payload)
    assert "private diagnostic" in caplog.text
    assert "diagnostic-run-id" in caplog.text
    checkpoint_path = output_path.with_name("checkpoint.json")
    assert checkpoint_path.exists() is save_first
    if save_first:
        assert json.loads(checkpoint_path.read_text()) == checkpoint_result


def test_child_reports_known_model_limit_with_nonzero_exit(child_call):
    def compute(**_):
        raise RunFailure("mechanism_contact_unsupported", "A contact state is unsupported.")

    code, payload, _ = child_call(compute)
    assert code == 1
    assert payload["error"]["code"] == "mechanism_contact_unsupported"
    assert payload["error"]["details"]["phase"] == "simulation"


@pytest.mark.parametrize(
    "bad_result,code",
    [
        ({"nonfinite": float("nan")}, "result_serialization_failed"),
        ({"oversized": "x" * 100_001}, "run_result_size_limit"),
    ],
)
def test_unusable_checkpoint_does_not_replace_last_saved_data(child_call, bad_result, code):
    previous = sample_result()

    def compute(*, checkpoint, **_):
        checkpoint(previous)
        checkpoint(bad_result)

    exit_code, payload, output_path = child_call(compute)
    assert exit_code == 1
    assert payload["error"]["code"] == code
    assert json.loads(output_path.with_name("checkpoint.json").read_text()) == previous


def test_child_success_still_returns_a_normal_completion_envelope(child_call):
    result = sample_result(reason="duration_reached", completed=True)
    code, payload, _ = child_call(lambda **_: result)
    assert code == 0
    assert payload == {"result": result}


@pytest.mark.parametrize("returncode", [0, 1])
def test_worker_reads_handled_errors_from_both_old_and_new_children(tmp_path, returncode):
    output = tmp_path / "output.json"
    error = {"code": "mechanism_contact_unsupported", "message": "Contact model limit."}
    output.write_text(json.dumps({"error": error}))
    assert run_worker.read_child_payload(output, returncode=returncode, result_bytes=1000) == (
        None,
        error,
    )


@pytest.mark.parametrize("payload", ["[]", "{}", "{truncated", '{"error": "bad"}'])
def test_unreadable_completion_is_an_error_even_after_a_checkpoint(tmp_path, payload):
    output = tmp_path / "output.json"
    output.write_text(payload)
    result, error = run_worker.read_child_payload(output, returncode=0, result_bytes=1000)
    assert result is None
    assert error["code"] == "child_protocol_error"


def test_no_final_envelope_never_means_success(tmp_path):
    result, error = run_worker.read_child_payload(
        tmp_path / "missing.json", returncode=0, result_bytes=1000
    )
    assert result is None
    assert error["code"] == "worker_process_stopped"


def test_nonzero_exit_with_result_retains_data_but_does_not_claim_success(tmp_path):
    output = tmp_path / "output.json"
    saved = sample_result(reason="duration_reached", completed=True)
    output.write_text(json.dumps({"result": saved}))
    result, error = run_worker.read_child_payload(output, returncode=2, result_bytes=100_000)
    assert result == saved
    assert error["code"] == "worker_process_stopped"


@pytest.mark.parametrize("completion", ["model_error", "missing", "unreadable"])
def test_actual_worker_retains_checkpoint_and_reports_child_failure(
    signed_in, monkeypatch, completion
):
    client = signed_in
    case = client.get("/api/v1/presets/baja-launch-baseline").json()["simulation_case"]
    case["scenario"]["time_span_s"] = [0.0, 1.0]
    queued = client.post(
        "/api/v1/runs", json={"request_key": str(uuid4()), "simulation_case": case}
    )
    assert queued.status_code == 202, queued.text
    factory, settings = client.app.state.database_session_factory, client.app.state.settings
    with factory.begin() as session:
        run = jobs.claim(session, settings)
    real_popen = run_worker.subprocess.Popen
    previous = sample_result()

    def bounded_child(argv, **kwargs):
        # Keep the real worker process supervision and DB code; substitute only
        # the expensive computation with a controlled child protocol response.
        script = (
            "import json, sys; from pathlib import Path; "
            "output = Path(sys.argv[1]); "
            "output.with_name('checkpoint.json').write_text(sys.argv[2]); "
        )
        if completion == "model_error":
            script += (
                "output.write_text(json.dumps({'error': "
                "{'code': 'mechanism_contact_unsupported', "
                "'message': 'Contact model limit.', "
                "'details': {'phase': 'simulation'}}})); sys.exit(1)"
            )
        elif completion == "unreadable":
            script += "output.write_text('{truncated')"
        return real_popen([sys.executable, "-c", script, argv[-1], json.dumps(previous)], **kwargs)

    monkeypatch.setattr(run_worker.subprocess, "Popen", bounded_child)
    run_worker.execute(factory, settings, run)
    status = client.get(f"/api/v1/runs/{run.id}").json()
    assert status["status"] == "failed"
    assert status["outcome"]["partial"] is True
    assert status["outcome"]["reached_time_s"] == 0.5
    assert status["outcome"]["category"] == (
        "model_limit" if completion == "model_error" else "service_error"
    )
    preview = client.get(f"/api/v1/runs/{run.id}/preview")
    assert preview.status_code == 200
    assert preview.json()["preview"]["original_row_count"] == 3
