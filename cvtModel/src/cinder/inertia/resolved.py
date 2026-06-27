"""Construction-time resolution of fixed drivetrain inertia quantities."""

from __future__ import annotations

from dataclasses import dataclass

from .belt import BeltMass, BeltSection, ResolvedBeltMass
from .primary import PrimaryInertia
from .secondary import (
    FinalDriveInertiaMap,
    ResolvedSecondaryInertia,
    SecondaryInertia,
    resolve_secondary_inertia,
)
from .shift import (
    ShiftTranslationMass,
    resolve_shift_translation_mass,
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

    ``shift`` stores the three physical translating masses. Its generalized
    mass is evaluated from GeometryPosition during each RHS evaluation,
    because dx_s/ds and dx_b/ds can change with shift.
    """

    primary: PrimaryInertia
    secondary: ResolvedSecondaryInertia
    belt: ResolvedBeltMass
    shift: ShiftTranslationMass


def resolve_inertias(
    *,
    drivetrain: DrivetrainInertias,
    vehicle: VehicleInertia,
    final_drive: FinalDriveInertiaMap,
    belt_section: BeltSection,
    belt_outer_length: float,
) -> ResolvedInertias:
    """
    Resolve all fixed inertia quantities at system construction.

    The final-drive reflection, belt mass, and physical translating masses
    are fixed. The generalized shift coefficient is formed later from the
    current geometry coordinates.
    """

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
        shift=resolve_shift_translation_mass(
            primary_moving_sheave_mass=(
                drivetrain.primary.moving_sheave_mass
            ),
            secondary_moving_sheave_mass=(
                drivetrain.secondary.moving_sheave_mass
            ),
            belt_mass=belt.mass,
        ),
    )
