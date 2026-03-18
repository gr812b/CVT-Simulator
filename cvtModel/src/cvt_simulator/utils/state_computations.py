"""Central scalar conversions used by CVT state/model code."""

from collections.abc import Sequence
import numpy as np
from cvt_simulator.constants.car_specs import WHEEL_RADIUS


def secondary_pulley_angular_velocity_to_car_velocity(
    secondary_pulley_angular_velocity: float,
) -> float:
    """Convert secondary pulley angular velocity ω_s [rad/s] to car velocity v [m/s]."""
    return secondary_pulley_angular_velocity * WHEEL_RADIUS


def car_velocity_to_secondary_pulley_angular_velocity(car_velocity: float) -> float:
    """Convert car velocity v [m/s] to secondary pulley angular velocity ω_s [rad/s]."""
    return car_velocity / WHEEL_RADIUS


def primary_pulley_angular_velocity_to_engine_angular_velocity(
    primary_pulley_angular_velocity: float,
) -> float:
    """Convert primary pulley angular velocity ω_p [rad/s] to engine angular velocity [rad/s]."""
    return primary_pulley_angular_velocity


def integrate_positions_trapezoidal(
    time: Sequence[float], velocities: Sequence[float]
) -> np.ndarray:
    """Integrate positions from velocity samples using trapezoidal integration."""
    if len(time) != len(velocities):
        raise ValueError(
            f"time and velocities length mismatch: {len(time)} != {len(velocities)}"
        )

    positions = np.zeros(len(time))
    for i in range(1, len(time)):
        dt = time[i] - time[i - 1]
        positions[i] = positions[i - 1] + (velocities[i - 1] + velocities[i]) * dt / 2.0
    return positions
