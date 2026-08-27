from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, replace
from math import isfinite, radians
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

# Package path is supplied by the runner through PYTHONPATH.
from cinder.execution.hybrid import HybridIntegratorSettings, integrate_hybrid
from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
from cinder.hosts import SecondaryShaftAngleHost
from cinder.model.boundaries.engine import (
    EngineTorquePoint,
    FullThrottleTorqueCurve,
    TorqueCurveSpec,
)
from cinder.model.boundaries.shaft import FullThrottleEngineBoundary, ShaftBoundaryContext
from cinder.model.boundaries.vehicle import (
    FixedFinalDrive,
    RoadLoadModel,
    VehicleInertia,
    VehicleRoadLoadSpec,
)
from cinder.model.cvt.actuation import (
    CentrifugalActuatorSpec,
    TorqueReactiveActuatorSpec,
    build_centrifugal_actuator,
    build_torque_reactive_actuator,
)
from cinder.model.cvt.actuation.forces import (
    AxialSpringForceSpec,
    CentrifugalRampForceSpec,
    HelicalTorqueReactionSpec,
)
from cinder.model.cvt.geometry import BeltPulleyGeometry, BeltPulleyGeometrySpec, BeltSectionSpec
from cinder.model.cvt.inertia import (
    BeltMass,
    DrivetrainInertias,
    PrimaryInertia,
    SecondaryInertia,
    resolve_inertias,
)
from cinder.model.cvt.profiles import (
    CircularSegment,
    HelixProfile,
    LinearSegment,
    PiecewiseRamp,
    linear_helix_segment,
)
from cinder.model.system import (
    BeltContactSpec,
    CVTAssemblySpec,
    CVTShaftBoundaryValues,
    CVTState,
    HelicalPulleyCoupling,
    MechanicalCVTPlant,
    PulleyPairSpec,
    PulleySpec,
    ShaftBoundaryValue,
)

INCH_TO_METRE = 0.0254
FOOT_POUND_TO_NEWTON_METRE = 1.3558179483
RPM_TO_RAD_PER_SECOND = 2.0 * np.pi / 60.0
RPM_PER_RADIAN_PER_SECOND = 60.0 / (2.0 * np.pi)
MILLIMETRE = 1.0e-3
WATTS_PER_MECHANICAL_HORSEPOWER = 745.6998715822702


@dataclass(frozen=True, slots=True)
class TuneCandidate:
    flyweight_mass_kg: float
    helix_angle_degrees: float
    secondary_torsional_pretension_degrees: float
    secondary_compression_preload_mm: float
    primary_ramp_kind: str = "linear"
    primary_ramp_angle_degrees: float = 30.0
    primary_ramp_start_angle_degrees: float = 42.0
    primary_ramp_end_angle_degrees: float = 12.0

    def label(self) -> str:
        if self.primary_ramp_kind == "linear":
            ramp = f"ramp=L{self.primary_ramp_angle_degrees:.0f}"
        else:
            ramp = (
                f"ramp=C{self.primary_ramp_start_angle_degrees:.0f}"
                f"→{self.primary_ramp_end_angle_degrees:.0f}"
            )
        return (
            f"tip={self.flyweight_mass_kg:.3f} kg/flyweight, "
            f"h={self.helix_angle_degrees:.1f} deg, "
            f"twist={self.secondary_torsional_pretension_degrees:.0f} deg, "
            f"sec={self.secondary_compression_preload_mm:.1f} mm, {ramp}"
        )


