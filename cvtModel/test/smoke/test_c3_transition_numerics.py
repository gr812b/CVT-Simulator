"""Regression tests for short, derivative-matched ramp stages.

These exercise the real profile classes. The independent Decimal reference
uses Bernstein control points, not the implementation's power coefficients.
"""

from dataclasses import replace
from decimal import Decimal, localcontext
from math import isclose, nextafter, radians, tan

import pytest

from cinder.model.cvt.profiles.c3_transition_segment import C3TransitionSegment
from cinder.model.cvt.profiles.linear_segment import LinearSegment
from cinder.model.cvt.profiles.piecewise_ramp import PiecewiseRamp


def transition(length=0.005, start=55.0, end=35.0):
    return C3TransitionSegment(
        length=length,
        slope_start=tan(radians(start)),
        curvature_start=0.0,
        third_derivative_start=0.0,
        slope_end=tan(radians(end)),
        curvature_end=0.0,
        third_derivative_end=0.0,
    )


def reference(segment, x):
    """80-digit Bernstein evaluation of the same Hermite boundary conditions."""
    with localcontext() as context:
        context.prec = 80
        dec = Decimal.from_float
        length = dec(segment.length)
        t = dec(x) / length
        s0, s1 = dec(segment.slope_start), dec(segment.slope_end)
        c0 = length * dec(segment.curvature_start)
        c1 = length * dec(segment.curvature_end)
        d0 = length**2 * dec(segment.third_derivative_start)
        d1 = length**2 * dec(segment.third_derivative_end)
        slopes = [
            s0,
            s0 + c0 / 5,
            s0 + 2 * c0 / 5 + d0 / 20,
            s1 - 2 * c1 / 5 + d1 / 20,
            s1 - c1 / 5,
            s1,
        ]
        curvatures = [5 * (b - a) / length for a, b in zip(slopes, slopes[1:])]
        thirds = [4 * (b - a) / length for a, b in zip(curvatures, curvatures[1:])]
        heights = [Decimal(0)]
        for slope in slopes:
            heights.append(heights[-1] + length * slope / 6)

        def casteljau(points):
            while len(points) > 1:
                points = [(1 - t) * a + t * b for a, b in zip(points, points[1:])]
            return float(points[0])

        return tuple(
            casteljau(points) for points in (heights, slopes, curvatures, thirds)
        )


def components(sample):
    return (
        sample.value,
        sample.first_derivative,
        sample.second_derivative,
        sample.third_derivative,
    )


def test_reported_five_mm_join_is_c3():
    # Guided UI: 55 -> 35 degrees at 5 mm, then constant 35 degree stages.
    ramp = PiecewiseRamp(
        [
            transition(),
            LinearSegment(length=0.01, angle_degrees=35.0),
            LinearSegment(length=0.01, angle_degrees=35.0),
        ]
    )
    junction = ramp.junction_continuity()[0]
    assert junction.coordinate == 0.005
    assert junction.left_third_derivative == junction.right_third_derivative == 0.0
    # Keep the existing audit thresholds; do not pass custom loose tolerances.
    ramp.require_continuity(order=3)


@pytest.mark.parametrize("length", [1e-6, 1e-4, 0.001, 0.005, 0.05, 1.0])
@pytest.mark.parametrize("angles", [(55.0, 35.0), (35.0, 55.0), (80.0, 10.0)])
def test_guided_stages_join_lines_and_other_transitions(length, angles):
    start, end = angles
    ramp = PiecewiseRamp(
        [
            LinearSegment(length=0.002, angle_degrees=start),
            transition(length, start, end),
            transition(length * 1.3, end, 40.0),
            LinearSegment(length=0.003, angle_degrees=40.0),
        ]
    )
    ramp.require_continuity(order=3)
    for junction in ramp.junction_continuity():
        assert (
            junction.left_second_derivative == junction.right_second_derivative == 0.0
        )
        assert junction.left_third_derivative == junction.right_third_derivative == 0.0


@pytest.mark.parametrize("length", [1e-6, 0.005, 0.027, 1.0])
def test_arbitrary_endpoint_derivatives_are_returned_exactly(length):
    segment = replace(
        transition(length),
        curvature_start=-12.3456789,
        third_derivative_start=1234.56789,
        curvature_end=31.2345678,
        third_derivative_end=-7654.321,
    )
    first, last = segment.evaluate_local(0.0), segment.evaluate_local(length)
    assert components(first) == (
        0.0,
        segment.slope_start,
        segment.curvature_start,
        segment.third_derivative_start,
    )
    assert components(last)[1:] == (
        segment.slope_end,
        segment.curvature_end,
        segment.third_derivative_end,
    )


