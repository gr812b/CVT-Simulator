"""Integrated state and trial-contact inputs for CINDER dynamics."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class CVTDynamicState:
    """
    The six integrated CINDER states.

    The state is ordered conceptually as:

        [omega_p, omega_s, v_b, s, s_dot, psi_s].

    ``secondary_shaft_angle = psi_s`` is accumulated secondary-shaft rotation,
    not the secondary pulley axial coordinate ``x_s``. Its derivative is known
    directly from the state:

        psi_s_dot = omega_s.

    It is included so position-dependent external environment models, such as a
    road-grade profile, can be evaluated without introducing a vehicle-side
    coordinate into the CVT mechanics. It is not an unknown in the six-by-six
    instantaneous closure solve, just as ``shift_speed`` is not an unknown.
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
class TrialFrictionUtilization:
    """
    One trial pair of dimensionless wrap-friction utilizations.

    These values are outer closure variables, not ODE states and not entries in
    the six-column linear unknown vector. The later stick root solve will vary
    them until the two local no-slip residuals vanish.

    No static- or kinetic-friction bound is imposed here. Branch-specific
    contact logic owns those admissibility checks.
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
