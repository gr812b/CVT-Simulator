"""Public contracts used by CINDER pulley-actuation components."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from cinder.closure import AffineClosureScalar, ClosureGains, ClosureUnknowns


@dataclass(frozen=True, slots=True)
class PulleyActuationState:
    """Known local quantities available before the closure solve.

    ``axial_position`` is expressed in the particular actuator's local pulley
    coordinate.  Positive local axial force always means that the pulley tends
    to close and clamp.
    """

    axial_position: float
    axial_speed: float
    shaft_speed: float

    def __post_init__(self) -> None:
        for name, value in (
            ("axial_position", self.axial_position),
            ("axial_speed", self.axial_speed),
            ("shaft_speed", self.shaft_speed),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")


@dataclass(frozen=True, slots=True)
class PulleyActuationResult:
    """The complete local axial-force relation returned by one actuator."""

    relation: AffineClosureScalar

    @property
    def bias_force(self) -> float:
        """Known local force at the current RHS evaluation point."""

        return self.relation.bias

    @property
    def gains(self) -> ClosureGains:
        """Gain row aligned with :class:`cinder.closure.ClosureUnknowns`."""

        return self.relation.gains

    def force(self, unknowns: ClosureUnknowns) -> float:
        """Evaluate the local axial force after solving the closure."""

        return self.relation.evaluate(unknowns)


class AxialForceLaw(Protocol):
    """One composable mechanism contributing local pulley axial force."""

    def evaluate(self, state: PulleyActuationState) -> AffineClosureScalar:
        """Return an affine local axial-force contribution."""
