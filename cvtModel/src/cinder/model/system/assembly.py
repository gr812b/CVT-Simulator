"""CVT-only physical assembly composition.

This module contains belt/pulley hardware only.  Engines, final drives,
wheels, vehicles, and road loads are external boundaries on a
:class:`~cinder.model.system.case.CVTSimulationCase`.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.model.cvt.actuation import HelicalTorqueReactionForce, PulleyActuator
from cinder.model.cvt.geometry import BeltPulleyGeometry
from cinder.model.cvt.inertia import ResolvedInertias
from cinder.model.cvt.profiles import HelixProfile, HelixShiftKinematics


@dataclass(frozen=True, slots=True)
class BeltContactSpec:
    """CVT belt/pulley contact constants independent of a traction solver."""

    friction_coefficient: float

    def __post_init__(self) -> None:
        if not isfinite(self.friction_coefficient) or self.friction_coefficient < 0.0:
            raise ValueError("friction_coefficient must be finite and non-negative.")


@dataclass(frozen=True, slots=True)
class HelicalPulleyCoupling:
    """Relative-rotation geometry physically installed on one pulley.

    The coupling belongs structurally to its host :class:`PulleySpec`; it is
    neither a secondary-only field nor selected by a ``mounted_pulley`` string.
    It can be mounted on either side.  The present six-state equations activate
    the output-side form, while the actuator-law contract is already generic.
    """

    profile: HelixProfile
    opening_per_axial_position: float = -1.0
    opening_offset: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.profile, HelixProfile):
            raise TypeError("profile must be a HelixProfile.")
        if (
            not isfinite(self.opening_per_axial_position)
            or self.opening_per_axial_position == 0.0
        ):
            raise ValueError("opening_per_axial_position must be finite and non-zero.")
        if not isfinite(self.opening_offset):
            raise ValueError("opening_offset must be finite.")

    def evaluate_from_local_coordinate(
        self,
        *,
        axial_position: float,
        d_axial_position_ds: float,
        d2_axial_position_ds2: float,
    ) -> HelixShiftKinematics:
        """Evaluate host-relative helix kinematics from the local axial map."""

        opening_travel = self.opening_offset + (
            self.opening_per_axial_position * axial_position
        )
        return self.profile.evaluate_shift_kinematics(
            opening_travel=opening_travel,
            d_opening_ds=self.opening_per_axial_position * d_axial_position_ds,
            d2_opening_ds2=self.opening_per_axial_position * d2_axial_position_ds2,
        )


@dataclass(frozen=True, slots=True)
class PulleySpec:
    """One physical pulley, its actuator, and optional relative-motion hardware."""

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
    """Input and output pulley hardware, named by shaft boundary."""

    input: PulleySpec
    output: PulleySpec


@dataclass(frozen=True, slots=True)
class CVTAssemblySpec:
    """Complete CVT-only assembly required by the current mechanical model."""

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
        if self.pulleys.output.helical_coupling is None:
            raise ValueError(
                "The current six-state shift dynamics require an output-pulley "
                "helical_coupling."
            )
        if self.pulleys.input.helical_coupling is not None:
            raise NotImplementedError(
                "The generic helical actuator law can be mounted and inspected on "
                "either pulley, but the current six-state dynamics implement only "
                "the output-pulley relative-rotation coordinate."
            )