@dataclass(frozen=True, slots=True)
class BajaTrialConstants:
    belt_height: float = 0.613 * INCH_TO_METRE
    belt_outer_width: float = 0.840 * INCH_TO_METRE
    belt_inner_width: float = 0.662 * INCH_TO_METRE
    belt_outer_length: float = 37.53 * INCH_TO_METRE
    belt_cord_depth_from_outer: float = 0.1 * INCH_TO_METRE
    sheave_half_angle_degrees: float = 11.5
    primary_inner_radius_at_low: float = (1.625 / 2.0) * INCH_TO_METRE
    secondary_outer_radius_at_low: float = 4.0 * INCH_TO_METRE
    deadzone_shift: float = (0.088 + 0.010) * INCH_TO_METRE
    max_shift: float = 0.75 * INCH_TO_METRE
    primary_ramp_kind: str = "linear"
    primary_ramp_angle_degrees: float = 30.0
    primary_ramp_start_angle_degrees: float = 42.0
    primary_ramp_end_angle_degrees: float = 12.0
    helix_angle_degrees: float = 26.0
    initial_flyweight_radius: float = 0.04878
    helix_radius: float = 0.04445
    flyweight_mass: float = 0.5
    primary_spring_rate: float = 12_784.0
    primary_spring_initial_compression: float = 0.1
    secondary_torsional_spring_rate: float = 3.476
    secondary_torsional_initial_twist: float = radians(200.0)
    secondary_compression_spring_rate: float = 3_532.0
    secondary_spring_initial_compression: float = 0.1
    engine_power_limit_hp: float = 10.0
    engine_low_speed_braking_torque: float = -5.0
    engine_low_speed_braking_peak_rpm: float = 500.0
    engine_governed_overspeed_torque: float = -28.0
    engine_governed_overspeed_transition_width_rpm: float = 1500.0
    engine_rotational_inertia: float = 0.05
    primary_cvt_rotational_inertia: float = 0.00491861
    primary_moving_sheave_mass: float = 1.0681
    secondary_fixed_rotational_inertia: float = 0.0023262599999999997
    gearbox_input_rotational_inertia: float = 0.002011338398044471
    secondary_movable_sheave_rotational_inertia: float = 0.0025139
    secondary_moving_sheave_mass: float = 0.705141
    rubber_density: float = 1100.0
    belt_static_friction_coefficient: float = 0.65
    belt_kinetic_friction_coefficient: float = 0.55
    vehicle_mass: float = 225.0 + 75.0
    wheel_rotational_inertia: float = 1.10781744
    final_drive_ratio: float = 7.556
    wheel_radius: float = 11.0 * INCH_TO_METRE
    frontal_area: float = 1.11484
    drag_coefficient: float = 0.6
    rolling_resistance_coefficient: float = 0.015


@dataclass(frozen=True, slots=True)
class ResolvedTune:
    candidate: TuneCandidate
    constants: BajaTrialConstants
    target_engagement_rpm: float
    resolved_primary_preload_mm: float
    lower_stop_reaction_at_target_n: float


@dataclass(frozen=True, slots=True)
class GradePhase:
    name: str
    start_s: float
    end_s: float
    start_degrees: float
    end_degrees: float
    transition: bool = False

    def contains(self, time_s: float, *, include_end: bool = False) -> bool:
        return self.start_s <= time_s <= self.end_s if include_end else self.start_s <= time_s < self.end_s

    def grade_radians(self, time_s: float) -> float:
        if self.end_s <= self.start_s or not self.transition:
            return radians(self.start_degrees)
        u = smoothstep((time_s - self.start_s) / (self.end_s - self.start_s))
        return radians(self.start_degrees + (self.end_degrees - self.start_degrees) * u)

    @property
    def display_label(self) -> str:
        grade = f"{self.start_degrees:+.0f}→{self.end_degrees:+.0f}°" if self.transition else f"{self.start_degrees:+.0f}°"
        return f"{self.name} ({grade})"


@dataclass(frozen=True, slots=True)
class GradeProgramme:
    phases: tuple[GradePhase, ...]

    @classmethod
    def default(cls, *, final_level_seconds: float = 3.0) -> "GradeProgramme":
        t = 0.0
        phases: list[GradePhase] = []
        def add(name: str, duration: float, start: float, end: float, transition: bool) -> None:
            nonlocal t
            phases.append(GradePhase(name, t, t + duration, start, end, transition))
            t += duration
        add("flat launch", 10.0, 0.0, 0.0, False)
        add("rise to 30", 2.0, 0.0, 30.0, True)
        add("30 degree hill", 10.0, 30.0, 30.0, False)
        add("ease to 15", 2.0, 30.0, 15.0, True)
        add("15 degree hill", 10.0, 15.0, 15.0, False)
        add("turn to downhill", 2.0, 15.0, -20.0, True)
        add("20 degree downhill", 4.0, -20.0, -20.0, False)
        add("return to level", 2.0, -20.0, 0.0, True)
        add("flat recovery", final_level_seconds, 0.0, 0.0, False)
        return cls(tuple(phases))

    @property
    def end_time_s(self) -> float:
        return self.phases[-1].end_s

    def grade_radians(self, time_s: float) -> float:
        for i, phase in enumerate(self.phases):
            if phase.contains(float(time_s), include_end=i == len(self.phases) - 1):
                return phase.grade_radians(float(time_s))
        return radians(self.phases[-1].end_degrees)


