"""Compare a rigid final drive against an ideal one-way wheel bearing.

This launchTools-only experiment leaves CINDER's CVT/contact closure unchanged.
It compares two otherwise identical output couplers:

* ``LOCKED``: the current rigid final-drive vehicle model; and
* ``ONE_WAY``: the same model, except a forward-driving ideal one-way bearing
  releases whenever the locked constraint would require wheel-to-CVT torque.

While the one-way bearing overruns, CINDER is attached to a zero-load secondary
boundary and the vehicle's position/speed advance independently under grade,
rolling resistance, and aerodynamic drag.  It captures again only when the
secondary-side driveline catches the wheel speed *and* can transmit positive
forward torque.

The named scenario set includes a flat launch plus sinusoidal rolling-road
profiles with ±10 deg and ±20 deg grade amplitudes, at long/medium/short
wavelengths. The default runs one representative 20 deg rolling-hill case.
The generated metrics are diagnostic comparisons rather than a closed global
energy balance: the present CVT model does not yet expose every dissipative
internal power channel.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field, replace
from enum import Enum
from math import pi, radians, sin
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

from cinder.downstream import FixedSecondaryLoad
from cinder.integration import (
    CVTDynamicState,
    HybridEvent,
    HybridIntegrationResult,
    HybridIntegratorSettings,
    HybridTransition,
    integrate_hybrid,
)
from cinder.integration.cvt_operating_hybrid import CVTOperatingHybridSystem
from cinder.integration.cvt_regime import CVTOperatingRegime
from cinder.vehicle import CallableRoadProfile, RoadProfile

from launch_tuning_common import (
    RPM_PER_RADIAN_PER_SECOND,
    build_operating_system,
    launch_initial_state,
    resolve_primary_preload,
)
from run_downhill_engine_braking import load_candidate

METRES_PER_100_FEET = 30.48


class BearingMode(str, Enum):
    """Output coupling state for the ideal wheel-side one-way bearing."""

    LOCKED = "locked"
    OVERRUN = "overrun"


@dataclass(frozen=True, slots=True)
class OutputMode:
    """Cross-product of CINDER's operating mode and output-coupler state."""

    cvt: CVTOperatingRegime
    bearing: BearingMode


@dataclass(frozen=True, slots=True)
class RollingRoadScenario:
    """Spatial road profile used for the flat and rolling-hill comparisons."""

    name: str
    description: str
    amplitude_degrees: float = 0.0
    wavelength_m: float | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Scenario name must be non-empty.")
        if not np.isfinite(self.amplitude_degrees) or self.amplitude_degrees < 0.0:
            raise ValueError("amplitude_degrees must be finite and non-negative.")
        if self.amplitude_degrees == 0.0:
            if self.wavelength_m is not None:
                raise ValueError("A flat scenario must not define a wavelength.")
        elif (
            self.wavelength_m is None
            or not np.isfinite(self.wavelength_m)
            or self.wavelength_m <= 0.0
        ):
            raise ValueError("A rolling scenario requires a finite positive wavelength.")

    def grade_radians(self, vehicle_distance_m: float) -> float:
        """Return a smooth grade angle that begins level and rises uphill."""

        if self.amplitude_degrees == 0.0:
            return 0.0
        assert self.wavelength_m is not None
        return radians(
            self.amplitude_degrees
            * sin(2.0 * pi * vehicle_distance_m / self.wavelength_m)
        )

    def road_profile(self) -> RoadProfile:
        return CallableRoadProfile(
            grade_angle_function=lambda distance: self.grade_radians(distance)
        )


@dataclass(frozen=True, slots=True)
class ComparisonTrace:
    """Sparse, diagnostic trajectory trace for one output-coupler variant."""

    time_s: NDArray[np.float64]
    state: NDArray[np.float64]
    mode: tuple[str, ...]
    bearing_mode: tuple[str, ...]
    grade_degrees: NDArray[np.float64]
    vehicle_acceleration_mps2: NDArray[np.float64]
    road_grade_force_n: NDArray[np.float64]
    road_rolling_force_n: NDArray[np.float64]
    road_aero_force_n: NDArray[np.float64]
    road_external_force_n: NDArray[np.float64]
    output_drive_torque_nm: NDArray[np.float64]
    engine_torque_nm: NDArray[np.float64]
    engine_power_w: NDArray[np.float64]
    output_drive_power_w: NDArray[np.float64]

    @property
    def vehicle_position_m(self) -> NDArray[np.float64]:
        return self.state[6]

    @property
    def vehicle_speed_mps(self) -> NDArray[np.float64]:
        return self.state[7]

    @property
    def primary_rpm(self) -> NDArray[np.float64]:
        return self.state[0] * RPM_PER_RADIAN_PER_SECOND

    @property
    def secondary_rpm(self) -> NDArray[np.float64]:
        return self.state[1] * RPM_PER_RADIAN_PER_SECOND

    @property
    def overrun_mask(self) -> NDArray[np.bool_]:
        return np.asarray(
            [mode == BearingMode.OVERRUN.value for mode in self.bearing_mode],
            dtype=bool,
        )


@dataclass(frozen=True, slots=True)
class ScenarioMetrics:
    """Comparable vehicle, output-coupling, and diagnostic energy metrics."""

    scenario: str
    variant: str
    final_distance_m: float
    final_speed_kph: float
    time_to_100ft_s: float | None
    time_to_target_s: float | None
    engine_positive_work_kj: float
    engine_braking_absorption_kj: float
    output_positive_work_kj: float
    wheel_to_cvt_backdrive_kj: float
    downhill_gravity_input_kj: float
    uphill_gravity_demand_kj: float
    road_loss_kj: float
    vehicle_kinetic_energy_change_kj: float
    overrun_time_s: float
    release_count: int
    capture_count: int
    completed: bool
    termination_reason: str


