import math

import numpy as np

try:
    from numba import njit

    NUMBA_ENABLED = True

    def maybe_njit(*args, **kwargs):
        return njit(*args, **kwargs)

except ImportError:  # pragma: no cover - exercised when numba is installed
    NUMBA_ENABLED = False

    def maybe_njit(*args, **kwargs):
        def decorator(func):
            return func

        return decorator


@maybe_njit(cache=True, fastmath=True)
def slip_relative_speed_kernel(
    primary_angular_velocity: float,
    secondary_angular_velocity: float,
    cvt_ratio: float,
) -> float:
    return primary_angular_velocity - (secondary_angular_velocity * cvt_ratio)


@maybe_njit(cache=True, fastmath=True)
def slip_coupling_torque_kernel(
    relative_speed: float,
    torque_demand: float,
    t_max_capacity: float,
    slip_speed_smoothing: float,
) -> tuple[float, bool]:
    coulomb_torque = t_max_capacity * math.tanh(relative_speed / slip_speed_smoothing)
    alpha = min(max(abs(relative_speed) / slip_speed_smoothing, 0.0), 1.0)
    torque_demand_clamped = min(max(torque_demand, -t_max_capacity), t_max_capacity)
    coupling_torque = (1.0 - alpha) * torque_demand_clamped + alpha * coulomb_torque
    return coupling_torque, alpha > 0.0


@maybe_njit(cache=True, fastmath=True)
def torque_demand_kernel(
    engine_torque: float,
    load_torque: float,
    wheel_inertia: float,
    wheel_angular_velocity: float,
    engine_to_wheel_ratio: float,
    engine_to_wheel_ratio_rate_of_change: float,
    engine_inertia: float,
) -> float:
    eng_term = engine_torque * wheel_inertia
    load_term = engine_inertia * load_torque * engine_to_wheel_ratio
    shift_term = (
        engine_inertia
        * wheel_inertia
        * wheel_angular_velocity
        * engine_to_wheel_ratio_rate_of_change
    )

    numerator = eng_term + load_term - shift_term
    denominator = wheel_inertia + engine_inertia * engine_to_wheel_ratio**2
    return numerator / denominator


@maybe_njit(cache=True, fastmath=True)
def primary_flyweight_force_kernel(
    flyweight_mass: float,
    angular_velocity: float,
    flyweight_radius: float,
    ramp_slope: float,
) -> tuple[float, float, float, float]:
    centrifugal_force = flyweight_mass * angular_velocity**2 * flyweight_radius
    angle = math.atan(-ramp_slope)
    angle_multiplier = math.tan(angle)
    net = centrifugal_force * angle_multiplier
    return angle, centrifugal_force, angle_multiplier, net


@maybe_njit(cache=True, fastmath=True)
def secondary_helix_force_kernel(
    torque: float,
    spring_torsion_torque: float,
    secondary_radius: float,
    ramp_slope: float,
) -> tuple[float, float, float]:
    helix_angle = math.atan(-ramp_slope)
    angle_multiplier = 2.0 * math.tan(helix_angle) * secondary_radius
    net = (torque + spring_torsion_torque) / angle_multiplier
    return helix_angle, angle_multiplier, net


@maybe_njit(cache=True, fastmath=True)
def radial_force_kernel(
    clamping_force: float,
    sheave_angle: float,
    wrap_angle: float,
    sec_angular_velocity: float,
    sec_radius: float,
    belt_cross_sectional_area: float,
    rubber_density: float,
) -> tuple[float, float, float]:
    radial_from_clamping = 2.0 * (clamping_force * math.tan(sheave_angle / 2.0)) / wrap_angle

    radial_from_centrifugal = (
        sec_angular_velocity**2
        * sec_radius**2
        * belt_cross_sectional_area
        * rubber_density
    )

    total_radial = (
        2.0
        * math.sin(wrap_angle / 2.0)
        * (radial_from_clamping + radial_from_centrifugal)
    )

    return radial_from_clamping, radial_from_centrifugal, total_radial


@maybe_njit(cache=True, fastmath=True)
def max_torque_primary_kernel(
    mu_effective: float,
    wrap_angle: float,
    total_radial: float,
    radius: float,
) -> float:
    exp_term = math.exp(mu_effective * wrap_angle)
    capstan_term = (exp_term - 1.0) / (exp_term + 1.0)
    radial_force_term = total_radial * radius / math.sin(wrap_angle / 2.0)
    max_torque = capstan_term * radial_force_term
    return max(0.0, max_torque)


@maybe_njit(cache=True, fastmath=True)
def max_torque_secondary_kernel(
    spring_comp_force: float,
    spring_tors_torque: float,
    sheave_angle: float,
    radial_from_centrifugal: float,
    wrap_angle: float,
    radius: float,
    mu_effective: float,
    cvt_ratio: float,
    helix_radius: float,
    helix_angle: float,
) -> float:
    spring_force_term = (spring_comp_force + spring_tors_torque) * math.tan(
        sheave_angle / 2.0
    )

    centrifugal_force = radial_from_centrifugal * wrap_angle / 2.0

    exp_term = math.exp(mu_effective * wrap_angle)
    capstan_term = (wrap_angle / (4.0 * radius)) * (exp_term + 1.0) / (exp_term - 1.0)

    transmission_term = (
        2.0
        * cvt_ratio
        * (helix_radius * math.tan(helix_angle))
        * math.tan(sheave_angle / 2.0)
    )

    numerator = centrifugal_force + spring_force_term
    denominator = capstan_term - transmission_term
    max_torque = numerator / denominator
    return max(0.0, max_torque)
