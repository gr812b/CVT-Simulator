"""Servo-like shaft boundaries that track commanded speed histories."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite
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

    This is intentionally *not* an exact prescribed-speed constraint. The
    boundary applies actuator torque to the normal shaft dynamics, allowing the
    achieved speed to differ from the reference when actuator authority is
    insufficient. That makes it suitable for dynamometers, motors, and
    experimental replay while preserving CINDER's force/torque-driven plant.

    ``proportional_gain`` is always the resolved controller gain used by the
    plant. For ordinary use, prefer :meth:`auto_tuned` or
    :meth:`from_tracking_error_budget` rather than choosing that gain directly.
    Those helpers use the configured torque authority to make the controller a
    predictable best-effort tracker while keeping the controller stateless.
    """

    speed_reference: PiecewiseLinearReference
    proportional_gain: float
    torque_limit: float
    equivalent_inertia: float = 0.0
    feedforward_inertia: float = 0.0
    tracking_error_budget: float | None = None
    feedback_authority_fraction: float | None = None

    DEFAULT_RELATIVE_ERROR_FRACTION = 0.01
    DEFAULT_MINIMUM_ERROR_BUDGET_RAD_PER_S = 0.5
    DEFAULT_FEEDBACK_AUTHORITY_FRACTION = 0.85

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

        if self.tracking_error_budget is None:
            if self.feedback_authority_fraction is not None:
                raise ValueError(
                    "feedback_authority_fraction requires tracking_error_budget."
                )
            return

        if (
            not isfinite(self.tracking_error_budget)
            or self.tracking_error_budget <= 0.0
        ):
            raise ValueError("tracking_error_budget must be positive and finite.")
        if self.feedback_authority_fraction is None or (
            not isfinite(self.feedback_authority_fraction)
            or not 0.0 < self.feedback_authority_fraction <= 1.0
        ):
            raise ValueError(
                "feedback_authority_fraction must be in (0, 1] when an error budget is supplied."
            )
        expected_gain = (
            self.feedback_authority_fraction
            * self.torque_limit
            / self.tracking_error_budget
        )
        if not isclose(
            self.proportional_gain,
            expected_gain,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ):
            raise ValueError(
                "proportional_gain is inconsistent with the supplied tracking-error budget."
            )

    @classmethod
    def from_tracking_error_budget(
        cls,
        *,
        speed_reference: PiecewiseLinearReference,
        torque_limit: float,
        tracking_error_budget: float,
        equivalent_inertia: float = 0.0,
        feedforward_inertia: float | None = None,
        feedback_authority_fraction: float = DEFAULT_FEEDBACK_AUTHORITY_FRACTION,
    ) -> "SpeedTrackingShaftBoundary":
        """Build a best-effort tracker from actuator authority and an error budget.

        At an error equal to ``tracking_error_budget``, the proportional term
        requests ``feedback_authority_fraction * torque_limit``. Larger errors
        therefore approach saturation quickly, while small errors retain a
        smooth proportional response.

        If ``feedforward_inertia`` is omitted, the boundary's own referred
        inertia is used. This compensates the acceleration of hardware explicitly
        owned by the boundary without pretending to know the rest of the CVT's
        configuration-dependent effective inertia.
        """

        if not isfinite(tracking_error_budget) or tracking_error_budget <= 0.0:
            raise ValueError("tracking_error_budget must be positive and finite.")
        if (
            not isfinite(feedback_authority_fraction)
            or not 0.0 < feedback_authority_fraction <= 1.0
        ):
            raise ValueError("feedback_authority_fraction must be in (0, 1].")
        if not isfinite(torque_limit) or torque_limit <= 0.0:
            raise ValueError("torque_limit must be positive and finite.")
        if not isfinite(equivalent_inertia) or equivalent_inertia < 0.0:
            raise ValueError("equivalent_inertia must be finite and non-negative.")
        resolved_feedforward = (
            equivalent_inertia
            if feedforward_inertia is None
            else float(feedforward_inertia)
        )
        gain = feedback_authority_fraction * torque_limit / tracking_error_budget
        return cls(
            speed_reference=speed_reference,
            proportional_gain=gain,
            torque_limit=torque_limit,
            equivalent_inertia=equivalent_inertia,
            feedforward_inertia=resolved_feedforward,
            tracking_error_budget=tracking_error_budget,
            feedback_authority_fraction=feedback_authority_fraction,
        )

    @classmethod
    def auto_tuned(
        cls,
        *,
        speed_reference: PiecewiseLinearReference,
        torque_limit: float,
        equivalent_inertia: float = 0.0,
        feedforward_inertia: float | None = None,
        relative_error_fraction: float = DEFAULT_RELATIVE_ERROR_FRACTION,
        minimum_error_budget_rad_per_s: float = DEFAULT_MINIMUM_ERROR_BUDGET_RAD_PER_S,
        feedback_authority_fraction: float = DEFAULT_FEEDBACK_AUTHORITY_FRACTION,
    ) -> "SpeedTrackingShaftBoundary":
        """Build a deterministic best-effort tracker with no hand-picked gain.

        The default error budget is one percent of the largest commanded speed,
        with a 0.5 rad/s floor. This is deliberately simple and scale-aware: it
        avoids a universal magic gain while still making an uploaded RPM trace
        usable without controller tuning in the common case.

        The resolved gain and error budget live on the returned object, so a
        serialized/frozen run remains completely reproducible.
        """

        if not isfinite(relative_error_fraction) or relative_error_fraction <= 0.0:
            raise ValueError("relative_error_fraction must be positive and finite.")
        if (
            not isfinite(minimum_error_budget_rad_per_s)
            or minimum_error_budget_rad_per_s <= 0.0
        ):
            raise ValueError(
                "minimum_error_budget_rad_per_s must be positive and finite."
            )
        characteristic_speed = max(abs(point.value) for point in speed_reference.points)
        error_budget = max(
            minimum_error_budget_rad_per_s,
            relative_error_fraction * characteristic_speed,
        )
        return cls.from_tracking_error_budget(
            speed_reference=speed_reference,
            torque_limit=torque_limit,
            tracking_error_budget=error_budget,
            equivalent_inertia=equivalent_inertia,
            feedforward_inertia=feedforward_inertia,
            feedback_authority_fraction=feedback_authority_fraction,
        )

    def evaluate(self, context: _ShaftContext) -> ShaftBoundaryValue:
        target_speed = self.speed_reference.value_at(context.time)
        target_acceleration = self.speed_reference.slope_at(context.time)
        error = target_speed - context.shaft_speed
        feedback_torque = self.proportional_gain * error
        feedforward_torque = self.feedforward_inertia * target_acceleration
        unsaturated = feedback_torque + feedforward_torque
        torque = _clamp(unsaturated, self.torque_limit)
        return ShaftBoundaryValue(
            external_torque=torque,
            equivalent_inertia=self.equivalent_inertia,
            metadata={
                "target_speed": target_speed,
                "target_acceleration": target_acceleration,
                "tracking_error": error,
                "proportional_gain": self.proportional_gain,
                "tracking_error_budget": self.tracking_error_budget,
                "feedback_authority_fraction": self.feedback_authority_fraction,
                "feedback_torque": feedback_torque,
                "feedforward_torque": feedforward_torque,
                "actuator_torque": torque,
                "actuator_saturated": not isclose(
                    torque, unsaturated, rel_tol=0.0, abs_tol=1.0e-15
                ),
            },
        )
