"""Shared kinematic tolerances for belt--pulley contact closure."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class ContactKinematicTolerances:
    """Numerical thresholds shared by all engaged contact regimes.

    These values describe only how the model interprets *kinematic* contact
    compatibility. They are not friction coefficients and they are not a
    hysteresis policy. A later regime selector can add separate entry/exit
    hysteresis without redefining relative motion itself.

    Units:
        ``relative_speed_tolerance``
            m/s; established slip direction is read from relative speed beyond
            this threshold.
        ``relative_acceleration_tolerance``
            m/s²; used only as an incipient-slip hint when relative speed is
            numerically near zero.
        ``stick_acceleration_tolerance``
            m/s²; maximum absolute acceleration-level compatibility residual
            accepted at one interface that is declared sticking.
    """

    relative_speed_tolerance: float = 1.0e-7
    relative_acceleration_tolerance: float = 1.0e-8
    stick_acceleration_tolerance: float = 1.0e-8

    def __post_init__(self) -> None:
        for name, value in (
            ("relative_speed_tolerance", self.relative_speed_tolerance),
            (
                "relative_acceleration_tolerance",
                self.relative_acceleration_tolerance,
            ),
            ("stick_acceleration_tolerance", self.stick_acceleration_tolerance),
        ):
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and strictly positive.")