def smoothstep(value: float) -> float:
    value = float(np.clip(value, 0.0, 1.0))
    return value * value * (3.0 - 2.0 * value)


class TimeProgrammedLockedFinalDriveBoundary:
    """Secondary shaft boundary with a time-programmed route grade."""

    def __init__(self, *, road_load: RoadLoadModel, programme: GradeProgramme, direct_secondary_shaft_inertia: float = 0.0) -> None:
        self.road_load = road_load
        self.programme = programme
        self.direct_secondary_shaft_inertia = direct_secondary_shaft_inertia

    @property
    def reflected_rotational_inertia(self) -> float:
        fd = self.road_load.final_drive
        vehicle = self.road_load.vehicle
        return (
            self.direct_secondary_shaft_inertia
            + fd.secondary_inertia_from_wheel_rotation(wheel_rotational_inertia=vehicle.wheel_rotational_inertia)
            + fd.secondary_inertia_from_vehicle_mass(vehicle_mass=vehicle.mass)
        )

    def evaluate(self, context: ShaftBoundaryContext) -> ShaftBoundaryValue:
        if context.shaft != "secondary":
            raise ValueError("TimeProgrammedLockedFinalDriveBoundary must attach to secondary.")
        secondary_angle = float(context.host["secondary_shaft_angle"])
        distance = self.road_load.final_drive.vehicle_distance_from_secondary_angle(secondary_shaft_angle=secondary_angle)
        grade_angle = self.programme.grade_radians(context.time)
        road = self.road_load.evaluate(
            secondary_angular_speed=context.cvt.secondary_angular_speed,
            grade_angle=grade_angle,
        )
        return ShaftBoundaryValue(
            external_torque=road.secondary_external_torque,
            equivalent_inertia=self.reflected_rotational_inertia,
            metadata={"road_load": road, "vehicle_distance": distance, "grade_angle": grade_angle},
        )


def load_candidate(path: Path) -> TuneCandidate:
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload["candidate"]
    return TuneCandidate(
        flyweight_mass_kg=float(data["flyweight_mass_kg"]),
        helix_angle_degrees=float(data["helix_angle_degrees"]),
        secondary_torsional_pretension_degrees=float(data["secondary_torsional_pretension_degrees"]),
        secondary_compression_preload_mm=float(data["secondary_compression_preload_mm"]),
        primary_ramp_kind=str(data["primary_ramp_kind"]),
        primary_ramp_angle_degrees=float(data.get("primary_ramp_angle_degrees", 30.0)),
        primary_ramp_start_angle_degrees=float(data["primary_ramp_start_angle_degrees"]),
        primary_ramp_end_angle_degrees=float(data["primary_ramp_end_angle_degrees"]),
    )


def candidate_constants(candidate: TuneCandidate, *, primary_preload_m: float | None = None) -> BajaTrialConstants:
    updates = {
        "flyweight_mass": candidate.flyweight_mass_kg,
        "helix_angle_degrees": candidate.helix_angle_degrees,
        "secondary_torsional_initial_twist": np.deg2rad(candidate.secondary_torsional_pretension_degrees),
        "secondary_spring_initial_compression": candidate.secondary_compression_preload_mm * MILLIMETRE,
        "primary_ramp_kind": candidate.primary_ramp_kind,
        "primary_ramp_angle_degrees": candidate.primary_ramp_angle_degrees,
        "primary_ramp_start_angle_degrees": candidate.primary_ramp_start_angle_degrees,
        "primary_ramp_end_angle_degrees": candidate.primary_ramp_end_angle_degrees,
    }
    if primary_preload_m is not None:
        updates["primary_spring_initial_compression"] = primary_preload_m
    return replace(BajaTrialConstants(), **updates)


