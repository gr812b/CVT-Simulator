from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .core import FeatureEffect, TrackEvaluationContext


@dataclass(frozen=True, slots=True)
class CurvatureSegment:
    """Constant plan-view curvature with optional banking.

    With curvature ``kappa = 1/R`` and bank angle ``beta`` positive into the
    turn, the road-normal and road-lateral force demands are approximated by

        N/m   = g cos(theta) cos(beta) + v^2 |kappa| sin(beta),
        F_y/m = v^2 |kappa| cos(beta) - g cos(theta) sin(beta).

    Longitudinal tire capacity then follows the friction circle

        F_x,max = sqrt(max((mu N)^2 - F_y^2, 0)).

    No arbitrary driver speed cap is stored in the track. Positive bank assists
    the specified turn; negative bank is adverse camber.
    """

    name: str
    start_m: float
    length_m: float
    radius_m: float
    direction: str = "left"
    bank_angle_degrees: float = 0.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("curvature segment name must be non-empty")
        if not isfinite(self.start_m) or self.start_m < 0.0:
            raise ValueError("start_m must be finite and non-negative")
        if not isfinite(self.length_m) or self.length_m <= 0.0:
            raise ValueError("length_m must be positive and finite")
        if not isfinite(self.radius_m) or self.radius_m <= 0.0:
            raise ValueError("radius_m must be positive and finite")
        if self.direction not in {"left", "right"}:
            raise ValueError("direction must be 'left' or 'right'")
        if (
            not isfinite(self.bank_angle_degrees)
            or not -60.0 < self.bank_angle_degrees < 60.0
        ):
            raise ValueError("bank_angle_degrees must lie strictly between -60 and 60")

    @property
    def type_name(self) -> str:
        return "curvature_segment"

    @property
    def end_m(self) -> float:
        return self.start_m + self.length_m

    @property
    def signed_curvature_1_per_m(self) -> float:
        return (1.0 if self.direction == "left" else -1.0) / self.radius_m

    def is_active(self, distance_m: float) -> bool:
        return self.start_m <= distance_m < self.end_m

    def evaluate(self, context: TrackEvaluationContext) -> FeatureEffect:
        if not self.is_active(context.distance_m):
            return FeatureEffect()
        return FeatureEffect(
            curvature_1_per_m=self.signed_curvature_1_per_m,
            bank_angle_degrees=self.bank_angle_degrees,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type_name,
            "name": self.name,
            "start_m": self.start_m,
            "length_m": self.length_m,
            "radius_m": self.radius_m,
            "direction": self.direction,
            "bank_angle_degrees": self.bank_angle_degrees,
        }
