from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from cinder.contracts import (
    decode_assembly_document,
    decode_simulation_case_document,
    encode_assembly_document,
    validate_simulation_case_document,
)
from cinder.model.cvt.actuation import HelicalTorqueReactionForce

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


@pytest.mark.parametrize("topology", [None, "slotted", "unilateral"])
def test_helix_contact_topology_is_explicit_after_document_round_trip(topology) -> None:
    document = json.loads(EXAMPLE_CASE.read_text(encoding="utf-8"))
    component = next(
        value
        for value in document["assembly"]["pulleys"]["secondary"]["components"]
        if value["kind"] == "helical_torque_reaction"
    )
    if topology is None:
        component.pop("contact_topology", None)
    else:
        component["contact_topology"] = topology
    expected = "slotted" if topology is None else topology

    decoded = decode_assembly_document(document["assembly"])
    encoded = encode_assembly_document(decoded)
    serialized = next(
        value
        for value in encoded["pulleys"]["secondary"]["components"]
        if value["kind"] == "helical_torque_reaction"
    )
    assert serialized["contact_topology"] == expected
    round_trip = decode_assembly_document(encoded)
    law = next(
        value
        for value in round_trip.pulleys.secondary.actuator.force_laws
        if isinstance(value, HelicalTorqueReactionForce)
    )
    assert law.spec.contact_topology == expected


@pytest.mark.parametrize("topology", ["unsupported", None, 1, True, {}])
def test_helix_document_rejects_invalid_contact_topology(topology) -> None:
    document = json.loads(EXAMPLE_CASE.read_text(encoding="utf-8"))
    component = next(
        value
        for value in document["assembly"]["pulleys"]["secondary"]["components"]
        if value["kind"] == "helical_torque_reaction"
    )
    component["contact_topology"] = topology
    with pytest.raises(ValueError, match="contact_topology"):
        decode_assembly_document(document["assembly"])
