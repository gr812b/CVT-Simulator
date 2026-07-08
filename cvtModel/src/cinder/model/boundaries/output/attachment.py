"""Output-shaft boundaries for composable CINDER drivetrain simulations.

The CVT/contact core owns the primary, belt, and secondary mechanics. An
``OutputBoundary`` supplies the known boundary condition at the output shaft for
one ODE state: equivalent rotational inertia and signed load torque. A
conventional locked final-drive vehicle is one attachment; a dyno or prescribed
output-shaft load is another.

Keeping this boundary outside the CVT closure preserves the existing contact
solve while avoiding a permanent assumption that the secondary is always rigidly
tied to a vehicle.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cinder.model.boundaries.output.vehicle import VehicleInertia
from cinder.model.boundaries.output.vehicle import (
    ConstantGradeRoadProfile,
    FixedFinalDrive,
    RoadLoadModel,
    RoadLoadResult,
    RoadProfile,
)

if TYPE_CHECKING:
    from cinder.execution.hybrid import CVTDynamicState


@dataclass(frozen=True, slots=True)
class OutputBoundaryEvaluation:
    """Known downstream contribution to one output-shaft RHS evaluation.

    ``equivalent_rotational_inertia`` is referred directly to the output shaft
    and is added to CINDER's resolved CVT-side secondary inertia. The signed
    ``load_torque`` is applied *to* the output shaft, matching the existing
    secondary rotational-row convention. A negative value resists positive
    secondary rotation; a positive value drives the secondary from downstream.

    Vehicle-specific observables are optional. They are populated by
    :class:`LockedFinalDriveVehicle` so existing launch tools can continue to
    report road force, vehicle speed, and vehicle distance without making those
    quantities mandatory for every secondary attachment.
    """

    equivalent_rotational_inertia: float = 0.0
    load_torque: float = 0.0
    road_load: RoadLoadResult | None = None
    vehicle_distance: float | None = None

    def __post_init__(self) -> None:
        if (
            not isfinite(self.equivalent_rotational_inertia)
            or self.equivalent_rotational_inertia < 0.0
        ):
            raise ValueError(
                "equivalent_rotational_inertia must be finite and non-negative."
            )
        if not isfinite(self.load_torque):
            raise ValueError("load_torque must be finite.")
        if self.vehicle_distance is not None and not isfinite(self.vehicle_distance):
            raise ValueError("vehicle_distance must be finite when supplied.")

    @property
    def added_rotational_inertia(self) -> float:
        """Compatibility alias for the new equivalent-rotational-inertia name."""

        return self.equivalent_rotational_inertia

    @property
    def external_torque(self) -> float:
        """Compatibility alias for the new load-torque name."""

        return self.load_torque


@runtime_checkable
class OutputBoundary(Protocol):
    """A state-evaluated boundary condition attached to CINDER's secondary."""

    def evaluate(self, *, state: "CVTDynamicState") -> OutputBoundaryEvaluation:
        """Return the known secondary boundary for ``state``."""


@dataclass(frozen=True, slots=True)
class LockedFinalDriveVehicle:
    """Current rigidly locked final-drive vehicle boundary.

    This preserves the existing launch-model physics:

    * vehicle position and speed are mapped from secondary angle and speed;
    * grade, rolling resistance, and aero load are reflected as secondary load
      torque; and
    * vehicle translation plus driven-wheel rotation are reflected as
      equivalent secondary inertia.

    ``direct_secondary_shaft_inertia`` captures gearbox input inertia or other
    non-CVT hardware rigidly attached to the secondary shaft. It belongs to the
    output boundary, not the CVT assembly.
    """

    road_load: RoadLoadModel
    road_profile: RoadProfile = ConstantGradeRoadProfile()
    direct_secondary_shaft_inertia: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.road_load, RoadLoadModel):
            raise TypeError("road_load must be a RoadLoadModel instance.")
        if not isinstance(self.road_profile, RoadProfile):
            raise TypeError("road_profile must implement RoadProfile.sample().")
        if (
            not isfinite(self.direct_secondary_shaft_inertia)
            or self.direct_secondary_shaft_inertia < 0.0
        ):
            raise ValueError(
                "direct_secondary_shaft_inertia must be finite and non-negative."
            )

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
        """Return boundary-owned inertia referred to the secondary."""

        return (
            self.direct_secondary_shaft_inertia
            + self.final_drive.secondary_inertia_from_wheel_rotation(
                wheel_rotational_inertia=self.vehicle.wheel_rotational_inertia,
            )
            + self.final_drive.secondary_inertia_from_vehicle_mass(
                vehicle_mass=self.vehicle.mass,
            )
        )

    def with_road_profile(self, road_profile: RoadProfile) -> "LockedFinalDriveVehicle":
        """Return the same locked drivetrain with a replacement route profile."""

        return replace(self, road_profile=road_profile)

    def evaluate(self, *, state: "CVTDynamicState") -> OutputBoundaryEvaluation:
        """Evaluate the current rigid vehicle load at the output shaft."""

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
        return OutputBoundaryEvaluation(
            equivalent_rotational_inertia=self.reflected_rotational_inertia,
            load_torque=road_load.secondary_external_torque,
            road_load=road_load,
            vehicle_distance=vehicle_distance,
        )


@dataclass(frozen=True, slots=True)
class FixedOutputLoad:
    """Constant direct output-shaft load for dyno-style CVT tests.

    ``load_torque`` follows CINDER's signed convention: a negative value
    opposes positive secondary rotation, while a positive value drives the
    secondary from downstream. ``equivalent_rotational_inertia`` is any constant
    non-CVT inertia rigidly attached to the output shaft.
    """

    load_torque: float = 0.0
    equivalent_rotational_inertia: float = 0.0

    def __post_init__(self) -> None:
        if not isfinite(self.load_torque):
            raise ValueError("load_torque must be finite.")
        if (
            not isfinite(self.equivalent_rotational_inertia)
            or self.equivalent_rotational_inertia < 0.0
        ):
            raise ValueError(
                "equivalent_rotational_inertia must be finite and non-negative."
            )

    @property
    def external_torque(self) -> float:
        """Compatibility alias for the new load-torque name."""

        return self.load_torque

    @property
    def added_rotational_inertia(self) -> float:
        """Compatibility alias for the new equivalent-inertia name."""

        return self.equivalent_rotational_inertia

    def evaluate(self, *, state: "CVTDynamicState") -> OutputBoundaryEvaluation:
        """Return the same direct boundary for every state."""

        del state
        return OutputBoundaryEvaluation(
            equivalent_rotational_inertia=self.equivalent_rotational_inertia,
            load_torque=self.load_torque,
        )
