"""Real HTTP/database fixtures; each journey owns a disposable SQLite copy."""

from pathlib import Path
from shutil import copyfile

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.database.bootstrap import create_and_seed_database
from app.main import create_app

BACKEND = Path(__file__).resolve().parents[1]
WEB_ORIGIN = "http://localhost:5173"


@pytest.fixture(scope="session")
def seeded_database(tmp_path_factory):
    path = tmp_path_factory.mktemp("api-seed") / "seed.sqlite3"
    create_and_seed_database(
        Settings(database_url=f"sqlite:///{path}", preset_directory=BACKEND / "presets")
    )
    return path


@pytest.fixture
def api(seeded_database, tmp_path):
    path = tmp_path / "journey.sqlite3"
    copyfile(seeded_database, path)
    app = create_app(
        Settings(
            database_url=f"sqlite:///{path}",
            preset_directory=BACKEND / "presets",
            run_timeout_seconds=30,
            worker_poll_seconds=0.01,
            web_url=WEB_ORIGIN,
            cors_origins=(WEB_ORIGIN,),
            environment="development",
            mail_mode="outbox",
            mail_outbox=tmp_path / "mail",
        )
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.state.database_engine.dispose()


@pytest.fixture
def register():
    def register_account(client, *, email="driver@example.com", name="Driver"):
        client.headers.update({"X-Cinder-Client": "web", "Origin": WEB_ORIGIN})
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "display_name": name, "password": "local-test-password"},
        )
        assert response.status_code == 201, response.text
        identity = response.json()
        client.headers["X-CSRF-Token"] = identity["csrf_token"]
        return identity

    return register_account


@pytest.fixture
def signed_in(api, register):
    register(api)
    return api
