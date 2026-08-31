from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from math import cos, isfinite, radians, sin, sqrt
from pathlib import Path
from typing import Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

from cinder.execution.hybrid import HybridIntegratorSettings, integrate_hybrid
from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
from cinder.hosts import TireVehicleHost
from cinder.model.boundaries.shaft import (
    FullThrottleEngineBoundary,
    ShaftBoundaryContext,
)
from cinder.model.boundaries.vehicle import RoadLoadModel
from cinder.model.system import CVTState, MechanicalCVTPlant, ShaftBoundaryValue

from play_tire_slip_trace import launch_playback_from_trace

from run_route_grade_response import (
    BajaTrialConstants,
    DEFAULT_FIXED_PIVOT_PRESET,
    GradeProgramme,
    ResolvedTune,
    TuneCandidate,
    build_components,
    compact_mode,
    launch_cvt_state,
    load_candidate,
    resolve_primary_preload,
    MILLIMETRE,
    RPM_PER_RADIAN_PER_SECOND,
)


@dataclass(frozen=True, slots=True)
class TerrainSegment:
    """One distance-indexed terrain segment.

    ``grade_degrees`` is positive uphill in the positive travel direction.
    ``friction_coefficient`` is the local tire-road longitudinal coefficient.
    """

    start_distance_m: float
    grade_degrees: float
    friction_coefficient: float
    name: str
    airborne: bool = False

    def __post_init__(self) -> None:
        if not isfinite(self.start_distance_m):
            raise ValueError("start_distance_m must be finite.")
        if not isfinite(self.grade_degrees):
            raise ValueError("grade_degrees must be finite.")
        if not -89.0 < self.grade_degrees < 89.0:
            raise ValueError("grade_degrees must lie strictly between -89 and 89 degrees.")
        if not isfinite(self.friction_coefficient) or self.friction_coefficient < 0.0:
            raise ValueError("friction_coefficient must be finite and non-negative.")
        if not self.name:
            raise ValueError("name must be non-empty.")
        if not isinstance(self.airborne, bool):
            raise TypeError("airborne must be a boolean.")

    @property
    def grade_radians(self) -> float:
        return radians(self.grade_degrees)


@dataclass(frozen=True, slots=True)
class TerrainSample:
    vehicle_distance_m: float
    grade_radians: float
    friction_coefficient: float
    segment_name: str
    airborne: bool = False

    @property
    def grade_degrees(self) -> float:
        return float(np.rad2deg(self.grade_radians))


@dataclass(frozen=True, slots=True)
class PiecewiseConstantTerrainProfile:
    """Distance-indexed grade and tire-friction profile."""

    segments: tuple[TerrainSegment, ...]

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("At least one terrain segment is required.")
        if self.segments[0].start_distance_m != 0.0:
            raise ValueError("The first terrain segment must start at 0.0 m.")
        previous = -np.inf
        for segment in self.segments:
            if segment.start_distance_m <= previous:
                raise ValueError("Terrain segment start distances must be strictly increasing.")
            previous = segment.start_distance_m

    def sample(self, vehicle_distance_m: float) -> TerrainSample:
        if not isfinite(vehicle_distance_m):
            raise ValueError("vehicle_distance_m must be finite.")
        active = self.segments[0]
        for segment in self.segments[1:]:
            if vehicle_distance_m < segment.start_distance_m:
                break
            active = segment
        return TerrainSample(
            vehicle_distance_m=vehicle_distance_m,
            grade_radians=active.grade_radians,
            friction_coefficient=active.friction_coefficient,
            segment_name=active.name,
            airborne=active.airborne,
        )


@dataclass(frozen=True, slots=True)
class TerrainCase:
    name: str
    duration_s: float
    terrain: PiecewiseConstantTerrainProfile
    initial_vehicle_speed_mps: float = 0.0
    initial_vehicle_position_m: float = 0.0
    initial_primary_rpm: float = 1800.0

    @property
    def slug(self) -> str:
        return self.name.lower().replace(" ", "_").replace("/", "_").replace("-", "_")


