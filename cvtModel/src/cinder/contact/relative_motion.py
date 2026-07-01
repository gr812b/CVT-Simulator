"""Shared belt--pulley relative-motion definitions for all contact regimes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from cinder.closure import ClosureUnknowns
    from cinder.dynamics.state import CVTDynamicState
    from cinder.geometry import GeometryPosition

from .tolerances import ContactKinematicTolerances


class ContactInterface(str, Enum):
    """The two belt--pulley interfaces."""

    PRIMARY = "primary"
    SECONDARY = "secondary"


class SlipDirection(str, Enum):
    """Kinematic direction of belt motion relative to a pulley surface.

    The direction is always stated in the global positive belt-travel
    direction through ``v_rel = v_b - r omega``.  It deliberately is *not*
    a kinetic-friction torque sign: converting this kinematic fact into a
    primary or secondary friction torque belongs in the later branch-specific
    traction law, where the pulley action--reaction convention is explicit.
    """

    BELT_LEADS_PULLEY = "belt_leads_pulley"
    PULLEY_LEADS_BELT = "pulley_leads_belt"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class ContactRelativeMotion:
    """Velocity- and acceleration-level belt--pulley compatibility data.

    For either interface ``j``:

    The shared definitions are ``v_rel,j = v_b - r_j omega_j`` and
    ``a_rel,j = v_b_dot - r_j omega_j_dot - r_j_prime s_dot omega_j``.

    A sticking interface imposes ``a_rel,j = 0``.  A slipping interface does
    *not* impose that acceleration constraint; instead ``v_rel,j`` supplies
    the slip direction used by its future kinetic-traction closure.  When
    relative speed is within tolerance, ``a_rel,j`` gives only an incipient
    direction hint for event/transition logic.
    """

    primary_relative_speed: float
    secondary_relative_speed: float
    primary_relative_acceleration: float
    secondary_relative_acceleration: float

    def __post_init__(self) -> None:
        for name, value in (
            ("primary_relative_speed", self.primary_relative_speed),
            ("secondary_relative_speed", self.secondary_relative_speed),
            (
                "primary_relative_acceleration",
                self.primary_relative_acceleration,
            ),
            (
                "secondary_relative_acceleration",
                self.secondary_relative_acceleration,
            ),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")

    @property
    def primary(self) -> float:
        """Compatibility alias: primary acceleration-level stick residual."""

        return self.primary_relative_acceleration

    @property
    def secondary(self) -> float:
        """Compatibility alias: secondary acceleration-level stick residual."""

        return self.secondary_relative_acceleration

    @property
    def acceleration_vector(self) -> NDArray[np.float64]:
        """Return ``[a_rel,p, a_rel,s]`` in primary, secondary order."""

        values = np.array(
            (
                self.primary_relative_acceleration,
                self.secondary_relative_acceleration,
            ),
            dtype=float,
        )
        values.setflags(write=False)
        return values

    @property
    def vector(self) -> NDArray[np.float64]:
        """Compatibility alias for the two acceleration-level stick residuals."""

        return self.acceleration_vector

    @property
    def acceleration_norm(self) -> float:
        """Return ``||(a_rel,p, a_rel,s)||_2`` in m/s^2."""

        return float(np.linalg.norm(self.acceleration_vector, ord=2))

    @property
    def norm(self) -> float:
        """Compatibility alias for :attr:`acceleration_norm`."""

        return self.acceleration_norm

    def relative_speed_at(self, interface: ContactInterface) -> float:
        """Return ``v_rel`` at one interface."""

        if interface is ContactInterface.PRIMARY:
            return self.primary_relative_speed
        if interface is ContactInterface.SECONDARY:
            return self.secondary_relative_speed
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def relative_acceleration_at(self, interface: ContactInterface) -> float:
        """Return ``a_rel`` at one interface."""

        if interface is ContactInterface.PRIMARY:
            return self.primary_relative_acceleration
        if interface is ContactInterface.SECONDARY:
            return self.secondary_relative_acceleration
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def slip_direction_at(
        self,
        interface: ContactInterface,
        *,
        tolerances: ContactKinematicTolerances,
    ) -> SlipDirection:
        """Classify established or incipient slip at one interface.

        Relative speed decides the direction whenever it is outside the speed
        tolerance.  At numerically zero speed, relative acceleration is used
        only as an incipient-direction hint.  Exact transition policy and
        hysteresis remain the future regime selector's responsibility.
        """

        return infer_slip_direction(
            relative_speed=self.relative_speed_at(interface),
            relative_acceleration=self.relative_acceleration_at(interface),
            tolerances=tolerances,
        )

    def is_stick_compatible(
        self,
        *,
        tolerances: ContactKinematicTolerances,
    ) -> bool:
        """Return whether both acceleration-level stick residuals are small."""

        return self.acceleration_norm <= tolerances.stick_acceleration_norm_tolerance


def evaluate_contact_relative_motion(
    *,
    state: "CVTDynamicState",
    geometry: "GeometryPosition",
    unknowns: "ClosureUnknowns",
) -> ContactRelativeMotion:
    """Evaluate the shared contact kinematics for one closure solution."""

    primary = geometry.primary
    secondary = geometry.secondary

    return ContactRelativeMotion(
        primary_relative_speed=(
            state.belt_speed - primary.effective * state.primary_angular_speed
        ),
        secondary_relative_speed=(
            state.belt_speed - secondary.effective * state.secondary_angular_speed
        ),
        primary_relative_acceleration=(
            unknowns.belt_acceleration
            - primary.effective * unknowns.primary_angular_acceleration
            - primary.d_effective_ds
            * state.shift_speed
            * state.primary_angular_speed
        ),
        secondary_relative_acceleration=(
            unknowns.belt_acceleration
            - secondary.effective * unknowns.secondary_angular_acceleration
            - secondary.d_effective_ds
            * state.shift_speed
            * state.secondary_angular_speed
        ),
    )


def infer_slip_direction(
    *,
    relative_speed: float,
    relative_acceleration: float,
    tolerances: ContactKinematicTolerances,
) -> SlipDirection:
    """Infer belt-versus-pulley slip direction from relative motion.

    This function intentionally returns ``INDETERMINATE`` around a genuinely
    stationary, non-accelerating contact.  That is not an error: such a point
    is exactly where a later event/hysteresis policy must decide whether an
    existing slip branch re-sticks or persists.
    """

    if relative_speed > tolerances.relative_speed_tolerance:
        return SlipDirection.BELT_LEADS_PULLEY
    if relative_speed < -tolerances.relative_speed_tolerance:
        return SlipDirection.PULLEY_LEADS_BELT

    if relative_acceleration > tolerances.relative_acceleration_tolerance:
        return SlipDirection.BELT_LEADS_PULLEY
    if relative_acceleration < -tolerances.relative_acceleration_tolerance:
        return SlipDirection.PULLEY_LEADS_BELT
    return SlipDirection.INDETERMINATE
