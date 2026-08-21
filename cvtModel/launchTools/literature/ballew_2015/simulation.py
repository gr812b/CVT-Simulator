"""Hybrid integration and reporting helpers for the Ballew (2015) benchmark."""

from __future__ import annotations

from dataclasses import dataclass
import json
from math import pi
from pathlib import Path
from typing import Sequence

import numpy as np
from numpy.typing import NDArray

from cinder.execution.hybrid import (
    HybridIntegrationResult,
    HybridIntegratorSettings,
    integrate_hybrid,
)
from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
from cinder.model.cvt.actuation import PulleyActuator
from cinder.model.system import CVTState, MechanicalCVTPlant

from case import (
    BallewBoundarySetup,
    build_ballew_assembly,
    build_boundary_setup,
    build_initial_cvt_state,
    build_primary_replay_actuator,
)
from constants import PUBLISHED
from controller import (
    BallewControllerHost,
    BallewPIControllerAxialForce,
    ControllerIntegralBridge,
)

RPM_PER_RAD_PER_S = 60.0 / (2.0 * pi)


@dataclass(frozen=True, slots=True)
class BallewSimulationSetup:
    """Fully assembled five-second composed CINDER benchmark."""

    system: ComposedCVTHybridSystem
    boundary_setup: BallewBoundarySetup
    initial_cvt_state: CVTState
    initial_full_state: NDArray[np.float64]
    initial_mode: object
    controller_force_law: BallewPIControllerAxialForce | None = None


@dataclass(frozen=True, slots=True)
class SampledCinderTrace:
    """CINDER states and reconstructed reporting signals at requested times."""

    time_s: NDArray[np.float64]
    full_state: NDArray[np.float64]
    primary_rpm: NDArray[np.float64]
    secondary_rpm: NDArray[np.float64]
    speed_ratio: NDArray[np.float64]
    belt_speed_m_per_s: NDArray[np.float64]
    shift_m: NDArray[np.float64]
    shift_speed_m_per_s: NDArray[np.float64]
    primary_effective_radius_m: NDArray[np.float64]
    secondary_effective_radius_m: NDArray[np.float64]
    vehicle_speed_m_per_s: NDArray[np.float64]
    vehicle_distance_m: NDArray[np.float64]
    secondary_road_torque_nm: NDArray[np.float64]
    mode: tuple[str, ...]


def build_simulation_setup(force_csv: str | Path) -> BallewSimulationSetup:
    """Construct the actual composed CINDER system used for the benchmark."""

    primary_actuator = build_primary_replay_actuator(force_csv)
    assembly, _ = build_ballew_assembly(primary_actuator=primary_actuator)
    plant = MechanicalCVTPlant.from_assembly(assembly)
    boundary_setup = build_boundary_setup()

    system = ComposedCVTHybridSystem.from_plant(
        plant=plant,
        primary_boundary=boundary_setup.primary,
        secondary_boundary=boundary_setup.secondary,
        host=boundary_setup.host,
    )
    # Reconstruction A5 uses no primary disengagement interval. CINDER's
    # operating graph therefore resolves lower_stop == engagement as a
    # zero-width deadzone: the legal shift domain is engaged all the way to
    # the low-ratio seat rather than inventing an epsilon-sized neutral region.
    if system.cvt.operating_limits.has_deadzone:
        raise RuntimeError(
            "Ballew reconstruction A5 requires an always-engaged zero-width deadzone."
        )
    initial_cvt_state = build_initial_cvt_state(plant.geometry)
    initial_full_state = system.initial_state(
        cvt_state=initial_cvt_state,
        host_state=boundary_setup.host.initial_state(secondary_shaft_angle=0.0),
    )
    initial_mode = system.classify_initial_mode_at_time(
        time=0.0,
        state=initial_full_state,
    )

    # Fail at construction time if the initial mode does not produce a finite
    # derivative. This is a useful benchmark-contract check before a long solve.
    initial_rhs = np.asarray(
        system.rhs(0.0, initial_full_state, initial_mode), dtype=float
    )
    if initial_rhs.shape != initial_full_state.shape or not np.all(np.isfinite(initial_rhs)):
        raise RuntimeError("Ballew initial CINDER RHS is not a finite aligned vector.")

    return BallewSimulationSetup(
        system=system,
        boundary_setup=boundary_setup,
        initial_cvt_state=initial_cvt_state,
        initial_full_state=_immutable_vector(initial_full_state),
        initial_mode=initial_mode,
    )


