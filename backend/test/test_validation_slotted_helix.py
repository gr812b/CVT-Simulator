from __future__ import annotations

import json
from pathlib import Path

from cinder.contracts import decode_simulation_case_document
from cinder.model.cvt.actuation import HelicalTorqueReactionForce

from app.application.cinder_gateway import (
    DEFAULT_EXECUTION_PROFILE,
    VALIDATION_SLOTTED_SECONDARY_HELIX_PROFILE,
    _apply_execution_profile,
)

ROOT = Path(__file__).resolve().parents[1]
PRESET = ROOT / "presets" / "baja-launch-baseline.json"


def _decoded():
    payload = json.loads(PRESET.read_text(encoding="utf-8"))
    return decode_simulation_case_document(payload["simulation_case"])


def _secondary_helix(decoded) -> HelicalTorqueReactionForce:
    laws = [
        law
        for law in decoded.plant.secondary_actuator.force_laws
        if isinstance(law, HelicalTorqueReactionForce)
    ]
    assert len(laws) == 1
    return laws[0]


def test_default_execution_profile_keeps_unilateral_secondary_helix() -> None:
    decoded = _decoded()
    _apply_execution_profile(decoded, DEFAULT_EXECUTION_PROFILE)

    helix = _secondary_helix(decoded)
    assert callable(getattr(helix, "compressive_contact_margin", None))


def test_validation_profile_uses_slotted_bilateral_secondary_helix() -> None:
    decoded = _decoded()
    _apply_execution_profile(
        decoded,
        VALIDATION_SLOTTED_SECONDARY_HELIX_PROFILE,
    )

    helix = _secondary_helix(decoded)
    assert getattr(helix, "compressive_contact_margin", None) is None
    assert getattr(helix, "has_compressive_contact", None) is None