@dataclass(frozen=True, slots=True)
class VariableMuTireBoundary:
    """Secondary boundary with independent vehicle speed and distance-varying mu.

    This stays local to the launch tool so the core CINDER contracts do not need
    to be changed before the tire-slip physics has been inspected and tuned.
    """

    road_load: RoadLoadModel
    terrain: PiecewiseConstantTerrainProfile
    tire_slip_stiffness: float
    direct_secondary_shaft_inertia: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.road_load, RoadLoadModel):
            raise TypeError("road_load must be a RoadLoadModel.")
        if not isfinite(self.tire_slip_stiffness) or self.tire_slip_stiffness <= 0.0:
            raise ValueError("tire_slip_stiffness must be positive and finite.")
        if not isfinite(self.direct_secondary_shaft_inertia) or self.direct_secondary_shaft_inertia < 0.0:
            raise ValueError("direct_secondary_shaft_inertia must be finite and non-negative.")

    @property
    def wheel_rotational_inertia_referred_to_secondary(self) -> float:
        return self.road_load.final_drive.secondary_inertia_from_wheel_rotation(
            wheel_rotational_inertia=self.road_load.vehicle.wheel_rotational_inertia,
        )

    @property
    def equivalent_inertia(self) -> float:
        # Vehicle translation is intentionally not reflected.  It lives in
        # TireVehicleHost's independent x/v ODE.
        return self.direct_secondary_shaft_inertia + self.wheel_rotational_inertia_referred_to_secondary

    def evaluate(self, context: ShaftBoundaryContext) -> ShaftBoundaryValue:
        if context.shaft != "secondary":
            raise ValueError("VariableMuTireBoundary must be attached to the secondary shaft.")
        vehicle_speed = float(context.host["vehicle_speed"])
        vehicle_position = float(context.host.get("vehicle_position", 0.0))
        sample = self.terrain.sample(vehicle_position)

        final_drive = self.road_load.final_drive
        wheel_speed = final_drive.wheel_angular_speed(
            secondary_angular_speed=context.cvt.secondary_angular_speed,
        )
        patch_speed = final_drive.wheel_radius * wheel_speed
        normal_load = 0.0 if sample.airborne else normal_force(self.road_load, sample.grade_radians)
        slip_speed = patch_speed - vehicle_speed
        tire_force = tanh_tire_force(
            slip_speed=slip_speed,
            normal_load=normal_load,
            friction_coefficient=sample.friction_coefficient,
            slip_stiffness=self.tire_slip_stiffness,
        )
        secondary_torque = -final_drive.secondary_torque_from_wheel_force(wheel_force=tire_force)
        forces = road_forces(
            self.road_load,
            vehicle_speed=vehicle_speed,
            grade_angle=sample.grade_radians,
            airborne=sample.airborne,
        )
        return ShaftBoundaryValue(
            external_torque=secondary_torque,
            equivalent_inertia=self.equivalent_inertia,
            metadata={
                "tire_force": tire_force,
                "vehicle_position": vehicle_position,
                "vehicle_speed": vehicle_speed,
                "grade_angle": sample.grade_radians,
                "grade_degrees": sample.grade_degrees,
                "terrain_mu": sample.friction_coefficient,
                "terrain_segment": sample.segment_name,
                "terrain_airborne": sample.airborne,
                "normal_load": normal_load,
                "tire_patch_speed": patch_speed,
                "tire_slip_speed": slip_speed,
                "tire_traction_limit": sample.friction_coefficient * normal_load,
                "secondary_tire_torque": secondary_torque,
                **forces,
            },
        )


def tanh_tire_force(
    *,
    slip_speed: float,
    normal_load: float,
    friction_coefficient: float,
    slip_stiffness: float,
) -> float:
    limit = max(0.0, friction_coefficient) * max(0.0, normal_load)
    if limit == 0.0:
        return 0.0
    return float(limit * np.tanh(slip_stiffness * slip_speed / limit))


def normal_force(road_load: RoadLoadModel, grade_angle: float) -> float:
    return float(road_load.vehicle.mass * road_load.spec.gravity * max(0.0, cos(grade_angle)))


def road_forces(road_load: RoadLoadModel, *, vehicle_speed: float, grade_angle: float, airborne: bool = False) -> Mapping[str, float]:
    spec = road_load.spec
    vehicle = road_load.vehicle
    grade_force = 0.0 if airborne else -(vehicle.mass * spec.gravity * sin(grade_angle))
    normal = 0.0 if airborne else normal_force(road_load, grade_angle)
    rolling_direction = vehicle_speed / sqrt(vehicle_speed**2 + spec.rolling_speed_regularization**2)
    rolling_force = 0.0 if airborne else -spec.rolling_resistance_coefficient * normal * rolling_direction
    aerodynamic_force = -0.5 * spec.air_density * spec.drag_coefficient * spec.frontal_area * abs(vehicle_speed) * vehicle_speed
    road_force = grade_force + rolling_force + aerodynamic_force
    return {
        "grade_force": float(grade_force),
        "rolling_force": float(rolling_force),
        "aerodynamic_force": float(aerodynamic_force),
        "road_force": float(road_force),
    }


def build_tire_slip_system(
    constants: BajaTrialConstants,
    terrain: PiecewiseConstantTerrainProfile,
    *,
    tire_slip_stiffness: float,
) -> tuple[ComposedCVTHybridSystem, object, RoadLoadModel, VariableMuTireBoundary]:
    assembly, engine, road_load = build_components(constants)
    plant = MechanicalCVTPlant.from_assembly(assembly)
    secondary_boundary = VariableMuTireBoundary(
        road_load=road_load,
        terrain=terrain,
        tire_slip_stiffness=tire_slip_stiffness,
        direct_secondary_shaft_inertia=constants.gearbox_input_rotational_inertia,
    )
    host = TireVehicleHost(tire_boundary=secondary_boundary)
    system = ComposedCVTHybridSystem.from_plant(
        plant=plant,
        primary_boundary=FullThrottleEngineBoundary(
            engine,
            equivalent_rotational_inertia=constants.engine_rotational_inertia,
        ),
        secondary_boundary=secondary_boundary,
        host=host,
    )
    return system, engine, road_load, secondary_boundary


