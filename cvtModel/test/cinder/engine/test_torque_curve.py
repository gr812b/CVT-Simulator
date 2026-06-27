from __future__ import annotations

import pytest

from cinder.engine import (
    EngineTorquePoint,
    FullThrottleTorqueCurve,
    TorqueCurveSpec,
)


def _curve() -> FullThrottleTorqueCurve:
    return FullThrottleTorqueCurve(
        TorqueCurveSpec(
            points=(
                EngineTorquePoint(angular_speed=100.0, torque=0.0),
                EngineTorquePoint(angular_speed=180.0, torque=24.0),
                EngineTorquePoint(angular_speed=240.0, torque=25.0),
                EngineTorquePoint(angular_speed=360.0, torque=18.0),
                EngineTorquePoint(angular_speed=400.0, torque=0.0),
            ),
            low_speed_braking_torque=-4.0,
            low_speed_braking_peak_speed=70.0,
            high_speed_braking_torque=-5.0,
            high_speed_braking_transition_width=40.0,
        )
    )


def test_curve_reproduces_measured_knots() -> None:
    curve = _curve()

    assert curve.evaluate(180.0) == pytest.approx(24.0)
    assert curve.evaluate(240.0) == pytest.approx(25.0)
    assert curve.evaluate(360.0) == pytest.approx(18.0)


def test_zero_torque_points_define_running_limits() -> None:
    curve = _curve()

    assert curve.minimum_speed == pytest.approx(100.0)
    assert curve.maximum_speed == pytest.approx(400.0)
    assert curve.evaluate(curve.minimum_speed) == pytest.approx(0.0)
    assert curve.evaluate(curve.maximum_speed) == pytest.approx(0.0)


def test_low_speed_tail_brakes_but_is_zero_at_rest() -> None:
    curve = _curve()

    assert curve.evaluate(0.0) == pytest.approx(0.0)
    assert curve.evaluate(70.0) == pytest.approx(-4.0)
    assert curve.evaluate(90.0) < 0.0


def test_high_speed_tail_is_negative_and_bounded() -> None:
    curve = _curve()

    assert curve.evaluate(420.0) < 0.0
    assert curve.evaluate(440.0) == pytest.approx(-5.0)
    assert curve.evaluate(600.0) == pytest.approx(-5.0)


def test_pchip_stays_between_neighboring_monotonic_knots() -> None:
    curve = _curve()

    torque = curve.evaluate(210.0)

    assert 24.0 <= torque <= 25.0
