# cinder/vehicle/final_drive.py

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class FixedFinalDrive:
    """
    Fixed secondary-shaft to wheel reduction.

    ``reduction_ratio`` is defined as:

        G = omega_secondary / omega_wheel

    and must therefore be positive.
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
            raise ValueError(
                "wheel_radius must be finite and positive."
            )

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
        """
        Return signed vehicle speed.

            v = r_w omega_secondary / G
        """

        return self.wheel_radius * self.wheel_angular_speed(
            secondary_angular_speed=secondary_angular_speed,
        )

    def secondary_torque_from_wheel_force(
        self,
        *,
        wheel_force: float,
    ) -> float:
        """
        Map signed longitudinal wheel force to signed secondary torque.

            tau_secondary = F_wheel r_w / G

        Positive force is forward on the vehicle and therefore applies
        positive torque to the secondary shaft.
        """

        _require_finite("wheel_force", wheel_force)

        return wheel_force * self.wheel_radius / self.reduction_ratio


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")