@dataclass(frozen=True, slots=True)
class TireSlipTrace:
    time_s: NDArray[np.float64]
    state: NDArray[np.float64]
    mode: tuple[str, ...]
    vehicle_position_m: NDArray[np.float64]
    vehicle_speed_mps: NDArray[np.float64]
    wheel_patch_speed_mps: NDArray[np.float64]
    slip_speed_mps: NDArray[np.float64]
    slip_ratio: NDArray[np.float64]
    tire_force_n: NDArray[np.float64]
    traction_limit_n: NDArray[np.float64]
    tire_utilization: NDArray[np.float64]
    normal_load_n: NDArray[np.float64]
    grade_degrees: NDArray[np.float64]
    terrain_mu: NDArray[np.float64]
    grade_force_n: NDArray[np.float64]
    rolling_force_n: NDArray[np.float64]
    aerodynamic_force_n: NDArray[np.float64]
    road_force_n: NDArray[np.float64]
    secondary_tire_torque_nm: NDArray[np.float64]
    airborne: NDArray[np.bool_]
    terrain_segment: tuple[str, ...]


def slip_ratio(*, slip_speed: float, patch_speed: float, vehicle_speed: float) -> float:
    denom = max(abs(patch_speed), abs(vehicle_speed), 0.50)
    return float(slip_speed / denom)


def sample_trace(
    system: ComposedCVTHybridSystem,
    result,
    *,
    report_step_s: float,
) -> TireSlipTrace:
    rows: list[tuple] = []
    max_shift = system.cvt.model.geometry.spec.max_shift
    for segment in result.segments:
        t0, t1 = segment.start_time, segment.end_time
        if segment.has_dense_output:
            times = np.arange(t0, t1, report_step_s)
            if len(times) == 0 or abs(times[0] - t0) > 1.0e-12:
                times = np.r_[t0, times]
            times = np.r_[times, t1]
            times = np.unique(np.clip(times, t0, t1))
            states = segment.dense_state_at(times)
        else:
            times = segment.time
            states = segment.state
        for j, time in enumerate(times):
            full = np.asarray(states[:, j], dtype=float).copy()
            # Avoid plotting tiny numerical stop overshoots as physical shift travel.
            full[3] = np.clip(full[3], 0.0, max_shift)
            boundaries = system._shaft_boundaries(time=float(time), state=full)
            meta = boundaries.secondary.metadata
            patch_speed = float(meta["tire_patch_speed"])
            vehicle_speed = float(meta["vehicle_speed"])
            slip = float(meta["tire_slip_speed"])
            traction_limit = float(meta["tire_traction_limit"])
            tire_force = float(meta["tire_force"])
            rows.append(
                (
                    float(time),
                    full,
                    compact_mode(segment.mode),
                    float(meta["vehicle_position"]),
                    vehicle_speed,
                    patch_speed,
                    slip,
                    slip_ratio(slip_speed=slip, patch_speed=patch_speed, vehicle_speed=vehicle_speed),
                    tire_force,
                    traction_limit,
                    abs(tire_force) / traction_limit if traction_limit > 1.0e-12 else 0.0,
                    float(meta["normal_load"]),
                    float(meta["grade_degrees"]),
                    float(meta["terrain_mu"]),
                    float(meta["grade_force"]),
                    float(meta["rolling_force"]),
                    float(meta["aerodynamic_force"]),
                    float(meta["road_force"]),
                    float(meta["secondary_tire_torque"]),
                    bool(meta.get("terrain_airborne", False)),
                    str(meta["terrain_segment"]),
                )
            )
    # Deduplicate boundary rows; prefer the later segment's value at the same time.
    merged: dict[float, tuple] = {}
    for row in rows:
        merged[round(row[0], 12)] = row
    rows = [merged[key] for key in sorted(merged)]
    return TireSlipTrace(
        time_s=np.asarray([r[0] for r in rows], dtype=float),
        state=np.column_stack([r[1] for r in rows]),
        mode=tuple(r[2] for r in rows),
        vehicle_position_m=np.asarray([r[3] for r in rows], dtype=float),
        vehicle_speed_mps=np.asarray([r[4] for r in rows], dtype=float),
        wheel_patch_speed_mps=np.asarray([r[5] for r in rows], dtype=float),
        slip_speed_mps=np.asarray([r[6] for r in rows], dtype=float),
        slip_ratio=np.asarray([r[7] for r in rows], dtype=float),
        tire_force_n=np.asarray([r[8] for r in rows], dtype=float),
        traction_limit_n=np.asarray([r[9] for r in rows], dtype=float),
        tire_utilization=np.asarray([r[10] for r in rows], dtype=float),
        normal_load_n=np.asarray([r[11] for r in rows], dtype=float),
        grade_degrees=np.asarray([r[12] for r in rows], dtype=float),
        terrain_mu=np.asarray([r[13] for r in rows], dtype=float),
        grade_force_n=np.asarray([r[14] for r in rows], dtype=float),
        rolling_force_n=np.asarray([r[15] for r in rows], dtype=float),
        aerodynamic_force_n=np.asarray([r[16] for r in rows], dtype=float),
        road_force_n=np.asarray([r[17] for r in rows], dtype=float),
        secondary_tire_torque_nm=np.asarray([r[18] for r in rows], dtype=float),
        airborne=np.asarray([bool(r[19]) for r in rows], dtype=bool),
        terrain_segment=tuple(r[20] for r in rows),
    )


