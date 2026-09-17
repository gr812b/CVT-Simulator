"""Force-limited tracking actuator for pulley-local axial motion."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.model.cvt.closure import AffineClosureScalar
from cinder.model.reference import PiecewiseLinearReference

from ..types import ActuationContribution, PulleyActuationContext


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


@dataclass(frozen=True, slots=True)
class AxialMotionTrackingForceSpec:
    """A physical servo-like pulley actuator.

    The actuator can track position, speed, or both.  It contributes a bounded
    force to the ordinary axial force balance rather than kinematically fixing
    the shift coordinate.  This keeps the CVT plant dynamic and makes the
    required actuator force observable.
    """

    position_reference: PiecewiseLinearReference | None = None
    speed_reference: PiecewiseLinearReference | None = None
    position_gain: float = 0.0
    speed_gain: float = 0.0
    force_limit: float = float("inf")

    def __post_init__(self) -> None:
        if self.position_reference is None and self.speed_reference is None:
            raise ValueError("At least one axial tracking reference is required.")
        for name, value in (
            ("position_gain", self.position_gain),
            ("speed_gain", self.speed_gain),
        ):
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")
        if self.position_reference is not None and self.position_gain == 0.0:
            raise ValueError("position_gain must be positive when tracking position.")
        if self.speed_reference is not None and self.speed_gain == 0.0:
            raise ValueError("speed_gain must be positive when tracking speed.")
        if self.force_limit != float("inf") and (
            not isfinite(self.force_limit) or self.force_limit <= 0.0
        ):
            raise ValueError("force_limit must be positive or infinity.")


class AxialMotionTrackingForce:
    """Bounded PD/P pulley-local tracking force."""

    def __init__(self, spec: AxialMotionTrackingForceSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> AxialMotionTrackingForceSpec:
        return self._spec

    def evaluate(self, context: PulleyActuationContext) -> AffineClosureScalar:
        force = 0.0
        if self._spec.position_reference is not None:
            target_position = self._spec.position_reference.value_at(context.time)
            force += self._spec.position_gain * (
                target_position - context.axial_position
            )
        target_speed = None
        if self._spec.speed_reference is not None:
            target_speed = self._spec.speed_reference.value_at(context.time)
        elif self._spec.position_reference is not None and self._spec.speed_gain > 0.0:
            # A position trajectory already defines its own local velocity.
            # Use that slope by default so position-only documents can express
            # the ordinary PD law without duplicating a second reference trace.
            target_speed = self._spec.position_reference.slope_at(context.time)
        if target_speed is not None:
            force += self._spec.speed_gain * (target_speed - context.axial_speed)
        if self._spec.force_limit != float("inf"):
            force = _clamp(force, self._spec.force_limit)
        return AffineClosureScalar(bias=force)

    def inspect(
        self, context: PulleyActuationContext
    ) -> tuple[ActuationContribution, ...]:
        return (
            ActuationContribution(
                key="axial_motion_tracking",
                label="Axial motion tracking actuator",
                relation=self.evaluate(context),
            ),
        )
