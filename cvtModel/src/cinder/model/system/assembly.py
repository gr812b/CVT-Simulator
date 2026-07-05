"""CVT-only hardware composition.

This module deliberately contains no engine, final drive, wheel, vehicle, or
road.  Those are external shaft boundaries in ``cinder.model.boundaries``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.model.cvt.actuation import PulleyActuator
from cinder.model.cvt.geometry import BeltPulleyGeometry
from cinder.model.cvt.inertia import ResolvedInertias
from cinder.model.cvt.profiles import HelixProfile


@dataclass(frozen=True, slots=True)
class BeltContactSpec:
    """CVT belt/pulley contact constants independent of a traction solver."""

    friction_coefficient: float

    def __post_init__(self) -> None:
        if not isfinite(self.friction_coefficient) or self.friction_coefficient < 0.0:
            raise ValueError("friction_coefficient must be finite and non-negative.")


@dataclass(frozen=True, slots=True)
class PulleySpec:
    """One physical pulley and its local actuation hardware.

    ``helical_profile`` is structurally owned by the pulley on which the helix
    physically lives.  The current six-state evaluator implements an output-pulley
    shift-coupled helical relation. The generic actuator contract itself is
    pulley-location independent.
    """

    actuator: PulleyActuator
    helical_profile: HelixProfile | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.actuator, PulleyActuator):
            raise TypeError("actuator must be a PulleyActuator.")
        if self.helical_profile is not None and not isinstance(self.helical_profile, HelixProfile):
            raise TypeError("helical_profile must be a HelixProfile or None.")


@dataclass(frozen=True, slots=True)
class PulleyPairSpec:
    """Input and output pulley hardware, named by shaft boundary rather than actuator type."""

    input: PulleySpec
    output: PulleySpec


@dataclass(frozen=True, slots=True)
class CVTAssemblySpec:
    """Complete CVT-only assembly required by the present mechanical model."""

    geometry: BeltPulleyGeometry
    pulleys: PulleyPairSpec
    inertias: ResolvedInertias
    contact: BeltContactSpec

    def __post_init__(self) -> None:
        if not isinstance(self.geometry, BeltPulleyGeometry):
            raise TypeError("geometry must be a BeltPulleyGeometry.")
        if not isinstance(self.pulleys, PulleyPairSpec):
            raise TypeError("pulleys must be a PulleyPairSpec.")
        if not isinstance(self.inertias, ResolvedInertias):
            raise TypeError("inertias must be a ResolvedInertias.")
        if not isinstance(self.contact, BeltContactSpec):
            raise TypeError("contact must be a BeltContactSpec.")
        if self.pulleys.output.helical_profile is None:
            raise ValueError(
                "The current six-state evaluator requires an output-pulley helical_profile."
            )
