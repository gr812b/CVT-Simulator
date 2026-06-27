"""Construction-time resolution of fixed drivetrain inertia quantities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .belt import BeltMass, BeltSection, ResolvedBeltMass
from .primary import PrimaryInertia
from .secondary import (
    FinalDriveInertiaMap,
    ResolvedSecondaryInertia,
    SecondaryInertia,
    resolve_secondary_inertia,
)
from .shift import (
    ConstantShiftKinematics,
    ShiftTranslationMass,
    resolve_shift_translation_mass,
)
from .vehicle import VehicleInertia


@dataclass(frozen=True, slots=True)
class DrivetrainInertias:
    """All fixed engine, CVT, belt, and shift-kinematic inputs."""

    primary: PrimaryInertia
    secondary: SecondaryInertia
    belt: BeltMass
    shift_kinematics: ConstantShiftKinematics = field(
        default_factory=ConstantShiftKinematics,
    )


@dataclass(frozen=True, slots=True)
class ResolvedInertias:
    """
    Constant quantities ready for the dynamic equations.

    The raw physical breakdown remains available through the nested objects;
    no model equation needs to rebuild these fixed combinations on each RHS
    evaluation.
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
    Resolve the fixed inertia constants at system construction.

    This is valid while the final-drive ratio, wheel radius, vehicle mass,
    belt geometry, and the three shift-coordinate slopes remain fixed.
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
            kinematics=drivetrain.shift_kinematics,
        ),
    )