def build_components(c: BajaTrialConstants):
    """Build the shared physical fixed-pivot Baja default assembly."""

    from fixed_pivot_default_support import (
        build_components as _build_fixed_pivot_components,
    )

    return _build_fixed_pivot_components(c)

def build_composed_system(c: BajaTrialConstants, programme: GradeProgramme | None = None) -> tuple[ComposedCVTHybridSystem, FullThrottleTorqueCurve, RoadLoadModel]:
    assembly, engine, road_load = build_components(c)
    plant = MechanicalCVTPlant.from_assembly(assembly)
    host = SecondaryShaftAngleHost()
    secondary_boundary = TimeProgrammedLockedFinalDriveBoundary(
        road_load=road_load,
        programme=programme or GradeProgramme.default(),
        direct_secondary_shaft_inertia=c.gearbox_input_rotational_inertia,
    )
    system = ComposedCVTHybridSystem.from_plant(
        plant=plant,
        primary_boundary=FullThrottleEngineBoundary(
            engine,
            equivalent_rotational_inertia=c.engine_rotational_inertia,
        ),
        secondary_boundary=secondary_boundary,
        host=host,
    )
    return system, engine, road_load


def launch_cvt_state(*, primary_rpm: float = 1800.0) -> CVTState:
    return CVTState(
        primary_angular_speed=primary_rpm * RPM_TO_RAD_PER_SECOND,
        secondary_angular_speed=0.0,
        belt_speed=0.0,
        shift_position=0.0,
        shift_speed=0.0,
    )


def lower_stop_reaction(system: ComposedCVTHybridSystem, *, primary_rpm: float) -> float:
    cvt_state = launch_cvt_state(primary_rpm=primary_rpm)
    full_state = system.initial_state(cvt_state=cvt_state, host_state=system.host.initial_state(secondary_shaft_angle=0.0))
    boundaries = system._shaft_boundaries(time=0.0, state=full_state)
    evaluation = system.cvt.deadzone_evaluator.evaluate_lower_stop(
        state=cvt_state,
        lower_stop_shift=0.0,
        shaft_boundaries=boundaries,
    )
    if evaluation.stop_reaction is None:
        raise RuntimeError("Lower-stop evaluation did not recover a reaction")
    return float(evaluation.stop_reaction)


def resolve_primary_preload(candidate: TuneCandidate, *, target_engagement_rpm: float, programme: GradeProgramme) -> ResolvedTune:
    provisional = candidate_constants(candidate)
    provisional_system, _, _ = build_composed_system(provisional, programme)
    reaction = lower_stop_reaction(provisional_system, primary_rpm=target_engagement_rpm)
    preload = provisional.primary_spring_initial_compression - reaction / provisional.primary_spring_rate
    if preload < -1.0e-12:
        raise ValueError("negative preload required")
    preload = max(0.0, preload)
    constants = candidate_constants(candidate, primary_preload_m=preload)
    resolved_system, _, _ = build_composed_system(constants, programme)
    resolved_reaction = lower_stop_reaction(resolved_system, primary_rpm=target_engagement_rpm)
    return ResolvedTune(candidate, constants, target_engagement_rpm, preload / MILLIMETRE, resolved_reaction)


@dataclass(frozen=True, slots=True)
class ProgrammeTrace:
    time: NDArray[np.float64]
    state: NDArray[np.float64]
    mode: tuple[str, ...]
    grade_degrees: NDArray[np.float64]
    secondary_road_torque_nm: NDArray[np.float64]
    vehicle_speed_mps: NDArray[np.float64]
    vehicle_distance_m: NDArray[np.float64]


def compact_mode(mode) -> str:
    cvt = getattr(mode, "cvt", mode)
    if cvt.contact_regime is None:
        return f"{cvt.engagement.value}/{cvt.shift_constraint.value}"
    return f"{cvt.engagement.value}/{cvt.shift_constraint.value}/{cvt.contact_regime.mode.value}"


