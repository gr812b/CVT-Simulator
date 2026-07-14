from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

import numpy as np

from simulation import SimulationTrace

WATTS_PER_HORSEPOWER = 745.6998715822702


def _integral(values: np.ndarray, time_s: np.ndarray) -> float:
    if len(time_s) < 2:
        return 0.0
    return float(np.trapezoid(values, time_s))


def _time_with_mask(mask: np.ndarray, time_s: np.ndarray) -> float:
    return _integral(mask.astype(float), time_s)


def _distance_with_mask(mask: np.ndarray, speed_mps: np.ndarray, time_s: np.ndarray) -> float:
    return _integral(mask.astype(float) * speed_mps, time_s)


def summarize_trace(
    trace: SimulationTrace,
    *,
    target_engine_rpm: float,
    ideal_peak_power_w: float,
    engine_rpm_band: float = 200.0,
) -> dict[str, Any]:
    n = trace.numeric
    t = n["time_s"]
    speed = n["vehicle_speed_mps"]
    modes = np.asarray(trace.text["cvt_mode"], dtype=object)
    throttle = n["throttle"]
    target_low = target_engine_rpm - engine_rpm_band
    target_high = target_engine_rpm + engine_rpm_band
    full_throttle = throttle > 0.95
    outside_band = full_throttle & (
        (n["engine_speed_rpm"] < target_low) | (n["engine_speed_rpm"] > target_high)
    )
    low_mode = np.asarray([mode.startswith("low_ratio") for mode in modes], dtype=bool)
    variable_mode = modes == "variable_peak_power"
    high_mode = modes == "high_ratio_fixed"
    traction_limited = n["tire_utilization"] >= 0.95
    slipping = np.abs(n["tire_slip_speed_mps"]) >= 0.25
    braking = n["brake_force_command_n"] > 1.0

    lap_time = trace.final_time_s
    distance = trace.final_distance_m
    average_speed = distance / max(lap_time, 1.0e-12)
    ideal_available_energy = _integral(
        throttle * ideal_peak_power_w * np.ones_like(t),
        t,
    )
    engine_energy = _integral(n["engine_power_w"], t)
    transmitted_energy = _integral(n["transmitted_power_w"], t)
    clutch_loss = _integral(n["clutch_loss_power_w"], t)
    operating_shortfall = _integral(n["operating_point_shortfall_power_w"], t)
    tire_loss = _integral(n["tire_slip_loss_power_w"], t)
    brake_loss = _integral(n["brake_loss_power_w"], t)
    rolling_loss = _integral(n["rolling_loss_power_w"], t)
    aero_loss = _integral(n["aerodynamic_loss_power_w"], t)
    obstacle_loss = _integral(n["obstacle_loss_power_w"], t)
    grade_work = _integral(n["grade_power_w"], t)

    finite_ratio_loss = clutch_loss + operating_shortfall

    def average_power_hp(energy_j: float, duration_s: float = lap_time) -> float:
        return energy_j / max(duration_s, 1.0e-12) / WATTS_PER_HORSEPOWER

    summary: dict[str, Any] = {
        "case": trace.case_name,
        "track": trace.track_name,
        "completed": trace.completed,
        "termination_reason": trace.termination_reason,
        "lap_time_s": lap_time,
        "distance_m": distance,
        "average_speed_mps": average_speed,
        "average_speed_kmh": 3.6 * average_speed,
        "maximum_speed_mps": float(np.max(speed)),
        "maximum_speed_kmh": 3.6 * float(np.max(speed)),
        "minimum_engine_rpm": float(np.min(n["engine_speed_rpm"])),
        "maximum_engine_rpm": float(np.max(n["engine_speed_rpm"])),
        "mean_engine_rpm_full_throttle": float(
            np.mean(n["engine_speed_rpm"][full_throttle]) if np.any(full_throttle) else 0.0
        ),
        "time_outside_target_rpm_band_s": _time_with_mask(outside_band, t),
        "distance_outside_target_rpm_band_m": _distance_with_mask(outside_band, speed, t),
        "time_low_ratio_s": _time_with_mask(low_mode, t),
        "time_variable_ratio_s": _time_with_mask(variable_mode, t),
        "time_high_ratio_s": _time_with_mask(high_mode, t),
        "distance_low_ratio_m": _distance_with_mask(low_mode, speed, t),
        "distance_variable_ratio_m": _distance_with_mask(variable_mode, speed, t),
        "distance_high_ratio_m": _distance_with_mask(high_mode, speed, t),
        "fraction_time_low_ratio": _time_with_mask(low_mode, t) / max(lap_time, 1.0e-12),
        "fraction_time_variable_ratio": _time_with_mask(variable_mode, t) / max(lap_time, 1.0e-12),
        "fraction_time_high_ratio": _time_with_mask(high_mode, t) / max(lap_time, 1.0e-12),
        "time_traction_limited_s": _time_with_mask(traction_limited, t),
        "distance_traction_limited_m": _distance_with_mask(traction_limited, speed, t),
        "time_tire_slipping_s": _time_with_mask(slipping, t),
        "maximum_abs_tire_slip_speed_mps": float(np.max(np.abs(n["tire_slip_speed_mps"]))),
        "maximum_tire_utilization": float(np.max(n["tire_utilization"])),
        "time_braking_s": _time_with_mask(braking, t),
        "engine_energy_kj": engine_energy / 1000.0,
        "transmitted_energy_kj": transmitted_energy / 1000.0,
        "clutch_loss_energy_kj": clutch_loss / 1000.0,
        "engine_operating_shortfall_energy_kj": operating_shortfall / 1000.0,
        "finite_ratio_opportunity_loss_energy_kj": finite_ratio_loss / 1000.0,
        "engine_average_power_hp": average_power_hp(engine_energy),
        "transmitted_average_power_hp": average_power_hp(transmitted_energy),
        "clutch_loss_average_power_hp": average_power_hp(clutch_loss),
        "engine_operating_shortfall_average_power_hp": average_power_hp(operating_shortfall),
        "finite_ratio_opportunity_loss_average_power_hp": average_power_hp(finite_ratio_loss),
        "tire_slip_loss_average_power_hp": average_power_hp(tire_loss),
        "brake_loss_average_power_hp": average_power_hp(brake_loss),
        "rolling_loss_average_power_hp": average_power_hp(rolling_loss),
        "aerodynamic_loss_average_power_hp": average_power_hp(aero_loss),
        "obstacle_loss_average_power_hp": average_power_hp(obstacle_loss),
        "tire_slip_loss_energy_kj": tire_loss / 1000.0,
        "brake_loss_energy_kj": brake_loss / 1000.0,
        "rolling_loss_energy_kj": rolling_loss / 1000.0,
        "aerodynamic_loss_energy_kj": aero_loss / 1000.0,
        "obstacle_loss_energy_kj": obstacle_loss / 1000.0,
        "net_grade_work_kj": grade_work / 1000.0,
        "ideal_peak_power_available_energy_kj": ideal_available_energy / 1000.0,
        "mode_sample_counts": dict(Counter(str(mode) for mode in modes)),
    }

    section_summaries: list[dict[str, Any]] = []
    sections = np.asarray(trace.text["section"], dtype=object)
    ordered_names: list[str] = []
    for name in sections:
        if str(name) not in ordered_names:
            ordered_names.append(str(name))
    for name in ordered_names:
        mask = sections == name
        section_time = _time_with_mask(mask, t)
        section_distance = _distance_with_mask(mask, speed, t)
        section_finite_ratio_loss_j = _integral(
            np.where(
                mask,
                n["clutch_loss_power_w"] + n["operating_point_shortfall_power_w"],
                0.0,
            ),
            t,
        )
        section_tire_loss_j = _integral(
            np.where(mask, n["tire_slip_loss_power_w"], 0.0), t
        )
        section_obstacle_loss_j = _integral(
            np.where(mask, n["obstacle_loss_power_w"], 0.0), t
        )
        section_summaries.append(
            {
                "section": name,
                "time_s": section_time,
                "distance_m": section_distance,
                "average_speed_kmh": 3.6 * section_distance / max(section_time, 1.0e-12),
                "maximum_speed_kmh": 3.6 * float(np.max(speed[mask])) if np.any(mask) else 0.0,
                "time_low_ratio_s": _time_with_mask(mask & low_mode, t),
                "time_variable_ratio_s": _time_with_mask(mask & variable_mode, t),
                "time_high_ratio_s": _time_with_mask(mask & high_mode, t),
                "time_outside_target_rpm_band_s": _time_with_mask(mask & outside_band, t),
                "finite_ratio_opportunity_loss_kj": section_finite_ratio_loss_j / 1000.0,
                "finite_ratio_opportunity_loss_average_power_hp": average_power_hp(
                    section_finite_ratio_loss_j, section_time
                ),
                "tire_slip_loss_kj": section_tire_loss_j / 1000.0,
                "tire_slip_loss_average_power_hp": average_power_hp(
                    section_tire_loss_j, section_time
                ),
                "obstacle_loss_kj": section_obstacle_loss_j / 1000.0,
                "obstacle_loss_average_power_hp": average_power_hp(
                    section_obstacle_loss_j, section_time
                ),
            }
        )
    summary["sections"] = section_summaries

    feature_labels = np.asarray(trace.text.get("active_features", ("",) * len(t)), dtype=object)
    ordered_features: list[str] = []
    for label in feature_labels:
        for name in (part.strip() for part in str(label).split("|")):
            if name and name not in ordered_features:
                ordered_features.append(name)
    feature_summaries: list[dict[str, Any]] = []
    for name in ordered_features:
        mask = np.asarray(
            [name in {part.strip() for part in str(label).split("|") if part.strip()} for label in feature_labels],
            dtype=bool,
        )
        feature_time = _time_with_mask(mask, t)
        feature_distance = _distance_with_mask(mask, speed, t)
        feature_obstacle_loss_j = _integral(
            np.where(mask, n["obstacle_loss_power_w"], 0.0), t
        )
        feature_tire_loss_j = _integral(
            np.where(mask, n["tire_slip_loss_power_w"], 0.0), t
        )
        feature_summaries.append(
            {
                "feature": name,
                "time_s": feature_time,
                "distance_m": feature_distance,
                "entry_speed_kmh": 3.6 * float(speed[np.flatnonzero(mask)[0]]) if np.any(mask) else 0.0,
                "exit_speed_kmh": 3.6 * float(speed[np.flatnonzero(mask)[-1]]) if np.any(mask) else 0.0,
                "minimum_speed_kmh": 3.6 * float(np.min(speed[mask])) if np.any(mask) else 0.0,
                "maximum_speed_kmh": 3.6 * float(np.max(speed[mask])) if np.any(mask) else 0.0,
                "obstacle_loss_kj": feature_obstacle_loss_j / 1000.0,
                "obstacle_loss_average_power_hp": average_power_hp(
                    feature_obstacle_loss_j, feature_time
                ),
                "tire_slip_loss_kj": feature_tire_loss_j / 1000.0,
                "time_low_ratio_s": _time_with_mask(mask & low_mode, t),
                "time_high_ratio_s": _time_with_mask(mask & high_mode, t),
                "time_traction_limited_s": _time_with_mask(mask & traction_limited, t),
            }
        )
    summary["features"] = feature_summaries
    return summary


def compare_to_reference(
    summary: Mapping[str, Any],
    reference: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(summary)
    lap_time = float(summary["lap_time_s"])
    reference_lap_time = float(reference["lap_time_s"])
    result.update(
        {
            "reference_lap_time_s": reference_lap_time,
            "lap_time_penalty_vs_infinite_s": lap_time - reference_lap_time,
            "lap_time_penalty_vs_infinite_percent": 100.0
            * (lap_time - reference_lap_time)
            / max(reference_lap_time, 1.0e-12),
            "average_speed_delta_vs_infinite_kmh": float(summary["average_speed_kmh"])
            - float(reference["average_speed_kmh"]),
            "maximum_speed_delta_vs_infinite_kmh": float(summary["maximum_speed_kmh"])
            - float(reference["maximum_speed_kmh"]),
            "extra_tire_slip_loss_vs_infinite_kj": float(summary["tire_slip_loss_energy_kj"])
            - float(reference["tire_slip_loss_energy_kj"]),
            "extra_brake_loss_vs_infinite_kj": float(summary["brake_loss_energy_kj"])
            - float(reference["brake_loss_energy_kj"]),
        }
    )
    return result
