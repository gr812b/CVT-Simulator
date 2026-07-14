from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, pi, sin

from .core import FeatureEffect, TrackEvaluationContext


_ALLOWED_KINDS = {"bump", "pipe", "tire", "hole", "dip", "drop_recovery"}


@dataclass(frozen=True, slots=True)
class ProfileObstacle:
    """Measured smooth obstacle profile for bumps, pipes, tires, holes, and dips.

    The obstacle is a signed raised-cosine profile over length ``L``:

        z(x)   = h/2 [1 - cos(2 pi xi/L)],
        z'(x)  = h pi/L sin(2 pi xi/L),
        z''(x) = 2 pi^2 h/L^2 cos(2 pi xi/L).

    ``vertical_amplitude_m`` is positive for bumps/pipes/tires and negative for
    holes/dips. The rigid-following normal-load estimate is

        k_N = clip(1 + v^2 z''/g, k_min, k_max).

    Unresolved impact and suspension work is distributed in space with

        psi(x) = [1 - cos(2 pi xi/L)] / L,
        F_loss = (E_fixed + k_impact v^2) psi(x).

    A permanent net elevation change belongs in the base sections. The
    ``drop_recovery`` kind represents a local drop and recovery, not a permanent
    step down.
    """

    name: str
    start_m: float
    length_m: float
    vertical_amplitude_m: float
    profile_kind: str = "bump"
    fixed_energy_loss_j: float = 0.0
    impact_loss_coefficient_kg: float = 0.0
    traction_multiplier: float = 1.0
    minimum_normal_load_scale: float = 0.0
    maximum_normal_load_scale: float = 2.5

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("profile obstacle name must be non-empty")
        if not isfinite(self.start_m) or self.start_m < 0.0:
            raise ValueError("start_m must be finite and non-negative")
        if not isfinite(self.length_m) or self.length_m <= 0.0:
            raise ValueError("length_m must be positive and finite")
        if not isfinite(self.vertical_amplitude_m):
            raise ValueError("vertical_amplitude_m must be finite")
        if self.profile_kind not in _ALLOWED_KINDS:
            raise ValueError(
                f"profile_kind must be one of {sorted(_ALLOWED_KINDS)}"
            )
        if self.profile_kind in {"bump", "pipe", "tire"} and self.vertical_amplitude_m < 0.0:
            raise ValueError(
                f"{self.profile_kind} requires non-negative vertical_amplitude_m"
            )
        if self.profile_kind in {"hole", "dip", "drop_recovery"} and self.vertical_amplitude_m > 0.0:
            raise ValueError(
                f"{self.profile_kind} requires non-positive vertical_amplitude_m"
            )
        for field_name, value in (
            ("fixed_energy_loss_j", self.fixed_energy_loss_j),
            ("impact_loss_coefficient_kg", self.impact_loss_coefficient_kg),
            ("traction_multiplier", self.traction_multiplier),
            ("minimum_normal_load_scale", self.minimum_normal_load_scale),
            ("maximum_normal_load_scale", self.maximum_normal_load_scale),
        ):
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{field_name} must be finite and non-negative")
        if self.maximum_normal_load_scale < self.minimum_normal_load_scale:
            raise ValueError(
                "maximum_normal_load_scale must be at least minimum_normal_load_scale"
            )

    @property
    def type_name(self) -> str:
        return "profile_obstacle"

    @property
    def end_m(self) -> float:
        return self.start_m + self.length_m

    def is_active(self, distance_m: float) -> bool:
        return self.start_m <= distance_m < self.end_m

    def evaluate(self, context: TrackEvaluationContext) -> FeatureEffect:
        if not self.is_active(context.distance_m):
            return FeatureEffect()
        xi = min(max(context.distance_m - self.start_m, 0.0), self.length_m)
        phase = 2.0 * pi * xi / self.length_m
        height = self.vertical_amplitude_m
        elevation = 0.5 * height * (1.0 - cos(phase))
        slope = height * pi / self.length_m * sin(phase)
        vertical_curvature = 2.0 * pi**2 * height / self.length_m**2 * cos(phase)
        raw_normal_scale = 1.0 + (
            context.vehicle_speed_mps**2 * vertical_curvature / context.gravity_mps2
        )
        normal_scale = min(
            self.maximum_normal_load_scale,
            max(self.minimum_normal_load_scale, raw_normal_scale),
        )
        loss_shape_1_per_m = (1.0 - cos(phase)) / self.length_m
        loss_energy_j = self.fixed_energy_loss_j + (
            self.impact_loss_coefficient_kg * context.vehicle_speed_mps**2
        )
        return FeatureEffect(
            elevation_offset_m=elevation,
            grade_slope_addition=slope,
            additional_resistance_force_n=loss_energy_j * loss_shape_1_per_m,
            normal_load_scale=normal_scale,
            friction_multiplier=self.traction_multiplier,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type_name,
            "name": self.name,
            "start_m": self.start_m,
            "length_m": self.length_m,
            "vertical_amplitude_m": self.vertical_amplitude_m,
            "profile_kind": self.profile_kind,
            "fixed_energy_loss_j": self.fixed_energy_loss_j,
            "impact_loss_coefficient_kg": self.impact_loss_coefficient_kg,
            "traction_multiplier": self.traction_multiplier,
            "minimum_normal_load_scale": self.minimum_normal_load_scale,
            "maximum_normal_load_scale": self.maximum_normal_load_scale,
        }
