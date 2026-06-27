from __future__ import annotations

import pytest

from cinder.actuation import PulleyActuationState
from cinder.actuation.forces import (
    AxialSpringForce,
    AxialSpringForceSpec,
    CentrifugalRampForce,
    CentrifugalRampForceSpec,
    SecondaryHelixForce,
    SecondaryHelixForceSpec,
)
from cinder.closure import ClosureGains, ClosureUnknown, ClosureUnknowns
from cinder.profiles.circular_segment import CircularSegment
from cinder.profiles.helix import HelixProfile
from cinder.profiles.linear_segment import LinearSegment
from cinder.profiles.piecewise_ramp import PiecewiseRamp


def _state(
    *,
    axial_position: float = 0.0,
    axial_speed: float = 0.0,
    shaft_speed: float = 0.0,
) -> PulleyActuationState:
    return PulleyActuationState(
        axial_position=axial_position,
        axial_speed=axial_speed,
        shaft_speed=shaft_speed,
    )


def _linear_profile() -> PiecewiseRamp:
    return PiecewiseRamp(
        (LinearSegment(length=0.020, angle_degrees=45.0),)
    )


def _curved_helix() -> HelixProfile:
    return HelixProfile(
        circumferential_profile=PiecewiseRamp(
            (
                CircularSegment(
                    length=0.020,
                    angle_start_degrees=60.0,
                    angle_end_degrees=30.0,
                    quadrant=2,
                ),
            )
        ),
        radius=0.020,
    )


def test_closure_unknowns_and_gains_share_one_named_order() -> None:
    unknowns = ClosureUnknowns.from_components(
        primary_angular_acceleration=1.0,
        secondary_angular_acceleration=2.0,
        belt_acceleration=3.0,
        shift_acceleration=4.0,
        primary_torque=5.0,
        secondary_torque=6.0,
    )
    gains = ClosureGains.from_components(
        primary_angular_acceleration=10.0,
        secondary_torque=20.0,
    )

    assert unknowns[ClosureUnknown.PRIMARY_ANGULAR_ACCELERATION] == 1.0
    assert unknowns[ClosureUnknown.SECONDARY_TORQUE] == 6.0
    assert unknowns.as_tuple() == (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    assert gains.dot(unknowns) == pytest.approx(130.0)


def test_primary_force_laws_are_bias_only() -> None:
    centrifugal = CentrifugalRampForce(
        CentrifugalRampForceSpec(
            flyweight_mass=2.0,
            radius_at_zero_position=1.0,
            radial_displacement_profile=_linear_profile(),
        )
    )
    spring = AxialSpringForce(
        AxialSpringForceSpec(
            stiffness=10.0,
            initial_compression=0.5,
            compression_per_axial_position=1.0,
        )
    )
    state = _state(axial_position=0.010, shaft_speed=3.0)

    centrifugal_relation = centrifugal.evaluate(state)
    spring_relation = spring.evaluate(state)

    # F_cf = 2 * 3² * (1 + 0.010) * 1 = 18.18 N.
    assert centrifugal_relation.bias == pytest.approx(18.18)
    assert centrifugal_relation.gains == ClosureGains.zeros()

    # F_spring = -10 * (0.5 + 0.010) * 1 = -5.1 N.
    assert spring_relation.bias == pytest.approx(-5.1)
    assert spring_relation.gains == ClosureGains.zeros()


def test_secondary_helix_uses_actual_cinder_helix_sample_fields() -> None:
    helix_profile = _curved_helix()
    state = _state(axial_position=0.008, axial_speed=0.5)
    sample = helix_profile.evaluate(state.axial_position)

    force = SecondaryHelixForce(
        SecondaryHelixForceSpec(
            helix_profile=helix_profile,
            movable_sheave_rotational_inertia=0.2,
            torsional_stiffness=10.0,
            initial_twist=0.1,
            movable_sheave_torque_fraction=0.5,
        )
    )

    relation = force.evaluate(state)

    expected_bias = (
        sample.dtheta_dx * 10.0 * (0.1 + sample.theta)
        + 0.2
        * sample.dtheta_dx
        * sample.d2theta_dx2
        * state.axial_speed**2
    )

    assert relation.bias == pytest.approx(expected_bias)
    assert relation.gains.as_tuple() == pytest.approx(
        (
            0.0,
            -0.2 * sample.dtheta_dx,
            0.0,
            0.2 * sample.dtheta_dx**2,
            0.0,
            0.5 * sample.dtheta_dx,
        )
    )
