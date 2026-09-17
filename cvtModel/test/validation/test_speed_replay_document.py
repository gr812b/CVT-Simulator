from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)
from cinder.contracts.simulation_document import (
    _decode_shaft_boundary,
    _encode_shaft_boundary,
)
from cinder.model.boundaries.shaft import SpeedReplayShaftBoundary
from cinder.model.reference import PiecewiseLinearReference, TimeValuePoint

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "examples" / "baja_baseline_simulation_case.json"


def _reference(values: tuple[tuple[float, float], ...]) -> PiecewiseLinearReference:
    return PiecewiseLinearReference(
        tuple(TimeValuePoint(time, value) for time, value in values)
    )


def test_speed_replay_document_roundtrip() -> None:
    boundary = SpeedReplayShaftBoundary(
        speed_reference=_reference(((0.0, 10.0), (1.0, 20.0))),
        tracking_gain=375.0,
    )

    encoded = _encode_shaft_boundary(boundary)
    assert encoded == {
        "kind": "speed_replay_shaft",
        "speed_reference": {
            "points": [
                {"time_s": 0.0, "value": 10.0},
                {"time_s": 1.0, "value": 20.0},
            ]
        },
        "tracking_gain_Nm_s_per_rad": 375.0,
    }

    decoded = _decode_shaft_boundary(encoded)
    assert isinstance(decoded, SpeedReplayShaftBoundary)
    assert decoded.speed_reference.value_at(0.5) == 15.0
    assert decoded.tracking_gain == 375.0


def test_minimal_speed_replay_document_uses_audited_default_gain() -> None:
    decoded = _decode_shaft_boundary(
        {
            "kind": "speed_replay_shaft",
            "speed_reference": {
                "points": [
                    {"time_s": 0.0, "value": 180.0},
                    {"time_s": 1.0, "value": 240.0},
                ]
            },
        }
    )

    assert isinstance(decoded, SpeedReplayShaftBoundary)
    assert decoded.tracking_gain == 400.0


def test_public_simulation_document_accepts_speed_replay_boundary() -> None:
    document = deepcopy(json.loads(BASELINE.read_text(encoding="utf-8")))
    omega0 = float(
        document["scenario"]["initial_cvt_state"]["primary_angular_speed_rad_per_s"]
    )
    document["shaft_boundaries"]["primary"] = {
        "kind": "speed_replay_shaft",
        "speed_reference": {
            "points": [
                {"time_s": 0.0, "value": omega0},
                {"time_s": 0.5, "value": omega0 + 20.0},
            ]
        },
    }

    validation = validate_simulation_case_document(document)
    assert validation.is_valid, validation.findings

    decoded = decode_simulation_case_document(document)
    assert isinstance(decoded.system.primary_boundary, SpeedReplayShaftBoundary)
    assert decoded.system.primary_boundary.tracking_gain == 400.0
