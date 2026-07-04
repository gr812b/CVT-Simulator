"""Run short engaged-CVT hybrid trajectories and inspect branch physics.

This is a diagnostic harness for the current engaged-contact hybrid model.  It
is intentionally not a vehicle-launch prediction yet: the deadzone/contact-loss
regimes remain terminal guards, and several baseline actuation numbers are still
provisional.  Its job is to confirm that the segmented solver, branch changes,
contact directions, and closure outputs remain interpretable *through time*.

Run from ``cvtModel/``::

    python tools/preview_engaged_hybrid_trajectory.py
    python tools/preview_engaged_hybrid_trajectory.py --scenario all
    python tools/preview_engaged_hybrid_trajectory.py --scenario primary-slip \
        --duration-ms 2 --save artifacts/primary_slip.png --no-show

The default one-millisecond window is deliberate.  The current Baja-ish
baseline has very aggressive provisional axial dynamics, so a short window
shows the contact logic before the trajectory reaches the unimplemented
engagement boundary.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import sys
from typing import Iterable

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
from numpy.typing import NDArray

# Support both ``src/cinder`` repositories and direct-package overlays.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (
    _REPOSITORY_ROOT / "src",
    _REPOSITORY_ROOT,
    _REPOSITORY_ROOT / "tools",
):
    if (_candidate / "cinder").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))
if str(_REPOSITORY_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT / "tools"))

from baja_trial_baseline import BajaTrialBaseline, build_baja_trial_baseline
from cinder.contact import ContactTractionLaw, ContactTractionUtilization
from cinder.dynamics import EngagedContactSolveSettings, LambdaSearchBounds
from cinder.integration import CVTDynamicState, HybridIntegratorSettings
from cinder.integration.cvt_hybrid import EngagedCVTHybridSystem


_DEFAULT_DURATION_MS = 1.0
_DEFAULT_MAX_STEP_US = 20.0
_DEFAULT_STATIC_LIMIT = 0.65
_DEFAULT_KINETIC_LAMBDA = 0.55
_DEFAULT_WIDE_STATIC_LIMIT = 2.0
_DEFAULT_WIDE_KINETIC_LAMBDA = 1.4
_DEFAULT_ESTABLISHED_SLIP_SPEED = 0.25
_DEFAULT_PLOT_SAMPLES = 240

_SCENARIOS = (
    "baseline",
    "wide-static",
    "primary-slip",
    "secondary-slip",
    "both-slip",
)


@dataclass(frozen=True, slots=True)
class Scenario:
    """One short integration case with a known contact-state intention."""

    key: str
    title: str
    description: str
    initial_state: CVTDynamicState
    traction_law: ContactTractionLaw


@dataclass(frozen=True, slots=True)
class TrajectoryTrace:
    """Sampled continuous-state and closure diagnostics over hybrid segments."""

    time: NDArray[np.float64]
    state: NDArray[np.float64]
    mode_code: NDArray[np.int_]
    mode_label: tuple[str, ...]
    lambda_primary: NDArray[np.float64]
    lambda_secondary: NDArray[np.float64]
    torque_primary: NDArray[np.float64]
    torque_secondary: NDArray[np.float64]
    normal_primary: NDArray[np.float64]
    normal_secondary: NDArray[np.float64]
    relative_speed_primary: NDArray[np.float64]
    relative_speed_secondary: NDArray[np.float64]
    relative_acceleration_primary: NDArray[np.float64]
    relative_acceleration_secondary: NDArray[np.float64]
    primary_dissipation: NDArray[np.float64]
    secondary_dissipation: NDArray[np.float64]
    closure_condition_number: NDArray[np.float64]


_MODE_CODE = {
    "stick_stick": 0,
    "primary_slip_secondary_stick": 1,
    "primary_stick_secondary_slip": 2,
    "both_slip": 3,
}
_MODE_DISPLAY = {
    0: "stick / stick",
    1: "primary slip / secondary stick",
    2: "primary stick / secondary slip",
    3: "slip / slip",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview short trajectories through the engaged-CVT hybrid contact solver."
    )
    parser.add_argument(
        "--scenario",
        choices=(*_SCENARIOS, "all"),
        default="baseline",
        help="Diagnostic initial condition to run.",
    )
    parser.add_argument(
        "--duration-ms",
        type=float,
        default=_DEFAULT_DURATION_MS,
        help="Integration duration in milliseconds.",
    )
    parser.add_argument(
        "--max-step-us",
        type=float,
        default=_DEFAULT_MAX_STEP_US,
        help="Maximum solve_ivp step in microseconds.",
    )
    parser.add_argument(
        "--static-limit",
        type=float,
        default=_DEFAULT_STATIC_LIMIT,
        help="Symmetric physical static lambda limit for ordinary diagnostic cases.",
    )
    parser.add_argument(
        "--kinetic-lambda",
        type=float,
        default=_DEFAULT_KINETIC_LAMBDA,
        help="Positive kinetic lambda magnitude for ordinary diagnostic cases.",
    )
    parser.add_argument(
        "--wide-static-limit",
        type=float,
        default=_DEFAULT_WIDE_STATIC_LIMIT,
        help="Static lambda limit used only by the wide-static stick case.",
    )
    parser.add_argument(
        "--wide-kinetic-lambda",
        type=float,
        default=_DEFAULT_WIDE_KINETIC_LAMBDA,
        help="Kinetic lambda magnitude used only by the wide-static stick case.",
    )
    parser.add_argument(
        "--established-slip-speed",
        type=float,
        default=_DEFAULT_ESTABLISHED_SLIP_SPEED,
        help="Magnitude of deliberately imposed relative speed for slip cases [m/s].",
    )
    parser.add_argument(
        "--plot-samples",
        type=int,
        default=_DEFAULT_PLOT_SAMPLES,
        help="Maximum closure-diagnostic samples retained for plotting.",
    )
    parser.add_argument(
        "--save",
        type=Path,
        help=(
            "Optional output path. With --scenario all, this is treated as a directory "
            "unless it already has an image suffix."
        ),
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Build figures without opening matplotlib windows.",
    )
    args = parser.parse_args()

    for name, value in (
        ("--duration-ms", args.duration_ms),
        ("--max-step-us", args.max_step_us),
        ("--static-limit", args.static_limit),
        ("--kinetic-lambda", args.kinetic_lambda),
        ("--wide-static-limit", args.wide_static_limit),
        ("--wide-kinetic-lambda", args.wide_kinetic_lambda),
        ("--established-slip-speed", args.established_slip_speed),
    ):
        if not isfinite(value) or value <= 0.0:
            parser.error(f"{name} must be finite and strictly positive.")
    if args.plot_samples < 12:
        parser.error("--plot-samples must be at least 12.")
    return args


def main() -> None:
    args = parse_arguments()
    baseline = build_baja_trial_baseline()
    scenarios = build_scenarios(baseline=baseline, args=args)
    selected = (
        scenarios.values() if args.scenario == "all" else (scenarios[args.scenario],)
    )

    figures = []
    for scenario in selected:
        system = build_hybrid_system(
            baseline=baseline,
            traction_law=scenario.traction_law,
        )
        initial_regime = system.classify_initial_regime(scenario.initial_state)
        result = system.integrate(
            time_span=(0.0, args.duration_ms * 1.0e-3),
            initial_state=scenario.initial_state,
            initial_regime=initial_regime,
            settings=HybridIntegratorSettings(
                max_step=args.max_step_us * 1.0e-6,
                maximum_transitions=80,
            ),
        )
        trace = sample_trajectory(
            system=system,
            result=result,
            maximum_samples=args.plot_samples,
        )
        print_case_summary(
            scenario=scenario,
            system=system,
            initial_regime=initial_regime,
            result=result,
            trace=trace,
        )
        figure = plot_case(
            scenario=scenario,
            result=result,
            trace=trace,
        )
        figures.append((scenario.key, figure))

    save_figures(figures=figures, path=args.save, all_cases=args.scenario == "all")
    if not args.no_show:
        plt.show()


def build_scenarios(
    *, baseline: BajaTrialBaseline, args: argparse.Namespace
) -> dict[str, Scenario]:
    """Build no-slip, one-slip, and two-slip diagnostics from one base state."""

    base = baseline.quasi_static_state
    snapshot = baseline.model.snapshot(state=base)
    r_primary = snapshot.geometry.primary.effective
    r_secondary = snapshot.geometry.secondary.effective
    slip_speed = args.established_slip_speed

    ordinary_law = ContactTractionLaw.symmetric(
        primary_static_lambda_limit=args.static_limit,
        secondary_static_lambda_limit=args.static_limit,
        primary_kinetic_lambda_magnitude=args.kinetic_lambda,
        secondary_kinetic_lambda_magnitude=args.kinetic_lambda,
    )
    wide_law = ContactTractionLaw.symmetric(
        primary_static_lambda_limit=args.wide_static_limit,
        secondary_static_lambda_limit=args.wide_static_limit,
        primary_kinetic_lambda_magnitude=args.wide_kinetic_lambda,
        secondary_kinetic_lambda_magnitude=args.wide_kinetic_lambda,
    )

    # Preserve the baseline belt speed while choosing shaft speeds that create
    # exactly the intended initial v_rel at each selected contact.
    primary_only = replace_state(
        base,
        primary_angular_speed=(base.belt_speed + slip_speed) / r_primary,
    )
    secondary_only = replace_state(
        base,
        secondary_angular_speed=(base.belt_speed - slip_speed) / r_secondary,
    )
    both_forward = replace_state(
        base,
        primary_angular_speed=(base.belt_speed + slip_speed) / r_primary,
        secondary_angular_speed=(base.belt_speed - slip_speed) / r_secondary,
    )

    return {
        "baseline": Scenario(
            key="baseline",
            title="Baseline: traction-limited engaged state",
            description=(
                "Start from the nominal engaged, zero-relative-speed state with the "
                "ordinary tentative static limit. The initial classifier should expose "
                "whether stick-stick is physically admissible."
            ),
            initial_state=base,
            traction_law=ordinary_law,
        ),
        "wide-static": Scenario(
            key="wide-static",
            title="Wide-static diagnostic: stick-stick demand allowed",
            description=(
                "Use a deliberately broad physical static interval so the known "
                "stick-stick lambda demand can remain adhered. This isolates the "
                "sticking branch and fixed-ratio transient response."
            ),
            initial_state=base,
            traction_law=wide_law,
        ),
        "primary-slip": Scenario(
            key="primary-slip",
            title="Established primary slip: primary pulley leads belt",
            description=(
                "Keep the secondary initially speed-matched to the belt and make the "
                "primary surface faster by the selected relative-slip speed."
            ),
            initial_state=primary_only,
            traction_law=ordinary_law,
        ),
        "secondary-slip": Scenario(
            key="secondary-slip",
            title="Established secondary slip: belt leads secondary pulley",
            description=(
                "Keep the primary initially speed-matched to the belt and make the "
                "belt faster than the secondary surface by the selected slip speed."
            ),
            initial_state=secondary_only,
            traction_law=ordinary_law,
        ),
        "both-slip": Scenario(
            key="both-slip",
            title="Established two-contact forward slip",
            description=(
                "Primary pulley initially leads the belt while the belt initially leads "
                "the secondary. This directly exercises the kinetic 8x8 branch at both contacts."
            ),
            initial_state=both_forward,
            traction_law=ordinary_law,
        ),
    }


def build_hybrid_system(
    *,
    baseline: BajaTrialBaseline,
    traction_law: ContactTractionLaw,
) -> EngagedCVTHybridSystem:
    """Construct one engaged-contact hybrid adapter with broad numerical bounds."""

    solve_settings = EngagedContactSolveSettings(
        lambda_search_bounds=LambdaSearchBounds.symmetric(
            primary_half_width=2.0,
            secondary_half_width=2.0,
        ),
        initial_guess=ContactTractionUtilization(
            primary_lambda=0.0,
            secondary_lambda=0.0,
        ),
        maximum_closure_condition_number=1.0e8,
    )
    return EngagedCVTHybridSystem(
        model=baseline.model,
        traction_law=traction_law,
        solve_settings=solve_settings,
    )


def replace_state(
    state: CVTDynamicState,
    *,
    primary_angular_speed: float | None = None,
    secondary_angular_speed: float | None = None,
    belt_speed: float | None = None,
) -> CVTDynamicState:
    """Return a copy after replacing selected continuous velocity components."""

    return CVTDynamicState(
        primary_angular_speed=(
            state.primary_angular_speed
            if primary_angular_speed is None
            else primary_angular_speed
        ),
        secondary_angular_speed=(
            state.secondary_angular_speed
            if secondary_angular_speed is None
            else secondary_angular_speed
        ),
        belt_speed=state.belt_speed if belt_speed is None else belt_speed,
        shift_position=state.shift_position,
        shift_speed=state.shift_speed,
        secondary_shaft_angle=state.secondary_shaft_angle,
    )


def sample_trajectory(
    *, system: EngagedCVTHybridSystem, result, maximum_samples: int
) -> TrajectoryTrace:
    """Evaluate branch diagnostics on a bounded number of actual ODE samples."""

    sample_plan = list(
        iter_segment_samples(result.segments, maximum_samples=maximum_samples)
    )
    count = len(sample_plan)
    time = np.empty(count)
    state = np.empty((6, count))
    mode_code = np.empty(count, dtype=int)
    labels: list[str] = []
    lambda_primary = np.empty(count)
    lambda_secondary = np.empty(count)
    torque_primary = np.empty(count)
    torque_secondary = np.empty(count)
    normal_primary = np.empty(count)
    normal_secondary = np.empty(count)
    relative_speed_primary = np.empty(count)
    relative_speed_secondary = np.empty(count)
    relative_acceleration_primary = np.empty(count)
    relative_acceleration_secondary = np.empty(count)
    primary_dissipation = np.empty(count)
    secondary_dissipation = np.empty(count)
    closure_condition = np.empty(count)

    for index, (mode, sample_time, sample_state) in enumerate(sample_plan):
        evaluation = system.evaluator.evaluate_vector(
            time=sample_time,
            vector=sample_state,
            regime=mode,
        )
        unknowns = evaluation.closure_unknowns
        geometry = evaluation.snapshot.geometry
        utilization = evaluation.traction_utilization
        relative = evaluation.relative_motion

        primary_belt_force = unknowns.primary_torque / geometry.primary.effective
        secondary_belt_force = -unknowns.secondary_torque / geometry.secondary.effective

        time[index] = sample_time
        state[:, index] = sample_state
        code = _MODE_CODE[mode.mode.value]
        mode_code[index] = code
        labels.append(_MODE_DISPLAY[code])
        lambda_primary[index] = utilization.primary_lambda
        lambda_secondary[index] = utilization.secondary_lambda
        torque_primary[index] = unknowns.primary_torque
        torque_secondary[index] = unknowns.secondary_torque
        normal_primary[index] = unknowns.primary_normal_resultant
        normal_secondary[index] = unknowns.secondary_normal_resultant
        relative_speed_primary[index] = relative.primary_relative_speed
        relative_speed_secondary[index] = relative.secondary_relative_speed
        relative_acceleration_primary[index] = relative.primary_relative_acceleration
        relative_acceleration_secondary[index] = (
            relative.secondary_relative_acceleration
        )
        primary_dissipation[index] = (
            -primary_belt_force * relative.primary_relative_speed
        )
        secondary_dissipation[index] = (
            -secondary_belt_force * relative.secondary_relative_speed
        )
        closure_condition[index] = (
            evaluation.branch_result.trial.closure.condition_number
        )

    return TrajectoryTrace(
        time=_freeze(time),
        state=_freeze(state),
        mode_code=_freeze(mode_code),
        mode_label=tuple(labels),
        lambda_primary=_freeze(lambda_primary),
        lambda_secondary=_freeze(lambda_secondary),
        torque_primary=_freeze(torque_primary),
        torque_secondary=_freeze(torque_secondary),
        normal_primary=_freeze(normal_primary),
        normal_secondary=_freeze(normal_secondary),
        relative_speed_primary=_freeze(relative_speed_primary),
        relative_speed_secondary=_freeze(relative_speed_secondary),
        relative_acceleration_primary=_freeze(relative_acceleration_primary),
        relative_acceleration_secondary=_freeze(relative_acceleration_secondary),
        primary_dissipation=_freeze(primary_dissipation),
        secondary_dissipation=_freeze(secondary_dissipation),
        closure_condition_number=_freeze(closure_condition),
    )


def iter_segment_samples(segments: Iterable, *, maximum_samples: int):
    """Yield endpoint-preserving samples, keeping each segment's active mode."""

    segments = tuple(segments)
    total_points = sum(segment.time.size for segment in segments)
    per_segment = max(4, maximum_samples // max(len(segments), 1))
    if total_points <= maximum_samples:
        per_segment = max(segment.time.size for segment in segments)

    for segment_index, segment in enumerate(segments):
        indices = endpoint_preserving_indices(segment.time.size, maximum=per_segment)
        # The event endpoint belongs to the preceding segment for diagnostics;
        # avoid duplicated state samples in following segments.
        if segment_index and indices.size and indices[0] == 0:
            indices = indices[1:]
        for index in indices:
            yield segment.mode, float(segment.time[index]), np.asarray(
                segment.state[:, index], dtype=float
            )


def endpoint_preserving_indices(count: int, *, maximum: int) -> NDArray[np.int_]:
    if count <= maximum:
        return np.arange(count, dtype=int)
    return np.unique(np.linspace(0, count - 1, maximum, dtype=int))


def print_case_summary(
    *,
    scenario: Scenario,
    system: EngagedCVTHybridSystem,
    initial_regime,
    result,
    trace: TrajectoryTrace,
) -> None:
    """Print the physical and hybrid checks that matter for one trajectory."""

    initial_evaluation = system.evaluator.evaluate_vector(
        time=0.0,
        vector=scenario.initial_state.as_vector(),
        regime=initial_regime,
    )
    print("\n" + "=" * 112)
    print(scenario.title)
    print(scenario.description)
    print("-" * 112)
    print(
        f"Initial regime: {_MODE_DISPLAY[_MODE_CODE[initial_regime.mode.value]]}; "
        f"initial v_rel=(p={initial_evaluation.relative_motion.primary_relative_speed:+.6e}, "
        f"s={initial_evaluation.relative_motion.secondary_relative_speed:+.6e}) m/s"
    )
    print(
        "Physical lambda intervals: "
        f"p=[{scenario.traction_law.primary_static_interval.lower:+.3f}, "
        f"{scenario.traction_law.primary_static_interval.upper:+.3f}], "
        f"s=[{scenario.traction_law.secondary_static_interval.lower:+.3f}, "
        f"{scenario.traction_law.secondary_static_interval.upper:+.3f}]; "
        f"kinetic magnitudes=(p={scenario.traction_law.primary_kinetic_lambda_magnitude:.3f}, "
        f"s={scenario.traction_law.secondary_kinetic_lambda_magnitude:.3f})"
    )
    print(
        f"Integration: completed={result.completed}; reason={result.termination_reason}; "
        f"segments={len(result.segments)}; transitions={len(result.transitions)}; "
        f"final t={result.final_time * 1e3:.6f} ms"
    )
    print(
        f"Final state: ω_p={result.final_state[0]:.6f} rad/s, "
        f"ω_s={result.final_state[1]:.6f} rad/s, v_b={result.final_state[2]:.6f} m/s, "
        f"s={result.final_state[3] * 1e3:.6f} mm, s_dot={result.final_state[4]:.6f} m/s"
    )

    if result.transitions:
        print("Transitions:")
        for record in result.transitions:
            next_label = (
                "terminal"
                if record.transition.next_mode is None
                else _MODE_DISPLAY[_MODE_CODE[record.transition.next_mode.mode.value]]
            )
            print(
                f"  t={record.time * 1e3: .6f} ms | events={','.join(record.fired_event_names)} "
                f"| {record.transition.reason} -> {next_label}"
            )
    else:
        print("Transitions: none")

    print("Sampled physical checks:")
    print(
        f"  normal resultants: N_p min={trace.normal_primary.min():.6f} N, "
        f"N_s min={trace.normal_secondary.min():.6f} N"
    )
    print(
        f"  closure condition number: min={trace.closure_condition_number.min():.3e}, "
        f"max={trace.closure_condition_number.max():.3e}"
    )
    print(
        f"  torque ranges: τ_p=[{trace.torque_primary.min():+.6f}, {trace.torque_primary.max():+.6f}] N m, "
        f"τ_s=[{trace.torque_secondary.min():+.6f}, {trace.torque_secondary.max():+.6f}] N m"
    )
    print(
        f"  λ ranges: λ_p=[{trace.lambda_primary.min():+.6f}, {trace.lambda_primary.max():+.6f}], "
        f"λ_s=[{trace.lambda_secondary.min():+.6f}, {trace.lambda_secondary.max():+.6f}]"
    )
    _print_dissipation_check(
        interface="primary",
        relative_speed=trace.relative_speed_primary,
        dissipation=trace.primary_dissipation,
    )
    _print_dissipation_check(
        interface="secondary",
        relative_speed=trace.relative_speed_secondary,
        dissipation=trace.secondary_dissipation,
    )


def _print_dissipation_check(
    *,
    interface: str,
    relative_speed: NDArray[np.float64],
    dissipation: NDArray[np.float64],
) -> None:
    slipping = np.abs(relative_speed) > 1.0e-7
    if not np.any(slipping):
        print(f"  {interface} contact: no established-slip samples in this window.")
        return
    minimum = float(np.min(dissipation[slipping]))
    maximum = float(np.max(dissipation[slipping]))
    verdict = "PASS" if minimum >= -1.0e-7 else "CHECK"
    print(
        f"  {interface} slip dissipation: [{minimum:+.6e}, {maximum:+.6e}] W "
        f"over established-slip samples -> {verdict} (expect non-negative)."
    )


def plot_case(*, scenario: Scenario, result, trace: TrajectoryTrace):
    """Build a compact diagnostic dashboard for one hybrid trajectory."""

    time_ms = trace.time * 1.0e3
    figure, axes = plt.subplots(3, 2, figsize=(15.5, 12.0), constrained_layout=True)
    ax_speed, ax_shift, ax_torque, ax_lambda, ax_relative, ax_normal = axes.flat

    ax_speed.plot(time_ms, trace.state[0] * 60.0 / (2.0 * np.pi), label=r"$\omega_p$")
    ax_speed.plot(time_ms, trace.state[1] * 60.0 / (2.0 * np.pi), label=r"$\omega_s$")
    ax_speed.set_title("Shaft speeds")
    ax_speed.set_ylabel("speed [rpm]")
    ax_speed.legend(loc="best")

    ax_shift.plot(time_ms, trace.state[3] * 1.0e3, label=r"$s$")
    ax_shift.set_title("Shift coordinate")
    ax_shift.set_ylabel(r"$s$ [mm]")
    shift_rate_axis = ax_shift.twinx()
    shift_rate_axis.plot(time_ms, trace.state[4], linestyle="--", label=r"$\dot{s}$")
    shift_rate_axis.set_ylabel(r"$\dot{s}$ [m/s]")
    _combined_legend(ax_shift, shift_rate_axis)

    ax_torque.plot(time_ms, trace.torque_primary, label=r"$\tau_p$")
    ax_torque.plot(time_ms, trace.torque_secondary, label=r"$\tau_s$")
    ax_torque.axhline(0.0, linewidth=1.0)
    ax_torque.set_title("Solved pulley torques")
    ax_torque.set_ylabel("torque [N m]")
    ax_torque.legend(loc="best")

    ax_lambda.plot(time_ms, trace.lambda_primary, label=r"$\lambda_p$")
    ax_lambda.plot(time_ms, trace.lambda_secondary, label=r"$\lambda_s$")
    for value, label in (
        (scenario.traction_law.primary_static_interval.upper, r"$+\lambda_{s,p}$"),
        (scenario.traction_law.primary_static_interval.lower, r"$-\lambda_{s,p}$"),
    ):
        ax_lambda.axhline(value, linestyle="--", linewidth=1.0, label=label)
    ax_lambda.set_title("Traction ratios and static capacity")
    ax_lambda.set_ylabel(r"$\lambda$ [-]")
    ax_lambda.legend(loc="best", ncols=2)

    ax_relative.plot(time_ms, trace.relative_speed_primary, label=r"$v_{rel,p}$")
    ax_relative.plot(time_ms, trace.relative_speed_secondary, label=r"$v_{rel,s}$")
    ax_relative.axhline(0.0, linewidth=1.0)
    ax_relative.set_title("Relative belt--pulley speed")
    ax_relative.set_ylabel("relative speed [m/s]")
    ax_relative.legend(loc="best")

    ax_normal.plot(time_ms, trace.normal_primary, label=r"$N_p$")
    ax_normal.plot(time_ms, trace.normal_secondary, label=r"$N_s$")
    ax_normal.set_title("Normal resultants")
    ax_normal.set_ylabel("normal resultant [N]")
    ax_normal.legend(loc="best")

    for axis in axes.flat:
        axis.set_xlabel("time [ms]")
        axis.grid(True, alpha=0.25)
        _mark_transitions(axis=axis, transitions=result.transitions)

    mode_axis = figure.add_axes((0.14, 0.015, 0.72, 0.018))
    mode_axis.imshow(
        trace.mode_code[np.newaxis, :],
        aspect="auto",
        interpolation="nearest",
        extent=(time_ms[0], time_ms[-1], 0.0, 1.0),
        vmin=0,
        vmax=3,
    )
    mode_axis.set_yticks([])
    mode_axis.set_xlabel("time [ms]")
    mode_axis.set_title("Active contact branch", fontsize=10)
    mode_axis.legend(
        handles=[Patch(label=_MODE_DISPLAY[index]) for index in sorted(_MODE_DISPLAY)],
        loc="upper center",
        bbox_to_anchor=(0.5, -1.7),
        ncols=2,
        frameon=False,
        fontsize=8,
    )

    figure.suptitle(
        f"CINDER engaged hybrid trajectory — {scenario.title}\n"
        f"{scenario.description}",
        fontsize=14,
    )
    return figure


def _combined_legend(left_axis, right_axis) -> None:
    left_handles, left_labels = left_axis.get_legend_handles_labels()
    right_handles, right_labels = right_axis.get_legend_handles_labels()
    left_axis.legend(
        left_handles + right_handles, left_labels + right_labels, loc="best"
    )


def _mark_transitions(*, axis, transitions) -> None:
    for record in transitions:
        axis.axvline(record.time * 1.0e3, linestyle=":", linewidth=1.0)


def save_figures(*, figures, path: Path | None, all_cases: bool) -> None:
    if path is None:
        return
    if all_cases and path.suffix:
        directory = path.with_suffix("")
        directory.mkdir(parents=True, exist_ok=True)
        for name, figure in figures:
            figure.savefig(directory / f"{name}.png", dpi=180)
        print(f"Saved {len(figures)} figures under {directory}")
        return

    if all_cases:
        path.mkdir(parents=True, exist_ok=True)
        for name, figure in figures:
            figure.savefig(path / f"{name}.png", dpi=180)
        print(f"Saved {len(figures)} figures under {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    figures[0][1].savefig(path, dpi=180)
    print(f"Saved {path}")


def _freeze(values: NDArray) -> NDArray:
    copy = np.array(values, copy=True)
    copy.setflags(write=False)
    return copy


if __name__ == "__main__":
    main()
