from __future__ import annotations

from math import pi

import pytest

from cinder.profiles import (
    HelixProfile,
    PiecewiseRamp,
    circular_helix_segment,
    linear_helix_segment,
)


def test_linear_helix_profile_scales_value_and_derivatives_by_radius() -> None:
    profile = PiecewiseRamp(
        (
            linear_helix_segment(
                length=0.02,
                helix_angle_degrees=45.0,
            ),
        )
    )
    helix = HelixProfile(
        circumferential_profile=profile,
        radius=0.01,
        theta_offset=0.3,
    )

    sample = helix.evaluate(0.004)

    # cot(45 degrees) = 1, so u = x.
    assert sample.circumferential_displacement == pytest.approx(0.004)
    assert sample.theta == pytest.approx(0.7)
    assert sample.dtheta_dx == pytest.approx(100.0)
    assert sample.d2theta_dx2 == pytest.approx(0.0)
    assert sample.helix_angle_magnitude == pytest.approx(pi / 4.0)


def test_circular_helix_profile_scales_second_derivative_by_radius() -> None:
    profile = PiecewiseRamp(
        (
            circular_helix_segment(
                length=0.02,
                start_helix_angle_degrees=20.0,
                end_helix_angle_degrees=36.0,
            ),
        )
    )
    helix = HelixProfile(circumferential_profile=profile, radius=0.015)

    x = 0.01
    profile_sample = profile.evaluate(x)
    helix_sample = helix.evaluate(x)

    assert helix_sample.dtheta_dx == pytest.approx(
        profile_sample.first_derivative / 0.015
    )
    assert helix_sample.d2theta_dx2 == pytest.approx(
        profile_sample.second_derivative / 0.015
    )


def test_negative_handedness_changes_rotation_sign_not_angle_magnitude() -> None:
    profile = PiecewiseRamp(
        (
            linear_helix_segment(
                length=0.02,
                helix_angle_degrees=30.0,
                handedness=-1,
            ),
        )
    )
    helix = HelixProfile(circumferential_profile=profile, radius=0.01)

    sample = helix.evaluate(0.005)

    assert sample.dtheta_dx < 0.0
    assert sample.helix_angle_magnitude == pytest.approx(pi / 6.0)
