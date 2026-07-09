"""Longitudinal wheel-slip host for a fixed final drive."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, sqrt
from typing import Any, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from cinder.core import StateBlock
from cinder.execution.hybrid.hybrid import HybridEvent, HybridTransition
from cinder.model.boundaries.shaft import TireCoupledShaftBoundary
from cinder.model.system import CVTShaftBoundaryValues, CVTState


@dataclass(frozen=True, slots=True)
class TireVehicleHost:
    """Host with secondary angle, vehicle position, and vehicle speed."""

    tire_boundary: TireCoupledShaftBoundary
    block_name: str = "host"

    @property
    def state_block(self) -> StateBlock:
        return StateBlock(self.block_name, 3)

    def initial_state(
        self,
        *,
        secondary_shaft_angle: float = 0.0,
        vehicle_position: float = 0.0,
        vehicle_speed: float = 0.0,
    ) -> NDArray[np.float64]:
        return np.asarray([secondary_shaft_angle, vehicle_position, vehicle_speed], dtype=float)

    def context(self, *, time: float, cvt_state: CVTState, host_state: NDArray[np.float64]) -> Mapping[str, Any]:
        del time, cvt_state
        return {
            "secondary_shaft_angle": float(host_state[0]),
            "vehicle_position": float(host_state[1]),
            "vehicle_speed": float(host_state[2]),
        }

    def rhs(self, *, time: float, cvt_state: CVTState, host_state: NDArray[np.float64], shaft_boundaries: CVTShaftBoundaryValues) -> NDArray[np.float64]:
        del time
        speed = float(host_state[2])
        metadata = shaft_boundaries.secondary.metadata
        tire_force = float(metadata.get("tire_force", 0.0))
        grade_angle = float(metadata.get("grade_angle", 0.0))
        road_force = _road_force(self.tire_boundary, vehicle_speed=speed, grade_angle=grade_angle)
        mass = self.tire_boundary.road_load.vehicle.mass
        acceleration = (tire_force + road_force) / mass
        return np.asarray([cvt_state.secondary_angular_speed, speed, acceleration], dtype=float)

    def events(self, *, time: float, cvt_state: CVTState, host_state: NDArray[np.float64], shaft_boundaries: CVTShaftBoundaryValues) -> Sequence[HybridEvent]:
        del time, cvt_state, host_state, shaft_boundaries
        return ()

    def transition(self, *, time: float, cvt_state: CVTState, host_state: NDArray[np.float64], shaft_boundaries: CVTShaftBoundaryValues, fired_event_names: tuple[str, ...]) -> HybridTransition[Any] | None:
        del time, cvt_state, host_state, shaft_boundaries, fired_event_names
        return None


def _road_force(boundary: TireCoupledShaftBoundary, *, vehicle_speed: float, grade_angle: float) -> float:
    model = boundary.road_load
    spec = model.spec
    vehicle = model.vehicle
    grade_force = -(vehicle.mass * spec.gravity * np.sin(grade_angle))
    normal_force = vehicle.mass * spec.gravity * cos(grade_angle)
    rolling_direction = vehicle_speed / sqrt(vehicle_speed**2 + spec.rolling_speed_regularization**2)
    rolling_force = -spec.rolling_resistance_coefficient * normal_force * rolling_direction
    aero_force = -0.5 * spec.air_density * spec.drag_coefficient * spec.frontal_area * abs(vehicle_speed) * vehicle_speed
    return grade_force + rolling_force + aero_force
