"""Shared executable Baja reference helpers for CINDER v1.1.2 Results.

This module is deliberately small.  It owns only definitions that are genuinely
shared by more than one Results study: loading the frozen Baja reference model,
a time-programmed road-grade boundary, the frozen tuning descriptors, and the
common trace sampler used by legacy-equivalent actuator/helix protocols.

No code here reads cvtModel/launchTools or repository Git history.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from math import radians
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
from cinder.hosts import SecondaryShaftAngleHost
from cinder.model.boundaries.shaft import (
    FullThrottleEngineBoundary,
    ShaftBoundaryContext,
)
from cinder.model.boundaries.vehicle import RoadLoadModel
from cinder.model.system import CVTState, MechanicalCVTPlant, ShaftBoundaryValue

from defaults.reference_model import decode_reference_case

HERE = Path(__file__).resolve().parent
SIMULATION_CASE = HERE / "simulation_case.json"
TUNING = HERE / "tuning.json"
DEFAULT_FIXED_PIVOT_PRESET = TUNING

RPM_TO_RAD_PER_SECOND = 2.0 * np.pi / 60.0
RPM_PER_RADIAN_PER_SECOND = 60.0 / (2.0 * np.pi)
MILLIMETRE = 1.0e-3


@dataclass(frozen=True, slots=True)
class TuneCandidate:
    tip_hardware_mass_per_flyweight_kg: float
    helix_angle_degrees: float
    secondary_torsional_pretension_degrees: float
    secondary_compression_preload_mm: float
    primary_linear_ramp_angle_degrees: float
    primary_circular_ramp_start_angle_degrees: float
    primary_circular_ramp_end_angle_degrees: float


@dataclass(frozen=True, slots=True)
class ReferenceConstants:
    engine_rotational_inertia: float
    gearbox_input_rotational_inertia: float
    final_drive_ratio: float
    deadzone_shift: float
    max_shift: float


@dataclass(frozen=True, slots=True)
class ResolvedTune:
    candidate: TuneCandidate
    constants: ReferenceConstants
    target_engagement_rpm: float


@dataclass(frozen=True, slots=True)
class GradePhase:
    name: str
    start_s: float
    end_s: float
    start_degrees: float
    end_degrees: float
    transition: bool = False

    def contains(self, time_s: float, *, include_end: bool = False) -> bool:
        return (
            self.start_s <= time_s <= self.end_s
            if include_end
            else self.start_s <= time_s < self.end_s
        )

    def grade_radians(self, time_s: float) -> float:
        if self.end_s <= self.start_s or not self.transition:
            return radians(self.start_degrees)
        u = smoothstep((float(time_s) - self.start_s) / (self.end_s - self.start_s))
        return radians(self.start_degrees + (self.end_degrees - self.start_degrees) * u)


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
        for index, phase in enumerate(self.phases):
            if phase.contains(float(time_s), include_end=index == len(self.phases) - 1):
                return phase.grade_radians(float(time_s))
        return radians(self.phases[-1].end_degrees)


def smoothstep(value: float) -> float:
    value = float(np.clip(value, 0.0, 1.0))
    return value * value * (3.0 - 2.0 * value)


class TimeProgrammedLockedFinalDriveBoundary:
    """Locked final-drive boundary whose road grade is programmed in time."""

    def __init__(
        self,
        *,
        road_load: RoadLoadModel,
        programme: GradeProgramme,
        direct_secondary_shaft_inertia: float = 0.0,
    ) -> None:
        self.road_load = road_load
        self.programme = programme
        self.direct_secondary_shaft_inertia = float(direct_secondary_shaft_inertia)

    @property
    def reflected_rotational_inertia(self) -> float:
        final_drive = self.road_load.final_drive
        vehicle = self.road_load.vehicle
        return (
            self.direct_secondary_shaft_inertia
            + final_drive.secondary_inertia_from_wheel_rotation(
                wheel_rotational_inertia=vehicle.wheel_rotational_inertia
            )
            + final_drive.secondary_inertia_from_vehicle_mass(vehicle_mass=vehicle.mass)
        )

    def evaluate(self, context: ShaftBoundaryContext) -> ShaftBoundaryValue:
        if context.shaft != "secondary":
            raise ValueError("TimeProgrammedLockedFinalDriveBoundary must attach to secondary.")
        secondary_angle = float(context.host["secondary_shaft_angle"])
        distance = self.road_load.final_drive.vehicle_distance_from_secondary_angle(
            secondary_shaft_angle=secondary_angle
        )
        grade_angle = self.programme.grade_radians(context.time)
        road = self.road_load.evaluate(
            secondary_angular_speed=context.cvt.secondary_angular_speed,
            grade_angle=grade_angle,
        )
        return ShaftBoundaryValue(
            external_torque=road.secondary_external_torque,
            equivalent_inertia=self.reflected_rotational_inertia,
            metadata={
                "road_load": road,
                "vehicle_distance": distance,
                "grade_angle": grade_angle,
            },
        )


def _document() -> dict[str, Any]:
    return json.loads(SIMULATION_CASE.read_text(encoding="utf-8"))


def load_candidate(path: Path = DEFAULT_FIXED_PIVOT_PRESET) -> TuneCandidate:
    # The tuning manifest is descriptive; simulation_case.json remains executable authority.
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return TuneCandidate(
        tip_hardware_mass_per_flyweight_kg=float(payload["primary"]["flyweights"]["tip_hardware_mass_per_flyweight_kg"]),
        helix_angle_degrees=float(payload["secondary"]["helix"]["helix_angle_from_circumferential_deg"]),
        secondary_torsional_pretension_degrees=float(payload["secondary"]["helix"]["initial_twist_deg"]),
        secondary_compression_preload_mm=1000.0 * float(payload["secondary"]["axial_spring"]["initial_compression_m"]),
        primary_linear_ramp_angle_degrees=float(payload["primary"]["ramp"]["linear_angle_deg"]),
        primary_circular_ramp_start_angle_degrees=float(payload["primary"]["ramp"]["circular_start_angle_deg"]),
        primary_circular_ramp_end_angle_degrees=float(payload["primary"]["ramp"]["circular_end_angle_deg"]),
    )


def reference_constants() -> ReferenceConstants:
    document = _document()
    primary = document["shaft_boundaries"]["primary"]
    secondary = document["shaft_boundaries"]["secondary"]
    geometry = document["assembly"]["geometry"]
    return ReferenceConstants(
        engine_rotational_inertia=float(primary["equivalent_rotational_inertia_kg_m2"]),
        gearbox_input_rotational_inertia=float(secondary["direct_secondary_shaft_inertia_kg_m2"]),
        final_drive_ratio=float(secondary["final_drive"]["reduction_ratio"]),
        deadzone_shift=float(geometry["deadzone_shift_m"]),
        max_shift=float(geometry["max_shift_m"]),
    )


def resolve_primary_preload(
    candidate: TuneCandidate,
    *,
    target_engagement_rpm: float,
    programme: GradeProgramme,
) -> ResolvedTune:
    # The release input already contains the resolved preload used by the Results
    # campaign. Re-solving it here would duplicate setup logic and permit the study
    # to drift away from the frozen executable document.
    del programme
    return ResolvedTune(
        candidate=candidate,
        constants=reference_constants(),
        target_engagement_rpm=float(target_engagement_rpm),
    )


def build_components(constants: ReferenceConstants):
    del constants
    decoded = decode_reference_case()
    primary = decoded.system.primary_boundary
    secondary = decoded.system.secondary_boundary
    return decoded.assembly, primary.torque_curve, secondary.road_load


def build_composed_system(
    constants: ReferenceConstants,
    programme: GradeProgramme | None = None,
) -> tuple[ComposedCVTHybridSystem, object, RoadLoadModel]:
    assembly, engine, road_load = build_components(constants)
    plant = MechanicalCVTPlant.from_assembly(assembly)
    host = SecondaryShaftAngleHost()
    secondary = TimeProgrammedLockedFinalDriveBoundary(
        road_load=road_load,
        programme=programme or GradeProgramme.default(),
        direct_secondary_shaft_inertia=constants.gearbox_input_rotational_inertia,
    )
    system = ComposedCVTHybridSystem.from_plant(
        plant=plant,
        primary_boundary=FullThrottleEngineBoundary(
            engine,
            equivalent_rotational_inertia=constants.engine_rotational_inertia,
        ),
        secondary_boundary=secondary,
        host=host,
    )
    return system, engine, road_load


def launch_cvt_state(*, primary_rpm: float = 1800.0) -> CVTState:
    return CVTState(
        primary_angular_speed=float(primary_rpm) * RPM_TO_RAD_PER_SECOND,
        secondary_angular_speed=0.0,
        belt_speed=0.0,
        shift_position=0.0,
        shift_speed=0.0,
    )


@dataclass(frozen=True, slots=True)
class ProgrammeTrace:
    time: NDArray[np.float64]
    state: NDArray[np.float64]
    mode: tuple[str, ...]
    grade_degrees: NDArray[np.float64]
    secondary_road_torque_nm: NDArray[np.float64]
    vehicle_speed_mps: NDArray[np.float64]
    vehicle_distance_m: NDArray[np.float64]


def _compact_mode(mode) -> str:
    cvt = getattr(mode, "cvt", mode)
    if cvt.contact_regime is None:
        return f"{cvt.engagement.value}/{cvt.shift_constraint.value}"
    return f"{cvt.engagement.value}/{cvt.shift_constraint.value}/{cvt.contact_regime.mode.value}"


def sample_trace(
    system: ComposedCVTHybridSystem,
    result,
    programme: GradeProgramme,
    report_step_s: float = 0.01,
) -> ProgrammeTrace:
    rows: list[tuple] = []
    for segment in result.segments:
        t0, t1 = segment.start_time, segment.end_time
        if segment.has_dense_output:
            times = np.arange(t0, t1, report_step_s)
            if len(times) == 0 or abs(times[0] - t0) > 1.0e-12:
                times = np.r_[t0, times]
            times = np.unique(np.r_[times, t1])
            states = segment.dense_state_at(times)
        else:
            times = segment.time
            states = segment.state
        for index, time in enumerate(times):
            full = np.asarray(states[:, index], dtype=float).copy()
            full[3] = np.clip(full[3], 0.0, system.cvt.model.geometry.spec.max_shift)
            boundaries = system._shaft_boundaries(time=float(time), state=full)
            road = boundaries.secondary.metadata.get("road_load")
            rows.append(
                (
                    float(time),
                    full,
                    _compact_mode(segment.mode),
                    float(np.rad2deg(programme.grade_radians(float(time)))),
                    float(getattr(road, "secondary_external_torque", np.nan)),
                    float(getattr(road, "vehicle_speed", np.nan)),
                    float(boundaries.secondary.metadata.get("vehicle_distance", np.nan)),
                )
            )
    merged = {round(row[0], 12): row for row in rows}
    ordered = [merged[key] for key in sorted(merged)]
    return ProgrammeTrace(
        time=np.asarray([row[0] for row in ordered], dtype=float),
        state=np.column_stack([row[1] for row in ordered]),
        mode=tuple(row[2] for row in ordered),
        grade_degrees=np.asarray([row[3] for row in ordered], dtype=float),
        secondary_road_torque_nm=np.asarray([row[4] for row in ordered], dtype=float),
        vehicle_speed_mps=np.asarray([row[5] for row in ordered], dtype=float),
        vehicle_distance_m=np.asarray([row[6] for row in ordered], dtype=float),
    )
