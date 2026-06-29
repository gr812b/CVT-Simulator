"""Secondary-side physical inertia data and fixed-drive reflection."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from .vehicle import VehicleInertia


class FinalDriveInertiaMap(Protocol):
    """The two fixed-drive reflections needed by the secondary inertia."""

    def secondary_inertia_from_vehicle_mass(
        self,
        *,
        vehicle_mass: float,
    ) -> float:
        """Return vehicle translation referred to the secondary shaft."""

    def secondary_inertia_from_wheel_rotation(
        self,
        *,
        wheel_rotational_inertia: float,
    ) -> float:
        """Return driven-wheel spin inertia referred to the secondary shaft."""


@dataclass(frozen=True, slots=True)
class SecondaryInertia:
    """
    Fixed secondary-side physical properties.

    ``fixed_rotational_inertia`` covers components rigidly attached directly to
    the secondary shaft. ``gearbox_input_rotational_inertia`` is the gearbox
    input-side inertia seen directly at that shaft.

    The movable sheave is stored separately because it has both absolute
    secondary rotation and relative helix rotation.
    """

    fixed_rotational_inertia: float
    gearbox_input_rotational_inertia: float
    movable_sheave_rotational_inertia: float
    moving_sheave_mass: float

    def __post_init__(self) -> None:
        for name, value in (
            ("fixed_rotational_inertia", self.fixed_rotational_inertia),
            (
                "gearbox_input_rotational_inertia",
                self.gearbox_input_rotational_inertia,
            ),
            (
                "movable_sheave_rotational_inertia",
                self.movable_sheave_rotational_inertia,
            ),
            ("moving_sheave_mass", self.moving_sheave_mass),
        ):
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")


@dataclass(frozen=True, slots=True)
class SecondaryFixedInertia:
    """
    The fixed-side secondary inertia I_s,F, with its full breakdown.

    I_s,F = I_sec,F + I_gb + (I_wheel + m r_w^2) / G^2.
    """

    secondary_fixed_rotational_inertia: float
    gearbox_input_rotational_inertia: float
    driven_wheel_rotational_inertia: float
    vehicle_translational_inertia: float

    @property
    def total(self) -> float:
        return (
            self.secondary_fixed_rotational_inertia
            + self.gearbox_input_rotational_inertia
            + self.driven_wheel_rotational_inertia
            + self.vehicle_translational_inertia
        )


@dataclass(frozen=True, slots=True)
class ResolvedSecondaryInertia:
    """
    Secondary rotational constants used by the two secondary equations.

    ``fixed_side.total`` is I_s,F. The coefficient of secondary angular
    acceleration in the secondary rotational balance is
    ``absolute_rotation_inertia`` = I_s,F + I_M.
    """

    fixed_side: SecondaryFixedInertia
    movable_sheave_rotational_inertia: float

    @property
    def absolute_rotation_inertia(self) -> float:
        return self.fixed_side.total + self.movable_sheave_rotational_inertia


def resolve_secondary_inertia(
    *,
    secondary: SecondaryInertia,
    vehicle: VehicleInertia,
    final_drive: FinalDriveInertiaMap,
) -> ResolvedSecondaryInertia:
    """Resolve all constant secondary-side rotational coefficients once."""

    fixed_side = SecondaryFixedInertia(
        secondary_fixed_rotational_inertia=(secondary.fixed_rotational_inertia),
        gearbox_input_rotational_inertia=(secondary.gearbox_input_rotational_inertia),
        driven_wheel_rotational_inertia=(
            final_drive.secondary_inertia_from_wheel_rotation(
                wheel_rotational_inertia=(vehicle.wheel_rotational_inertia),
            )
        ),
        vehicle_translational_inertia=(
            final_drive.secondary_inertia_from_vehicle_mass(
                vehicle_mass=vehicle.mass,
            )
        ),
    )

    return ResolvedSecondaryInertia(
        fixed_side=fixed_side,
        movable_sheave_rotational_inertia=(secondary.movable_sheave_rotational_inertia),
    )