@dataclass(frozen=True, slots=True)
class ComparisonDelta:
    """One-way minus locked difference for a shared road scenario."""

    scenario: str
    distance_gain_m: float
    final_speed_gain_kph: float
    time_to_100ft_change_s: float | None
    time_to_target_change_s: float | None
    engine_braking_avoided_kj: float
    wheel_backdrive_avoided_kj: float
    output_positive_work_change_kj: float
    overrun_time_s: float
    release_count: int
    capture_count: int


@dataclass(slots=True)
class IdealOneWayBearingSystem:
    """Output hybrid built around a locked and an unloaded CINDER child.

    The child systems are ordinary ``CVTOperatingHybridSystem`` objects.  The
    wrapper only adds explicit vehicle position/speed states and switches the
    downstream boundary condition.  No belt contact equation, lambda solve,
    or CINDER operating-regime transition is altered here.
    """

    locked: CVTOperatingHybridSystem
    overrunning: CVTOperatingHybridSystem
    road_profile: RoadProfile
    allow_overrun: bool
    release_torque_tolerance_nm: float = 0.5
    capture_torque_tolerance_nm: float = 0.5
    capture_speed_tolerance_mps: float = 0.01
    release_min_vehicle_speed_mps: float = 1.0
    _speed_factor: float = field(init=False, repr=False)
    _effective_vehicle_mass: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        attachment = self.locked.model.locked_vehicle_attachment
        final_drive = attachment.final_drive
        vehicle = attachment.vehicle
        self._speed_factor = final_drive.wheel_radius / final_drive.reduction_ratio
        self._effective_vehicle_mass = (
            vehicle.mass + vehicle.wheel_rotational_inertia / final_drive.wheel_radius**2
        )
        if self._speed_factor <= 0.0 or self._effective_vehicle_mass <= 0.0:
            raise ValueError("Output kinematics must have positive scale and inertia.")
        for name, value in (
            ("release_torque_tolerance_nm", self.release_torque_tolerance_nm),
            ("capture_torque_tolerance_nm", self.capture_torque_tolerance_nm),
            ("capture_speed_tolerance_mps", self.capture_speed_tolerance_mps),
            ("release_min_vehicle_speed_mps", self.release_min_vehicle_speed_mps),
        ):
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")

    @property
    def speed_factor(self) -> float:
        """Return k = r_w/G, so v = k omega_s when the bearing is locked."""

        return self._speed_factor

    @property
    def effective_vehicle_mass(self) -> float:
        """Return m + J_w/r_w² for the explicit wheel/vehicle subsystem."""

        return self._effective_vehicle_mass

    def initial_mode(self, cvt_state: CVTDynamicState) -> OutputMode:
        return OutputMode(
            cvt=self.locked.classify_initial_regime(cvt_state),
            bearing=BearingMode.LOCKED,
        )

    def initial_state(self, cvt_state: CVTDynamicState) -> NDArray[np.float64]:
        """Return [six CINDER states, explicit vehicle position, vehicle speed]."""

        vector = np.empty(8, dtype=float)
        vector[:6] = cvt_state.as_vector()
        vector[6] = self.speed_factor * cvt_state.secondary_shaft_angle
        vector[7] = self.speed_factor * cvt_state.secondary_angular_speed
        return vector

    def rhs(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: OutputMode,
    ) -> NDArray[np.float64]:
        child = self._child(mode)
        cvt_derivative = child.rhs(time, np.asarray(state[:6], dtype=float), mode.cvt)
        derivative = np.empty(8, dtype=float)
        derivative[:6] = cvt_derivative
        if mode.bearing is BearingMode.LOCKED:
            derivative[6] = self.speed_factor * state[1]
            derivative[7] = self.speed_factor * cvt_derivative[1]
        else:
            road = self.road_load_at(
                vehicle_position_m=float(state[6]), vehicle_speed_mps=float(state[7])
            )
            derivative[6] = state[7]
            derivative[7] = road.external_force / self.effective_vehicle_mass
        return derivative

    def events(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: OutputMode,
    ) -> tuple[HybridEvent, ...]:
        child = self._child(mode)
        cvt_events = tuple(
            HybridEvent(
                name=f"cvt::{event.name}",
                function=lambda event_time, vector, event=event: event.function(
                    event_time, np.asarray(vector[:6], dtype=float)
                ),
                direction=event.direction,
                terminal=event.terminal,
            )
            for event in child.events(time, np.asarray(state[:6], dtype=float), mode.cvt)
        )
        if not self.allow_overrun:
            return cvt_events
        if mode.bearing is BearingMode.LOCKED:
            return cvt_events + (
                HybridEvent(
                    name="one_way_release",
                    function=lambda event_time, vector: self._release_margin(
                        time=event_time, state=vector, cvt_mode=mode.cvt
                    ),
                    direction=-1.0,
                ),
            )
        return cvt_events + (
            HybridEvent(
                name="one_way_capture",
                function=lambda event_time, vector: self._capture_margin(
                    time=event_time, state=vector, cvt_mode=mode.cvt
                ),
                direction=1.0,
            ),
        )

    def transition(
        self,
        time: float,
        state: NDArray[np.float64],
        mode: OutputMode,
        fired_event_names: tuple[str, ...],
    ) -> HybridTransition[OutputMode]:
        successor = np.asarray(state, dtype=float).copy()
        bearing = mode.bearing
        cvt_mode = mode.cvt
        reasons: list[str] = []

        cvt_event_names = tuple(
            name.removeprefix("cvt::")
            for name in fired_event_names
            if name.startswith("cvt::")
        )
        if cvt_event_names:
            child_transition = self._child(mode).transition(
                time,
                np.asarray(successor[:6], dtype=float),
                cvt_mode,
                cvt_event_names,
            )
            if child_transition.terminates:
                return HybridTransition(
                    next_mode=None,
                    reason=f"cvt::{child_transition.reason}",
                    metadata=child_transition.metadata,
                    successor_state=successor,
                )
            assert child_transition.next_mode is not None
            cvt_mode = child_transition.next_mode
            if child_transition.successor_state is not None:
                successor[:6] = child_transition.successor_state
            reasons.append(f"cvt::{child_transition.reason}")

        post_cvt_release = (
            self.allow_overrun
            and bearing is BearingMode.LOCKED
            and max(abs(successor[7]), abs(self.speed_factor * successor[1]))
            >= self.release_min_vehicle_speed_mps
            and self.output_drive_torque(
                time=time, state=successor, cvt_mode=cvt_mode
            )
            <= -self.release_torque_tolerance_nm
        )
        if self.allow_overrun and (
            "one_way_release" in fired_event_names or post_cvt_release
        ):
            # Release is velocity-continuous: preserve the just-valid locked
            # kinematics, then remove the constraint in the successor segment.
            successor[6] = self.speed_factor * successor[5]
            successor[7] = self.speed_factor * successor[1]
            bearing = BearingMode.OVERRUN
            reasons.append("one_way_release")

        if self.allow_overrun and "one_way_capture" in fired_event_names:
            # Capture happens at k*omega_s = v.  Re-align only the auxiliary
            # secondary-angle bookkeeping required by the locked attachment.
            successor[5] = successor[6] / self.speed_factor
            successor[7] = self.speed_factor * successor[1]
            bearing = BearingMode.LOCKED
            reasons.append("one_way_capture")

        if bearing is BearingMode.LOCKED:
            # A child-CVT impact may change a constrained state.  Keep the
            # explicit reporting states exactly aligned after every such reset.
            successor[6] = self.speed_factor * successor[5]
            successor[7] = self.speed_factor * successor[1]

        if not reasons:
            raise RuntimeError("Output-coupler transition received no known event.")
        return HybridTransition(
            next_mode=OutputMode(cvt=cvt_mode, bearing=bearing),
            reason=" + ".join(reasons),
            successor_state=successor,
        )

    def output_drive_torque(
        self,
        *,
        time: float,
        state: NDArray[np.float64],
        cvt_mode: CVTOperatingRegime,
    ) -> float:
        """Return required secondary-to-wheel torque if the output is locked.

        Under rigid final-drive kinematics, the torque delivered from the
        secondary toward the wheels is

            tau_out = k [M_eq k alpha_s - F_road].

        Negative ``tau_out`` means the locked constraint would require the
        wheels to drive the CVT, which is exactly the release condition of an
        ideal forward-driving one-way bearing.
        """

        candidate = np.asarray(state[:6], dtype=float).copy()
        candidate[5] = state[6] / self.speed_factor
        evaluation = self.locked.evaluate(time=time, state=candidate, mode=cvt_mode)
        alpha_secondary = evaluation.state_derivative.secondary_angular_acceleration
        road = self.road_load_at(
            vehicle_position_m=float(state[6]), vehicle_speed_mps=float(state[7])
        )
        drive_force = (
            self.effective_vehicle_mass * self.speed_factor * alpha_secondary
            - road.external_force
        )
        return self.speed_factor * drive_force

    def road_load_at(self, *, vehicle_position_m: float, vehicle_speed_mps: float):
        """Evaluate grade/rolling/aero forces from explicit vehicle states."""

        attachment = self.locked.model.locked_vehicle_attachment
        grade = self.road_profile.sample(vehicle_distance=vehicle_position_m).grade_angle
        return attachment.road_load.evaluate(
            secondary_angular_speed=vehicle_speed_mps / self.speed_factor,
            grade_angle=grade,
        )

    def _release_margin(
        self,
        *,
        time: float,
        state: NDArray[np.float64],
        cvt_mode: CVTOperatingRegime,
    ) -> float:
        if max(abs(state[7]), abs(self.speed_factor * state[1])) < self.release_min_vehicle_speed_mps:
            return self.release_torque_tolerance_nm
        return (
            self.output_drive_torque(time=time, state=state, cvt_mode=cvt_mode)
            + self.release_torque_tolerance_nm
        )

    def _capture_margin(
        self,
        *,
        time: float,
        state: NDArray[np.float64],
        cvt_mode: CVTOperatingRegime,
    ) -> float:
        relative_speed = self.speed_factor * state[1] - state[7]
        available_drive_torque = (
            self.output_drive_torque(time=time, state=state, cvt_mode=cvt_mode)
            - self.capture_torque_tolerance_nm
        )
        # A dimensionless min-intersection event: capture only when both the
        # driveline has caught the wheels and positive drive torque is available.
        return min(
            relative_speed / max(self.capture_speed_tolerance_mps, 1.0e-12),
            available_drive_torque / max(self.capture_torque_tolerance_nm, 1.0e-12),
        )

    def _child(self, mode: OutputMode) -> CVTOperatingHybridSystem:
        return self.locked if mode.bearing is BearingMode.LOCKED else self.overrunning


