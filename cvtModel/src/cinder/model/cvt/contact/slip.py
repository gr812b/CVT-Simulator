"""Explicit kinetic-slip specifications for the engaged contact branches."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .relative_motion import (
    ContactInterface,
    ContactRelativeMotion,
    SlipDirection,
)
from .tolerances import ContactKinematicTolerances


@dataclass(frozen=True, slots=True)
class KineticSlipSpecification:
    """A known kinetic lambda magnitude at one slipping interface.

    The signed traction convention is identical on both pulleys:

        dF_t,j = lambda_j dN_j

    is the force exerted by pulley ``j`` on the belt in the positive belt-travel
    direction. Friction therefore always opposes ``v_rel = v_b - r_eff omega``:

        belt leads pulley   -> lambda = -mu_k,
        pulley leads belt   -> lambda = +mu_k.

    No primary/secondary sign exception is required.
    """

    interface: ContactInterface
    direction: SlipDirection
    kinetic_lambda_magnitude: float

    def __post_init__(self) -> None:
        if not isinstance(self.interface, ContactInterface):
            raise TypeError("interface must be a ContactInterface.")
        if self.direction is SlipDirection.INDETERMINATE:
            raise ValueError("A kinetic slip specification requires a direction.")
        if (
            not isfinite(self.kinetic_lambda_magnitude)
            or self.kinetic_lambda_magnitude <= 0.0
        ):
            raise ValueError(
                "kinetic_lambda_magnitude must be finite and strictly positive."
            )

    @property
    def signed_lambda(self) -> float:
        """Return the fixed non-zero lambda imposed by this kinetic branch."""

        if self.interface not in (ContactInterface.PRIMARY, ContactInterface.SECONDARY):
            raise ValueError(f"Unsupported contact interface: {self.interface!r}.")
        if self.direction is SlipDirection.PULLEY_LEADS_BELT:
            return self.kinetic_lambda_magnitude
        return -self.kinetic_lambda_magnitude

    def direction_is_consistent(
        self,
        relative_motion: ContactRelativeMotion,
        *,
        tolerances: ContactKinematicTolerances,
    ) -> bool:
        """Return whether solved relative motion agrees with branch direction.

        ``INDETERMINATE`` observed motion is retained as acceptable here. It is
        expected at an instantaneous stick-to-slip or re-stick boundary and is
        resolved later by event hysteresis rather than by rejecting an otherwise
        well-defined kinetic closure.
        """

        observed = relative_motion.slip_direction_at(
            self.interface,
            tolerances=tolerances,
        )
        return observed in (SlipDirection.INDETERMINATE, self.direction)
