"""Signed effective traction-utilization values for the two contacts."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .relative_motion import ContactInterface


@dataclass(frozen=True, slots=True)
class ContactTractionUtilization:
    """One signed pair of effective contact traction utilizations.

    Each value is the resolved or imposed effective ratio

        lambda_j = Q_j / N_j = tau_j / (r_tau,j N_j).

    It is not a commanded percentage of a friction coefficient. During stick,
    lambda is solved as the traction *required* by compatibility. During
    established slip, its magnitude is supplied by the kinetic contact law and
    its sign follows the stored slip direction.
    """

    primary_lambda: float
    secondary_lambda: float

    def __post_init__(self) -> None:
        _require_finite(
            primary_lambda=self.primary_lambda,
            secondary_lambda=self.secondary_lambda,
        )

    def at(self, interface: ContactInterface) -> float:
        """Return the signed lambda associated with one contact interface."""

        if interface is ContactInterface.PRIMARY:
            return self.primary_lambda
        if interface is ContactInterface.SECONDARY:
            return self.secondary_lambda
        raise ValueError(f"Unsupported contact interface: {interface!r}.")

    def with_at(
        self,
        interface: ContactInterface,
        value: float,
    ) -> "ContactTractionUtilization":
        """Return a copy with one contact utilization replaced."""

        if not isfinite(value):
            raise ValueError("value must be finite.")
        if interface is ContactInterface.PRIMARY:
            return type(self)(primary_lambda=value, secondary_lambda=self.secondary_lambda)
        if interface is ContactInterface.SECONDARY:
            return type(self)(primary_lambda=self.primary_lambda, secondary_lambda=value)
        raise ValueError(f"Unsupported contact interface: {interface!r}.")


def _require_finite(**values: float) -> None:
    for name, value in values.items():
        if not isfinite(value):
            raise ValueError(f"{name} must be finite.")
