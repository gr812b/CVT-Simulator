"""Continuous CINDER ODE state and its aligned time derivative."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import ArrayLike, NDArray

if TYPE_CHECKING:
    from cinder.closure import ClosureUnknowns

_STATE_SIZE = 6


@dataclass(frozen=True, slots=True)
class CVTDynamicState:
    """The six integrated CINDER states in conceptual order.

    ``[omega_p, omega_s, v_b, s, s_dot, psi_s]``.

    ``secondary_shaft_angle = psi_s`` accumulates secondary-shaft rotation for
    road-profile lookup. It is a continuous ODE state, not a closure unknown.
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

    def as_vector(self) -> NDArray[np.float64]:
        """Return the immutable solve_ivp-compatible state vector."""

        values = np.asarray(
            (
                self.primary_angular_speed,
                self.secondary_angular_speed,
                self.belt_speed,
                self.shift_position,
                self.shift_speed,
                self.secondary_shaft_angle,
            ),
            dtype=float,
        )
        values.setflags(write=False)
        return values

    @classmethod
    def from_vector(cls, values: ArrayLike) -> "CVTDynamicState":
        """Reconstruct the named state from one six-entry ODE vector."""

        vector = _coerce_vector(values=values, name="CVTDynamicState")
        return cls(
            primary_angular_speed=float(vector[0]),
            secondary_angular_speed=float(vector[1]),
            belt_speed=float(vector[2]),
            shift_position=float(vector[3]),
            shift_speed=float(vector[4]),
            secondary_shaft_angle=float(vector[5]),
        )


@dataclass(frozen=True, slots=True)
class CVTDynamicStateDerivative:
    """Time derivative aligned with :class:`CVTDynamicState`.

    ``shift_position_rate`` and ``secondary_shaft_angle_rate`` are direct
    kinematic derivatives from the integrated state. The remaining entries
    come from the active engaged-contact closure.
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

    def as_vector(self) -> NDArray[np.float64]:
        """Return the immutable solve_ivp-compatible derivative vector."""

        values = np.asarray(
            (
                self.primary_angular_acceleration,
                self.secondary_angular_acceleration,
                self.belt_acceleration,
                self.shift_position_rate,
                self.shift_acceleration,
                self.secondary_shaft_angle_rate,
            ),
            dtype=float,
        )
        values.setflags(write=False)
        return values

    @classmethod
    def from_engaged_closure(
        cls,
        *,
        state: CVTDynamicState,
        unknowns: "ClosureUnknowns",
    ) -> "CVTDynamicStateDerivative":
        """Convert one engaged closure solution into ODE derivatives."""

        return cls(
            primary_angular_acceleration=unknowns.primary_angular_acceleration,
            secondary_angular_acceleration=unknowns.secondary_angular_acceleration,
            belt_acceleration=unknowns.belt_acceleration,
            shift_position_rate=state.shift_speed,
            shift_acceleration=unknowns.shift_acceleration,
            secondary_shaft_angle_rate=state.secondary_angular_speed,
        )

    @classmethod
    def from_fixed_engaged_shift_constraint_closure(
        cls,
        *,
        state: CVTDynamicState,
        unknowns: "ClosureUnknowns",
    ) -> "CVTDynamicStateDerivative":
        """Convert an engaged fixed-shift closure into ODE derivatives.

        Both the low-ratio seat and high-ratio stop enforce ``s_ddot = 0`` in
        the closure.  This factory also sets ``s_dot = 0`` explicitly so a
        constrained segment cannot inherit a tiny nonzero shift velocity from
        numerical stage arithmetic.  The event transition still projects the
        state itself to zero axial speed before this RHS is entered.
        """

        return cls(
            primary_angular_acceleration=unknowns.primary_angular_acceleration,
            secondary_angular_acceleration=unknowns.secondary_angular_acceleration,
            belt_acceleration=unknowns.belt_acceleration,
            shift_position_rate=0.0,
            shift_acceleration=0.0,
            secondary_shaft_angle_rate=state.secondary_angular_speed,
        )

    @classmethod
    def from_vector(cls, values: ArrayLike) -> "CVTDynamicStateDerivative":
        """Reconstruct the named derivative from one six-entry ODE vector."""

        vector = _coerce_vector(values=values, name="CVTDynamicStateDerivative")
        return cls(
            primary_angular_acceleration=float(vector[0]),
            secondary_angular_acceleration=float(vector[1]),
            belt_acceleration=float(vector[2]),
            shift_position_rate=float(vector[3]),
            shift_acceleration=float(vector[4]),
            secondary_shaft_angle_rate=float(vector[5]),
        )


def _coerce_vector(*, values: ArrayLike, name: str) -> NDArray[np.float64]:
    vector = np.asarray(values, dtype=float)
    if vector.ndim != 1 or vector.size != _STATE_SIZE:
        raise ValueError(f"{name} vector must contain exactly {_STATE_SIZE} entries.")
    if not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} vector entries must be finite.")
    return vector


def _require_finite(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value):
            raise ValueError(f"{name} must be finite.")
