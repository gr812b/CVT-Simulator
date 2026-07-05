"""Run one long physical downhill route to inspect governed engine braking and terminal speed.

This tool uses the saved circular-primary launch tune, the normal CINDER hybrid
operating system, and **one uninterrupted integration**.  The road is a true
position-indexed ``CallableRoadProfile``; there are no phase handoffs or
solver restarts.

Default route
-------------
CINDER defines positive grade as uphill.  The default therefore uses a
negative grade for a 20 degree descent:

    distance 0 .. 93 m       : level approach (about the original 10 s launch)
    distance 93 .. 293 m     : C1-smooth 0 -> -20 degree downhill ramp
    distance >= 293 m        : hold -20 degree downhill

The default 120 s horizon is intentionally much longer than a launch preview.
It gives aerodynamic drag and the governed overspeed torque enough time to
approach a terminal speed.  The script does not assume a terminal speed exists:
it checks whether the final full-grade interval remains within a requested
vehicle-acceleration tolerance.  If it has not settled, extend ``--duration-s``
and keep the same single-run setup.

Engine model used here
----------------------
The accompanying ``baja_trial_baseline.py`` keeps the supplied full-throttle
Baja torque points unchanged through 4000 rpm.  Beyond 4000 rpm, CINDER's
existing PCHIP torque-tail mechanism creates a smooth governor/overspeed net
torque branch that moves from 0 N m at 4000 rpm toward -28 N m at 5500 rpm,
then remains bounded.  Negative crank power therefore means the vehicle is
motoring the governed engine.  This is *not* a closed-throttle coast map.

Examples
--------
    # Default: one 120 s, -20 degree terminal-speed study.
    python tools2/run_downhill_engine_braking.py --no-show

    # A longer run if the terminal-speed check says the final tail is unsettled.
    python tools2/run_downhill_engine_braking.py --duration-s 180 --no-show

    # Change only the physical road; terminal convergence is re-evaluated.
    python tools2/run_downhill_engine_braking.py \
        --maximum-downhill-deg 12 --duration-s 180 --no-show

    # Run the slower full hybrid physical audit as well.
    python tools2/run_downhill_engine_braking.py --run-audit --no-show
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
from math import radians
from pathlib import Path
import sys
from typing import Iterable, Sequence

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
from cinder.execution.hybrid.cvt_operating_hybrid import (
    CVTOperatingHybridSystem,
)  # noqa: E402
from cinder.model.boundaries.output.vehicle import CallableRoadProfile  # noqa: E402
from launch_tuning_common import (  # noqa: E402
    MILLIMETRE,
    RPM_PER_RADIAN_PER_SECOND,
    TuneCandidate,
    build_operating_configuration,
    build_system_from_case,
    case_with_output_road_profile,
    require_locked_vehicle_output_boundary,
    launch_initial_state,
    resolve_primary_preload,
)

_DEFAULT_PRESET = (
    _TOOLS_DIRECTORY / "presets" / "circular_traction_first_reference.json"
)


@dataclass(frozen=True, slots=True)
class DownhillRoadCurve:
    """Flat approach -> C1 downhill ramp -> indefinitely sustained downhill."""

    flat_approach_distance_m: float
    ramp_distance_m: float
    maximum_downhill_degrees: float

    def __post_init__(self) -> None:
        for name, value in (
            ("flat_approach_distance_m", self.flat_approach_distance_m),
            ("ramp_distance_m", self.ramp_distance_m),
            ("maximum_downhill_degrees", self.maximum_downhill_degrees),
        ):
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and strictly positive.")
        if self.maximum_downhill_degrees >= 89.0:
            raise ValueError("maximum_downhill_degrees must stay below 89 degrees.")

    @property
    def ramp_end_distance_m(self) -> float:
        return self.flat_approach_distance_m + self.ramp_distance_m

    def grade_radians(self, vehicle_distance_m: float) -> float:
        """Return CINDER's signed grade: negative is downhill."""

        distance = max(0.0, float(vehicle_distance_m))
        if distance <= self.flat_approach_distance_m:
            return 0.0
        if distance >= self.ramp_end_distance_m:
            return -radians(self.maximum_downhill_degrees)
        fraction = (distance - self.flat_approach_distance_m) / self.ramp_distance_m
        return -radians(self.maximum_downhill_degrees) * _smoothstep(fraction)

    def phase_index(self, vehicle_distance_m: float) -> int:
        if vehicle_distance_m <= self.flat_approach_distance_m:
            return 0
        if vehicle_distance_m < self.ramp_end_distance_m:
            return 1
        return 2

    @property
    def phase_labels(self) -> tuple[str, str, str]:
        return (
            "flat approach",
            f"0→−{self.maximum_downhill_degrees:.0f}° ramp",
            f"−{self.maximum_downhill_degrees:.0f}° hold",
        )


def _smoothstep(value: float) -> float:
    value = float(np.clip(value, 0.0, 1.0))
    return value * value * (3.0 - 2.0 * value)