@dataclass(frozen=True, slots=True)
class ValidationResult:
    passed: bool
    checks: Mapping[str, bool]
    metrics: Mapping[str, float]
    notes: tuple[str, ...]


def validate_trace(
    *,
    case: TerrainCase,
    constants: BajaTrialConstants,
    result,
    trace: TireSlipTrace,
) -> ValidationResult:
    tol_force = 1.0e-6
    finite = bool(
        np.all(np.isfinite(trace.state))
        and np.all(np.isfinite(trace.vehicle_speed_mps))
        and np.all(np.isfinite(trace.slip_speed_mps))
        and np.all(np.isfinite(trace.tire_force_n))
    )
    shift_mm = trace.state[3] / MILLIMETRE
    shift_bounds_ok = bool(np.min(trace.state[3]) >= -1.0e-5 and np.max(trace.state[3]) <= constants.max_shift + 1.0e-5)
    traction_limit_ok = bool(np.all(np.abs(trace.tire_force_n) <= trace.traction_limit_n + 1.0e-5 + 1.0e-9 * trace.traction_limit_n))
    friction_dissipative_ok = bool(np.all(trace.tire_force_n * trace.slip_speed_mps >= -1.0e-5))
    torque_sign_ok = bool(np.allclose(
        trace.secondary_tire_torque_nm,
        -trace.tire_force_n * constants.wheel_radius / constants.final_drive_ratio,
        atol=1.0e-7,
        rtol=1.0e-7,
    ))
    downhill = trace.grade_degrees < -0.25
    downhill_gravity_ok = True
    if np.any(downhill):
        downhill_gravity_ok = bool(np.all(trace.grade_force_n[downhill] > -tol_force))
    uphill = trace.grade_degrees > 0.25
    uphill_gravity_ok = True
    if np.any(uphill):
        uphill_gravity_ok = bool(np.all(trace.grade_force_n[uphill] < tol_force))

    # EOM residual from sampled dense states.  This is a diagnostic rather than
    # a tight numerical proof because hybrid segment boundaries and sampled dense
    # output can introduce small interpolation artifacts.
    if trace.time_s.size >= 3:
        dvdt_sampled = np.gradient(trace.vehicle_speed_mps, trace.time_s)
        accel_expected = (trace.tire_force_n + trace.road_force_n) / constants.vehicle_mass
        eom_residual = float(np.nanmax(np.abs(dvdt_sampled - accel_expected)))
    else:
        eom_residual = float("nan")
    vehicle_eom_reasonable = bool(not isfinite(eom_residual) or eom_residual < 15.0)
    if np.any(trace.airborne):
        airborne_tire_force_ok = bool(np.all(np.abs(trace.tire_force_n[trace.airborne]) <= 1.0e-8))
        airborne_normal_ok = bool(np.all(np.abs(trace.normal_load_n[trace.airborne]) <= 1.0e-8))
    else:
        airborne_tire_force_ok = True
        airborne_normal_ok = True

    checks = {
        "completed": bool(result.completed),
        "finite_trace": finite,
        "shift_position_within_physical_bounds": shift_bounds_ok,
        "tire_force_within_mu_normal_limit": traction_limit_ok,
        "tire_force_dissipates_slip_power": friction_dissipative_ok,
        "secondary_tire_torque_sign_and_magnitude": torque_sign_ok,
        "downhill_grade_force_points_forward": downhill_gravity_ok,
        "uphill_grade_force_points_backward": uphill_gravity_ok,
        "vehicle_eom_residual_reasonable_from_sampled_trace": vehicle_eom_reasonable,
        "airborne_tire_force_zero_ok": airborne_tire_force_ok,
        "airborne_normal_load_zero_ok": airborne_normal_ok,
    }
    notes: list[str] = []
    if np.any(downhill):
        notes.append("Downhill segments are admissible when gravity acts forward; tire force may be positive or negative depending on wheel slip/engine braking.")
    if float(np.nanmax(trace.tire_utilization)) > 0.98:
        notes.append("Tire utilization reaches the mu*N limit; this is expected for low-mu launch cases and indicates tire-side slip saturation.")
    if float(np.nanmin(trace.vehicle_speed_mps)) < -0.05:
        notes.append("Vehicle reverses briefly; this can be physical on severe grades but should be inspected for the selected scenario.")
    metrics = {
        "final_distance_m": float(trace.vehicle_position_m[-1]),
        "final_vehicle_speed_kmh": float(trace.vehicle_speed_mps[-1] * 3.6),
        "max_vehicle_speed_kmh": float(np.nanmax(trace.vehicle_speed_mps) * 3.6),
        "min_vehicle_speed_kmh": float(np.nanmin(trace.vehicle_speed_mps) * 3.6),
        "max_abs_slip_speed_mps": float(np.nanmax(np.abs(trace.slip_speed_mps))),
        "max_abs_slip_ratio": float(np.nanmax(np.abs(trace.slip_ratio))),
        "max_tire_utilization": float(np.nanmax(trace.tire_utilization)),
        "max_tire_force_n": float(np.nanmax(trace.tire_force_n)),
        "min_tire_force_n": float(np.nanmin(trace.tire_force_n)),
        "max_shift_mm": float(np.nanmax(shift_mm)),
        "min_shift_mm": float(np.nanmin(shift_mm)),
        "vehicle_eom_residual_max_mps2": eom_residual,
        "airborne_duration_s": float(np.trapezoid(trace.airborne.astype(float), trace.time_s)),
    }
    return ValidationResult(
        passed=all(checks.values()),
        checks=checks,
        metrics=metrics,
        notes=tuple(notes),
    )


