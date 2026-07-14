from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class TrackEvaluationContext:
    """Dynamic context used when evaluating a static track at one position."""

    distance_m: float
    vehicle_speed_mps: float
    vehicle_mass_kg: float
    gravity_mps2: float

    def __post_init__(self) -> None:
        for name, value in (
            ("distance_m", self.distance_m),
            ("vehicle_speed_mps", self.vehicle_speed_mps),
            ("vehicle_mass_kg", self.vehicle_mass_kg),
            ("gravity_mps2", self.gravity_mps2),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.vehicle_speed_mps < 0.0:
            raise ValueError("vehicle_speed_mps must be non-negative")
        if self.vehicle_mass_kg <= 0.0:
            raise ValueError("vehicle_mass_kg must be positive")
        if self.gravity_mps2 <= 0.0:
            raise ValueError("gravity_mps2 must be positive")


@dataclass(frozen=True, slots=True)
class FeatureEffect:
    """One feature's contribution to the compiled one-dimensional track sample."""

    elevation_offset_m: float = 0.0
    grade_slope_addition: float = 0.0
    curvature_1_per_m: float = 0.0
    bank_angle_degrees: float = 0.0
    friction_coefficient_override: float | None = None
    friction_multiplier: float = 1.0
    rolling_resistance_override: float | None = None
    rolling_resistance_multiplier: float = 1.0
    additional_resistance_force_n: float = 0.0
    normal_load_scale: float = 1.0
    surface_override: str | None = None


@runtime_checkable
class TrackFeature(Protocol):
    name: str

    @property
    def type_name(self) -> str: ...

    @property
    def start_m(self) -> float: ...

    @property
    def end_m(self) -> float: ...

    def is_active(self, distance_m: float) -> bool: ...

    def evaluate(self, context: TrackEvaluationContext) -> FeatureEffect: ...

    def to_dict(self) -> dict[str, object]: ...