def sample_trace(system: ComposedCVTHybridSystem, result, programme: GradeProgramme, report_step_s: float = 0.01) -> ProgrammeTrace:
    rows: list[tuple[float, NDArray[np.float64], str, float, float, float, float]] = []
    for segment in result.segments:
        t0, t1 = segment.start_time, segment.end_time
        if segment.has_dense_output:
            times = np.arange(t0, t1, report_step_s)
            if len(times) == 0 or abs(times[0] - t0) > 1e-12:
                times = np.r_[t0, times]
            times = np.r_[times, t1]
            times = np.unique(np.clip(times, t0, t1))
            states = segment.dense_state_at(times)
        else:
            times = segment.time
            states = segment.state
        for j, time in enumerate(times):
            full = np.asarray(states[:, j], dtype=float).copy()
            full[3] = np.clip(full[3], 0.0, system.cvt.model.geometry.spec.max_shift)
            cvt_state = CVTState.from_vector(system.layout.view(full, "cvt"))
            boundaries = system._shaft_boundaries(time=float(time), state=full)
            road = boundaries.secondary.metadata.get("road_load")
            distance = float(boundaries.secondary.metadata.get("vehicle_distance", np.nan))
            rows.append((
                float(time),
                full,
                compact_mode(segment.mode),
                float(np.rad2deg(programme.grade_radians(float(time)))),
                float(getattr(road, "secondary_external_torque", np.nan)),
                float(getattr(road, "vehicle_speed", np.nan)),
                distance,
            ))
    # Deduplicate by time, preferring later segment boundary rows.
    merged: dict[float, tuple] = {}
    for row in rows:
        merged[round(row[0], 12)] = row
    rows = [merged[key] for key in sorted(merged)]
    return ProgrammeTrace(
        time=np.asarray([r[0] for r in rows], dtype=float),
        state=np.column_stack([r[1] for r in rows]),
        mode=tuple(r[2] for r in rows),
        grade_degrees=np.asarray([r[3] for r in rows], dtype=float),
        secondary_road_torque_nm=np.asarray([r[4] for r in rows], dtype=float),
        vehicle_speed_mps=np.asarray([r[5] for r in rows], dtype=float),
        vehicle_distance_m=np.asarray([r[6] for r in rows], dtype=float),
    )


def plot_masked_runs(axis, x, y, mask, **kwargs):
    starts = np.flatnonzero(mask & np.r_[True, ~mask[:-1]])
    ends = np.flatnonzero(mask & np.r_[~mask[1:], True])
    label = kwargs.pop("label", None)
    for k, (start, end) in enumerate(zip(starts, ends, strict=True)):
        if end - start < 1:
            continue
        axis.plot(x[start:end+1], y[start:end+1], label=label if k == 0 else None, **kwargs)


def short_event(reason: str) -> str:
    mapping = (("lower_stop_released", "low stop"), ("primary_closed_into_engaged_contact", "engage"), ("low_ratio_seat_reached", "low seat"), ("low_ratio_seat_released", "shift start"), ("contact_restuck", "re-stick"), ("upper_stop_reached", "high stop"), ("upper_stop_released", "high release"), ("static_capacity_exhausted", "slip"))
    for fragment, label in mapping:
        if fragment in reason:
            return label
    return reason.replace("_", " ")


def annotate_transitions(axes, label_axes, result):
    for count, rec in enumerate(result.transitions):
        for ax in axes:
            ax.axvline(rec.time, linestyle="--", linewidth=0.75, alpha=0.45)
        frac = 0.97 - 0.11 * (count % 6)
        for ax in label_axes:
            ax.annotate(short_event(rec.transition.reason), xy=(rec.time, frac), xycoords=("data", "axes fraction"), xytext=(2, 0), textcoords="offset points", rotation=90, va="top", ha="left", fontsize=6)


