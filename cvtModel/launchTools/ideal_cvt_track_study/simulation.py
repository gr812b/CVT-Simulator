from __future__ import annotations

import csv
from dataclasses import dataclass
from math import isfinite, sin, sqrt
from pathlib import Path
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from models import (
    DriverModel,
    EngineModel,
    IdealCVTModel,
    RAD_PER_SECOND_TO_RPM,
    RPM_TO_RAD_PER_SECOND,
    SimulationSettings,
    TireModel,
    VehicleModel,
)
from track_builder import Track, TrackSample, banked_tire_loads_n

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class StudyCase:
    name: str
    engine: EngineModel
    vehicle: VehicleModel
    tire: TireModel
    cvt: IdealCVTModel
    driver: DriverModel
    infinite_cvt: bool = False

    @property
    def slug(self) -> str:
        return (
            self.name.lower()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("-", "_")
        )


@dataclass(frozen=True, slots=True)
class PowertrainSample:
    cvt_ratio: float
    ratio_required: float
    mode: str
    engine_speed_rpm: float
    engine_torque_nm: float
    engine_power_w: float
    transmitted_power_w: float
    drive_torque_wheel_nm: float
    clutch_loss_power_w: float
    operating_point_shortfall_power_w: float


@dataclass(frozen=True, slots=True)
class DynamicsSample:
    dx_dt: float
    dv_dt: float
    domega_wheel_dt: float
    throttle: float
    brake_force_command_n: float
    brake_torque_wheel_nm: float
    target_speed_mps: float
    track: TrackSample
    powertrain: PowertrainSample
    tire_force_n: float
    tire_limit_n: float
    tire_utilization: float
    tire_slip_speed_mps: float
    grade_force_n: float
    rolling_force_n: float
    aerodynamic_force_n: float
    obstacle_force_n: float
    lateral_force_n: float
    tire_slip_loss_power_w: float
    brake_loss_power_w: float
    rolling_loss_power_w: float
    aerodynamic_loss_power_w: float
    obstacle_loss_power_w: float
    grade_power_w: float


@dataclass(frozen=True, slots=True)
class SimulationTrace:
    case_name: str
    track_name: str
    completed: bool
    termination_reason: str
    numeric: Mapping[str, FloatArray]
    text: Mapping[str, tuple[str, ...]]

    @property
    def time_s(self) -> FloatArray:
        return self.numeric["time_s"]

    @property
    def final_time_s(self) -> float:
        return float(self.time_s[-1])

    @property
    def final_distance_m(self) -> float:
        return float(self.numeric["distance_m"][-1])

    def write_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        numeric_keys = list(self.numeric)
        text_keys = list(self.text)
        count = len(self.time_s)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([*numeric_keys, *text_keys])
            for index in range(count):
                writer.writerow(
                    [
                        *(float(self.numeric[key][index]) for key in numeric_keys),
                        *(self.text[key][index] for key in text_keys),
                    ]
                )


def _driver_commands(
    *,
    track: Track,
    distance_m: float,
    vehicle_speed_mps: float,
    driver: DriverModel,
) -> tuple[float, float, float]:
    target = track.safe_speed_limit_mps(
        distance_m,
        braking_deceleration_mps2=driver.maximum_braking_deceleration_mps2,
    )
    if not isfinite(target):
        return 1.0, 0.0, target

    error = vehicle_speed_mps - target
    if error > 0.0:
        command = min(1.0, driver.speed_control_gain * error / max(target, 1.0))
        return 0.0, command * driver.maximum_brake_force_n, target

    if vehicle_speed_mps > target - driver.speed_margin_mps:
        available = max(0.0, target - vehicle_speed_mps)
        throttle = min(1.0, available / max(driver.speed_margin_mps, 1.0e-9))
        return throttle, 0.0, target

    return 1.0, 0.0, target