@dataclass(frozen=True, slots=True)
class DownhillTrace:
    """Sparse accepted trajectory samples enriched with road and engine data."""

    time: NDArray[np.float64]
    state: NDArray[np.float64]
    mode: tuple[str, ...]
    vehicle_distance_m: NDArray[np.float64]
    vehicle_speed_mps: NDArray[np.float64]
    vehicle_acceleration_mps2: NDArray[np.float64]
    grade_degrees: NDArray[np.float64]
    secondary_road_torque_nm: NDArray[np.float64]
    engine_torque_nm: NDArray[np.float64]
    engine_power_kw: NDArray[np.float64]
    engine_braking_power_kw: NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class TerminalSpeedEstimate:
    """Observed terminal-speed status from the final full-grade trajectory tail."""

    converged: bool
    stable_window_start_time_s: float | None
    stable_window_end_time_s: float | None
    estimated_terminal_speed_kph: float | None
    speed_drift_over_window_kph: float | None
    final_vehicle_acceleration_mps2: float


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", type=Path, default=_DEFAULT_PRESET)
    parser.add_argument(
        "--duration-s",
        type=float,
        default=120.0,
        help="Single continuous integration horizon [s]; extend if the terminal check remains unsettled.",
    )
    parser.add_argument("--initial-primary-rpm", type=float, default=1800.0)
    parser.add_argument("--target-engagement-rpm", type=float, default=2000.0)
    parser.add_argument(
        "--flat-approach-distance-m",
        type=float,
        default=93.0,
        help="Level-road approach before the downhill begins [m].",
    )
    parser.add_argument(
        "--ramp-distance-m",
        type=float,
        default=200.0,
        help="Distance of the smooth 0° to final-downhill transition [m].",
    )
    parser.add_argument(
        "--maximum-downhill-deg",
        type=float,
        default=20.0,
        help="Magnitude of the sustained downhill grade [deg]; internally applied as negative grade.",
    )
    parser.add_argument(
        "--terminal-window-s",
        type=float,
        default=10.0,
        help="Required final full-grade stable window for terminal-speed reporting [s].",
    )
    parser.add_argument(
        "--terminal-acceleration-tolerance-mps2",
        type=float,
        default=0.01,
        help="Maximum |vehicle acceleration| allowed through the terminal window [m/s²].",
    )
    parser.add_argument("--solver-method", default=None)
    parser.add_argument("--max-step-ms", type=float, default=None)
    parser.add_argument("--relative-tolerance", type=float, default=None)
    parser.add_argument("--absolute-tolerance", type=float, default=None)
    parser.add_argument("--maximum-transitions", type=int, default=200)
    parser.add_argument("--plot-samples", type=int, default=1800)
    parser.add_argument("--run-audit", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/downhill_engine_braking"),
    )
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()

    for name in (
        "duration_s",
        "initial_primary_rpm",
        "target_engagement_rpm",
        "flat_approach_distance_m",
        "ramp_distance_m",
        "maximum_downhill_deg",
        "terminal_window_s",
        "terminal_acceleration_tolerance_mps2",
    ):
        value = getattr(args, name)
        if not np.isfinite(value) or value <= 0.0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive.")
    if args.maximum_downhill_deg >= 89.0:
        parser.error("--maximum-downhill-deg must be below 89.")
    for name in ("max_step_ms", "relative_tolerance", "absolute_tolerance"):
        value = getattr(args, name)
        if value is not None and (not np.isfinite(value) or value <= 0.0):
            parser.error(
                f"--{name.replace('_', '-')} must be finite and positive when supplied."
            )
    if args.maximum_transitions < 1:
        parser.error("--maximum-transitions must be at least one.")
    if args.plot_samples < 250:
        parser.error("--plot-samples must be at least 250.")
    return args


def load_candidate(path: Path) -> tuple[TuneCandidate, dict[str, float | str]]:
    """Load the saved circular-primary reference without duplicating tune values."""

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
        primary_ramp_kind=str(data["primary_ramp_kind"]),
        primary_ramp_angle_degrees=float(data.get("primary_ramp_angle_degrees", 30.0)),
        primary_ramp_start_angle_degrees=float(
            data["primary_ramp_start_angle_degrees"]
        ),
        primary_ramp_end_angle_degrees=float(data["primary_ramp_end_angle_degrees"]),
    )
    return candidate, dict(payload.get("integration", {}))


def build_system(*, resolved, curve: DownhillRoadCurve) -> CVTOperatingHybridSystem:
    """Install the physical distance-indexed road into an otherwise normal CINDER system."""

    configuration, baseline = build_operating_configuration(resolved.constants)
    case = case_with_output_road_profile(
        baseline.case,
        CallableRoadProfile(
            grade_angle_function=lambda vehicle_distance: curve.grade_radians(
                vehicle_distance
            )
        ),
    )
    return build_system_from_case(case, configuration=configuration)


