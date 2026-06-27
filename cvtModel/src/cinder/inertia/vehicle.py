"""Vehicle-side physical inertia data."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class VehicleInertia:
    """
    Vehicle mass and driven-wheel spin inertia.

    ``wheel_rotational_inertia`` is the combined inertia of all driven wheels,
    expressed about their wheel axes. ``mass`` is also the one shared vehicle
    mass used by road load for grade and rolling resistance.
    """

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
