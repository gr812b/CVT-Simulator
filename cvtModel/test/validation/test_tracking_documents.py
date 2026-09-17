from __future__ import annotations

from math import isclose

from cinder.contracts.document import _decode_force_law, _encode_force_law
from cinder.contracts.simulation_document import _decode_shaft_boundary, _encode_shaft_boundary
from cinder.model.boundaries.shaft import SpeedTrackingShaftBoundary
from cinder.model.cvt.actuation import AxialMotionTrackingForce, AxialMotionTrackingForceSpec
from cinder.model.reference import PiecewiseLinearReference, TimeValuePoint


def _reference(values: tuple[tuple[float, float], ...]) -> PiecewiseLinearReference:
    return PiecewiseLinearReference(tuple(TimeValuePoint(t, value) for t, value in values))


def test_speed_tracking_boundary_explicit_gain_document_roundtrip() -> None:
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


def test_speed_tracking_boundary_error_budget_document_roundtrip() -> None:
    boundary = SpeedTrackingShaftBoundary.from_tracking_error_budget(
        speed_reference=_reference(((0.0, 100.0), (1.0, 120.0))),
        torque_limit=30.0,
        tracking_error_budget=1.5,
        equivalent_inertia=0.2,
        feedback_authority_fraction=0.8,
    )
    encoded = _encode_shaft_boundary(boundary)
    assert encoded["tracking_error_budget_rad_per_s"] == 1.5
    assert encoded["feedback_authority_fraction"] == 0.8
    decoded = _decode_shaft_boundary(encoded)
    assert isinstance(decoded, SpeedTrackingShaftBoundary)
    assert decoded.tracking_error_budget == 1.5
    assert decoded.feedback_authority_fraction == 0.8
    assert isclose(decoded.proportional_gain, 16.0)


def test_speed_tracking_boundary_minimal_document_auto_tunes() -> None:
    decoded = _decode_shaft_boundary(
        {
            "kind": "speed_tracking_shaft",
            "speed_reference": {
                "points": [
                    {"time_s": 0.0, "value": 180.0},
                    {"time_s": 1.0, "value": 240.0},
                ]
            },
            "torque_limit_Nm": 30.0,
            "equivalent_inertia_kg_m2": 0.05,
        }
    )
    assert isinstance(decoded, SpeedTrackingShaftBoundary)
    assert isclose(decoded.tracking_error_budget or 0.0, 2.4)
    assert isclose(decoded.proportional_gain, 0.85 * 30.0 / 2.4)
    assert isclose(decoded.feedforward_inertia, 0.05)


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
