"""Servo-like shaft boundaries that track commanded speed histories."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from cinder.model.reference import PiecewiseLinearReference
from cinder.model.system.ports import ShaftBoundaryValue


class _ShaftContext(Protocol):
    time: float

    @property
    def shaft_speed(self) -> float: ...


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


@dataclass(frozen=True, slots=True)
class SpeedTrackingShaftBoundary:
    """Torque-limited proportional shaft-speed tracking boundary.

    This is intentionally *not* an exact prescribed-speed constraint.  The
    boundary applies actuator torque to the normal shaft dynamics, allowing the
    achieved speed to differ from the reference when gain or torque authority is
    insufficient.  That makes it suitable for dynamometers, motors, and
    experimental replay while preserving CINDER's force/torque-driven plant.
    """

    speed_reference: PiecewiseLinearReference
    proportional_gain: float
    torque_limit: float
    equivalent_inertia: float = 0.0
    feedforward_inertia: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.speed_reference, PiecewiseLinearReference):
            raise TypeError("speed_reference must be a PiecewiseLinearReference.")
        if not isfinite(self.proportional_gain) or self.proportional_gain <= 0.0:
            raise ValueError("proportional_gain must be positive and finite.")
        if not isfinite(self.torque_limit) or self.torque_limit <= 0.0:
            raise ValueError("torque_limit must be positive and finite.")
        for name, value in (
            ("equivalent_inertia", self.equivalent_inertia),
            ("feedforward_inertia", self.feedforward_inertia),
        ):
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")

    def evaluate(self, context: _ShaftContext) -> ShaftBoundaryValue:
        target_speed = self.speed_reference.value_at(context.time)
        target_acceleration = self.speed_reference.slope_at(context.time)
        error = target_speed - context.shaft_speed
        unsaturated = (
            self.proportional_gain * error
            + self.feedforward_inertia * target_acceleration
        )
        torque = _clamp(unsaturated, self.torque_limit)
        return ShaftBoundaryValue(
            external_torque=torque,
            equivalent_inertia=self.equivalent_inertia,
            metadata={
                "target_speed": target_speed,
                "target_acceleration": target_acceleration,
                "tracking_error": error,
                "actuator_torque": torque,
                "actuator_saturated": torque != unsaturated,
            },
        )
