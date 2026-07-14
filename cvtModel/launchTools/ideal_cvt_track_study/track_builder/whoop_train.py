from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, pi, sin

from .core import FeatureEffect, TrackEvaluationContext


@dataclass(frozen=True, slots=True)
class WhoopTrain:
    """Repeated smooth elevation profile with load transfer and energy loss.

    For each whoop of wavelength lambda and height h,

        z(x)   = h/2 [1 - cos(2 pi xi/lambda)],
        z'(x)  = h pi/lambda sin(2 pi xi/lambda),
        z''(x) = 2 pi^2 h/lambda^2 cos(2 pi xi/lambda).

    The local grade receives z'(x). A rigid-following normal-load estimate uses

        N ~= m [g cos(theta) + v^2 z''(x)].

    Optional suspension/tire dissipation is specified directly as energy lost
    per whoop and distributed using the same normalized raised-cosine shape.
    This is a longitudinal effective model, not a suspension simulation.
    """

    name: str
    start_m: float
    count: int
    wavelength_m: float
    height_m: float
    energy_loss_j_per_whoop: float = 0.0
    minimum_normal_load_scale: float = 0.05
    maximum_normal_load_scale: float = 2.0
    traction_multiplier: float = 1.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("whoop train name must be non-empty")
        if not isfinite(self.start_m) or self.start_m < 0.0:
            raise ValueError("start_m must be finite and non-negative")
        if self.count <= 0:
            raise ValueError("count must be positive")
        if not isfinite(self.wavelength_m) or self.wavelength_m <= 0.0:
            raise ValueError("wavelength_m must be positive and finite")
        if not isfinite(self.height_m) or self.height_m < 0.0:
            raise ValueError("height_m must be finite and non-negative")
        if (
            not isfinite(self.energy_loss_j_per_whoop)
            or self.energy_loss_j_per_whoop < 0.0
        ):
            raise ValueError("energy_loss_j_per_whoop must be non-negative")
        if (
            not isfinite(self.minimum_normal_load_scale)
            or self.minimum_normal_load_scale < 0.0
        ):
            raise ValueError("minimum_normal_load_scale must be non-negative")
        if (
            not isfinite(self.maximum_normal_load_scale)
            or self.maximum_normal_load_scale < self.minimum_normal_load_scale
        ):
            raise ValueError(
                "maximum_normal_load_scale must be at least minimum_normal_load_scale"
            )
        if not isfinite(self.traction_multiplier) or self.traction_multiplier < 0.0:
            raise ValueError("traction_multiplier must be finite and non-negative")

    @property
    def type_name(self) -> str:
        return "whoop_train"

    @property
    def end_m(self) -> float:
        return self.start_m + self.count * self.wavelength_m

    def is_active(self, distance_m: float) -> bool:
        return self.start_m <= distance_m < self.end_m

    def evaluate(self, context: TrackEvaluationContext) -> FeatureEffect:
        if not self.is_active(context.distance_m):
            return FeatureEffect()
        local = min(max(context.distance_m - self.start_m, 0.0), self.end_m - self.start_m)
        xi = local % self.wavelength_m
        phase = 2.0 * pi * xi / self.wavelength_m
        elevation = 0.5 * self.height_m * (1.0 - cos(phase))
        slope = self.height_m * pi / self.wavelength_m * sin(phase)
        vertical_curvature = (
            2.0 * pi**2 * self.height_m / self.wavelength_m**2 * cos(phase)
        )
        raw_normal_scale = 1.0 + (
            context.vehicle_speed_mps**2 * vertical_curvature / context.gravity_mps2
        )
        normal_scale = min(
            self.maximum_normal_load_scale,
            max(self.minimum_normal_load_scale, raw_normal_scale),
        )
        loss_shape_1_per_m = (1.0 - cos(phase)) / self.wavelength_m
        return FeatureEffect(
            elevation_offset_m=elevation,
            grade_slope_addition=slope,
            additional_resistance_force_n=self.energy_loss_j_per_whoop
            * loss_shape_1_per_m,
            normal_load_scale=normal_scale,
            friction_multiplier=self.traction_multiplier,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type_name,
            "name": self.name,
            "start_m": self.start_m,
            "count": self.count,
            "wavelength_m": self.wavelength_m,
            "height_m": self.height_m,
            "energy_loss_j_per_whoop": self.energy_loss_j_per_whoop,
            "minimum_normal_load_scale": self.minimum_normal_load_scale,
            "maximum_normal_load_scale": self.maximum_normal_load_scale,
            "traction_multiplier": self.traction_multiplier,
        }
