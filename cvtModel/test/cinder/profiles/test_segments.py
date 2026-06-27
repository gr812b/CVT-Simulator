from __future__ import annotations

from dataclasses import dataclass
from math import pi

import pytest

from cinder.profiles import (
    CircularSegment,
    LinearSegment,
    PiecewiseRamp,
    ProfileSample,
    RampSegment,
)


def test_linear_segment_returns_value_slope_and_curvature() -> None:
    segment = LinearSegment(length=0.02, angle_degrees=45.0)

    sample = segment.evaluate_local(0.008)

    assert sample.value == pytest.approx(0.008)
    assert sample.first_derivative == pytest.approx(1.0)
    assert sample.second_derivative == pytest.approx(0.0)


def test_circular_segment_derivatives_match_finite_differences() -> None:
    segment = CircularSegment(
        length=0.02,
        angle_start_degrees=60.0,
        angle_end_degrees=30.0,
        quadrant=2,
    )

    x = 0.009
    step = 1e-6

    before = segment.evaluate_local(x - step)
    current = segment.evaluate_local(x)
    after = segment.evaluate_local(x + step)

    first_difference = (after.value - before.value) / (2.0 * step)
    second_difference = (
        after.value - 2.0 * current.value + before.value
    ) / step**2

    assert current.first_derivative == pytest.approx(
        first_difference,
        abs=1e-7,
    )
    assert current.second_derivative == pytest.approx(
        second_difference,
        abs=2e-5,
    )


def test_piecewise_ramp_applies_global_offsets_without_mutating_segments() -> None:
    first = LinearSegment(length=0.01, angle_degrees=45.0)
    second = CircularSegment(
        length=0.02,
        angle_start_degrees=45.0,
        angle_end_degrees=20.0,
        quadrant=2,
    )
    ramp = PiecewiseRamp((first, second))

    left = ramp.evaluate(0.01)
    right = ramp.evaluate(0.01 + 1e-9)

    assert left.value == pytest.approx(0.01)
    assert right.value == pytest.approx(0.01, abs=2e-9)
    assert ramp.x_min == pytest.approx(0.0)
    assert ramp.x_max == pytest.approx(0.03)

    # The same segment can be reused in another ramp because it owns no
    # mutable global x/y placement state.
    reused = PiecewiseRamp((first,))
    assert reused.height(0.005) == pytest.approx(0.005)


@dataclass(frozen=True, slots=True)
class QuadraticSegment(RampSegment):
    """A minimal custom segment proving the explicit base contract."""

    def evaluate_local(self, x_local: float) -> ProfileSample:
        self._validate_local_coordinate(x_local)
        return ProfileSample(
            value=x_local**2,
            first_derivative=2.0 * x_local,
            second_derivative=2.0,
        )


def test_custom_ramp_segment_implements_the_same_contract() -> None:
    ramp = PiecewiseRamp((QuadraticSegment(length=0.5),))

    sample = ramp.evaluate(0.2)

    assert sample.value == pytest.approx(0.04)
    assert sample.first_derivative == pytest.approx(0.4)
    assert sample.second_derivative == pytest.approx(2.0)


def test_circular_segment_inverse_is_local_and_unambiguous() -> None:
    segment = CircularSegment(
        length=0.02,
        angle_start_degrees=60.0,
        angle_end_degrees=30.0,
        quadrant=2,
    )

    x = 0.007
    value = segment.height_local(x)

    assert segment.inverse_local_value(value) == pytest.approx(x)