def build_closed_loop_simulation_setup(
    *, initial_error_integral_rpm_s: float = 0.0
) -> BallewSimulationSetup:
    """Construct CINDER under the reconstructed Ballew PI speed controller.

    The controller is benchmark plumbing around the unchanged CINDER plant.
    Its integral is a host state, while Figure 45 is reserved as an output
    reference rather than an imposed force. See Reconstruction A11.
    """

    bridge = ControllerIntegralBridge()
    controller_force = BallewPIControllerAxialForce(bridge=bridge)
    primary_actuator = PulleyActuator(controller_force)
    assembly, _ = build_ballew_assembly(primary_actuator=primary_actuator)
    plant = MechanicalCVTPlant.from_assembly(assembly)
    controller_host = BallewControllerHost(bridge=bridge)
    boundary_setup = build_boundary_setup(host=controller_host)

    system = ComposedCVTHybridSystem.from_plant(
        plant=plant,
        primary_boundary=boundary_setup.primary,
        secondary_boundary=boundary_setup.secondary,
        host=controller_host,
    )
    if system.cvt.operating_limits.has_deadzone:
        raise RuntimeError(
            "Ballew reconstruction A5 requires an always-engaged zero-width deadzone."
        )

    initial_cvt_state = build_initial_cvt_state(plant.geometry)
    initial_full_state = system.initial_state(
        cvt_state=initial_cvt_state,
        host_state=controller_host.initial_state(
            secondary_shaft_angle=0.0,
            error_integral_rpm_s=initial_error_integral_rpm_s,
        ),
    )
    initial_mode = system.classify_initial_mode_at_time(
        time=0.0, state=initial_full_state
    )
    initial_rhs = np.asarray(
        system.rhs(0.0, initial_full_state, initial_mode), dtype=float
    )
    if initial_rhs.shape != initial_full_state.shape or not np.all(np.isfinite(initial_rhs)):
        raise RuntimeError("Ballew closed-loop initial CINDER RHS is not finite/aligned.")

    return BallewSimulationSetup(
        system=system,
        boundary_setup=boundary_setup,
        initial_cvt_state=initial_cvt_state,
        initial_full_state=_immutable_vector(initial_full_state),
        initial_mode=initial_mode,
        controller_force_law=controller_force,
    )


def integrate_ballew_case_to(
    setup: BallewSimulationSetup,
    *,
    final_time_s: float,
    relative_tolerance: float = 1.0e-7,
    absolute_tolerance: float = 1.0e-9,
    max_step_s: float = 1.0e-3,
    method: str = "LSODA",
    maximum_transitions: int = 200,
) -> HybridIntegrationResult:
    """Integrate one Ballew setup to an arbitrary positive horizon.

    This is benchmark plumbing, not a new physical model.  The arbitrary horizon
    is useful for diagnosing a CINDER/controller incompatibility that terminates
    before the full five-second paper interval.
    """

    if not np.isfinite(final_time_s) or final_time_s <= 0.0:
        raise ValueError("final_time_s must be finite and strictly positive.")
    settings = HybridIntegratorSettings(
        relative_tolerance=relative_tolerance,
        absolute_tolerance=absolute_tolerance,
        method=method,
        max_step=max_step_s,
        maximum_transitions=maximum_transitions,
        retain_dense_output=True,
    )
    return integrate_hybrid(
        system=setup.system,
        time_span=(0.0, float(final_time_s)),
        initial_state=setup.initial_full_state,
        initial_mode=setup.initial_mode,
        settings=settings,
    )