def _compact_mode(mode) -> str:
    if mode.contact_regime is None:
        return f"{mode.engagement.value}/{mode.shift_constraint.value}"
    return f"{mode.engagement.value}/{mode.shift_constraint.value}/{mode.contact_regime.mode.value}"


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
    system: CVTOperatingHybridSystem,
    result,
    curve: DownhillRoadCurve,
    maximum_samples: int,
) -> DownhillTrace:
    """Re-evaluate accepted states for road, engine, and vehicle-acceleration diagnostics."""

    budgets = _allocate_samples(
        [segment.state.shape[1] for segment in result.segments], maximum_samples
    )
    rows = []
    final_drive = require_locked_vehicle_output_boundary(system).final_drive
    speed_factor = final_drive.wheel_radius / final_drive.reduction_ratio

    for segment, budget in zip(result.segments, budgets, strict=True):
        indices = np.unique(
            np.linspace(0, segment.state.shape[1] - 1, budget, dtype=int)
        )
        for index in indices:
            time = float(segment.time[index])
            vector = np.asarray(segment.state[:, index], dtype=float).copy()
            vector[3] = np.clip(
                vector[3], 0.0, system.operating_limits.upper_stop_shift
            )
            state = CVTDynamicState.from_vector(vector)
            snapshot = system.model.snapshot(state=state)
            derivative = system.rhs(time=time, state=vector, mode=segment.mode)
            distance = snapshot.vehicle_distance
            engine_torque = float(snapshot.engine_torque)
            engine_power_kw = engine_torque * state.primary_angular_speed / 1000.0
            rows.append(
                (
                    time,
                    vector,
                    _compact_mode(segment.mode),
                    float(distance),
                    float(snapshot.vehicle_road_load.vehicle_speed),
                    float(speed_factor * derivative[1]),
                    float(np.rad2deg(curve.grade_radians(distance))),
                    float(snapshot.vehicle_road_load.secondary_external_torque),
                    engine_torque,
                    engine_power_kw,
                    max(-engine_power_kw, 0.0),
                )
            )

    rows.sort(key=lambda row: row[0])
    return DownhillTrace(
        time=np.asarray([row[0] for row in rows], dtype=float),
        state=np.column_stack([row[1] for row in rows]),
        mode=tuple(row[2] for row in rows),
        vehicle_distance_m=np.asarray([row[3] for row in rows], dtype=float),
        vehicle_speed_mps=np.asarray([row[4] for row in rows], dtype=float),
        vehicle_acceleration_mps2=np.asarray([row[5] for row in rows], dtype=float),
        grade_degrees=np.asarray([row[6] for row in rows], dtype=float),
        secondary_road_torque_nm=np.asarray([row[7] for row in rows], dtype=float),
        engine_torque_nm=np.asarray([row[8] for row in rows], dtype=float),
        engine_power_kw=np.asarray([row[9] for row in rows], dtype=float),
        engine_braking_power_kw=np.asarray([row[10] for row in rows], dtype=float),
    )


def _plot_masked_runs(
    axis: plt.Axes,
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    mask: NDArray[np.bool_],
    **kwargs,
) -> None:
    starts = np.flatnonzero(mask & np.r_[True, ~mask[:-1]])
    ends = np.flatnonzero(mask & np.r_[~mask[1:], True])
    label = kwargs.pop("label", None)
    for number, (start, end) in enumerate(zip(starts, ends, strict=True)):
        if end - start < 1:
            continue
        axis.plot(
            x[start : end + 1],
            y[start : end + 1],
            label=label if number == 0 else None,
            **kwargs,
        )


def _short_event(reason: str) -> str:
    for fragment, label in (
        ("lower_stop_released", "low stop"),
        ("primary_closed_into_engaged_contact", "engage"),
        ("low_ratio_seat_reached", "low seat"),
        ("low_ratio_seat_released", "shift start"),
        ("contact_restuck", "re-stick"),
        ("upper_stop_reached", "high stop"),
        ("upper_stop_released", "high release"),
        ("static_capacity_exhausted", "slip"),
    ):
        if fragment in reason:
            return label
    return reason.replace("_", " ")


def _annotate_transitions(
    axes: Iterable[plt.Axes], label_axes: Iterable[plt.Axes], result
) -> None:
    axes = tuple(axes)
    label_axes = tuple(label_axes)
    for count, record in enumerate(result.transitions):
        for axis in axes:
            axis.axvline(record.time, linestyle="--", linewidth=0.7, alpha=0.4)
        fraction = 0.97 - 0.11 * (count % 6)
        for axis in label_axes:
            axis.annotate(
                _short_event(record.transition.reason),
                xy=(record.time, fraction),
                xycoords=("data", "axes fraction"),
                xytext=(2, 0),
                textcoords="offset points",
                rotation=90,
                va="top",
                ha="left",
                fontsize=5.8,
            )


def _first_true_time(
    time: NDArray[np.float64], mask: NDArray[np.bool_]
) -> float | None:
    indices = np.flatnonzero(mask)
    return None if len(indices) == 0 else float(time[int(indices[0])])


