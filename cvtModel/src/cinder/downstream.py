"""Secondary-shaft attachments for composable CINDER drivetrain simulations.

The CVT/contact core owns the primary, belt, and secondary mechanics.  A
``SecondaryAttachment`` supplies the *known* boundary condition at the
secondary shaft for one ODE state: added rotational inertia and external
secondary torque.  A conventional locked final-drive vehicle is one
attachment; a dyno or prescribed secondary-shaft load is another.

Keeping this boundary outside the CVT closure preserves the existing 8x8
contact solve while avoiding a permanent assumption that the secondary is
always rigidly tied to a vehicle.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cinder.inertia import VehicleInertia
from cinder.vehicle import (
    ConstantGradeRoadProfile,
    FixedFinalDrive,
    RoadLoadModel,
    RoadLoadResult,
    RoadProfile,
)

if TYPE_CHECKING:
    from cinder.integration import CVTDynamicState


@dataclass(frozen=True, slots=True)
class SecondaryBoundary:
    """Known downstream contribution to one secondary-shaft RHS evaluation.

    ``added_rotational_inertia`` is referred directly to the secondary shaft
    and is added to CINDER's resolved CVT-side secondary inertia.  The signed
    ``external_torque`` is applied *to* the secondary shaft, matching the
    existing secondary rotational-row convention.

    Vehicle-specific observables are optional.  They are populated by
    :class:`LockedFinalDriveVehicle` so existing launch tools can continue to
    report road force, vehicle speed, and vehicle distance without making
    those quantities mandatory for every secondary attachment.
    """

    added_rotational_inertia: float = 0.0
    external_torque: float = 0.0
    road_load: RoadLoadResult | None = None
    vehicle_distance: float | None = None

    def __post_init__(self) -> None:
        if (
            not isfinite(self.added_rotational_inertia)
            or self.added_rotational_inertia < 0.0
        ):
            raise ValueError(
                "added_rotational_inertia must be finite and non-negative."
            )
        if not isfinite(self.external_torque):
            raise ValueError("external_torque must be finite.")
        if self.vehicle_distance is not None and not isfinite(self.vehicle_distance):
            raise ValueError("vehicle_distance must be finite when supplied.")


@runtime_checkable
class SecondaryAttachment(Protocol):
    """A state-evaluated boundary condition attached to CINDER's secondary."""

    def evaluate(self, *, state: "CVTDynamicState") -> SecondaryBoundary:
        """Return the known secondary boundary for ``state``."""


@dataclass(frozen=True, slots=True)
class LockedFinalDriveVehicle:
    """Current rigidly locked final-drive vehicle boundary.

    This preserves the existing launch-model physics:

    * vehicle position and speed are mapped from secondary angle and speed;
    * grade, rolling resistance, and aero load are reflected as secondary
      external torque; and
    * vehicle translation plus driven-wheel rotation are reflected as added
      secondary inertia.

    ``include_reflected_vehicle_inertia`` exists only for legacy-model
    compatibility.  New model assembly should leave it at its default
    ``True`` and resolve CVT inertias without vehicle reflection.  The legacy
    ``CVTDynamicsModel(road_load=..., road_profile=...)`` path sets it to
    ``False`` because those old resolved inertias already include the same
    reflected terms.
    """

    road_load: RoadLoadModel
    road_profile: RoadProfile = ConstantGradeRoadProfile()
    include_reflected_vehicle_inertia: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.road_load, RoadLoadModel):
            raise TypeError("road_load must be a RoadLoadModel instance.")
        if not isinstance(self.road_profile, RoadProfile):
            raise TypeError("road_profile must implement RoadProfile.sample().")
        if not isinstance(self.include_reflected_vehicle_inertia, bool):
            raise TypeError("include_reflected_vehicle_inertia must be bool.")

    @property
    def final_drive(self) -> FixedFinalDrive:
        """Return the rigid secondary-to-wheel reduction."""

        return self.road_load.final_drive

    @property
    def vehicle(self) -> VehicleInertia:
        """Return the physical vehicle mass and driven-wheel inertia."""

        return self.road_load.vehicle

    @property
    def reflected_rotational_inertia(self) -> float:
        """Return wheel plus translation inertia referred to the secondary."""

        if not self.include_reflected_vehicle_inertia:
            return 0.0
        return self.final_drive.secondary_inertia_from_wheel_rotation(
            wheel_rotational_inertia=self.vehicle.wheel_rotational_inertia,
        ) + self.final_drive.secondary_inertia_from_vehicle_mass(
            vehicle_mass=self.vehicle.mass,
        )

    def with_road_profile(self, road_profile: RoadProfile) -> "LockedFinalDriveVehicle":
        """Return the same locked drivetrain with a replacement route profile."""

        return replace(self, road_profile=road_profile)

    def evaluate(self, *, state: "CVTDynamicState") -> SecondaryBoundary:
        """Evaluate the current rigid vehicle load at the secondary shaft."""

        vehicle_distance = self.final_drive.vehicle_distance_from_secondary_angle(
            secondary_shaft_angle=state.secondary_shaft_angle,
        )
        grade_angle = self.road_profile.sample(
            vehicle_distance=vehicle_distance,
        ).grade_angle
        road_load = self.road_load.evaluate(
            secondary_angular_speed=state.secondary_angular_speed,
            grade_angle=grade_angle,
        )
        return SecondaryBoundary(
            added_rotational_inertia=self.reflected_rotational_inertia,
            external_torque=road_load.secondary_external_torque,
            road_load=road_load,
            vehicle_distance=vehicle_distance,
        )


@dataclass(frozen=True, slots=True)
class FixedSecondaryLoad:
    """Constant direct load for secondary-shaft and dyno-style CVT tests.

    ``external_torque`` follows CINDER's signed convention: a negative value
    opposes positive secondary rotation, while a positive value drives the
    secondary from downstream.  ``added_rotational_inertia`` is any constant
    inertia rigidly attached to the secondary shaft.
    """

    external_torque: float = 0.0
    added_rotational_inertia: float = 0.0

    def __post_init__(self) -> None:
        if not isfinite(self.external_torque):
            raise ValueError("external_torque must be finite.")
        if (
            not isfinite(self.added_rotational_inertia)
            or self.added_rotational_inertia < 0.0
        ):
            raise ValueError(
                "added_rotational_inertia must be finite and non-negative."
            )

    def evaluate(self, *, state: "CVTDynamicState") -> SecondaryBoundary:
        """Return the same direct boundary for every state."""

        del state
        return SecondaryBoundary(
            added_rotational_inertia=self.added_rotational_inertia,
            external_torque=self.external_torque,
        )