def integrate_ballew_case(
    setup: BallewSimulationSetup,
    *,
    relative_tolerance: float = 1.0e-7,
    absolute_tolerance: float = 1.0e-9,
    max_step_s: float = 1.0e-3,
    method: str = "LSODA",
    maximum_transitions: int = 200,
) -> HybridIntegrationResult:
    """Run the headline five-second CINDER benchmark without calibration."""

    result = integrate_ballew_case_to(
        setup,
        final_time_s=PUBLISHED.simulation_duration_s,
        relative_tolerance=relative_tolerance,
        absolute_tolerance=absolute_tolerance,
        max_step_s=max_step_s,
        method=method,
        maximum_transitions=maximum_transitions,
    )
    if not result.completed:
        details = [
            "Ballew CINDER run terminated before five seconds",
            f"reason={result.termination_reason}",
            f"t={result.final_time:.12g} s",
            f"segments={len(result.segments)}",
            f"transitions={len(result.transitions)}",
        ]
        if result.transitions:
            record = result.transitions[-1]
            details.extend(
                (
                    f"last_events={record.fired_event_names}",
                    f"previous_mode={record.previous_mode}",
                )
            )
            metadata = dict(record.transition.metadata)
            diagnostics = metadata.get("cvt", {}).get(
                "zero_crossing_candidate_diagnostics"
            )
            if diagnostics is not None:
                metadata["cvt"] = dict(metadata["cvt"])
                metadata["cvt"].pop("zero_crossing_candidate_diagnostics", None)
                details.append(f"transition_metadata={metadata}")
                details.append(
                    "zero-crossing candidate diagnostics:\n"
                    + json.dumps(diagnostics, indent=2, sort_keys=True)
                )
            else:
                details.append(f"transition_metadata={metadata}")
        raise RuntimeError("; ".join(details))
    if abs(result.final_time - PUBLISHED.simulation_duration_s) > 5.0e-10:
        raise RuntimeError(
            "Ballew CINDER run did not reach the requested five-second endpoint."
        )
    return result


def uniform_report_times(*, step_s: float) -> NDArray[np.float64]:
    """Return a monotone 0-5 s reporting grid including both endpoints."""

    if not np.isfinite(step_s) or step_s <= 0.0:
        raise ValueError("step_s must be finite and strictly positive.")
    duration = PUBLISHED.simulation_duration_s
    count = max(1, int(np.ceil(duration / step_s)))
    values = np.linspace(0.0, duration, count + 1, dtype=float)
    values.setflags(write=False)
    return values


def sample_cinder_trace(
    setup: BallewSimulationSetup,
    result: HybridIntegrationResult,
    times_s: Sequence[float] | NDArray[np.float64],
) -> SampledCinderTrace:
    """Evaluate solver-native dense states and reporting signals at exact times."""

    times = _validated_times(times_s, final_time=result.final_time)
    states, modes = _dense_states_and_modes(result=result, times_s=times)

    n = times.size
    primary_rpm = np.empty(n, dtype=float)
    secondary_rpm = np.empty(n, dtype=float)
    speed_ratio = np.empty(n, dtype=float)
    belt_speed = np.empty(n, dtype=float)
    shift = np.empty(n, dtype=float)
    shift_speed = np.empty(n, dtype=float)
    rp = np.empty(n, dtype=float)
    rs = np.empty(n, dtype=float)
    vehicle_speed = np.empty(n, dtype=float)
    vehicle_distance = np.empty(n, dtype=float)
    road_torque = np.empty(n, dtype=float)

    max_shift = setup.system.cvt.model.geometry.spec.max_shift
    for index, time in enumerate(times):
        full = states[:, index]
        cvt = CVTState.from_vector(setup.system.layout.view(full, "cvt"))
        primary_rpm[index] = cvt.primary_angular_speed * RPM_PER_RAD_PER_S
        secondary_rpm[index] = cvt.secondary_angular_speed * RPM_PER_RAD_PER_S
        if abs(cvt.secondary_angular_speed) <= 1.0e-14:
            speed_ratio[index] = np.nan
        else:
            speed_ratio[index] = (
                cvt.primary_angular_speed / cvt.secondary_angular_speed
            )
        belt_speed[index] = cvt.belt_speed
        shift[index] = cvt.shift_position
        shift_speed[index] = cvt.shift_speed

        # The hybrid solver can land a floating-point ulp beyond a stop before
        # event projection. Reporting may clip only roundoff-scale excursions;
        # anything larger is a real benchmark failure and must remain visible.
        if cvt.shift_position < -1.0e-9 or cvt.shift_position > max_shift + 1.0e-9:
            raise RuntimeError(
                f"CINDER shift left its physical domain at t={time:.12g} s: "
                f"s={cvt.shift_position:.12g} m."
            )
        reporting_shift = float(np.clip(cvt.shift_position, 0.0, max_shift))
        geometry = setup.system.cvt.model.geometry.evaluate(reporting_shift)
        rp[index] = geometry.primary.effective
        rs[index] = geometry.secondary.effective

        boundaries = setup.system._shaft_boundaries(time=float(time), state=full)
        road = boundaries.secondary.metadata.get("road_load")
        if road is None:
            raise RuntimeError("Ballew secondary boundary did not expose road-load data.")
        vehicle_speed[index] = float(road.vehicle_speed)
        road_torque[index] = float(road.secondary_external_torque)
        vehicle_distance[index] = float(
            boundaries.secondary.metadata.get("vehicle_distance", np.nan)
        )

    arrays = (
        primary_rpm,
        secondary_rpm,
        speed_ratio,
        belt_speed,
        shift,
        shift_speed,
        rp,
        rs,
        vehicle_speed,
        vehicle_distance,
        road_torque,
    )
    for values in arrays:
        values.setflags(write=False)

    return SampledCinderTrace(
        time_s=times,
        full_state=states,
        primary_rpm=primary_rpm,
        secondary_rpm=secondary_rpm,
        speed_ratio=speed_ratio,
        belt_speed_m_per_s=belt_speed,
        shift_m=shift,
        shift_speed_m_per_s=shift_speed,
        primary_effective_radius_m=rp,
        secondary_effective_radius_m=rs,
        vehicle_speed_m_per_s=vehicle_speed,
        vehicle_distance_m=vehicle_distance,
        secondary_road_torque_nm=road_torque,
        mode=modes,
    )