@pytest.mark.parametrize("length", [1e-6, 1e-4, 0.005, 0.027, 1.0])
@pytest.mark.parametrize(
    "shape", ["falling", "rising", "nonzero-derivatives", "sign-change"]
)
def test_entire_polynomial_agrees_with_high_precision_reference(length, shape):
    segment = (
        transition(length, 35.0, 55.0) if shape == "rising" else transition(length)
    )
    if shape == "nonzero-derivatives":
        segment = replace(
            segment,
            curvature_start=-0.3 / length,
            curvature_end=0.7 / length,
            third_derivative_start=0.2 / length**2,
            third_derivative_end=-0.4 / length**2,
        )
    elif shape == "sign-change":
        segment = replace(segment, slope_start=-0.75, slope_end=0.75)
    positions = [length * (i / 100) for i in range(101)] + [
        length * 1e-12,
        length * (1 - 1e-12),
        nextafter(length, 0.0),
        nextafter(length / 2, 0.0),
        nextafter(length / 2, length),
    ]
    # Dimensionless comparisons cover short stages without hiding scaled errors.
    scales = (1 / length, 1.0, length, length**2)
    for x in positions:
        actual = components(segment.evaluate_local(x))
        expected = reference(segment, x)
        for order, (a, e, scale) in enumerate(zip(actual, expected, scales)):
            assert isclose(a * scale, e * scale, rel_tol=3e-13, abs_tol=3e-14), (
                shape,
                length,
                x,
                order,
                a,
                e,
            )


@pytest.mark.parametrize("length", [1e-6, 1e-4, 0.005, 0.027])
def test_near_right_endpoint_derivatives_do_not_have_a_cancellation_floor(length):
    segment = transition(length)
    for x in (nextafter(length, 0.0), length * (1 - 1e-10)):
        actual = components(segment.evaluate_local(x))
        expected = reference(segment, x)
        for order in (2, 3):
            assert expected[order] != 0.0
            assert isclose(actual[order], expected[order], rel_tol=3e-12, abs_tol=0.0)


@pytest.mark.parametrize("length", [1e-4, 0.005, 0.04])
def test_between_segments_retains_nonzero_neighbor_derivatives(length):
    left = replace(transition(0.007), curvature_end=2.4, third_derivative_end=-31.2)
    right = replace(
        transition(0.009, 40.0, 50.0),
        curvature_start=-3.7,
        third_derivative_start=43.9,
    )
    bridge = C3TransitionSegment.between_segments(left=left, right=right, length=length)
    ramp = PiecewiseRamp([left, bridge, right])
    ramp.require_continuity(order=3, relative_tolerance=0.0, absolute_tolerance=0.0)


@pytest.mark.parametrize(
    "field,delta",
    [
        ("slope_start", 1e-4),
        ("curvature_start", 1e-5),
        ("third_derivative_start", 1e-8),
    ],
)
def test_real_derivative_mismatches_still_fail(field, delta):
    left = transition()
    right = transition(0.01, 35.0, 40.0)
    right = replace(right, **{field: getattr(right, field) + delta})
    ramp = PiecewiseRamp([left, right])
    with pytest.raises(ValueError, match="not C3"):
        ramp.require_continuity(order=3)


@pytest.mark.parametrize("angle", [-55.0, 0.0, 35.0, 80.0])
def test_constant_transition_is_still_a_straight_line(angle):
    segment = transition(0.005, angle, angle)
    line = LinearSegment(length=segment.length, angle_degrees=angle)
    for fraction in (0.0, 0.1, 0.5, 0.9, 1.0):
        x = fraction * segment.length
        a, b = segment.evaluate_local(x), line.evaluate_local(x)
        assert isclose(a.value, b.value, rel_tol=1e-15, abs_tol=1e-18)
        assert components(a)[1:] == components(b)[1:]


@pytest.mark.parametrize("x", [-1e-15, 0.005000001, float("nan"), float("inf")])
def test_invalid_coordinates_are_not_clamped_to_endpoints(x):
    with pytest.raises(ValueError):
        transition().evaluate_local(x)
