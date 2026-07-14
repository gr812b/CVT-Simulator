from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi, radians, sin

from .core import FeatureEffect, TrackEvaluationContext


@dataclass(frozen=True, slots=True)
class RoughPatch:
    """Distributed rough ground, ruts, or rocks with deterministic load variation.

    Let ``xi = x - start``. The effective normal-load multiplier is

        k_N(x) = clip(1 + a_N sin(2 pi xi/lambda + phase), k_min, k_max).

    The unresolved longitudinal loss is represented as

        F_rough(x, v) = e_rough + k_v v^2,

    where ``e_rough`` has units J/m (equivalently N) and ``k_v`` has units
    kg/m. Surface friction and rolling resistance may also be overridden or
    multiplied. This captures the longitudinal consequence of rough terrain;
    it is not a suspension or individual-wheel model.
    """

    name: str
    start_m: float
    length_m: float
    roughness_wavelength_m: float
    normal_load_variation_fraction: float = 0.0
    phase_degrees: float = 0.0
    minimum_normal_load_scale: float = 0.05
    maximum_normal_load_scale: float = 2.0
    energy_loss_j_per_m: float = 0.0
    speed_squared_resistance_coefficient_kg_per_m: float = 0.0
    friction_coefficient: float | None = None
    rolling_resistance_coefficient: float | None = None
    friction_multiplier: float = 1.0
    rolling_resistance_multiplier: float = 1.0
    surface: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("rough patch name must be non-empty")
        if not isfinite(self.start_m) or self.start_m < 0.0:
            raise ValueError("start_m must be finite and non-negative")
        if not isfinite(self.length_m) or self.length_m <= 0.0:
            raise ValueError("length_m must be positive and finite")
        if (
            not isfinite(self.roughness_wavelength_m)
            or self.roughness_wavelength_m <= 0.0
        ):
            raise ValueError("roughness_wavelength_m must be positive and finite")
        if (
            not isfinite(self.normal_load_variation_fraction)
            or self.normal_load_variation_fraction < 0.0
        ):
            raise ValueError("normal_load_variation_fraction must be non-negative")
        if not isfinite(self.phase_degrees):
            raise ValueError("phase_degrees must be finite")
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
        for field_name, value in (
            ("energy_loss_j_per_m", self.energy_loss_j_per_m),
            (
                "speed_squared_resistance_coefficient_kg_per_m",
                self.speed_squared_resistance_coefficient_kg_per_m,
            ),
            ("friction_multiplier", self.friction_multiplier),
            ("rolling_resistance_multiplier", self.rolling_resistance_multiplier),
        ):
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{field_name} must be finite and non-negative")
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

    @property
    def type_name(self) -> str:
        return "rough_patch"

    @property
    def end_m(self) -> float:
        return self.start_m + self.length_m

    def is_active(self, distance_m: float) -> bool:
        return self.start_m <= distance_m < self.end_m

    def evaluate(self, context: TrackEvaluationContext) -> FeatureEffect:
        if not self.is_active(context.distance_m):
            return FeatureEffect()
        local = context.distance_m - self.start_m
        phase = 2.0 * pi * local / self.roughness_wavelength_m + radians(
            self.phase_degrees
        )
        raw_normal_scale = 1.0 + self.normal_load_variation_fraction * sin(phase)
        normal_scale = min(
            self.maximum_normal_load_scale,
            max(self.minimum_normal_load_scale, raw_normal_scale),
        )
        resistance_force = self.energy_loss_j_per_m + (
            self.speed_squared_resistance_coefficient_kg_per_m
            * context.vehicle_speed_mps**2
        )
        return FeatureEffect(
            friction_coefficient_override=self.friction_coefficient,
            friction_multiplier=self.friction_multiplier,
            rolling_resistance_override=self.rolling_resistance_coefficient,
            rolling_resistance_multiplier=self.rolling_resistance_multiplier,
            additional_resistance_force_n=resistance_force,
            normal_load_scale=normal_scale,
            surface_override=self.surface,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type_name,
            "name": self.name,
            "start_m": self.start_m,
            "length_m": self.length_m,
            "roughness_wavelength_m": self.roughness_wavelength_m,
            "normal_load_variation_fraction": self.normal_load_variation_fraction,
            "phase_degrees": self.phase_degrees,
            "minimum_normal_load_scale": self.minimum_normal_load_scale,
            "maximum_normal_load_scale": self.maximum_normal_load_scale,
            "energy_loss_j_per_m": self.energy_loss_j_per_m,
            "speed_squared_resistance_coefficient_kg_per_m": (
                self.speed_squared_resistance_coefficient_kg_per_m
            ),
            "friction_coefficient": self.friction_coefficient,
            "rolling_resistance_coefficient": self.rolling_resistance_coefficient,
            "friction_multiplier": self.friction_multiplier,
            "rolling_resistance_multiplier": self.rolling_resistance_multiplier,
            "surface": self.surface,
        }
