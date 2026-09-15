"""HTTP journey for the isolated primary design tool."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def _client() -> TestClient:
    return TestClient(
        create_app(
            Settings(
                preset_directory=ROOT / "presets",
                run_timeout_seconds=30.0,
                run_executor_mode="inline",
                cors_origins=(),
            )
        )
    )


def test_primary_design_concrete_round_trip() -> None:
    client = _client()
    defaults_response = client.get(
        "/api/v1/engineering/fixed-pivot-primary/defaults"
    )
    assert defaults_response.status_code == 200
    defaults = defaults_response.json()

    analysis_response = client.post(
        "/api/v1/engineering/fixed-pivot-primary/concrete/analyze",
        json={
            "architecture": defaults["architecture"],
            "ramp": defaults["ramp"],
            "sample_count": 61,
        },
    )
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()
    assert analysis["validity"]["valid"] is True
    assert len(analysis["geometry"]["axis_values"]) == 61

    response = client.post(
        "/api/v1/engineering/fixed-pivot-primary/concrete/response",
        json={
            "analysis_id": analysis["analysis_id"],
            **defaults["operating"],
        },
    )
    assert response.status_code == 200
    loads = response.json()["loads"]
    assert len(loads["axis_values"]) == 61
    assert "flyweight_total_closing_force_N" in loads["fields"]


def test_primary_design_architecture_workspace_round_trip() -> None:
    client = _client()
    defaults = client.get(
        "/api/v1/engineering/fixed-pivot-primary/defaults"
    ).json()
    response = client.post(
        "/api/v1/engineering/fixed-pivot-primary/architecture/analyze",
        json={
            "architecture": defaults["architecture"],
            "ramp": defaults["ramp"],
            "zones": [],
            "reach_sample_count": 181,
        },
    )
    assert response.status_code == 200
    workspace = response.json()
    assert workspace["validity"]["valid"] is True
    assert len(workspace["reach"]["q_deg"]) == 181
    assert workspace["reach"]["admissible_intervals_deg"] == [[0.0, 90.0]]
    assert workspace["envelopes"]["flyweight_swept"]
    assert workspace["ramp_surface"]["open"]["x_m"]
