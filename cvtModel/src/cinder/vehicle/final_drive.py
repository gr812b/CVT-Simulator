"""Fixed secondary-shaft to wheel reduction and inertia reflection."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class FixedFinalDrive:
    """
    Fixed secondary-shaft to wheel reduction.

    ``reduction_ratio`` is defined as:

        G = omega_secondary / omega_wheel
    """

    reduction_ratio: float
    wheel_radius: float

    def __post_init__(self) -> None:
        if (
            not isfinite(self.reduction_ratio)
            or self.reduction_ratio <= 0.0
        ):
            raise ValueError(
                "reduction_ratio must be finite and positive."
            )

        if not isfinite(self.wheel_radius) or self.wheel_radius <= 0.0:
            raise ValueError("wheel_radius must be finite and positive.")

    def wheel_angular_speed(
        self,
        *,
        secondary_angular_speed: float,
    ) -> float:
        """Return wheel angular speed from secondary shaft speed."""

        _require_finite(
            "secondary_angular_speed",
            secondary_angular_speed,
        )
        return secondary_angular_speed / self.reduction_ratio

    def vehicle_speed(
        self,
        *,
        secondary_angular_speed: float,
    ) -> float:
        """Return signed vehicle speed v = r_w omega_secondary / G."""

        return self.wheel_radius * self.wheel_angular_speed(
            secondary_angular_speed=secondary_angular_speed,
        )

    def secondary_torque_from_wheel_force(
        self,
        *,
        wheel_force: float,
    ) -> float:
        """Map signed longitudinal wheel force to secondary torque."""

        _require_finite("wheel_force", wheel_force)
        return wheel_force * self.wheel_radius / self.reduction_ratio

    def secondary_inertia_from_vehicle_mass(
        self,
        *,
        vehicle_mass: float,
    ) -> float:
        """
        Reflect vehicle translation to the secondary shaft.

            I_vehicle@secondary = m (r_w / G)^2.
        """

        _require_nonnegative("vehicle_mass", vehicle_mass)
        return vehicle_mass * (
            self.wheel_radius / self.reduction_ratio
        ) ** 2

    def secondary_inertia_from_wheel_rotation(
        self,
        *,
        wheel_rotational_inertia: float,
    ) -> float:
        """
        Reflect driven-wheel spin inertia to the secondary shaft.

            I_wheels@secondary = I_wheels / G^2.
        """

        _require_nonnegative(
            "wheel_rotational_inertia",
            wheel_rotational_inertia,
        )
        return (
            wheel_rotational_inertia
            / self.reduction_ratio**2
        )


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
