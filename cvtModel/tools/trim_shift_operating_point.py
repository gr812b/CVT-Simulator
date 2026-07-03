"""Trim one physical baseline preload for a chosen *initial* shift acceleration.

This is an operating-point diagnostic, not an actuator controller.  It changes
only ``BajaTrialConstants.primary_spring_initial_compression`` and solves for
that one physical baseline value such that the fully coupled, stick--stick
engaged closure gives a requested initial ``s_ddot``.

The script then runs the normal engaged-contact hybrid simulator from that
trimmed initial condition.  This is useful for looking at slower shaft-speed
transients without the default placeholder preload immediately driving a hard
backshift into the unimplemented deadzone boundary.

Run from cvtModel/:

    python tools/trim_shift_operating_point.py
    python tools/trim_shift_operating_point.py --target-s-ddot 10 --duration-ms 20
    python tools/trim_shift_operating_point.py --target-s-ddot 0 --save artifacts/trim.png --no-show

Positive ``s_ddot`` is primary closing / upshift in CINDER's current
coordinate convention.  A zero target is only an *instantaneous* balance at
the initial state.  It does not hold ratio forever once shaft speeds and
actuation loads evolve; that would require a controller or a true equilibrium
calculation across all relevant state derivatives.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from math import isfinite
from pathlib import Path
import sys
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray
from scipy.optimize import brentq

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if (_candidate / "cinder").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import (  # noqa: E402
    BajaTrialBaseline,
    BajaTrialConstants,
    build_baja_trial_baseline,
)
from cinder.contact import (  # noqa: E402
    ContactRegime,
    ContactTractionLaw,
    ContactTractionUtilization,
)
from cinder.dynamics import EngagedContactSolveSettings, LambdaSearchBounds  # noqa: E402
from cinder.integration import CVTDynamicState  # noqa: E402
from cinder.integration.cvt_hybrid import EngagedCVTHybridSystem  # noqa: E402
from cinder.integration.hybrid import HybridIntegratorSettings  # noqa: E402

_DEFAULT_STATIC_LIMIT = 0.65
_DEFAULT_KINETIC_LAMBDA = 0.55
_DEFAULT_TARGET_SHIFT_ACCELERATION = 0.0
_DEFAULT_DURATION_MS = 10.0
_DEFAULT_MAX_STEP_US = 100.0
_DEFAULT_PRELOAD_MIN = 0.0
_DEFAULT_SCAN_POINTS = 41
_DEFAULT_PLOT_SAMPLES = 500


@dataclass(frozen=True, slots=True)
class TrimOperatingPoint:
    """One stick--stick operating point after solving the preload trim."""

    preload: float
    baseline: BajaTrialBaseline
    system: EngagedCVTHybridSystem
    state: CVTDynamicState
    evaluation: object

    @property
    def shift_acceleration(self) -> float:
        return float(self.evaluation.closure_unknowns.shift_acceleration)


@dataclass(frozen=True, slots=True)
class TrajectoryTrace:
    """Selected hybrid outputs evaluated at actual integration samples."""

    time: NDArray[np.float64]
    state: NDArray[np.float64]
    mode_label: tuple[str, ...]
    shift_acceleration: NDArray[np.float64]
    torque_primary: NDArray[np.float64]
    torque_secondary: NDArray[np.float64]
    lambda_primary: NDArray[np.float64]
    lambda_secondary: NDArray[np.float64]
    normal_primary: NDArray[np.float64]
    normal_secondary: NDArray[np.float64]
    relative_speed_primary: NDArray[np.float64]
    relative_speed_secondary: NDArray[np.float64]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Solve one primary-spring preload that produces a requested initial "
            "engaged stick--stick shift acceleration, then integrate the trimmed state."
        )
    )
    parser.add_argument(
        "--target-s-ddot",
        type=float,
        default=_DEFAULT_TARGET_SHIFT_ACCELERATION,
        help=(
            "Requested initial shift acceleration [m/s^2]. Positive is primary closing / "
            "upshift; zero gives an instantaneous shift-hold trim."
        ),
    )
    parser.add_argument(
        "--static-limit",
        type=float,
        default=_DEFAULT_STATIC_LIMIT,
        help="Symmetric physical static lambda limit used to validate the trim.",
    )
    parser.add_argument(
        "--kinetic-lambda",
        type=float,
        default=_DEFAULT_KINETIC_LAMBDA,
        help="Positive kinetic lambda magnitude retained for any later slip transition.",
    )
    parser.add_argument(
        "--preload-min",
        type=float,
        default=_DEFAULT_PRELOAD_MIN,
        help="Lower primary spring initial-compression value searched [m].",
    )
    parser.add_argument(
        "--preload-max",
        type=float,
        help=(
            "Upper primary spring initial-compression value searched [m]. Defaults to "
            "the untrimmed Baja baseline value."
        ),
    )
    parser.add_argument(
        "--scan-points",
        type=int,
        default=_DEFAULT_SCAN_POINTS,
        help="Number of preload samples used to locate a scalar root bracket.",
    )
    parser.add_argument(
        "--duration-ms",
        type=float,
        default=_DEFAULT_DURATION_MS,
        help="Hybrid integration duration after trimming [ms].",
    )
    parser.add_argument(
        "--max-step-us",
        type=float,
        default=_DEFAULT_MAX_STEP_US,
        help="Maximum hybrid solve_ivp step [microseconds].",
    )
    parser.add_argument(
        "--plot-samples",
        type=int,
        default=_DEFAULT_PLOT_SAMPLES,
        help="Maximum sampled points used for the diagnostic figure.",
    )
    parser.add_argument("--save", type=Path, help="Optional output PNG/PDF/SVG path.")
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Build and optionally save the figure without opening a matplotlib window.",
    )
    args = parser.parse_args()

    for name, value in (
        ("--target-s-ddot", args.target_s_ddot),
        ("--static-limit", args.static_limit),
        ("--kinetic-lambda", args.kinetic_lambda),
        ("--preload-min", args.preload_min),
        ("--duration-ms", args.duration_ms),
        ("--max-step-us", args.max_step_us),
    ):
        if not isfinite(value):
            parser.error(f"{name} must be finite.")
    if args.static_limit <= 0.0:
        parser.error("--static-limit must be strictly positive.")
    if args.kinetic_lambda <= 0.0:
        parser.error("--kinetic-lambda must be strictly positive.")
    if args.preload_min < 0.0:
        parser.error("--preload-min must be non-negative for a compression spring.")
    if args.preload_max is not None:
        if not isfinite(args.preload_max) or args.preload_max <= args.preload_min:
            parser.error("--preload-max must be finite and greater than --preload-min.")
    if args.scan_points < 3:
        parser.error("--scan-points must be at least 3.")
    if args.duration_ms <= 0.0:
        parser.error("--duration-ms must be strictly positive.")
    if args.max_step_us <= 0.0:
        parser.error("--max-step-us must be strictly positive.")
    if args.plot_samples < 20:
        parser.error("--plot-samples must be at least 20.")
    return args


def main() -> None:
    args = parse_arguments()
    reference_constants = BajaTrialConstants()
    preload_max = (
        reference_constants.primary_spring_initial_compression
        if args.preload_max is None
        else args.preload_max
    )
    traction_law = ContactTractionLaw.symmetric(
        primary_static_lambda_limit=args.static_limit,
        secondary_static_lambda_limit=args.static_limit,
        primary_kinetic_lambda_magnitude=args.kinetic_lambda,
        secondary_kinetic_lambda_magnitude=args.kinetic_lambda,
    )

    operating_point = solve_primary_preload_trim(
        reference_constants=reference_constants,
        traction_law=traction_law,
        target_shift_acceleration=args.target_s_ddot,
        preload_min=args.preload_min,
        preload_max=preload_max,
        scan_points=args.scan_points,
    )
    assessment = traction_law.assess_static_requirement(
        operating_point.evaluation.branch_result.required_static_utilization
    )
    if not assessment.all_admissible:
        raise RuntimeError(
            "The mathematical stick--stick trim is outside the requested physical static "
            "lambda limits. Increase --static-limit only for a diagnostic, or choose a "
            "different physical trim variable."
        )

    result = operating_point.system.integrate(
        time_span=(0.0, args.duration_ms * 1.0e-3),
        initial_state=operating_point.state,
        initial_regime=ContactRegime.stick_stick(),
        settings=HybridIntegratorSettings(
            max_step=args.max_step_us * 1.0e-6,
            maximum_transitions=80,
        ),
    )
    trace = sample_trajectory(
        system=operating_point.system,
        result=result,
        maximum_samples=args.plot_samples,
    )
    print_summary(
        args=args,
        reference_constants=reference_constants,
        operating_point=operating_point,
        result=result,
        trace=trace,
        assessment=assessment,
    )

    figure = plot_trace(
        trace=trace,
        target_shift_acceleration=args.target_s_ddot,
        static_limit=args.static_limit,
        target_label=_target_label(args.target_s_ddot),
    )
    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180)
        print(f"Saved {args.save}")
    if not args.no_show:
        plt.show()


def solve_primary_preload_trim(
    *,
    reference_constants: BajaTrialConstants,
    traction_law: ContactTractionLaw,
    target_shift_acceleration: float,
    preload_min: float,
    preload_max: float,
    scan_points: int,
) -> TrimOperatingPoint:
    """Find a primary-spring preload matching one initial stick--stick s_ddot target.

    Root evaluation intentionally enforces the stick--stick branch directly.
    This exposes the required static lambda pair even when an endpoint of the
    search interval would otherwise classify into a kinetic branch.  Physical
    admissibility is assessed after the mathematical root is found.
    """

    cache: dict[float, TrimOperatingPoint] = {}

    def evaluate(preload: float) -> TrimOperatingPoint:
        key = float(preload)
        cached = cache.get(key)
        if cached is not None:
            return cached
        constants = dataclass_replace(
            reference_constants,
            primary_spring_initial_compression=key,
        )
        baseline = build_baja_trial_baseline(constants)
        system = build_hybrid_system(baseline=baseline, traction_law=traction_law)
        state = baseline.quasi_static_state
        evaluation = system.evaluator.evaluate_vector(
            time=0.0,
            vector=state.as_vector(),
            regime=ContactRegime.stick_stick(),
        )
        if not evaluation.branch_result.accepted:
            raise RuntimeError(
                "Stick--stick required-lambda solve did not converge during preload trim."
            )
        candidate = TrimOperatingPoint(
            preload=key,
            baseline=baseline,
            system=system,
            state=state,
            evaluation=evaluation,
        )
        cache[key] = candidate
        return candidate

    def residual(preload: float) -> float:
        return evaluate(preload).shift_acceleration - target_shift_acceleration

    preloads = np.linspace(preload_min, preload_max, scan_points)
    values = np.empty(preloads.size)
    for index, preload in enumerate(preloads):
        values[index] = residual(float(preload))

    exact = np.where(np.isclose(values, 0.0, atol=1.0e-10, rtol=0.0))[0]
    if exact.size:
        return evaluate(float(preloads[int(exact[0])]))

    bracket: tuple[float, float] | None = None
    for lower, upper, lower_value, upper_value in zip(
        preloads[:-1],
        preloads[1:],
        values[:-1],
        values[1:],
        strict=True,
    ):
        if lower_value * upper_value < 0.0:
            bracket = (float(lower), float(upper))
            break
    if bracket is None:
        summary = (
            f"s_ddot-target ranges from {values.min():+.6e} to {values.max():+.6e} "
            f"m/s^2 over preload=[{preload_min:.6e}, {preload_max:.6e}] m."
        )
        raise RuntimeError(
            "No primary-spring-preload bracket reaches the requested initial shift "
            f"acceleration. {summary}"
        )

    root = brentq(
        residual,
        *bracket,
        xtol=1.0e-12,
        rtol=1.0e-12,
        maxiter=100,
    )
    return evaluate(float(root))


def build_hybrid_system(
    *,
    baseline: BajaTrialBaseline,
    traction_law: ContactTractionLaw,
) -> EngagedCVTHybridSystem:
    """Build an engaged hybrid system with broad *numerical* lambda bounds."""

    return EngagedCVTHybridSystem(
        model=baseline.model,
        traction_law=traction_law,
        solve_settings=EngagedContactSolveSettings(
            lambda_search_bounds=LambdaSearchBounds.symmetric(
                primary_half_width=2.0,
                secondary_half_width=2.0,
            ),
            initial_guess=ContactTractionUtilization(
                primary_lambda=0.0,
                secondary_lambda=0.0,
            ),
            maximum_closure_condition_number=1.0e8,
        ),
    )


def sample_trajectory(*, system: EngagedCVTHybridSystem, result, maximum_samples: int) -> TrajectoryTrace:
    plan = list(iter_segment_samples(result.segments, maximum_samples=maximum_samples))
    count = len(plan)
    time = np.empty(count)
    state = np.empty((6, count))
    shift_acceleration = np.empty(count)
    torque_primary = np.empty(count)
    torque_secondary = np.empty(count)
    lambda_primary = np.empty(count)
    lambda_secondary = np.empty(count)
    normal_primary = np.empty(count)
    normal_secondary = np.empty(count)
    relative_speed_primary = np.empty(count)
    relative_speed_secondary = np.empty(count)
    labels: list[str] = []

    for index, (regime, sample_time, sample_state) in enumerate(plan):
        evaluation = system.evaluator.evaluate_vector(
            time=sample_time,
            vector=sample_state,
            regime=regime,
        )
        unknowns = evaluation.closure_unknowns
        relative = evaluation.relative_motion
        utilization = evaluation.traction_utilization
        time[index] = sample_time
        state[:, index] = sample_state
        labels.append(regime.mode.value.replace("_", " / "))
        shift_acceleration[index] = unknowns.shift_acceleration
        torque_primary[index] = unknowns.primary_torque
        torque_secondary[index] = unknowns.secondary_torque
        lambda_primary[index] = utilization.primary_lambda
        lambda_secondary[index] = utilization.secondary_lambda
        normal_primary[index] = unknowns.primary_normal_resultant
        normal_secondary[index] = unknowns.secondary_normal_resultant
        relative_speed_primary[index] = relative.primary_relative_speed
        relative_speed_secondary[index] = relative.secondary_relative_speed

    return TrajectoryTrace(
        time=_freeze(time),
        state=_freeze(state),
        mode_label=tuple(labels),
        shift_acceleration=_freeze(shift_acceleration),
        torque_primary=_freeze(torque_primary),
        torque_secondary=_freeze(torque_secondary),
        lambda_primary=_freeze(lambda_primary),
        lambda_secondary=_freeze(lambda_secondary),
        normal_primary=_freeze(normal_primary),
        normal_secondary=_freeze(normal_secondary),
        relative_speed_primary=_freeze(relative_speed_primary),
        relative_speed_secondary=_freeze(relative_speed_secondary),
    )


def iter_segment_samples(segments: Iterable, *, maximum_samples: int):
    segments = tuple(segments)
    total = sum(segment.time.size for segment in segments)
    per_segment = max(4, maximum_samples // max(len(segments), 1))
    if total <= maximum_samples:
        per_segment = max(segment.time.size for segment in segments)
    for segment_index, segment in enumerate(segments):
        indices = endpoint_preserving_indices(segment.time.size, maximum=per_segment)
        if segment_index and indices.size and indices[0] == 0:
            indices = indices[1:]
        for index in indices:
            yield (
                segment.mode,
                float(segment.time[index]),
                np.asarray(segment.state[:, index], dtype=float),
            )


def endpoint_preserving_indices(count: int, *, maximum: int) -> NDArray[np.int_]:
    if count <= maximum:
        return np.arange(count, dtype=int)
    return np.unique(np.linspace(0, count - 1, maximum, dtype=int))


def print_summary(
    *,
    args: argparse.Namespace,
    reference_constants: BajaTrialConstants,
    operating_point: TrimOperatingPoint,
    result,
    trace: TrajectoryTrace,
    assessment,
) -> None:
    evaluation = operating_point.evaluation
    unknowns = evaluation.closure_unknowns
    required = evaluation.branch_result.required_static_utilization
    delta_preload = operating_point.preload - reference_constants.primary_spring_initial_compression
    final = result.final_state
    initial = operating_point.state.as_vector()

    print("\n" + "=" * 108)
    print("CINDER primary-spring operating-point trim")
    print("=" * 108)
    print(
        f"Requested initial s_ddot={args.target_s_ddot:+.6f} m/s^2 "
        f"({_target_label(args.target_s_ddot)})."
    )
    print(
        f"Solved primary spring initial compression={operating_point.preload:.9f} m "
        f"({operating_point.preload * 1e3:.3f} mm); "
        f"baseline={reference_constants.primary_spring_initial_compression:.9f} m; "
        f"delta={delta_preload * 1e3:+.3f} mm."
    )
    print(
        f"Initial stick--stick result: s_ddot={unknowns.shift_acceleration:+.9e} m/s^2; "
        f"lambda_req=(p={required.primary_lambda:+.6f}, s={required.secondary_lambda:+.6f}); "
        f"static margins=(p={assessment.primary_margin:+.6f}, s={assessment.secondary_margin:+.6f})."
    )
    print(
        f"Initial torque path: tau_p={unknowns.primary_torque:+.6f} N m, "
        f"tau_s={unknowns.secondary_torque:+.6f} N m; "
        f"normals=(N_p={unknowns.primary_normal_resultant:.6f}, "
        f"N_s={unknowns.secondary_normal_resultant:.6f}) N."
    )
    print(
        f"Integration: completed={result.completed}; reason={result.termination_reason}; "
        f"segments={len(result.segments)}; transitions={len(result.transitions)}; "
        f"final time={result.final_time * 1e3:.3f} ms."
    )
    print(
        "State change: "
        f"Delta omega_p={final[0] - initial[0]:+.6e} rad/s, "
        f"Delta omega_s={final[1] - initial[1]:+.6e} rad/s, "
        f"Delta v_b={final[2] - initial[2]:+.6e} m/s, "
        f"Delta s={(final[3] - initial[3]) * 1e3:+.6e} mm, "
        f"final s_dot={final[4] * 1e3:+.6e} mm/s."
    )
    print(
        f"Trace ranges: s_ddot=[{trace.shift_acceleration.min():+.6f}, "
        f"{trace.shift_acceleration.max():+.6f}] m/s^2; "
        f"tau_p=[{trace.torque_primary.min():+.6f}, {trace.torque_primary.max():+.6f}] N m; "
        f"tau_s=[{trace.torque_secondary.min():+.6f}, {trace.torque_secondary.max():+.6f}] N m."
    )
    print(
        f"Relative-speed maxima: |v_rel,p|={np.abs(trace.relative_speed_primary).max():.3e} m/s, "
        f"|v_rel,s|={np.abs(trace.relative_speed_secondary).max():.3e} m/s."
    )
    if result.transitions:
        print("Transitions:")
        for record in result.transitions:
            next_mode = "terminal" if record.transition.next_mode is None else record.transition.next_mode.mode.value
            print(
                f"  t={record.time * 1e3:.6f} ms | events={','.join(record.fired_event_names)} "
                f"| {record.transition.reason} -> {next_mode}"
            )
    else:
        print("Transitions: none")


def plot_trace(
    *,
    trace: TrajectoryTrace,
    target_shift_acceleration: float,
    static_limit: float,
    target_label: str,
):
    time_ms = trace.time * 1e3
    figure, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)

    ax = axes[0, 0]
    ax.plot(time_ms, trace.state[0], label=r"$\omega_p$")
    ax.plot(time_ms, trace.state[1], label=r"$\omega_s$")
    ax.set_title("Shaft-speed transient")
    ax.set_xlabel("Time [ms]")
    ax.set_ylabel("Angular speed [rad/s]")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")

    ax = axes[0, 1]
    ax.plot(time_ms, trace.state[3] * 1e3, label=r"$s$")
    ax.set_title("Shift coordinate and speed")
    ax.set_xlabel("Time [ms]")
    ax.set_ylabel(r"Shift coordinate $s$ [mm]")
    ax.grid(True, alpha=0.25)
    twin = ax.twinx()
    twin.plot(time_ms, trace.state[4] * 1e3, linestyle="--", label=r"$\dot s$")
    twin.set_ylabel(r"Shift speed $\dot s$ [mm/s]")
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = twin.get_legend_handles_labels()
    ax.legend(handles + handles2, labels + labels2, loc="best")

    ax = axes[1, 0]
    ax.plot(time_ms, trace.shift_acceleration, label=r"$\ddot s$")
    ax.axhline(target_shift_acceleration, linestyle="--", label=f"initial target ({target_label})")
    ax.axhline(0.0, linestyle=":", linewidth=1.0)
    ax.set_title("Shift acceleration and transmitted torques")
    ax.set_xlabel("Time [ms]")
    ax.set_ylabel(r"Shift acceleration $\ddot s$ [m/s$^2$]")
    ax.grid(True, alpha=0.25)
    twin = ax.twinx()
    twin.plot(time_ms, trace.torque_primary, linestyle="--", label=r"$\tau_p$")
    twin.plot(time_ms, trace.torque_secondary, linestyle="-.", label=r"$\tau_s$")
    twin.set_ylabel("Torque [N m]")
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = twin.get_legend_handles_labels()
    ax.legend(handles + handles2, labels + labels2, loc="best")

    ax = axes[1, 1]
    ax.plot(time_ms, trace.lambda_primary, label=r"$\lambda_p$")
    ax.plot(time_ms, trace.lambda_secondary, label=r"$\lambda_s$")
    ax.axhline(static_limit, linestyle="--", label=r"static bounds")
    ax.axhline(-static_limit, linestyle="--")
    ax.set_title("Required static traction and normal resultants")
    ax.set_xlabel("Time [ms]")
    ax.set_ylabel(r"$\lambda$ [-]")
    ax.grid(True, alpha=0.25)
    twin = ax.twinx()
    twin.plot(time_ms, trace.normal_primary, linestyle="--", label=r"$N_p$")
    twin.plot(time_ms, trace.normal_secondary, linestyle="-.", label=r"$N_s$")
    twin.set_ylabel("Normal resultant [N]")
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = twin.get_legend_handles_labels()
    ax.legend(handles + handles2, labels + labels2, loc="best")

    figure.suptitle(
        "CINDER engaged operating-point trim: primary spring preload chosen for "
        f"initial {target_label}",
        fontsize=15,
    )
    return figure


def _target_label(value: float) -> str:
    if abs(value) <= 1.0e-10:
        return "shift hold"
    if value > 0.0:
        return "upshift"
    return "backshift"


def _freeze(values: NDArray) -> NDArray:
    frozen = np.array(values, dtype=values.dtype, copy=True)
    frozen.setflags(write=False)
    return frozen


if __name__ == "__main__":
    main()
