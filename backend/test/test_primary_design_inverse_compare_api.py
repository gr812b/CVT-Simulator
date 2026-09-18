from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.engineering.fixed_pivot_primary.service import FixedPivotPrimaryDesignService
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


def test_inverse_design_api_wires_force_target_points(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_inverse(self, **kwargs):
        del self
        captured.update(kwargs)
        points = kwargs["target_points"]
        return {
            "target": {
                "shaft_speed_rad_s": kwargs["shaft_speed_rad_s"],
                "shift_m": [point.shift_m for point in points],
                "force_N": [point.force_N for point in points],
                "input_points": [
                    {"shift_m": point.shift_m, "force_N": point.force_N} for point in points
                ],
            },
            "solutions": [],
            "diagnostics": [],
            "summary": {"method": "api-wiring-test"},
        }

    monkeypatch.setattr(FixedPivotPrimaryDesignService, "inverse_design_force_curve", fake_inverse)
    client = _client()
    defaults = client.get("/api/v1/engineering/fixed-pivot-primary/defaults").json()
    response = client.post(
        "/api/v1/engineering/fixed-pivot-primary/inverse-design",
        json={
            "architecture": defaults["architecture"],
            "zones": [],
            "target_points": [
                {"shift_m": 0.0, "force_N": 3200.0},
                {"shift_m": defaults["architecture"]["required_travel_m"], "force_N": 4700.0},
            ],
            "shaft_speed_rad_s": defaults["operating"]["shaft_speed_rad_s"],
            "max_tip_mass_per_flyweight_kg": 0.35,
            "solution_count": 4,
            "sample_count": 101,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["method"] == "api-wiring-test"
    assert len(captured["target_points"]) == 2
    assert captured["max_tip_mass_per_flyweight_kg"] == 0.35


def test_compare_target_api_wires_relative_force_shape(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_compare(self, **kwargs):
        del self
        captured.update(kwargs)
        points = kwargs["target_points"]
        return {
            "definition": {"mass_scale_agnostic": True, "method": "continuous-inverse"},
            "target": {
                "shift_fraction": [point[0] for point in points],
                "normalized_shape": [point[1] / 100.0 for point in points],
                "input_points": [
                    {"shift_fraction": point[0], "relative_force": point[1]} for point in points
                ],
            },
            "architecture_a": None,
            "architecture_b": None,
            "summary": {"method": "api-wiring-test"},
        }

    monkeypatch.setattr(
        FixedPivotPrimaryDesignService, "compare_path_domains_to_target", fake_compare
    )
    client = _client()
    response = client.post(
        "/api/v1/engineering/fixed-pivot-primary/architecture/path-domain/compare-target",
        json={
            "domain_id_a": "domain-a",
            "domain_id_b": "domain-b",
            "target_points": [
                {"shift_fraction": 0.0, "relative_force": 178.0},
                {"shift_fraction": 0.5, "relative_force": 95.0},
                {"shift_fraction": 1.0, "relative_force": 16.0},
            ],
            "mass_mix_count": 7,
            "sample_count": 81,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["definition"]["method"] == "continuous-inverse"
    assert captured["target_points"] == [(0.0, 178.0), (0.5, 95.0), (1.0, 16.0)]
    assert captured["mass_mix_count"] == 7
    assert captured["sample_count"] == 81