def build_locked_child(*, resolved, road_profile: RoadProfile) -> CVTOperatingHybridSystem:
    """Build the standard CINDER vehicle model on one spatial road profile."""

    template, _ = build_operating_system(resolved.constants)
    model = template.model.with_road_profile(road_profile)
    return CVTOperatingHybridSystem(
        model=model,
        traction_law=template.traction_law,
        solve_settings=template.solve_settings,
        operating_limits=template.operating_limits,
        switching_settings=template.switching_settings,
    )


def build_overrunning_child(*, locked: CVTOperatingHybridSystem) -> CVTOperatingHybridSystem:
    """Clone CINDER with the wheel/vehicle boundary physically removed."""

    model = replace(
        locked.model,
        secondary_attachment=FixedSecondaryLoad(),
    )
    return CVTOperatingHybridSystem(
        model=model,
        traction_law=locked.traction_law,
        solve_settings=locked.solve_settings,
        operating_limits=locked.operating_limits,
        switching_settings=locked.switching_settings,
    )


def _compact_mode(mode: OutputMode) -> str:
    contact = "" if mode.cvt.contact_regime is None else f"/{mode.cvt.contact_regime.mode.value}"
    return f"{mode.bearing.value}/{mode.cvt.engagement.value}/{mode.cvt.shift_constraint.value}{contact}"


