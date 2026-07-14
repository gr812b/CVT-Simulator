from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np

from simulation import SimulationTrace
from track_builder import Track

WATTS_PER_HORSEPOWER = 745.6998715822702


def _track_boundaries(ax: plt.Axes, track: Track) -> None:
    boundaries = track.boundaries_m
    for boundary in boundaries[1:-1]:
        ax.axvline(boundary, linestyle=":", linewidth=0.8, alpha=0.45)


def _save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    return path


def plot_single_run(
    *,
    trace: SimulationTrace,
    reference: SimulationTrace,
    track: Track,
    target_engine_rpm: float,
    minimum_ratio: float,
    maximum_ratio: float,
    output_dir: Path,
    show: bool,
) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    x = trace.numeric["distance_m"]
    xr = reference.numeric["distance_m"]
    paths: list[Path] = []

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(x, trace.numeric["vehicle_speed_kmh"], label="Bounded perfect CVT")
    ax.plot(xr, reference.numeric["vehicle_speed_kmh"], label="Infinite CVT reference", linestyle="--")
    speed_limit = trace.numeric["physical_corner_speed_limit_mps"] * 3.6
    if np.any(np.isfinite(speed_limit)):
        ax.plot(x, speed_limit, label="Physical corner limit", linestyle=":")
    ax.set_xlabel("Distance [m]")
    ax.set_ylabel("Vehicle speed [km/h]")
    ax.set_title(f"{track.name}: speed")
    ax.grid(True, alpha=0.25)
    ax.legend()
    _track_boundaries(ax, track)
    paths.append(_save(fig, output_dir / "01_speed_vs_distance.png"))

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(x, trace.numeric["cvt_ratio"], label="Selected CVT speed ratio")
    axes[0].axhline(maximum_ratio, linestyle=":", label="Low-ratio bound")
    axes[0].axhline(minimum_ratio, linestyle=":", label="High-ratio bound")
    axes[0].set_ylabel(r"CVT ratio $\omega_e/\omega_s$")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend()
    axes[1].plot(x, trace.numeric["engine_speed_rpm"], label="Bounded engine speed")
    axes[1].plot(xr, reference.numeric["engine_speed_rpm"], linestyle="--", label="Infinite reference")
    axes[1].axhline(target_engine_rpm, linestyle=":", label="Peak-power target")
    axes[1].set_xlabel("Distance [m]")
    axes[1].set_ylabel("Engine speed [rpm]")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend()
    for ax in axes:
        _track_boundaries(ax, track)
    fig.suptitle(f"{track.name}: ratio use and engine operating point")
    paths.append(_save(fig, output_dir / "02_ratio_and_engine_rpm.png"))

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(x, trace.numeric["engine_power_w"] / WATTS_PER_HORSEPOWER, label="Engine power")
    ax.plot(x, trace.numeric["transmitted_power_w"] / WATTS_PER_HORSEPOWER, label="Power delivered to wheel rotation")
    ax.plot(x, trace.numeric["clutch_loss_power_w"] / WATTS_PER_HORSEPOWER, label="Launch-clutch loss")
    ax.plot(
        x,
        trace.numeric["operating_point_shortfall_power_w"] / WATTS_PER_HORSEPOWER,
        label="Off-peak power shortfall",
    )
    ax.set_xlabel("Distance [m]")
    ax.set_ylabel("Power [hp]")
    ax.set_title(f"{track.name}: finite-ratio power availability")
    ax.grid(True, alpha=0.25)
    ax.legend(ncol=2)
    _track_boundaries(ax, track)
    paths.append(_save(fig, output_dir / "03_power_and_cvt_opportunity_losses.png"))

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(x, trace.numeric["tire_slip_speed_mps"], label="Tire slip speed")
    axes[0].axhline(0.0, linewidth=0.8)
    axes[0].set_ylabel("Slip speed [m/s]")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend()
    axes[1].plot(x, trace.numeric["tire_utilization"], label="Tire-force utilization")
    axes[1].axhline(1.0, linestyle=":", label="Traction limit")
    axes[1].set_xlabel("Distance [m]")
    axes[1].set_ylabel("Utilization")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend()
    for ax in axes:
        _track_boundaries(ax, track)
    fig.suptitle(f"{track.name}: tire slip and traction")
    paths.append(_save(fig, output_dir / "04_tire_slip_and_utilization.png"))

    loss_power_series = {
        "Clutch": trace.numeric["clutch_loss_power_w"],
        "Off-peak shortfall": trace.numeric["operating_point_shortfall_power_w"],
        "Tire slip": trace.numeric["tire_slip_loss_power_w"],
        "Braking": trace.numeric["brake_loss_power_w"],
        "Rolling": trace.numeric["rolling_loss_power_w"],
        "Aerodynamic": trace.numeric["aerodynamic_loss_power_w"],
        "Obstacles": trace.numeric["obstacle_loss_power_w"],
    }
    fig, ax = plt.subplots(figsize=(10, 6))
    for label, power_w in loss_power_series.items():
        ax.plot(x, power_w / WATTS_PER_HORSEPOWER, label=label)
    ax.set_xlabel("Distance [m]")
    ax.set_ylabel("Loss power [hp]")
    ax.set_title(f"{track.name}: loss and dissipation power channels")
    ax.grid(True, alpha=0.25)
    ax.legend(ncol=2)
    _track_boundaries(ax, track)
    paths.append(_save(fig, output_dir / "05_loss_power_channels_hp.png"))

    fig, axes = plt.subplots(4, 1, figsize=(13, 12), sharex=True)
    axes[0].plot(x, trace.numeric["elevation_m"], label="Elevation")
    axes[0].set_ylabel("Elevation [m]")
    axes[0].legend()

    axes[1].plot(x, trace.numeric["grade_degrees"], label="Grade")
    axes[1].plot(
        x,
        100.0 * trace.numeric["curvature_1_per_m"],
        label="Curvature ×100",
    )
    axes[1].plot(
        x,
        trace.numeric["bank_angle_degrees"],
        label="Bank angle [deg]",
    )
    axes[1].set_ylabel("Grade / bank [deg] / curvature")
    axes[1].legend()

    axes[2].plot(x, trace.numeric["friction_coefficient"], label="Tire-road μ")
    axes[2].plot(
        x,
        trace.numeric["rolling_resistance_coefficient"],
        label="Rolling coefficient",
    )
    axes[2].plot(x, trace.numeric["normal_load_scale"], label="Normal-load scale")
    axes[2].set_ylabel("Surface / load")
    axes[2].legend(ncol=3)

    axes[3].plot(x, trace.numeric["obstacle_force_n"], label="Obstacle resistance")
    axes[3].plot(x, np.abs(trace.numeric["lateral_force_n"]), label="Lateral force demand")
    axes[3].set_ylabel("Force [N]")
    axes[3].set_xlabel("Distance [m]")
    axes[3].legend()

    for ax in axes:
        ax.grid(True, alpha=0.25)
        _track_boundaries(ax, track)
    for feature_index, feature in enumerate(track.features):
        for ax in axes:
            ax.axvspan(feature.start_m, feature.end_m, alpha=0.06)
        axes[0].annotate(
            feature.name,
            xy=((feature.start_m + feature.end_m) / 2.0, 1.0),
            xycoords=("data", "axes fraction"),
            xytext=(0, -4 - 12 * (feature_index % 3)),
            textcoords="offset points",
            rotation=90,
            va="top",
            ha="center",
            fontsize=7,
        )
    fig.suptitle(f"{track.name}: compiled track geometry and physical features")
    paths.append(_save(fig, output_dir / "06_track_profile_and_features.png"))

    fig, axes = plt.subplots(3, 2, figsize=(15, 13), sharex=True)
    axes[0, 0].plot(x, trace.numeric["vehicle_speed_kmh"], label="Bounded")
    axes[0, 0].plot(xr, reference.numeric["vehicle_speed_kmh"], linestyle="--", label="Infinite")
    axes[0, 0].set_ylabel("Speed [km/h]")
    axes[0, 0].legend()

    axes[0, 1].plot(x, trace.numeric["engine_speed_rpm"])
    axes[0, 1].axhline(target_engine_rpm, linestyle=":")
    axes[0, 1].set_ylabel("Engine [rpm]")

    axes[1, 0].plot(x, trace.numeric["cvt_ratio"])
    axes[1, 0].axhline(minimum_ratio, linestyle=":")
    axes[1, 0].axhline(maximum_ratio, linestyle=":")
    axes[1, 0].set_ylabel(r"$\omega_e/\omega_s$")

    axes[1, 1].plot(x, trace.numeric["tire_slip_speed_mps"])
    axes[1, 1].set_ylabel("Tire slip [m/s]")

    axes[2, 0].plot(x, trace.numeric["clutch_loss_power_w"] / WATTS_PER_HORSEPOWER, label="Clutch")
    axes[2, 0].plot(
        x,
        trace.numeric["operating_point_shortfall_power_w"] / WATTS_PER_HORSEPOWER,
        label="Off-peak",
    )
    axes[2, 0].set_ylabel("CVT opportunity loss [hp]")
    axes[2, 0].set_xlabel("Distance [m]")
    axes[2, 0].legend()

    axes[2, 1].plot(x, trace.numeric["grade_degrees"], label="Grade [deg]")
    axes[2, 1].plot(
        x,
        100.0 * trace.numeric["curvature_1_per_m"],
        label="Curvature ×100 [1/m]",
    )
    axes[2, 1].plot(
        x,
        trace.numeric["bank_angle_degrees"],
        label="Bank angle [deg]",
    )
    axes[2, 1].plot(x, trace.numeric["friction_coefficient"], label="Tire-road μ")
    axes[2, 1].set_ylabel("Track input")
    axes[2, 1].set_xlabel("Distance [m]")
    axes[2, 1].legend()

    for ax in axes.flat:
        ax.grid(True, alpha=0.25)
        _track_boundaries(ax, track)
    fig.suptitle(f"{track.name}: bounded perfect CVT study dashboard")
    paths.append(_save(fig, output_dir / "00_single_run_dashboard.png"))

    if show:
        plt.show()
    else:
        plt.close("all")
    return tuple(paths)


