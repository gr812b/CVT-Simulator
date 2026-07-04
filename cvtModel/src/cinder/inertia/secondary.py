"""Secondary-side physical inertia data and optional legacy vehicle reflection."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from .vehicle import VehicleInertia


class FinalDriveInertiaMap(Protocol):
    """The two fixed-drive reflections needed by the legacy secondary inertia."""

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
    """Fixed CVT-side physical secondary inertia data.

    ``fixed_rotational_inertia`` covers components rigidly attached directly to
    the secondary shaft. ``gearbox_input_rotational_inertia`` is the gearbox
    input-side inertia seen directly at that shaft.

    The movable sheave is stored separately because it has both absolute
    secondary rotation and relative helix rotation.  Vehicle and wheel inertia
    are normally supplied later by a downstream secondary attachment.
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
    """The resolved fixed-side secondary inertia breakdown.

    New CINDER assembly leaves the vehicle and driven-wheel terms at zero and
    supplies them through ``LockedFinalDriveVehicle``.  The fields are retained
    for compatibility with legacy callers that still resolve vehicle reflection
    into the CINDER core.
    """

    secondary_fixed_rotational_inertia: float
    gearbox_input_rotational_inertia: float
    driven_wheel_rotational_inertia: float = 0.0
    vehicle_translational_inertia: float = 0.0

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
    """Secondary rotational constants supplied by the CVT core.

    ``fixed_side.total`` is the core fixed-side inertia in new assembly.  The
    secondary attachment contributes any downstream inertia at RHS evaluation.
    """

    fixed_side: SecondaryFixedInertia
    movable_sheave_rotational_inertia: float

    @property
    def absolute_rotation_inertia(self) -> float:
        """Return fixed-side plus movable-sheave absolute rotation inertia."""

        return self.fixed_side.total + self.movable_sheave_rotational_inertia


def resolve_secondary_inertia(
    *,
    secondary: SecondaryInertia,
    vehicle: VehicleInertia | None = None,
    final_drive: FinalDriveInertiaMap | None = None,
) -> ResolvedSecondaryInertia:
    """Resolve constant secondary-side inertia coefficients.

    Passing neither ``vehicle`` nor ``final_drive`` produces the preferred
    CVT-core-only inertia.  Passing both preserves the former reflected-vehicle
    behavior for compatibility while callers migrate to a downstream
    attachment.  Passing only one is rejected because it would hide an
    incomplete physical coupling.
    """

    if (vehicle is None) != (final_drive is None):
        raise ValueError(
            "vehicle and final_drive must either both be supplied or both be omitted."
        )

    driven_wheel_rotational_inertia = 0.0
    vehicle_translational_inertia = 0.0
    if vehicle is not None and final_drive is not None:
        driven_wheel_rotational_inertia = (
            final_drive.secondary_inertia_from_wheel_rotation(
                wheel_rotational_inertia=vehicle.wheel_rotational_inertia,
            )
        )
        vehicle_translational_inertia = final_drive.secondary_inertia_from_vehicle_mass(
            vehicle_mass=vehicle.mass,
        )

    fixed_side = SecondaryFixedInertia(
        secondary_fixed_rotational_inertia=secondary.fixed_rotational_inertia,
        gearbox_input_rotational_inertia=secondary.gearbox_input_rotational_inertia,
        driven_wheel_rotational_inertia=driven_wheel_rotational_inertia,
        vehicle_translational_inertia=vehicle_translational_inertia,
    )

    return ResolvedSecondaryInertia(
        fixed_side=fixed_side,
        movable_sheave_rotational_inertia=secondary.movable_sheave_rotational_inertia,
    )
