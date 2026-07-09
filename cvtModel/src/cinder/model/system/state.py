"""Core CVT ODE state and its aligned derivative.

The mechanical CVT plant integrates only the states that belong to the CVT
itself. Shaft angle, vehicle position, wheel speed, suspension states, and
controller states are host states layered around the plant by a composed
simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import ArrayLike, NDArray

if TYPE_CHECKING:
    from cinder.model.cvt.closure import ClosureUnknowns

_CVT_STATE_SIZE = 5


@dataclass(frozen=True, slots=True)
class CVTState:
    """The five integrated states owned by the mechanical CVT plant.

    ``[omega_p, omega_s, v_b, s, s_dot]``.

    The state intentionally stops at the secondary shaft speed. A simulation
    that needs secondary angle, vehicle position, tire slip, or suspension
    motion should add those as host states and pass their effects back to the
    CVT through shaft boundary values.
    """

    primary_angular_speed: float
    secondary_angular_speed: float
    belt_speed: float
    shift_position: float
    shift_speed: float

    def __post_init__(self) -> None:
        _require_finite(
            primary_angular_speed=self.primary_angular_speed,
            secondary_angular_speed=self.secondary_angular_speed,
            belt_speed=self.belt_speed,
            shift_position=self.shift_position,
            shift_speed=self.shift_speed,
        )

    def as_vector(self) -> NDArray[np.float64]:
        values = np.asarray(
            (
                self.primary_angular_speed,
                self.secondary_angular_speed,
                self.belt_speed,
                self.shift_position,
                self.shift_speed,
            ),
            dtype=float,
        )
        values.setflags(write=False)
        return values

    @classmethod
    def from_vector(cls, values: ArrayLike) -> "CVTState":
        vector = _coerce_vector(values=values, name="CVTState")
        return cls(
            primary_angular_speed=float(vector[0]),
            secondary_angular_speed=float(vector[1]),
            belt_speed=float(vector[2]),
            shift_position=float(vector[3]),
            shift_speed=float(vector[4]),
        )


@dataclass(frozen=True, slots=True)
class CVTStateDerivative:
    """Time derivative aligned with :class:`CVTState`."""

    primary_angular_acceleration: float
    secondary_angular_acceleration: float
    belt_acceleration: float
    shift_position_rate: float
    shift_acceleration: float

    def __post_init__(self) -> None:
        _require_finite(
            primary_angular_acceleration=self.primary_angular_acceleration,
            secondary_angular_acceleration=self.secondary_angular_acceleration,
            belt_acceleration=self.belt_acceleration,
            shift_position_rate=self.shift_position_rate,
            shift_acceleration=self.shift_acceleration,
        )

    def as_vector(self) -> NDArray[np.float64]:
        values = np.asarray(
            (
                self.primary_angular_acceleration,
                self.secondary_angular_acceleration,
                self.belt_acceleration,
                self.shift_position_rate,
                self.shift_acceleration,
            ),
            dtype=float,
        )
        values.setflags(write=False)
        return values

    @classmethod
    def from_engaged_closure(
        cls,
        *,
        state: CVTState,
        unknowns: "ClosureUnknowns",
    ) -> "CVTStateDerivative":
        return cls(
            primary_angular_acceleration=unknowns.primary_angular_acceleration,
            secondary_angular_acceleration=unknowns.secondary_angular_acceleration,
            belt_acceleration=unknowns.belt_acceleration,
            shift_position_rate=state.shift_speed,
            shift_acceleration=unknowns.shift_acceleration,
        )

    @classmethod
    def from_fixed_engaged_shift_constraint_closure(
        cls,
        *,
        state: CVTState,
        unknowns: "ClosureUnknowns",
    ) -> "CVTStateDerivative":
        """Convert an engaged fixed-shift closure into ODE derivatives."""

        return cls(
            primary_angular_acceleration=unknowns.primary_angular_acceleration,
            secondary_angular_acceleration=unknowns.secondary_angular_acceleration,
            belt_acceleration=unknowns.belt_acceleration,
            shift_position_rate=0.0,
            shift_acceleration=0.0,
        )

    @classmethod
    def from_vector(cls, values: ArrayLike) -> "CVTStateDerivative":
        vector = _coerce_vector(values=values, name="CVTStateDerivative")
        return cls(
            primary_angular_acceleration=float(vector[0]),
            secondary_angular_acceleration=float(vector[1]),
            belt_acceleration=float(vector[2]),
            shift_position_rate=float(vector[3]),
            shift_acceleration=float(vector[4]),
        )



def _coerce_vector(*, values: ArrayLike, name: str) -> NDArray[np.float64]:
    vector = np.asarray(values, dtype=float)
    if vector.ndim != 1 or vector.size != _CVT_STATE_SIZE:
        raise ValueError(f"{name} vector must contain exactly {_CVT_STATE_SIZE} entries.")
    if not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} vector entries must be finite.")
    return vector


def _require_finite(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value):
            raise ValueError(f"{name} must be finite.")