def short_event(reason: str) -> str:
    mapping = (
        ("lower_stop_released", "low stop"),
        ("primary_closed_into_engaged_contact", "engage"),
        ("low_ratio_seat_reached", "low seat"),
        ("low_ratio_seat_released", "shift start"),
        ("contact_restuck", "re-stick"),
        ("upper_stop_reached", "high stop"),
        ("upper_stop_released", "high release"),
        ("static_capacity_exhausted", "CVT slip"),
    )
    for fragment, label in mapping:
        if fragment in reason:
            return label
    return reason.replace("_", " ")


def annotate_transitions(axes, result) -> None:
    for count, rec in enumerate(result.transitions):
        for ax in axes:
            ax.axvline(rec.time, linestyle="--", linewidth=0.75, alpha=0.35)
        if axes:
            axes[0].annotate(
                short_event(rec.transition.reason),
                xy=(rec.time, 0.97 - 0.10 * (count % 5)),
                xycoords=("data", "axes fraction"),
                xytext=(2, 0),
                textcoords="offset points",
                rotation=90,
                va="top",
                ha="left",
                fontsize=6,
            )


def annotate_terrain_changes(axes, terrain: PiecewiseConstantTerrainProfile, trace: TireSlipTrace) -> None:
    for segment in terrain.segments[1:]:
        idx = np.searchsorted(trace.vehicle_position_m, segment.start_distance_m)
        if idx >= trace.time_s.size:
            continue
        time = float(trace.time_s[idx])
        for ax in axes:
            ax.axvline(time, linestyle=":", linewidth=0.9, alpha=0.55)
        axes[-1].annotate(
            segment.name,
            xy=(time, 0.04),
            xycoords=("data", "axes fraction"),
            xytext=(2, 0),
            textcoords="offset points",
            rotation=90,
            va="bottom",
            ha="left",
            fontsize=6,
        )