def _allocate_samples(sizes: Sequence[int], maximum: int) -> list[int]:
    total = sum(sizes)
    if total <= maximum:
        return list(sizes)
    allocation = [max(2, round(maximum * size / total)) for size in sizes]
    while sum(allocation) > maximum:
        index = max(range(len(allocation)), key=lambda item: allocation[item])
        if allocation[index] <= 2:
            break
        allocation[index] -= 1
    return allocation


def sample_trace(
    *,
    result: HybridIntegrationResult[OutputMode],
    system: IdealOneWayBearingSystem,
    maximum_samples: int,
) -> ComparisonTrace:
    """Re-evaluate accepted states for speed, force, power, and energy diagnostics."""

    budgets = _allocate_samples(
        [segment.state.shape[1] for segment in result.segments], maximum_samples
    )
    rows: list[tuple] = []
    for segment, budget in zip(result.segments, budgets, strict=True):
        indices = np.unique(
            np.linspace(0, segment.state.shape[1] - 1, budget, dtype=int)
        )
        for index in indices:
            if rows and index == 0:
                continue
            time = float(segment.time[index])
            vector = np.asarray(segment.state[:, index], dtype=float).copy()
            vector[3] = np.clip(
                vector[3], 0.0, system.locked.operating_limits.upper_stop_shift
            )
            road = system.road_load_at(
                vehicle_position_m=float(vector[6]), vehicle_speed_mps=float(vector[7])
            )
            child = system._child(segment.mode)
            evaluation = child.evaluate(time=time, state=vector[:6], mode=segment.mode.cvt)
            derivative = evaluation.state_derivative.as_vector()
            if segment.mode.bearing is BearingMode.LOCKED:
                output_torque = system.output_drive_torque(
                    time=time, state=vector, cvt_mode=segment.mode.cvt
                )
                vehicle_acceleration = system.speed_factor * derivative[1]
            else:
                output_torque = 0.0
                vehicle_acceleration = road.external_force / system.effective_vehicle_mass
            engine_torque = float(evaluation.snapshot.engine_torque)
            engine_power = engine_torque * vector[0]
            output_power = output_torque * vector[1]
            grade = system.road_profile.sample(vehicle_distance=float(vector[6])).grade_angle
            rows.append(
                (
                    time,
                    vector,
                    _compact_mode(segment.mode),
                    segment.mode.bearing.value,
                    float(np.rad2deg(grade)),
                    float(vehicle_acceleration),
                    float(road.grade_force),
                    float(road.rolling_force),
                    float(road.aerodynamic_force),
                    float(road.external_force),
                    float(output_torque),
                    engine_torque,
                    float(engine_power),
                    float(output_power),
                )
            )

    rows.sort(key=lambda row: row[0])
    return ComparisonTrace(
        time_s=np.asarray([row[0] for row in rows], dtype=float),
        state=np.column_stack([row[1] for row in rows]),
        mode=tuple(row[2] for row in rows),
        bearing_mode=tuple(row[3] for row in rows),
        grade_degrees=np.asarray([row[4] for row in rows], dtype=float),
        vehicle_acceleration_mps2=np.asarray([row[5] for row in rows], dtype=float),
        road_grade_force_n=np.asarray([row[6] for row in rows], dtype=float),
        road_rolling_force_n=np.asarray([row[7] for row in rows], dtype=float),
        road_aero_force_n=np.asarray([row[8] for row in rows], dtype=float),
        road_external_force_n=np.asarray([row[9] for row in rows], dtype=float),
        output_drive_torque_nm=np.asarray([row[10] for row in rows], dtype=float),
        engine_torque_nm=np.asarray([row[11] for row in rows], dtype=float),
        engine_power_w=np.asarray([row[12] for row in rows], dtype=float),
        output_drive_power_w=np.asarray([row[13] for row in rows], dtype=float),
    )


def _integral(time_s: NDArray[np.float64], quantity: NDArray[np.float64]) -> float:
    return float(np.trapezoid(quantity, time_s))


def _time_to_distance(
    time_s: NDArray[np.float64],
    distance_m: NDArray[np.float64],
    target_m: float,
) -> float | None:
    indices = np.flatnonzero(distance_m >= target_m)
    if indices.size == 0:
        return None
    index = int(indices[0])
    if index == 0:
        return float(time_s[0])
    x0, x1 = distance_m[index - 1], distance_m[index]
    t0, t1 = time_s[index - 1], time_s[index]
    if x1 <= x0:
        return float(t1)
    fraction = (target_m - x0) / (x1 - x0)
    return float(t0 + fraction * (t1 - t0))


def _count_events(result: HybridIntegrationResult[OutputMode], token: str) -> int:
    return sum(token in record.transition.reason for record in result.transitions)


