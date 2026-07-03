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

    The branch selector/event logic supplies ``direction``. This object does
    not decide whether an interface should slip; it only maps the selected
    kinematic direction to the signed lambda required by the present
    pulley-torque convention.

    Positive forward-drive variables mean:

        lambda_p > 0: primary pulley transfers traction to the belt;
        lambda_s > 0: belt transfers traction to the secondary pulley.

    Therefore the mapping from global relative motion is intentionally
    asymmetric:

        primary, pulley leads belt -> +mu_k;
        primary, belt leads pulley -> -mu_k;
        secondary, belt leads pulley -> +mu_k;
        secondary, pulley leads belt -> -mu_k.
    """

    interface: ContactInterface
    direction: SlipDirection
    kinetic_lambda_magnitude: float

    def __post_init__(self) -> None:
        if not isinstance(self.interface, ContactInterface):
            raise TypeError("interface must be a ContactInterface.")
        if self.direction is SlipDirection.INDETERMINATE:
            raise ValueError("A kinetic slip specification requires a direction.")
        if not isfinite(self.kinetic_lambda_magnitude) or self.kinetic_lambda_magnitude <= 0.0:
            raise ValueError("kinetic_lambda_magnitude must be finite and strictly positive.")

    @property
    def signed_lambda(self) -> float:
        """Return the fixed non-zero lambda imposed by this kinetic branch."""

        if self.interface is ContactInterface.PRIMARY:
            if self.direction is SlipDirection.PULLEY_LEADS_BELT:
                return self.kinetic_lambda_magnitude
            return -self.kinetic_lambda_magnitude

        if self.interface is ContactInterface.SECONDARY:
            if self.direction is SlipDirection.BELT_LEADS_PULLEY:
                return self.kinetic_lambda_magnitude
            return -self.kinetic_lambda_magnitude

        raise ValueError(f"Unsupported contact interface: {self.interface!r}.")

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
