"""Account unit preferences are personal, durable and display-only metadata."""

from fastapi.testclient import TestClient

WEB_ORIGIN = "http://localhost:5173"


def _browser(client: TestClient) -> None:
    client.headers.update({"X-Cinder-Client": "web", "Origin": WEB_ORIGIN})


def _login(client: TestClient, email: str) -> dict:
    _browser(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "local-test-password"},
    )
    assert response.status_code == 200, response.text
    identity = response.json()
    client.headers["X-CSRF-Token"] = identity["csrf_token"]
    return identity


def test_unit_preferences_persist_across_sessions_and_stay_user_isolated(api, register):
    first = register(api, email="units-a@example.com", name="Units A")
    assert first["user"]["unit_preferences"]["hardware_length"] == "in"
    chosen = {
        "preset": "imperial",
        "hardware_length": "in",
        "component_mass": "oz",
        "vehicle_length": "ft",
        "vehicle_mass": "lb",
        "course_length": "ft",
        "speed": "mph",
        "output_length": "ft",
        "output_speed": "mph",
    }
    saved = api.patch("/api/v1/auth/unit-preferences", json=chosen)
    assert saved.status_code == 200, saved.text
    assert saved.json()["user"]["unit_preferences"] == chosen

    with TestClient(api.app) as second_device:
        identity = _login(second_device, "units-a@example.com")
        assert identity["user"]["unit_preferences"] == chosen

    with TestClient(api.app) as other:
        _browser(other)
        created = other.post(
            "/api/v1/auth/register",
            json={
                "email": "units-b@example.com",
                "display_name": "Units B",
                "password": "local-test-password",
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["user"]["unit_preferences"]["preset"] == "recommended"
        assert created.json()["user"]["unit_preferences"]["output_speed"] == "km/h"