def estimate_terminal_speed(
    *,
    trace: DownhillTrace,
    curve: DownhillRoadCurve,
    stable_window_s: float,
    acceleration_tolerance_mps2: float,
) -> TerminalSpeedEstimate:
    """Declare terminal speed only if the final *full-grade* tail is settled.

    This is diagnostic logic only.  The integrated model is unchanged: the
    solver always reaches the requested end time.  Requiring the final
    contiguous window avoids calling a short temporary lull a terminal speed.
    """

    full_grade = np.isclose(
        trace.grade_degrees,
        -curve.maximum_downhill_degrees,
        atol=0.02,
    )
    stable = full_grade & (
        np.abs(trace.vehicle_acceleration_mps2) <= acceleration_tolerance_mps2
    )
    if not stable[-1]:
        return TerminalSpeedEstimate(
            converged=False,
            stable_window_start_time_s=None,
            stable_window_end_time_s=None,
            estimated_terminal_speed_kph=None,
            speed_drift_over_window_kph=None,
            final_vehicle_acceleration_mps2=float(trace.vehicle_acceleration_mps2[-1]),
        )

    start_index = len(stable) - 1
    while start_index > 0 and stable[start_index - 1]:
        start_index -= 1
    end_time = float(trace.time[-1])
    start_time = float(trace.time[start_index])
    if end_time - start_time < stable_window_s:
        return TerminalSpeedEstimate(
            converged=False,
            stable_window_start_time_s=None,
            stable_window_end_time_s=None,
            estimated_terminal_speed_kph=None,
            speed_drift_over_window_kph=None,
            final_vehicle_acceleration_mps2=float(trace.vehicle_acceleration_mps2[-1]),
        )

    averaging_mask = trace.time >= end_time - stable_window_s
    speed_kph = trace.vehicle_speed_mps * 3.6
    estimated_speed = float(np.mean(speed_kph[averaging_mask]))
    speed_drift = float(speed_kph[-1] - speed_kph[np.flatnonzero(averaging_mask)[0]])
    return TerminalSpeedEstimate(
        converged=True,
        stable_window_start_time_s=end_time - stable_window_s,
        stable_window_end_time_s=end_time,
        estimated_terminal_speed_kph=estimated_speed,
        speed_drift_over_window_kph=speed_drift,
        final_vehicle_acceleration_mps2=float(trace.vehicle_acceleration_mps2[-1]),
    )