def calculate_metrics(
    *,
    scenario: RollingRoadScenario,
    variant: str,
    trace: ComparisonTrace,
    result: HybridIntegrationResult[OutputMode],
    effective_vehicle_mass: float,
    performance_distance_m: float,
) -> ScenarioMetrics:
    time = trace.time_s
    engine_positive_work = _integral(time, np.maximum(trace.engine_power_w, 0.0))
    engine_braking_work = _integral(time, np.maximum(-trace.engine_power_w, 0.0))
    output_positive_work = _integral(time, np.maximum(trace.output_drive_power_w, 0.0))
    wheel_backdrive_work = _integral(time, np.maximum(-trace.output_drive_power_w, 0.0))
    grade_power = trace.road_grade_force_n * trace.vehicle_speed_mps
    road_loss_power = (
        trace.road_rolling_force_n + trace.road_aero_force_n
    ) * trace.vehicle_speed_mps
    overrun_time = _integral(time, trace.overrun_mask.astype(float))
    vehicle_ke_change = 0.5 * effective_vehicle_mass * (
        trace.vehicle_speed_mps[-1] ** 2 - trace.vehicle_speed_mps[0] ** 2
    )
    return ScenarioMetrics(
        scenario=scenario.name,
        variant=variant,
        final_distance_m=float(trace.vehicle_position_m[-1]),
        final_speed_kph=float(trace.vehicle_speed_mps[-1] * 3.6),
        time_to_100ft_s=_time_to_distance(time, trace.vehicle_position_m, METRES_PER_100_FEET),
        time_to_target_s=_time_to_distance(
            time, trace.vehicle_position_m, performance_distance_m
        ),
        engine_positive_work_kj=engine_positive_work / 1000.0,
        engine_braking_absorption_kj=engine_braking_work / 1000.0,
        output_positive_work_kj=output_positive_work / 1000.0,
        wheel_to_cvt_backdrive_kj=wheel_backdrive_work / 1000.0,
        downhill_gravity_input_kj=_integral(time, np.maximum(grade_power, 0.0)) / 1000.0,
        uphill_gravity_demand_kj=_integral(time, np.maximum(-grade_power, 0.0)) / 1000.0,
        road_loss_kj=_integral(time, np.maximum(-road_loss_power, 0.0)) / 1000.0,
        vehicle_kinetic_energy_change_kj=vehicle_ke_change / 1000.0,
        overrun_time_s=overrun_time,
        release_count=_count_events(result, "one_way_release"),
        capture_count=_count_events(result, "one_way_capture"),
        completed=result.completed,
        termination_reason=result.termination_reason,
    )


def calculate_delta(*, locked: ScenarioMetrics, one_way: ScenarioMetrics) -> ComparisonDelta:
    def delta_time(one: float | None, baseline: float | None) -> float | None:
        if one is None or baseline is None:
            return None
        return one - baseline

    return ComparisonDelta(
        scenario=locked.scenario,
        distance_gain_m=one_way.final_distance_m - locked.final_distance_m,
        final_speed_gain_kph=one_way.final_speed_kph - locked.final_speed_kph,
        time_to_100ft_change_s=delta_time(one_way.time_to_100ft_s, locked.time_to_100ft_s),
        time_to_target_change_s=delta_time(one_way.time_to_target_s, locked.time_to_target_s),
        engine_braking_avoided_kj=(
            locked.engine_braking_absorption_kj - one_way.engine_braking_absorption_kj
        ),
        wheel_backdrive_avoided_kj=(
            locked.wheel_to_cvt_backdrive_kj - one_way.wheel_to_cvt_backdrive_kj
        ),
        output_positive_work_change_kj=(
            one_way.output_positive_work_kj - locked.output_positive_work_kj
        ),
        overrun_time_s=one_way.overrun_time_s,
        release_count=one_way.release_count,
        capture_count=one_way.capture_count,
    )


def write_trace(path: Path, trace: ComparisonTrace) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "time_s",
                "mode",
                "bearing_mode",
                "primary_angular_speed_rad_s",
                "secondary_angular_speed_rad_s",
                "belt_speed_m_s",
                "shift_position_m",
                "shift_speed_m_s",
                "secondary_shaft_angle_rad",
                "vehicle_position_m",
                "vehicle_speed_m_s",
                "grade_degrees",
                "vehicle_acceleration_mps2",
                "grade_force_n",
                "rolling_force_n",
                "aero_force_n",
                "road_external_force_n",
                "secondary_to_wheel_drive_torque_nm",
                "engine_torque_nm",
                "engine_power_w",
                "secondary_to_wheel_drive_power_w",
            )
        )
        for index, time in enumerate(trace.time_s):
            writer.writerow(
                (
                    time,
                    trace.mode[index],
                    trace.bearing_mode[index],
                    *trace.state[:, index],
                    trace.grade_degrees[index],
                    trace.vehicle_acceleration_mps2[index],
                    trace.road_grade_force_n[index],
                    trace.road_rolling_force_n[index],
                    trace.road_aero_force_n[index],
                    trace.road_external_force_n[index],
                    trace.output_drive_torque_nm[index],
                    trace.engine_torque_nm[index],
                    trace.engine_power_w[index],
                    trace.output_drive_power_w[index],
                )
            )


def _optional_value(value: float | None) -> str:
    return "" if value is None else f"{value:.9g}"


def write_metrics(path: Path, metrics: Iterable[ScenarioMetrics]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "scenario",
                "variant",
                "final_distance_m",
                "final_speed_kph",
                "time_to_100ft_s",
                "time_to_target_s",
                "engine_positive_work_kj",
                "engine_braking_absorption_kj",
                "output_positive_work_kj",
                "wheel_to_cvt_backdrive_kj",
                "downhill_gravity_input_kj",
                "uphill_gravity_demand_kj",
                "road_loss_kj",
                "vehicle_kinetic_energy_change_kj",
                "overrun_time_s",
                "release_count",
                "capture_count",
                "completed",
                "termination_reason",
            )
        )
        for item in metrics:
            writer.writerow(
                (
                    item.scenario,
                    item.variant,
                    item.final_distance_m,
                    item.final_speed_kph,
                    _optional_value(item.time_to_100ft_s),
                    _optional_value(item.time_to_target_s),
                    item.engine_positive_work_kj,
                    item.engine_braking_absorption_kj,
                    item.output_positive_work_kj,
                    item.wheel_to_cvt_backdrive_kj,
                    item.downhill_gravity_input_kj,
                    item.uphill_gravity_demand_kj,
                    item.road_loss_kj,
                    item.vehicle_kinetic_energy_change_kj,
                    item.overrun_time_s,
                    item.release_count,
                    item.capture_count,
                    int(item.completed),
                    item.termination_reason,
                )
            )


def write_deltas(path: Path, deltas: Iterable[ComparisonDelta]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "scenario",
                "distance_gain_m",
                "final_speed_gain_kph",
                "time_to_100ft_change_s",
                "time_to_target_change_s",
                "engine_braking_avoided_kj",
                "wheel_backdrive_avoided_kj",
                "output_positive_work_change_kj",
                "overrun_time_s",
                "release_count",
                "capture_count",
            )
        )
        for item in deltas:
            writer.writerow(
                (
                    item.scenario,
                    item.distance_gain_m,
                    item.final_speed_gain_kph,
                    _optional_value(item.time_to_100ft_change_s),
                    _optional_value(item.time_to_target_change_s),
                    item.engine_braking_avoided_kj,
                    item.wheel_backdrive_avoided_kj,
                    item.output_positive_work_change_kj,
                    item.overrun_time_s,
                    item.release_count,
                    item.capture_count,
                )
            )


def _shade_overrun(axis: plt.Axes, trace: ComparisonTrace) -> None:
    mask = trace.overrun_mask
    if not np.any(mask):
        return
    starts = np.flatnonzero(mask & np.r_[True, ~mask[:-1]])
    ends = np.flatnonzero(mask & np.r_[~mask[1:], True])
    for count, (start, end) in enumerate(zip(starts, ends, strict=True)):
        axis.axvspan(
            trace.time_s[start],
            trace.time_s[end],
            alpha=0.11,
            label="one-way overrun" if count == 0 else None,
        )


def _plot_reference_vs_oneway(
    *,
    scenario: RollingRoadScenario,
    locked: ComparisonTrace,
    one_way: ComparisonTrace,
    output_path: Path,
) -> None:
    figure, axes = plt.subplots(4, 1, figsize=(12, 12), sharex=True, constrained_layout=True)
    for trace, label, linestyle in (
        (locked, "locked final drive", "-"),
        (one_way, "ideal one-way bearing", "--"),
    ):
        axes[0].plot(trace.time_s, trace.vehicle_speed_mps * 3.6, linestyle=linestyle, label=label)
        axes[1].plot(trace.time_s, trace.vehicle_position_m, linestyle=linestyle, label=label)
        axes[2].plot(trace.time_s, trace.primary_rpm, linestyle=linestyle, label=f"primary — {label}")
        axes[2].plot(trace.time_s, trace.secondary_rpm, linestyle=linestyle, alpha=0.7, label=f"secondary — {label}")
        axes[3].plot(trace.time_s, trace.output_drive_power_w / 1000.0, linestyle=linestyle, label=label)
    _shade_overrun(axes[0], one_way)
    _shade_overrun(axes[1], one_way)
    _shade_overrun(axes[2], one_way)
    _shade_overrun(axes[3], one_way)
    axes[0].set_ylabel("vehicle speed [km/h]")
    axes[1].set_ylabel("distance [m]")
    axes[2].set_ylabel("shaft speed [rpm]")
    axes[3].plot(one_way.time_s, one_way.grade_degrees, linewidth=0.9, alpha=0.65, label="road grade [deg]")
    axes[3].axhline(0.0, linewidth=0.7, linestyle=":")
    axes[3].set_ylabel("output power [kW]\n/ grade [deg]")
    axes[3].set_xlabel("time [s]")
    for axis in axes:
        axis.grid(True, alpha=0.25)
        axis.legend(loc="best", fontsize=7)
    figure.suptitle(f"{scenario.name}: {scenario.description}")
    figure.savefig(output_path, dpi=175)
    plt.close(figure)


def _plot_suite_summary(
    *,
    deltas: Sequence[ComparisonDelta],
    output_path: Path,
) -> None:
    names = [item.scenario for item in deltas]
    locations = np.arange(len(names))
    figure, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    axes[0, 0].bar(locations, [item.distance_gain_m for item in deltas])
    axes[0, 0].set_ylabel("one-way − locked distance [m]")
    axes[0, 1].bar(locations, [item.final_speed_gain_kph for item in deltas])
    axes[0, 1].set_ylabel("one-way − locked final speed [km/h]")
    axes[1, 0].bar(locations, [item.engine_braking_avoided_kj for item in deltas], label="engine braking avoided")
    axes[1, 0].bar(locations, [item.wheel_backdrive_avoided_kj for item in deltas], alpha=0.6, label="wheel backdrive avoided")
    axes[1, 0].set_ylabel("avoided upstream absorption [kJ]")
    axes[1, 0].legend(loc="best")
    axes[1, 1].bar(locations, [item.overrun_time_s for item in deltas], label="overrun time")
    axes[1, 1].plot(locations, [item.release_count for item in deltas], marker="o", label="release count")
    axes[1, 1].plot(locations, [item.capture_count for item in deltas], marker="s", label="capture count")
    axes[1, 1].set_ylabel("overrun time [s] / events")
    axes[1, 1].legend(loc="best")
    for axis in axes.flat:
        axis.set_xticks(locations, names, rotation=32, ha="right")
        axis.grid(True, axis="y", alpha=0.25)
    figure.suptitle("Ideal one-way bearing: output and backdrive comparison")
    figure.savefig(output_path, dpi=175)
    plt.close(figure)


def _plot_energy_summary(
    *,
    locked_metrics: Sequence[ScenarioMetrics],
    one_way_metrics: Sequence[ScenarioMetrics],
    output_path: Path,
) -> None:
    names = [item.scenario for item in locked_metrics]
    locations = np.arange(len(names))
    width = 0.37
    figure, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True, constrained_layout=True)
    for values, label, offset in (
        ([item.engine_positive_work_kj for item in locked_metrics], "locked", -width / 2.0),
        ([item.engine_positive_work_kj for item in one_way_metrics], "one-way", width / 2.0),
    ):
        axes[0].bar(locations + offset, values, width=width, label=label)
    axes[0].set_ylabel("engine positive work [kJ]")
    axes[0].legend(loc="best")
    for values, label, offset in (
        ([item.engine_braking_absorption_kj for item in locked_metrics], "engine braking, locked", -width / 2.0),
        ([item.engine_braking_absorption_kj for item in one_way_metrics], "engine braking, one-way", width / 2.0),
    ):
        axes[1].bar(locations + offset, values, width=width, label=label)
    axes[1].plot(locations, [item.wheel_to_cvt_backdrive_kj for item in locked_metrics], marker="o", label="wheel→CVT, locked")
    axes[1].plot(locations, [item.wheel_to_cvt_backdrive_kj for item in one_way_metrics], marker="s", label="wheel→CVT, one-way")
    axes[1].set_ylabel("absorbed / backdrive work [kJ]")
    axes[1].legend(loc="best", fontsize=8)
    for axis in axes:
        axis.grid(True, axis="y", alpha=0.25)
    axes[1].set_xticks(locations, names, rotation=32, ha="right")
    figure.suptitle("Diagnostic energy comparison (not a complete CVT energy balance)")
    figure.savefig(output_path, dpi=175)
    plt.close(figure)


def _short_reason(reason: str) -> str:
    for token, label in (
        ("one_way_release", "release"),
        ("one_way_capture", "capture"),
        ("upper_stop_reached", "high stop"),
        ("low_ratio_seat_released", "shift start"),
        ("primary_closed_into_engaged_contact", "engage"),
    ):
        if token in reason:
            return label
    return reason.replace("_", " ")


def _write_event_log(
    *,
    path: Path,
    scenario: str,
    variant: str,
    result: HybridIntegrationResult[OutputMode],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("scenario", "variant", "time_s", "event_reason"))
        for record in result.transitions:
            writer.writerow((scenario, variant, record.time, record.transition.reason))


def default_scenarios() -> tuple[RollingRoadScenario, ...]:
    return (
        RollingRoadScenario("flat_launch", "Classic level-road launch", 0.0),
        RollingRoadScenario("rolling_10_long", "±10° rolling grade, 80 m cycle", 10.0, 80.0),
        RollingRoadScenario("rolling_10_medium", "±10° rolling grade, 40 m cycle", 10.0, 40.0),
        RollingRoadScenario("rolling_10_short", "±10° rolling grade, 20 m cycle", 10.0, 20.0),
        RollingRoadScenario("rolling_20_long", "±20° rolling grade, 80 m cycle", 20.0, 80.0),
        RollingRoadScenario("rolling_20_medium", "±20° rolling grade, 40 m cycle", 20.0, 40.0),
        RollingRoadScenario("rolling_20_short", "±20° rolling grade, 20 m cycle", 20.0, 20.0),
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset",
        type=Path,
        default=Path(__file__).with_name("presets") / "circular_traction_first_reference.json",
    )
    parser.add_argument(
        "--scenarios",
        default="rolling_20_long",
        help="Comma-separated scenario names, or 'all'. Run aggressive cases individually for the most repeatable LSODA runs.",
    )
    parser.add_argument("--duration-s", type=float, default=12.0)
    parser.add_argument("--initial-primary-rpm", type=float, default=1800.0)
    parser.add_argument("--target-engagement-rpm", type=float, default=2000.0)
    parser.add_argument("--performance-distance-m", type=float, default=100.0)
    parser.add_argument("--max-step-ms", type=float, default=150.0)
    parser.add_argument("--relative-tolerance", type=float, default=1.0e-2)
    parser.add_argument("--absolute-tolerance", type=float, default=1.0e-5)
    parser.add_argument("--maximum-transitions", type=int, default=700)
    parser.add_argument("--trace-samples", type=int, default=700)
    parser.add_argument("--release-torque-hysteresis-nm", type=float, default=0.5)
    parser.add_argument("--capture-torque-hysteresis-nm", type=float, default=0.5)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/one_way_bearing_comparison"))
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    for name in (
        "duration_s",
        "initial_primary_rpm",
        "target_engagement_rpm",
        "performance_distance_m",
        "max_step_ms",
        "relative_tolerance",
        "absolute_tolerance",
        "release_torque_hysteresis_nm",
        "capture_torque_hysteresis_nm",
    ):
        value = getattr(args, name)
        if not np.isfinite(value) or value <= 0.0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive.")
    if args.maximum_transitions < 1:
        parser.error("--maximum-transitions must be at least one.")
    if args.trace_samples < 150:
        parser.error("--trace-samples must be at least 150.")
    return args


def _select_scenarios(request: str) -> tuple[RollingRoadScenario, ...]:
    available = {item.name: item for item in default_scenarios()}
    if request.strip().lower() == "all":
        return tuple(available.values())
    requested = [name.strip() for name in request.split(",") if name.strip()]
    unknown = sorted(set(requested) - set(available))
    if unknown:
        raise ValueError(
            "Unknown scenario(s): " + ", ".join(unknown) + ". Available: " + ", ".join(available)
        )
    return tuple(available[name] for name in requested)


def _print_metrics(metrics: ScenarioMetrics) -> None:
    target = "not reached" if metrics.time_to_target_s is None else f"{metrics.time_to_target_s:.3f} s"
    hundred_feet = "not reached" if metrics.time_to_100ft_s is None else f"{metrics.time_to_100ft_s:.3f} s"
    print(
        f"  {metrics.variant:7s}  dist={metrics.final_distance_m:7.2f} m  "
        f"speed={metrics.final_speed_kph:6.2f} km/h  "
        f"100 ft={hundred_feet:>12s}  target={target:>12s}  "
        f"brake={metrics.engine_braking_absorption_kj:6.2f} kJ  "
        f"backdrive={metrics.wheel_to_cvt_backdrive_kj:6.2f} kJ  "
        f"overrun={metrics.overrun_time_s:5.2f} s  "
        f"R/C={metrics.release_count}/{metrics.capture_count}"
    )


def run_scenario(
    *,
    scenario: RollingRoadScenario,
    resolved,
    settings: HybridIntegratorSettings,
    initial: CVTDynamicState,
    duration_s: float,
    trace_samples: int,
    performance_distance_m: float,
    output_dir: Path,
    release_torque_hysteresis_nm: float,
    capture_torque_hysteresis_nm: float,
) -> tuple[ScenarioMetrics, ScenarioMetrics, ComparisonDelta]:
    """Run and write one comparison case in an isolated, reusable unit."""

    road_profile = scenario.road_profile()
    locked_child = build_locked_child(resolved=resolved, road_profile=road_profile)
    overrun_child = build_overrunning_child(locked=locked_child)
    locked_system = IdealOneWayBearingSystem(
        locked=locked_child,
        overrunning=overrun_child,
        road_profile=road_profile,
        allow_overrun=False,
        release_torque_tolerance_nm=release_torque_hysteresis_nm,
        capture_torque_tolerance_nm=capture_torque_hysteresis_nm,
    )
    one_way_system = IdealOneWayBearingSystem(
        locked=locked_child,
        overrunning=overrun_child,
        road_profile=road_profile,
        allow_overrun=True,
        release_torque_tolerance_nm=release_torque_hysteresis_nm,
        capture_torque_tolerance_nm=capture_torque_hysteresis_nm,
    )
    locked_result = integrate_hybrid(
        system=locked_system,
        time_span=(0.0, duration_s),
        initial_state=locked_system.initial_state(initial),
        initial_mode=locked_system.initial_mode(initial),
        settings=settings,
    )
    one_way_result = integrate_hybrid(
        system=one_way_system,
        time_span=(0.0, duration_s),
        initial_state=one_way_system.initial_state(initial),
        initial_mode=one_way_system.initial_mode(initial),
        settings=settings,
    )
    locked_trace = sample_trace(
        result=locked_result, system=locked_system, maximum_samples=trace_samples
    )
    one_way_trace = sample_trace(
        result=one_way_result, system=one_way_system, maximum_samples=trace_samples
    )
    locked_metric = calculate_metrics(
        scenario=scenario,
        variant="locked",
        trace=locked_trace,
        result=locked_result,
        effective_vehicle_mass=locked_system.effective_vehicle_mass,
        performance_distance_m=performance_distance_m,
    )
    one_way_metric = calculate_metrics(
        scenario=scenario,
        variant="one_way",
        trace=one_way_trace,
        result=one_way_result,
        effective_vehicle_mass=one_way_system.effective_vehicle_mass,
        performance_distance_m=performance_distance_m,
    )
    delta = calculate_delta(locked=locked_metric, one_way=one_way_metric)

    write_trace(output_dir / f"{scenario.name}_locked_trace.csv", locked_trace)
    write_trace(output_dir / f"{scenario.name}_one_way_trace.csv", one_way_trace)
    _write_event_log(
        path=output_dir / f"{scenario.name}_locked_events.csv",
        scenario=scenario.name,
        variant="locked",
        result=locked_result,
    )
    _write_event_log(
        path=output_dir / f"{scenario.name}_one_way_events.csv",
        scenario=scenario.name,
        variant="one_way",
        result=one_way_result,
    )
    _plot_reference_vs_oneway(
        scenario=scenario,
        locked=locked_trace,
        one_way=one_way_trace,
        output_path=output_dir / f"{scenario.name}_comparison.png",
    )
    return locked_metric, one_way_metric, delta


def main() -> None:
    args = parse_arguments()
    try:
        scenarios = _select_scenarios(args.scenarios)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    candidate, _ = load_candidate(args.preset)
    resolved = resolve_primary_preload(
        candidate, target_engagement_rpm=args.target_engagement_rpm
    )
    settings = HybridIntegratorSettings(
        relative_tolerance=args.relative_tolerance,
        absolute_tolerance=args.absolute_tolerance,
        method="LSODA",
        max_step=args.max_step_ms * 1.0e-3,
        maximum_transitions=args.maximum_transitions,
    )
    initial = launch_initial_state(primary_rpm=args.initial_primary_rpm)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    all_metrics: list[ScenarioMetrics] = []
    locked_metrics: list[ScenarioMetrics] = []
    one_way_metrics: list[ScenarioMetrics] = []
    deltas: list[ComparisonDelta] = []

    print("Ideal one-way-bearing comparison")
    print("=" * 88)
    print(candidate.label())
    print(f"duration={args.duration_s:.1f} s; output directory={args.output_dir}")
    print(
        "release/capture torque hysteresis="
        f"{args.release_torque_hysteresis_nm:.2f}/{args.capture_torque_hysteresis_nm:.2f} N m"
    )
    if len(scenarios) > 1:
        print(
            "Running several scenarios serially. For the most repeatable LSODA runs, "
            "run the more aggressive cases one command at a time."
        )

    for scenario in scenarios:
        print(f"\nRunning {scenario.name} ...", flush=True)
        locked_metric, one_way_metric, delta = run_scenario(
            scenario=scenario,
            resolved=resolved,
            settings=settings,
            initial=initial,
            duration_s=args.duration_s,
            trace_samples=args.trace_samples,
            performance_distance_m=args.performance_distance_m,
            output_dir=args.output_dir,
            release_torque_hysteresis_nm=args.release_torque_hysteresis_nm,
            capture_torque_hysteresis_nm=args.capture_torque_hysteresis_nm,
        )
        print(f"{scenario.name}: {scenario.description}")
        _print_metrics(locked_metric)
        _print_metrics(one_way_metric)
        print(
            f"  delta     distance={delta.distance_gain_m:+.2f} m  "
            f"speed={delta.final_speed_gain_kph:+.2f} km/h  "
            f"backdrive avoided={delta.wheel_backdrive_avoided_kj:+.2f} kJ"
        )
        all_metrics.extend((locked_metric, one_way_metric))
        locked_metrics.append(locked_metric)
        one_way_metrics.append(one_way_metric)
        deltas.append(delta)

    write_metrics(args.output_dir / "one_way_bearing_metrics.csv", all_metrics)
    write_deltas(args.output_dir / "one_way_bearing_comparison.csv", deltas)
    _plot_suite_summary(
        deltas=deltas,
        output_path=args.output_dir / "one_way_bearing_suite_summary.png",
    )
    _plot_energy_summary(
        locked_metrics=locked_metrics,
        one_way_metrics=one_way_metrics,
        output_path=args.output_dir / "one_way_bearing_energy_summary.png",
    )
    print(f"\nWrote metrics and figures to {args.output_dir}")
    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
