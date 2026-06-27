# cinder/vehicle/road_load.py

from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, pi, sin, sqrt

from .final_drive import FixedFinalDrive
from .spec import VehicleRoadLoadSpec


@dataclass(frozen=True, slots=True)
class RoadLoadResult:
    """
    Known-state road-load evaluation.

    Force convention:
        Positive longitudinal force acts forward on the vehicle.

    Torque convention:
        ``secondary_external_torque`` is the external torque applied
        to the secondary shaft by the vehicle and road. Positive torque
        acts in the positive secondary rotation direction.
    """

    secondary_angular_speed: float
    vehicle_speed: float
    grade_angle: float

    grade_force: float
    rolling_force: float
    aerodynamic_force: float
    external_force: float

    secondary_external_torque: float


class RoadLoadModel:
    """
    Map current secondary speed and road grade to known road-load torque.

    The model contains no vehicle acceleration term and contributes no
    closure gain. Reflected vehicle inertia belongs in the later inertia
    layer, not here.
    """

    def __init__(
        self,
        *,
        spec: VehicleRoadLoadSpec,
        final_drive: FixedFinalDrive,
    ) -> None:
        self._spec = spec
        self._final_drive = final_drive

    @property
    def spec(self) -> VehicleRoadLoadSpec:
        return self._spec

    @property
    def final_drive(self) -> FixedFinalDrive:
        return self._final_drive

    def evaluate(
        self,
        *,
        secondary_angular_speed: float,
        grade_angle: float,
    ) -> RoadLoadResult:
        """
        Return the signed longitudinal road force and secondary torque.

        ``grade_angle`` is positive uphill in the positive vehicle
        direction. It must lie strictly between -pi/2 and pi/2.
        """

        _require_finite(
            "secondary_angular_speed",
            secondary_angular_speed,
        )
        _validate_grade_angle(grade_angle)

        vehicle_speed = self._final_drive.vehicle_speed(
            secondary_angular_speed=secondary_angular_speed,
        )

        grade_force = self._grade_force(grade_angle=grade_angle)
        rolling_force = self._rolling_force(
            vehicle_speed=vehicle_speed,
            grade_angle=grade_angle,
        )
        aerodynamic_force = self._aerodynamic_force(
            vehicle_speed=vehicle_speed,
        )

        external_force = (
            grade_force
            + rolling_force
            + aerodynamic_force
        )

        secondary_external_torque = (
            self._final_drive.secondary_torque_from_wheel_force(
                wheel_force=external_force,
            )
        )

        return RoadLoadResult(
            secondary_angular_speed=secondary_angular_speed,
            vehicle_speed=vehicle_speed,
            grade_angle=grade_angle,
            grade_force=grade_force,
            rolling_force=rolling_force,
            aerodynamic_force=aerodynamic_force,
            external_force=external_force,
            secondary_external_torque=secondary_external_torque,
        )

    def _grade_force(self, *, grade_angle: float) -> float:
        """
        Return gravity's signed force along the road.

            F_grade = -m g sin(gamma)
        """

        return -self._spec.mass * self._spec.gravity * sin(
            grade_angle
        )

    def _rolling_force(
        self,
        *,
        vehicle_speed: float,
        grade_angle: float,
    ) -> float:
        """
        Return regularized rolling resistance.

            F_roll = -C_rr m g cos(gamma)
                     v / sqrt(v^2 + v_eps^2)

        The regularization makes rolling resistance smoothly vanish at
        rest without imposing a static holding force.
        """

        normal_force = (
            self._spec.mass
            * self._spec.gravity
            * cos(grade_angle)
        )

        direction_factor = vehicle_speed / sqrt(
            vehicle_speed**2
            + self._spec.rolling_speed_regularization**2
        )

        return (
            -self._spec.rolling_resistance_coefficient
            * normal_force
            * direction_factor
        )

    def _aerodynamic_force(self, *, vehicle_speed: float) -> float:
        """
        Return signed aerodynamic drag.

            F_aero = -0.5 rho C_d A |v| v
        """

        return (
            -0.5
            * self._spec.air_density
            * self._spec.drag_coefficient
            * self._spec.frontal_area
            * abs(vehicle_speed)
            * vehicle_speed
        )


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def _validate_grade_angle(grade_angle: float) -> None:
    if not isfinite(grade_angle):
        raise ValueError("grade_angle must be finite.")

    if not -pi / 2.0 < grade_angle < pi / 2.0:
        raise ValueError(
            "grade_angle must lie strictly between -pi/2 and pi/2."
        )