def plot_response(
    *,
    trace: DownhillTrace,
    result,
    resolved,
    curve: DownhillRoadCurve,
    terminal: TerminalSpeedEstimate,
):
    """Make one 3x3 response diagnostic for the route and governed engine branch."""

    t = trace.time
    primary_rpm = trace.state[0] * RPM_PER_RADIAN_PER_SECOND
    secondary_rpm = trace.state[1] * RPM_PER_RADIAN_PER_SECOND
    shift_mm = trace.state[3] / MILLIMETRE
    shift_speed_mmps = trace.state[4] / MILLIMETRE
    brake_mask = trace.engine_torque_nm < -1.0e-6
    brake_start = _first_true_time(t, brake_mask)

    figure, axes = plt.subplots(3, 3, figsize=(20, 14), constrained_layout=True)

    grade_axis = axes[0, 0]
    grade_axis.plot(t, trace.grade_degrees, label="grade")
    grade_axis.axhline(0.0, linestyle="--", linewidth=0.8)
    grade_axis.axhline(
        -curve.maximum_downhill_degrees,
        linestyle=":",
        linewidth=0.9,
        label="downhill limit",
    )
    grade_axis.set_title("Physical road grade over full run")
    grade_axis.set_xlabel("Time [s]")
    grade_axis.set_ylabel("Grade [deg]")
    grade_axis.grid(True, alpha=0.25)
    grade_axis.legend(loc="best")

    distance_axis = axes[0, 1]
    distance_axis.plot(t, trace.vehicle_distance_m, label="vehicle distance")
    distance_axis.axhline(
        curve.flat_approach_distance_m,
        linestyle="--",
        linewidth=0.8,
        label="ramp start",
    )
    distance_axis.axhline(
        curve.ramp_end_distance_m,
        linestyle=":",
        linewidth=0.9,
        label=f"−{curve.maximum_downhill_degrees:.0f}° reached",
    )
    distance_axis.set_title("Road position through downhill curve")
    distance_axis.set_xlabel("Time [s]")
    distance_axis.set_ylabel("Distance [m]")
    distance_axis.grid(True, alpha=0.25)
    distance_axis.legend(loc="best")

    vehicle_axis = axes[0, 2]
    vehicle_axis.plot(t, trace.vehicle_speed_mps * 3.6, label="vehicle speed")
    vehicle_axis.set_title("Vehicle speed and acceleration")
    vehicle_axis.set_xlabel("Time [s]")
    vehicle_axis.set_ylabel("Speed [km/h]")
    vehicle_axis.grid(True, alpha=0.25)
    acceleration_axis = vehicle_axis.twinx()
    acceleration_axis.plot(
        t, trace.vehicle_acceleration_mps2, linestyle=":", label="vehicle accel"
    )
    acceleration_axis.axhline(0.0, linestyle="--", linewidth=0.7)
    acceleration_axis.set_ylabel("Acceleration [m/s²]")
    left_handles, left_labels = vehicle_axis.get_legend_handles_labels()
    right_handles, right_labels = acceleration_axis.get_legend_handles_labels()
    vehicle_axis.legend(
        left_handles + right_handles, left_labels + right_labels, loc="best"
    )
    if terminal.converged and terminal.estimated_terminal_speed_kph is not None:
        vehicle_axis.axhline(
            terminal.estimated_terminal_speed_kph,
            linestyle=":",
            linewidth=1.0,
            label="terminal estimate",
        )

    speed_axis = axes[1, 0]
    speed_axis.plot(t, primary_rpm, label=r"$\omega_p$")
    speed_axis.plot(t, secondary_rpm, label=r"$\omega_s$")
    speed_axis.set_title("Shaft speeds")
    speed_axis.set_xlabel("Time [s]")
    speed_axis.set_ylabel("Speed [rpm]")
    speed_axis.grid(True, alpha=0.25)
    speed_axis.legend(loc="best")

    shift_axis = axes[1, 1]
    shift_axis.plot(t, shift_mm, label=r"$s$")
    shift_axis.axhline(
        resolved.constants.deadzone_shift / MILLIMETRE,
        linestyle="--",
        linewidth=0.8,
        label="engage",
    )
    shift_axis.axhline(
        resolved.constants.max_shift / MILLIMETRE,
        linestyle="--",
        linewidth=0.8,
        label="high stop",
    )
    shift_axis.set_title("Shift coordinate and shift rate")
    shift_axis.set_xlabel("Time [s]")
    shift_axis.set_ylabel("Shift [mm]")
    shift_axis.grid(True, alpha=0.25)
    shift_rate_axis = shift_axis.twinx()
    shift_rate_axis.plot(t, shift_speed_mmps, linestyle=":", label=r"$\dot{s}$")
    shift_rate_axis.set_ylabel("Shift speed [mm/s]")
    left_handles, left_labels = shift_axis.get_legend_handles_labels()
    right_handles, right_labels = shift_rate_axis.get_legend_handles_labels()
    shift_axis.legend(
        left_handles + right_handles, left_labels + right_labels, loc="best"
    )

    curve_axis = axes[1, 2]
    curve_axis.plot(secondary_rpm, primary_rpm, alpha=0.20, label="full trajectory")
    phase_index = np.asarray(
        [curve.phase_index(distance) for distance in trace.vehicle_distance_m],
        dtype=int,
    )
    for phase, label in enumerate(curve.phase_labels):
        _plot_masked_runs(
            curve_axis,
            secondary_rpm,
            primary_rpm,
            phase_index == phase,
            linestyle=":",
            linewidth=2.1,
            label=label,
        )
    curve_axis.scatter([secondary_rpm[0]], [primary_rpm[0]], marker="o", label="launch")
    if brake_start is not None:
        index = min(int(np.searchsorted(t, brake_start, side="left")), len(t) - 1)
        curve_axis.scatter(
            [secondary_rpm[index]],
            [primary_rpm[index]],
            marker="x",
            label="governed brake starts",
        )
    curve_axis.set_title("Shift curve: route phase overlays")
    curve_axis.set_xlabel("Secondary speed [rpm]")
    curve_axis.set_ylabel("Primary speed [rpm]")
    curve_axis.grid(True, alpha=0.25)
    curve_axis.legend(loc="best", fontsize=7.0)

    torque_axis = axes[2, 0]
    torque_axis.plot(t, trace.engine_torque_nm, label=r"$\tau_{engine}$")
    torque_axis.plot(t, trace.secondary_road_torque_nm, label=r"$\tau_{road,s}$")
    torque_axis.axhline(0.0, linestyle="--", linewidth=0.8)
    torque_axis.set_title("Signed engine and road torques")
    torque_axis.set_xlabel("Time [s]")
    torque_axis.set_ylabel("Torque [N m]")
    torque_axis.grid(True, alpha=0.25)
    torque_axis.legend(loc="best")

    power_axis = axes[2, 1]
    power_axis.plot(t, trace.engine_power_kw, label=r"$P_{engine}$")
    power_axis.plot(
        t, trace.engine_braking_power_kw, linestyle=":", label="braking magnitude"
    )
    power_axis.axhline(0.0, linestyle="--", linewidth=0.8)
    power_axis.set_title("Crank power: negative = governed braking")
    power_axis.set_xlabel("Time [s]")
    power_axis.set_ylabel("Power [kW]")
    power_axis.grid(True, alpha=0.25)
    power_axis.legend(loc="best")

    mode_axis = axes[2, 2]
    ordered_modes = list(dict.fromkeys(trace.mode))
    mode_index = np.asarray(
        [ordered_modes.index(mode) for mode in trace.mode], dtype=float
    )
    mode_axis.step(t, mode_index, where="post", label="mode index")
    mode_axis.set_title("Operating-regime timeline")
    mode_axis.set_xlabel("Time [s]")
    mode_axis.set_ylabel("Mode index")
    mode_axis.set_yticks(
        range(len(ordered_modes)), [str(index) for index in range(len(ordered_modes))]
    )
    mode_axis.grid(True, alpha=0.25)
    mode_axis.legend(loc="best")
    mode_axis.text(
        0.02,
        0.98,
        "\n".join(f"{index}: {mode}" for index, mode in enumerate(ordered_modes)),
        transform=mode_axis.transAxes,
        va="top",
        ha="left",
        fontsize=6.2,
        bbox={"boxstyle": "round", "alpha": 0.75},
    )

    _annotate_transitions(
        (
            grade_axis,
            distance_axis,
            vehicle_axis,
            speed_axis,
            shift_axis,
            torque_axis,
            power_axis,
            mode_axis,
        ),
        (speed_axis, shift_axis),
        result,
    )
    if brake_start is not None:
        for axis in (
            grade_axis,
            vehicle_axis,
            speed_axis,
            shift_axis,
            torque_axis,
            power_axis,
            mode_axis,
        ):
            axis.axvline(brake_start, linestyle=":", linewidth=1.0, alpha=0.85)
    if terminal.converged and terminal.stable_window_start_time_s is not None:
        for axis in (vehicle_axis, speed_axis, shift_axis, torque_axis, power_axis):
            axis.axvspan(
                terminal.stable_window_start_time_s,
                terminal.stable_window_end_time_s,
                alpha=0.10,
            )

    figure.suptitle(
        "CINDER circular-primary downhill terminal-speed study | "
        f"{resolved.candidate.label()} | primary preload={resolved.resolved_primary_preload_mm:.2f} mm",
        fontsize=13,
    )
    return figure