def annotate_programme(axes, grade_axis, programme):
    for phase in programme.phases[1:]:
        for ax in axes:
            ax.axvline(phase.start_s, linestyle=":", linewidth=0.9, alpha=0.7)
        grade_axis.annotate(phase.name, xy=(phase.start_s, 0.04), xycoords=("data", "axes fraction"), xytext=(2,0), textcoords="offset points", rotation=90, va="bottom", ha="left", fontsize=6)


def plot_response(trace: ProgrammeTrace, result, resolved: ResolvedTune, programme: GradeProgramme, output_dir: Path):
    t = trace.time
    primary_rpm = trace.state[0] * RPM_PER_RADIAN_PER_SECOND
    secondary_rpm = trace.state[1] * RPM_PER_RADIAN_PER_SECOND
    shift_mm = trace.state[3] / MILLIMETRE
    shift_speed_mmps = trace.state[4] / MILLIMETRE
    fig, axes = plt.subplots(2, 3, figsize=(19, 10), constrained_layout=True)
    ax1, ax2, ax3, ax4, ax5, ax6 = axes.flat

    ax1.plot(t, primary_rpm, label=r"$\omega_p$")
    ax1.plot(t, secondary_rpm, label=r"$\omega_s$")
    ax1.set(title="Shaft speeds", xlabel="Time [s]", ylabel="Speed [rpm]")
    ax1.grid(True, alpha=0.25); ax1.legend()

    ax2.plot(t, shift_mm, label=r"$s$")
    ax2.axhline(resolved.constants.deadzone_shift/MILLIMETRE, linestyle="--", label="engage")
    ax2.axhline(resolved.constants.max_shift/MILLIMETRE, linestyle="--", label="high stop")
    ax2.set(title="Shift coordinate and speed", xlabel="Time [s]", ylabel="Shift [mm]")
    ax2.grid(True, alpha=0.25)
    ax2b = ax2.twinx(); ax2b.plot(t, shift_speed_mmps, linestyle=":", label=r"$\dot{s}$")
    ax2b.set_ylabel("Shift speed [mm/s]")
    h,l = ax2.get_legend_handles_labels(); h2,l2 = ax2b.get_legend_handles_labels(); ax2.legend(h+h2, l+l2, loc="best")

    ax3.plot(secondary_rpm, primary_rpm, alpha=0.22, label="full trajectory")
    for i, phase in enumerate(programme.phases):
        include_end = i == len(programme.phases) - 1
        mask = (t >= phase.start_s) & ((t <= phase.end_s) if include_end else (t < phase.end_s))
        plot_masked_runs(ax3, secondary_rpm, primary_rpm, mask, linestyle=":", linewidth=2.25, label=phase.display_label)
    ax3.scatter([secondary_rpm[0]], [primary_rpm[0]], marker="o", label="launch")
    ax3.set(title="Shift curve: phase-dotted grade programme", xlabel="Secondary speed [rpm]", ylabel="Primary speed [rpm]")
    ax3.grid(True, alpha=0.25); ax3.legend(fontsize=6.8, ncol=2)

    ax4.plot(t, trace.grade_degrees, label="grade")
    ax4.axhline(0.0, linestyle="--", linewidth=0.8)
    ax4.set(title="Route-grade programme", xlabel="Time [s]", ylabel="Grade [deg]", ylim=(-24,34))
    ax4.grid(True, alpha=0.25); ax4.legend()

    ax5.plot(t, trace.secondary_road_torque_nm, label=r"$\tau_{road,s}$")
    ax5.axhline(0.0, linestyle="--", linewidth=0.8)
    ax5.set(title="Secondary road-load torque", xlabel="Time [s]", ylabel="Torque [N m]")
    ax5.grid(True, alpha=0.25); ax5.legend()

    ax6.plot(t, trace.vehicle_speed_mps * 3.6, label="speed")
    ax6.set(title="Vehicle response and distance", xlabel="Time [s]", ylabel="Vehicle speed [km/h]")
    ax6.grid(True, alpha=0.25)
    ax6b = ax6.twinx(); ax6b.plot(t, trace.vehicle_distance_m, linestyle=":", label="distance")
    ax6b.set_ylabel("Distance [m]")
    h,l = ax6.get_legend_handles_labels(); h2,l2 = ax6b.get_legend_handles_labels(); ax6.legend(h+h2, l+l2)

    annotate_transitions((ax1, ax2, ax5, ax6), (ax1, ax2), result)
    annotate_programme((ax1, ax2, ax4, ax5, ax6), ax4, programme)
    fig.suptitle("CINDER composed grade programme | " + resolved.candidate.label() + f" | primary preload={resolved.resolved_primary_preload_mm:.2f} mm", fontsize=13)

    combined = output_dir / "grade_program_response_composed_combined.png"
    fig.savefig(combined, dpi=160)

    # Individual exports for the six panels.
    panel_specs = [
        ("01_shaft_speeds.png", ax1),
        ("02_shift_coordinate_speed.png", ax2),
        ("03_shift_curve_phase_dotted.png", ax3),
        ("04_grade_programme.png", ax4),
        ("05_secondary_road_load_torque.png", ax5),
        ("06_vehicle_response_distance.png", ax6),
    ]
    for filename, source_ax in panel_specs:
        pfig, pax = plt.subplots(figsize=(8.5, 5.0), constrained_layout=True)
        # Replot each panel directly for clean standalone images.
        if filename.startswith("01"):
            pax.plot(t, primary_rpm, label=r"$\omega_p$"); pax.plot(t, secondary_rpm, label=r"$\omega_s$"); pax.set(title="Shaft speeds", xlabel="Time [s]", ylabel="Speed [rpm]"); pax.legend()
        elif filename.startswith("02"):
            pax.plot(t, shift_mm, label=r"$s$"); pax.axhline(resolved.constants.deadzone_shift/MILLIMETRE, linestyle="--", label="engage"); pax.axhline(resolved.constants.max_shift/MILLIMETRE, linestyle="--", label="high stop"); pax.set(title="Shift coordinate", xlabel="Time [s]", ylabel="Shift [mm]"); pax.legend()
        elif filename.startswith("03"):
            pax.plot(secondary_rpm, primary_rpm, alpha=0.22, label="full trajectory")
            for i, phase in enumerate(programme.phases):
                include_end = i == len(programme.phases) - 1
                mask = (t >= phase.start_s) & ((t <= phase.end_s) if include_end else (t < phase.end_s))
                plot_masked_runs(pax, secondary_rpm, primary_rpm, mask, linestyle=":", linewidth=2.25, label=phase.display_label)
            pax.scatter([secondary_rpm[0]], [primary_rpm[0]], marker="o", label="launch")
            pax.set(title="Shift curve", xlabel="Secondary speed [rpm]", ylabel="Primary speed [rpm]"); pax.legend(fontsize=6.5, ncol=2)
        elif filename.startswith("04"):
            pax.plot(t, trace.grade_degrees, label="grade"); pax.axhline(0.0, linestyle="--", linewidth=0.8); pax.set(title="Route-grade programme", xlabel="Time [s]", ylabel="Grade [deg]", ylim=(-24,34)); pax.legend()
        elif filename.startswith("05"):
            pax.plot(t, trace.secondary_road_torque_nm, label=r"$\tau_{road,s}$"); pax.axhline(0, linestyle="--", linewidth=0.8); pax.set(title="Secondary road-load torque", xlabel="Time [s]", ylabel="Torque [N m]"); pax.legend()
        elif filename.startswith("06"):
            pax.plot(t, trace.vehicle_speed_mps * 3.6, label="speed"); pax.set(title="Vehicle response", xlabel="Time [s]", ylabel="Vehicle speed [km/h]"); p2 = pax.twinx(); p2.plot(t, trace.vehicle_distance_m, linestyle=":", label="distance"); p2.set_ylabel("Distance [m]"); h,l = pax.get_legend_handles_labels(); h2,l2 = p2.get_legend_handles_labels(); pax.legend(h+h2, l+l2)
        pax.grid(True, alpha=0.25)
        pfig.savefig(output_dir / filename, dpi=160)
        plt.close(pfig)
    return fig, combined


