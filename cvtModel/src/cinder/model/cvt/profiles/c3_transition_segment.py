"""C3 derivative-matched transition for acceleration-level ramp mechanics."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from .ramp_segment import RampSegment
from .types import ProfileSample, require_finite


@dataclass(frozen=True, slots=True)
class C3TransitionSegment(RampSegment):
    """Polynomial ramp segment matching derivatives through third order.

    The profile itself is a sixth-order polynomial. It is parameterized by
    the first, second, and third profile derivatives at both ends.

    ``between_segments`` is the preferred constructor: it copies endpoint
    derivatives from the neighboring physical segments so the assembled
    PiecewiseRamp is C3 at both joins.
    """

    slope_start: float
    curvature_start: float
    third_derivative_start: float
    slope_end: float
    curvature_end: float
    third_derivative_end: float

    _coefficients: tuple[float, float, float, float, float, float] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        RampSegment.__post_init__(self)
        require_finite(
            slope_start=self.slope_start,
            curvature_start=self.curvature_start,
            third_derivative_start=self.third_derivative_start,
            slope_end=self.slope_end,
            curvature_end=self.curvature_end,
            third_derivative_end=self.third_derivative_end,
        )

        length = self.length

        # Let m(t)=y'(x), t=x/L, be quintic.
        a0 = self.slope_start
        a1 = length * self.curvature_start
        a2 = 0.5 * length**2 * self.third_derivative_start

        b0 = self.slope_end - (a0 + a1 + a2)
        b1 = length * self.curvature_end - (a1 + 2.0 * a2)
        b2 = length**2 * self.third_derivative_end - 2.0 * a2

        a3 = 10.0 * b0 - 4.0 * b1 + 0.5 * b2
        a4 = -15.0 * b0 + 7.0 * b1 - b2
        a5 = 6.0 * b0 - 3.0 * b1 + 0.5 * b2

        coefficients = (a0, a1, a2, a3, a4, a5)
        if not all(isfinite(value) for value in coefficients):
            raise ValueError("C3 transition coefficients must be finite.")
        object.__setattr__(self, "_coefficients", coefficients)

    @classmethod
    def between_segments(
        cls,
        *,
        left: RampSegment,
        right: RampSegment,
        length: float,
    ) -> "C3TransitionSegment":
        """Construct a C3 blend from exact neighboring endpoint data."""

        if not isinstance(left, RampSegment) or not isinstance(right, RampSegment):
            raise TypeError("left and right must be RampSegment instances.")

        left_sample = left.evaluate_local(left.length)
        right_sample = right.evaluate_local(0.0)
        if left_sample.third_derivative is None:
            raise ValueError(
                "Left segment must provide a third derivative for a C3 transition."
            )
        if right_sample.third_derivative is None:
            raise ValueError(
                "Right segment must provide a third derivative for a C3 transition."
            )

        return cls(
            length=length,
            slope_start=left_sample.first_derivative,
            curvature_start=left_sample.second_derivative,
            third_derivative_start=left_sample.third_derivative,
            slope_end=right_sample.first_derivative,
            curvature_end=right_sample.second_derivative,
            third_derivative_end=right_sample.third_derivative,
        )

    def evaluate_local(self, x_local: float) -> ProfileSample:
        self._validate_local_coordinate(x_local)
        length = self.length
        t = x_local / length
        a0, a1, a2, a3, a4, a5 = self._coefficients

        value = length * (
            a0 * t
            + 0.5 * a1 * t**2
            + (a2 / 3.0) * t**3
            + 0.25 * a3 * t**4
            + 0.2 * a4 * t**5
            + (a5 / 6.0) * t**6
        )
        first = a0 + a1 * t + a2 * t**2 + a3 * t**3 + a4 * t**4 + a5 * t**5
        second = (
            a1 + 2.0 * a2 * t + 3.0 * a3 * t**2 + 4.0 * a4 * t**3 + 5.0 * a5 * t**4
        ) / length
        third = (
            2.0 * a2 + 6.0 * a3 * t + 12.0 * a4 * t**2 + 20.0 * a5 * t**3
        ) / length**2

        return ProfileSample(
            value=value,
            first_derivative=first,
            second_derivative=second,
            third_derivative=third,
        )