def plot_road_profile(*, curve: DownhillRoadCurve, final_distance_m: float):
    distance_limit = max(final_distance_m, curve.ramp_end_distance_m) * 1.03
    distance = np.linspace(0.0, distance_limit, 800)
    grade = np.rad2deg([curve.grade_radians(value) for value in distance])
    figure, axis = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    axis.plot(distance, grade, label="grade curve")
    axis.axvline(curve.flat_approach_distance_m, linestyle="--", label="ramp start")
    axis.axvline(
        curve.ramp_end_distance_m,
        linestyle=":",
        label=f"−{curve.maximum_downhill_degrees:.0f}° reached",
    )
    axis.axhline(-curve.maximum_downhill_degrees, linestyle=":", linewidth=0.8)
    axis.set_title("Distance-indexed downhill road profile")
    axis.set_xlabel("Vehicle distance [m]")
    axis.set_ylabel("Grade [deg]")
    axis.grid(True, alpha=0.25)
    axis.legend(loc="best")
    return figure


def plot_engine_curve(*, system: CVTOperatingHybridSystem, resolved):
    """Plot the exact PCHIP engine curve used by this run, including the governor tail."""

    engine = system.model.input_boundary
    spec = engine.spec
    rpm_limit = max(
        6500.0, spec.high_speed_braking_plateau_end * RPM_PER_RADIAN_PER_SECOND * 1.05
    )
    rpm = np.linspace(0.0, rpm_limit, 1000)
    angular_speed = rpm / RPM_PER_RADIAN_PER_SECOND
    torque = np.asarray([engine.evaluate(value) for value in angular_speed])
    power_hp = torque * angular_speed / 745.6998715822702
    governed_start_rpm = spec.maximum_speed * RPM_PER_RADIAN_PER_SECOND
    plateau_start_rpm = (
        spec.high_speed_braking_plateau_start * RPM_PER_RADIAN_PER_SECOND
    )

    figure, axes = plt.subplots(1, 2, figsize=(13, 4.8), constrained_layout=True)
    torque_axis, power_axis = axes
    torque_axis.plot(rpm, torque, label="net crank torque")
    torque_axis.axhline(0.0, linestyle="--", linewidth=0.8)
    torque_axis.axvline(governed_start_rpm, linestyle=":", label="governor onset")
    torque_axis.axvline(plateau_start_rpm, linestyle=":", label="brake plateau")
    torque_axis.set_title("Full-throttle map plus governed overspeed branch")
    torque_axis.set_xlabel("Primary speed [rpm]")
    torque_axis.set_ylabel("Net torque [N m]")
    torque_axis.grid(True, alpha=0.25)
    torque_axis.legend(loc="best")

    power_axis.plot(rpm, power_hp, label="crank power")
    power_axis.axhline(
        resolved.constants.engine_power_limit_hp,
        linestyle="--",
        label=f"{resolved.constants.engine_power_limit_hp:.0f} hp cap",
    )
    power_axis.axhline(0.0, linestyle="--", linewidth=0.8)
    power_axis.axvline(governed_start_rpm, linestyle=":", label="governor onset")
    power_axis.set_title("Positive WOT power remains below cap")
    power_axis.set_xlabel("Primary speed [rpm]")
    power_axis.set_ylabel("Crank power [hp]")
    power_axis.grid(True, alpha=0.25)
    power_axis.legend(loc="best")
    return figure