def plot_sweep(
    *,
    rows: Sequence[Mapping[str, Any]],
    output_dir: Path,
    independent_variable: str,
    baseline_minimum_ratio: float,
    baseline_maximum_ratio: float,
    baseline_final_drive: float,
    baseline_wheel_radius_m: float,
    show: bool,
) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    completed = [row for row in rows if bool(row.get("completed", False))]
    if not completed:
        return tuple()

    variable_labels = {
        "minimum_speed_ratio": "Minimum CVT ratio (high-gear end)",
        "maximum_speed_ratio": "Maximum CVT ratio (low-gear end)",
        "final_drive_ratio": "Final-drive ratio",
        "wheel_radius_in": "Wheel radius [in]",
    }
    if independent_variable not in variable_labels:
        raise ValueError(
            f"Unsupported independent variable {independent_variable!r}; "
            f"choose from {sorted(variable_labels)}"
        )

    baseline_values = {
        "minimum_speed_ratio": baseline_minimum_ratio,
        "maximum_speed_ratio": baseline_maximum_ratio,
        "final_drive_ratio": baseline_final_drive,
        "wheel_radius_in": baseline_wheel_radius_m / 0.0254,
    }
    parameter_keys = tuple(variable_labels)

    x_all = np.asarray([float(row[independent_variable]) for row in completed])
    lap_all = np.asarray([float(row["lap_time_s"]) for row in completed])
    loss_hp_all = np.asarray(
        [float(row["finite_ratio_opportunity_loss_average_power_hp"]) for row in completed]
    )

    x_values = sorted(set(float(value) for value in x_all))

    def baseline_distance(row: Mapping[str, Any]) -> float:
        distance = 0.0
        for key in parameter_keys:
            if key == independent_variable:
                continue
            target = baseline_values[key]
            scale = max(abs(target), 1.0)
            distance += abs(float(row[key]) - target) / scale
        return distance

    baseline_slice = [
        min(
            (row for row in completed if abs(float(row[independent_variable]) - x_value) < 1.0e-12),
            key=baseline_distance,
        )
        for x_value in x_values
    ]
    x_slice = np.asarray([float(row[independent_variable]) for row in baseline_slice])
    lap_slice = np.asarray([float(row["lap_time_s"]) for row in baseline_slice])
    loss_hp_slice = np.asarray(
        [float(row["finite_ratio_opportunity_loss_average_power_hp"]) for row in baseline_slice]
    )

    x_label = variable_labels[independent_variable]
    filename_key = {
        "minimum_speed_ratio": "minimum_cvt_ratio",
        "maximum_speed_ratio": "maximum_cvt_ratio",
        "final_drive_ratio": "final_drive",
        "wheel_radius_in": "wheel_radius",
    }[independent_variable]
    has_background_cases = len(completed) > len(baseline_slice)

    fig, ax = plt.subplots(figsize=(9, 6))
    if has_background_cases:
        ax.scatter(x_all, loss_hp_all, s=24, alpha=0.20, label="All swept combinations")
    ax.plot(x_slice, loss_hp_slice, marker="o", linewidth=1.8, label="Baseline configuration slice")
    ax.set_xlabel(x_label)
    ax.set_ylabel("Average finite-ratio opportunity-loss power [hp]")
    ax.set_title(f"Finite-ratio loss versus {x_label.lower()}")
    ax.grid(True, alpha=0.25)
    ax.legend()
    paths.append(_save(fig, output_dir / f"01_opportunity_loss_power_vs_{filename_key}.png"))

    fig, ax = plt.subplots(figsize=(9, 6))
    if has_background_cases:
        ax.scatter(x_all, lap_all, s=24, alpha=0.20, label="All swept combinations")
    ax.plot(x_slice, lap_slice, marker="o", linewidth=1.8, label="Baseline configuration slice")
    if independent_variable == "final_drive_ratio":
        ax.axvline(baseline_final_drive, linestyle=":", label="Baseline final drive")
    ax.set_xlabel(x_label)
    ax.set_ylabel("Lap time [s]")
    ax.set_title(f"Lap time versus {x_label.lower()}")
    ax.grid(True, alpha=0.25)
    ax.legend()
    paths.append(_save(fig, output_dir / f"02_lap_time_vs_{filename_key}.png"))

    fig, ax = plt.subplots(figsize=(9, 6))
    if has_background_cases:
        scatter = ax.scatter(loss_hp_all, lap_all, c=x_all, s=32, alpha=0.45)
        fig.colorbar(scatter, ax=ax, label=x_label)
    ax.plot(loss_hp_slice, lap_slice, marker="o", linewidth=1.8, label="Baseline configuration slice")
    for x_value, loss_value, lap_value in zip(x_slice, loss_hp_slice, lap_slice):
        ax.annotate(f"{x_value:.3g}", (loss_value, lap_value), xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("Average finite-ratio opportunity-loss power [hp]")
    ax.set_ylabel("Lap time [s]")
    ax.set_title("Lap time versus finite-ratio opportunity loss")
    ax.grid(True, alpha=0.25)
    ax.legend()
    paths.append(_save(fig, output_dir / "03_lap_time_vs_opportunity_loss_power_hp.png"))

    fig, ax = plt.subplots(figsize=(9, 6))
    outside = np.asarray([float(row["time_outside_target_rpm_band_s"]) for row in completed])
    high_time = np.asarray([float(row["time_high_ratio_s"]) for row in completed])
    scatter = ax.scatter(outside, high_time, c=lap_all, s=45)
    ax.set_xlabel("Time outside target engine-speed band [s]")
    ax.set_ylabel("Time at high-ratio bound [s]")
    ax.set_title("Engine-speed miss versus high-ratio saturation")
    ax.grid(True, alpha=0.25)
    fig.colorbar(scatter, ax=ax, label="Lap time [s]")
    paths.append(_save(fig, output_dir / "04_engine_band_vs_high_ratio_time.png"))

    closest = min(
        completed,
        key=lambda row: abs(float(row["final_drive_ratio"]) - baseline_final_drive)
        + 10.0 * abs(float(row["wheel_radius_m"]) - baseline_wheel_radius_m),
    )
    fixed_fd = float(closest["final_drive_ratio"])
    fixed_wheel = float(closest["wheel_radius_m"])
    subset = [
        row
        for row in completed
        if abs(float(row["final_drive_ratio"]) - fixed_fd) < 1.0e-9
        and abs(float(row["wheel_radius_m"]) - fixed_wheel) < 1.0e-9
    ]
    min_ratios = sorted({float(row["minimum_speed_ratio"]) for row in subset})
    max_ratios = sorted({float(row["maximum_speed_ratio"]) for row in subset})
    if len(min_ratios) > 1 and len(max_ratios) > 1:
        matrix = np.full((len(min_ratios), len(max_ratios)), np.nan)
        for row in subset:
            i = min_ratios.index(float(row["minimum_speed_ratio"]))
            j = max_ratios.index(float(row["maximum_speed_ratio"]))
            matrix[i, j] = float(row["lap_time_s"])
        fig, ax = plt.subplots(figsize=(9, 6))
        image = ax.imshow(matrix, origin="lower", aspect="auto")
        ax.set_xticks(range(len(max_ratios)), [f"{value:.2f}" for value in max_ratios])
        ax.set_yticks(range(len(min_ratios)), [f"{value:.2f}" for value in min_ratios])
        ax.set_xlabel("Maximum CVT ratio (low-gear end)")
        ax.set_ylabel("Minimum CVT ratio (high-gear end)")
        ax.set_title(
            f"Lap time [s] at final drive {fixed_fd:.3f}, wheel radius {fixed_wheel:.3f} m"
        )
        fig.colorbar(image, ax=ax, label="Lap time [s]")
        paths.append(_save(fig, output_dir / "05_ratio_bounds_lap_time_heatmap.png"))

    ranked = sorted(completed, key=lambda row: float(row["lap_time_s"]))[:20]
    labels = [
        f"q={float(row['minimum_speed_ratio']):.2f}–{float(row['maximum_speed_ratio']):.2f}, "
        f"G={float(row['final_drive_ratio']):.2f}, r={float(row['wheel_radius_in']):.1f}in"
        for row in ranked
    ]
    values = [float(row["lap_time_s"]) for row in ranked]
    fig, ax = plt.subplots(figsize=(11, 8))
    positions = np.arange(len(ranked))
    ax.barh(positions, values)
    ax.set_yticks(positions, labels)
    ax.invert_yaxis()
    ax.set_xlabel("Lap time [s]")
    ax.set_title("Fastest completed sweep configurations")
    ax.grid(True, axis="x", alpha=0.25)
    paths.append(_save(fig, output_dir / "06_fastest_configurations.png"))

    if show:
        plt.show()
    else:
        plt.close("all")
    return tuple(paths)
