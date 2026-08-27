from __future__ import annotations

from math import isclose

from cinder.model.cvt.profiles import (
    C3TransitionSegment,
    CircularSegment,
    LinearSegment,
    PiecewiseRamp,
)


def test_c3_transition_matches_neighbors_through_third_derivative() -> None:
    left = LinearSegment(length=0.005, angle_degrees=20.0)
    right = CircularSegment(
        length=0.030,
        angle_start_degrees=35.0,
        angle_end_degrees=10.0,
        quadrant=2,
    )
    transition = C3TransitionSegment.between_segments(
        left=left,
        right=right,
        length=0.003,
    )

    left_end = left.evaluate_local(left.length)
    start = transition.evaluate_local(0.0)
    end = transition.evaluate_local(transition.length)
    right_start = right.evaluate_local(0.0)

    for actual, expected in (
        (start.first_derivative, left_end.first_derivative),
        (start.second_derivative, left_end.second_derivative),
        (start.third_derivative, left_end.third_derivative),
        (end.first_derivative, right_start.first_derivative),
        (end.second_derivative, right_start.second_derivative),
        (end.third_derivative, right_start.third_derivative),
    ):
        assert expected is not None
        assert isclose(
            actual,
            expected,
            rel_tol=2.0e-12,
            abs_tol=2.0e-9,
        )


def test_piecewise_continuity_distinguishes_raw_and_smoothed_join() -> None:
    left = LinearSegment(length=0.005, angle_degrees=20.0)
    right = CircularSegment(
        length=0.030,
        angle_start_degrees=35.0,
        angle_end_degrees=10.0,
        quadrant=2,
    )

    raw = PiecewiseRamp((left, right))
    assert not raw.junction_continuity()[0].is_continuous(order=1)

    transition = C3TransitionSegment.between_segments(
        left=left,
        right=right,
        length=0.003,
    )
    smooth = PiecewiseRamp((left, transition, right))
    smooth.require_continuity(order=3)
    assert all(
        junction.is_continuous(order=3)
        for junction in smooth.junction_continuity()
    )