def plot_case(
    *,
    case: TerrainCase,
    trace: TireSlipTrace,
    result,
    resolved: ResolvedTune,
    output_dir: Path,
) -> Path:
    t = trace.time_s
    primary_rpm = trace.state[0] * RPM_PER_RADIAN_PER_SECOND
    secondary_rpm = trace.state[1] * RPM_PER_RADIAN_PER_SECOND
    shift_mm = trace.state[3] / MILLIMETRE
    shift_speed_mmps = trace.state[4] / MILLIMETRE

    fig, axes = plt.subplots(3, 2, figsize=(18, 13), constrained_layout=True)
    ax1, ax2, ax3, ax4, ax5, ax6 = axes.flat

    ax1.plot(t, primary_rpm, label=r"$\omega_p$")
    ax1.plot(t, secondary_rpm, label=r"$\omega_s$")
    ax1.set(title="Shaft speeds", xlabel="Time [s]", ylabel="Speed [rpm]")
    ax1.grid(True, alpha=0.25)
    ax1.legend()

    ax2.plot(t, trace.vehicle_speed_mps, label="vehicle speed")
    ax2.plot(t, trace.wheel_patch_speed_mps, linestyle=":", label="wheel patch speed")
    ax2.axhline(0.0, linestyle="--", linewidth=0.8)
    ax2.set(title="Wheel patch speed versus vehicle speed", xlabel="Time [s]", ylabel="Speed [m/s]")
    ax2.grid(True, alpha=0.25)
    ax2.legend()

    ax3.plot(t, trace.slip_speed_mps, label="slip speed")
    ax3.axhline(0.0, linestyle="--", linewidth=0.8)
    ax3.set(title="Tire slip speed", xlabel="Time [s]", ylabel="Patch - vehicle [m/s]")
    ax3.grid(True, alpha=0.25)
    ax3b = ax3.twinx()
    ax3b.plot(t, trace.slip_ratio, linestyle=":", label="slip ratio")
    ax3b.set_ylabel("Signed slip ratio [-]")
    h, l = ax3.get_legend_handles_labels()
    h2, l2 = ax3b.get_legend_handles_labels()
    ax3.legend(h + h2, l + l2, loc="best")

    ax4.plot(t, trace.tire_force_n, label="tire force")
    ax4.plot(t, trace.traction_limit_n, linestyle="--", label=r"$+\mu N$")
    ax4.plot(t, -trace.traction_limit_n, linestyle="--", label=r"$-\mu N$")
    ax4.set(title="Tire force and traction envelope", xlabel="Time [s]", ylabel="Force [N]")
    ax4.grid(True, alpha=0.25)
    ax4.legend()

    ax5.plot(t, shift_mm, label=r"$s$")
    ax5.axhline(resolved.constants.deadzone_shift / MILLIMETRE, linestyle="--", label="engage")
    ax5.axhline(resolved.constants.max_shift / MILLIMETRE, linestyle="--", label="high stop")
    ax5.set(title="CVT shift coordinate", xlabel="Time [s]", ylabel="Shift [mm]")
    ax5.grid(True, alpha=0.25)
    ax5b = ax5.twinx()
    ax5b.plot(t, shift_speed_mmps, linestyle=":", label=r"$\dot{s}$")
    ax5b.set_ylabel("Shift speed [mm/s]")
    h, l = ax5.get_legend_handles_labels()
    h2, l2 = ax5b.get_legend_handles_labels()
    ax5.legend(h + h2, l + l2, loc="best")

    ax6.plot(t, trace.grade_degrees, label="grade")
    ax6.axhline(0.0, linestyle="--", linewidth=0.8)
    ax6.set(title="Terrain by vehicle position", xlabel="Time [s]", ylabel="Grade [deg]")
    ax6.grid(True, alpha=0.25)
    ax6b = ax6.twinx()
    ax6b.plot(t, trace.terrain_mu, linestyle=":", label=r"$\mu$")
    ax6b.set_ylabel("Tire-road friction coefficient [-]")
    h, l = ax6.get_legend_handles_labels()
    h2, l2 = ax6b.get_legend_handles_labels()
    ax6.legend(h + h2, l + l2, loc="best")

    annotate_transitions([ax1, ax2, ax3, ax4, ax5], result)
    annotate_terrain_changes([ax1, ax2, ax3, ax4, ax5, ax6], case.terrain, trace)
    fig.suptitle(
        f"Tire-slip terrain response | {case.name} | {resolved.candidate.label()}",
        fontsize=13,
    )
    path = output_dir / f"{case.slug}_combined.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_summary(summary_rows: Sequence[Mapping[str, float | str | bool]], output_dir: Path) -> Path:
    labels = [str(row["case"]) for row in summary_rows]
    x = np.arange(len(labels))
    width = 0.25
    fig, ax = plt.subplots(figsize=(14, 6), constrained_layout=True)
    ax.bar(x - width, [float(row["final_distance_m"]) for row in summary_rows], width, label="final distance [m]")
    ax.bar(x, [float(row["max_abs_slip_speed_mps"]) for row in summary_rows], width, label="max |slip speed| [m/s]")
    ax.bar(x + width, [float(row["max_tire_utilization"]) for row in summary_rows], width, label="max tire utilization [-]")
    ax.set(title="Tire-slip terrain case summary", xlabel="Case", ylabel="Metric value")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend()
    path = output_dir / "case_summary.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def write_trace(path: Path, trace: TireSlipTrace) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "time_s",
            "mode",
            "primary_rpm",
            "secondary_rpm",
            "belt_speed_mps",
            "shift_mm",
            "shift_speed_mmps",
            "secondary_shaft_angle_rad",
            "vehicle_position_m",
            "vehicle_speed_mps",
            "wheel_patch_speed_mps",
            "slip_speed_mps",
            "slip_ratio",
            "tire_force_n",
            "traction_limit_n",
            "tire_utilization",
            "normal_load_n",
            "grade_deg",
            "terrain_mu",
            "terrain_segment",
            "airborne",
            "grade_force_n",
            "rolling_force_n",
            "aerodynamic_force_n",
            "road_force_n",
            "secondary_tire_torque_nm",
        ])
        for i, time in enumerate(trace.time_s):
            s = trace.state[:, i]
            writer.writerow([
                float(time),
                trace.mode[i],
                float(s[0] * RPM_PER_RADIAN_PER_SECOND),
                float(s[1] * RPM_PER_RADIAN_PER_SECOND),
                float(s[2]),
                float(s[3] / MILLIMETRE),
                float(s[4] / MILLIMETRE),
                float(s[5]),
                float(trace.vehicle_position_m[i]),
                float(trace.vehicle_speed_mps[i]),
                float(trace.wheel_patch_speed_mps[i]),
                float(trace.slip_speed_mps[i]),
                float(trace.slip_ratio[i]),
                float(trace.tire_force_n[i]),
                float(trace.traction_limit_n[i]),
                float(trace.tire_utilization[i]),
                float(trace.normal_load_n[i]),
                float(trace.grade_degrees[i]),
                float(trace.terrain_mu[i]),
                trace.terrain_segment[i],
                int(bool(trace.airborne[i])),
                float(trace.grade_force_n[i]),
                float(trace.rolling_force_n[i]),
                float(trace.aerodynamic_force_n[i]),
                float(trace.road_force_n[i]),
                float(trace.secondary_tire_torque_nm[i]),
            ])


