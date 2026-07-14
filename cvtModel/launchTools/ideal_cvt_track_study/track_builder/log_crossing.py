from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, pi

from .core import FeatureEffect, TrackEvaluationContext


@dataclass(frozen=True, slots=True)
class LogCrossing:
    """Localized obstacle represented by required work distributed in space.

    The crossing energy is

        E_log = m g h f_lift + k_impact v^2.

    It is converted into a smooth force using a normalized raised-cosine shape

        psi(x) = [1 - cos(2 pi xi/L)] / L,
        integral_0^L psi dx = 1,
        F_log = E_log psi(x).

    The model therefore removes the requested energy without an instantaneous
    speed jump. ``traction_multiplier`` can model reduced grip on the log.
    """

    name: str
    position_m: float
    crossing_length_m: float
    height_m: float
    effective_lift_fraction: float = 0.35
    impact_loss_coefficient_kg: float = 0.0
    traction_multiplier: float = 1.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("log crossing name must be non-empty")
        if not isfinite(self.position_m) or self.position_m < 0.0:
            raise ValueError("position_m must be finite and non-negative")
        if not isfinite(self.crossing_length_m) or self.crossing_length_m <= 0.0:
            raise ValueError("crossing_length_m must be positive and finite")
        if not isfinite(self.height_m) or self.height_m < 0.0:
            raise ValueError("height_m must be finite and non-negative")
        if not 0.0 <= self.effective_lift_fraction <= 1.0:
            raise ValueError("effective_lift_fraction must lie in [0, 1]")
        if (
            not isfinite(self.impact_loss_coefficient_kg)
            or self.impact_loss_coefficient_kg < 0.0
        ):
            raise ValueError("impact_loss_coefficient_kg must be non-negative")
        if not isfinite(self.traction_multiplier) or self.traction_multiplier < 0.0:
            raise ValueError("traction_multiplier must be finite and non-negative")

    @property
    def type_name(self) -> str:
        return "log_crossing"

    @property
    def start_m(self) -> float:
        return self.position_m - 0.5 * self.crossing_length_m

    @property
    def end_m(self) -> float:
        return self.position_m + 0.5 * self.crossing_length_m

    def is_active(self, distance_m: float) -> bool:
        return self.start_m <= distance_m < self.end_m

    def evaluate(self, context: TrackEvaluationContext) -> FeatureEffect:
        if not self.is_active(context.distance_m):
            return FeatureEffect()
        xi = min(max(context.distance_m - self.start_m, 0.0), self.crossing_length_m)
        shape_1_per_m = (
            1.0 - cos(2.0 * pi * xi / self.crossing_length_m)
        ) / self.crossing_length_m
        lift_energy_j = (
            context.vehicle_mass_kg
            * context.gravity_mps2
            * self.height_m
            * self.effective_lift_fraction
        )
        impact_energy_j = (
            self.impact_loss_coefficient_kg * context.vehicle_speed_mps**2
        )
        return FeatureEffect(
            additional_resistance_force_n=(lift_energy_j + impact_energy_j)
            * shape_1_per_m,
            friction_multiplier=self.traction_multiplier,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type_name,
            "name": self.name,
            "position_m": self.position_m,
            "crossing_length_m": self.crossing_length_m,
            "height_m": self.height_m,
            "effective_lift_fraction": self.effective_lift_fraction,
            "impact_loss_coefficient_kg": self.impact_loss_coefficient_kg,
            "traction_multiplier": self.traction_multiplier,
        }