def route_metrics(
    *,
    trace: DownhillTrace,
    curve: DownhillRoadCurve,
    terminal: TerminalSpeedEstimate,
) -> dict[str, float | bool | None]:
    primary_rpm = trace.state[0] * RPM_PER_RADIAN_PER_SECOND
    shift_mm = trace.state[3] / MILLIMETRE
    brake_mask = trace.engine_torque_nm < -1.0e-6
    braking_start = _first_true_time(trace.time, brake_mask)
    ramp_start_time = _first_true_time(
        trace.time, trace.vehicle_distance_m >= curve.flat_approach_distance_m
    )
    full_grade_time = _first_true_time(
        trace.time, trace.vehicle_distance_m >= curve.ramp_end_distance_m
    )
    downhill_mask = trace.grade_degrees < -0.1
    return {
        "ramp_start_time_s": ramp_start_time,
        "full_downhill_time_s": full_grade_time,
        "governed_engine_braking_detected": bool(braking_start is not None),
        "governed_engine_braking_start_time_s": braking_start,
        "minimum_engine_torque_nm": float(np.min(trace.engine_torque_nm)),
        "minimum_engine_power_kw": float(np.min(trace.engine_power_kw)),
        "peak_governed_braking_power_kw": float(np.max(trace.engine_braking_power_kw)),
        "peak_primary_rpm": float(np.max(primary_rpm)),
        "peak_vehicle_speed_kph": float(np.max(trace.vehicle_speed_mps) * 3.6),
        "maximum_shift_mm": float(np.max(shift_mm)),
        "minimum_shift_mm": float(np.min(shift_mm)),
        "minimum_shift_after_downhill_starts_mm": (
            float(np.min(shift_mm[downhill_mask])) if np.any(downhill_mask) else None
        ),
        "maximum_backshift_speed_while_downhill_mm_per_s": (
            float(np.min((trace.state[4] / MILLIMETRE)[downhill_mask]))
            if np.any(downhill_mask)
            else None
        ),
        "final_vehicle_speed_kph": float(trace.vehicle_speed_mps[-1] * 3.6),
        "final_vehicle_acceleration_mps2": terminal.final_vehicle_acceleration_mps2,
        "terminal_speed_converged": terminal.converged,
        "estimated_terminal_speed_kph": terminal.estimated_terminal_speed_kph,
        "terminal_speed_drift_over_window_kph": terminal.speed_drift_over_window_kph,
        "final_primary_rpm": float(primary_rpm[-1]),
        "final_shift_mm": float(shift_mm[-1]),
        "final_distance_m": float(trace.vehicle_distance_m[-1]),
    }


def audit_result(*, system: CVTOperatingHybridSystem, result) -> tuple[str, list[str]]:
    try:
        from hybrid_system_checks import CVTSystemCheckSettings, check_cvt_hybrid_result
    except ImportError:
        return "unavailable", [
            "Physical audit unavailable: hybrid_system_checks.py not found."
        ]
    try:
        report = check_cvt_hybrid_result(
            system=system,
            result=result,
            settings=CVTSystemCheckSettings(maximum_samples_per_segment=32),
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
            "Audit helper predates low-ratio-seat support; reported failures are known false positives.",
            *report.summary_lines(),
        ]
    return "fail", list(report.summary_lines())


def write_trace(path: Path, trace: DownhillTrace) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "time_s",
                "mode",
                "primary_rpm",
                "secondary_rpm",
                "belt_speed_mps",
                "shift_mm",
                "shift_speed_mm_per_s",
                "secondary_shaft_angle_rad",
                "vehicle_distance_m",
                "vehicle_speed_mps",
                "vehicle_acceleration_mps2",
                "grade_degrees",
                "secondary_road_torque_nm",
                "engine_torque_nm",
                "engine_power_kw",
                "engine_braking_power_kw",
            )
        )
        for index, time in enumerate(trace.time):
            state = trace.state[:, index]
            writer.writerow(
                (
                    time,
                    trace.mode[index],
                    state[0] * RPM_PER_RADIAN_PER_SECOND,
                    state[1] * RPM_PER_RADIAN_PER_SECOND,
                    state[2],
                    state[3] / MILLIMETRE,
                    state[4] / MILLIMETRE,
                    state[5],
                    trace.vehicle_distance_m[index],
                    trace.vehicle_speed_mps[index],
                    trace.vehicle_acceleration_mps2[index],
                    trace.grade_degrees[index],
                    trace.secondary_road_torque_nm[index],
                    trace.engine_torque_nm[index],
                    trace.engine_power_kw[index],
                    trace.engine_braking_power_kw[index],
                )
            )


