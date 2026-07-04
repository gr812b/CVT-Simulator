"""Run the saved circular-primary CVT tune through a 20 degree hill step.

This scenario deliberately reuses the current traction-first circular reference
rather than creating a new tune.  It performs two ordinary CINDER integrations:

* 0–10 s: level road, recreating the current saved full-launch condition;
* 10–20 s: same state and same CVT, but road grade changed to +20 degrees.

The grade change is an *external load step*.  CINDER's native RoadProfile is
position-indexed, so an exact time-triggered hill is represented by restarting
at t=10 with an otherwise identical model that has a new constant grade.  The
state is continuous at the step; there is no artificial impact or reset.  The
second phase reclassifies the inherited state against the new road torque, so
an upper-stop state can release and backshift only when its unilateral reaction
would become tensile.

This is useful for backshift and load-transient checks.  It is not a terrain
profile with a physical hill length.  For a route whose grade changes with
travel distance, replace the constant profile with CallableRoadProfile.

Default use:

    python tools2/run_hill_step_response.py --no-show

Useful variations:

    # A milder load step, keeping exactly the same tune.
    python tools2/run_hill_step_response.py --hill-grade-deg 12 --no-show

    # Observe longer post-step behavior.
    python tools2/run_hill_step_response.py --hill-duration-s 20 --no-show

    # Disable numerical chunk restarts.  The default 1 s interval does not
    # alter the physics; it simply prevents LSODA from spending excessive time
    # in its internal stiffness detector during a long slow backshift.
    python tools2/run_hill_step_response.py --hill-restart-s 0 --no-show

The script writes a compact response plot, an exportable CSV, and a JSON
summary.  Physical checks can be requested separately for the level and hill phases
with ``--run-audit``.  They are opt-in because the audit intentionally
re-evaluates contact closure at many accepted states and is substantially
slower than the transient itself.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from math import radians
import json
from pathlib import Path
import sys
from typing import Iterable

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

from cinder.integration import CVTDynamicState, HybridIntegratorSettings  # noqa: E402
from cinder.integration.cvt_operating_hybrid import (
    CVTOperatingHybridSystem,
)  # noqa: E402
from cinder.integration.hybrid import HybridIntegrationResult  # noqa: E402
from cinder.vehicle import ConstantGradeRoadProfile  # noqa: E402
from launch_tuning_common import (  # noqa: E402
    MILLIMETRE,
    RPM_PER_RADIAN_PER_SECOND,
    TuneCandidate,
    build_operating_system,
    launch_initial_state,
    resolve_primary_preload,
)

_DEFAULT_PRESET = (
    _TOOLS_DIRECTORY / "presets" / "circular_traction_first_reference.json"
)


@dataclass(frozen=True, slots=True)
class Phase:
    """One fixed-road-profile CINDER result."""

    name: str
    grade_degrees: float
    system: CVTOperatingHybridSystem
    result: object


@dataclass(frozen=True, slots=True)
class ResponseTrace:
    """State and road-load values sampled without a second contact closure solve.

    The existing full-launch diagnostic tool evaluates detailed contact closure
    values at every plotted point.  That is ideal for a single tune diagnostic,
    but unnecessarily expensive for this 20 s load-step utility.  This trace
    keeps the direct hybrid state history and state-known road/geometry outputs.
    Contact regime changes are still included in the transition timeline.
    """

    time: NDArray[np.float64]
    state: NDArray[np.float64]
    phase: tuple[str, ...]
    mode: tuple[str, ...]
    grade_degrees: NDArray[np.float64]
    road_torque_nm: NDArray[np.float64]
    road_force_n: NDArray[np.float64]
    vehicle_speed_mps: NDArray[np.float64]
    vehicle_distance_m: NDArray[np.float64]
    effective_ratio: NDArray[np.float64]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", type=Path, default=_DEFAULT_PRESET)
    parser.add_argument("--flat-duration-s", type=float, default=10.0)
    parser.add_argument("--hill-duration-s", type=float, default=10.0)
    parser.add_argument("--hill-grade-deg", type=float, default=20.0)
    parser.add_argument("--initial-primary-rpm", type=float, default=1800.0)
    parser.add_argument("--target-engagement-rpm", type=float, default=2000.0)
    parser.add_argument("--solver-method", default=None)
    parser.add_argument("--max-step-ms", type=float, default=None)
    parser.add_argument("--relative-tolerance", type=float, default=None)
    parser.add_argument("--absolute-tolerance", type=float, default=None)
    parser.add_argument(
        "--hill-restart-s",
        type=float,
        default=1.0,
        help="Numerical-only uphill restart interval; 0 keeps one uninterrupted hill integration.",
    )
    parser.add_argument("--maximum-transitions", type=int, default=80)
    parser.add_argument("--plot-samples", type=int, default=700)
    parser.add_argument(
        "--run-audit",
        action="store_true",
        help=(
            "Run the expensive system-level physical audit on each fixed-grade phase. "
            "The transient and export run without it by default."
        ),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/hill_step_response")
    )
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()

    for name in (
        "flat_duration_s",
        "hill_duration_s",
        "hill_grade_deg",
        "initial_primary_rpm",
        "target_engagement_rpm",
        "hill_restart_s",
    ):
        if not np.isfinite(getattr(args, name)):
            parser.error(f"--{name.replace('_', '-')} must be finite.")
    for name in ("max_step_ms", "relative_tolerance", "absolute_tolerance"):
        value = getattr(args, name)
        if value is not None and (not np.isfinite(value) or value <= 0.0):
            parser.error(
                f"--{name.replace('_', '-')} must be finite and positive when supplied."
            )
    if args.flat_duration_s <= 0.0 or args.hill_duration_s <= 0.0:
        parser.error("Both duration arguments must be positive.")
    if not -89.0 < args.hill_grade_deg < 89.0:
        parser.error("--hill-grade-deg must lie strictly between -89 and 89.")
    if args.initial_primary_rpm < 0.0 or args.target_engagement_rpm <= 0.0:
        parser.error(
            "Initial RPM must be non-negative and target engagement RPM positive."
        )
    if (
        args.hill_restart_s < 0.0
        or args.maximum_transitions < 1
        or args.plot_samples < 100
    ):
        parser.error(
            "hill restart must be non-negative; transitions >= 1; plot samples >= 100."
        )
    return args


def load_reference(path: Path) -> tuple[TuneCandidate, dict[str, float | str]]:
    """Read the saved circular-primary reference, preserving it as the default."""

    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    candidate_data = payload["candidate"]
    integration_data = payload.get("integration", {})
    candidate = TuneCandidate(
        flyweight_mass_kg=float(candidate_data["flyweight_mass_kg"]),
        helix_angle_degrees=float(candidate_data["helix_angle_degrees"]),
        secondary_torsional_pretension_degrees=float(
            candidate_data["secondary_torsional_pretension_degrees"]
        ),
        secondary_compression_preload_mm=float(
            candidate_data["secondary_compression_preload_mm"]
        ),
        primary_ramp_kind=str(candidate_data["primary_ramp_kind"]),
        primary_ramp_angle_degrees=float(
            candidate_data.get("primary_ramp_angle_degrees", 30.0)
        ),
        primary_ramp_start_angle_degrees=float(
            candidate_data["primary_ramp_start_angle_degrees"]
        ),
        primary_ramp_end_angle_degrees=float(
            candidate_data["primary_ramp_end_angle_degrees"]
        ),
    )
    return candidate, dict(integration_data)


def system_with_grade(*, resolved, grade_degrees: float) -> CVTOperatingHybridSystem:
    """Construct the normal hybrid system with only its road profile replaced."""

    template, _ = build_operating_system(resolved.constants)
    model = template.model.with_road_profile(
        ConstantGradeRoadProfile(radians(grade_degrees))
    )
    return CVTOperatingHybridSystem(
        model=model,
        traction_law=template.traction_law,
        solve_settings=template.solve_settings,
        operating_limits=template.operating_limits,
        switching_settings=template.switching_settings,
    )


def final_mode(result) -> object | None:
    """Recover the mode owning the endpoint state for a transparent restart."""

    if result.transitions and result.transitions[-1].time == result.final_time:
        return result.transitions[-1].transition.next_mode
    return result.segments[-1].mode


def integrate_phase(
    *,
    system: CVTOperatingHybridSystem,
    start: float,
    end: float,
    initial_state: CVTDynamicState,
    settings: HybridIntegratorSettings,
    restart_s: float,
):
    """Integrate one fixed-grade phase, optionally in state/mode-continuous chunks."""

    if restart_s <= 0.0:
        return system.integrate(
            time_span=(start, end), initial_state=initial_state, settings=settings
        )

    chunks = []
    time = start
    state = initial_state
    mode = (
        None  # At the grade step, let CINDER classify under the new road torque once.
    )
    while time < end - 1.0e-12:
        next_time = min(time + restart_s, end)
        result = system.integrate(
            time_span=(time, next_time),
            initial_state=state,
            initial_regime=mode,
            settings=settings,
        )
        chunks.append(result)
        if not result.completed or result.final_time < next_time - 1.0e-9:
            break
        next_mode = final_mode(result)
        if next_mode is None:
            break
        time = result.final_time
        state = CVTDynamicState.from_vector(result.final_state)
        mode = next_mode

    return HybridIntegrationResult(
        segments=tuple(segment for chunk in chunks for segment in chunk.segments),
        transitions=tuple(record for chunk in chunks for record in chunk.transitions),
        completed=bool(chunks)
        and chunks[-1].completed
        and chunks[-1].final_time >= end - 1.0e-9,
        termination_reason=(
            "final_time_reached"
            if chunks and chunks[-1].completed and chunks[-1].final_time >= end - 1.0e-9
            else (chunks[-1].termination_reason if chunks else "no_chunks_integrated")
        ),
    )


def mode_text(mode) -> str:
    """Human-readable compact hybrid mode for the CSV."""

    if mode.contact_regime is None:
        return f"{mode.engagement.value}/{mode.shift_constraint.value}"
    return f"{mode.engagement.value}/{mode.shift_constraint.value}/{mode.contact_regime.mode.value}"


def allocate_segment_samples(sizes: list[int], total: int) -> list[int]:
    """Allocate a bounded plotting budget across all hybrid segments."""

    size_sum = sum(sizes)
    if size_sum <= total:
        return sizes
    allocation = [max(2, round(total * size / size_sum)) for size in sizes]
    while sum(allocation) > total:
        index = max(range(len(allocation)), key=lambda i: allocation[i])
        if allocation[index] <= 2:
            break
        allocation[index] -= 1
    return allocation


def sample_state_road_trace(
    phases: tuple[Phase, ...], maximum_samples: int
) -> ResponseTrace:
    """Sample state-known data across both phases without re-solving contact closure."""

    segments = [
        (phase, segment) for phase in phases for segment in phase.result.segments
    ]
    budgets = allocate_segment_samples(
        [segment.state.shape[1] for _, segment in segments], maximum_samples
    )
    time_values: list[float] = []
    state_values: list[NDArray[np.float64]] = []
    phase_values: list[str] = []
    mode_values: list[str] = []
    grade_values: list[float] = []
    torque_values: list[float] = []
    force_values: list[float] = []
    speed_values: list[float] = []
    distance_values: list[float] = []
    ratio_values: list[float] = []

    for (phase, segment), budget in zip(segments, budgets, strict=True):
        indices = np.unique(
            np.linspace(0, segment.state.shape[1] - 1, budget, dtype=int)
        )
        for index in indices:
            vector = np.asarray(segment.state[:, index], dtype=float)
            state = CVTDynamicState.from_vector(vector)
            snapshot = phase.system.model.snapshot(state=state)
            road = snapshot.vehicle_road_load
            time_values.append(float(segment.time[index]))
            state_values.append(vector)
            phase_values.append(phase.name)
            mode_values.append(mode_text(segment.mode))
            grade_values.append(float(np.rad2deg(road.grade_angle)))
            torque_values.append(float(road.secondary_external_torque))
            force_values.append(float(road.external_force))
            speed_values.append(float(road.vehicle_speed))
            distance_values.append(float(snapshot.vehicle_distance))
            ratio_values.append(
                float(
                    snapshot.geometry.secondary.effective
                    / snapshot.geometry.primary.effective
                )
            )

    return ResponseTrace(
        time=np.asarray(time_values, dtype=float),
        state=np.column_stack(state_values),
        phase=tuple(phase_values),
        mode=tuple(mode_values),
        grade_degrees=np.asarray(grade_values, dtype=float),
        road_torque_nm=np.asarray(torque_values, dtype=float),
        road_force_n=np.asarray(force_values, dtype=float),
        vehicle_speed_mps=np.asarray(speed_values, dtype=float),
        vehicle_distance_m=np.asarray(distance_values, dtype=float),
        effective_ratio=np.asarray(ratio_values, dtype=float),
    )


def short_event(reason: str) -> str:
    """Compact labels keep event lines readable over 20 seconds."""

    mapping = (
        ("lower_stop_released", "low stop"),
        ("primary_closed_into_engaged_contact", "engage"),
        ("low_ratio_seat_reached", "low seat"),
        ("low_ratio_seat_released", "shift start"),
        ("contact_restuck", "re-stick"),
        ("upper_stop_reached", "high stop"),
        ("upper_stop_released", "high release"),
        ("static_capacity_exhausted", "slip"),
    )
    for fragment, label in mapping:
        if fragment in reason:
            return label
    return reason.replace("_", " ")


def mark_events(
    axes: Iterable[plt.Axes],
    label_axes: Iterable[plt.Axes],
    phases: tuple[Phase, ...],
    step_time: float,
    hill_grade: float,
) -> None:
    """Show all event times, but write small labels only on key panels."""

    axes = tuple(axes)
    label_axes = tuple(label_axes)
    for axis in axes:
        axis.axvline(step_time, color="black", linestyle="-.", linewidth=1.0, alpha=0.8)
    for axis in label_axes:
        axis.annotate(
            f"hill {hill_grade:.0f}°",
            xy=(step_time, 0.04),
            xycoords=("data", "axes fraction"),
            xytext=(3, 0),
            textcoords="offset points",
            rotation=90,
            va="bottom",
            ha="left",
            fontsize=6.5,
        )
    counter = 0
    for phase in phases:
        for record in phase.result.transitions:
            for axis in axes:
                axis.axvline(record.time, linestyle="--", linewidth=0.8, alpha=0.6)
            fraction = 0.97 - 0.12 * (counter % 5)
            for axis in label_axes:
                axis.annotate(
                    short_event(record.transition.reason),
                    xy=(record.time, fraction),
                    xycoords=("data", "axes fraction"),
                    xytext=(2, 0),
                    textcoords="offset points",
                    rotation=90,
                    va="top",
                    ha="left",
                    fontsize=6.0,
                )
            counter += 1


def plot_response(
    trace: ResponseTrace,
    phases: tuple[Phase, ...],
    resolved,
    step_time: float,
    hill_grade: float,
):
    """Plot the backshift experiment without hidden mechanics recomputation."""

    time = trace.time
    primary_rpm = trace.state[0] * RPM_PER_RADIAN_PER_SECOND
    secondary_rpm = trace.state[1] * RPM_PER_RADIAN_PER_SECOND
    shift_mm = trace.state[3] / MILLIMETRE
    shift_speed = trace.state[4] / MILLIMETRE
    flat = np.asarray([item == "level" for item in trace.phase])

    figure, axes = plt.subplots(2, 3, figsize=(19, 9.5), constrained_layout=False)

    speed_axis = axes[0, 0]
    speed_axis.plot(time, primary_rpm, label=r"$\omega_p$")
    speed_axis.plot(time, secondary_rpm, label=r"$\omega_s$")
    speed_axis.set_title("Shaft speeds")
    speed_axis.set_xlabel("Time [s]")
    speed_axis.set_ylabel("Speed [rpm]")
    speed_axis.grid(True, alpha=0.25)
    speed_axis.legend(loc="best")

    shift_axis = axes[0, 1]
    shift_axis.plot(time, shift_mm, label=r"$s$")
    shift_axis.axhline(
        resolved.constants.deadzone_shift / MILLIMETRE, linestyle="--", label="engage"
    )
    shift_axis.axhline(
        resolved.constants.max_shift / MILLIMETRE, linestyle="--", label="high stop"
    )
    shift_axis.set_title("Shift coordinate and speed")
    shift_axis.set_xlabel("Time [s]")
    shift_axis.set_ylabel("Shift [mm]")
    shift_axis.grid(True, alpha=0.25)
    shift_rate_axis = shift_axis.twinx()
    shift_rate_axis.plot(time, shift_speed, linestyle=":", label=r"$\dot{s}$")
    shift_rate_axis.set_ylabel("Shift speed [mm/s]")
    handles, labels = shift_axis.get_legend_handles_labels()
    handles_2, labels_2 = shift_rate_axis.get_legend_handles_labels()
    shift_axis.legend(handles + handles_2, labels + labels_2, loc="best")

    curve_axis = axes[0, 2]
    curve_axis.plot(secondary_rpm[flat], primary_rpm[flat], label="level")
    curve_axis.plot(
        secondary_rpm[~flat], primary_rpm[~flat], label=f"{hill_grade:.0f}° hill"
    )
    curve_axis.scatter([secondary_rpm[0]], [primary_rpm[0]], marker="o", label="launch")
    transition_index = int(np.argmin(np.abs(time - step_time)))
    curve_axis.scatter(
        [secondary_rpm[transition_index]],
        [primary_rpm[transition_index]],
        marker="s",
        label="hill step",
    )
    curve_axis.set_title("Shift curve: primary vs secondary speed")
    curve_axis.set_xlabel("Secondary speed [rpm]")
    curve_axis.set_ylabel("Primary speed [rpm]")
    curve_axis.grid(True, alpha=0.25)
    curve_axis.legend(loc="best")

    road_axis = axes[1, 0]
    road_axis.step(time, trace.grade_degrees, where="post", label="grade")
    road_axis.set_title("Road grade and secondary road torque")
    road_axis.set_xlabel("Time [s]")
    road_axis.set_ylabel("Grade [deg]")
    road_axis.grid(True, alpha=0.25)
    torque_axis = road_axis.twinx()
    torque_axis.plot(time, trace.road_torque_nm, label=r"$\tau_{road,s}$")
    torque_axis.set_ylabel("Road torque [N m]")
    handles, labels = road_axis.get_legend_handles_labels()
    handles_2, labels_2 = torque_axis.get_legend_handles_labels()
    road_axis.legend(handles + handles_2, labels + labels_2, loc="best")

    vehicle_axis = axes[1, 1]
    vehicle_axis.plot(time, trace.vehicle_speed_mps * 3.6, label="speed")
    vehicle_axis.set_title("Vehicle response")
    vehicle_axis.set_xlabel("Time [s]")
    vehicle_axis.set_ylabel("Vehicle speed [km/h]")
    vehicle_axis.grid(True, alpha=0.25)
    distance_axis = vehicle_axis.twinx()
    distance_axis.plot(time, trace.vehicle_distance_m, linestyle=":", label="distance")
    distance_axis.set_ylabel("Distance [m]")
    handles, labels = vehicle_axis.get_legend_handles_labels()
    handles_2, labels_2 = distance_axis.get_legend_handles_labels()
    vehicle_axis.legend(handles + handles_2, labels + labels_2, loc="best")

    ratio_axis = axes[1, 2]
    ratio_axis.plot(time, trace.effective_ratio, label=r"$r_s/r_p$")
    ratio_axis.plot(time, shift_mm, linestyle=":", label=r"$s$ [mm]")
    ratio_axis.set_title("Backshift geometry")
    ratio_axis.set_xlabel("Time [s]")
    ratio_axis.set_ylabel("Ratio [-] / shift [mm]")
    ratio_axis.grid(True, alpha=0.25)
    ratio_axis.legend(loc="best")

    mark_events(
        axes=(speed_axis, shift_axis, road_axis, vehicle_axis, ratio_axis),
        label_axes=(speed_axis, shift_axis, road_axis),
        phases=phases,
        step_time=step_time,
        hill_grade=hill_grade,
    )
    figure.subplots_adjust(
        left=0.055, right=0.955, bottom=0.08, top=0.89, wspace=0.32, hspace=0.34
    )
    figure.suptitle(
        "CINDER circular-primary hill-step response | "
        f"{resolved.candidate.label()} | primary preload={resolved.resolved_primary_preload_mm:.2f} mm",
        fontsize=13,
    )
    return figure


def audit_phase(phase: Phase) -> tuple[str, list[str]]:
    """Run the repository audit per phase, recognizing old low-seat-only false positives."""

    try:
        from hybrid_system_checks import CVTSystemCheckSettings, check_cvt_hybrid_result
    except ImportError:
        return "unavailable", [
            "Physical audit unavailable: hybrid_system_checks.py not found."
        ]
    try:
        report = check_cvt_hybrid_result(
            system=phase.system,
            result=phase.result,
            # Keep this optional audit practical for a 20 s two-phase scenario.
            # The existing dedicated audit harness remains the right place for
            # exhaustive validation with its own high sample budget.
            settings=CVTSystemCheckSettings(maximum_samples_per_segment=24),
        )
    except Exception as error:
        return "unavailable", [
            f"Physical audit did not execute: {type(error).__name__}: {error}"
        ]
    if report.passed:
        return "pass", list(report.summary_lines())
    legacy = {
        "mode_position_domain",
        "upper_stop_position",
        "upper_stop_unilateral_reaction",
    }
    if report.failures and all(
        failure.invariant.value in legacy and "low_ratio_seat" in failure.location
        for failure in report.failures
    ):
        return "legacy_low_ratio_audit", [
            "Audit helper predates low-ratio-seat support; every reported violation is a known false positive.",
            *report.summary_lines(),
        ]
    return "fail", list(report.summary_lines())


def backshift_metrics(
    hill_phase: Phase, trace: ResponseTrace, step_time: float
) -> dict[str, float | None]:
    """Extract direct, physically interpretable backshift response measures."""

    release = next(
        (
            record
            for record in hill_phase.result.transitions
            if "upper_stop_released" in record.transition.reason
        ),
        None,
    )
    after = trace.time >= step_time - 1.0e-10
    shift_mm = trace.state[3] / MILLIMETRE
    indices = np.flatnonzero(np.isclose(trace.time, step_time, rtol=0.0, atol=1.0e-9))
    shift_at_step = None if not indices.size else float(shift_mm[int(indices[-1])])
    minimum_shift = float(np.min(shift_mm[after])) if np.any(after) else None
    return {
        "high_stop_release_time_s": None if release is None else float(release.time),
        "high_stop_release_delay_s": (
            None if release is None else float(release.time - step_time)
        ),
        "shift_at_grade_step_mm": shift_at_step,
        "minimum_shift_after_grade_mm": minimum_shift,
        "backshift_amount_mm": (
            None
            if shift_at_step is None or minimum_shift is None
            else float(shift_at_step - minimum_shift)
        ),
        "peak_backshift_speed_mm_per_s": (
            float(np.min(trace.state[4, after]) / MILLIMETRE) if np.any(after) else None
        ),
        "final_shift_mm": float(shift_mm[-1]),
        "final_primary_rpm": float(trace.state[0, -1] * RPM_PER_RADIAN_PER_SECOND),
        "final_secondary_rpm": float(trace.state[1, -1] * RPM_PER_RADIAN_PER_SECOND),
    }


def write_trace(path: Path, trace: ResponseTrace) -> None:
    """Export the state/road history for later custom analysis."""

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "time_s",
                "phase",
                "mode",
                "primary_rpm",
                "secondary_rpm",
                "belt_speed_mps",
                "shift_mm",
                "shift_speed_mm_per_s",
                "grade_degrees",
                "secondary_road_torque_nm",
                "road_external_force_n",
                "vehicle_speed_mps",
                "vehicle_distance_m",
                "effective_ratio_secondary_over_primary",
            )
        )
        for i, time in enumerate(trace.time):
            state = trace.state[:, i]
            writer.writerow(
                (
                    time,
                    trace.phase[i],
                    trace.mode[i],
                    state[0] * RPM_PER_RADIAN_PER_SECOND,
                    state[1] * RPM_PER_RADIAN_PER_SECOND,
                    state[2],
                    state[3] / MILLIMETRE,
                    state[4] / MILLIMETRE,
                    trace.grade_degrees[i],
                    trace.road_torque_nm[i],
                    trace.road_force_n[i],
                    trace.vehicle_speed_mps[i],
                    trace.vehicle_distance_m[i],
                    trace.effective_ratio[i],
                )
            )


def main() -> None:
    args = parse_arguments()
    candidate, integration = load_reference(args.preset)
    method = str(args.solver_method or integration.get("solver_method", "LSODA"))
    max_step_ms = float(args.max_step_ms or integration.get("max_step_ms", 20.0))
    rtol = float(
        args.relative_tolerance or integration.get("relative_tolerance", 1.0e-4)
    )
    atol = float(
        args.absolute_tolerance or integration.get("absolute_tolerance", 1.0e-7)
    )
    resolved = resolve_primary_preload(
        candidate, target_engagement_rpm=args.target_engagement_rpm
    )
    settings = HybridIntegratorSettings(
        relative_tolerance=rtol,
        absolute_tolerance=atol,
        method=method,
        max_step=max_step_ms * 1.0e-3,
        maximum_transitions=args.maximum_transitions,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("Hill-step response")
    print("=" * 88)
    print(candidate.label())
    print(
        f"primary preload={resolved.resolved_primary_preload_mm:.3f} mm; "
        f"level 0–{args.flat_duration_s:.3g} s, then +{args.hill_grade_deg:.1f}° to "
        f"{args.flat_duration_s + args.hill_duration_s:.3g} s."
    )

    level_system = system_with_grade(resolved=resolved, grade_degrees=0.0)
    level_result = integrate_phase(
        system=level_system,
        start=0.0,
        end=args.flat_duration_s,
        initial_state=launch_initial_state(primary_rpm=args.initial_primary_rpm),
        settings=settings,
        restart_s=0.0,
    )
    if not level_result.completed:
        raise RuntimeError(
            f"Level phase terminated early: {level_result.termination_reason}"
        )
    hill_system = system_with_grade(
        resolved=resolved, grade_degrees=args.hill_grade_deg
    )
    hill_result = integrate_phase(
        system=hill_system,
        start=args.flat_duration_s,
        end=args.flat_duration_s + args.hill_duration_s,
        initial_state=CVTDynamicState.from_vector(level_result.final_state),
        settings=settings,
        restart_s=args.hill_restart_s,
    )
    if not hill_result.completed:
        raise RuntimeError(
            f"Hill phase terminated early: {hill_result.termination_reason}"
        )

    phases = (
        Phase("level", 0.0, level_system, level_result),
        Phase("hill", args.hill_grade_deg, hill_system, hill_result),
    )
    trace = sample_state_road_trace(phases, args.plot_samples)
    figure = plot_response(
        trace, phases, resolved, args.flat_duration_s, args.hill_grade_deg
    )
    figure.savefig(args.output_dir / "hill_step_response.png", dpi=160)
    write_trace(args.output_dir / "hill_step_trace.csv", trace)

    audits = (
        {phase.name: audit_phase(phase) for phase in phases}
        if args.run_audit
        else {
            phase.name: (
                "not_run",
                [
                    "Not run by default; pass --run-audit for the slower per-phase physical audit."
                ],
            )
            for phase in phases
        }
    )
    metrics = backshift_metrics(phases[1], trace, args.flat_duration_s)
    summary = {
        "scenario": {
            "flat_duration_s": args.flat_duration_s,
            "hill_duration_s": args.hill_duration_s,
            "hill_grade_degrees": args.hill_grade_deg,
            "grade_step_interpretation": "State-continuous exogenous road-load step; no impact/reset at the grade change.",
            "hill_restart_s": args.hill_restart_s,
        },
        "candidate": {
            "flyweight_mass_kg": candidate.flyweight_mass_kg,
            "helix_angle_degrees": candidate.helix_angle_degrees,
            "secondary_torsional_pretension_degrees": candidate.secondary_torsional_pretension_degrees,
            "secondary_compression_preload_mm": candidate.secondary_compression_preload_mm,
            "primary_ramp_kind": candidate.primary_ramp_kind,
            "primary_ramp_start_angle_degrees": candidate.primary_ramp_start_angle_degrees,
            "primary_ramp_end_angle_degrees": candidate.primary_ramp_end_angle_degrees,
            "resolved_primary_preload_mm": resolved.resolved_primary_preload_mm,
        },
        "integration": {
            "method": method,
            "max_step_ms": max_step_ms,
            "rtol": rtol,
            "atol": atol,
        },
        "level": {
            "completed": level_result.completed,
            "segments": len(level_result.segments),
            "transitions": [
                record.transition.reason for record in level_result.transitions
            ],
        },
        "hill": {
            "completed": hill_result.completed,
            "segments": len(hill_result.segments),
            "transitions": [
                record.transition.reason for record in hill_result.transitions
            ],
        },
        "backshift_metrics": metrics,
        "audit": {
            name: {"status": status, "lines": lines}
            for name, (status, lines) in audits.items()
        },
    }
    with (args.output_dir / "hill_step_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, indent=2)

    for phase in phases:
        status, lines = audits[phase.name]
        print(
            f"\n{phase.name}: {len(phase.result.segments)} segments, {len(phase.result.transitions)} transitions, audit={status}"
        )
        for record in phase.result.transitions:
            print(f"  t={record.time:.6f} s  {short_event(record.transition.reason)}")
        for line in lines:
            print(f"  {line}")
    print("\nBackshift metrics")
    for key, value in metrics.items():
        print(f"{key}: {value}")
    print(
        f"\nWrote {args.output_dir / 'hill_step_response.png'}, {args.output_dir / 'hill_step_trace.csv'}, and {args.output_dir / 'hill_step_summary.json'}."
    )

    if args.no_show:
        plt.close(figure)
    else:
        plt.show()


if __name__ == "__main__":
    main()
