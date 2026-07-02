"""Integrated CINDER state, state derivative, and trial lambda input."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cinder.closure import ClosureUnknowns


@dataclass(frozen=True, slots=True)
class CVTDynamicState:
    """The six integrated CINDER states in conceptual order.

        [omega_p, omega_s, v_b, s, s_dot, psi_s].

    ``secondary_shaft_angle = psi_s`` accumulates secondary-shaft rotation for
    road-profile lookup. It is not a closure unknown, just as ``shift_speed``
    is not; their derivatives are known after an engaged six-by-six solve.
    """

    primary_angular_speed: float
    secondary_angular_speed: float
    belt_speed: float
    shift_position: float
    shift_speed: float
    secondary_shaft_angle: float

    def __post_init__(self) -> None:
        _require_finite(
            primary_angular_speed=self.primary_angular_speed,
            secondary_angular_speed=self.secondary_angular_speed,
            belt_speed=self.belt_speed,
            shift_position=self.shift_position,
            shift_speed=self.shift_speed,
            secondary_shaft_angle=self.secondary_shaft_angle,
        )


@dataclass(frozen=True, slots=True)
class CVTDynamicStateDerivative:
    """Time derivative aligned with :class:`CVTDynamicState`.

    ``shift_position_rate`` and ``secondary_shaft_angle_rate`` are direct
    kinematic derivatives from the integrated state. All remaining entries
    come from the six-by-six closure solution.
    """

    primary_angular_acceleration: float
    secondary_angular_acceleration: float
    belt_acceleration: float
    shift_position_rate: float
    shift_acceleration: float
    secondary_shaft_angle_rate: float

    def __post_init__(self) -> None:
        _require_finite(
            primary_angular_acceleration=self.primary_angular_acceleration,
            secondary_angular_acceleration=self.secondary_angular_acceleration,
            belt_acceleration=self.belt_acceleration,
            shift_position_rate=self.shift_position_rate,
            shift_acceleration=self.shift_acceleration,
            secondary_shaft_angle_rate=self.secondary_shaft_angle_rate,
        )

    @classmethod
    def from_engaged_closure(
        cls,
        *,
        state: CVTDynamicState,
        unknowns: "ClosureUnknowns",
    ) -> "CVTDynamicStateDerivative":
        """Convert one engaged six-by-six solution into ODE derivatives."""

        return cls(
            primary_angular_acceleration=unknowns.primary_angular_acceleration,
            secondary_angular_acceleration=unknowns.secondary_angular_acceleration,
            belt_acceleration=unknowns.belt_acceleration,
            shift_position_rate=state.shift_speed,
            shift_acceleration=unknowns.shift_acceleration,
            secondary_shaft_angle_rate=state.secondary_angular_speed,
        )


@dataclass(frozen=True, slots=True)
class TrialFrictionUtilization:
    """One trial pair of signed outer wrap-friction utilizations.

    These values are not ODE states and are not six-by-six unknowns. Engaged
    branch logic either solves selected lambdas from stick residuals or fixes
    them to signed kinetic values in a slip branch.
    """

    primary_lambda: float
    secondary_lambda: float

    def __post_init__(self) -> None:
        _require_finite(
            primary_lambda=self.primary_lambda,
            secondary_lambda=self.secondary_lambda,
        )


def _require_finite(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value):
            raise ValueError(f"{name} must be finite.")
