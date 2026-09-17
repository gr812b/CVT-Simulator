from __future__ import annotations

from cinder.contracts.document import _decode_force_law, _encode_force_law
from cinder.contracts.simulation_document import _decode_shaft_boundary, _encode_shaft_boundary
from cinder.model.boundaries.shaft import SpeedTrackingShaftBoundary
from cinder.model.cvt.actuation import AxialMotionTrackingForce, AxialMotionTrackingForceSpec
from cinder.model.reference import PiecewiseLinearReference, TimeValuePoint


def _reference(values: tuple[tuple[float, float], ...]) -> PiecewiseLinearReference:
    return PiecewiseLinearReference(tuple(TimeValuePoint(t, value) for t, value in values))


def test_speed_tracking_boundary_document_roundtrip() -> None:
    boundary = SpeedTrackingShaftBoundary(
        speed_reference=_reference(((0.0, 10.0), (1.0, 20.0))),
        proportional_gain=0.75,
        torque_limit=30.0,
        equivalent_inertia=0.2,
        feedforward_inertia=0.1,
    )
    encoded = _encode_shaft_boundary(boundary)
    assert encoded["kind"] == "speed_tracking_shaft"
    decoded = _decode_shaft_boundary(encoded)
    assert isinstance(decoded, SpeedTrackingShaftBoundary)
    assert decoded.speed_reference.value_at(0.5) == 15.0
    assert decoded.proportional_gain == 0.75
    assert decoded.torque_limit == 30.0


def test_axial_tracking_document_roundtrip() -> None:
    force = AxialMotionTrackingForce(
        AxialMotionTrackingForceSpec(
            position_reference=_reference(((0.0, 0.0), (1.0, 0.01))),
            speed_reference=None,
            position_gain=5000.0,
            speed_gain=0.0,
            force_limit=1200.0,
        )
    )
    encoded = _encode_force_law(force)
    assert encoded["kind"] == "axial_motion_tracking"
    decoded = _decode_force_law(encoded)
    assert isinstance(decoded, AxialMotionTrackingForce)
    assert decoded.spec.position_reference is not None
    assert decoded.spec.position_reference.value_at(0.5) == 0.005
    assert decoded.spec.position_gain == 5000.0
    assert decoded.spec.force_limit == 1200.0