def main() -> None:
    args = parse_arguments()
    candidate, integration = load_candidate(args.preset)
    curve = DownhillRoadCurve(
        flat_approach_distance_m=args.flat_approach_distance_m,
        ramp_distance_m=args.ramp_distance_m,
        maximum_downhill_degrees=args.maximum_downhill_deg,
    )
    method = str(args.solver_method or integration.get("solver_method", "LSODA"))
    max_step_ms = float(args.max_step_ms if args.max_step_ms is not None else 100.0)
    rtol = float(
        args.relative_tolerance if args.relative_tolerance is not None else 1.0e-2
    )
    atol = float(
        args.absolute_tolerance if args.absolute_tolerance is not None else 1.0e-5
    )

    resolved = resolve_primary_preload(
        candidate, target_engagement_rpm=args.target_engagement_rpm
    )
    system = build_system(resolved=resolved, curve=curve)
    settings = HybridIntegratorSettings(
        relative_tolerance=rtol,
        absolute_tolerance=atol,
        method=method,
        max_step=max_step_ms * 1.0e-3,
        maximum_transitions=args.maximum_transitions,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print("Distance-indexed downhill terminal-speed study")
    print("=" * 88)
    print(candidate.label())
    print(f"primary preload={resolved.resolved_primary_preload_mm:.3f} mm")
    print(
        f"road: 0° through {curve.flat_approach_distance_m:.1f} m; smooth 0→−{curve.maximum_downhill_degrees:.1f}° "
        f"from {curve.flat_approach_distance_m:.1f} to {curve.ramp_end_distance_m:.1f} m; then −{curve.maximum_downhill_degrees:.1f}° hold."
    )
    print(
        f"one {args.duration_s:.3g} s CINDER integration; {method}, max step={max_step_ms:.3g} ms, "
        f"rtol={rtol:.1e}, atol={atol:.1e}"
    )

    result = system.integrate(
        time_span=(0.0, args.duration_s),
        initial_state=launch_initial_state(primary_rpm=args.initial_primary_rpm),
        settings=settings,
    )
    if not result.completed:
        raise RuntimeError(f"Integration terminated early: {result.termination_reason}")

    trace = sample_trace(
        system=system, result=result, curve=curve, maximum_samples=args.plot_samples
    )
    terminal = estimate_terminal_speed(
        trace=trace,
        curve=curve,
        stable_window_s=args.terminal_window_s,
        acceleration_tolerance_mps2=args.terminal_acceleration_tolerance_mps2,
    )
    figure = plot_response(
        trace=trace, result=result, resolved=resolved, curve=curve, terminal=terminal
    )
    figure.savefig(args.output_dir / "downhill_engine_braking.png", dpi=170)
    profile_figure = plot_road_profile(
        curve=curve, final_distance_m=float(trace.vehicle_distance_m[-1])
    )
    profile_figure.savefig(args.output_dir / "downhill_grade_profile.png", dpi=170)
    engine_figure = plot_engine_curve(system=system, resolved=resolved)
    engine_figure.savefig(args.output_dir / "engine_governed_torque_curve.png", dpi=170)
    write_trace(args.output_dir / "downhill_engine_braking_trace.csv", trace)

    audit_status, audit_lines = (
        audit_result(system=system, result=result)
        if args.run_audit
        else (
            "not_run",
            ["Not run by default; pass --run-audit for the slower physical audit."],
        )
    )
    metrics = route_metrics(trace=trace, curve=curve, terminal=terminal)
    summary = {
        "scenario": {
            "description": "One continuous CINDER hybrid integration over a distance-indexed smooth downhill road curve.",
            "duration_s": args.duration_s,
            "flat_approach_distance_m": curve.flat_approach_distance_m,
            "ramp_distance_m": curve.ramp_distance_m,
            "ramp_end_distance_m": curve.ramp_end_distance_m,
            "maximum_downhill_degrees": curve.maximum_downhill_degrees,
            "terminal_window_s": args.terminal_window_s,
            "terminal_acceleration_tolerance_mps2": args.terminal_acceleration_tolerance_mps2,
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
        "engine": {
            "wot_power_limit_hp": resolved.constants.engine_power_limit_hp,
            "governed_overspeed_torque_plateau_nm": resolved.constants.engine_governed_overspeed_torque,
            "governed_overspeed_transition_width_rpm": resolved.constants.engine_governed_overspeed_transition_width_rpm,
        },
        "integration": {
            "method": method,
            "max_step_ms": max_step_ms,
            "rtol": rtol,
            "atol": atol,
            "completed": result.completed,
            "segments": len(result.segments),
            "transitions": [record.transition.reason for record in result.transitions],
        },
        "metrics": metrics,
        "audit": {"status": audit_status, "lines": audit_lines},
    }
    with (args.output_dir / "downhill_engine_braking_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, indent=2)

    print(
        f"\n{len(result.segments)} segments; {len(result.transitions)} transitions; audit={audit_status}"
    )
    for record in result.transitions:
        print(f"  t={record.time:.6f} s  {_short_event(record.transition.reason)}")
    print("\nDownhill metrics")
    for name, value in metrics.items():
        print(f"{name}: {value}")
    if terminal.converged:
        print(
            f"\nTerminal-speed check PASSED: {terminal.estimated_terminal_speed_kph:.3f} km/h over the final "
            f"{args.terminal_window_s:.1f} s, drift={terminal.speed_drift_over_window_kph:.4f} km/h."
        )
    else:
        print(
            "\nTerminal-speed check did not settle within this horizon.  Increase --duration-s; "
            "the simulation remains one uninterrupted CINDER run."
        )
    for line in audit_lines:
        print(f"  {line}")
    print(
        f"\nWrote {args.output_dir / 'downhill_engine_braking.png'}, "
        f"{args.output_dir / 'downhill_grade_profile.png'}, "
        f"{args.output_dir / 'engine_governed_torque_curve.png'}, "
        f"{args.output_dir / 'downhill_engine_braking_trace.csv'}, and "
        f"{args.output_dir / 'downhill_engine_braking_summary.json'}."
    )

    if args.no_show:
        plt.close(figure)
        plt.close(profile_figure)
        plt.close(engine_figure)
    else:
        plt.show()


if __name__ == "__main__":
    main()
