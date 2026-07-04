"""Exercise CINDER's public stick--stick solver under one-at-a-time perturbations.

This is a diagnostic / regression tool.  It intentionally calls only the
public engaged-contact API::

    solve_stick_stick(snapshot=..., settings=...)

rather than assembling a lambda residual map or solving the 8x8 system
manually.  The frozen snapshot is perturbed one known input at a time so the
resulting changes in lambda, torque, normal reaction, and acceleration can be
read as controlled local-response checks.

Run from cvtModel/::

    python tools/probe_stick_solver_response.py
    python tools/probe_stick_solver_response.py --scenario active-shift
    python tools/probe_stick_solver_response.py --lambda-upper 2.5 --points 9
    python tools/probe_stick_solver_response.py --save artifacts/stick_response.png

The default uses a deliberately broad non-negative diagnostic lambda box.  It
is not a physical traction-limit policy.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
import sys
from typing import Callable, Iterable

import matplotlib.pyplot as plt
import numpy as np

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if (_candidate / "cinder").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import BajaTrialBaseline, build_baja_trial_baseline
from cinder.actuation import PulleyActuationResult
from cinder.closure import AffineClosureScalar
from cinder.dynamics import (
    CVTDynamicState,
    DynamicsSnapshot,
    EngagedContactSolveResult,
    EngagedContactSolveSettings,
    FrictionUtilizationBounds,
    TrialFrictionUtilization,
    solve_stick_stick,
)


DEFAULT_LAMBDA_LOWER = 0.0
DEFAULT_LAMBDA_UPPER = 2.0
DEFAULT_POINTS = 7
DEFAULT_MAX_NFEV = 250
DEFAULT_ROOT_MATCH_TOLERANCE = 1.0e-7

# These changes are intentionally applied to the *frozen snapshot*, not to
# model specifications.  That isolates one row input at a time: no geometry,
# speed, engine-curve interpolation, road model, or actuator state changes
# incidentally with the tested value.
DEFAULT_ENGINE_TORQUE_OFFSETS = (-8.0, -4.0, 0.0, 4.0, 8.0)
DEFAULT_SECONDARY_EXTERNAL_TORQUE_OFFSETS = (-10.0, -5.0, 0.0, 5.0, 10.0)
DEFAULT_PRIMARY_CLAMP_BIAS_OFFSETS = (-200.0, -100.0, 0.0, 100.0, 200.0)
DEFAULT_SECONDARY_CLAMP_BIAS_OFFSETS = (-200.0, -100.0, 0.0, 100.0, 200.0)
DEFAULT_SEEDS = (
    (0.00, 0.00),
    (0.05, 0.05),
    (0.20, 0.20),
    (0.65, 0.65),
    (1.00, 0.25),
    (0.25, 1.00),
    (1.00, 1.00),
    (1.80, 0.20),
    (0.20, 1.80),
    (1.80, 1.80),
)


@dataclass(frozen=True, slots=True)
class ResponseSample:
    """One public-solver result for one controlled frozen-snapshot change."""

    name: str
    offset: float
    result: EngagedContactSolveResult | None
    error: str | None = None

    @property
    def has_result(self) -> bool:
        return self.result is not None

    @property
    def solved(self) -> bool:
        """Return whether this point is an accepted stick--stick root."""

        return self.result is not None and self.result.accepted


@dataclass(frozen=True, slots=True)
class SweepDefinition:
    """A one-parameter perturbation of a frozen state snapshot."""

    name: str
    unit: str
    offsets: tuple[float, ...]
    apply: Callable[[DynamicsSnapshot, float], DynamicsSnapshot]
    expected_note: str


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe the public CINDER stick--stick solver one input at a time."
    )
    parser.add_argument(
        "--scenario",
        choices=("quasi-static", "active-shift"),
        default="quasi-static",
        help="Baseline state used to create the frozen snapshot.",
    )
    parser.add_argument(
        "--lambda-lower",
        type=float,
        default=DEFAULT_LAMBDA_LOWER,
        help="Diagnostic lower bound shared by lambda_p and lambda_s.",
    )
    parser.add_argument(
        "--lambda-upper",
        type=float,
        default=DEFAULT_LAMBDA_UPPER,
        help="Diagnostic upper bound shared by lambda_p and lambda_s.",
    )
    parser.add_argument(
        "--points",
        type=int,
        default=DEFAULT_POINTS,
        help="Odd number of values per centered one-at-a-time sweep.",
    )
    parser.add_argument(
        "--engine-torque-span",
        type=float,
        default=8.0,
        help="Centered engine-torque perturbation span [N m].",
    )
    parser.add_argument(
        "--secondary-external-torque-span",
        type=float,
        default=10.0,
        help="Centered secondary external-torque perturbation span [N m].",
    )
    parser.add_argument(
        "--primary-clamp-bias-span",
        type=float,
        default=200.0,
        help="Centered additive primary clamp-bias perturbation span [N].",
    )
    parser.add_argument(
        "--secondary-clamp-bias-span",
        type=float,
        default=200.0,
        help="Centered additive secondary clamp-bias perturbation span [N].",
    )
    parser.add_argument(
        "--maximum-function-evaluations",
        type=int,
        default=DEFAULT_MAX_NFEV,
        help="Per public-solver call maximum nonlinear residual evaluations.",
    )
    parser.add_argument(
        "--save",
        type=Path,
        help="Optional PNG/PDF/SVG response-plot path.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Build and optionally save the figure without opening a window.",
    )
    args = parser.parse_args()

    if not isfinite(args.lambda_lower) or not isfinite(args.lambda_upper):
        parser.error("lambda bounds must be finite.")
    if args.lambda_lower >= args.lambda_upper:
        parser.error("--lambda-lower must be below --lambda-upper.")
    if args.points < 3 or args.points % 2 == 0:
        parser.error("--points must be an odd integer of at least 3.")
    for option_name, value in (
        ("--engine-torque-span", args.engine_torque_span),
        ("--secondary-external-torque-span", args.secondary_external_torque_span),
        ("--primary-clamp-bias-span", args.primary_clamp_bias_span),
        ("--secondary-clamp-bias-span", args.secondary_clamp_bias_span),
    ):
        if not isfinite(value) or value < 0.0:
            parser.error(f"{option_name} must be finite and non-negative.")
    if args.maximum_function_evaluations < 1:
        parser.error("--maximum-function-evaluations must be at least one.")
    return args


def main() -> None:
    args = parse_arguments()
    baseline = build_baja_trial_baseline()
    state = _select_state(baseline=baseline, scenario=args.scenario)
    snapshot = baseline.model.snapshot(state=state)

    bounds = FrictionUtilizationBounds(
        primary_lower=args.lambda_lower,
        primary_upper=args.lambda_upper,
        secondary_lower=args.lambda_lower,
        secondary_upper=args.lambda_upper,
    )

    _print_header(snapshot=snapshot, scenario=args.scenario, bounds=bounds)
    root = _verify_public_solver_multistart(
        snapshot=snapshot,
        bounds=bounds,
        maximum_function_evaluations=args.maximum_function_evaluations,
    )
    if root is None:
        print("\nNo accepted baseline root was available. Sweep phase skipped.")
        return

    sweeps = _build_sweeps(args)
    all_samples: list[tuple[SweepDefinition, tuple[ResponseSample, ...]]] = []
    for sweep in sweeps:
        print("\n" + "=" * 112)
        print(f"One-at-a-time sweep: {sweep.name}")
        print(sweep.expected_note)
        samples = _run_sweep(
            snapshot=snapshot,
            sweep=sweep,
            bounds=bounds,
            continuation_initial=root.friction_utilization,
            maximum_function_evaluations=args.maximum_function_evaluations,
        )
        _print_sweep_table(samples=samples, unit=sweep.unit)
        _print_local_trend(samples=samples, sweep_name=sweep.name)
        all_samples.append((sweep, samples))

    figure = _plot_sweeps(all_samples)
    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180)
        print(f"\nSaved {args.save}")
    if not args.no_show:
        plt.show()


def _select_state(*, baseline: BajaTrialBaseline, scenario: str) -> CVTDynamicState:
    if scenario == "quasi-static":
        return baseline.quasi_static_state
    return baseline.active_shift_state


def _make_settings(
    *,
    bounds: FrictionUtilizationBounds,
    initial_guess: TrialFrictionUtilization,
    maximum_function_evaluations: int,
) -> EngagedContactSolveSettings:
    return EngagedContactSolveSettings(
        static_bounds=bounds,
        initial_guess=initial_guess,
        maximum_function_evaluations=maximum_function_evaluations,
    )


def _verify_public_solver_multistart(
    *,
    snapshot: DynamicsSnapshot,
    bounds: FrictionUtilizationBounds,
    maximum_function_evaluations: int,
) -> EngagedContactSolveResult | None:
    print("\nPublic-solver multistart check")
    print("-" * 112)
    print(
        "Each line calls solve_stick_stick(); no residual map or manual lambda solve is used."
    )
    accepted: list[EngagedContactSolveResult] = []

    for seed_primary, seed_secondary in _seeds_within(bounds=bounds):
        seed = TrialFrictionUtilization(
            primary_lambda=seed_primary,
            secondary_lambda=seed_secondary,
        )
        try:
            result = solve_stick_stick(
                snapshot=snapshot,
                settings=_make_settings(
                    bounds=bounds,
                    initial_guess=seed,
                    maximum_function_evaluations=maximum_function_evaluations,
                ),
            )
        except (ArithmeticError, ValueError, RuntimeError) as error:
            print(
                f"seed=({seed_primary: .3f}, {seed_secondary: .3f})  ERROR  {type(error).__name__}: {error}"
            )
            continue

        residual = np.linalg.norm(result.sticking_residuals)
        print(
            f"seed=({seed_primary: .3f}, {seed_secondary: .3f})  "
            f"lambda=({result.friction_utilization.primary_lambda: .9f}, "
            f"{result.friction_utilization.secondary_lambda: .9f})  "
            f"||R||={residual:.3e}  accepted={result.accepted}  "
            f"nfev={result.function_evaluations:3d}  "
            f"cond(J)={result.jacobian_condition_number:.3e}"
        )
        if result.accepted:
            accepted.append(result)

    if not accepted:
        print(
            "No public-solver multistart call produced an accepted stick--stick root."
        )
        return None

    chosen = min(
        accepted, key=lambda candidate: np.linalg.norm(candidate.sticking_residuals)
    )
    roots = np.asarray(
        [
            (
                result.friction_utilization.primary_lambda,
                result.friction_utilization.secondary_lambda,
            )
            for result in accepted
        ],
        dtype=float,
    )
    spread = np.max(np.abs(roots - roots[0]), axis=0)
    same_root = bool(np.all(spread <= DEFAULT_ROOT_MATCH_TOLERANCE))

    print("\nMultistart verdict")
    print(
        f"accepted={len(accepted)}, root spread=(lambda_p {spread[0]:.3e}, lambda_s {spread[1]:.3e}), "
        f"same-root={same_root}"
    )
    print(
        "Selected public-solver root: "
        f"lambda_p={chosen.friction_utilization.primary_lambda:.12f}, "
        f"lambda_s={chosen.friction_utilization.secondary_lambda:.12f}, "
        f"||R||={np.linalg.norm(chosen.sticking_residuals):.3e}, "
        f"cond(A)={chosen.closure.condition_number:.3e}"
    )
    if not same_root:
        print(
            "WARNING: accepted initial guesses converged to materially different roots. "
            "Keep multistart / continuation as a diagnostic until branch structure is understood."
        )
    return chosen


def _seeds_within(
    *,
    bounds: FrictionUtilizationBounds,
) -> Iterable[tuple[float, float]]:
    yielded: set[tuple[float, float]] = set()
    for primary, secondary in DEFAULT_SEEDS:
        seed = (primary, secondary)
        if (
            bounds.primary_lower <= primary <= bounds.primary_upper
            and bounds.secondary_lower <= secondary <= bounds.secondary_upper
            and seed not in yielded
        ):
            yielded.add(seed)
            yield seed

    centre = (
        0.5 * (bounds.primary_lower + bounds.primary_upper),
        0.5 * (bounds.secondary_lower + bounds.secondary_upper),
    )
    if centre not in yielded:
        yield centre


def _build_sweeps(args: argparse.Namespace) -> tuple[SweepDefinition, ...]:
    return (
        SweepDefinition(
            name="engine torque bias",
            unit="N m",
            offsets=_centered_offsets(args.engine_torque_span, args.points),
            apply=_with_engine_torque_offset,
            expected_note=(
                "At fixed state and fixed secondary load, increasing engine torque should generally "
                "increase transmitted tau_p and tau_s. The primary may also accelerate faster, so "
                "tau_p need not rise one-for-one with engine torque."
            ),
        ),
        SweepDefinition(
            name="secondary external torque bias",
            unit="N m",
            offsets=_centered_offsets(args.secondary_external_torque_span, args.points),
            apply=_with_secondary_external_torque_offset,
            expected_note=(
                "Negative offset means more resisting road torque under the present sign convention. "
                "That should generally demand larger tau_s and, through the belt, larger tau_p."
            ),
        ),
        SweepDefinition(
            name="primary clamp-force bias",
            unit="N",
            offsets=_centered_offsets(args.primary_clamp_bias_span, args.points),
            apply=_with_primary_clamp_bias_offset,
            expected_note=(
                "This changes only the known primary local actuator-force bias. It primarily tests "
                "whether the coupled axial/contact rows move N_p and lambda_p coherently."
            ),
        ),
        SweepDefinition(
            name="secondary clamp-force bias",
            unit="N",
            offsets=_centered_offsets(args.secondary_clamp_bias_span, args.points),
            apply=_with_secondary_clamp_bias_offset,
            expected_note=(
                "This changes only the known secondary local actuator-force bias. It primarily tests "
                "whether the coupled axial/contact rows move N_s and lambda_s coherently."
            ),
        ),
    )


def _centered_offsets(span: float, points: int) -> tuple[float, ...]:
    return tuple(float(value) for value in np.linspace(-span, span, points))


def _with_engine_torque_offset(
    snapshot: DynamicsSnapshot,
    offset: float,
) -> DynamicsSnapshot:
    return replace(snapshot, engine_torque=snapshot.engine_torque + offset)


def _with_secondary_external_torque_offset(
    snapshot: DynamicsSnapshot,
    offset: float,
) -> DynamicsSnapshot:
    return replace(
        snapshot,
        road_load=replace(
            snapshot.road_load,
            secondary_external_torque=(snapshot.secondary_external_torque + offset),
        ),
    )


def _with_primary_clamp_bias_offset(
    snapshot: DynamicsSnapshot,
    offset: float,
) -> DynamicsSnapshot:
    return replace(
        snapshot,
        primary_actuation=PulleyActuationResult(
            relation=(
                snapshot.primary_actuation.relation
                + AffineClosureScalar.constant(offset)
            )
        ),
    )


def _with_secondary_clamp_bias_offset(
    snapshot: DynamicsSnapshot,
    offset: float,
) -> DynamicsSnapshot:
    return replace(
        snapshot,
        secondary_actuation=PulleyActuationResult(
            relation=(
                snapshot.secondary_actuation.relation
                + AffineClosureScalar.constant(offset)
            )
        ),
    )


def _run_sweep(
    *,
    snapshot: DynamicsSnapshot,
    sweep: SweepDefinition,
    bounds: FrictionUtilizationBounds,
    continuation_initial: TrialFrictionUtilization,
    maximum_function_evaluations: int,
) -> tuple[ResponseSample, ...]:
    samples: list[ResponseSample] = []
    initial = continuation_initial

    # Walk in increasing perturbation order and warm-start from the nearest
    # previous solution. This mirrors time-domain RHS usage more closely than
    # restarting every point from one arbitrary constant guess.
    for offset in sweep.offsets:
        perturbed_snapshot = sweep.apply(snapshot, offset)
        try:
            result = solve_stick_stick(
                snapshot=perturbed_snapshot,
                settings=_make_settings(
                    bounds=bounds,
                    initial_guess=initial,
                    maximum_function_evaluations=maximum_function_evaluations,
                ),
            )
        except (ArithmeticError, ValueError, RuntimeError) as error:
            samples.append(
                ResponseSample(
                    name=sweep.name,
                    offset=offset,
                    result=None,
                    error=f"{type(error).__name__}: {error}",
                )
            )
            continue

        samples.append(ResponseSample(name=sweep.name, offset=offset, result=result))
        if result.accepted:
            initial = result.friction_utilization
    return tuple(samples)


def _print_sweep_table(*, samples: tuple[ResponseSample, ...], unit: str) -> None:
    print(
        f"{'offset [' + unit + ']':>14}  {'lambda_p':>11}  {'lambda_s':>11}  "
        f"{'tau_p [N m]':>12}  {'tau_s [N m]':>12}  {'N_p [N]':>11}  {'N_s [N]':>11}  "
        f"{'alpha_p':>10}  {'alpha_s':>10}  {'s_ddot':>11}  {'||R||':>10}  {'status':>10}"
    )
    print("-" * 142)
    for sample in samples:
        if sample.result is None:
            print(f"{sample.offset:14.5g}  ERROR  {sample.error or 'no solver result'}")
            continue

        result = sample.result
        unknowns = result.closure.unknowns
        residual_norm = float(np.linalg.norm(result.sticking_residuals))
        if result.accepted:
            status = "yes"
        else:
            active = []
            if any(result.active_lower_bounds):
                active.append("lower")
            if any(result.active_upper_bounds):
                active.append("upper")
            status = "no:" + ("/".join(active) if active else "residual")
        print(
            f"{sample.offset:14.5g}  "
            f"{result.friction_utilization.primary_lambda:11.6f}  "
            f"{result.friction_utilization.secondary_lambda:11.6f}  "
            f"{unknowns.primary_torque:12.6f}  {unknowns.secondary_torque:12.6f}  "
            f"{unknowns.primary_normal_resultant:11.5f}  {unknowns.secondary_normal_resultant:11.5f}  "
            f"{unknowns.primary_angular_acceleration:10.4f}  "
            f"{unknowns.secondary_angular_acceleration:10.4f}  "
            f"{unknowns.shift_acceleration:11.4f}  {residual_norm:10.3e}  {status}"
        )


def _print_local_trend(*, samples: tuple[ResponseSample, ...], sweep_name: str) -> None:
    valid = [sample for sample in samples if sample.solved]
    if len(valid) < 2:
        print("Trend check: insufficient solved points.")
        return

    first = valid[0]
    last = valid[-1]
    assert first.result is not None and last.result is not None
    first_unknowns = first.result.closure.unknowns
    last_unknowns = last.result.closure.unknowns
    delta_offset = last.offset - first.offset
    if delta_offset == 0.0:
        return

    print("Local end-to-end response across solved sweep range")
    for label, start, end in (
        ("tau_p", first_unknowns.primary_torque, last_unknowns.primary_torque),
        ("tau_s", first_unknowns.secondary_torque, last_unknowns.secondary_torque),
        (
            "lambda_p",
            first.result.friction_utilization.primary_lambda,
            last.result.friction_utilization.primary_lambda,
        ),
        (
            "lambda_s",
            first.result.friction_utilization.secondary_lambda,
            last.result.friction_utilization.secondary_lambda,
        ),
        ("s_ddot", first_unknowns.shift_acceleration, last_unknowns.shift_acceleration),
    ):
        slope = (end - start) / delta_offset
        direction = (
            "increases" if slope > 0.0 else "decreases" if slope < 0.0 else "is flat"
        )
        print(
            f"  {label:8s}: {direction:10s} over sweep; secant slope={slope:.6g} per offset unit"
        )


def _plot_sweeps(
    all_samples: list[tuple[SweepDefinition, tuple[ResponseSample, ...]]],
):
    figure, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)
    for axis, (sweep, samples) in zip(axes.flat, all_samples, strict=True):
        offsets = np.asarray([sample.offset for sample in samples], dtype=float)
        tau_p = _series(samples, lambda result: result.closure.unknowns.primary_torque)
        tau_s = _series(
            samples, lambda result: result.closure.unknowns.secondary_torque
        )
        lambda_p = _series(
            samples, lambda result: result.friction_utilization.primary_lambda
        )
        lambda_s = _series(
            samples, lambda result: result.friction_utilization.secondary_lambda
        )

        left = axis
        right = left.twinx()
        line_tau_p = left.plot(offsets, tau_p, marker="o", label=r"$\tau_p$")
        line_tau_s = left.plot(offsets, tau_s, marker="s", label=r"$\tau_s$")
        line_lambda_p = right.plot(
            offsets, lambda_p, marker="^", linestyle="--", label=r"$\lambda_p$"
        )
        line_lambda_s = right.plot(
            offsets, lambda_s, marker="v", linestyle="--", label=r"$\lambda_s$"
        )
        left.axvline(0.0, linewidth=1.0)
        left.set_title(sweep.name)
        left.set_xlabel(f"additive offset [{sweep.unit}]")
        left.set_ylabel("transmitted torque [N m]")
        right.set_ylabel("solved utilization [-]")
        left.grid(True, alpha=0.25)
        lines = line_tau_p + line_tau_s + line_lambda_p + line_lambda_s
        left.legend(lines, [line.get_label() for line in lines], loc="best")

    figure.suptitle(
        "CINDER public stick--stick solver: one-at-a-time frozen-snapshot response"
    )
    return figure


def _series(
    samples: tuple[ResponseSample, ...],
    selector: Callable[[EngagedContactSolveResult], float],
) -> np.ndarray:
    values: list[float] = []
    for sample in samples:
        if sample.has_result:
            assert sample.result is not None
            values.append(float(selector(sample.result)))
        else:
            values.append(float("nan"))
    return np.asarray(values, dtype=float)


def _print_header(
    *,
    snapshot: DynamicsSnapshot,
    scenario: str,
    bounds: FrictionUtilizationBounds,
) -> None:
    state = snapshot.state
    print("=" * 112)
    print("CINDER public stick--stick solver response probe")
    print("=" * 112)
    print(f"Scenario: {scenario}")
    print(
        "Diagnostic static box: "
        f"lambda_p in [{bounds.primary_lower:g}, {bounds.primary_upper:g}], "
        f"lambda_s in [{bounds.secondary_lower:g}, {bounds.secondary_upper:g}]"
    )
    print(
        f"State: omega_p={state.primary_angular_speed:.6f} rad/s, "
        f"omega_s={state.secondary_angular_speed:.6f} rad/s, "
        f"v_b={state.belt_speed:.6f} m/s, s_dot={state.shift_speed:.6f} m/s"
    )
    print(
        f"Known snapshot loads: tau_engine={snapshot.engine_torque:.6f} N m, "
        f"tau_secondary_external={snapshot.secondary_external_torque:.6f} N m"
    )


if __name__ == "__main__":
    main()
