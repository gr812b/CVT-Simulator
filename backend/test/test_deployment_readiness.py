"""Release gating keeps queued runs untouched while API images are being replaced."""

from __future__ import annotations

import io
import json
from http.client import IncompleteRead
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from app.core import deployment
from app.core.settings import Settings
from app.main import create_app
from app.scripts import wait_for_api

REVISION = "a" * 40
HEALTH = {"status": "ok", "api_version": "v1"}


@pytest.fixture
def revision_file(monkeypatch, tmp_path):
    path = tmp_path / "image-revision.txt"
    path.write_text(REVISION + "\n", encoding="utf-8")
    monkeypatch.setattr(deployment, "IMAGE_REVISION_FILE", path)
    return path


def health_response(body=HEALTH, *, revision=REVISION, status=200):
    response = io.BytesIO(body if isinstance(body, bytes) else json.dumps(body).encode())
    response.status = status
    response.headers = {}
    if revision is not None:
        response.headers[deployment.IMAGE_REVISION_HEADER] = revision
    return response


def test_api_health_reports_baked_revision_without_changing_body(revision_file, monkeypatch):
    monkeypatch.setenv("CVT_IMAGE_REVISION", "stale-container-environment")
    app = create_app(Settings(database_url="sqlite://"))
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == HEALTH
        assert response.headers[deployment.IMAGE_REVISION_HEADER] == REVISION
        assert deployment.image_revision() == REVISION
    finally:
        app.state.database_engine.dispose()


def test_local_health_remains_available_without_image_revision(revision_file):
    revision_file.unlink()
    app = create_app(Settings(database_url="sqlite://"))
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
        assert response.json() == HEALTH
        assert deployment.IMAGE_REVISION_HEADER not in response.headers
    finally:
        app.state.database_engine.dispose()


@pytest.mark.parametrize("value", [None, "", "unknown", "development", "unversioned"])
def test_readiness_cannot_match_an_unversioned_worker(revision_file, monkeypatch, value):
    if value is None:
        revision_file.unlink()
    else:
        revision_file.write_text(value, encoding="utf-8")
    monkeypatch.setenv("CVT_IMAGE_REVISION", REVISION)
    with pytest.raises(ValueError, match="build-arg CVT_IMAGE_REVISION"):
        deployment.ApiReadinessGate("http://cvt-backend:8000")


def test_gate_pauses_again_when_api_disappears_or_moves_to_another_revision(
    revision_file, monkeypatch, caplog
):
    attempts = iter(
        [
            health_response(),
            URLError("unreachable with private connection details"),
            health_response(revision="b" * 40),
            health_response(),
        ]
    )

    def get_health(url, timeout):
        assert url == "http://cvt-backend:8000/api/v1/health"
        assert timeout == 2.0
        response = next(attempts)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(deployment, "urlopen", get_health)
    caplog.set_level("INFO", logger="cinder.deployment")
    gate = deployment.ApiReadinessGate("http://cvt-backend:8000/")
    assert [gate() for _ in range(4)] == [True, False, False, True]
    assert "private connection details" not in caplog.text


@pytest.mark.parametrize(
    "body,revision,status",
    [
        (HEALTH, None, 200),
        (HEALTH, "older-image", 200),
        (HEALTH, REVISION, 201),
        ({"status": "starting", "api_version": "v1"}, REVISION, 200),
        ({"status": "ok", "api_version": "v2"}, REVISION, 200),
        ({"status": "ok"}, REVISION, 200),
        ([], REVISION, 200),
        (None, REVISION, 200),
        (b"not json", REVISION, 200),
        (b"\xff", REVISION, 200),
        (b" " * 4097, REVISION, 200),
    ],
)
def test_gate_rejects_old_unready_and_malformed_api_responses(
    revision_file, monkeypatch, body, revision, status
):
    monkeypatch.setattr(
        deployment,
        "urlopen",
        lambda *_args, **_kwargs: health_response(body, revision=revision, status=status),
    )
    assert not deployment.ApiReadinessGate("http://cvt-backend:8000")()


@pytest.mark.parametrize("failure", [URLError("offline"), TimeoutError(), IncompleteRead(b"")])
def test_gate_retries_network_failures_without_logging_every_poll(
    revision_file, monkeypatch, caplog, failure
):
    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(deployment, "urlopen", fail)
    caplog.set_level("INFO", logger="cinder.deployment")
    gate = deployment.ApiReadinessGate("http://cvt-backend:8000")
    assert not gate()
    assert not gate()
    assert caplog.text.count("Worker intake is paused") == 1


@pytest.mark.parametrize("succeeds", [True, False])
def test_hook_wait_is_bounded_and_allows_delayed_startup(monkeypatch, succeeds):
    clock = [0.0]
    attempts = []

    def sleep(seconds):
        clock[0] += seconds

    def ready():
        attempts.append(clock[0])
        return succeeds and len(attempts) == 3

    monkeypatch.setattr(wait_for_api.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(wait_for_api.time, "sleep", sleep)
    assert wait_for_api.wait_until_ready(ready, timeout_seconds=3.0) is succeeds
    assert attempts == [0.0, 1.0, 2.0]
    assert clock[0] <= 3.0


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf"])
def test_hook_rejects_invalid_timeout(monkeypatch, timeout):
    monkeypatch.setattr("sys.argv", ["wait_for_api", "--timeout", timeout])
    with pytest.raises(SystemExit) as error:
        wait_for_api.main()
    assert error.value.code == 2


def test_hook_reports_a_failed_wait(revision_file, monkeypatch):
    monkeypatch.setattr("sys.argv", ["wait_for_api"])
    monkeypatch.setattr(wait_for_api, "wait_until_ready", lambda *_args, **_kwargs: False)
    with pytest.raises(SystemExit) as error:
        wait_for_api.main()
    assert error.value.code == 1
