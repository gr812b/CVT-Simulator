"""Run a one-second engaged CVT transient from a shift-hold preload trim.

This is an exploratory long-time diagnostic, not a shift controller. It first
chooses one physical primary-spring preload that makes the *initial*
stick--stick shift acceleration zero, then releases the ordinary hybrid
engaged model for one second. The result makes the coupled shaft-speed and
contact-branch evolution visible on a time scale where millisecond previews
were too short to be informative.

The current engaged model includes physical travel-stop guards. A stop is
terminal until a separate constrained stop-reaction / impact branch is added.
For this diagnostic the lower stop is placed just above the unimplemented
pre-engagement deadzone, while the upper stop remains the geometry maximum.

Run from cvtModel/:

    python tools/preview_one_second_engaged_trajectory.py
    python tools/preview_one_second_engaged_trajectory.py --target-s-ddot 5
    python tools/preview_one_second_engaged_trajectory.py --save artifacts/one_second.png --no-show
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if (_candidate / "cinder").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import BajaTrialConstants  # noqa: E402
from cinder.contact import (
    ContactKinematicTolerances,
    ContactRegime,
    ContactTractionLaw,
)  # noqa: E402
from cinder.dynamics import (
    EngagedContactSolveSettings,
    LambdaSearchBounds,
)  # noqa: E402
from cinder.integration import (
    EngagedShiftTravelLimits,
    HybridIntegratorSettings,
)  # noqa: E402
from cinder.integration.cvt_hybrid import EngagedCVTHybridSystem  # noqa: E402
from trim_shift_operating_point import (  # noqa: E402
    sample_trajectory,
    solve_primary_preload_trim,
)

_RPM_PER_RADIAN_PER_SECOND = 60.0 / (2.0 * np.pi)
_DEFAULT_STATIC_LIMIT = 0.65
_DEFAULT_KINETIC_LAMBDA = 0.55
_DEFAULT_TARGET_SHIFT_ACCELERATION = 0.0
_DEFAULT_DURATION_SECONDS = 1.0
_DEFAULT_MAX_STEP_MILLISECONDS = 5.0
_DEFAULT_LOWER_STOP_OFFSET_MILLIMETRES = 0.10
_DEFAULT_STICK_ACCELERATION_TOLERANCE = 1.0e-6
_DEFAULT_PLOT_SAMPLES = 600


@dataclass(frozen=True, slots=True)
class LongRunConfiguration:
    """Resolved physical/numerical settings printed with the trace."""

    duration_seconds: float
    static_limit: float
    kinetic_lambda: float
    target_shift_acceleration: float
    lower_stop: float
    upper_stop: float
    stick_acceleration_tolerance: float


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview a one-second, trimmed engaged-CVT hybrid trajectory."
    )
    parser.add_argument(
        "--duration-s",
        type=float,
        default=_DEFAULT_DURATION_SECONDS,
        help="Requested trajectory duration [s].",
    )
    parser.add_argument(
        "--target-s-ddot",
        type=float,
        default=_DEFAULT_TARGET_SHIFT_ACCELERATION,
        help="Initial shift trim target [m/s^2]; positive is primary-closing upshift.",
    )
    parser.add_argument(
        "--static-limit",
        type=float,
        default=_DEFAULT_STATIC_LIMIT,
        help="Symmetric physical static lambda limit.",
    )
    parser.add_argument(
        "--kinetic-lambda",
        type=float,
        default=_DEFAULT_KINETIC_LAMBDA,
        help="Positive kinetic lambda magnitude for later slip branches.",
    )
    parser.add_argument(
        "--lower-stop-offset-mm",
        type=float,
        default=_DEFAULT_LOWER_STOP_OFFSET_MILLIMETRES,
        help=(
            "Distance placed above deadzone for the temporary engaged-only lower "
            "physical stop [mm]."
        ),
    )
    parser.add_argument(
        "--max-step-ms",
        type=float,
        default=_DEFAULT_MAX_STEP_MILLISECONDS,
        help="Maximum solve_ivp step [ms].",
    )
    parser.add_argument(
        "--stick-acceleration-tolerance",
        type=float,
        default=_DEFAULT_STICK_ACCELERATION_TOLERANCE,
        help=(
            "Acceleration-level stick residual tolerance [m/s^2]. A value of 1e-6 "
            "keeps the long continuation accurate while avoiding needless repeated "
            "sub-nanoscopic lambda root refinements."
        ),
    )
    parser.add_argument(
        "--plot-samples",
        type=int,
        default=_DEFAULT_PLOT_SAMPLES,
        help="Maximum diagnostic samples evaluated for the dashboard.",
    )
    parser.add_argument("--save", type=Path, help="Optional PNG/PDF/SVG output path.")
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Build and optionally save the figure without opening a window.",
    )
    args = parser.parse_args()

    for name, value in (
        ("--duration-s", args.duration_s),
        ("--target-s-ddot", args.target_s_ddot),
        ("--static-limit", args.static_limit),
        ("--kinetic-lambda", args.kinetic_lambda),
        ("--lower-stop-offset-mm", args.lower_stop_offset_mm),
        ("--max-step-ms", args.max_step_ms),
        ("--stick-acceleration-tolerance", args.stick_acceleration_tolerance),
    ):
        if not isfinite(value):
            parser.error(f"{name} must be finite.")
    if args.duration_s <= 0.0:
        parser.error("--duration-s must be strictly positive.")
    if args.static_limit <= 0.0 or args.kinetic_lambda <= 0.0:
        parser.error("--static-limit and --kinetic-lambda must be strictly positive.")
    if args.lower_stop_offset_mm < 0.0:
        parser.error("--lower-stop-offset-mm must be non-negative.")
    if args.max_step_ms <= 0.0:
        parser.error("--max-step-ms must be strictly positive.")
    if args.stick_acceleration_tolerance <= 0.0:
        parser.error("--stick-acceleration-tolerance must be strictly positive.")
    if args.plot_samples < 40:
        parser.error("--plot-samples must be at least 40.")
    return args


def main() -> None:
    args = parse_arguments()
    constants = BajaTrialConstants()
    traction_law = ContactTractionLaw.symmetric(
        primary_static_lambda_limit=args.static_limit,
        secondary_static_lambda_limit=args.static_limit,
        primary_kinetic_lambda_magnitude=args.kinetic_lambda,
        secondary_kinetic_lambda_magnitude=args.kinetic_lambda,
    )

    operating_point = solve_primary_preload_trim(
        reference_constants=constants,
        traction_law=traction_law,
        target_shift_acceleration=args.target_s_ddot,
        preload_min=0.0,
        preload_max=constants.primary_spring_initial_compression,
        scan_points=41,
    )
    lower_stop = (
        operating_point.baseline.constants.deadzone_shift
        + args.lower_stop_offset_mm * 1.0e-3
    )
    upper_stop = operating_point.baseline.constants.max_shift
    limits = EngagedShiftTravelLimits(
        minimum_shift=lower_stop,
        maximum_shift=upper_stop,
    )
    limits.validate_against_geometry_spec(operating_point.baseline.model.geometry.spec)

    contact_tolerances = ContactKinematicTolerances(
        relative_speed_tolerance=1.0e-7,
        relative_acceleration_tolerance=1.0e-7,
        stick_acceleration_tolerance=args.stick_acceleration_tolerance,
    )
    system = EngagedCVTHybridSystem(
        model=operating_point.baseline.model,
        traction_law=traction_law,
        solve_settings=EngagedContactSolveSettings(
            lambda_search_bounds=LambdaSearchBounds.symmetric(
                primary_half_width=2.0,
                secondary_half_width=2.0,
            ),
            initial_guess=operating_point.evaluation.traction_utilization,
            contact_tolerances=contact_tolerances,
            maximum_closure_condition_number=1.0e8,
        ),
        shift_travel_limits=limits,
    )

    result = system.integrate(
        time_span=(0.0, args.duration_s),
        initial_state=operating_point.state,
        initial_regime=ContactRegime.stick_stick(),
        settings=HybridIntegratorSettings(
            method="RK45",
            relative_tolerance=1.0e-6,
            absolute_tolerance=1.0e-8,
            max_step=args.max_step_ms * 1.0e-3,
            maximum_transitions=100,
        ),
    )
    trace = sample_trajectory(
        system=system,
        result=result,
        maximum_samples=args.plot_samples,
    )
    configuration = LongRunConfiguration(
        duration_seconds=args.duration_s,
        static_limit=args.static_limit,
        kinetic_lambda=args.kinetic_lambda,
        target_shift_acceleration=args.target_s_ddot,
        lower_stop=lower_stop,
        upper_stop=upper_stop,
        stick_acceleration_tolerance=args.stick_acceleration_tolerance,
    )
    print_summary(
        configuration=configuration,
        operating_point=operating_point,
        result=result,
        trace=trace,
    )

    figure = plot_trace(
        configuration=configuration,
        trace=trace,
        result=result,
    )
    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180)
        print(f"Saved {args.save}")
    if not args.no_show:
        plt.show()


def print_summary(
    *, configuration: LongRunConfiguration, operating_point, result, trace
) -> None:
    initial = operating_point.state.as_vector()
    final = result.final_state
    initial_rpm = initial[:2] * _RPM_PER_RADIAN_PER_SECOND
    final_rpm = final[:2] * _RPM_PER_RADIAN_PER_SECOND
    modes = tuple(dict.fromkeys(trace.mode_label))

    print("\n" + "=" * 108)
    print("CINDER one-second engaged trajectory preview")
    print("=" * 108)
    print(
        f"Initial trim: target s_ddot={configuration.target_shift_acceleration:+.6f} m/s^2; "
        f"primary preload={operating_point.preload * 1e3:.3f} mm."
    )
    print(
        "Physical free-travel interval: "
        f"s_min={configuration.lower_stop * 1e3:.3f} mm, "
        f"s_max={configuration.upper_stop * 1e3:.3f} mm. "
        "Stops are terminal guards until constrained stop-reaction dynamics are added."
    )
    print(
        f"Integration: completed={result.completed}; reason={result.termination_reason}; "
        f"final t={result.final_time:.6f} s; segments={len(result.segments)}; "
        f"transitions={len(result.transitions)}."
    )
    print(
        "Shaft speeds: "
        f"omega_p={initial_rpm[0]:.1f} -> {final_rpm[0]:.1f} rpm "
        f"(delta={final_rpm[0] - initial_rpm[0]:+.1f}); "
        f"omega_s={initial_rpm[1]:.1f} -> {final_rpm[1]:.1f} rpm "
        f"(delta={final_rpm[1] - initial_rpm[1]:+.1f})."
    )
    print(
        "Shift: "
        f"s={initial[3] * 1e3:.3f} -> {final[3] * 1e3:.3f} mm; "
        f"s_dot(final)={final[4] * 1e3:+.3f} mm/s; "
        f"s_ddot range=[{trace.shift_acceleration.min():+.3f}, "
        f"{trace.shift_acceleration.max():+.3f}] m/s^2."
    )
    print(
        "Contact ranges: "
        f"lambda_p=[{trace.lambda_primary.min():+.4f}, {trace.lambda_primary.max():+.4f}], "
        f"lambda_s=[{trace.lambda_secondary.min():+.4f}, {trace.lambda_secondary.max():+.4f}]; "
        f"N_p,min={trace.normal_primary.min():.2f} N; "
        f"N_s,min={trace.normal_secondary.min():.2f} N."
    )
    print(f"Modes visited: {', '.join(modes)}.")
    if result.transitions:
        print("Transitions:")
        for record in result.transitions:
            next_mode = (
                "terminal"
                if record.transition.next_mode is None
                else record.transition.next_mode.mode.value
            )
            print(
                f"  t={record.time:.6f} s | events={','.join(record.fired_event_names)} "
                f"| {record.transition.reason} -> {next_mode}"
            )
    else:
        print("Transitions: none")


def plot_trace(*, configuration: LongRunConfiguration, trace, result):
    time = trace.time
    state = trace.state
    figure, axes = plt.subplots(3, 2, figsize=(16, 13), constrained_layout=True)

    ax = axes[0, 0]
    ax.plot(time, state[0] * _RPM_PER_RADIAN_PER_SECOND, label=r"$\omega_p$")
    ax.plot(time, state[1] * _RPM_PER_RADIAN_PER_SECOND, label=r"$\omega_s$")
    ax.set_title("Shaft-speed evolution")
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Shaft speed [rpm]")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")

    ax = axes[0, 1]
    ax.plot(time, state[3] * 1e3, label=r"$s$")
    ax.axhline(configuration.lower_stop * 1e3, linestyle="--", label=r"$s_{\min}$")
    ax.axhline(configuration.upper_stop * 1e3, linestyle="--", label=r"$s_{\max}$")
    ax.set_title("Physical shift travel")
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Shift coordinate [mm]")
    ax.grid(True, alpha=0.25)
    twin = ax.twinx()
    twin.plot(time, state[4] * 1e3, linestyle=":", label=r"$\dot s$")
    twin.set_ylabel("Shift speed [mm/s]")
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = twin.get_legend_handles_labels()
    ax.legend(handles + handles2, labels + labels2, loc="best")

    ax = axes[1, 0]
    ax.plot(time, trace.torque_primary, label=r"$\tau_p$")
    ax.plot(time, trace.torque_secondary, label=r"$\tau_s$")
    ax.set_title("Transmitted torque path")
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Torque [N m]")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")

    ax = axes[1, 1]
    ax.plot(time, trace.lambda_primary, label=r"$\lambda_p$")
    ax.plot(time, trace.lambda_secondary, label=r"$\lambda_s$")
    ax.axhline(configuration.static_limit, linestyle="--", label="static limits")
    ax.axhline(-configuration.static_limit, linestyle="--")
    ax.set_title("Contact traction ratio")
    ax.set_xlabel("Time [s]")
    ax.set_ylabel(r"$\lambda$ [-]")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")

    ax = axes[2, 0]
    ax.plot(time, trace.normal_primary, label=r"$N_p$")
    ax.plot(time, trace.normal_secondary, label=r"$N_s$")
    ax.set_title("Normal resultants")
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Normal resultant [N]")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")

    ax = axes[2, 1]
    ax.plot(time, trace.relative_speed_primary, label=r"$v_{\mathrm{rel},p}$")
    ax.plot(time, trace.relative_speed_secondary, label=r"$v_{\mathrm{rel},s}$")
    ax.axhline(0.0, linestyle=":")
    for record in result.transitions:
        ax.axvline(record.time, linestyle="--", linewidth=1.1)
    ax.set_title("Contact relative speeds and transitions")
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Relative speed [m/s]")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")

    figure.suptitle(
        "CINDER engaged trajectory: initial shift-hold trim released for long-time dynamics",
        fontsize=15,
    )
    return figure


if __name__ == "__main__":
    main()
