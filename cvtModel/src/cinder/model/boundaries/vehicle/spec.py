"""Vehicle and road-load specifications used by shaft boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class VehicleInertia:
    """Vehicle mass and combined wheel spin inertia."""

    mass: float
    wheel_rotational_inertia: float = 0.0

    def __post_init__(self) -> None:
        if not isfinite(self.mass) or self.mass <= 0.0:
            raise ValueError("mass must be finite and positive.")
        if (
            not isfinite(self.wheel_rotational_inertia)
            or self.wheel_rotational_inertia < 0.0
        ):
            raise ValueError(
                "wheel_rotational_inertia must be finite and non-negative."
            )


@dataclass(frozen=True, slots=True)
class VehicleRoadLoadSpec:
    """Fixed non-inertial road-load parameters."""

    rolling_resistance_coefficient: float
    drag_coefficient: float
    frontal_area: float

    air_density: float = 1.225
    gravity: float = 9.80665
    rolling_speed_regularization: float = 0.01

    def __post_init__(self) -> None:
        _require_finite_nonnegative(
            "rolling_resistance_coefficient",
            self.rolling_resistance_coefficient,
        )
        _require_finite_nonnegative("drag_coefficient", self.drag_coefficient)
        _require_finite_nonnegative("frontal_area", self.frontal_area)
        _require_finite_positive("air_density", self.air_density)
        _require_finite_positive("gravity", self.gravity)
        _require_finite_positive(
            "rolling_speed_regularization",
            self.rolling_speed_regularization,
        )


def _require_finite_positive(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive.")


def _require_finite_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