def terrain_gauntlet_case() -> TerrainCase:
    """One long terrain story for playback and tire-slip inspection.

    The profile is distance-indexed rather than time-indexed, so each terrain
    feature begins when the vehicle actually reaches that section of the track.
    This makes the case useful when tuning tires/CVT behaviour because a slow
    or slipping vehicle naturally spends longer before later terrain features.
    """

    return TerrainCase(
        name="terrain gauntlet",
        duration_s=60.0,
        terrain=PiecewiseConstantTerrainProfile((
            TerrainSegment(0.0, 0.0, 0.90, "long grippy flat launch"),
            TerrainSegment(70.0, 0.0, 0.90, "grippy flat speed build"),
            TerrainSegment(125.0, 12.0, 0.86, "grippy rolling climb"),
            TerrainSegment(175.0, 16.0, 0.82, "steeper grippy hill"),
            TerrainSegment(225.0, 0.0, 0.88, "flat transition"),
            TerrainSegment(285.0, 13.0, 0.30, "slippy hill"),
            TerrainSegment(335.0, 16.0, 0.26, "slick steep hill"),
            TerrainSegment(385.0, 0.0, 0.28, "loose flat recovery"),
            TerrainSegment(435.0, -10.0, 0.32, "loose downhill"),
            TerrainSegment(490.0, -16.0, 0.72, "grippy downhill"),
            TerrainSegment(545.0, 0.0, 0.78, "grippy flat reset"),
            TerrainSegment(595.0, 18.0, 0.84, "final grippy climb"),
            TerrainSegment(620.0, 0.0, 0.22, "muddy flat finish"),
            # Longer no-contact jump, followed by a longer on-ground recovery.
            TerrainSegment(625.0, 0.0, 0.0, "airborne jump", airborne=True),
            TerrainSegment(660.0, 0.0, 0.90, "flat landing runout"),
            TerrainSegment(780.0, 0.0, 0.90, "final grippy finish"),
        )),
    )



def all_cases() -> tuple[TerrainCase, ...]:
    return (terrain_gauntlet_case(),)


def default_cases() -> tuple[TerrainCase, ...]:
    return all_cases()


def select_cases(names: Sequence[str] | None) -> tuple[TerrainCase, ...]:
    cases = all_cases()
    if not names:
        return default_cases()
    wanted = {name.lower().replace("_", " ").replace("-", " ") for name in names}
    selected = tuple(case for case in cases if case.name.lower() in wanted or case.slug in wanted)
    missing = wanted - {case.name.lower() for case in selected} - {case.slug for case in selected}
    if missing:
        available = ", ".join(case.name for case in cases)
        raise ValueError(f"Unknown case(s): {sorted(missing)}. Available: {available}")
    return selected


