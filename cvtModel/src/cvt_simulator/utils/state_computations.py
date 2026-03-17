"""Central scalar conversions used by CVT state/model code."""

from cvt_simulator.constants.car_specs import WHEEL_RADIUS


def secondary_pulley_angular_velocity_to_car_velocity(
    secondary_pulley_angular_velocity: float,
) -> float:
    """Convert secondary pulley angular velocity ω_s [rad/s] to car velocity v [m/s]."""
    return secondary_pulley_angular_velocity * WHEEL_RADIUS


def car_velocity_to_secondary_pulley_angular_velocity(car_velocity: float) -> float:
    """Convert car velocity v [m/s] to secondary pulley angular velocity ω_s [rad/s]."""
    return car_velocity / WHEEL_RADIUS
