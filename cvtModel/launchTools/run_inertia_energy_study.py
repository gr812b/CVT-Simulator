"""Run one-factor CVT/vehicle inertia studies with the saved launch tune.

This tool keeps the selected launch tune fixed, then varies only one inertia
source at a time:

* complete primary-side spin inertia, including engine plus primary CVT inertia;
* secondary-side spin inertia, including secondary CVT/driveline/wheel rotation but
  excluding vehicle translational mass;
* physical vehicle mass, reflected to the secondary through the locked final drive.

It writes an effective-inertia-vs-ratio plot plus a small suite of driving
scenarios that expose when inertial energy helps, hurts, or is thrown away:

* level_accel: flat straight acceleration from rest;
* uphill_route: flat approach, then a distance-indexed smooth uphill step;
* brake_pulse: flat route with a distance-indexed braking-force pulse;
* rolling_route: repeated grade changes on the same distance-indexed route.

The reported "useful energy" is not a thermodynamic CVT efficiency.  It is an
application metric: final vehicle translational kinetic energy plus net vehicle
potential-energy gain, divided by positive crank work.  Brake work is reported
separately so inertial energy that was stored and then intentionally discarded
is visible.

Example, from the repository root:

    python launchTools/run_inertia_energy_study.py --no-show

    python launchTools/run_inertia_energy_study.py --duration-s 8 --primary-scales 0.5 1.0 2.0 --secondary-scales 0.5 1.0 1.25 --vehicle-mass-scales 0.85 1.0 1.15 --no-show

PowerShell uses a backtick (`), not a backslash, for multi-line commands.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
import json
from contextlib import contextmanager
from math import radians, sqrt
import signal
from pathlib import Path
import sys
from typing import Callable, Iterable, Sequence

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

_TOOLS_DIRECTORY = Path(__file__).resolve().parent
_REPOSITORY_ROOT = _TOOLS_DIRECTORY.parent
if str(_TOOLS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIRECTORY))
for candidate_path in (
    _REPOSITORY_ROOT / "src",
    _REPOSITORY_ROOT,
    _REPOSITORY_ROOT / "tools",
):
    if str(candidate_path) not in sys.path:
        sys.path.append(str(candidate_path))

from cinder.execution.hybrid import CVTDynamicState, HybridIntegratorSettings  # noqa: E402
from cinder.model.boundaries.output import (  # noqa: E402
    LockedFinalDriveVehicle,
    OutputBoundaryEvaluation,
)
from cinder.model.boundaries.output.vehicle import (  # noqa: E402
    CallableRoadProfile,
    ConstantGradeRoadProfile,
)
from cinder.results import ReportingGrid, ReportingSettings  # noqa: E402
from launch_tuning_common import (  # noqa: E402
    MILLIMETRE,
    RPM_PER_RADIAN_PER_SECOND,
    TuneCandidate,
    build_operating_configuration,
    build_system_from_case,
    launch_initial_state,
    resolve_primary_preload,
)

_DEFAULT_PRESET = (
    _TOOLS_DIRECTORY / "presets" / "circular_traction_first_reference.json"
)


@dataclass(frozen=True, slots=True)
class InertiaVariant:
    """One fixed tune with exactly one inertia source varied."""

    key: str
    label: str
    varied_piece: str
    scale: float
    constants: object


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    """One distance-indexed test route."""

    key: str
    label: str
    duration_s: float
    road_profile_factory: Callable[[], object]
    output_boundary_factory: Callable[[LockedFinalDriveVehicle], object] | None = None


@dataclass(frozen=True, slots=True)
class SampledRun:
    """State-known samples for one completed integration."""

    scenario_key: str
    scenario_label: str
    variant_key: str
    variant_label: str
    varied_piece: str
    scale: float
    time_s: NDArray[np.float64]
    state: NDArray[np.float64]
    vehicle_distance_m: NDArray[np.float64]
    vehicle_speed_mps: NDArray[np.float64]
    grade_rad: NDArray[np.float64]
    effective_ratio: NDArray[np.float64]
    engine_torque_nm: NDArray[np.float64]
    engine_power_w: NDArray[np.float64]
    road_external_force_n: NDArray[np.float64]
    road_external_torque_nm: NDArray[np.float64]
    brake_force_n: NDArray[np.float64]
    brake_power_w: NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class BrakePulseVehicle:
    """Locked final-drive vehicle with an extra distance-indexed brake force.

    The brake force is not part of the base road-load model; it is added here as
    an external force so the same CVT case contract can represent a simple
    driver-braking or obstacle-drag pulse.  The force always opposes vehicle
    motion and is smoothed at the distance boundaries.
    """

    base: LockedFinalDriveVehicle
    start_distance_m: float
    end_distance_m: float
    brake_force_n: float
    edge_distance_m: float = 3.0
    speed_regularization_mps: float = 0.05

    def __post_init__(self) -> None:
        if not isinstance(self.base, LockedFinalDriveVehicle):
            raise TypeError("base must be a LockedFinalDriveVehicle.")
        if not self.start_distance_m < self.end_distance_m:
            raise ValueError("Brake pulse requires start < end distance.")
        for name, value in (
            ("brake_force_n", self.brake_force_n),
            ("edge_distance_m", self.edge_distance_m),
            ("speed_regularization_mps", self.speed_regularization_mps),
        ):
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive.")

    @property
    def final_drive(self):
        return self.base.final_drive

    @property
    def vehicle(self):
        return self.base.vehicle

    @property
    def reflected_rotational_inertia(self) -> float:
        return self.base.reflected_rotational_inertia

    def brake_weight(self, *, vehicle_distance_m: float) -> float:
        up = _smoothstep(
            (vehicle_distance_m - self.start_distance_m) / self.edge_distance_m
        )
        down = 1.0 - _smoothstep(
            (vehicle_distance_m - self.end_distance_m) / self.edge_distance_m
        )
        return float(np.clip(up * down, 0.0, 1.0))

    def brake_force(self, *, vehicle_distance_m: float, vehicle_speed_mps: float) -> float:
        weight = self.brake_weight(vehicle_distance_m=vehicle_distance_m)
        direction = vehicle_speed_mps / sqrt(
            vehicle_speed_mps**2 + self.speed_regularization_mps**2
        )
        return -self.brake_force_n * weight * direction

    def evaluate(self, *, state: CVTDynamicState) -> OutputBoundaryEvaluation:
        evaluation = self.base.evaluate(state=state)
        if evaluation.road_load is None or evaluation.vehicle_distance is None:
            return evaluation
        brake_force = self.brake_force(
            vehicle_distance_m=evaluation.vehicle_distance,
            vehicle_speed_mps=evaluation.road_load.vehicle_speed,
        )
        brake_torque = self.base.final_drive.secondary_torque_from_wheel_force(
            wheel_force=brake_force
        )
        return replace(
            evaluation,
            external_torque=evaluation.external_torque + brake_torque,
        )


class MultiHillRoad:
    """Compact distance-indexed route used for the rolling-route scenario."""

    def __init__(self) -> None:
        self._bumps = (
            # start, end, grade degrees; positive is uphill.
            (12.0, 32.0, 9.0),
            (38.0, 62.0, -7.0),
            (70.0, 95.0, 12.0),
            (105.0, 130.0, -5.0),
        )

    def grade_radians(self, vehicle_distance_m: float) -> float:
        distance = max(0.0, float(vehicle_distance_m))
        grade = 0.0
        edge = 6.0
        for start, end, degrees in self._bumps:
            up = _smoothstep((distance - start) / edge)
            down = 1.0 - _smoothstep((distance - end) / edge)
            grade += radians(degrees) * float(np.clip(up * down, 0.0, 1.0))
        return grade


class UphillStepRoad:
    """Flat approach, smooth ramp, then constant uphill hold."""

    def __init__(
        self,
        *,
        start_distance_m: float = 16.0,
        ramp_distance_m: float = 8.0,
        hold_grade_degrees: float = 18.0,
    ) -> None:
        self.start_distance_m = start_distance_m
        self.ramp_distance_m = ramp_distance_m
        self.hold_grade_degrees = hold_grade_degrees

    def grade_radians(self, vehicle_distance_m: float) -> float:
        distance = max(0.0, float(vehicle_distance_m))
        fraction = (distance - self.start_distance_m) / self.ramp_distance_m
        return radians(self.hold_grade_degrees) * _smoothstep(fraction)


def _smoothstep(value: float) -> float:
    value = float(np.clip(value, 0.0, 1.0))
    return value * value * (3.0 - 2.0 * value)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", type=Path, default=_DEFAULT_PRESET)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/inertia_energy_study"))
    parser.add_argument("--duration-s", type=float, default=10.0)
    parser.add_argument("--initial-primary-rpm", type=float, default=1800.0)
    parser.add_argument("--target-engagement-rpm", type=float, default=2000.0)
    parser.add_argument("--solver-method", default=None)
    parser.add_argument("--max-step-ms", type=float, default=None)
    parser.add_argument("--relative-tolerance", type=float, default=None)
    parser.add_argument("--absolute-tolerance", type=float, default=None)
    parser.add_argument("--report-step-ms", type=float, default=20.0)
    parser.add_argument("--maximum-transitions", type=int, default=80)
    parser.add_argument(
        "--primary-scales",
        type=float,
        nargs="+",
        default=(0.5, 1.0, 2.0),
        help="Scale factors for complete primary-side spin inertia: engine plus primary CVT inertia.",
    )
    parser.add_argument(
        "--secondary-scales",
        type=float,
        nargs="+",
        default=(0.5, 1.0, 1.25),
        help="Scale factors for secondary-side rotational inertia: secondary CVT, gearbox input, movable secondary, and driven-wheel rotation. Vehicle translational mass is excluded.",
    )
    parser.add_argument(
        "--vehicle-mass-scales",
        type=float,
        nargs="+",
        default=(0.85, 1.0, 1.15),
        help="Scale factors for physical vehicle mass.",
    )
    parser.add_argument(
        "--scenario",
        choices=("level_accel", "uphill_route", "brake_pulse", "rolling_route"),
        action="append",
        help="Run only the selected scenario(s). Omit to run the full suite.",
    )
    parser.add_argument(
        "--per-run-timeout-s",
        type=float,
        default=120.0,
        help="Best-effort Unix timeout for one variant/scenario integration; use 0 to disable.",
    )
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()

    for name in (
        "duration_s",
        "initial_primary_rpm",
        "target_engagement_rpm",
        "report_step_ms",
    ):
        value = getattr(args, name)
        if not np.isfinite(value) or value <= 0.0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive.")
    for name in ("max_step_ms", "relative_tolerance", "absolute_tolerance"):
        value = getattr(args, name)
        if value is not None and (not np.isfinite(value) or value <= 0.0):
            parser.error(f"--{name.replace('_', '-')} must be finite and positive.")
    for group_name in ("primary_scales", "secondary_scales", "vehicle_mass_scales"):
        values = tuple(getattr(args, group_name))
        if not values or any((not np.isfinite(value) or value <= 0.0) for value in values):
            parser.error(f"--{group_name.replace('_', '-')} values must be positive.")
    if args.maximum_transitions < 1:
        parser.error("--maximum-transitions must be at least one.")
    if args.per_run_timeout_s < 0.0 or not np.isfinite(args.per_run_timeout_s):
        parser.error("--per-run-timeout-s must be finite and non-negative.")
    return args


def load_reference(path: Path) -> tuple[TuneCandidate, dict[str, float | str]]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    data = payload["candidate"]
    candidate = TuneCandidate(
        flyweight_mass_kg=float(data["flyweight_mass_kg"]),
        helix_angle_degrees=float(data["helix_angle_degrees"]),
        secondary_torsional_pretension_degrees=float(
            data["secondary_torsional_pretension_degrees"]
        ),
        secondary_compression_preload_mm=float(
            data["secondary_compression_preload_mm"]
        ),
        primary_ramp_kind=data.get("primary_ramp_kind") or "linear",
        primary_ramp_angle_degrees=float(data.get("primary_ramp_angle_degrees") or 30.0),
        primary_ramp_start_angle_degrees=float(
            data.get("primary_ramp_start_angle_degrees") or 42.0
        ),
        primary_ramp_end_angle_degrees=float(
            data.get("primary_ramp_end_angle_degrees") or 12.0
        ),
    )
    return candidate, dict(payload.get("integration", {}))


def build_variants(
    *,
    base_constants,
    primary_scales: Sequence[float],
    secondary_scales: Sequence[float],
    vehicle_mass_scales: Sequence[float],
) -> tuple[InertiaVariant, ...]:
    variants: list[InertiaVariant] = []
    seen_baseline = False

    def add_variant(key: str, label: str, varied_piece: str, scale: float, constants) -> None:
        nonlocal seen_baseline
        if abs(scale - 1.0) < 1.0e-12:
            if seen_baseline:
                return
            key = "baseline"
            label = "baseline"
            varied_piece = "none"
            seen_baseline = True
        variants.append(
            InertiaVariant(
                key=key,
                label=label,
                varied_piece=varied_piece,
                scale=float(scale),
                constants=constants,
            )
        )

    for scale in primary_scales:
        add_variant(
            key=f"primary_x{scale:g}",
            label=f"primary spin ×{scale:g}",
            varied_piece="primary_side_spin_inertia",
            scale=scale,
            constants=replace(
                base_constants,
                engine_rotational_inertia=(
                    base_constants.engine_rotational_inertia * scale
                ),
                primary_cvt_rotational_inertia=(
                    base_constants.primary_cvt_rotational_inertia * scale
                ),
            ),
        )
    for scale in secondary_scales:
        add_variant(
            key=f"secondary_x{scale:g}",
            label=f"secondary spin ×{scale:g}",
            varied_piece="secondary_side_spin_inertia_excluding_vehicle_translation",
            scale=scale,
            constants=replace(
                base_constants,
                secondary_fixed_rotational_inertia=(
                    base_constants.secondary_fixed_rotational_inertia * scale
                ),
                gearbox_input_rotational_inertia=(
                    base_constants.gearbox_input_rotational_inertia * scale
                ),
                secondary_movable_sheave_rotational_inertia=(
                    base_constants.secondary_movable_sheave_rotational_inertia * scale
                ),
                driven_wheel_rotational_inertia=(
                    base_constants.driven_wheel_rotational_inertia * scale
                ),
            ),
        )
    for scale in vehicle_mass_scales:
        add_variant(
            key=f"vehicle_x{scale:g}",
            label=f"vehicle mass ×{scale:g}",
            varied_piece="vehicle_mass",
            scale=scale,
            constants=replace(
                base_constants,
                vehicle_mass=base_constants.vehicle_mass * scale,
            ),
        )
    return tuple(variants)


def scenario_specs(duration_s: float) -> tuple[ScenarioSpec, ...]:
    return (
        ScenarioSpec(
            key="level_accel",
            label="Level acceleration",
            duration_s=duration_s,
            road_profile_factory=lambda: ConstantGradeRoadProfile(0.0),
        ),
        ScenarioSpec(
            key="uphill_route",
            label="Flat → 18° uphill route",
            duration_s=duration_s,
            road_profile_factory=lambda: CallableRoadProfile(
                grade_angle_function=UphillStepRoad().grade_radians
            ),
        ),
        ScenarioSpec(
            key="brake_pulse",
            label="Level route with brake pulse",
            duration_s=duration_s,
            road_profile_factory=lambda: ConstantGradeRoadProfile(0.0),
            output_boundary_factory=lambda base: BrakePulseVehicle(
                base=base,
                start_distance_m=16.0,
                end_distance_m=30.0,
                brake_force_n=350.0,
            ),
        ),
        ScenarioSpec(
            key="rolling_route",
            label="Rolling grade route",
            duration_s=duration_s,
            road_profile_factory=lambda: CallableRoadProfile(
                grade_angle_function=MultiHillRoad().grade_radians
            ),
        ),
    )


def build_case_for_scenario(constants, scenario: ScenarioSpec):
    configuration, baseline = build_operating_configuration(constants)
    road_profile = scenario.road_profile_factory()
    base_boundary = baseline.case.output_boundary
    if not isinstance(base_boundary, LockedFinalDriveVehicle):
        raise TypeError("Inertia study expects the baseline locked vehicle boundary.")
    road_boundary = base_boundary.with_road_profile(road_profile)
    output_boundary = (
        scenario.output_boundary_factory(road_boundary)
        if scenario.output_boundary_factory is not None
        else road_boundary
    )
    return baseline.case.with_output_boundary(output_boundary), configuration


def run_variant_scenario(
    *,
    variant: InertiaVariant,
    scenario: ScenarioSpec,
    initial_primary_rpm: float,
    solver_method: str,
    max_step_s: float,
    relative_tolerance: float,
    absolute_tolerance: float,
    maximum_transitions: int,
    report_step_s: float,
) -> tuple[object, object, SampledRun]:
    case, configuration = build_case_for_scenario(variant.constants, scenario)
    system = build_system_from_case(case, configuration=configuration)
    result = system.run(
        time_span=(0.0, scenario.duration_s),
        initial_state=launch_initial_state(primary_rpm=initial_primary_rpm),
        settings=HybridIntegratorSettings(
            method=solver_method,
            max_step=max_step_s,
            relative_tolerance=relative_tolerance,
            absolute_tolerance=absolute_tolerance,
            maximum_transitions=maximum_transitions,
        ),
        reporting_settings=ReportingSettings(
            grid=ReportingGrid.uniform_time_step(report_step_s),
        ),
    )
    trace = sample_run(
        system=system,
        result=result,
        scenario=scenario,
        variant=variant,
    )
    return system, result, trace


def _sample_indices(count: int) -> range:
    return range(count)


def sample_run(*, system, result, scenario: ScenarioSpec, variant: InertiaVariant) -> SampledRun:
    time_values: list[float] = []
    state_values: list[NDArray[np.float64]] = []
    distance_values: list[float] = []
    speed_values: list[float] = []
    grade_values: list[float] = []
    ratio_values: list[float] = []
    engine_torque_values: list[float] = []
    engine_power_values: list[float] = []
    road_force_values: list[float] = []
    road_torque_values: list[float] = []
    brake_force_values: list[float] = []
    brake_power_values: list[float] = []

    brake_boundary = (
        system.model.output_boundary
        if isinstance(system.model.output_boundary, BrakePulseVehicle)
        else None
    )

    for segment in result.segments:
        for index in _sample_indices(segment.state.shape[1]):
            vector = np.asarray(segment.state[:, index], dtype=float)
            state = CVTDynamicState.from_vector(vector)
            snapshot = system.model.snapshot(state=state)
            road = snapshot.vehicle_road_load
            brake_force = 0.0
            if brake_boundary is not None:
                brake_force = brake_boundary.brake_force(
                    vehicle_distance_m=snapshot.vehicle_distance,
                    vehicle_speed_mps=road.vehicle_speed,
                )
            time_values.append(float(segment.time[index]))
            state_values.append(vector)
            distance_values.append(float(snapshot.vehicle_distance))
            speed_values.append(float(road.vehicle_speed))
            grade_values.append(float(road.grade_angle))
            ratio_values.append(
                float(
                    snapshot.geometry.secondary.effective
                    / snapshot.geometry.primary.effective
                )
            )
            engine_torque_values.append(float(snapshot.engine_torque))
            engine_power_values.append(float(snapshot.engine_torque * state.primary_angular_speed))
            road_force_values.append(float(road.external_force + brake_force))
            road_torque_values.append(float(snapshot.secondary_external_torque))
            brake_force_values.append(float(brake_force))
            brake_power_values.append(float(brake_force * road.vehicle_speed))

    return SampledRun(
        scenario_key=scenario.key,
        scenario_label=scenario.label,
        variant_key=variant.key,
        variant_label=variant.label,
        varied_piece=variant.varied_piece,
        scale=variant.scale,
        time_s=np.asarray(time_values, dtype=float),
        state=np.column_stack(state_values),
        vehicle_distance_m=np.asarray(distance_values, dtype=float),
        vehicle_speed_mps=np.asarray(speed_values, dtype=float),
        grade_rad=np.asarray(grade_values, dtype=float),
        effective_ratio=np.asarray(ratio_values, dtype=float),
        engine_torque_nm=np.asarray(engine_torque_values, dtype=float),
        engine_power_w=np.asarray(engine_power_values, dtype=float),
        road_external_force_n=np.asarray(road_force_values, dtype=float),
        road_external_torque_nm=np.asarray(road_torque_values, dtype=float),
        brake_force_n=np.asarray(brake_force_values, dtype=float),
        brake_power_w=np.asarray(brake_power_values, dtype=float),
    )


def integrate_positive(time: NDArray[np.float64], signal: NDArray[np.float64]) -> float:
    if len(time) < 2:
        return 0.0
    return float(np.trapezoid(np.maximum(signal, 0.0), time))


def integrate_negative_magnitude(time: NDArray[np.float64], signal: NDArray[np.float64]) -> float:
    if len(time) < 2:
        return 0.0
    return float(np.trapezoid(np.maximum(-signal, 0.0), time))


def summarize_run(trace: SampledRun, constants) -> dict[str, float | str]:
    time = trace.time_s
    distance = trace.vehicle_distance_m
    speed = trace.vehicle_speed_mps
    mass = constants.vehicle_mass
    final_ke_j = 0.5 * mass * speed[-1] ** 2
    potential_j = float(
        np.trapezoid(mass * constants.gravity_like() * np.sin(trace.grade_rad), distance)
        if hasattr(constants, "gravity_like")
        else np.trapezoid(mass * 9.80665 * np.sin(trace.grade_rad), distance)
    )
    positive_engine_work_j = integrate_positive(time, trace.engine_power_w)
    engine_braking_work_j = integrate_negative_magnitude(time, trace.engine_power_w)
    brake_dissipated_j = integrate_negative_magnitude(time, trace.brake_power_w)
    useful_energy_j = final_ke_j + potential_j
    useful_fraction = useful_energy_j / positive_engine_work_j if positive_engine_work_j > 0.0 else np.nan
    return {
        "scenario": trace.scenario_key,
        "scenario_label": trace.scenario_label,
        "variant": trace.variant_key,
        "variant_label": trace.variant_label,
        "varied_piece": trace.varied_piece,
        "scale": trace.scale,
        "completed_time_s": float(time[-1]),
        "final_distance_m": float(distance[-1]),
        "final_speed_mps": float(speed[-1]),
        "maximum_speed_mps": float(np.max(speed)),
        "final_ratio_secondary_over_primary": float(trace.effective_ratio[-1]),
        "minimum_ratio_secondary_over_primary": float(np.min(trace.effective_ratio)),
        "maximum_ratio_secondary_over_primary": float(np.max(trace.effective_ratio)),
        "final_shift_mm": float(trace.state[3, -1] / MILLIMETRE),
        "maximum_shift_mm": float(np.max(trace.state[3]) / MILLIMETRE),
        "positive_engine_work_kj": positive_engine_work_j / 1000.0,
        "engine_braking_work_kj": engine_braking_work_j / 1000.0,
        "final_vehicle_kinetic_kj": final_ke_j / 1000.0,
        "net_vehicle_potential_change_kj": potential_j / 1000.0,
        "apparent_useful_energy_kj": useful_energy_j / 1000.0,
        "apparent_useful_fraction": float(useful_fraction),
        "brake_dissipated_kj": brake_dissipated_j / 1000.0,
    }


def effective_inertia_curves(
    *,
    variants: Sequence[InertiaVariant],
    ratio_grid: NDArray[np.float64],
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for variant in variants:
        c = variant.constants
        primary_direct = c.engine_rotational_inertia + c.primary_cvt_rotational_inertia
        secondary_core = (
            c.secondary_fixed_rotational_inertia
            + c.gearbox_input_rotational_inertia
            + c.secondary_movable_sheave_rotational_inertia
        )
        wheel_at_secondary = c.driven_wheel_rotational_inertia / c.final_drive_ratio**2
        vehicle_translation_at_secondary = (
            c.vehicle_mass * (c.wheel_radius / c.final_drive_ratio) ** 2
        )
        secondary_spin_at_secondary = secondary_core + wheel_at_secondary
        for ratio in ratio_grid:
            secondary_spin_reflected = secondary_spin_at_secondary / ratio**2
            vehicle_translation_reflected = vehicle_translation_at_secondary / ratio**2
            total = primary_direct + secondary_spin_reflected + vehicle_translation_reflected
            rows.append(
                {
                    "variant": variant.key,
                    "variant_label": variant.label,
                    "varied_piece": variant.varied_piece,
                    "scale": variant.scale,
                    "ratio_secondary_over_primary": float(ratio),
                    "primary_direct_kg_m2": float(primary_direct),
                    "secondary_spin_reflected_to_primary_kg_m2": float(secondary_spin_reflected),
                    "vehicle_translation_reflected_to_primary_kg_m2": float(vehicle_translation_reflected),
                    "total_effective_primary_side_kg_m2": float(total),
                }
            )
    return rows


def write_dict_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_trace_csv(path: Path, traces: Sequence[SampledRun]) -> None:
    header = (
        "scenario",
        "variant",
        "variant_label",
        "varied_piece",
        "scale",
        "time_s",
        "primary_rpm",
        "secondary_rpm",
        "belt_speed_mps",
        "shift_mm",
        "shift_speed_mmps",
        "secondary_shaft_angle_rad",
        "vehicle_distance_m",
        "vehicle_speed_mps",
        "grade_deg",
        "ratio_secondary_over_primary",
        "engine_torque_nm",
        "engine_power_kw",
        "road_external_force_n",
        "road_external_torque_nm",
        "brake_force_n",
        "brake_power_kw",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for trace in traces:
            for i, time in enumerate(trace.time_s):
                writer.writerow(
                    (
                        trace.scenario_key,
                        trace.variant_key,
                        trace.variant_label,
                        trace.varied_piece,
                        trace.scale,
                        time,
                        trace.state[0, i] * RPM_PER_RADIAN_PER_SECOND,
                        trace.state[1, i] * RPM_PER_RADIAN_PER_SECOND,
                        trace.state[2, i],
                        trace.state[3, i] / MILLIMETRE,
                        trace.state[4, i] / MILLIMETRE,
                        trace.state[5, i],
                        trace.vehicle_distance_m[i],
                        trace.vehicle_speed_mps[i],
                        np.rad2deg(trace.grade_rad[i]),
                        trace.effective_ratio[i],
                        trace.engine_torque_nm[i],
                        trace.engine_power_w[i] / 1000.0,
                        trace.road_external_force_n[i],
                        trace.road_external_torque_nm[i],
                        trace.brake_force_n[i],
                        trace.brake_power_w[i] / 1000.0,
                    )
                )


def plot_effective_inertia(path: Path, rows: Sequence[dict[str, object]]) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5), constrained_layout=True, sharex=True)
    groups = (
        ("primary_side_spin_inertia", "Primary-side spin variants"),
        ("secondary_side_spin_inertia_excluding_vehicle_translation", "Secondary-side spin variants"),
        ("vehicle_mass", "Vehicle-mass variants"),
    )
    for axis, (piece, title) in zip(axes, groups, strict=True):
        subset = [row for row in rows if row["varied_piece"] in (piece, "none")]
        labels = tuple(dict.fromkeys(str(row["variant_label"]) for row in subset))
        for label in labels:
            data = [row for row in subset if row["variant_label"] == label]
            data = sorted(data, key=lambda row: float(row["ratio_secondary_over_primary"]))
            axis.plot(
                [row["ratio_secondary_over_primary"] for row in data],
                [row["total_effective_primary_side_kg_m2"] for row in data],
                label=label,
            )
        axis.set_title(title)
        axis.set_xlabel(r"CVT ratio $R=r_s/r_p=\omega_p/\omega_s$")
        axis.set_ylabel(r"Primary-side effective inertia [kg m$^2$]")
        axis.grid(True, alpha=0.25)
        axis.legend(loc="best", fontsize=8)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _ordered_variants(traces: Sequence[SampledRun]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(trace.variant_label for trace in traces))


def plot_scenario_distances(path: Path, summaries: Sequence[dict[str, object]]) -> None:
    """Plot distances even when one scenario/variant run failed.

    Earlier versions assumed every scenario had every variant.  That is brittle
    for long hybrid contact sweeps because one integration can legitimately fail
    or time out while the rest of the study remains useful.  Missing combinations
    are plotted as empty bars and recorded in inertia_study_failures.csv.
    """

    scenarios = tuple(dict.fromkeys(str(row["scenario_label"]) for row in summaries))
    variants = tuple(dict.fromkeys(str(row["variant_label"]) for row in summaries))
    x = np.arange(len(variants))
    width = 0.80 / max(1, len(scenarios))
    fig, axis = plt.subplots(figsize=(18, 7), constrained_layout=True)
    for j, scenario in enumerate(scenarios):
        values: list[float] = []
        missing_positions: list[float] = []
        for i, variant in enumerate(variants):
            match = next(
                (row for row in summaries
                 if row["scenario_label"] == scenario and row["variant_label"] == variant),
                None,
            )
            if match is None:
                values.append(np.nan)
                missing_positions.append(float(i))
            else:
                values.append(float(match["final_distance_m"]))
        offsets = x + (j - (len(scenarios) - 1) / 2) * width
        axis.bar(offsets, values, width, label=scenario)
        for i in missing_positions:
            axis.text(
                i + (j - (len(scenarios) - 1) / 2) * width,
                0.0,
                "failed",
                rotation=90,
                va="bottom",
                ha="center",
                fontsize=7,
            )
    axis.set_xticks(x)
    axis.set_xticklabels(variants, rotation=30, ha="right")
    axis.set_ylabel("Distance after set time [m]")
    axis.set_title("Same-time distance by inertia variant and scenario")
    axis.grid(True, axis="y", alpha=0.25)
    axis.legend(loc="best")
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_scenario_traces(output_dir: Path, traces: Sequence[SampledRun]) -> None:
    scenario_keys = tuple(dict.fromkeys(trace.scenario_key for trace in traces))
    for scenario_key in scenario_keys:
        subset = [trace for trace in traces if trace.scenario_key == scenario_key]
        fig, axes = plt.subplots(2, 2, figsize=(16, 10), constrained_layout=True)
        for trace in subset:
            t = trace.time_s
            label = trace.variant_label
            axes[0, 0].plot(t, trace.vehicle_distance_m, label=label)
            axes[0, 1].plot(t, trace.vehicle_speed_mps, label=label)
            axes[1, 0].plot(t, trace.effective_ratio, label=label)
            axes[1, 1].plot(t, trace.state[3] / MILLIMETRE, label=label)
        axes[0, 0].set_title(f"{subset[0].scenario_label}: distance")
        axes[0, 0].set_ylabel("Distance [m]")
        axes[0, 1].set_title("Vehicle speed")
        axes[0, 1].set_ylabel("Speed [m/s]")
        axes[1, 0].set_title("CVT ratio")
        axes[1, 0].set_ylabel(r"$r_s/r_p$")
        axes[1, 1].set_title("Shift coordinate")
        axes[1, 1].set_ylabel("Shift [mm]")
        for axis in axes.flat:
            axis.set_xlabel("Time [s]")
            axis.grid(True, alpha=0.25)
        axes[0, 0].legend(loc="best", fontsize=7)
        fig.savefig(output_dir / f"{scenario_key}_traces.png", dpi=180)
        plt.close(fig)


def plot_energy_bars(path: Path, summaries: Sequence[dict[str, object]]) -> None:
    scenarios = tuple(dict.fromkeys(str(row["scenario_label"]) for row in summaries))
    fig, axes = plt.subplots(len(scenarios), 1, figsize=(18, 4.0 * len(scenarios)), constrained_layout=True)
    if len(scenarios) == 1:
        axes = np.asarray([axes])
    for axis, scenario in zip(axes, scenarios, strict=True):
        rows = [row for row in summaries if row["scenario_label"] == scenario]
        labels = [str(row["variant_label"]) for row in rows]
        x = np.arange(len(labels))
        width = 0.28
        axis.bar(
            x - width,
            [float(row["positive_engine_work_kj"]) for row in rows],
            width,
            label="positive crank work",
        )
        axis.bar(
            x,
            [float(row["apparent_useful_energy_kj"]) for row in rows],
            width,
            label="useful vehicle energy",
        )
        axis.bar(
            x + width,
            [float(row["brake_dissipated_kj"]) for row in rows],
            width,
            label="brake dissipated",
        )
        axis.set_title(scenario)
        axis.set_ylabel("Energy [kJ]")
        axis.set_xticks(x)
        axis.set_xticklabels(labels, rotation=30, ha="right")
        axis.grid(True, axis="y", alpha=0.25)
        axis.legend(loc="best", fontsize=8)
    fig.savefig(path, dpi=180)
    plt.close(fig)


@contextmanager
def _best_effort_time_limit(seconds: float):
    """Raise TimeoutError after ``seconds`` on Unix; no-op when disabled.

    This keeps long contact-chatter cases from blocking the whole sweep.  On
    platforms without SIGALRM, the context degrades to a normal block.
    """

    if seconds <= 0.0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(signum, frame):  # pragma: no cover - signal delivery is OS-owned.
        del signum, frame
        raise TimeoutError(f"run exceeded {seconds:g} s")

    previous_handler = signal.signal(signal.SIGALRM, _handler)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0.0:
            signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])


def main() -> None:
    args = parse_arguments()
    candidate, integration_defaults = load_reference(args.preset)
    target_engagement = args.target_engagement_rpm
    resolved = resolve_primary_preload(
        candidate,
        target_engagement_rpm=target_engagement,
    )
    base_constants = resolved.constants
    variants = build_variants(
        base_constants=base_constants,
        primary_scales=tuple(args.primary_scales),
        secondary_scales=tuple(args.secondary_scales),
        vehicle_mass_scales=tuple(args.vehicle_mass_scales),
    )
    scenarios = scenario_specs(args.duration_s)
    if args.scenario:
        selected = set(args.scenario)
        scenarios = tuple(scenario for scenario in scenarios if scenario.key in selected)

    solver_method = str(args.solver_method or integration_defaults.get("solver_method", "LSODA"))
    max_step_s = float(
        (args.max_step_ms if args.max_step_ms is not None else integration_defaults.get("max_step_ms", 20.0))
        * 1.0e-3
    )
    rtol = float(
        args.relative_tolerance
        if args.relative_tolerance is not None
        else integration_defaults.get("relative_tolerance", 1.0e-4)
    )
    atol = float(
        args.absolute_tolerance
        if args.absolute_tolerance is not None
        else integration_defaults.get("absolute_tolerance", 1.0e-7)
    )
    report_step_s = args.report_step_ms * 1.0e-3

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ratio_grid = np.linspace(0.55, 4.0, 350)
    inertia_rows = effective_inertia_curves(variants=variants, ratio_grid=ratio_grid)
    write_dict_csv(args.output_dir / "effective_inertia_curves.csv", inertia_rows)
    plot_effective_inertia(args.output_dir / "effective_inertia_vs_ratio.png", inertia_rows)

    traces: list[SampledRun] = []
    summaries: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    print("Selected tune")
    print("=" * 88)
    print(candidate.label())
    print(
        f"primary preload={resolved.resolved_primary_preload_mm:.3f} mm for "
        f"{target_engagement:.0f} rpm lower-stop release."
    )
    print(
        f"Running {len(variants)} inertia variants across {len(scenarios)} scenarios "
        f"for {args.duration_s:.2f} s each."
    )

    for scenario in scenarios:
        print(f"\nScenario: {scenario.label}")
        for variant in variants:
            print(f"  {variant.label} ...", flush=True)
            try:
                with _best_effort_time_limit(args.per_run_timeout_s):
                    _, result, trace = run_variant_scenario(
                        variant=variant,
                        scenario=scenario,
                        initial_primary_rpm=args.initial_primary_rpm,
                        solver_method=solver_method,
                        max_step_s=max_step_s,
                        relative_tolerance=rtol,
                        absolute_tolerance=atol,
                        maximum_transitions=args.maximum_transitions,
                        report_step_s=report_step_s,
                    )
                traces.append(trace)
                summary = summarize_run(trace, variant.constants)
                summary["completed"] = int(bool(result.completed))
                summary["termination_reason"] = result.termination_reason
                summaries.append(summary)
                print(
                    f"    distance={summary['final_distance_m']:.2f} m, "
                    f"useful={summary['apparent_useful_energy_kj']:.2f} kJ, "
                    f"engine={summary['positive_engine_work_kj']:.2f} kJ"
                )
            except Exception as error:
                failures.append(
                    {
                        "scenario": scenario.key,
                        "variant": variant.key,
                        "variant_label": variant.label,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
                print(f"    FAILED: {type(error).__name__}: {error}")

    write_dict_csv(args.output_dir / "inertia_study_summary.csv", summaries)
    if traces:
        write_trace_csv(args.output_dir / "inertia_study_traces.csv", traces)
        plot_scenario_distances(args.output_dir / "final_distance_by_scenario.png", summaries)
        plot_scenario_traces(args.output_dir, traces)
        plot_energy_bars(args.output_dir / "energy_accounting_by_scenario.png", summaries)
    if failures:
        write_dict_csv(args.output_dir / "inertia_study_failures.csv", failures)

    with (args.output_dir / "inertia_study_manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "preset": str(args.preset),
                "candidate": candidate.label(),
                "target_engagement_rpm": target_engagement,
                "resolved_primary_preload_mm": resolved.resolved_primary_preload_mm,
                "integration": {
                    "duration_s": args.duration_s,
                    "solver_method": solver_method,
                    "max_step_s": max_step_s,
                    "relative_tolerance": rtol,
                    "absolute_tolerance": atol,
                    "report_step_s": report_step_s,
                    "maximum_transitions": args.maximum_transitions,
                },
                "variants": [
                    {
                        "key": variant.key,
                        "label": variant.label,
                        "varied_piece": variant.varied_piece,
                        "scale": variant.scale,
                    }
                    for variant in variants
                ],
                "scenarios": [
                    {"key": scenario.key, "label": scenario.label, "duration_s": scenario.duration_s}
                    for scenario in scenarios
                ],
                "failures": failures,
            },
            handle,
            indent=2,
        )

    print("\nWrote:")
    for file_name in (
        "effective_inertia_vs_ratio.png",
        "effective_inertia_curves.csv",
        "inertia_study_summary.csv",
        "inertia_study_traces.csv",
        "final_distance_by_scenario.png",
        "energy_accounting_by_scenario.png",
        "inertia_study_manifest.json",
        "inertia_study_failures.csv",
    ):
        path = args.output_dir / file_name
        if path.exists():
            print(f"  {path}")
    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