def _bounded_powertrain(
    *,
    wheel_speed_rad_s: float,
    throttle: float,
    engine: EngineModel,
    cvt: IdealCVTModel,
) -> PowertrainSample:
    wheel_speed = max(0.0, float(wheel_speed_rad_s))
    secondary_speed = cvt.final_drive_ratio * wheel_speed
    target_omega = engine.peak_power_rpm * RPM_TO_RAD_PER_SECOND
    ratio_required = target_omega / max(secondary_speed, 1.0e-12)
    peak_power = engine.peak_power_w

    if ratio_required > cvt.maximum_speed_ratio:
        ratio = cvt.maximum_speed_ratio
        synchronous_engine_omega = ratio * secondary_speed
        if cvt.ideal_launch_clutch and synchronous_engine_omega < target_omega:
            mode = "low_ratio_clutch"
            engine_omega = target_omega
        else:
            mode = "low_ratio_fixed"
            engine_omega = synchronous_engine_omega
    elif ratio_required < cvt.minimum_speed_ratio:
        ratio = cvt.minimum_speed_ratio
        mode = "high_ratio_fixed"
        engine_omega = ratio * secondary_speed
    else:
        ratio = ratio_required
        mode = "variable_peak_power"
        engine_omega = target_omega

    engine_rpm = engine_omega * RAD_PER_SECOND_TO_RPM
    engine_torque = max(0.0, engine.torque_nm(engine_rpm)) * throttle
    engine_power = engine_torque * engine_omega
    wheel_drive_torque = (
        engine_torque
        * ratio
        * cvt.final_drive_ratio
        * cvt.transmission_efficiency
    )
    transmitted_power = max(0.0, wheel_drive_torque * wheel_speed)
    clutch_loss = 0.0
    if mode == "low_ratio_clutch":
        clutch_loss = max(0.0, engine_power * cvt.transmission_efficiency - transmitted_power)
    operating_shortfall = max(0.0, peak_power * throttle - engine_power)

    return PowertrainSample(
        cvt_ratio=float(ratio),
        ratio_required=float(ratio_required),
        mode=mode,
        engine_speed_rpm=float(engine_rpm),
        engine_torque_nm=float(engine_torque),
        engine_power_w=float(engine_power),
        transmitted_power_w=float(transmitted_power),
        drive_torque_wheel_nm=float(wheel_drive_torque),
        clutch_loss_power_w=float(clutch_loss),
        operating_point_shortfall_power_w=float(operating_shortfall),
    )


def _infinite_powertrain(
    *,
    wheel_speed_rad_s: float,
    throttle: float,
    engine: EngineModel,
    cvt: IdealCVTModel,
    settings: SimulationSettings,
) -> PowertrainSample:
    wheel_speed = max(0.0, float(wheel_speed_rad_s))
    secondary_speed = cvt.final_drive_ratio * wheel_speed
    target_omega = engine.peak_power_rpm * RPM_TO_RAD_PER_SECOND
    ratio_required = target_omega / max(secondary_speed, 1.0e-12)
    engine_torque = max(0.0, engine.torque_nm(engine.peak_power_rpm)) * throttle
    engine_power = engine_torque * target_omega
    requested_torque = (
        engine_power
        * cvt.transmission_efficiency
        / max(wheel_speed, settings.ideal_reference_omega_floor_rad_s)
    )
    wheel_drive_torque = min(requested_torque, settings.ideal_reference_torque_cap_nm)
    transmitted_power = wheel_drive_torque * wheel_speed
    return PowertrainSample(
        cvt_ratio=float(ratio_required),
        ratio_required=float(ratio_required),
        mode="infinite_peak_power",
        engine_speed_rpm=float(engine.peak_power_rpm),
        engine_torque_nm=float(engine_torque),
        engine_power_w=float(engine_power),
        transmitted_power_w=float(transmitted_power),
        drive_torque_wheel_nm=float(wheel_drive_torque),
        clutch_loss_power_w=0.0,
        operating_point_shortfall_power_w=max(0.0, engine.peak_power_w * throttle - engine_power),
    )


