from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .core import FeatureEffect, TrackEvaluationContext


@dataclass(frozen=True, slots=True)
class SurfacePatch:
    """Distance-local change in grip and rolling resistance.

    The simulator then uses

        F_tire,max = mu(x) N(x)
        F_rr       = C_rr(x) N(x) sign(v)

    so mud, sand, wet grass, and loose gravel can alter both available traction
    and parasitic resistance. This is physical terrain, not driver behaviour.
    """

    name: str
    start_m: float
    length_m: float
    friction_coefficient: float | None = None
    rolling_resistance_coefficient: float | None = None
    friction_multiplier: float = 1.0
    rolling_resistance_multiplier: float = 1.0
    surface: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("surface patch name must be non-empty")
        if not isfinite(self.start_m) or self.start_m < 0.0:
            raise ValueError("start_m must be finite and non-negative")
        if not isfinite(self.length_m) or self.length_m <= 0.0:
            raise ValueError("length_m must be positive and finite")
        if self.friction_coefficient is not None and (
            not isfinite(self.friction_coefficient) or self.friction_coefficient < 0.0
        ):
            raise ValueError("friction_coefficient must be non-negative when provided")
        if self.rolling_resistance_coefficient is not None and (
            not isfinite(self.rolling_resistance_coefficient)
            or self.rolling_resistance_coefficient < 0.0
        ):
            raise ValueError(
                "rolling_resistance_coefficient must be non-negative when provided"
            )
        for field_name, value in (
            ("friction_multiplier", self.friction_multiplier),
            ("rolling_resistance_multiplier", self.rolling_resistance_multiplier),
        ):
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{field_name} must be finite and non-negative")

    @property
    def type_name(self) -> str:
        return "surface_patch"

    @property
    def end_m(self) -> float:
        return self.start_m + self.length_m

    def is_active(self, distance_m: float) -> bool:
        return self.start_m <= distance_m < self.end_m

    def evaluate(self, context: TrackEvaluationContext) -> FeatureEffect:
        if not self.is_active(context.distance_m):
            return FeatureEffect()
        return FeatureEffect(
            friction_coefficient_override=self.friction_coefficient,
            friction_multiplier=self.friction_multiplier,
            rolling_resistance_override=self.rolling_resistance_coefficient,
            rolling_resistance_multiplier=self.rolling_resistance_multiplier,
            surface_override=self.surface,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type_name,
            "name": self.name,
            "start_m": self.start_m,
            "length_m": self.length_m,
            "friction_coefficient": self.friction_coefficient,
            "rolling_resistance_coefficient": self.rolling_resistance_coefficient,
            "friction_multiplier": self.friction_multiplier,
            "rolling_resistance_multiplier": self.rolling_resistance_multiplier,
            "surface": self.surface,
        }
