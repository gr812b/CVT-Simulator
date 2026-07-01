"""Validate the three pre-branch contact-regime diagnostics for CINDER.

This is a diagnostic-only tool.  It intentionally keeps the production
six-by-six row builders untouched and asks three separate questions:

1. Does the engaged zero-shift-speed state recover one bounded stick root?
2. As prescribed shift speed changes, does an admissible stick root persist,
   or does the root leave the static-friction box and therefore require a
   later slip branch?
3. Does the deadzone geometry activate no wrap/lambda solve and reduce to the
   intended disengaged free-body expectations?

Run from cvtModel/:

    python tools/preview_contact_regimes.py
    python tools/preview_contact_regimes.py --mode shift-sweep
    python tools/preview_contact_regimes.py --shift-speeds-mm-s -12,-9,-6,-3,0,3,6,9,12
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
import sys
from typing import Callable, Iterable

import numpy as np
from scipy.optimize import least_squares

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (
    _REPOSITORY_ROOT / "src",
    _REPOSITORY_ROOT,
    _REPOSITORY_ROOT / "tests" / "support",
):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import BajaTrialBaseline, build_baja_trial_baseline
from cinder.dynamics import (
    CVTDynamicState,
    TrialEquationContext,
    TrialFrictionUtilization,
    build_state_fixed_equations,
    build_trial_six_by_six_system,
)

DEFAULT_LAMBDA_MIN = 0.01
DEFAULT_LAMBDA_MAX = 0.65
DEFAULT_RESIDUAL_TOLERANCE = 1.0e-8
DEFAULT_SEEDS = (
    (0.5304, 0.3826),
    (0.1861, 0.1417),
    (0.35, 0.26),
    (0.60, 0.45),
)
DEFAULT_SHIFT_SPEEDS_MM_S = (-12.0, -9.0, -6.0, -3.0, 0.0, 3.0, 6.0, 9.0, 12.0)


@dataclass(frozen=True, slots=True)
class StickEvaluation:
    lambda_primary: float
    lambda_secondary: float
    residual_primary: float
    residual_secondary: float
    trial_result: object

    @property
    def residual_vector(self) -> np.ndarray:
        return np.array((self.residual_primary, self.residual_secondary), dtype=float)

    @property
    def residual_norm(self) -> float:
        return float(np.linalg.norm(self.residual_vector))


@dataclass(frozen=True, slots=True)
class RootAttempt:
    evaluation: StickEvaluation | None
    optimizer_success: bool
    accepted: bool
    nfev: int
    message: str
    jacobian_condition_number: float | None
    error: str | None = None


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run compact CINDER contact-regime diagnostics.")
    parser.add_argument(
        "--mode",
        choices=("all", "quasi-static", "shift-sweep", "deadzone"),
        default="all",
        help="Diagnostic section to run.",
    )
    parser.add_argument(
        "--shift-speeds-mm-s",
        default=",".join(str(value) for value in DEFAULT_SHIFT_SPEEDS_MM_S),
        help="Comma-separated engaged shift speeds used by --mode shift-sweep.",
    )
    parser.add_argument("--lambda-min", type=float, default=DEFAULT_LAMBDA_MIN)
    parser.add_argument("--lambda-max", type=float, default=DEFAULT_LAMBDA_MAX)
    parser.add_argument("--residual-tolerance", type=float, default=DEFAULT_RESIDUAL_TOLERANCE)
    parser.add_argument("--max-nfev", type=int, default=300)
    args = parser.parse_args()

    if not (0.0 < args.lambda_min < args.lambda_max):
        parser.error("Require 0 < --lambda-min < --lambda-max.")
    if args.residual_tolerance <= 0.0 or not isfinite(args.residual_tolerance):
        parser.error("--residual-tolerance must be finite and positive.")
    if args.max_nfev < 1:
        parser.error("--max-nfev must be at least one.")
    args.shift_speeds_mm_s = _parse_shift_speeds(args.shift_speeds_mm_s, parser)
    return args


def main() -> None:
    args = parse_arguments()
    baseline = build_baja_trial_baseline()

    if args.mode in ("all", "quasi-static"):
        _run_quasi_static_reference(baseline=baseline, args=args)
    if args.mode in ("all", "shift-sweep"):
        _run_shift_speed_sweep(baseline=baseline, args=args)
    if args.mode in ("all", "deadzone"):
        _run_deadzone_check(baseline=baseline)


def _run_quasi_static_reference(*, baseline: BajaTrialBaseline, args: argparse.Namespace) -> None:
    print("\n" + "=" * 104)
    print("Engaged zero-shift-speed stick reference")
    print("Purpose: retain one compact regression check for the validated quasi-static stick root.")
    attempt = _solve_state(
        model=baseline.model,
        state=baseline.quasi_static_state,
        seeds=DEFAULT_SEEDS,
        lambda_min=args.lambda_min,
        lambda_max=args.lambda_max,
        residual_tolerance=args.residual_tolerance,
        max_nfev=args.max_nfev,
    )
    _print_root_attempt(attempt=attempt)


def _run_shift_speed_sweep(*, baseline: BajaTrialBaseline, args: argparse.Namespace) -> None:
    print("\n" + "=" * 104)
    print("Engaged stick feasibility versus imposed shift speed")
    print(
        "Each point rebuilds the snapshot because actuator and helix terms depend on s_dot. "
        "A rejected point does not mean the six-by-six failed; it means no bounded stick root was found."
    )
    print(
        "  s_dot [mm/s] | stick root | lambda_p lambda_s | ||R|| [m/s^2] | "
        "tau_p [N m] tau_s [N m] | s_ddot [m/s^2] | cond(J)"
    )
    print("  " + "-" * 123)

    ordered_speeds = _continuation_order(args.shift_speeds_mm_s)
    previous_seed: tuple[float, float] | None = None
    attempts: dict[float, RootAttempt] = {}

    for shift_speed_mm_s in ordered_speeds:
        state = replace(
            baseline.quasi_static_state,
            shift_speed=shift_speed_mm_s / 1_000.0,
        )
        seeds = _deduplicate_seeds(
            ((previous_seed,) if previous_seed is not None else ()) + DEFAULT_SEEDS
        )
        attempt = _solve_state(
            model=baseline.model,
            state=state,
            seeds=seeds,
            lambda_min=args.lambda_min,
            lambda_max=args.lambda_max,
            residual_tolerance=args.residual_tolerance,
            max_nfev=args.max_nfev,
        )
        attempts[shift_speed_mm_s] = attempt
        if attempt.accepted and attempt.evaluation is not None:
            previous_seed = (
                attempt.evaluation.lambda_primary,
                attempt.evaluation.lambda_secondary,
            )

    for shift_speed_mm_s in sorted(attempts):
        attempt = attempts[shift_speed_mm_s]
        if attempt.evaluation is None:
            print(f"  {shift_speed_mm_s:12.3f} | ERROR      | {attempt.error}")
            continue
        evaluation = attempt.evaluation
        unknowns = evaluation.trial_result.unknowns
        condition_j = (
            f"{attempt.jacobian_condition_number:8.3e}"
            if attempt.jacobian_condition_number is not None
            else "      n/a"
        )
        status = "yes" if attempt.accepted else "no"
        print(
            f"  {shift_speed_mm_s:12.3f} | {status:^10s} | "
            f"{evaluation.lambda_primary:8.5f} {evaluation.lambda_secondary:8.5f} | "
            f"{evaluation.residual_norm:13.6e} | "
            f"{unknowns.primary_torque:11.6f} {unknowns.secondary_torque:11.6f} | "
            f"{unknowns.shift_acceleration:14.6f} | {condition_j}"
        )

    print("\nInterpretation:")
    print("  yes: both no-slip residuals vanish inside the static-utilization box.")
    print("  no : the best bounded solve remains incompatible with stick; a later regime selector")
    print("       should enter a slip branch or the mechanical shift state must change.")


def _run_deadzone_check(*, baseline: BajaTrialBaseline) -> None:
    state = baseline.deadzone_state
    snapshot = baseline.model.snapshot(state=state)
    geometry = snapshot.geometry
    primary_coordinate = geometry.primary_axial_coordinate
    secondary_coordinate = geometry.secondary_axial_coordinate
    belt_coordinate = geometry.belt_axial_coordinate

    print("\n" + "=" * 104)
    print("Deadzone / disengaged-contact check")
    print("This deliberately does NOT call the lambda root or six-by-six engaged-wrap closure.")
    print(
        f"  s={state.shift_position * 1_000.0:.6f} mm, "
        f"deadzone limit={baseline.constants.deadzone_shift * 1_000.0:.6f} mm"
    )
    print(
        f"  x_p={primary_coordinate.value * 1_000.0:.6f} mm, "
        f"x_s={secondary_coordinate.value * 1_000.0:.6f} mm, "
        f"x_b={belt_coordinate.value * 1_000.0:.6f} mm"
    )
    print(
        f"  dx_p/ds={primary_coordinate.d_value_ds:.6f}, "
        f"dx_s/ds={secondary_coordinate.d_value_ds:.6f}, "
        f"dx_b/ds={belt_coordinate.d_value_ds:.6f}, "
        f"H=dtheta/ds={snapshot.secondary_helix.dtheta_ds:.6f} rad/m"
    )

    geometry_ok = (
        state.shift_position < baseline.constants.deadzone_shift
        and abs(secondary_coordinate.value) <= 1.0e-12
        and abs(secondary_coordinate.d_value_ds) <= 1.0e-12
        and abs(belt_coordinate.d_value_ds) <= 1.0e-12
        and abs(snapshot.secondary_helix.dtheta_ds) <= 1.0e-12
    )
    print(f"  inactive-contact geometry check: {'PASS' if geometry_ok else 'CHECK'}")

    primary_free_acceleration = snapshot.engine_torque / snapshot.primary_rotational_inertia
    secondary_free_acceleration = (
        snapshot.secondary_external_torque / snapshot.secondary_absolute_rotational_inertia
    )
    primary_force = snapshot.primary_actuation.bias_force
    unconstrained_primary_shift_acceleration = (
        primary_force / snapshot.shift_translation_inertia.mass
    )

    print("\nExpected future disengaged-branch behaviour:")
    print("  tau_p = tau_s = 0; no lambda variables or wrap equations are active.")
    print("  belt_acceleration = 0 in the absence of a separate belt drag model.")
    print(
        f"  primary free acceleration = tau_eng / I_p = {primary_free_acceleration:.6f} rad/s^2"
    )
    print(
        "  secondary free acceleration = tau_external / I_s,total = "
        f"{secondary_free_acceleration:.6f} rad/s^2"
    )
    print(
        "  primary-only unconstrained shift estimate = F_p / M_trans = "
        f"{unconstrained_primary_shift_acceleration:.6f} m/s^2"
    )
    print(
        "  The final disengaged branch still needs its own travel-limit/event policy; this check only "
        "verifies that the geometry correctly removes secondary, belt, and helix contact coupling."
    )


def _solve_state(
    *,
    model,
    state: CVTDynamicState,
    seeds: Iterable[tuple[float, float]],
    lambda_min: float,
    lambda_max: float,
    residual_tolerance: float,
    max_nfev: int,
) -> RootAttempt:
    snapshot = model.snapshot(state=state)
    fixed_equations = build_state_fixed_equations(snapshot=snapshot)
    residual_function = _build_residual_function(snapshot=snapshot, fixed_equations=fixed_equations)

    best: RootAttempt | None = None
    for seed in seeds:
        attempt = _solve_seed(
            residual_function=residual_function,
            seed=seed,
            lambda_min=lambda_min,
            lambda_max=lambda_max,
            residual_tolerance=residual_tolerance,
            max_nfev=max_nfev,
        )
        if best is None:
            best = attempt
            continue
        if attempt.accepted and not best.accepted:
            best = attempt
        elif attempt.evaluation is not None and best.evaluation is not None:
            if attempt.evaluation.residual_norm < best.evaluation.residual_norm:
                best = attempt
    if best is None:
        raise RuntimeError("No stick-root seed was supplied.")
    return best


def _solve_seed(
    *,
    residual_function: Callable[[np.ndarray], StickEvaluation],
    seed: tuple[float, float],
    lambda_min: float,
    lambda_max: float,
    residual_tolerance: float,
    max_nfev: int,
) -> RootAttempt:
    try:
        optimized = least_squares(
            lambda lambda_values: residual_function(lambda_values).residual_vector,
            x0=np.array(seed, dtype=float),
            bounds=(
                np.array((lambda_min, lambda_min), dtype=float),
                np.array((lambda_max, lambda_max), dtype=float),
            ),
            method="trf",
            jac="3-point",
            x_scale="jac",
            xtol=1.0e-12,
            ftol=1.0e-12,
            gtol=1.0e-12,
            max_nfev=max_nfev,
        )
        evaluation = residual_function(optimized.x)
        accepted = bool(optimized.success) and evaluation.residual_norm <= residual_tolerance
        jacobian_condition = None
        if accepted:
            jacobian_condition = float(
                np.linalg.cond(
                    _finite_difference_jacobian(
                        residual_function=residual_function,
                        lambdas=optimized.x,
                        lambda_min=lambda_min,
                        lambda_max=lambda_max,
                    )
                )
            )
        return RootAttempt(
            evaluation=evaluation,
            optimizer_success=bool(optimized.success),
            accepted=accepted,
            nfev=int(optimized.nfev),
            message=str(optimized.message).replace("\n", " "),
            jacobian_condition_number=jacobian_condition,
        )
    except Exception as error:
        return RootAttempt(
            evaluation=None,
            optimizer_success=False,
            accepted=False,
            nfev=0,
            message="exception",
            jacobian_condition_number=None,
            error=f"{type(error).__name__}: {error}",
        )


def _build_residual_function(*, snapshot, fixed_equations) -> Callable[[np.ndarray], StickEvaluation]:
    def evaluate(lambdas: np.ndarray) -> StickEvaluation:
        context = TrialEquationContext(
            snapshot=snapshot,
            friction_utilization=TrialFrictionUtilization(
                primary_lambda=float(lambdas[0]),
                secondary_lambda=float(lambdas[1]),
            ),
        )
        result = build_trial_six_by_six_system(
            fixed_equations=fixed_equations,
            trial_context=context,
        ).solve()
        residual_primary, residual_secondary = _no_slip_errors(snapshot=snapshot, unknowns=result.unknowns)
        return StickEvaluation(
            lambda_primary=float(lambdas[0]),
            lambda_secondary=float(lambdas[1]),
            residual_primary=residual_primary,
            residual_secondary=residual_secondary,
            trial_result=result,
        )
    return evaluate


def _no_slip_errors(*, snapshot, unknowns) -> tuple[float, float]:
    geometry = snapshot.geometry
    state = snapshot.state
    return (
        unknowns.belt_acceleration
        - geometry.primary.effective * unknowns.primary_angular_acceleration
        - geometry.primary.d_effective_ds * state.shift_speed * state.primary_angular_speed,
        unknowns.belt_acceleration
        - geometry.secondary.effective * unknowns.secondary_angular_acceleration
        - geometry.secondary.d_effective_ds * state.shift_speed * state.secondary_angular_speed,
    )


def _finite_difference_jacobian(*, residual_function, lambdas, lambda_min, lambda_max) -> np.ndarray:
    jacobian = np.empty((2, 2), dtype=float)
    for column in range(2):
        room = min(lambdas[column] - lambda_min, lambda_max - lambdas[column])
        step = min(1.0e-5 * max(1.0, abs(lambdas[column])), 0.25 * room)
        if step <= 0.0:
            raise ValueError("Cannot form Jacobian at a lambda bound.")
        plus = np.array(lambdas, dtype=float)
        minus = np.array(lambdas, dtype=float)
        plus[column] += step
        minus[column] -= step
        jacobian[:, column] = (
            residual_function(plus).residual_vector - residual_function(minus).residual_vector
        ) / (2.0 * step)
    return jacobian


def _print_root_attempt(*, attempt: RootAttempt) -> None:
    if attempt.evaluation is None:
        print(f"  ERROR: {attempt.error}")
        return
    evaluation = attempt.evaluation
    unknowns = evaluation.trial_result.unknowns
    print(
        f"  accepted={attempt.accepted}; lambda_p={evaluation.lambda_primary:.10f}, "
        f"lambda_s={evaluation.lambda_secondary:.10f}, ||R||={evaluation.residual_norm:.3e} m/s^2"
    )
    print(
        f"  tau_p={unknowns.primary_torque:.6f} N m, tau_s={unknowns.secondary_torque:.6f} N m, "
        f"s_ddot={unknowns.shift_acceleration:.6f} m/s^2"
    )
    print(
        f"  R_p={evaluation.residual_primary:.3e}, R_s={evaluation.residual_secondary:.3e}, "
        f"cond(A)={evaluation.trial_result.condition_number:.3e}, "
        f"cond(J)={attempt.jacobian_condition_number if attempt.jacobian_condition_number is not None else float('nan'):.3e}"
    )
    print(f"  nfev={attempt.nfev}; optimizer={'success' if attempt.optimizer_success else 'failed'} ({attempt.message})")


def _parse_shift_speeds(value: str, parser: argparse.ArgumentParser) -> tuple[float, ...]:
    try:
        speeds = tuple(float(token.strip()) for token in value.split(",") if token.strip())
    except ValueError:
        parser.error("--shift-speeds-mm-s must be comma-separated finite numbers.")
    if not speeds or not all(isfinite(speed) for speed in speeds):
        parser.error("--shift-speeds-mm-s must contain at least one finite number.")
    return tuple(sorted(set(speeds)))


def _continuation_order(speeds: tuple[float, ...]) -> tuple[float, ...]:
    # Start at the value nearest zero, then follow positive and negative branches
    # away from it so each accepted root can seed a nearby continuation point.
    anchor = min(speeds, key=abs)
    positive = sorted(speed for speed in speeds if speed > anchor)
    negative = sorted((speed for speed in speeds if speed < anchor), reverse=True)
    return (anchor,) + tuple(positive) + tuple(negative)


def _deduplicate_seeds(seeds: Iterable[tuple[float, float] | None]) -> tuple[tuple[float, float], ...]:
    result: list[tuple[float, float]] = []
    for seed in seeds:
        if seed is None:
            continue
        if seed not in result:
            result.append(seed)
    return tuple(result)


if __name__ == "__main__":
    main()
