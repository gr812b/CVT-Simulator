"""Generic shaft-boundary contracts and common implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, isfinite
from typing import Any, Mapping, Protocol, runtime_checkable

from cinder.model.system.ports import ShaftBoundaryValue
from cinder.model.system.state import CVTState


@dataclass(frozen=True, slots=True)
class ShaftBoundaryContext:
    """Inputs available to a shaft boundary at one plant evaluation."""

    time: float
    cvt: CVTState
    shaft: str
    host: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isfinite(self.time):
            raise ValueError("time must be finite.")
        if not isinstance(self.cvt, CVTState):
            raise TypeError("cvt must be a CVTState.")
        if self.shaft not in {"primary", "secondary"}:
            raise ValueError("shaft must be 'primary' or 'secondary'.")
        object.__setattr__(self, "host", dict(self.host))

    @property
    def shaft_speed(self) -> float:
        if self.shaft == "primary":
            return self.cvt.primary_angular_speed
        return self.cvt.secondary_angular_speed


@runtime_checkable
class ShaftBoundary(Protocol):
    """Component that supplies a signed external torque and referred inertia."""

    def evaluate(self, context: ShaftBoundaryContext) -> ShaftBoundaryValue:
        """Return the shaft boundary value for ``context``."""


@dataclass(frozen=True, slots=True)
class FixedShaftBoundary:
    """Constant shaft torque and equivalent inertia."""

    external_torque: float = 0.0
    equivalent_inertia: float = 0.0

    def __post_init__(self) -> None:
        if not isfinite(self.external_torque):
            raise ValueError("external_torque must be finite.")
        if not isfinite(self.equivalent_inertia) or self.equivalent_inertia < 0.0:
            raise ValueError("equivalent_inertia must be finite and non-negative.")

    def evaluate(self, context: ShaftBoundaryContext) -> ShaftBoundaryValue:
        del context
        return ShaftBoundaryValue(
            external_torque=self.external_torque,
            equivalent_inertia=self.equivalent_inertia,
        )


class FullThrottleEngineBoundary:
    """Full-throttle engine shaft boundary.

    The torque curve stores only torque-vs-speed behavior. Engine/flywheel/
    coupler inertia is part of the shaft boundary because it is the boundary
    object that attaches that rotating hardware to the primary shaft.
    """

    def __init__(self, torque_curve, *, equivalent_rotational_inertia: float) -> None:
        if (
            not isfinite(equivalent_rotational_inertia)
            or equivalent_rotational_inertia < 0.0
        ):
            raise ValueError(
                "equivalent_rotational_inertia must be finite and non-negative."
            )
        self._torque_curve = torque_curve
        self._equivalent_rotational_inertia = float(equivalent_rotational_inertia)

    @property
    def torque_curve(self):
        return self._torque_curve

    @property
    def equivalent_rotational_inertia(self) -> float:
        return self._equivalent_rotational_inertia

    def evaluate(self, context: ShaftBoundaryContext) -> ShaftBoundaryValue:
        torque = self._torque_curve.torque_at(context.shaft_speed)
        return ShaftBoundaryValue(
            external_torque=torque,
            equivalent_inertia=self._equivalent_rotational_inertia,
        )


from cinder.model.boundaries.vehicle import (  # noqa: E402
    ConstantGradeRoadProfile,
    RoadLoadModel,
    RoadProfile,
)


@dataclass(frozen=True, slots=True)
class LockedFinalDriveShaftBoundary:
    """Rigid final-drive vehicle boundary for the secondary shaft.

    The host must provide ``secondary_shaft_angle`` in radians. Vehicle speed is
    still locked to secondary speed through the final drive, so vehicle mass is
    reflected to the secondary as equivalent rotational inertia.
    """

    road_load: RoadLoadModel
    road_profile: RoadProfile = ConstantGradeRoadProfile()
    direct_secondary_shaft_inertia: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.road_load, RoadLoadModel):
            raise TypeError("road_load must be a RoadLoadModel.")
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
    def reflected_rotational_inertia(self) -> float:
        final_drive = self.road_load.final_drive
        vehicle = self.road_load.vehicle
        return (
            self.direct_secondary_shaft_inertia
            + final_drive.secondary_inertia_from_wheel_rotation(
                wheel_rotational_inertia=vehicle.wheel_rotational_inertia,
            )
            + final_drive.secondary_inertia_from_vehicle_mass(vehicle_mass=vehicle.mass)
        )

    def evaluate(self, context: ShaftBoundaryContext) -> ShaftBoundaryValue:
        if context.shaft != "secondary":
            raise ValueError(
                "LockedFinalDriveShaftBoundary must be attached to secondary."
            )
        try:
            secondary_angle = float(context.host["secondary_shaft_angle"])
        except KeyError as exc:
            raise KeyError(
                "LockedFinalDriveShaftBoundary requires host['secondary_shaft_angle']."
            ) from exc
        vehicle_distance = (
            self.road_load.final_drive.vehicle_distance_from_secondary_angle(
                secondary_shaft_angle=secondary_angle,
            )
        )
        grade_angle = self.road_profile.sample(
            vehicle_distance=vehicle_distance
        ).grade_angle
        road_load = self.road_load.evaluate(
            secondary_angular_speed=context.cvt.secondary_angular_speed,
            grade_angle=grade_angle,
        )
        return ShaftBoundaryValue(
            external_torque=road_load.secondary_external_torque,
            equivalent_inertia=self.reflected_rotational_inertia,
            metadata={"road_load": road_load, "vehicle_distance": vehicle_distance},
        )


@dataclass(frozen=True, slots=True)
class TanhLongitudinalTire:
    """Small smooth longitudinal tire model for first-pass wheel-slip hosts."""

    slip_stiffness: float
    friction_coefficient: float

    def __post_init__(self) -> None:
        if not isfinite(self.slip_stiffness) or self.slip_stiffness <= 0.0:
            raise ValueError("slip_stiffness must be positive and finite.")
        if not isfinite(self.friction_coefficient) or self.friction_coefficient < 0.0:
            raise ValueError("friction_coefficient must be finite and non-negative.")

    def force(self, *, slip_speed: float, normal_load: float) -> float:
        import math

        if not isfinite(slip_speed) or not isfinite(normal_load):
            raise ValueError("slip_speed and normal_load must be finite.")
        limit = self.friction_coefficient * max(0.0, normal_load)
        if limit == 0.0:
            return 0.0
        return limit * math.tanh(self.slip_stiffness * slip_speed / limit)


@dataclass(frozen=True, slots=True)
class TireCoupledShaftBoundary:
    """Secondary boundary for a fixed final drive with independent car speed.

    The host must provide ``vehicle_speed`` and may provide
    ``vehicle_position``. Translating vehicle mass is not reflected to the
    secondary; it belongs in the host vehicle ODE. This boundary returns only
    tire reaction torque and wheel/shaft rotational inertia.
    """

    road_load: RoadLoadModel
    tire: TanhLongitudinalTire
    road_profile: RoadProfile = ConstantGradeRoadProfile()
    direct_secondary_shaft_inertia: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.road_load, RoadLoadModel):
            raise TypeError("road_load must be a RoadLoadModel.")
        if not isinstance(self.tire, TanhLongitudinalTire):
            raise TypeError("tire must be a TanhLongitudinalTire.")
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
    def wheel_rotational_inertia_referred_to_secondary(self) -> float:
        return self.road_load.final_drive.secondary_inertia_from_wheel_rotation(
            wheel_rotational_inertia=self.road_load.vehicle.wheel_rotational_inertia,
        )

    def evaluate(self, context: ShaftBoundaryContext) -> ShaftBoundaryValue:
        if context.shaft != "secondary":
            raise ValueError("TireCoupledShaftBoundary must be attached to secondary.")
        try:
            vehicle_speed = float(context.host["vehicle_speed"])
        except KeyError as exc:
            raise KeyError(
                "TireCoupledShaftBoundary requires host['vehicle_speed']."
            ) from exc
        vehicle_position = float(context.host.get("vehicle_position", 0.0))
        grade_angle = self.road_profile.sample(
            vehicle_distance=vehicle_position
        ).grade_angle
        wheel_speed = self.road_load.final_drive.wheel_angular_speed(
            secondary_angular_speed=context.cvt.secondary_angular_speed,
        )
        patch_speed = self.road_load.final_drive.wheel_radius * wheel_speed
        normal_load = (
            self.road_load.vehicle.mass
            * self.road_load.spec.gravity
            * max(0.0, cos(grade_angle))
        )
        tire_force = self.tire.force(
            slip_speed=patch_speed - vehicle_speed,
            normal_load=normal_load,
        )
        torque = -self.road_load.final_drive.secondary_torque_from_wheel_force(
            wheel_force=tire_force,
        )
        return ShaftBoundaryValue(
            external_torque=torque,
            equivalent_inertia=(
                self.direct_secondary_shaft_inertia
                + self.wheel_rotational_inertia_referred_to_secondary
            ),
            metadata={
                "tire_force": tire_force,
                "vehicle_position": vehicle_position,
                "vehicle_speed": vehicle_speed,
                "grade_angle": grade_angle,
                "normal_load": normal_load,
                "tire_patch_speed": patch_speed,
            },
        )
