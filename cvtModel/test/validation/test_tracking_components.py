from __future__ import annotations

from math import isclose

from cinder.model.boundaries.shaft import ShaftBoundaryContext, SpeedTrackingShaftBoundary
from cinder.model.cvt.actuation import AxialMotionTrackingForce, AxialMotionTrackingForceSpec, PulleyActuationContext
from cinder.model.reference import PiecewiseLinearReference, TimeValuePoint
from cinder.model.system import CVTState


def _reference(*pairs: tuple[float, float]) -> PiecewiseLinearReference:
    return PiecewiseLinearReference(tuple(TimeValuePoint(t, v) for t, v in pairs))


def test_piecewise_reference_interpolates_and_clamps() -> None:
    reference = _reference((0.0, 10.0), (2.0, 14.0), (3.0, 11.0))
    assert reference.value_at(-1.0) == 10.0
    assert reference.value_at(1.0) == 12.0
    assert reference.value_at(4.0) == 11.0
    assert reference.slope_at(1.0) == 2.0
    assert reference.slope_at(2.5) == -3.0
    assert reference.slope_at(4.0) == 0.0


def test_speed_tracking_boundary_applies_torque_and_saturates() -> None:
    boundary = SpeedTrackingShaftBoundary(
        speed_reference=_reference((0.0, 100.0), (1.0, 110.0)),
        proportional_gain=2.0,
        torque_limit=5.0,
        equivalent_inertia=0.2,
        feedforward_inertia=0.1,
    )
    state = CVTState(
        primary_angular_speed=90.0,
        secondary_angular_speed=0.0,
        belt_speed=0.0,
        shift_position=0.0,
        shift_speed=0.0,
    )
    result = boundary.evaluate(ShaftBoundaryContext(time=0.5, cvt=state, shaft="primary"))
    assert result.external_torque == 5.0
    assert result.equivalent_inertia == 0.2
    assert result.metadata["actuator_saturated"] is True


def test_axial_tracking_force_tracks_local_position_and_speed() -> None:
    law = AxialMotionTrackingForce(
        AxialMotionTrackingForceSpec(
            position_reference=_reference((0.0, 0.01), (1.0, 0.02)),
            speed_reference=_reference((0.0, 0.01), (1.0, 0.01)),
            position_gain=1000.0,
            speed_gain=100.0,
            force_limit=100.0,
        )
    )
    context = PulleyActuationContext(
        time=0.5,
        axial_position=0.012,
        axial_speed=0.005,
        shaft_speed=0.0,
    )
    relation = law.evaluate(context)
    expected = 1000.0 * (0.015 - 0.012) + 100.0 * (0.01 - 0.005)
    assert isclose(relation.bias, expected)
