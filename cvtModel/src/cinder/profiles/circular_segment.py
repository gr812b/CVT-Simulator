from __future__ import annotations

from dataclasses import dataclass, field
from math import acos, asin, cos, pi, radians, sin

from .ramp_segment import RampSegment
from .types import ProfileSample, require_finite


@dataclass(frozen=True, slots=True)
class CircularSegment(RampSegment):
    """
    A circular local ramp segment parameterized by slope magnitudes and quadrant.

    The positive angles describe slope magnitudes measured from +x. Quadrant
    supplies the slope sign and determines the arc orientation:

        Q1: negative slope, gentle -> steep
        Q2: positive slope, steep  -> gentle
        Q3: negative slope, steep  -> gentle
        Q4: positive slope, gentle -> steep

    The segment starts at local coordinate (0, 0). Its global position and
    vertical offset are assigned only by PiecewiseRamp.
    """

    angle_start_degrees: float
    angle_end_degrees: float
    quadrant: int = 3

    radius: float = field(init=False)
    _theta_start: float = field(init=False, repr=False)
    _theta_end: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        RampSegment.__post_init__(self)
        require_finite(
            angle_start_degrees=self.angle_start_degrees,
            angle_end_degrees=self.angle_end_degrees,
        )

        if self.quadrant not in (1, 2, 3, 4):
            raise ValueError("quadrant must be one of 1, 2, 3, or 4.")

        if not 0.0 <= self.angle_start_degrees < 90.0:
            raise ValueError(
                "angle_start_degrees must lie in [0, 90)."
            )

        if not 0.0 <= self.angle_end_degrees < 90.0:
            raise ValueError(
                "angle_end_degrees must lie in [0, 90)."
            )

        if self.quadrant in (2, 3):
            valid_order = (
                self.angle_start_degrees >= self.angle_end_degrees
            )
            expected_order = "greater than or equal to"
        else:
            valid_order = (
                self.angle_start_degrees <= self.angle_end_degrees
            )
            expected_order = "less than or equal to"

        if not valid_order:
            raise ValueError(
                f"For quadrant {self.quadrant}, angle_start_degrees must be "
                f"{expected_order} angle_end_degrees."
            )

        theta_start = self._position_angle(
            angle_degrees=self.angle_start_degrees,
            quadrant=self.quadrant,
        )
        theta_end = self._position_angle(
            angle_degrees=self.angle_end_degrees,
            quadrant=self.quadrant,
        )

        cos_difference = cos(theta_end) - cos(theta_start)
        if cos_difference <= 0.0:
            raise ValueError(
                "The supplied endpoint angles do not produce increasing x."
            )

        object.__setattr__(self, "radius", self.length / cos_difference)
        object.__setattr__(self, "_theta_start", theta_start)
        object.__setattr__(self, "_theta_end", theta_end)

    def evaluate_local(self, x_local: float) -> ProfileSample:
        self._validate_local_coordinate(x_local)

        cos_theta = cos(self._theta_start) + x_local / self.radius
        cos_theta = max(-1.0, min(1.0, cos_theta))

        theta = self._theta_from_cosine(cos_theta)
        sin_theta = sin(theta)

        return ProfileSample(
            value=self.radius * (sin_theta - sin(self._theta_start)),
            first_derivative=-cos_theta / sin_theta,
            second_derivative=-1.0 / (self.radius * sin_theta**3),
        )

    def inverse_local_value(self, value: float) -> float:
        """Invert a local circular-segment height when it has one valid root."""

        require_finite(value=value)

        sin_theta = sin(self._theta_start) + value / self.radius
        tolerance = 1e-12

        if sin_theta < -1.0 - tolerance or sin_theta > 1.0 + tolerance:
            raise ValueError("value lies outside this circular segment's range.")

        sin_theta = max(-1.0, min(1.0, sin_theta))
        principal = asin(sin_theta)
        candidates = (
            principal % (2.0 * pi),
            (pi - principal) % (2.0 * pi),
        )

        valid_x: list[float] = []
        for theta in candidates:
            x_local = self.radius * (cos(theta) - cos(self._theta_start))
            if -tolerance <= x_local <= self.length + tolerance:
                sampled = self.evaluate_local(
                    min(self.length, max(0.0, x_local))
                )
                if abs(sampled.value - value) <= tolerance:
                    valid_x.append(
                        min(self.length, max(0.0, x_local))
                    )

        unique_x: list[float] = []
        for x_local in valid_x:
            if not any(abs(x_local - other) <= tolerance for other in unique_x):
                unique_x.append(x_local)

        if len(unique_x) == 1:
            return unique_x[0]

        if len(unique_x) > 1:
            raise ValueError(
                "value has multiple valid inverse positions in this segment."
            )

        raise ValueError("value does not map to this circular segment.")

    def _theta_from_cosine(self, cos_theta: float) -> float:
        if self.quadrant in (1, 2):
            return acos(cos_theta)

        return 2.0 * pi - acos(cos_theta)

    @staticmethod
    def _position_angle(*, angle_degrees: float, quadrant: int) -> float:
        angle_radians = radians(angle_degrees)

        if quadrant == 1:
            return pi / 2.0 - angle_radians
        if quadrant == 2:
            return pi / 2.0 + angle_radians
        if quadrant == 3:
            return 3.0 * pi / 2.0 - angle_radians
        return 3.0 * pi / 2.0 + angle_radians
