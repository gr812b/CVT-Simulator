"""Run one continuous CVT simulation through a scheduled grade programme.

This is a **single hybrid CINDER integration**.  The CVT state, contact regime,
and shift state continue smoothly throughout the whole scenario.  Only the
external road grade changes.

Why a time programme rather than a distance-indexed road profile?
---------------------------------------------------------------
``CallableRoadProfile`` in CINDER is intentionally position-indexed, which is
right for modelling a real surveyed road.  A request such as “hold 30 degrees
for ten seconds” is instead a controlled load scenario: under a steep grade,
the vehicle speed changes, so no fixed road length can guarantee a ten-second
exposure.  This tool therefore uses a small time-aware adapter around the same
road-profile interface.  It keeps CINDER's road-load equations unchanged, but
feeds them a smooth, explicitly timed grade schedule.

Default 45 s programme
-----------------------
  0–10 s   : level ground (0 deg)
 10–12 s   : smooth 0 -> +30 deg rise
 12–22 s   : +30 deg hold
 22–24 s   : smooth +30 -> +15 deg easing
 24–34 s   : +15 deg hold
 34–36 s   : smooth +15 -> -20 deg transition
 36–40 s   : -20 deg downhill hold
 40–42 s   : smooth -20 -> 0 deg recovery
 42–45 s   : level recovery

Each scheduled phase receives its own dotted overlay on the primary-vs-
secondary speed curve.  This lets the shift curve be read as one continuous
trajectory while still showing which part occurred under each grade condition.

Examples
--------
    python tools2/run_grade_program_response.py --no-show

    # Keep the same stages but remove the final level-recovery dwell.
    python tools2/run_grade_program_response.py --duration-s 42 --no-show

    # Run physical checks as well (slower than the transient itself).
    python tools2/run_grade_program_response.py --run-audit --no-show
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
from math import radians
import json
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

from cinder.dynamics.shift_constraints import EngagedShiftConstraint  # noqa: E402
from cinder.integration import CVTDynamicState, HybridIntegratorSettings  # noqa: E402
from cinder.integration.cvt_contact_events import build_cvt_contact_events  # noqa: E402
from cinder.integration.cvt_operating_hybrid import (
    CVTOperatingHybridSystem,
)  # noqa: E402
from cinder.integration.cvt_regime import (
    CVTEngagementState,
    CVTShiftConstraint,
)  # noqa: E402
from cinder.integration.cvt_regime_events import (  # noqa: E402
    build_deadzone_free_boundary_events,
    build_engaged_free_boundary_events,
    build_lower_stop_release_event,
    build_low_ratio_seat_events,
    build_upper_stop_release_event,
)
from cinder.vehicle import CallableRoadProfile  # noqa: E402
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
class GradePhase:
    """One named time interval in a smooth grade programme."""

    name: str
    start_s: float
    end_s: float
    start_degrees: float
    end_degrees: float
    transition: bool = False

    def contains(self, time_s: float, *, include_end: bool = False) -> bool:
        if include_end:
            return self.start_s <= time_s <= self.end_s
        return self.start_s <= time_s < self.end_s

    def grade_radians(self, time_s: float) -> float:
        """Return constant or C1-smooth grade over this phase."""

        if self.end_s <= self.start_s:
            return radians(self.end_degrees)
        if not self.transition:
            return radians(self.start_degrees)
        u = _smoothstep((time_s - self.start_s) / (self.end_s - self.start_s))
        return radians(self.start_degrees + (self.end_degrees - self.start_degrees) * u)

    @property
    def display_label(self) -> str:
        """Compact unique legend label for this one shift-curve overlay."""

        if self.transition:
            grade = f"{self.start_degrees:+.0f}→{self.end_degrees:+.0f}°"
        else:
            grade = f"{self.start_degrees:+.0f}°"
        return f"{self.name} ({grade})"


@dataclass(frozen=True, slots=True)
class GradeProgramme:
    """Time-scheduled grade curve with C1 transitions and named phases."""

    phases: tuple[GradePhase, ...]

    def __post_init__(self) -> None:
        if not self.phases:
            raise ValueError("A grade programme requires at least one phase.")
        previous_end = 0.0
        previous_grade = None
        for phase in self.phases:
            if phase.start_s < previous_end - 1.0e-12 or phase.end_s <= phase.start_s:
                raise ValueError("Grade phases must be ordered with positive duration.")
            if (
                previous_grade is not None
                and abs(phase.start_degrees - previous_grade) > 1.0e-9
            ):
                raise ValueError("Adjacent grade phases must be grade-continuous.")
            previous_end = phase.end_s
            previous_grade = phase.end_degrees

    @property
    def end_time_s(self) -> float:
        return self.phases[-1].end_s

    def grade_radians(self, time_s: float) -> float:
        time = float(time_s)
        for index, phase in enumerate(self.phases):
            if phase.contains(time, include_end=index == len(self.phases) - 1):
                return phase.grade_radians(time)
        return radians(self.phases[-1].end_degrees)

    def phase_index(self, time_s: float) -> int:
        time = float(time_s)
        for index, phase in enumerate(self.phases):
            if phase.contains(time, include_end=index == len(self.phases) - 1):
                return index
        return len(self.phases) - 1

    @classmethod
    def default(cls, *, final_level_seconds: float = 3.0) -> "GradeProgramme":
        """Build the requested 0/+30/+15/-20/0 test sequence.

        The three main holds are exactly ten seconds at 0, +30, and +15 deg.
        Two-second cubic smoothsteps avoid a finite grade-force jump.  The
        final level dwell is separate so recovery after the downhill transition
        is visible rather than ending at the instant grade returns to zero.
        """

        t = 0.0

        def add(
            name: str, duration: float, start: float, end: float, transition: bool
        ) -> GradePhase:
            nonlocal t
            phase = GradePhase(name, t, t + duration, start, end, transition)
            t += duration
            return phase

        return cls(
            (
                add("flat launch", 10.0, 0.0, 0.0, False),
                add("rise to 30", 2.0, 0.0, 30.0, True),
                add("30 degree hill", 10.0, 30.0, 30.0, False),
                add("ease to 15", 2.0, 30.0, 15.0, True),
                add("15 degree hill", 10.0, 15.0, 15.0, False),
                add("turn to downhill", 2.0, 15.0, -20.0, True),
                add("20 degree downhill", 4.0, -20.0, -20.0, False),
                add("return to level", 2.0, -20.0, 0.0, True),
                add("flat recovery", final_level_seconds, 0.0, 0.0, False),
            )
        )


class _TimeClockedRoadProfile:
    """Mutable clock wrapper used only by the time-aware hybrid adapter.

    It intentionally implements the same ``sample(vehicle_distance=...)``
    protocol as CINDER's standard profiles.  ``vehicle_distance`` is retained
    in the returned sample by the wrapped ``CallableRoadProfile``; the grade
    itself is prescribed by the current integration time.
    """

    def __init__(self, programme: GradeProgramme) -> None:
        self.programme = programme
        self.current_time_s = 0.0
        self._profile = CallableRoadProfile(
            grade_angle_function=lambda _distance: self.programme.grade_radians(
                self.current_time_s
            )
        )

    def set_time(self, time_s: float) -> None:
        self.current_time_s = float(time_s)

    def sample(self, *, vehicle_distance: float):
        return self._profile.sample(vehicle_distance=vehicle_distance)


class TimeAwareRoadHybridSystem(CVTOperatingHybridSystem):
    """CINDER operating adapter that sets a schedule clock before every model call.

    CINDER's public ``RoadProfile`` API is spatial by design.  This subclass is
    deliberately local to this tool so a *controlled time programme* can be
    evaluated without altering production CINDER mechanics.  Every RHS, contact
    event, unilateral-reaction event, and transition resolves the grade at the
    exact solver time supplied by CINDER.
    """

    def __init__(self, *, time_profile: _TimeClockedRoadProfile, **kwargs) -> None:
        self._time_profile = time_profile
        super().__init__(**kwargs)

    def _set_time(self, time_s: float) -> None:
        self._time_profile.set_time(time_s)

    def evaluate(self, *, time: float, state: NDArray[np.float64], mode):
        self._set_time(time)
        return super().evaluate(time=time, state=state, mode=mode)

    def events(self, time: float, state: NDArray[np.float64], mode):
        """Build event functions whose state evaluation carries the correct time."""

        self._set_time(time)
        if mode.engagement is CVTEngagementState.DEADZONE:
            if mode.shift_constraint is CVTShiftConstraint.FREE:
                return build_deadzone_free_boundary_events(limits=self.operating_limits)
            if mode.shift_constraint is CVTShiftConstraint.LOWER_STOP:
                return (
                    build_lower_stop_release_event(
                        closing_reaction=lambda event_time, vector: self._lower_stop_reaction_at_time(
                            time=event_time, vector=vector
                        )
                    ),
                )
            raise RuntimeError(
                f"Unsupported deadzone constraint: {mode.shift_constraint!r}."
            )

        constraint = self._engaged_constraint_for(mode)
        assert mode.contact_regime is not None
        contact_events = build_cvt_contact_events(
            regime=mode.contact_regime,
            evaluate=lambda event_time, vector: self._contact_evaluation_at_time(
                time=event_time,
                vector=vector,
                regime=mode.contact_regime,
                shift_constraint=constraint,
            ),
            traction_law=self.traction_law,
            switching_settings=self.switching_settings,
            relative_speed_tolerance=self.solve_settings.contact_tolerances.relative_speed_tolerance,
            relative_acceleration_tolerance=self.solve_settings.contact_tolerances.relative_acceleration_tolerance,
            include_shift_boundary_events=False,
        )
        if mode.shift_constraint is CVTShiftConstraint.FREE:
            return contact_events + build_engaged_free_boundary_events(
                limits=self.operating_limits
            )
        if mode.shift_constraint is CVTShiftConstraint.LOW_RATIO_SEAT:
            return contact_events + build_low_ratio_seat_events(
                primary_clamping_force=lambda event_time, vector: self._primary_clamping_force_at_time(
                    time=event_time, vector=vector
                ),
                closing_reaction=lambda event_time, vector: self._low_ratio_seat_reaction_at_time(
                    time=event_time, vector=vector, contact_regime=mode.contact_regime
                ),
            )
        if mode.shift_constraint is CVTShiftConstraint.UPPER_STOP:
            return contact_events + (
                build_upper_stop_release_event(
                    opening_reaction=lambda event_time, vector: self._upper_stop_reaction_at_time(
                        time=event_time,
                        vector=vector,
                        contact_regime=mode.contact_regime,
                    )
                ),
            )
        raise RuntimeError(
            f"Unsupported engaged constraint: {mode.shift_constraint!r}."
        )

    def transition(
        self, time: float, state: NDArray[np.float64], mode, fired_event_names
    ):
        self._set_time(time)
        return super().transition(time, state, mode, fired_event_names)

    def classify_initial_regime(self, state: CVTDynamicState):
        self._set_time(0.0)
        return super().classify_initial_regime(state)

    def _lower_stop_reaction_at_time(
        self, *, time: float, vector: NDArray[np.float64]
    ) -> float:
        self._set_time(time)
        return self._lower_stop_reaction(vector=vector)

    def _primary_clamping_force_at_time(
        self, *, time: float, vector: NDArray[np.float64]
    ) -> float:
        self._set_time(time)
        return self._primary_clamping_force(time=time, vector=vector)

    def _low_ratio_seat_reaction_at_time(
        self, *, time: float, vector: NDArray[np.float64], contact_regime
    ) -> float:
        self._set_time(time)
        return self._low_ratio_seat_reaction(
            time=time, vector=vector, contact_regime=contact_regime
        )

    def _upper_stop_reaction_at_time(
        self, *, time: float, vector: NDArray[np.float64], contact_regime
    ) -> float:
        self._set_time(time)
        return self._upper_stop_reaction(
            time=time, vector=vector, contact_regime=contact_regime
        )

    def _contact_evaluation_at_time(
        self, *, time: float, vector: NDArray[np.float64], regime, shift_constraint
    ):
        self._set_time(time)
        return self.evaluator.evaluate_vector(
            time=time,
            vector=vector,
            regime=regime,
            shift_constraint=shift_constraint,
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


def _smoothstep(value: float) -> float:
    value = float(np.clip(value, 0.0, 1.0))
    return value * value * (3.0 - 2.0 * value)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", type=Path, default=_DEFAULT_PRESET)
    parser.add_argument("--duration-s", type=float, default=45.0)
    parser.add_argument("--final-level-s", type=float, default=3.0)
    parser.add_argument("--initial-primary-rpm", type=float, default=1800.0)
    parser.add_argument("--target-engagement-rpm", type=float, default=2000.0)
    parser.add_argument("--solver-method", default=None)
    parser.add_argument("--max-step-ms", type=float, default=None)
    parser.add_argument("--relative-tolerance", type=float, default=None)
    parser.add_argument("--absolute-tolerance", type=float, default=None)
    parser.add_argument("--maximum-transitions", type=int, default=160)
    parser.add_argument("--plot-samples", type=int, default=1500)
    parser.add_argument("--run-audit", action="store_true")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/grade_program_response")
    )
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    for name in (
        "duration_s",
        "final_level_s",
        "initial_primary_rpm",
        "target_engagement_rpm",
    ):
        value = getattr(args, name)
        if not np.isfinite(value) or value <= 0.0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive.")
    for name in ("max_step_ms", "relative_tolerance", "absolute_tolerance"):
        value = getattr(args, name)
        if value is not None and (not np.isfinite(value) or value <= 0.0):
            parser.error(
                f"--{name.replace('_', '-')} must be finite and positive when supplied."
            )
    if args.maximum_transitions < 1 or args.plot_samples < 200:
        parser.error(
            "--maximum-transitions must be at least one and --plot-samples at least 200."
        )
    return args


def load_candidate(path: Path) -> tuple[TuneCandidate, dict[str, float | str]]:
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


def build_system(*, resolved, programme: GradeProgramme) -> TimeAwareRoadHybridSystem:
    template, _ = build_operating_system(resolved.constants)
    time_profile = _TimeClockedRoadProfile(programme)
    model = replace(template.model, road_profile=time_profile)
    return TimeAwareRoadHybridSystem(
        time_profile=time_profile,
        model=model,
        traction_law=template.traction_law,
        solve_settings=template.solve_settings,
        operating_limits=template.operating_limits,
        switching_settings=template.switching_settings,
    )


def compact_mode(mode) -> str:
    if mode.contact_regime is None:
        return f"{mode.engagement.value}/{mode.shift_constraint.value}"
    return f"{mode.engagement.value}/{mode.shift_constraint.value}/{mode.contact_regime.mode.value}"


def allocate_samples(sizes: Sequence[int], maximum: int) -> list[int]:
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
    system: TimeAwareRoadHybridSystem,
    result,
    programme: GradeProgramme,
    maximum_samples: int,
) -> ProgrammeTrace:
    budgets = allocate_samples(
        [segment.state.shape[1] for segment in result.segments], maximum_samples
    )
    rows = []
    final_drive = system.model.road_load.final_drive
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
            system._set_time(time)
            snapshot = system.model.snapshot(state=state)
            distance = final_drive.vehicle_distance_from_secondary_angle(
                secondary_shaft_angle=state.secondary_shaft_angle
            )
            rows.append(
                (
                    time,
                    vector,
                    compact_mode(segment.mode),
                    float(np.rad2deg(programme.grade_radians(time))),
                    float(snapshot.road_load.secondary_external_torque),
                    float(snapshot.road_load.vehicle_speed),
                    float(distance),
                )
            )
    rows.sort(key=lambda row: row[0])
    return ProgrammeTrace(
        time=np.asarray([row[0] for row in rows], dtype=float),
        state=np.column_stack([row[1] for row in rows]),
        mode=tuple(row[2] for row in rows),
        grade_degrees=np.asarray([row[3] for row in rows], dtype=float),
        secondary_road_torque_nm=np.asarray([row[4] for row in rows], dtype=float),
        vehicle_speed_mps=np.asarray([row[5] for row in rows], dtype=float),
        vehicle_distance_m=np.asarray([row[6] for row in rows], dtype=float),
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
        ("static_capacity_exhausted", "slip"),
    )
    for fragment, label in mapping:
        if fragment in reason:
            return label
    return reason.replace("_", " ")


def plot_masked_runs(
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


def annotate_transitions(
    axes: Iterable[plt.Axes], label_axes: Iterable[plt.Axes], result
) -> None:
    axes = tuple(axes)
    label_axes = tuple(label_axes)
    for count, record in enumerate(result.transitions):
        for axis in axes:
            axis.axvline(record.time, linestyle="--", linewidth=0.75, alpha=0.45)
        fraction = 0.97 - 0.11 * (count % 6)
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


def annotate_programme_boundaries(
    axes: Iterable[plt.Axes], grade_axis: plt.Axes, programme: GradeProgramme
) -> None:
    for phase in programme.phases[1:]:
        for axis in axes:
            axis.axvline(phase.start_s, linestyle=":", linewidth=0.9, alpha=0.7)
        grade_axis.annotate(
            phase.name,
            xy=(phase.start_s, 0.04),
            xycoords=("data", "axes fraction"),
            xytext=(2, 0),
            textcoords="offset points",
            rotation=90,
            va="bottom",
            ha="left",
            fontsize=6.0,
        )


def plot_response(
    *, trace: ProgrammeTrace, result, resolved, programme: GradeProgramme
):
    t = trace.time
    primary_rpm = trace.state[0] * RPM_PER_RADIAN_PER_SECOND
    secondary_rpm = trace.state[1] * RPM_PER_RADIAN_PER_SECOND
    shift_mm = trace.state[3] / MILLIMETRE
    shift_speed_mmps = trace.state[4] / MILLIMETRE

    figure, axes = plt.subplots(2, 3, figsize=(19, 10), constrained_layout=True)

    speed_axis = axes[0, 0]
    speed_axis.plot(t, primary_rpm, label=r"$\omega_p$")
    speed_axis.plot(t, secondary_rpm, label=r"$\omega_s$")
    speed_axis.set_title("Shaft speeds")
    speed_axis.set_xlabel("Time [s]")
    speed_axis.set_ylabel("Speed [rpm]")
    speed_axis.grid(True, alpha=0.25)
    speed_axis.legend(loc="best")

    shift_axis = axes[0, 1]
    shift_axis.plot(t, shift_mm, label=r"$s$")
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
    shift_rate_axis.plot(t, shift_speed_mmps, linestyle=":", label=r"$\dot{s}$")
    shift_rate_axis.set_ylabel("Shift speed [mm/s]")
    handles, labels = shift_axis.get_legend_handles_labels()
    right_handles, right_labels = shift_rate_axis.get_legend_handles_labels()
    shift_axis.legend(handles + right_handles, labels + right_labels, loc="best")

    curve_axis = axes[0, 2]
    curve_axis.plot(secondary_rpm, primary_rpm, alpha=0.22, label="full trajectory")
    for index, phase in enumerate(programme.phases):
        include_end = index == len(programme.phases) - 1
        mask = (t >= phase.start_s) & (
            (t <= phase.end_s) if include_end else (t < phase.end_s)
        )
        plot_masked_runs(
            curve_axis,
            secondary_rpm,
            primary_rpm,
            mask,
            linestyle=":",
            linewidth=2.25,
            label=phase.display_label,
        )
    curve_axis.scatter([secondary_rpm[0]], [primary_rpm[0]], marker="o", label="launch")
    curve_axis.set_title("Shift curve: phase-dotted grade programme")
    curve_axis.set_xlabel("Secondary speed [rpm]")
    curve_axis.set_ylabel("Primary speed [rpm]")
    curve_axis.grid(True, alpha=0.25)
    curve_axis.legend(loc="best", fontsize=6.8, ncol=2)

    grade_axis = axes[1, 0]
    grade_axis.plot(t, trace.grade_degrees, label="grade")
    grade_axis.axhline(0.0, linestyle="--", linewidth=0.8)
    grade_axis.set_title("Route-grade programme (full window)")
    grade_axis.set_xlabel("Time [s]")
    grade_axis.set_ylabel("Grade [deg]")
    grade_axis.set_xlim(0.0, max(float(t[-1]), programme.end_time_s))
    grade_axis.set_ylim(-24.0, 34.0)
    grade_axis.grid(True, alpha=0.25)
    grade_axis.legend(loc="best")

    torque_axis = axes[1, 1]
    torque_axis.plot(t, trace.secondary_road_torque_nm, label=r"$\tau_{road,s}$")
    torque_axis.axhline(0.0, linestyle="--", linewidth=0.8)
    torque_axis.set_title("Secondary road-load torque")
    torque_axis.set_xlabel("Time [s]")
    torque_axis.set_ylabel("Torque [N m]")
    torque_axis.grid(True, alpha=0.25)
    torque_axis.legend(loc="best")

    vehicle_axis = axes[1, 2]
    vehicle_axis.plot(t, trace.vehicle_speed_mps * 3.6, label="speed")
    vehicle_axis.set_title("Vehicle response and distance")
    vehicle_axis.set_xlabel("Time [s]")
    vehicle_axis.set_ylabel("Vehicle speed [km/h]")
    vehicle_axis.grid(True, alpha=0.25)
    distance_axis = vehicle_axis.twinx()
    distance_axis.plot(t, trace.vehicle_distance_m, linestyle=":", label="distance")
    distance_axis.set_ylabel("Distance [m]")
    handles, labels = vehicle_axis.get_legend_handles_labels()
    right_handles, right_labels = distance_axis.get_legend_handles_labels()
    vehicle_axis.legend(handles + right_handles, labels + right_labels, loc="best")

    annotate_transitions(
        (speed_axis, shift_axis, torque_axis, vehicle_axis),
        (speed_axis, shift_axis),
        result,
    )
    annotate_programme_boundaries(
        (speed_axis, shift_axis, grade_axis, torque_axis, vehicle_axis),
        grade_axis,
        programme,
    )

    figure.suptitle(
        "CINDER circular-primary controlled grade programme | "
        f"{resolved.candidate.label()} | primary preload={resolved.resolved_primary_preload_mm:.2f} mm",
        fontsize=13,
    )
    return figure


def programme_metrics(
    trace: ProgrammeTrace, programme: GradeProgramme
) -> dict[str, float | None]:
    shift_mm = trace.state[3] / MILLIMETRE
    shift_speed = trace.state[4] / MILLIMETRE
    metrics: dict[str, float | None] = {
        "minimum_shift_mm": float(np.min(shift_mm)),
        "maximum_shift_mm": float(np.max(shift_mm)),
        "maximum_upshift_speed_mm_per_s": float(np.max(shift_speed)),
        "maximum_backshift_speed_mm_per_s": float(np.min(shift_speed)),
        "final_shift_mm": float(shift_mm[-1]),
        "final_primary_rpm": float(trace.state[0, -1] * RPM_PER_RADIAN_PER_SECOND),
        "final_secondary_rpm": float(trace.state[1, -1] * RPM_PER_RADIAN_PER_SECOND),
        "final_vehicle_distance_m": float(trace.vehicle_distance_m[-1]),
    }
    for phase in programme.phases:
        mask = (trace.time >= phase.start_s) & (trace.time <= phase.end_s)
        if np.any(mask):
            metrics[f"min_shift_during_{phase.name.replace(' ', '_')}_mm"] = float(
                np.min(shift_mm[mask])
            )
    return metrics


def audit_result(*, system: TimeAwareRoadHybridSystem, result) -> tuple[str, list[str]]:
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


def write_trace(path: Path, trace: ProgrammeTrace) -> None:
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
                "grade_degrees",
                "secondary_road_torque_nm",
                "vehicle_speed_mps",
                "vehicle_distance_m",
            )
        )
        for i, time in enumerate(trace.time):
            state = trace.state[:, i]
            writer.writerow(
                (
                    time,
                    trace.mode[i],
                    state[0] * RPM_PER_RADIAN_PER_SECOND,
                    state[1] * RPM_PER_RADIAN_PER_SECOND,
                    state[2],
                    state[3] / MILLIMETRE,
                    state[4] / MILLIMETRE,
                    state[5],
                    trace.grade_degrees[i],
                    trace.secondary_road_torque_nm[i],
                    trace.vehicle_speed_mps[i],
                    trace.vehicle_distance_m[i],
                )
            )


def main() -> None:
    args = parse_arguments()
    programme = GradeProgramme.default(final_level_seconds=args.final_level_s)
    if args.duration_s < programme.end_time_s - 1.0e-12:
        print(
            f"warning: duration {args.duration_s:.2f} s ends before the complete "
            f"{programme.end_time_s:.2f} s grade programme."
        )
    candidate, integration = load_candidate(args.preset)
    method = str(args.solver_method or integration.get("solver_method", "LSODA"))
    # A 45 s programme includes slow backshift/re-upshift intervals.  These
    # exploratory defaults are intentionally looser than the saved 10 s launch
    # diagnostic so the one uninterrupted scenario remains practical.  Re-run
    # accepted candidates with 1e-3 / 1e-6 (and preferably the original 20 ms
    # cap) as a sensitivity check before drawing tuning conclusions.
    max_step_ms = float(args.max_step_ms if args.max_step_ms is not None else 50.0)
    rtol = float(
        args.relative_tolerance if args.relative_tolerance is not None else 1.0e-2
    )
    atol = float(
        args.absolute_tolerance if args.absolute_tolerance is not None else 1.0e-5
    )
    resolved = resolve_primary_preload(
        candidate, target_engagement_rpm=args.target_engagement_rpm
    )
    system = build_system(resolved=resolved, programme=programme)
    settings = HybridIntegratorSettings(
        relative_tolerance=rtol,
        absolute_tolerance=atol,
        method=method,
        max_step=max_step_ms * 1.0e-3,
        maximum_transitions=args.maximum_transitions,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print("Controlled grade-programme response")
    print("=" * 88)
    print(candidate.label())
    print(f"primary preload={resolved.resolved_primary_preload_mm:.3f} mm")
    print(
        f"one {args.duration_s:.3g} s CINDER integration; programme ends at {programme.end_time_s:.1f} s"
    )
    for phase in programme.phases:
        print(
            f"  {phase.start_s:5.1f}–{phase.end_s:5.1f} s  {phase.name}: {phase.start_degrees:+.0f} -> {phase.end_degrees:+.0f} deg"
        )

    result = system.integrate(
        time_span=(0.0, args.duration_s),
        initial_state=launch_initial_state(primary_rpm=args.initial_primary_rpm),
        settings=settings,
    )
    if not result.completed:
        raise RuntimeError(f"Integration terminated early: {result.termination_reason}")

    trace = sample_trace(
        system=system,
        result=result,
        programme=programme,
        maximum_samples=args.plot_samples,
    )
    figure = plot_response(
        trace=trace, result=result, resolved=resolved, programme=programme
    )
    figure.savefig(args.output_dir / "grade_program_response.png", dpi=160)
    write_trace(args.output_dir / "grade_program_trace.csv", trace)
    audit_status, audit_lines = (
        audit_result(system=system, result=result)
        if args.run_audit
        else (
            "not_run",
            ["Not run by default; pass --run-audit for the slower physical audit."],
        )
    )
    summary = {
        "scenario": {
            "description": "One continuous CINDER hybrid integration under a time-programmed grade schedule.",
            "duration_s": args.duration_s,
            "programme": [
                {
                    "name": phase.name,
                    "start_s": phase.start_s,
                    "end_s": phase.end_s,
                    "start_degrees": phase.start_degrees,
                    "end_degrees": phase.end_degrees,
                    "transition": phase.transition,
                }
                for phase in programme.phases
            ],
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
            "completed": result.completed,
            "segments": len(result.segments),
            "transitions": [record.transition.reason for record in result.transitions],
        },
        "programme_metrics": programme_metrics(trace, programme),
        "audit": {"status": audit_status, "lines": audit_lines},
    }
    with (args.output_dir / "grade_program_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, indent=2)

    print(
        f"\n{len(result.segments)} segments; {len(result.transitions)} transitions; audit={audit_status}"
    )
    for record in result.transitions:
        print(f"  t={record.time:.6f} s  {short_event(record.transition.reason)}")
    print("\nProgramme metrics")
    for name, value in summary["programme_metrics"].items():
        print(f"{name}: {value}")
    for line in audit_lines:
        print(f"  {line}")
    print(
        f"\nWrote {args.output_dir / 'grade_program_response.png'}, {args.output_dir / 'grade_program_trace.csv'}, and {args.output_dir / 'grade_program_summary.json'}."
    )

    if args.no_show:
        plt.close(figure)
    else:
        plt.show()


if __name__ == "__main__":
    main()