def evaluate_dynamics(
    *,
    state: NDArray[np.float64],
    case: StudyCase,
    track: Track,
    settings: SimulationSettings,
) -> DynamicsSample:
    distance_m = max(0.0, float(state[0]))
    vehicle_speed = max(0.0, float(state[1]))
    wheel_speed = max(0.0, float(state[2]))
    sample = track.sample(
        distance_m,
        vehicle_speed_mps=vehicle_speed,
        vehicle_mass_kg=case.vehicle.mass_kg,
        gravity_mps2=case.vehicle.gravity_mps2,
    )

    throttle, brake_force_command, target_speed = _driver_commands(
        track=track,
        distance_m=distance_m,
        vehicle_speed_mps=vehicle_speed,
        driver=case.driver,
    )
    if case.infinite_cvt:
        powertrain = _infinite_powertrain(
            wheel_speed_rad_s=wheel_speed,
            throttle=throttle,
            engine=case.engine,
            cvt=case.cvt,
            settings=settings,
        )
    else:
        powertrain = _bounded_powertrain(
            wheel_speed_rad_s=wheel_speed,
            throttle=throttle,
            engine=case.engine,
            cvt=case.cvt,
        )

    grade = sample.grade_radians
    vehicle = case.vehicle
    tire = case.tire
    total_normal, lateral_force = banked_tire_loads_n(
        mass_kg=vehicle.mass_kg,
        gravity_mps2=vehicle.gravity_mps2,
        grade_radians=grade,
        speed_mps=vehicle_speed,
        curvature_1_per_m=sample.curvature_1_per_m,
        bank_angle_degrees=sample.bank_angle_degrees,
        normal_load_scale=sample.normal_load_scale,
    )
    driven_normal = vehicle.driven_normal_load_fraction * total_normal
    total_friction_capacity = sample.friction_coefficient * total_normal
    friction_circle_longitudinal_limit = sqrt(
        max(total_friction_capacity**2 - lateral_force**2, 0.0)
    )
    tire_limit = min(
        sample.friction_coefficient * driven_normal,
        friction_circle_longitudinal_limit,
    )
    patch_speed = tire.wheel_radius_m * wheel_speed
    slip_speed = patch_speed - vehicle_speed
    if tire_limit > 0.0:
        tire_force = tire_limit * np.tanh(
            tire.slip_stiffness_n_per_mps * slip_speed / tire_limit
        )
        tire_utilization = abs(tire_force) / tire_limit
    else:
        tire_force = 0.0
        tire_utilization = 0.0

    grade_force = vehicle.mass_kg * vehicle.gravity_mps2 * sin(grade)
    rolling_force = (
        sample.rolling_resistance_coefficient
        * total_normal
        * np.tanh(vehicle_speed / 0.1)
    )
    aerodynamic_force = (
        0.5
        * vehicle.air_density_kg_m3
        * vehicle.drag_coefficient
        * vehicle.frontal_area_m2
        * vehicle_speed**2
    )

    brake_torque = brake_force_command * tire.wheel_radius_m
    net_wheel_torque = (
        powertrain.drive_torque_wheel_nm
        - brake_torque
        - tire_force * tire.wheel_radius_m
    )
    domega = net_wheel_torque / vehicle.wheel_rotational_inertia_kg_m2
    obstacle_force = sample.additional_resistance_force_n
    dv = (
        tire_force
        - grade_force
        - rolling_force
        - aerodynamic_force
        - obstacle_force
    ) / vehicle.mass_kg

    if wheel_speed <= 0.0 and domega < 0.0:
        domega = 0.0
    if vehicle_speed <= 0.0 and dv < 0.0:
        dv = 0.0

    tire_slip_loss_power = max(0.0, tire_force * slip_speed)
    brake_loss_power = max(0.0, brake_torque * wheel_speed)
    rolling_loss_power = max(0.0, rolling_force * vehicle_speed)
    aerodynamic_loss_power = max(0.0, aerodynamic_force * vehicle_speed)
    obstacle_loss_power = max(0.0, obstacle_force * vehicle_speed)
    grade_power = grade_force * vehicle_speed

    return DynamicsSample(
        dx_dt=vehicle_speed,
        dv_dt=float(dv),
        domega_wheel_dt=float(domega),
        throttle=float(throttle),
        brake_force_command_n=float(brake_force_command),
        brake_torque_wheel_nm=float(brake_torque),
        target_speed_mps=float(target_speed),
        track=sample,
        powertrain=powertrain,
        tire_force_n=float(tire_force),
        tire_limit_n=float(tire_limit),
        tire_utilization=float(tire_utilization),
        tire_slip_speed_mps=float(slip_speed),
        grade_force_n=float(grade_force),
        rolling_force_n=float(rolling_force),
        aerodynamic_force_n=float(aerodynamic_force),
        obstacle_force_n=float(obstacle_force),
        lateral_force_n=float(lateral_force),
        tire_slip_loss_power_w=float(tire_slip_loss_power),
        brake_loss_power_w=float(brake_loss_power),
        rolling_loss_power_w=float(rolling_loss_power),
        aerodynamic_loss_power_w=float(aerodynamic_loss_power),
        obstacle_loss_power_w=float(obstacle_loss_power),
        grade_power_w=float(grade_power),
    )


