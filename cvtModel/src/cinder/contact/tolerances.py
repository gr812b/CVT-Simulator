"""Shared kinematic tolerances for contact closure and regime transitions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class ContactKinematicTolerances:
    """Numerical thresholds shared by stick and slip contact logic.

    These are kinematic decision tolerances, not friction limits and not a
    hysteresis policy.  The future regime selector may add separate entry and
    exit hysteresis around them, but every branch should use the same
    definitions of "near-zero relative speed" and "stick-compatible
    acceleration residual".

    Units:
        ``relative_speed_tolerance``
            m/s;
        ``relative_acceleration_tolerance``
            m/s^2, used only to infer an incipient slip direction when the
            relative speed is numerically zero;
        ``stick_acceleration_norm_tolerance``
            m/s^2, applied to the Euclidean norm of the two stick residuals.
    """

    relative_speed_tolerance: float = 1.0e-7
    relative_acceleration_tolerance: float = 1.0e-8
    stick_acceleration_norm_tolerance: float = 1.0e-8

    def __post_init__(self) -> None:
        for name, value in (
            ("relative_speed_tolerance", self.relative_speed_tolerance),
            (
                "relative_acceleration_tolerance",
                self.relative_acceleration_tolerance,
            ),
            (
                "stick_acceleration_norm_tolerance",
                self.stick_acceleration_norm_tolerance,
            ),
        ):
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and strictly positive.")
