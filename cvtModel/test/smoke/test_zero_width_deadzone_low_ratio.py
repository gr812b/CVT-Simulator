from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from cinder.execution.hybrid import cvt_regime_switching as switching
from cinder.execution.hybrid.cvt_impact import CVTVelocityTopology
from cinder.execution.hybrid.cvt_operating_limits import CVTShiftOperatingLimits
from cinder.execution.hybrid.cvt_regime import CVTEngagementState, CVTShiftConstraint
from cinder.model.cvt.contact import ContactRegime


def _projection(*, successor: np.ndarray, dissipated_energy: float):
    return SimpleNamespace(
        successor_state=np.array(successor, dtype=float, copy=True),
        pre_kinetic_energy=1.0,
        dissipated_energy=float(dissipated_energy),
        metadata=lambda: {},
    )


def test_zero_width_low_ratio_arrival_stays_engaged(monkeypatch) -> None:
    limits = CVTShiftOperatingLimits(0.0, 0.0, 0.02)
    assert not limits.has_deadzone

    contact = ContactRegime.stick_stick()
    vector = np.asarray([10.0, 5.0, 0.5, 0.0, -0.25], dtype=float)
    projected = np.asarray([10.0, 5.0, 0.5, 0.0, 0.0], dtype=float)
    topology_calls: list[CVTVelocityTopology] = []

    def fake_project(**kwargs):
        topology_calls.append(kwargs["to_topology"])
        if kwargs["to_topology"] is CVTVelocityTopology.DEADZONE:
            raise AssertionError("zero-width arrival attempted to enter deadzone")
        return _projection(successor=projected, dissipated_energy=0.1)

    monkeypatch.setattr(switching, "project_cvt_velocity_topology", fake_project)
    monkeypatch.setattr(
        switching,
        "_resolve_contact_at_constraint",
        lambda **_kwargs: (contact, None),
    )
    monkeypatch.setattr(
        switching,
        "primary_contact_separation_at_engagement",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("zero-width arrival evaluated deadzone separation")
        ),
    )

    evaluator = SimpleNamespace(
        model=object(),
        evaluate_vector=lambda **_kwargs: SimpleNamespace(
            low_ratio_seat_reaction=1.0,
            normal_primary=2.0,
        ),
    )

    transition = switching._resolve_low_ratio_seat_arrival(
        time=0.5,
        vector=vector,
        old_contact_regime=contact,
        contact_events=(),
        limits=limits,
        evaluator=evaluator,
        switching_settings=SimpleNamespace(),
        shaft_boundaries=None,
    )

    assert topology_calls == [CVTVelocityTopology.ENGAGED]
    assert transition.next_mode is not None
    assert transition.next_mode.engagement is CVTEngagementState.ENGAGED
    assert transition.next_mode.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT
    assert transition.reason == (
        "zero_width_deadzone_low_ratio_secondary_stop_seated_after_impact"
    )


def test_zero_width_low_ratio_release_stays_engaged(monkeypatch) -> None:
    limits = CVTShiftOperatingLimits(0.0, 0.0, 0.02)
    contact = ContactRegime.stick_stick()
    vector = np.asarray([10.0, 5.0, 0.5, 0.0, 0.0], dtype=float)

    monkeypatch.setattr(
        switching,
        "primary_contact_separation_at_engagement",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("zero-width release evaluated deadzone separation")
        ),
    )
    monkeypatch.setattr(
        switching,
        "_resolve_contact_at_constraint",
        lambda **_kwargs: (contact, None),
    )

    transition = switching._resolve_low_ratio_seat_release(
        time=0.5,
        vector=vector,
        old_contact_regime=contact,
        contact_events=(),
        limits=limits,
        evaluator=SimpleNamespace(),
        switching_settings=SimpleNamespace(),
        shaft_boundaries=None,
    )

    assert transition.next_mode is not None
    assert transition.next_mode.engagement is CVTEngagementState.ENGAGED
    assert transition.next_mode.shift_constraint is CVTShiftConstraint.FREE
    assert transition.reason == "low_ratio_seat_released_by_tensile_reaction"
    assert transition.metadata == {"release": "low_ratio_seat_reaction_crossed_zero"}


def test_positive_width_finite_arrival_can_still_enter_deadzone(monkeypatch) -> None:
    limits = CVTShiftOperatingLimits(0.0, 0.002, 0.02)
    assert limits.has_deadzone

    contact = ContactRegime.stick_stick()
    vector = np.asarray([10.0, 5.0, 0.5, 0.002, -0.25], dtype=float)
    projected = np.asarray([10.0, 5.0, 0.5, 0.002, 0.0], dtype=float)
    topology_calls: list[CVTVelocityTopology] = []

    def fake_project(**kwargs):
        topology = kwargs["to_topology"]
        topology_calls.append(topology)
        return _projection(successor=projected, dissipated_energy=0.1)

    monkeypatch.setattr(switching, "project_cvt_velocity_topology", fake_project)

    transition = switching._resolve_low_ratio_seat_arrival(
        time=0.5,
        vector=vector,
        old_contact_regime=contact,
        contact_events=(),
        limits=limits,
        evaluator=SimpleNamespace(model=object()),
        switching_settings=SimpleNamespace(),
        shaft_boundaries=None,
    )

    assert topology_calls == [
        CVTVelocityTopology.ENGAGED,
        CVTVelocityTopology.DEADZONE,
    ]
    assert transition.next_mode is not None
    assert transition.next_mode.engagement is CVTEngagementState.DEADZONE
    assert transition.next_mode.shift_constraint is CVTShiftConstraint.FREE


def test_zero_width_primary_disengagement_is_rejected_before_deadzone_mechanics() -> None:
    limits = CVTShiftOperatingLimits(0.0, 0.0, 0.02)
    with pytest.raises(RuntimeError, match="zero-width deadzone"):
        switching._resolve_low_ratio_seat_disengagement(
            time=0.5,
            vector=np.zeros(5, dtype=float),
            old_contact_regime=ContactRegime.stick_stick(),
            limits=limits,
            evaluator=SimpleNamespace(),
            switching_settings=SimpleNamespace(),
            shaft_boundaries=None,
        )
