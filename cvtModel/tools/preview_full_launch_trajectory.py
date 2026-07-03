"""Run and visualize one 10 s CVT launch with transition diagnostics.

This is a **system-level diagnostic**, not a calibrated Baja prediction. It
starts at the lower physical stop with the primary at 1800 rpm, the vehicle at
rest, and the belt locked to the stationary secondary in deadzone.

The default 2 kg / 20 mm configuration is intentionally aggressive: it is a
repeatable way to exercise engagement, free engaged contact, upper-stop impact,
and held-stop dynamics. It is *not* a recommended primary tune.

For tuning work, first map the coupled free-shift tendency:

    python tools/preview_primary_shift_tuning.py --no-show

Then use a physical lower-stop release target rather than guessing preload:

    python tools/preview_full_launch_trajectory.py \
        --target-lower-stop-release-rpm 2300 --no-show

That target derives the preload at which the deadzone lower-stop reaction first
falls to zero. It controls initial primary release speed; it does not promise a
particular complete-launch shift trajectory or replace later calibration.

Every hybrid transition is printed and labelled on all time-domain panels.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import sys
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT, _REPOSITORY_ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import (  # noqa: E402
    BajaTrialConstants,
    RPM_TO_RAD_PER_SECOND,
    build_baja_trial_baseline,
)
from primary_tuning import (  # noqa: E402
    PrimaryTuningRequest,
    PrimaryTuningResult,
    resolve_primary_tuning,
)
from cinder.contact import ContactTractionLaw  # noqa: E402
from cinder.dynamics import EngagedContactSolveSettings, LambdaSearchBounds  # noqa: E402
from cinder.dynamics.deadzone import DeadzoneEvaluation  # noqa: E402
from cinder.integration import CVTDynamicState, HybridIntegratorSettings  # noqa: E402
from cinder.integration.cvt_contact import CVTContactEvaluation  # noqa: E402
from cinder.integration.cvt_operating_hybrid import CVTOperatingHybridSystem  # noqa: E402
from cinder.integration.cvt_operating_limits import CVTShiftOperatingLimits  # noqa: E402
from cinder.integration.cvt_regime import CVTOperatingRegime  # noqa: E402

_RPM_PER_RADIAN_PER_SECOND = 60.0 / (2.0 * np.pi)


@dataclass(frozen=True, slots=True)
class LaunchConfiguration:
    duration_seconds: float
    initial_primary_rpm: float
    flyweight_mass: float
    primary_preload: float
    primary_ramp_angle_degrees: float
    primary_spring_rate: float
    target_lower_stop_release_rpm: float | None
    static_lambda_limit: float
    kinetic_lambda_magnitude: float
    maximum_step: float
    diagnostic_samples: int


@dataclass(frozen=True, slots=True)
class LaunchTrace:
    time: NDArray[np.float64]
    state: NDArray[np.float64]
    mode_label: tuple[str, ...]
    primary_surface_speed: NDArray[np.float64]
    secondary_surface_speed: NDArray[np.float64]
    primary_torque: NDArray[np.float64]
    secondary_torque: NDArray[np.float64]
    primary_lambda: NDArray[np.float64]
    secondary_lambda: NDArray[np.float64]
    primary_normal: NDArray[np.float64]
    secondary_normal: NDArray[np.float64]
    primary_relative_speed: NDArray[np.float64]
    secondary_relative_speed: NDArray[np.float64]
    stop_reaction: NDArray[np.float64]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-s", type=float, default=10.0, help="Simulation duration [s].")
    parser.add_argument(
        "--initial-primary-rpm",
        type=float,
        default=1800.0,
        help="Primary shaft speed at the lower-stop launch state [rpm].",
    )
    parser.add_argument(
        "--flyweight-mass-kg",
        type=float,
        default=2.0,
        help=(
            "Diagnostic flyweight mass [kg]. The default is intentionally upshift-biased "
            "so the uncalibrated baseline reaches the upper stop."
        ),
    )
    parser.add_argument(
        "--primary-preload-mm",
        type=float,
        default=20.0,
        help="Primary spring initial compression for the diagnostic [mm].",
    )
    parser.add_argument(
        "--primary-ramp-angle-deg",
        type=float,
        default=30.0,
        help="Primary centrifugal-ramp angle [deg].",
    )
    parser.add_argument(
        "--primary-spring-rate-n-per-m",
        type=float,
        default=12_784.0,
        help="Primary return-spring rate [N/m].",
    )
    parser.add_argument(
        "--target-lower-stop-release-rpm",
        type=float,
        default=None,
        help=(
            "When supplied, derive primary preload so the free deadzone primary force "
            "at the lower stop is zero at this speed [rpm]. This overrides "
            "--primary-preload-mm."
        ),
    )
    parser.add_argument("--static-lambda-limit", type=float, default=0.65)
    parser.add_argument("--kinetic-lambda", type=float, default=0.55)
    parser.add_argument("--max-step-ms", type=float, default=10.0)
    parser.add_argument(
        "--diagnostic-samples",
        type=int,
        default=420,
        help="Maximum accepted states re-evaluated for diagnostic traces.",
    )
    parser.add_argument("--save", type=Path, help="Optional PNG/PDF/SVG output path.")
    parser.add_argument("--no-show", action="store_true", help="Do not open the matplotlib window.")
    args = parser.parse_args()

    for name, value in (
        ("--duration-s", args.duration_s),
        ("--initial-primary-rpm", args.initial_primary_rpm),
        ("--flyweight-mass-kg", args.flyweight_mass_kg),
        ("--primary-preload-mm", args.primary_preload_mm),
        ("--primary-ramp-angle-deg", args.primary_ramp_angle_deg),
        ("--primary-spring-rate-n-per-m", args.primary_spring_rate_n_per_m),
        ("--static-lambda-limit", args.static_lambda_limit),
        ("--kinetic-lambda", args.kinetic_lambda),
        ("--max-step-ms", args.max_step_ms),
    ):
        if not isfinite(value):
            parser.error(f"{name} must be finite.")
    if args.duration_s <= 0.0:
        parser.error("--duration-s must be strictly positive.")
    if args.initial_primary_rpm < 0.0:
        parser.error("--initial-primary-rpm must be non-negative.")
    if args.flyweight_mass_kg <= 0.0:
        parser.error("--flyweight-mass-kg must be strictly positive.")
    if args.primary_preload_mm < 0.0:
        parser.error("--primary-preload-mm must be non-negative.")
    if not 0.0 < args.primary_ramp_angle_deg < 89.0:
        parser.error("--primary-ramp-angle-deg must lie strictly between 0 and 89 degrees.")
    if args.primary_spring_rate_n_per_m <= 0.0:
        parser.error("--primary-spring-rate-n-per-m must be strictly positive.")
    if args.target_lower_stop_release_rpm is not None:
        if (
            not isfinite(args.target_lower_stop_release_rpm)
            or args.target_lower_stop_release_rpm <= 0.0
        ):
            parser.error("--target-lower-stop-release-rpm must be finite and strictly positive.")
    if args.static_lambda_limit <= 0.0 or args.kinetic_lambda <= 0.0:
        parser.error("Traction limits must be strictly positive.")
    if args.max_step_ms <= 0.0:
        parser.error("--max-step-ms must be strictly positive.")
    if args.diagnostic_samples < 40:
        parser.error("--diagnostic-samples must be at least 40.")
    return args


def build_launch_system(configuration: LaunchConfiguration) -> tuple[
    CVTOperatingHybridSystem,
    CVTDynamicState,
    BajaTrialConstants,
    PrimaryTuningResult,
]:
    """Build one rest-launch state and full operating hybrid system.

    The optional lower-stop release target changes only the primary spring
    preload.  It makes launch tuning interpretable: the target is the primary
    speed at which the lower stop first loses its unilateral reaction, not a
    hidden time-domain controller.
    """

    tuning = resolve_primary_tuning(
        reference_constants=BajaTrialConstants(),
        request=PrimaryTuningRequest(
            flyweight_mass=configuration.flyweight_mass,
            ramp_angle_degrees=configuration.primary_ramp_angle_degrees,
            spring_rate=configuration.primary_spring_rate,
            explicit_preload=configuration.primary_preload,
            target_lower_stop_release_rpm=configuration.target_lower_stop_release_rpm,
        ),
    )
    constants = tuning.constants
    baseline = build_baja_trial_baseline(constants)
    traction_law = ContactTractionLaw.symmetric(
        primary_static_lambda_limit=configuration.static_lambda_limit,
        secondary_static_lambda_limit=configuration.static_lambda_limit,
        primary_kinetic_lambda_magnitude=configuration.kinetic_lambda_magnitude,
        secondary_kinetic_lambda_magnitude=configuration.kinetic_lambda_magnitude,
    )
    system = CVTOperatingHybridSystem(
        model=baseline.model,
        traction_law=traction_law,
        solve_settings=EngagedContactSolveSettings(
            lambda_search_bounds=LambdaSearchBounds.symmetric(
                primary_half_width=3.0,
                secondary_half_width=3.0,
            ),
            initial_guess=baseline.default_trial,
            maximum_closure_condition_number=1.0e8,
        ),
        operating_limits=CVTShiftOperatingLimits(
            lower_stop_shift=0.0,
            engagement_shift=constants.deadzone_shift,
            upper_stop_shift=constants.max_shift,
        ),
    )
    launch_state = CVTDynamicState(
        primary_angular_speed=configuration.initial_primary_rpm * RPM_TO_RAD_PER_SECOND,
        secondary_angular_speed=0.0,
        belt_speed=0.0,
        shift_position=0.0,
        shift_speed=0.0,
        secondary_shaft_angle=0.0,
    )
    return system, launch_state, constants, tuning


def _sample_indices(count: int, maximum: int) -> NDArray[np.int64]:
    if count <= maximum:
        return np.arange(count, dtype=np.int64)
    return np.unique(np.linspace(0, count - 1, maximum, dtype=np.int64))


def _allocate_sample_budget(segment_sizes: Iterable[int], maximum: int) -> tuple[int, ...]:
    sizes = tuple(segment_sizes)
    total = sum(sizes)
    if total <= maximum:
        return sizes
    raw = [max(2, round(maximum * size / total)) for size in sizes]
    while sum(raw) > maximum:
        candidate = max(range(len(raw)), key=lambda index: raw[index])
        if raw[candidate] <= 2:
            break
        raw[candidate] -= 1
    return tuple(raw)


def _mode_label(mode: CVTOperatingRegime) -> str:
    if mode.contact_regime is None:
        return f"{mode.engagement.value}/{mode.shift_constraint.value}"
    return (
        f"{mode.engagement.value}/{mode.shift_constraint.value}/"
        f"{mode.contact_regime.mode.value}"
    )


def sample_launch_trace(
    *,
    system: CVTOperatingHybridSystem,
    result,
    maximum_samples: int,
) -> LaunchTrace:
    """Re-evaluate selected accepted samples for one complete diagnostic trace."""

    trace_time: list[float] = []
    trace_state: list[NDArray[np.float64]] = []
    mode_labels: list[str] = []
    primary_surface: list[float] = []
    secondary_surface: list[float] = []
    primary_torque: list[float] = []
    secondary_torque: list[float] = []
    primary_lambda: list[float] = []
    secondary_lambda: list[float] = []
    primary_normal: list[float] = []
    secondary_normal: list[float] = []
    primary_relative_speed: list[float] = []
    secondary_relative_speed: list[float] = []
    stop_reaction: list[float] = []

    budgets = _allocate_sample_budget(
        (segment.state.shape[1] for segment in result.segments),
        maximum=maximum_samples,
    )
    for segment, budget in zip(result.segments, budgets, strict=True):
        for index in _sample_indices(segment.state.shape[1], maximum=budget):
            time = float(segment.time[index])
            vector = np.asarray(segment.state[:, index], dtype=float)
            state = CVTDynamicState.from_vector(vector)
            evaluation = system.evaluate(time=time, state=vector, mode=segment.mode)

            trace_time.append(time)
            trace_state.append(vector)
            mode_labels.append(_mode_label(segment.mode))
            if isinstance(evaluation, DeadzoneEvaluation):
                primary_surface.append(np.nan)
                secondary_surface.append(evaluation.snapshot.belt_secondary_lock_radius * state.secondary_angular_speed)
                primary_torque.append(evaluation.primary_transmitted_torque)
                secondary_torque.append(np.nan)
                primary_lambda.append(np.nan)
                secondary_lambda.append(np.nan)
                primary_normal.append(evaluation.primary_normal_resultant)
                secondary_normal.append(np.nan)
                primary_relative_speed.append(np.nan)
                secondary_relative_speed.append(np.nan)
                stop_reaction.append(
                    np.nan if evaluation.stop_reaction is None else evaluation.stop_reaction
                )
                continue

            assert isinstance(evaluation, CVTContactEvaluation)
            unknowns = evaluation.closure_unknowns
            primary_surface.append(
                evaluation.snapshot.geometry.primary.effective * state.primary_angular_speed
            )
            secondary_surface.append(
                evaluation.snapshot.geometry.secondary.effective * state.secondary_angular_speed
            )
            primary_torque.append(unknowns.primary_torque)
            secondary_torque.append(unknowns.secondary_torque)
            primary_lambda.append(evaluation.traction_utilization.primary_lambda)
            secondary_lambda.append(evaluation.traction_utilization.secondary_lambda)
            primary_normal.append(evaluation.normal_primary)
            secondary_normal.append(evaluation.normal_secondary)
            primary_relative_speed.append(evaluation.relative_motion.primary_relative_speed)
            secondary_relative_speed.append(evaluation.relative_motion.secondary_relative_speed)
            stop_reaction.append(
                np.nan if evaluation.upper_stop_reaction is None else evaluation.upper_stop_reaction
            )

    return LaunchTrace(
        time=np.asarray(trace_time, dtype=float),
        state=np.column_stack(trace_state),
        mode_label=tuple(mode_labels),
        primary_surface_speed=np.asarray(primary_surface, dtype=float),
        secondary_surface_speed=np.asarray(secondary_surface, dtype=float),
        primary_torque=np.asarray(primary_torque, dtype=float),
        secondary_torque=np.asarray(secondary_torque, dtype=float),
        primary_lambda=np.asarray(primary_lambda, dtype=float),
        secondary_lambda=np.asarray(secondary_lambda, dtype=float),
        primary_normal=np.asarray(primary_normal, dtype=float),
        secondary_normal=np.asarray(secondary_normal, dtype=float),
        primary_relative_speed=np.asarray(primary_relative_speed, dtype=float),
        secondary_relative_speed=np.asarray(secondary_relative_speed, dtype=float),
        stop_reaction=np.asarray(stop_reaction, dtype=float),
    )


def _short_transition_label(reason: str) -> str:
    if "primary_closed_into_engaged_contact" in reason:
        return "engagement"
    if "upper_stop_reached" in reason:
        return "upper stop impact"
    if "upper_stop_released" in reason:
        return "upper stop release"
    if "static_capacity_exhausted" in reason:
        return "static capacity -> slip"
    if "contact_restuck" in reason:
        return "re-stick"
    if "primary_opened_through_disengagement" in reason:
        return "disengagement"
    return reason.replace("_", " ")


def _add_transition_markers(*, axes: Iterable[plt.Axes], result) -> None:
    """Draw and label every time-domain transition on every time plot.

    The secondary-vs-primary shift curve has its own point labels, so it is
    intentionally excluded by the caller.  Staggering annotation heights keeps
    repeated launch events legible without assigning a meaning to colour.
    """

    axes = tuple(axes)
    for record_index, record in enumerate(result.transitions):
        label = _short_transition_label(record.transition.reason)
        y_fraction = 0.985 - 0.13 * (record_index % 5)
        for axis in axes:
            axis.axvline(record.time, linestyle="--", linewidth=0.9, alpha=0.75)
            axis.annotate(
                label,
                xy=(record.time, y_fraction),
                xycoords=("data", "axes fraction"),
                xytext=(3, 0),
                textcoords="offset points",
                rotation=90,
                va="top",
                ha="left",
                fontsize=7,
                alpha=0.9,
            )


def _transition_state(result, record) -> NDArray[np.float64]:
    """Use the post-event state so impact projections appear on shift curves."""

    return np.asarray(record.post_transition_state, dtype=float)


def plot_launch_trace(*, trace: LaunchTrace, result, constants: BajaTrialConstants, configuration: LaunchConfiguration):
    time = trace.time
    state = trace.state
    rpm_primary = state[0] * _RPM_PER_RADIAN_PER_SECOND
    rpm_secondary = state[1] * _RPM_PER_RADIAN_PER_SECOND

    figure, axes = plt.subplots(3, 3, figsize=(19, 14), constrained_layout=True)
    speed_axis = axes[0, 0]
    speed_axis.plot(time, rpm_primary, label=r"$\omega_p$")
    speed_axis.plot(time, rpm_secondary, label=r"$\omega_s$")
    speed_axis.set_title("Shaft speeds")
    speed_axis.set_xlabel("Time [s]")
    speed_axis.set_ylabel("Speed [rpm]")
    speed_axis.grid(True, alpha=0.25)
    speed_axis.legend(loc="best")

    shift_axis = axes[0, 1]
    shift_axis.plot(time, state[3] * 1.0e3, label=r"$s$")
    shift_axis.axhline(0.0, linestyle=":", label=r"$s_{\rm low}$")
    shift_axis.axhline(constants.deadzone_shift * 1.0e3, linestyle="--", label=r"$s_{\rm engage}$")
    shift_axis.axhline(constants.max_shift * 1.0e3, linestyle="--", label=r"$s_{\rm high}$")
    shift_axis.set_title("Shift coordinate and physical boundaries")
    shift_axis.set_xlabel("Time [s]")
    shift_axis.set_ylabel("Shift coordinate [mm]")
    shift_axis.grid(True, alpha=0.25)
    shift_speed_axis = shift_axis.twinx()
    shift_speed_axis.plot(time, state[4] * 1.0e3, linestyle=":", label=r"$\dot{s}$")
    shift_speed_axis.set_ylabel("Shift speed [mm/s]")
    handles, labels = shift_axis.get_legend_handles_labels()
    handles2, labels2 = shift_speed_axis.get_legend_handles_labels()
    shift_axis.legend(handles + handles2, labels + labels2, loc="best")

    curve_axis = axes[0, 2]
    curve_axis.plot(rpm_primary, rpm_secondary, label="trajectory")
    curve_axis.scatter([rpm_primary[0]], [rpm_secondary[0]], marker="o", label="launch")
    for record in result.transitions:
        event_state = _transition_state(result, record)
        point = event_state[:2] * _RPM_PER_RADIAN_PER_SECOND
        curve_axis.scatter([point[0]], [point[1]], marker="x")
        curve_axis.annotate(
            _short_transition_label(record.transition.reason),
            xy=(point[0], point[1]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    curve_axis.set_title("Shift curve: secondary vs primary speed")
    curve_axis.set_xlabel("Primary speed [rpm]")
    curve_axis.set_ylabel("Secondary speed [rpm]")
    curve_axis.grid(True, alpha=0.25)
    curve_axis.legend(loc="best")

    surface_axis = axes[1, 0]
    surface_axis.plot(time, state[2], label=r"$v_b$")
    surface_axis.plot(time, trace.primary_surface_speed, label=r"$r_p\omega_p$")
    surface_axis.plot(time, trace.secondary_surface_speed, label=r"$r_s\omega_s$")
    surface_axis.set_title("Belt and pulley surface speeds")
    surface_axis.set_xlabel("Time [s]")
    surface_axis.set_ylabel("Tangential speed [m/s]")
    surface_axis.grid(True, alpha=0.25)
    surface_axis.legend(loc="best")

    torque_axis = axes[1, 1]
    torque_axis.plot(time, trace.primary_torque, label=r"$\tau_p$")
    torque_axis.plot(time, trace.secondary_torque, label=r"$\tau_s$")
    torque_axis.set_title("Engaged torque path")
    torque_axis.set_xlabel("Time [s]")
    torque_axis.set_ylabel("Torque [N m]")
    torque_axis.grid(True, alpha=0.25)
    torque_axis.legend(loc="best")

    lambda_axis = axes[1, 2]
    lambda_axis.plot(time, trace.primary_lambda, label=r"$\lambda_p$")
    lambda_axis.plot(time, trace.secondary_lambda, label=r"$\lambda_s$")
    lambda_axis.axhline(configuration.static_lambda_limit, linestyle="--", label="static bounds")
    lambda_axis.axhline(-configuration.static_lambda_limit, linestyle="--")
    lambda_axis.set_title("Contact traction utilization")
    lambda_axis.set_xlabel("Time [s]")
    lambda_axis.set_ylabel(r"$\lambda$ [-]")
    lambda_axis.grid(True, alpha=0.25)
    lambda_axis.legend(loc="best")

    normal_axis = axes[2, 0]
    normal_axis.plot(time, trace.primary_normal, label=r"$N_p$")
    normal_axis.plot(time, trace.secondary_normal, label=r"$N_s$")
    normal_axis.set_title("Normal resultants")
    normal_axis.set_xlabel("Time [s]")
    normal_axis.set_ylabel("Resultant [N]")
    normal_axis.grid(True, alpha=0.25)
    normal_axis.legend(loc="best")

    relative_axis = axes[2, 1]
    relative_axis.plot(time, trace.primary_relative_speed, label=r"$v_{\rm rel,p}$")
    relative_axis.plot(time, trace.secondary_relative_speed, label=r"$v_{\rm rel,s}$")
    relative_axis.axhline(0.0, linestyle=":")
    relative_axis.set_title("Engaged contact relative speeds")
    relative_axis.set_xlabel("Time [s]")
    relative_axis.set_ylabel("Relative speed [m/s]")
    relative_axis.grid(True, alpha=0.25)
    relative_axis.legend(loc="best")

    reaction_axis = axes[2, 2]
    reaction_axis.plot(time, trace.stop_reaction, label="active stop reaction")
    reaction_axis.axhline(0.0, linestyle=":")
    reaction_axis.set_title("Unilateral stop reaction")
    reaction_axis.set_xlabel("Time [s]")
    reaction_axis.set_ylabel("Reaction [N]")
    reaction_axis.grid(True, alpha=0.25)
    reaction_axis.legend(loc="best")

    _add_transition_markers(
        axes=(
            speed_axis,
            shift_axis,
            surface_axis,
            torque_axis,
            lambda_axis,
            normal_axis,
            relative_axis,
            reaction_axis,
        ),
        result=result,
    )
    figure.suptitle(
        "CINDER full launch diagnostic: deadzone launch, engaged shift, and upper-stop continuation",
        fontsize=15,
    )
    return figure


def print_summary(
    *,
    result,
    trace: LaunchTrace,
    configuration: LaunchConfiguration,
    tuning: PrimaryTuningResult,
) -> None:
    initial_rpm = trace.state[:2, 0] * _RPM_PER_RADIAN_PER_SECOND
    final_rpm = result.final_state[:2] * _RPM_PER_RADIAN_PER_SECOND
    reasons = tuple(record.transition.reason for record in result.transitions)
    expected = {
        "engagement": any("primary_closed_into_engaged_contact" in reason for reason in reasons),
        "upper stop": any("upper_stop_reached" in reason for reason in reasons),
    }
    print("\n" + "=" * 108)
    print("CINDER full launch trajectory")
    print("=" * 108)
    print(
        "Diagnostic configuration: "
        f"primary(0)={configuration.initial_primary_rpm:.1f} rpm; "
        f"flyweight mass={configuration.flyweight_mass:.3f} kg; "
        f"ramp={configuration.primary_ramp_angle_degrees:.2f} deg; "
        f"spring rate={configuration.primary_spring_rate:.1f} N/m; "
        f"resolved preload={tuning.resolved_preload * 1e3:.3f} mm."
    )
    if tuning.target_lower_stop_release_rpm is not None:
        print(
            "Primary lower-stop release target: "
            f"{tuning.target_lower_stop_release_rpm:.1f} rpm; "
            f"recovered force={tuning.lower_stop_force_at_target:+.3e} N."
        )
    print(
        "This is intentionally upshift-biased to exercise the full hybrid path; "
        "it is not a calibrated hardware prediction."
    )
    print(
        f"Integration: completed={result.completed}; reason={result.termination_reason}; "
        f"segments={len(result.segments)}; final t={result.final_time:.6f} s."
    )
    print(
        f"Shaft speeds: primary {initial_rpm[0]:.1f} -> {final_rpm[0]:.1f} rpm; "
        f"secondary {initial_rpm[1]:.1f} -> {final_rpm[1]:.1f} rpm."
    )
    print(
        f"Shift: {trace.state[3, 0] * 1e3:.3f} -> {result.final_state[3] * 1e3:.3f} mm; "
        f"final shift speed={result.final_state[4] * 1e3:+.5f} mm/s."
    )
    print(
        "Expected sequence coverage: " + ", ".join(
            f"{name}={'PASS' if observed else 'NOT OBSERVED'}"
            for name, observed in expected.items()
        )
    )
    if result.transitions:
        print("Transitions:")
        for record in result.transitions:
            next_mode = "terminal" if record.transition.next_mode is None else _mode_label(record.transition.next_mode)
            print(
                f"  t={record.time:.6f} s | events={','.join(record.fired_event_names)} | "
                f"{record.transition.reason} -> {next_mode}"
            )
    else:
        print("Transitions: none")


def main() -> None:
    args = parse_arguments()
    configuration = LaunchConfiguration(
        duration_seconds=args.duration_s,
        initial_primary_rpm=args.initial_primary_rpm,
        flyweight_mass=args.flyweight_mass_kg,
        primary_preload=args.primary_preload_mm * 1.0e-3,
        primary_ramp_angle_degrees=args.primary_ramp_angle_deg,
        primary_spring_rate=args.primary_spring_rate_n_per_m,
        target_lower_stop_release_rpm=args.target_lower_stop_release_rpm,
        static_lambda_limit=args.static_lambda_limit,
        kinetic_lambda_magnitude=args.kinetic_lambda,
        maximum_step=args.max_step_ms * 1.0e-3,
        diagnostic_samples=args.diagnostic_samples,
    )
    system, launch_state, constants, tuning = build_launch_system(configuration)
    result = system.integrate(
        time_span=(0.0, configuration.duration_seconds),
        initial_state=launch_state,
        settings=HybridIntegratorSettings(
            relative_tolerance=3.0e-5,
            absolute_tolerance=1.0e-7,
            max_step=configuration.maximum_step,
            maximum_transitions=100,
        ),
    )
    trace = sample_launch_trace(
        system=system,
        result=result,
        maximum_samples=configuration.diagnostic_samples,
    )
    print_summary(result=result, trace=trace, configuration=configuration, tuning=tuning)
    figure = plot_launch_trace(
        trace=trace,
        result=result,
        constants=constants,
        configuration=configuration,
    )
    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180)
        print(f"Saved {args.save}")
    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
