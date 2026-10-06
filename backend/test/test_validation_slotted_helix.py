from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from cinder.contracts import decode_simulation_case_document
from cinder.model.boundaries import FixedShaftBoundary
from cinder.model.cvt.actuation import (
    FixedPivotFlyweightForce,
    HelicalTorqueReactionForce,
    HelicalTorqueReactionSpec,
)
from cinder.model.cvt.closure import ClosureUnknowns
from cinder.model.system import CVTState

from app.application.cinder_gateway import (
    DEFAULT_EXECUTION_PROFILE,
    VALIDATION_SLOTTED_SECONDARY_HELIX_PROFILE,
    _apply_execution_profile,
)
from app.database.resolver import normalize_preset_case

ROOT = Path(__file__).resolve().parents[1]
PRESET = ROOT / "presets" / "baja-launch-baseline.json"
NATIVE_TOPOLOGY = "contact_topology" in HelicalTorqueReactionSpec.__dataclass_fields__


def _decoded(*, topology=None):
    payload = json.loads(PRESET.read_text(encoding="utf-8"))
    document = normalize_preset_case(payload["simulation_case"])
    if topology is not None:
        for component in document["assembly"]["pulleys"]["secondary"]["components"]:
            if component["kind"] == "helical_torque_reaction":
                component["contact_topology"] = topology
    return decode_simulation_case_document(document)


def _secondary_helix(decoded) -> HelicalTorqueReactionForce:
    laws = [
        law
        for law in decoded.plant.secondary_actuator.force_laws
        if isinstance(law, HelicalTorqueReactionForce)
    ]
    assert len(laws) == 1
    return laws[0]


def _context(decoded, *, primary=False):
    geometry = decoded.plant.geometry
    state = replace(
        CVTState.from_vector(decoded.initial_state[:5]),
        shift_position=(geometry.spec.deadzone_shift + geometry.spec.max_shift) / 2,
    )
    builder = (
        decoded.plant.primary_actuation_context
        if primary
        else decoded.plant.secondary_actuation_context
    )
    return builder(time=0.0, state=state, geometry=geometry.evaluate_engaged(state.shift_position))


def test_default_profile_supports_both_helix_flanks_with_signed_force() -> None:
    decoded = _decoded()
    context = _context(decoded)
    original = _secondary_helix(decoded).evaluate_element(context)
    _apply_execution_profile(decoded, DEFAULT_EXECUTION_PROFILE)
    helix = _secondary_helix(decoded)
    element = helix.evaluate_element(context)
    forces = []
    for torque in (1000.0, -1000.0):
        unknowns = ClosureUnknowns(secondary_torque=torque)
        assert decoded.plant.secondary_actuator.has_compressive_contacts(context, unknowns)
        force = element.closing_force.evaluate(unknowns)
        forces.append(force)
        assert force == pytest.approx(original.closing_force.evaluate(unknowns))
        assert element.shaft_torque.evaluate(unknowns) == pytest.approx(
            original.shaft_torque.evaluate(unknowns)
        )
    assert forces[0] * forces[1] < 0.0


@pytest.mark.parametrize(
    "profile", [DEFAULT_EXECUTION_PROFILE, VALIDATION_SLOTTED_SECONDARY_HELIX_PROFILE]
)
def test_execution_profile_is_idempotent_and_keeps_primary_contact_guard(profile) -> None:
    decoded = _decoded()
    primary = decoded.plant.primary_actuator
    flyweight = next(law for law in primary.force_laws if isinstance(law, FixedPivotFlyweightForce))
    _apply_execution_profile(decoded, profile)
    first = _secondary_helix(decoded)
    _apply_execution_profile(decoded, profile)
    assert _secondary_helix(decoded) is first
    assert decoded.plant.primary_actuator is primary

    context = _context(decoded, primary=True)
    relation = flyweight.evaluate(context)
    gain = relation.gains.shift_acceleration
    assert gain != 0
    unknowns = ClosureUnknowns(shift_acceleration=(-1.0 - relation.bias) / gain)
    assert flyweight.compressive_contact_margin(context=context, unknowns=unknowns) < 0
    assert not primary.has_compressive_contacts(context, unknowns)


def test_validation_and_default_profiles_match_under_reverse_driving_load() -> None:
    derivatives = []
    for profile in (DEFAULT_EXECUTION_PROFILE, VALIDATION_SLOTTED_SECONDARY_HELIX_PROFILE):
        decoded = _decoded()
        _apply_execution_profile(decoded, profile)
        # A controlled reverse-driving shaft load requires the opposite helix
        # flank. This exercises the real RHS guard rather than just its helper.
        decoded.system.secondary_boundary = FixedShaftBoundary(
            external_torque=5000.0,
            equivalent_inertia=0.3,
        )
        derivatives.append(decoded.system.rhs(0.0, decoded.initial_state, decoded.initial_mode))
    assert np.all(np.isfinite(derivatives))
    np.testing.assert_allclose(derivatives[0], derivatives[1], rtol=1e-12, atol=1e-12)


@pytest.mark.skipif(
    not NATIVE_TOPOLOGY, reason="Installed CINDER predates native topology choices."
)
def test_default_profile_preserves_explicit_unilateral_hardware() -> None:
    decoded = _decoded(topology="unilateral")
    original = _secondary_helix(decoded)
    _apply_execution_profile(decoded, DEFAULT_EXECUTION_PROFILE)
    assert _secondary_helix(decoded) is original
    assert original.spec.contact_topology == "unilateral"
    decoded.system.secondary_boundary = FixedShaftBoundary(
        external_torque=5000.0,
        equivalent_inertia=0.3,
    )
    with pytest.raises(
        RuntimeError, match="Unilateral pulley-mechanism contact became inadmissible"
    ):
        decoded.system.rhs(0.0, decoded.initial_state, decoded.initial_mode)


@pytest.mark.skipif(
    not NATIVE_TOPOLOGY, reason="Installed CINDER predates native topology choices."
)
def test_validation_profile_explicitly_overrides_unilateral_hardware() -> None:
    decoded = _decoded(topology="unilateral")
    _apply_execution_profile(decoded, VALIDATION_SLOTTED_SECONDARY_HELIX_PROFILE)
    context = _context(decoded)
    assert decoded.plant.secondary_actuator.has_compressive_contacts(
        context, ClosureUnknowns(secondary_torque=-1000.0)
    )


def test_unknown_execution_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported execution profile"):
        _apply_execution_profile(_decoded(), "unsupported")
