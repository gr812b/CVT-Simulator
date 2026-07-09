"""CVT-only physical assembly composition.

This module contains belt/pulley hardware only. Engines, final drives,
vehicles, road loads, and dynos are shaft boundaries supplied by a host
simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.model.cvt.actuation import HelicalTorqueReactionForce, PulleyActuator
from cinder.model.cvt.contact import ContactTractionLaw
from cinder.model.cvt.geometry import BeltPulleyGeometry
from cinder.model.cvt.inertia import ResolvedInertias
from cinder.model.cvt.profiles import HelixProfile, HelixShiftKinematics


@dataclass(frozen=True, slots=True)
class BeltContactSpec:
    """Belt/pulley friction constants owned by the CVT assembly.

    The contact solver is fixed by CINDER. Users provide physical friction
    coefficients; the plant converts them into the internal signed traction
    law used by the stick/slip closure.
    """

    static_friction_coefficient: float
    kinetic_friction_coefficient: float | None = None

    def __post_init__(self) -> None:
        if (
            not isfinite(self.static_friction_coefficient)
            or self.static_friction_coefficient <= 0.0
        ):
            raise ValueError("static_friction_coefficient must be finite and strictly positive.")
        if self.kinetic_friction_coefficient is not None and (
            not isfinite(self.kinetic_friction_coefficient)
            or self.kinetic_friction_coefficient <= 0.0
        ):
            raise ValueError("kinetic_friction_coefficient must be finite and strictly positive.")

    @property
    def resolved_kinetic_friction_coefficient(self) -> float:
        return (
            self.static_friction_coefficient
            if self.kinetic_friction_coefficient is None
            else self.kinetic_friction_coefficient
        )

    def traction_law(self) -> ContactTractionLaw:
        """Build the internal contact-capacity law from friction coefficients."""

        return ContactTractionLaw.symmetric(
            primary_static_lambda_limit=self.static_friction_coefficient,
            secondary_static_lambda_limit=self.static_friction_coefficient,
            primary_kinetic_lambda_magnitude=self.resolved_kinetic_friction_coefficient,
            secondary_kinetic_lambda_magnitude=self.resolved_kinetic_friction_coefficient,
        )


@dataclass(frozen=True, slots=True)
class HelicalPulleyCoupling:
    """Relative-rotation geometry installed on one pulley.

    The coupling belongs to its host :class:`PulleySpec`. The profile coordinate
    is the pulley-local opening travel ``q = -x``, where the pulley-local axial
    coordinate ``x`` is positive closing. This mapping is part of the CVT
    geometry convention and is not user-configurable.
    """

    profile: HelixProfile

    def __post_init__(self) -> None:
        if not isinstance(self.profile, HelixProfile):
            raise TypeError("profile must be a HelixProfile.")

    def evaluate_from_local_coordinate(
        self,
        *,
        axial_position: float,
        d_axial_position_ds: float,
        d2_axial_position_ds2: float,
    ) -> HelixShiftKinematics:
        return self.profile.evaluate_shift_kinematics(
            opening_travel=-axial_position,
            d_opening_ds=-d_axial_position_ds,
            d2_opening_ds2=-d2_axial_position_ds2,
        )


@dataclass(frozen=True, slots=True)
class PulleySpec:
    """One physical pulley and its mounted local actuator/coupling hardware."""

    actuator: PulleyActuator
    helical_coupling: HelicalPulleyCoupling | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.actuator, PulleyActuator):
            raise TypeError("actuator must be a PulleyActuator.")
        if self.helical_coupling is not None and not isinstance(
            self.helical_coupling, HelicalPulleyCoupling
        ):
            raise TypeError("helical_coupling must be a HelicalPulleyCoupling or None.")
        has_helical_force = any(
            isinstance(law, HelicalTorqueReactionForce)
            for law in self.actuator.force_laws
        )
        if has_helical_force != (self.helical_coupling is not None):
            raise ValueError(
                "A pulley with HelicalTorqueReactionForce must provide exactly one "
                "helical_coupling, and a helical_coupling must be consumed by a "
                "HelicalTorqueReactionForce."
            )


@dataclass(frozen=True, slots=True)
class PulleyPairSpec:
    """Primary and secondary pulley hardware.

    The names define CVT sign conventions only. They do not imply engine side,
    vehicle side, power-flow direction, or actuation type.
    """

    primary: PulleySpec
    secondary: PulleySpec


@dataclass(frozen=True, slots=True)
class CVTAssemblySpec:
    """Complete CVT-only assembly required by the mechanical plant."""

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
