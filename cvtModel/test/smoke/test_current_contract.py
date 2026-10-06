from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from cinder.contracts import (
    decode_simulation_case_document,
    validate_simulation_case_document,
)

EXAMPLE_CASE = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "baja_baseline_simulation_case.json"
)


def test_bundled_v1_case_decodes_and_evaluates_current_composed_system() -> None:
    document = json.loads(EXAMPLE_CASE.read_text(encoding="utf-8"))

    assert document["schema_version"] == 1
    assert document["document_type"] == "cinder_composed_simulation_case"

    validation = validate_simulation_case_document(document)
    assert validation.is_valid, [finding.message for finding in validation.findings]

    decoded = decode_simulation_case_document(document)
    derivative = decoded.system.rhs(
        0.0,
        decoded.initial_state,
        decoded.initial_mode,
    )

    assert derivative.shape == decoded.initial_state.shape
    assert derivative.shape == (6,)
    assert np.all(np.isfinite(derivative))
