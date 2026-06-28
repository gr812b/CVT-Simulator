"""Construction-time resolution of fixed drivetrain inertia quantities."""

from __future__ import annotations

from dataclasses import dataclass

from .belt import BeltMass, ResolvedBeltMass, TrapezoidalBeltSection
from .primary import PrimaryInertia
from .secondary import (
    FinalDriveInertiaMap,
    ResolvedSecondaryInertia,
    SecondaryInertia,
    resolve_secondary_inertia,
)
from .shift import (
    ShiftTranslationMasses,
    resolve_shift_translation_masses,
)
from .vehicle import VehicleInertia


@dataclass(frozen=True, slots=True)
class DrivetrainInertias:
    """All fixed engine, CVT, and belt physical inertia inputs."""

    primary: PrimaryInertia
    secondary: SecondaryInertia
    belt: BeltMass


@dataclass(frozen=True, slots=True)
class ResolvedInertias:
    """
    Fixed quantities ready for the dynamic equations.

    ``shift`` stores physical translation masses only. Its generalized mass
    and coordinate-curvature coefficient are evaluated from live geometry
    on each RHS call.
    """

    primary: PrimaryInertia
    secondary: ResolvedSecondaryInertia
    belt: ResolvedBeltMass
    shift: ShiftTranslationMasses


def resolve_inertias(
    *,
    drivetrain: DrivetrainInertias,
    vehicle: VehicleInertia,
    final_drive: FinalDriveInertiaMap,
    belt_section: TrapezoidalBeltSection,
    belt_outer_length: float,
) -> ResolvedInertias:
    """Resolve physical constants that do not depend on the live shift state."""

    belt = drivetrain.belt.resolve(
        belt_section=belt_section,
        outer_length=belt_outer_length,
    )

    return ResolvedInertias(
        primary=drivetrain.primary,
        secondary=resolve_secondary_inertia(
            secondary=drivetrain.secondary,
            vehicle=vehicle,
            final_drive=final_drive,
        ),
        belt=belt,
        shift=resolve_shift_translation_masses(
            primary_moving_sheave_mass=(
                drivetrain.primary.moving_sheave_mass
            ),
            secondary_moving_sheave_mass=(
                drivetrain.secondary.moving_sheave_mass
            ),
            belt_mass=belt.mass,
        ),
    )
