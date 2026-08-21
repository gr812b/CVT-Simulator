"""Regression tests for always-engaged (zero-width deadzone) CVTs."""

from __future__ import annotations

import numpy as np
import pytest

from cinder.execution.hybrid.cvt_operating_limits import CVTShiftOperatingLimits
from cinder.execution.hybrid.cvt_regime import (
    CVTEngagementState,
    CVTShiftConstraint,
)
from cinder.execution.hybrid.cvt_regime_events import (
    CVTRegimeEvent,
    build_low_ratio_seat_events,
)
from cinder.execution.hybrid import cvt_regime_switching
from cinder.model.cvt.contact import ContactRegime
from cinder.model.system import CVTState


def test_zero_width_deadzone_is_a_valid_always_engaged_topology() -> None:
    limits = CVTShiftOperatingLimits(
        lower_stop_shift=0.0,
        engagement_shift=0.0,
        upper_stop_shift=0.02,
    )

    assert not limits.has_deadzone
    assert not limits.is_in_deadzone(0.0)
    assert limits.is_engaged(0.0)
    assert limits.is_engaged(0.01)


def test_positive_width_deadzone_behavior_is_unchanged() -> None:
    limits = CVTShiftOperatingLimits(
        lower_stop_shift=0.0,
        engagement_shift=0.002,
        upper_stop_shift=0.02,
    )

    assert limits.has_deadzone
    assert limits.is_in_deadzone(0.0)
    assert limits.is_in_deadzone(0.001)
    assert not limits.is_in_deadzone(0.002)
    assert limits.is_engaged(0.002)


def test_invalid_operating_limit_order_is_still_rejected() -> None:
    with pytest.raises(ValueError):
        CVTShiftOperatingLimits(
            lower_stop_shift=0.001,
            engagement_shift=0.0,
            upper_stop_shift=0.02,
        )
    with pytest.raises(ValueError):
        CVTShiftOperatingLimits(
            lower_stop_shift=0.0,
            engagement_shift=0.02,
            upper_stop_shift=0.02,
        )


def test_zero_width_low_ratio_seat_omits_disengagement_event() -> None:
    vector = np.zeros(5, dtype=float)
    events = build_low_ratio_seat_events(
        primary_clamping_force=lambda _time, _vector: -1.0,
        closing_reaction=lambda _time, _vector: 1.0,
        include_primary_clamp_loss=False,
    )

    assert tuple(event.name for event in events) == (
        CVTRegimeEvent.LOW_RATIO_SEAT_RELEASE.value,
    )
    assert events[0].function(0.0, vector) == pytest.approx(1.0)


def test_positive_width_low_ratio_seat_retains_disengagement_event() -> None:
    events = build_low_ratio_seat_events(
        primary_clamping_force=lambda _time, _vector: 1.0,
        closing_reaction=lambda _time, _vector: 1.0,
    )

    assert tuple(event.name for event in events) == (
        CVTRegimeEvent.PRIMARY_CLAMP_LOST.value,
        CVTRegimeEvent.LOW_RATIO_SEAT_RELEASE.value,
    )


def test_shared_lower_boundary_classifies_as_engaged_low_ratio_seat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contact = ContactRegime.stick_stick()
    monkeypatch.setattr(
        cvt_regime_switching,
        "resolve_initial_engaged_regime",
        lambda **_kwargs: contact,
    )
    limits = CVTShiftOperatingLimits(
        lower_stop_shift=0.0,
        engagement_shift=0.0,
        upper_stop_shift=0.02,
    )
    state = CVTState(
        primary_angular_speed=10.0,
        secondary_angular_speed=5.0,
        belt_speed=0.5,
        shift_position=0.0,
        shift_speed=0.0,
    )

    regime = cvt_regime_switching.classify_initial_cvt_regime(
        evaluator=object(),
        time=0.0,
        state=state,
        limits=limits,
        switching_settings=object(),
    )

    assert regime.engagement is CVTEngagementState.ENGAGED
    assert regime.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT
    assert regime.contact_regime == contact