def _implicit_tire_slip_step(
    *,
    previous_slip_speed_mps: float,
    step_s: float,
    free_slip_acceleration_mps2: float,
    tire_force_coefficient: float,
    tire_limit_n: float,
    tire_stiffness_n_per_mps: float,
) -> tuple[float, float]:
    """Backward-Euler update for the stiff wheel/vehicle slip coordinate.

    The tire law is monotone, so Newton's method is scalar, stable, and fast.
    This preserves the independent wheel and vehicle states without forcing the
    entire track sweep through a general-purpose stiff ODE solver.
    """

    if tire_limit_n <= 0.0:
        new_slip = previous_slip_speed_mps + step_s * free_slip_acceleration_mps2
        return float(new_slip), 0.0

    new_slip = previous_slip_speed_mps
    for _ in range(12):
        scaled = tire_stiffness_n_per_mps * new_slip / tire_limit_n
        tanh_scaled = float(np.tanh(scaled))
        tire_force = tire_limit_n * tanh_scaled
        residual = (
            new_slip
            - previous_slip_speed_mps
            - step_s
            * (
                free_slip_acceleration_mps2
                - tire_force_coefficient * tire_force
            )
        )
        derivative = 1.0 + (
            step_s
            * tire_force_coefficient
            * tire_stiffness_n_per_mps
            * (1.0 - tanh_scaled**2)
        )
        correction = residual / max(derivative, 1.0e-12)
        new_slip -= correction
        if abs(correction) <= 1.0e-11:
            break

    tire_force = tire_limit_n * float(
        np.tanh(tire_stiffness_n_per_mps * new_slip / tire_limit_n)
    )
    return float(new_slip), float(tire_force)