def write_trace(path: Path, trace: ProgrammeTrace):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "mode", "primary_rpm", "secondary_rpm", "belt_speed_mps", "shift_mm", "shift_speed_mmps", "secondary_shaft_angle_rad", "grade_deg", "secondary_road_torque_nm", "vehicle_speed_mps", "vehicle_distance_m"])
        for i, time in enumerate(trace.time):
            s = trace.state[:, i]
            w.writerow([time, trace.mode[i], s[0]*RPM_PER_RADIAN_PER_SECOND, s[1]*RPM_PER_RADIAN_PER_SECOND, s[2], s[3]/MILLIMETRE, s[4]/MILLIMETRE, s[5], trace.grade_degrees[i], trace.secondary_road_torque_nm[i], trace.vehicle_speed_mps[i], trace.vehicle_distance_m[i]])


def parse_args(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(description="Run the composed CINDER 45 s route-grade response.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/route_grade"))
    parser.add_argument("--preset", type=Path, default=Path(__file__).resolve().parent / "presets" / "circular_traction_first_reference.json")
    parser.add_argument("--final-level-seconds", type=float, default=3.0)
    parser.add_argument("--report-step-s", type=float, default=0.05)
    parser.add_argument("--rtol", type=float, default=1.0e-2)
    parser.add_argument("--atol", type=float, default=1.0e-5)
    parser.add_argument("--max-step", type=float, default=0.050)
    parser.add_argument("--no-show", action="store_true", help="Save plots without opening interactive plot windows.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None):
    args = parse_args(argv)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    preset = args.preset
    programme = GradeProgramme.default(final_level_seconds=args.final_level_seconds)
    candidate = load_candidate(preset)
    resolved = resolve_primary_preload(candidate, target_engagement_rpm=2000.0, programme=programme)
    system, engine, road_load = build_composed_system(resolved.constants, programme)
    initial_cvt = launch_cvt_state(primary_rpm=1800.0)
    initial_full = system.initial_state(cvt_state=initial_cvt, host_state=system.host.initial_state(secondary_shaft_angle=0.0))
    initial_mode = system.classify_initial_mode(initial_full)
    settings = HybridIntegratorSettings(relative_tolerance=args.rtol, absolute_tolerance=args.atol, method="LSODA", max_step=args.max_step, maximum_transitions=160, retain_dense_output=True)
    print("Running composed 45 s grade programme")
    print(resolved.candidate.label())
    print(f"primary preload={resolved.resolved_primary_preload_mm:.3f} mm; lower-stop reaction={resolved.lower_stop_reaction_at_target_n:.6g} N")
    result = integrate_hybrid(system=system, time_span=(0.0, 45.0), initial_state=initial_full, initial_mode=initial_mode, settings=settings)
    print("completed", result.completed, result.termination_reason, len(result.segments), "segments", len(result.transitions), "transitions")
    if not result.completed:
        raise RuntimeError(result.termination_reason)
    trace = sample_trace(system, result, programme, report_step_s=args.report_step_s)
    fig, combined = plot_response(trace, result, resolved, programme, output_dir)
    write_trace(output_dir / "grade_program_trace_composed.csv", trace)
    summary = {
        "completed": result.completed,
        "termination_reason": result.termination_reason,
        "segments": len(result.segments),
        "transitions": [{"time": rec.time, "reason": rec.transition.reason} for rec in result.transitions],
        "resolved_primary_preload_mm": resolved.resolved_primary_preload_mm,
        "final_primary_rpm": float(trace.state[0, -1] * RPM_PER_RADIAN_PER_SECOND),
        "final_secondary_rpm": float(trace.state[1, -1] * RPM_PER_RADIAN_PER_SECOND),
        "final_vehicle_speed_kmh": float(trace.vehicle_speed_mps[-1] * 3.6),
        "final_vehicle_distance_m": float(trace.vehicle_distance_m[-1]),
        "max_shift_mm": float(np.max(trace.state[3] / MILLIMETRE)),
        "min_shift_mm": float(np.min(trace.state[3] / MILLIMETRE)),
    }
    (output_dir / "grade_program_summary_composed.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote plots and trace to: {output_dir.resolve()}")
    if args.no_show:
        plt.close(fig)
    else:
        plt.show()

if __name__ == "__main__":
    main()
