"""C3 derivative-matched transition for acceleration-level ramp mechanics."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import fsum, isfinite

from .ramp_segment import RampSegment
from .types import ProfileSample, require_finite


def _slope_coefficients(
    length: float,
    slope_start: float,
    curvature_start: float,
    third_derivative_start: float,
    slope_end: float,
    curvature_end: float,
    third_derivative_end: float,
) -> tuple[float, float, float, float, float, float]:
    """Quintic coefficients for y'(x), using the local coordinate x / length."""

    a0 = slope_start
    a1 = length * curvature_start
    a2 = 0.5 * length**2 * third_derivative_start
    b0 = fsum((slope_end, -a0, -a1, -a2))
    b1 = fsum((length * curvature_end, -a1, -2.0 * a2))
    b2 = fsum((length**2 * third_derivative_end, -2.0 * a2))
    return (
        a0,
        a1,
        a2,
        fsum((10.0 * b0, -4.0 * b1, 0.5 * b2)),
        fsum((-15.0 * b0, 7.0 * b1, -b2)),
        fsum((6.0 * b0, -3.0 * b1, 0.5 * b2)),
    )


@dataclass(frozen=True, slots=True)
class C3TransitionSegment(RampSegment):
    """Polynomial ramp segment matching derivatives through third order.

    The profile itself is a sixth-order polynomial. It is parameterized by
    the first, second, and third profile derivatives at both ends.

    ``between_segments`` is the preferred constructor: it copies endpoint
    derivatives from the neighboring physical segments so the assembled
    PiecewiseRamp is C3 at both joins.

    Evaluate the same polynomial from its nearer endpoint to avoid cancellation
    in short stages. No additional blend or change of the physical profile is
    introduced; the endpoint derivatives remain the supplied constraints.
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

    _reverse_coefficients: tuple[float, float, float, float, float, float] = field(
        init=False,
        repr=False,
    )
    _end_value: float = field(init=False, repr=False)

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

        coefficients = _slope_coefficients(
            length,
            self.slope_start,
            self.curvature_start,
            self.third_derivative_start,
            self.slope_end,
            self.curvature_end,
            self.third_derivative_end,
        )
        # m(1-u), where u=(L-x)/L. Odd derivatives change sign on reversal.
        reverse = _slope_coefficients(
            length,
            self.slope_end,
            -self.curvature_end,
            self.third_derivative_end,
            self.slope_start,
            -self.curvature_start,
            self.third_derivative_start,
        )
        # Exact integral of the quintic Hermite slope, in endpoint form.
        end_value = length * fsum(
            (
                self.slope_start / 2.0,
                self.slope_end / 2.0,
                length * self.curvature_start / 10.0,
                -length * self.curvature_end / 10.0,
                length**2 * self.third_derivative_start / 120.0,
                length**2 * self.third_derivative_end / 120.0,
            )
        )
        if not all(isfinite(value) for value in (*coefficients, *reverse, end_value)):
            raise ValueError("C3 transition coefficients and end value must be finite.")
        object.__setattr__(self, "_coefficients", coefficients)
        object.__setattr__(self, "_reverse_coefficients", reverse)
        object.__setattr__(self, "_end_value", end_value)

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
        # These are boundary conditions, not approximations to a nearby point.
        # In particular, do not recover zero endpoint derivatives by subtracting
        # large polynomial terms and then dividing their residual by L or L^2.
        if x_local == 0.0:
            return ProfileSample(
                value=0.0,
                first_derivative=self.slope_start,
                second_derivative=self.curvature_start,
                third_derivative=self.third_derivative_start,
            )
        if x_local == length:
            return ProfileSample(
                value=self._end_value,
                first_derivative=self.slope_end,
                second_derivative=self.curvature_end,
                third_derivative=self.third_derivative_end,
            )

        reverse = x_local > length / 2.0
        # Subtract before normalizing: 1 - x/L can lose the near-end distance.
        t = (length - x_local) / length if reverse else x_local / length
        a0, a1, a2, a3, a4, a5 = (
            self._reverse_coefficients if reverse else self._coefficients
        )
        integral = (
            length
            * t
            * (
                a0
                + t
                * (
                    a1 / 2.0
                    + t * (a2 / 3.0 + t * (a3 / 4.0 + t * (a4 / 5.0 + t * a5 / 6.0)))
                )
            )
        )
        first = a0 + t * (a1 + t * (a2 + t * (a3 + t * (a4 + t * a5))))
        second = (
            a1 + t * (2.0 * a2 + t * (3.0 * a3 + t * (4.0 * a4 + t * 5.0 * a5)))
        ) / length
        third = (
            2.0 * a2 + t * (6.0 * a3 + t * (12.0 * a4 + t * 20.0 * a5))
        ) / length**2

        return ProfileSample(
            value=self._end_value - integral if reverse else integral,
            first_derivative=first,
            second_derivative=-second if reverse else second,
            third_derivative=third,
        )
