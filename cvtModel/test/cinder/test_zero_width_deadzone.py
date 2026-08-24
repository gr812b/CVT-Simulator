from __future__ import annotations

from types import SimpleNamespace
import numpy as np
import pytest

from cinder.execution.hybrid.cvt_operating_limits import CVTShiftOperatingLimits
from cinder.execution.hybrid.cvt_regime import CVTEngagementState, CVTShiftConstraint
from cinder.execution.hybrid.cvt_regime_events import (
    CVTRegimeEvent,
    build_low_ratio_seat_events,
)
from cinder.execution.hybrid import cvt_regime_switching
from cinder.model.cvt.contact import ContactRegime
from cinder.model.system import CVTState


def test_zero_width_deadzone_is_valid_always_engaged_topology() -> None:
    limits = CVTShiftOperatingLimits(0.0, 0.0, 0.02)
    assert not limits.has_deadzone
    assert not limits.is_in_deadzone(0.0)
    assert limits.is_engaged(0.0)


def test_positive_width_deadzone_behavior_unchanged() -> None:
    limits = CVTShiftOperatingLimits(0.0, 0.002, 0.02)
    assert limits.has_deadzone
    assert limits.is_in_deadzone(0.001)
    assert not limits.is_in_deadzone(0.002)


def test_invalid_limit_order_rejected() -> None:
    with pytest.raises(ValueError):
        CVTShiftOperatingLimits(0.001, 0.0, 0.02)
    with pytest.raises(ValueError):
        CVTShiftOperatingLimits(0.0, 0.02, 0.02)


def test_zero_width_low_ratio_seat_omits_disengagement_event() -> None:
    vector = np.zeros(5, dtype=float)
    events = build_low_ratio_seat_events(
        primary_separation=lambda _time, _vector: -1.0,
        closing_reaction=lambda _time, _vector: 1.0,
        include_primary_separation=False,
    )
    assert tuple(event.name for event in events) == (
        CVTRegimeEvent.LOW_RATIO_SEAT_RELEASE.value,
    )
    assert events[0].function(0.0, vector) == pytest.approx(1.0)


class _Classifier:
    def classify_initial_regime_at_time(self, **_kwargs):
        return ContactRegime.stick_stick()


def test_shared_lower_boundary_classifies_as_engaged_low_ratio_seat() -> None:
    limits = CVTShiftOperatingLimits(0.0, 0.0, 0.02)
    state = CVTState(
        primary_angular_speed=10.0,
        secondary_angular_speed=5.0,
        belt_speed=0.5,
        shift_position=0.0,
        shift_speed=0.0,
    )
    regime = cvt_regime_switching.classify_initial_cvt_regime(
        evaluator=_Classifier(),
        time=0.0,
        state=state,
        limits=limits,
        switching_settings=SimpleNamespace(),
    )
    assert regime.engagement is CVTEngagementState.ENGAGED
    assert regime.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT
