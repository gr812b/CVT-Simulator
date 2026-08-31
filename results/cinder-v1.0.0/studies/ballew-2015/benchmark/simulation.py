"""CINDER 1.0.0 assembly, integration, and dense sampling for Ballew."""

from __future__ import annotations

from dataclasses import dataclass
from math import pi
from pathlib import Path
from typing import Sequence

import numpy as np
from numpy.typing import NDArray

from cinder import ComposedCVTHybridSystem, CVTState, MechanicalCVTPlant
from cinder.execution.hybrid import HybridIntegratorSettings
from cinder.model.cvt.actuation import PulleyActuator
from cinder.results import ReportingGrid, ReportingSettings

from .case import (
    BallewBoundarySetup,
    build_ballew_assembly,
    build_boundary_setup,
    build_initial_cvt_state,
    build_primary_replay_actuator,
)
from .constants import PUBLISHED
from .controller import (
    BallewControllerHost,
    BallewPIControllerAxialForce,
    ControllerIntegralBridge,
)

RPM_PER_RAD_PER_S = 60.0 / (2.0 * pi)


@dataclass(frozen=True, slots=True)
class BallewSimulationSetup:
    system: ComposedCVTHybridSystem
    boundary_setup: BallewBoundarySetup
    assembly: object
    initial_cvt_state: CVTState
    initial_full_state: NDArray[np.float64]
    initial_mode: object
    controller_force_law: BallewPIControllerAxialForce | None = None


@dataclass(frozen=True, slots=True)
class DenseSample:
    time_s: NDArray[np.float64]
    full_state: NDArray[np.float64]
    primary_rpm: NDArray[np.float64]
    secondary_rpm: NDArray[np.float64]
    speed_ratio: NDArray[np.float64]
    shift_m: NDArray[np.float64]
    shift_speed_m_per_s: NDArray[np.float64]
    mode: tuple[str, ...]


def _freeze(values) -> NDArray[np.float64]:
    array = np.asarray(values, dtype=float)
    frozen = np.array(array, copy=True)
    frozen.setflags(write=False)
    return frozen


def _finish_setup(
    *, assembly, boundary_setup: BallewBoundarySetup, controller_force_law=None
) -> BallewSimulationSetup:
    plant = MechanicalCVTPlant.from_assembly(assembly)
    system = ComposedCVTHybridSystem.from_plant(
        plant=plant,
        primary_boundary=boundary_setup.primary,
        secondary_boundary=boundary_setup.secondary,
        host=boundary_setup.host,
    )
    if system.cvt.operating_limits.has_deadzone:
        raise RuntimeError("Ballew A5 requires an always-engaged zero-width deadzone.")

    initial_cvt_state = build_initial_cvt_state(plant.geometry)
    if isinstance(boundary_setup.host, BallewControllerHost):
        host_state = boundary_setup.host.initial_state(
            secondary_shaft_angle=0.0,
            error_integral_rpm_s=0.0,
        )
    else:
        host_state = boundary_setup.host.initial_state(secondary_shaft_angle=0.0)
    initial_full_state = system.initial_state(
        cvt_state=initial_cvt_state,
        host_state=host_state,
    )
    initial_mode = system.classify_initial_mode_at_time(
        time=0.0, state=initial_full_state
    )
    initial_rhs = np.asarray(system.rhs(0.0, initial_full_state, initial_mode), dtype=float)
    if initial_rhs.shape != initial_full_state.shape or not np.all(np.isfinite(initial_rhs)):
        raise RuntimeError("Ballew initial CINDER RHS is not finite/aligned.")

    return BallewSimulationSetup(
        system=system,
        boundary_setup=boundary_setup,
        assembly=assembly,
        initial_cvt_state=initial_cvt_state,
        initial_full_state=_freeze(initial_full_state),
        initial_mode=initial_mode,
        controller_force_law=controller_force_law,
    )


def build_force_replay_setup(force_csv: str | Path) -> BallewSimulationSetup:
    assembly = build_ballew_assembly(
        primary_actuator=build_primary_replay_actuator(force_csv)
    )
    boundaries = build_boundary_setup()
    return _finish_setup(assembly=assembly, boundary_setup=boundaries)


def build_closed_loop_setup() -> BallewSimulationSetup:
    bridge = ControllerIntegralBridge()
    controller_force = BallewPIControllerAxialForce(bridge=bridge)
    controller_host = BallewControllerHost(bridge=bridge)
    assembly = build_ballew_assembly(
        primary_actuator=PulleyActuator(controller_force)
    )
    boundaries = build_boundary_setup(host=controller_host)
    return _finish_setup(
        assembly=assembly,
        boundary_setup=boundaries,
        controller_force_law=controller_force,
    )


def run_setup(
    setup: BallewSimulationSetup,
    *,
    relative_tolerance: float,
    absolute_tolerance: float,
    max_step_s: float,
    maximum_transitions: int,
    report_step_s: float,
    method: str = "LSODA",
):
    settings = HybridIntegratorSettings(
        relative_tolerance=relative_tolerance,
        absolute_tolerance=absolute_tolerance,
        method=method,
        max_step=max_step_s,
        maximum_transitions=maximum_transitions,
        retain_dense_output=True,
    )
    reporting = ReportingSettings(
        grid=ReportingGrid.uniform_time_step(report_step_s),
        include_contact=True,
        include_actuation=True,
        include_closure_audit=False,
        include_integrated_observers=True,
    )
    return setup.system.run(
        time_span=(0.0, PUBLISHED.simulation_duration_s),
        initial_state=setup.initial_full_state,
        initial_mode=setup.initial_mode,
        settings=settings,
        reporting_settings=reporting,
    )


def compact_mode(mode: object) -> str:
    cvt = getattr(mode, "cvt", mode)
    engagement = getattr(getattr(cvt, "engagement", None), "value", "unknown")
    shift_constraint = getattr(
        getattr(cvt, "shift_constraint", None), "value", "unknown"
    )
    contact = getattr(cvt, "contact_regime", None)
    if contact is None:
        return f"{engagement}/{shift_constraint}"
    contact_mode = getattr(getattr(contact, "mode", None), "value", None)
    return (
        f"{engagement}/{shift_constraint}/{contact_mode}"
        if contact_mode is not None
        else f"{engagement}/{shift_constraint}/{contact}"
    )


def _segment_for_time(raw_result, time: float):
    scale = max(1.0, abs(time), abs(raw_result.final_time))
    tol = 128.0 * np.finfo(float).eps * scale
    matches = [
        segment
        for segment in raw_result.segments
        if segment.start_time - tol <= time <= segment.end_time + tol
    ]
    if not matches:
        raise RuntimeError(f"No dense hybrid segment contains t={time:.12g} s.")
    # At a transition timestamp use the successor segment when both are valid.
    return max(matches, key=lambda segment: segment.start_time)


def sample_dense(
    setup: BallewSimulationSetup,
    result,
    times_s: Sequence[float] | NDArray[np.float64],
) -> DenseSample:
    times = np.asarray(times_s, dtype=float)
    if times.ndim != 1 or times.size == 0 or not np.all(np.isfinite(times)):
        raise ValueError("times_s must be a finite non-empty vector.")
    raw = result.trace.raw
    if times[0] < -1e-12 or times[-1] > raw.final_time + 1e-12:
        raise ValueError("Requested dense-sample time lies outside integration interval.")
    states = np.empty((setup.initial_full_state.size, times.size), dtype=float)
    modes: list[str] = []
    for index, time in enumerate(times):
        segment = _segment_for_time(raw, float(time))
        if not segment.has_dense_output:
            raise RuntimeError("Exact Ballew comparison requires retained dense output.")
        state = np.asarray(segment.dense_state_at(np.asarray([time], dtype=float)))[:, 0]
        states[:, index] = state
        modes.append(compact_mode(segment.mode))

    primary = np.empty(times.size, dtype=float)
    secondary = np.empty(times.size, dtype=float)
    ratio = np.empty(times.size, dtype=float)
    shift = np.empty(times.size, dtype=float)
    shift_speed = np.empty(times.size, dtype=float)
    for index in range(times.size):
        cvt = CVTState.from_vector(setup.system.layout.view(states[:, index], "cvt"))
        primary[index] = cvt.primary_angular_speed * RPM_PER_RAD_PER_S
        secondary[index] = cvt.secondary_angular_speed * RPM_PER_RAD_PER_S
        ratio[index] = (
            cvt.primary_angular_speed / cvt.secondary_angular_speed
            if abs(cvt.secondary_angular_speed) > 1e-14
            else np.nan
        )
        shift[index] = cvt.shift_position
        shift_speed[index] = cvt.shift_speed

    return DenseSample(
        time_s=_freeze(times),
        full_state=_freeze(states),
        primary_rpm=_freeze(primary),
        secondary_rpm=_freeze(secondary),
        speed_ratio=_freeze(ratio),
        shift_m=_freeze(shift),
        shift_speed_m_per_s=_freeze(shift_speed),
        mode=tuple(modes),
    )


def controller_force_for_sample(
    setup: BallewSimulationSetup, sample: DenseSample
) -> NDArray[np.float64]:
    law = setup.controller_force_law
    if law is None:
        raise RuntimeError("Setup has no controller force law.")
    force = np.empty(sample.time_s.size, dtype=float)
    for index in range(sample.time_s.size):
        host = setup.system.layout.view(sample.full_state[:, index], "host")
        force[index] = law.force_from_state(
            primary_rpm=float(sample.primary_rpm[index]),
            error_integral_rpm_s=float(host[1]),
        )
    return _freeze(force)
