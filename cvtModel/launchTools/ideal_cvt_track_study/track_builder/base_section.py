from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, radians, tan


@dataclass(frozen=True, slots=True)
class TrackSection:
    """Sequential base terrain on which local feature overlays are placed.

    A constant section grade uses

        dz/dx = tan(theta)

    so its base elevation varies linearly with distance. Obstacles may add a
    local elevation profile and therefore add to this slope.
    """

    name: str
    length_m: float
    grade_degrees: float
    friction_coefficient: float
    rolling_resistance_coefficient: float
    surface: str = "unspecified"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("section name must be non-empty")
        if not isfinite(self.length_m) or self.length_m <= 0.0:
            raise ValueError("section length_m must be positive and finite")
        if not isfinite(self.grade_degrees) or not -89.0 < self.grade_degrees < 89.0:
            raise ValueError("grade_degrees must lie strictly between -89 and 89")
        if not isfinite(self.friction_coefficient) or self.friction_coefficient < 0.0:
            raise ValueError("friction_coefficient must be finite and non-negative")
        if (
            not isfinite(self.rolling_resistance_coefficient)
            or self.rolling_resistance_coefficient < 0.0
        ):
            raise ValueError(
                "rolling_resistance_coefficient must be finite and non-negative"
            )
        if not self.surface:
            raise ValueError("surface must be non-empty")

    @property
    def grade_radians(self) -> float:
        return radians(self.grade_degrees)

    @property
    def grade_slope(self) -> float:
        return tan(self.grade_radians)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "length_m": self.length_m,
            "grade_degrees": self.grade_degrees,
            "friction_coefficient": self.friction_coefficient,
            "rolling_resistance_coefficient": self.rolling_resistance_coefficient,
            "surface": self.surface,
        }
