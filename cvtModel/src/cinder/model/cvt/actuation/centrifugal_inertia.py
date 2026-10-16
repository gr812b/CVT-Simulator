"""Position-dependent inertia boundary for constrained centrifugal mechanisms."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class CentrifugalInertiaSample:
    """Two inertia functions and their local closing-position derivatives.

    The retained energy is ``T = 1/2 M(x) x_dot**2 + 1/2 J(x) omega**2``.
    ``effective_mass`` is M in kg; ``effective_mass_gradient`` is dM/dx in
    kg/m. ``shaft_inertia`` is J in kg m^2; its gradient is dJ/dx in kg m.

    M and J must be C1 on the admitted branch and the gradients must be their
    actual derivatives. These are provider obligations, not properties that
    can be established from one sample. Both gradients may have either sign.
    The represented mass must not also enter the host's constant inertias.
    """

    effective_mass: float
    effective_mass_gradient: float
    shaft_inertia: float
    shaft_inertia_gradient: float

    def __post_init__(self) -> None:
        for name, value in (
            ("effective_mass", self.effective_mass),
            ("effective_mass_gradient", self.effective_mass_gradient),
            ("shaft_inertia", self.shaft_inertia),
            ("shaft_inertia_gradient", self.shaft_inertia_gradient),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite.")
        if self.effective_mass < 0.0:
            raise ValueError("effective_mass must be non-negative.")
        if self.shaft_inertia < 0.0:
            raise ValueError("shaft_inertia must be non-negative.")


@runtime_checkable
class CentrifugalInertiaMap(Protocol):
    """Inertia of one mechanism whose internal configuration follows x.

    The reduction assumes no mixed ``B(x) omega x_dot`` kinetic term and no
    independent internal state. Geometry, branch selection, contact reactions,
    and any additional loads belong to the particular mechanism. The provider
    enforces its evaluation domain, including any documented endpoint roundoff
    tolerance; the declared interval is used for host travel validation.
    """

    @property
    def axial_position_min(self) -> float:
        """Smallest supported local pulley-closing position, in metres."""

    @property
    def axial_position_max(self) -> float:
        """Largest supported local pulley-closing position, in metres."""

    def evaluate(self, axial_position: float) -> CentrifugalInertiaSample:
        """Return M, dM/dx, J, and dJ/dx from the same compatible motion."""
