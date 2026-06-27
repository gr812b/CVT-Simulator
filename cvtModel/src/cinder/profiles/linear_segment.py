from __future__ import annotations

from dataclasses import dataclass, field
from math import radians, tan

from .ramp_segment import RampSegment
from .types import ProfileSample, require_finite


@dataclass(frozen=True, slots=True)
class LinearSegment(RampSegment):
    """
    A straight local ramp segment.

    ``angle_degrees`` is the signed tangent angle measured from +x:

        slope = tan(angle_degrees).
    """

    angle_degrees: float

    _slope: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        RampSegment.__post_init__(self)
        require_finite(angle_degrees=self.angle_degrees)

        if not -90.0 < self.angle_degrees < 90.0:
            raise ValueError(
                "angle_degrees must lie strictly between -90 and 90."
            )

        object.__setattr__(
            self,
            "_slope",
            tan(radians(self.angle_degrees)),
        )

    @property
    def constant_slope(self) -> float:
        return self._slope

    def evaluate_local(self, x_local: float) -> ProfileSample:
        self._validate_local_coordinate(x_local)

        return ProfileSample(
            value=self._slope * x_local,
            first_derivative=self._slope,
            second_derivative=0.0,
        )

    def inverse_local_value(self, value: float) -> float:
        require_finite(value=value)

        if self._slope == 0.0:
            raise ValueError("A horizontal linear segment is not invertible.")

        x_local = value / self._slope
        self._validate_local_coordinate(x_local)
        return x_local
