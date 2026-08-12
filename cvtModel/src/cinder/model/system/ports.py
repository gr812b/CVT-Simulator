"""Symmetric shaft-port values supplied to the mechanical CVT plant."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ShaftBoundaryValue:
    """External shaft contribution at one RHS evaluation.

    ``external_torque`` is positive when it acts in the positive rotation
    direction of the shaft it is attached to. ``equivalent_inertia`` is any
    non-CVT rotational inertia referred directly to that same shaft.
    """

    external_torque: float = 0.0
    equivalent_inertia: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isfinite(self.external_torque):
            raise ValueError("external_torque must be finite.")
        if not isfinite(self.equivalent_inertia) or self.equivalent_inertia < 0.0:
            raise ValueError("equivalent_inertia must be finite and non-negative.")
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class CVTShaftBoundaryValues:
    """Boundary values for the two CVT shaft ports."""

    primary: ShaftBoundaryValue = field(default_factory=ShaftBoundaryValue)
    secondary: ShaftBoundaryValue = field(default_factory=ShaftBoundaryValue)

    def __post_init__(self) -> None:
        if not isinstance(self.primary, ShaftBoundaryValue):
            raise TypeError("primary must be a ShaftBoundaryValue.")
        if not isinstance(self.secondary, ShaftBoundaryValue):
            raise TypeError("secondary must be a ShaftBoundaryValue.")

    @classmethod
    def zero(cls) -> "CVTShaftBoundaryValues":
        return cls()
