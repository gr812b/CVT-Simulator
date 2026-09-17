from __future__ import annotations

from math import isclose

import pytest

from cinder.model.boundaries.shaft import ShaftBoundaryContext, SpeedReplayShaftBoundary
from cinder.model.reference import PiecewiseLinearReference, TimeValuePoint
from cinder.model.system import CVTState


def _reference(*pairs: tuple[float, float]) -> PiecewiseLinearReference:
    return PiecewiseLinearReference(
        tuple(TimeValuePoint(time, value) for time, value in pairs)
    )


def _state(*, primary: float = 90.0, secondary: float = 80.0) -> CVTState:
    return CVTState(
        primary_angular_speed=primary,
        secondary_angular_speed=secondary,
        belt_speed=0.0,
        shift_position=0.0,
        shift_speed=0.0,
    )


def test_piecewise_reference_interpolates_and_clamps() -> None:
    reference = _reference((0.0, 10.0), (2.0, 14.0), (3.0, 11.0))

    assert reference.value_at(-1.0) == 10.0
    assert reference.value_at(1.0) == 12.0
    assert reference.value_at(4.0) == 11.0
    assert reference.slope_at(1.0) == 2.0
    assert reference.slope_at(2.5) == -3.0


def test_piecewise_reference_requires_strictly_increasing_times() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        _reference((0.0, 10.0), (0.0, 12.0))


def test_speed_replay_returns_unbounded_proportional_torque() -> None:
    boundary = SpeedReplayShaftBoundary(
        speed_reference=_reference((0.0, 100.0), (1.0, 100.0)),
        tracking_gain=20.0,
    )

    result = boundary.evaluate(
        ShaftBoundaryContext(
            time=0.5,
            cvt=_state(primary=90.0),
            shaft="primary",
        )
    )

    assert result.external_torque == 200.0
    assert result.equivalent_inertia == 0.0
    assert result.metadata["speed_replay_target_rad_per_s"] == 100.0
    assert result.metadata["speed_replay_error_rad_per_s"] == 10.0
    assert result.metadata["speed_replay_torque_Nm"] == 200.0


def test_speed_replay_changes_torque_sign_across_target() -> None:
    boundary = SpeedReplayShaftBoundary(
        speed_reference=_reference((0.0, 100.0), (1.0, 100.0)),
        tracking_gain=10.0,
    )

    below = boundary.evaluate(
        ShaftBoundaryContext(
            time=0.5,
            cvt=_state(primary=95.0),
            shaft="primary",
        )
    )
    above = boundary.evaluate(
        ShaftBoundaryContext(
            time=0.5,
            cvt=_state(primary=105.0),
            shaft="primary",
        )
    )

    assert below.external_torque == 50.0
    assert above.external_torque == -50.0


def test_speed_replay_is_generic_to_either_shaft() -> None:
    boundary = SpeedReplayShaftBoundary(
        speed_reference=_reference((0.0, 100.0), (1.0, 100.0)),
        tracking_gain=5.0,
    )
    state = _state(primary=90.0, secondary=80.0)

    primary = boundary.evaluate(
        ShaftBoundaryContext(time=0.5, cvt=state, shaft="primary")
    )
    secondary = boundary.evaluate(
        ShaftBoundaryContext(time=0.5, cvt=state, shaft="secondary")
    )

    assert primary.external_torque == 50.0
    assert secondary.external_torque == 100.0


def test_default_gain_is_the_audited_replay_gain() -> None:
    boundary = SpeedReplayShaftBoundary(
        speed_reference=_reference((0.0, 100.0), (1.0, 100.0))
    )

    assert isclose(
        boundary.tracking_gain,
        400.0,
    )
    assert isclose(
        boundary.tracking_gain,
        SpeedReplayShaftBoundary.DEFAULT_TRACKING_GAIN_NM_S_PER_RAD,
    )


@pytest.mark.parametrize("gain", [0.0, -1.0, float("inf"), float("nan")])
def test_speed_replay_rejects_invalid_gain(gain: float) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        SpeedReplayShaftBoundary(
            speed_reference=_reference((0.0, 100.0), (1.0, 100.0)),
            tracking_gain=gain,
        )