def run_simulation(
    *,
    case: StudyCase,
    track: Track,
    settings: SimulationSettings,
) -> SimulationTrace:
    """Run one lap with a fixed-step, semi-implicit tire-slip integrator."""

    step_s = settings.integration_step_s
    distance_m = 0.0
    vehicle_speed = settings.initial_vehicle_speed_mps
    wheel_speed = settings.initial_wheel_speed_rad_s
    slip_speed = case.tire.wheel_radius_m * wheel_speed - vehicle_speed
    time_s = 0.0

    times = [time_s]
    distances = [distance_m]
    vehicle_speeds = [vehicle_speed]
    wheel_speeds = [wheel_speed]

    maximum_steps = int(np.ceil(settings.maximum_time_s / step_s))
    completed = False
    reason = "maximum_time_reached"

    for _ in range(maximum_steps):
        state = np.asarray([distance_m, vehicle_speed, wheel_speed], dtype=float)
        dynamics = evaluate_dynamics(
            state=state,
            case=case,
            track=track,
            settings=settings,
        )
        road_resistance_n = (
            dynamics.grade_force_n
            + dynamics.rolling_force_n
            + dynamics.aerodynamic_force_n
            + dynamics.obstacle_force_n
        )
        free_slip_acceleration = (
            case.tire.wheel_radius_m
            * (
                dynamics.powertrain.drive_torque_wheel_nm
                - dynamics.brake_torque_wheel_nm
            )
            / case.vehicle.wheel_rotational_inertia_kg_m2
            + road_resistance_n / case.vehicle.mass_kg
        )
        tire_force_coefficient = (
            case.tire.wheel_radius_m**2
            / case.vehicle.wheel_rotational_inertia_kg_m2
            + 1.0 / case.vehicle.mass_kg
        )
        new_slip_speed, new_tire_force = _implicit_tire_slip_step(
            previous_slip_speed_mps=slip_speed,
            step_s=step_s,
            free_slip_acceleration_mps2=free_slip_acceleration,
            tire_force_coefficient=tire_force_coefficient,
            tire_limit_n=dynamics.tire_limit_n,
            tire_stiffness_n_per_mps=case.tire.slip_stiffness_n_per_mps,
        )

        new_vehicle_speed = max(
            0.0,
            vehicle_speed
            + step_s
            * (new_tire_force - road_resistance_n)
            / case.vehicle.mass_kg,
        )
        new_wheel_speed = max(
            0.0,
            (new_slip_speed + new_vehicle_speed) / case.tire.wheel_radius_m,
        )
        if new_wheel_speed <= 0.0:
            new_slip_speed = -new_vehicle_speed
        new_distance = distance_m + 0.5 * step_s * (
            vehicle_speed + new_vehicle_speed
        )
        new_time = time_s + step_s

        if new_distance >= track.length_m:
            fraction = (track.length_m - distance_m) / max(
                new_distance - distance_m,
                1.0e-12,
            )
            new_time = time_s + fraction * step_s
            new_distance = track.length_m
            new_vehicle_speed = vehicle_speed + fraction * (
                new_vehicle_speed - vehicle_speed
            )
            new_slip_speed = slip_speed + fraction * (
                new_slip_speed - slip_speed
            )
            new_wheel_speed = max(
                0.0,
                (new_slip_speed + new_vehicle_speed) / case.tire.wheel_radius_m,
            )
            completed = True
            reason = "track_complete"

        time_s = new_time
        distance_m = new_distance
        vehicle_speed = new_vehicle_speed
        wheel_speed = new_wheel_speed
        slip_speed = new_slip_speed
        times.append(time_s)
        distances.append(distance_m)
        vehicle_speeds.append(vehicle_speed)
        wheel_speeds.append(wheel_speed)

        if completed:
            break

    internal_times = np.asarray(times, dtype=float)
    internal_distance = np.asarray(distances, dtype=float)
    internal_vehicle_speed = np.asarray(vehicle_speeds, dtype=float)
    internal_wheel_speed = np.asarray(wheel_speeds, dtype=float)
    final_time = float(internal_times[-1])
    report_times = np.arange(0.0, final_time, settings.report_step_s, dtype=float)
    if report_times.size == 0 or report_times[-1] < final_time:
        report_times = np.append(report_times, final_time)
    states = np.vstack(
        (
            np.interp(report_times, internal_times, internal_distance),
            np.interp(report_times, internal_times, internal_vehicle_speed),
            np.interp(report_times, internal_times, internal_wheel_speed),
        )
    )

    numeric: dict[str, list[float]] = {
        "time_s": [],
        "distance_m": [],
        "vehicle_speed_mps": [],
        "vehicle_speed_kmh": [],
        "vehicle_acceleration_mps2": [],
        "wheel_speed_rad_s": [],
        "wheel_speed_rpm": [],
        "wheel_patch_speed_mps": [],
        "tire_slip_speed_mps": [],
        "tire_force_n": [],
        "tire_limit_n": [],
        "tire_utilization": [],
        "elevation_m": [],
        "grade_degrees": [],
        "curvature_1_per_m": [],
        "bank_angle_degrees": [],
        "friction_coefficient": [],
        "rolling_resistance_coefficient": [],
        "normal_load_scale": [],
        "physical_corner_speed_limit_mps": [],
        "target_speed_mps": [],
        "throttle": [],
        "brake_force_command_n": [],
        "brake_torque_wheel_nm": [],
        "cvt_ratio": [],
        "ratio_required": [],
        "engine_speed_rpm": [],
        "engine_torque_nm": [],
        "engine_power_w": [],
        "transmitted_power_w": [],
        "drive_torque_wheel_nm": [],
        "clutch_loss_power_w": [],
        "operating_point_shortfall_power_w": [],
        "tire_slip_loss_power_w": [],
        "brake_loss_power_w": [],
        "rolling_loss_power_w": [],
        "aerodynamic_loss_power_w": [],
        "obstacle_loss_power_w": [],
        "grade_power_w": [],
        "grade_force_n": [],
        "rolling_force_n": [],
        "aerodynamic_force_n": [],
        "obstacle_force_n": [],
        "lateral_force_n": [],
    }
    text: dict[str, list[str]] = {
        "section": [],
        "surface": [],
        "cvt_mode": [],
        "active_features": [],
        "active_feature_types": [],
    }

    for index, report_time in enumerate(report_times):
        state = states[:, index]
        dynamics = evaluate_dynamics(
            state=state,
            case=case,
            track=track,
            settings=settings,
        )
        distance = max(0.0, float(state[0]))
        speed = max(0.0, float(state[1]))
        wheel_speed = max(0.0, float(state[2]))
        target_speed = dynamics.target_speed_mps
        numeric["time_s"].append(float(report_time))
        numeric["distance_m"].append(distance)
        numeric["vehicle_speed_mps"].append(speed)
        numeric["vehicle_speed_kmh"].append(3.6 * speed)
        numeric["vehicle_acceleration_mps2"].append(dynamics.dv_dt)
        numeric["wheel_speed_rad_s"].append(wheel_speed)
        numeric["wheel_speed_rpm"].append(wheel_speed * RAD_PER_SECOND_TO_RPM)
        numeric["wheel_patch_speed_mps"].append(case.tire.wheel_radius_m * wheel_speed)
        numeric["tire_slip_speed_mps"].append(dynamics.tire_slip_speed_mps)
        numeric["tire_force_n"].append(dynamics.tire_force_n)
        numeric["tire_limit_n"].append(dynamics.tire_limit_n)
        numeric["tire_utilization"].append(dynamics.tire_utilization)
        numeric["elevation_m"].append(dynamics.track.elevation_m)
        numeric["grade_degrees"].append(dynamics.track.grade_degrees)
        numeric["curvature_1_per_m"].append(dynamics.track.curvature_1_per_m)
        numeric["bank_angle_degrees"].append(dynamics.track.bank_angle_degrees)
        numeric["friction_coefficient"].append(dynamics.track.friction_coefficient)
        numeric["rolling_resistance_coefficient"].append(
            dynamics.track.rolling_resistance_coefficient
        )
        numeric["normal_load_scale"].append(dynamics.track.normal_load_scale)
        numeric["physical_corner_speed_limit_mps"].append(
            float("nan")
            if dynamics.track.physical_corner_speed_limit_mps is None
            else dynamics.track.physical_corner_speed_limit_mps
        )
        numeric["target_speed_mps"].append(
            float("nan") if not isfinite(target_speed) else target_speed
        )
        numeric["throttle"].append(dynamics.throttle)
        numeric["brake_force_command_n"].append(dynamics.brake_force_command_n)
        numeric["brake_torque_wheel_nm"].append(dynamics.brake_torque_wheel_nm)
        numeric["cvt_ratio"].append(dynamics.powertrain.cvt_ratio)
        numeric["ratio_required"].append(dynamics.powertrain.ratio_required)
        numeric["engine_speed_rpm"].append(dynamics.powertrain.engine_speed_rpm)
        numeric["engine_torque_nm"].append(dynamics.powertrain.engine_torque_nm)
        numeric["engine_power_w"].append(dynamics.powertrain.engine_power_w)
        numeric["transmitted_power_w"].append(dynamics.powertrain.transmitted_power_w)
        numeric["drive_torque_wheel_nm"].append(dynamics.powertrain.drive_torque_wheel_nm)
        numeric["clutch_loss_power_w"].append(dynamics.powertrain.clutch_loss_power_w)
        numeric["operating_point_shortfall_power_w"].append(
            dynamics.powertrain.operating_point_shortfall_power_w
        )
        numeric["tire_slip_loss_power_w"].append(dynamics.tire_slip_loss_power_w)
        numeric["brake_loss_power_w"].append(dynamics.brake_loss_power_w)
        numeric["rolling_loss_power_w"].append(dynamics.rolling_loss_power_w)
        numeric["aerodynamic_loss_power_w"].append(dynamics.aerodynamic_loss_power_w)
        numeric["obstacle_loss_power_w"].append(dynamics.obstacle_loss_power_w)
        numeric["grade_power_w"].append(dynamics.grade_power_w)
        numeric["grade_force_n"].append(dynamics.grade_force_n)
        numeric["rolling_force_n"].append(dynamics.rolling_force_n)
        numeric["aerodynamic_force_n"].append(dynamics.aerodynamic_force_n)
        numeric["obstacle_force_n"].append(dynamics.obstacle_force_n)
        numeric["lateral_force_n"].append(dynamics.lateral_force_n)
        text["section"].append(dynamics.track.section_name)
        text["surface"].append(dynamics.track.surface)
        text["cvt_mode"].append(dynamics.powertrain.mode)
        text["active_features"].append(" | ".join(dynamics.track.active_features))
        text["active_feature_types"].append(
            " | ".join(dynamics.track.active_feature_types)
        )

    return SimulationTrace(
        case_name=case.name,
        track_name=track.name,
        completed=completed,
        termination_reason=reason,
        numeric={key: np.asarray(values, dtype=float) for key, values in numeric.items()},
        text={key: tuple(values) for key, values in text.items()},
    )
