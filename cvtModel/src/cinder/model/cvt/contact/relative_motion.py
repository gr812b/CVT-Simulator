"""Shared belt--pulley relative-motion definitions for every contact mode."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import TYPE_CHECKING, Iterable

import numpy as np
from numpy.typing import NDArray

from .tolerances import ContactKinematicTolerances

if TYPE_CHECKING:
    from cinder.model.cvt.closure import ClosureUnknowns
    from cinder.model.system.state import CVTState
    from cinder.model.cvt.geometry import GeometryPosition


class ContactInterface(str, Enum):
    """The two belt--pulley contact interfaces."""

    PRIMARY = "primary"
    SECONDARY = "secondary"


class SlipDirection(str, Enum):
    """Direction of belt motion relative to a pulley surface.

    The direction is stated in the global positive belt-travel direction using

        v_rel = v_b - r omega.

    It is deliberately a kinematic fact, not a friction-torque sign. The
    primary and secondary map the same kinematic direction to opposite
    action--reaction torque roles, which is handled by ``KineticSlipSpecification``.
    """

    BELT_LEADS_PULLEY = "belt_leads_pulley"
    PULLEY_LEADS_BELT = "pulley_leads_belt"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class ContactRelativeMotion:
    """Velocity- and acceleration-level relative motion at both interfaces.

    The stored values are calculated once from an already solved closure
    trial. Convenience methods merely read those four scalars; they do not
    re-evaluate geometry, actuation, the helix, or the linear system.

    For interface ``j``:

        v_rel,j = v_b - r_j omega_j,
        a_rel,j = v_b_dot - r_j omega_j_dot - r_j' s_dot omega_j.

    A sticking interface imposes ``a_rel,j = 0``. A slipping interface leaves
    that residual unconstrained and uses ``v_rel,j`` (or, at zero speed,
    ``a_rel,j``) for future direction and re-stick logic.
    """

    primary_relative_speed: float
    secondary_relative_speed: float
    primary_relative_acceleration: float
    secondary_relative_acceleration: float

    def __post_init__(self) -> None:
        for name, value in (
            ("primary_relative_speed", self.primary_relative_speed),
            ("secondary_relative_speed", self.secondary_relative_speed),
            ("primary_relative_acceleration", self.primary_relative_acceleration),
            ("secondary_relative_acceleration", self.secondary_relative_acceleration),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")

    def relative_speed_at(self, interface: ContactInterface) -> float:
        """Return the stored velocity-level relative motion at one interface."""

        if interface is ContactInterface.PRIMARY:
            return self.primary_relative_speed
        if interface is ContactInterface.SECONDARY:
            return self.secondary_relative_speed
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def relative_acceleration_at(self, interface: ContactInterface) -> float:
        """Return the stored acceleration-level compatibility residual."""

        if interface is ContactInterface.PRIMARY:
            return self.primary_relative_acceleration
        if interface is ContactInterface.SECONDARY:
            return self.secondary_relative_acceleration
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def acceleration_residual_vector(
        self,
        interfaces: Iterable[ContactInterface],
    ) -> NDArray[np.float64]:
        """Return stick residuals in the supplied interface order."""

        values = np.asarray(
            [self.relative_acceleration_at(interface) for interface in interfaces],
            dtype=float,
        )
        if values.ndim != 1 or values.size == 0:
            raise ValueError("interfaces must contain at least one contact interface.")
        values.setflags(write=False)
        return values

    @property
    def both_acceleration_residuals(self) -> NDArray[np.float64]:
        """Return ``[a_rel,p, a_rel,s]`` in canonical interface order."""

        return self.acceleration_residual_vector(
            (ContactInterface.PRIMARY, ContactInterface.SECONDARY)
        )

    def is_stick_compatible_at(
        self,
        interface: ContactInterface,
        *,
        tolerances: ContactKinematicTolerances,
    ) -> bool:
        """Return whether one contact satisfies its acceleration stick closure."""

        return (
            abs(self.relative_acceleration_at(interface))
            <= tolerances.stick_acceleration_tolerance
        )

    def are_stick_compatible(
        self,
        interfaces: Iterable[ContactInterface],
        *,
        tolerances: ContactKinematicTolerances,
    ) -> bool:
        """Return whether every supplied sticking interface is compatible."""

        ordered = tuple(interfaces)
        if not ordered:
            raise ValueError("interfaces must contain at least one contact interface.")
        return all(
            self.is_stick_compatible_at(interface, tolerances=tolerances)
            for interface in ordered
        )

    def slip_direction_at(
        self,
        interface: ContactInterface,
        *,
        tolerances: ContactKinematicTolerances,
    ) -> SlipDirection:
        """Classify established or incipient slip direction at one interface."""

        return infer_slip_direction(
            relative_speed=self.relative_speed_at(interface),
            relative_acceleration=self.relative_acceleration_at(interface),
            tolerances=tolerances,
        )


def evaluate_contact_relative_motion(
    *,
    state: "CVTState",
    geometry: "GeometryPosition",
    unknowns: "ClosureUnknowns",
) -> ContactRelativeMotion:
    """Evaluate all four shared contact-relative-motion scalars once."""

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
            - primary.d_effective_ds * state.shift_speed * state.primary_angular_speed
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
    """Infer established slip, or only an incipient direction at zero speed."""

    if relative_speed > tolerances.relative_speed_tolerance:
        return SlipDirection.BELT_LEADS_PULLEY
    if relative_speed < -tolerances.relative_speed_tolerance:
        return SlipDirection.PULLEY_LEADS_BELT
    if relative_acceleration > tolerances.relative_acceleration_tolerance:
        return SlipDirection.BELT_LEADS_PULLEY
    if relative_acceleration < -tolerances.relative_acceleration_tolerance:
        return SlipDirection.PULLEY_LEADS_BELT
    return SlipDirection.INDETERMINATE