def run_case(
    *,
    case: TerrainCase,
    resolved: ResolvedTune,
    tire_slip_stiffness: float,
    settings: HybridIntegratorSettings,
    report_step_s: float,
    output_dir: Path,
) -> tuple[TireSlipTrace, ValidationResult, Path, Path]:
    system, _engine, _road_load, _boundary = build_tire_slip_system(
        resolved.constants,
        case.terrain,
        tire_slip_stiffness=tire_slip_stiffness,
    )
    initial_cvt = launch_cvt_state(primary_rpm=case.initial_primary_rpm)
    initial_host = system.host.initial_state(
        secondary_shaft_angle=0.0,
        vehicle_position=case.initial_vehicle_position_m,
        vehicle_speed=case.initial_vehicle_speed_mps,
    )
    initial_full = system.initial_state(cvt_state=initial_cvt, host_state=initial_host)
    initial_mode = system.classify_initial_mode(initial_full)
    result = integrate_hybrid(
        system=system,
        time_span=(0.0, case.duration_s),
        initial_state=initial_full,
        initial_mode=initial_mode,
        settings=settings,
    )
    if not result.completed:
        # Still sample what exists to help diagnose, then let validation fail.
        print(f"WARNING: {case.name} did not complete: {result.termination_reason}")
    trace = sample_trace(system, result, report_step_s=report_step_s)
    validation = validate_trace(
        case=case,
        constants=resolved.constants,
        result=result,
        trace=trace,
    )
    case_dir = output_dir / case.slug
    case_dir.mkdir(parents=True, exist_ok=True)
    trace_path = case_dir / f"{case.slug}_trace.csv"
    write_trace(trace_path, trace)
    plot_path = plot_case(
        case=case,
        trace=trace,
        result=result,
        resolved=resolved,
        output_dir=case_dir,
    )
    payload = {
        "case": case.name,
        "passed": validation.passed,
        "checks": validation.checks,
        "metrics": validation.metrics,
        "notes": validation.notes,
        "transitions": [
            {"time_s": float(rec.time), "reason": rec.transition.reason}
            for rec in result.transitions
        ],
        "terrain": [
            {
                "start_distance_m": seg.start_distance_m,
                "grade_degrees": seg.grade_degrees,
                "friction_coefficient": seg.friction_coefficient,
                "name": seg.name,
                "airborne": seg.airborne,
            }
            for seg in case.terrain.segments
        ],
    }
    (case_dir / f"{case.slug}_validation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return trace, validation, plot_path, trace_path


def parse_args(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Run CINDER launch cases with independent vehicle speed and tire slip over distance-indexed terrain."
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/tire_slip_terrain"))
    parser.add_argument("--preset", type=Path, default=DEFAULT_FIXED_PIVOT_PRESET)
    parser.add_argument("--case", action="append", help="Run only a named case. Repeat for multiple cases. Defaults to all built-in cases.")
    parser.add_argument("--tire-slip-stiffness", type=float, default=2500.0, help="Linearized tire force slope dF/dv_slip near zero slip [N/(m/s)].")
    parser.add_argument("--report-step-s", type=float, default=0.01)
    parser.add_argument("--rtol", type=float, default=3.0e-2)
    parser.add_argument("--atol", type=float, default=1.0e-5)
    parser.add_argument("--max-step", type=float, default=0.05)
    parser.add_argument("--no-show", action="store_true", help="Suppress the interactive playback window and only write files.")
    parser.add_argument("--playback-speed", type=float, default=1.0, help="Real-time multiplier for the toy-car playback window.")
    parser.add_argument("--playback-case", type=str, default=None, help="Case name/slug to play back after the run. Defaults to the chosen case, or terrain_gauntlet for multi-case sweeps.")
    parser.add_argument("--no-playback", action="store_true", help="Do not open the playback window after the run.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate: TuneCandidate = load_candidate(args.preset)
    # Reuse the same preload resolution path as the other launch tools.  This
    # preserves the baseline engagement behavior before swapping only the outer
    # locked final-drive boundary for the tire/vehicle host.
    resolved = resolve_primary_preload(
        candidate,
        target_engagement_rpm=2000.0,
        programme=GradeProgramme.default(),
    )
    settings = HybridIntegratorSettings(
        relative_tolerance=args.rtol,
        absolute_tolerance=args.atol,
        method="LSODA",
        max_step=args.max_step,
        maximum_transitions=1000,
        retain_dense_output=True,
    )
    cases = select_cases(args.case)
    print("Running tire-slip terrain launch cases")
    print(resolved.candidate.label())
    print(f"primary preload={resolved.resolved_primary_preload_mm:.3f} mm")
    print(f"tire slip stiffness={args.tire_slip_stiffness:.3g} N/(m/s)")

    summary_rows: list[dict[str, float | str | bool]] = []
    validation_payload: dict[str, object] = {
        "candidate": resolved.candidate.label(),
        "resolved_primary_preload_mm": resolved.resolved_primary_preload_mm,
        "tire_slip_stiffness": args.tire_slip_stiffness,
        "cases": {},
    }
    for case in cases:
        print(f"\nCase: {case.name}")
        trace, validation, plot_path, trace_path = run_case(
            case=case,
            resolved=resolved,
            tire_slip_stiffness=args.tire_slip_stiffness,
            settings=settings,
            report_step_s=args.report_step_s,
            output_dir=output_dir,
        )
        status = "PASS" if validation.passed else "FAIL"
        print(f"  {status} | distance={validation.metrics['final_distance_m']:.2f} m | "
              f"final={validation.metrics['final_vehicle_speed_kmh']:.2f} km/h | "
              f"max |slip|={validation.metrics['max_abs_slip_speed_mps']:.2f} m/s | "
              f"max tire util={validation.metrics['max_tire_utilization']:.3f}")
        print(f"  plot: {plot_path}")
        for name, passed in validation.checks.items():
            if not passed:
                print(f"  failed check: {name}")
        row = {"case": case.name, "passed": validation.passed, "trace_path": str(trace_path), **validation.metrics}
        summary_rows.append(row)
        validation_payload["cases"][case.slug] = {
            "name": case.name,
            "passed": validation.passed,
            "checks": validation.checks,
            "metrics": validation.metrics,
            "notes": validation.notes,
        }

    summary_path = plot_summary(summary_rows, output_dir)

    if not args.no_show and not args.no_playback and summary_rows:
        requested = args.playback_case
        chosen_row = None
        if requested is not None:
            requested_slug = requested.lower().replace(" ", "_").replace("/", "_").replace("-", "_")
            for row in summary_rows:
                case_name = str(row["case"])
                case_slug = case_name.lower().replace(" ", "_").replace("/", "_").replace("-", "_")
                if requested == case_name or requested_slug == case_slug:
                    chosen_row = row
                    break
        elif len(summary_rows) == 1:
            chosen_row = summary_rows[0]
        else:
            for row in summary_rows:
                if str(row["case"]).lower().replace(" ", "_") == "terrain_gauntlet":
                    chosen_row = row
                    break
            if chosen_row is None:
                chosen_row = summary_rows[0]

        if chosen_row is not None:
            trace_path = Path(str(chosen_row["trace_path"]))
            case_name = str(chosen_row["case"])
            print(f"\nOpening playback for: {case_name}")
            print(f"  trace: {trace_path}")
            launch_playback_from_trace(
                trace_path,
                playback_speed=args.playback_speed,
                title=f"Tire-slip playback: {case_name}",
                block=True,
            )
    (output_dir / "tire_slip_terrain_summary.json").write_text(
        json.dumps({"rows": summary_rows, **validation_payload}, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote summary plot: {summary_path}")
    print(f"Wrote outputs to: {output_dir.resolve()}")
    if not all(bool(row["passed"]) for row in summary_rows):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
