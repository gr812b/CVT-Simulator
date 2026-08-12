"""Construction-time resolution of CVT-core inertia quantities."""

from __future__ import annotations

from dataclasses import dataclass

from .belt import BeltMass, ResolvedBeltMass, TrapezoidalBeltSection
from .primary import PrimaryInertia
from .secondary import (
    ResolvedSecondaryInertia,
    SecondaryInertia,
    resolve_secondary_inertia,
)
from .shift import AxialTranslationMasses, resolve_axial_translation_masses


@dataclass(frozen=True, slots=True)
class DrivetrainInertias:
    """CVT-owned primary, secondary, and belt inertia inputs."""

    primary: PrimaryInertia
    secondary: SecondaryInertia
    belt: BeltMass


@dataclass(frozen=True, slots=True)
class ResolvedInertias:
    """Fixed CVT quantities ready for the dynamic equations.

    ``axial_translation`` stores literal primary, secondary, and belt
    translation masses. Their coordinate mappings are evaluated from live
    geometry on each RHS call.
    """

    primary: PrimaryInertia
    secondary: ResolvedSecondaryInertia
    belt: ResolvedBeltMass
    axial_translation: AxialTranslationMasses


def resolve_inertias(
    *,
    drivetrain: DrivetrainInertias,
    belt_section: TrapezoidalBeltSection,
    belt_outer_length: float,
) -> ResolvedInertias:
    """Resolve fixed CVT-core constants independent of the live shift state."""

    belt = drivetrain.belt.resolve(
        belt_section=belt_section,
        outer_length=belt_outer_length,
    )

    return ResolvedInertias(
        primary=drivetrain.primary,
        secondary=resolve_secondary_inertia(secondary=drivetrain.secondary),
        belt=belt,
        axial_translation=resolve_axial_translation_masses(
            primary_moving_sheave_mass=drivetrain.primary.moving_sheave_mass,
            secondary_moving_sheave_mass=drivetrain.secondary.moving_sheave_mass,
            belt_mass=belt.mass,
        ),
    )