def compact_mode(mode: object) -> str:
    """Return a stable human-readable label for one composed CVT mode."""

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


def _dense_states_and_modes(
    *, result: HybridIntegrationResult, times_s: NDArray[np.float64]
) -> tuple[NDArray[np.float64], tuple[str, ...]]:
    if not all(segment.has_dense_output for segment in result.segments):
        raise RuntimeError(
            "Ballew comparison requires retained solver-native dense output."
        )

    n_state = result.segments[0].state.shape[0]
    states = np.full((n_state, times_s.size), np.nan, dtype=float)
    assigned = np.zeros(times_s.size, dtype=bool)
    modes: list[str | None] = [None] * times_s.size
    tolerance = 2.0e-10

    # Later segments deliberately overwrite shared event endpoints. This gives
    # post-transition state/mode semantics at an exact hybrid boundary while
    # never interpolating across a reset.
    for segment in result.segments:
        mask = (
            (times_s >= segment.start_time - tolerance)
            & (times_s <= segment.end_time + tolerance)
        )
        indices = np.flatnonzero(mask)
        if indices.size == 0:
            continue
        local_times = np.clip(
            times_s[indices], segment.start_time, segment.end_time
        )
        values = segment.dense_state_at(local_times)
        states[:, indices] = values
        assigned[indices] = True
        label = compact_mode(segment.mode)
        for index in indices:
            modes[int(index)] = label

    if not np.all(assigned) or not np.all(np.isfinite(states)):
        missing = times_s[~assigned]
        raise RuntimeError(
            "Dense hybrid sampling did not cover all requested times; "
            f"first missing={missing[0] if missing.size else 'non-finite state'}."
        )
    if any(value is None for value in modes):
        raise RuntimeError("Dense hybrid sampling did not assign every mode label.")

    states.setflags(write=False)
    return states, tuple(str(value) for value in modes)


def _validated_times(
    values: Sequence[float] | NDArray[np.float64], *, final_time: float
) -> NDArray[np.float64]:
    times = np.asarray(values, dtype=float)
    if times.ndim != 1 or times.size == 0 or not np.all(np.isfinite(times)):
        raise ValueError("times must be a non-empty finite one-dimensional sequence.")
    if np.any(np.diff(times) <= 0.0):
        raise ValueError("times must be strictly increasing.")
    tolerance = 2.0e-10
    if times[0] < -tolerance or times[-1] > final_time + tolerance:
        raise ValueError("requested times must lie inside the integrated interval.")
    times = np.clip(times, 0.0, final_time)
    times = np.array(times, dtype=float, copy=True)
    times.setflags(write=False)
    return times


def _immutable_vector(values: NDArray[np.float64]) -> NDArray[np.float64]:
    vector = np.array(values, dtype=float, copy=True)
    if vector.ndim != 1 or not np.all(np.isfinite(vector)):
        raise ValueError("expected one finite vector.")
    vector.setflags(write=False)
    return vector
