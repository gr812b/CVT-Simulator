"""Map primary tuning choices to coupled shift tendency before long launches.

The map fixes a primary shaft speed, constructs no-slip states across engaged
shift travel, and forces the stick--stick closure only to expose the *required*
traction and shift acceleration.  A zero of ``s_ddot(s)`` is an instantaneous
shift equilibrium at that chosen speed.  A negative local slope is restoring:

    s < s*  -> s_ddot > 0,
    s > s*  -> s_ddot < 0.

This is a tuning diagnostic, not a controller design and not a claim that every
mapped point is statically admissible.  The lambda panel shows that separately.

Examples:

    python tools/preview_primary_shift_tuning.py --no-show
    python tools/preview_primary_shift_tuning.py \\
        --flyweight-mass-kg 0.5 --target-lower-stop-release-rpm 2500 --no-show
    python tools/preview_primary_shift_tuning.py \\
        --flyweight-mass-kg 2.0 --primary-ramp-angle-deg 20 \\
        --target-lower-stop-release-rpm 2400 --save artifacts/primary_tuning.png
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

from baja_trial_baseline import BajaTrialConstants, RPM_TO_RAD_PER_SECOND, build_baja_trial_baseline  # noqa: E402
from cinder.contact import ContactRegime, ContactTractionLaw, ContactTractionUtilization  # noqa: E402
from cinder.dynamics import EngagedContactSolveSettings, LambdaSearchBounds  # noqa: E402
from cinder.integration import CVTDynamicState  # noqa: E402
from cinder.integration.cvt_contact import EngagedCVTContactEvaluator  # noqa: E402
from primary_tuning import PrimaryTuningRequest, PrimaryTuningResult, resolve_primary_tuning  # noqa: E402

_RPM_PER_RADIAN_PER_SECOND = 60.0 / (2.0 * np.pi)


@dataclass(frozen=True, slots=True)
class TuningMap:
    shift: NDArray[np.float64]
    primary_rpm: tuple[float, ...]
    shift_acceleration: NDArray[np.float64]
    primary_lambda: NDArray[np.float64]
    primary_actuation_force: NDArray[np.float64]


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flyweight-mass-kg", type=float, default=0.5)
    parser.add_argument("--primary-ramp-angle-deg", type=float, default=30.0)
    parser.add_argument("--primary-spring-rate-n-per-m", type=float, default=12_784.0)
    parser.add_argument("--primary-preload-mm", type=float, default=30.0)
    parser.add_argument(
        "--target-lower-stop-release-rpm",
        type=float,
        default=None,
        help="Derive preload so free primary force at the lower stop is zero at this speed [rpm].",
    )
    parser.add_argument(
        "--primary-rpm",
        type=float,
        nargs="+",
        default=(2400.0, 3000.0, 3400.0),
        help="Primary-speed slices evaluated in the map [rpm].",
    )
    parser.add_argument("--shift-samples", type=int, default=61)
    parser.add_argument("--static-lambda-limit", type=float, default=0.65)
    parser.add_argument("--kinetic-lambda", type=float, default=0.55)
    parser.add_argument("--save", type=Path)
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    for name, value in (
        ("--flyweight-mass-kg", args.flyweight_mass_kg),
        ("--primary-ramp-angle-deg", args.primary_ramp_angle_deg),
        ("--primary-spring-rate-n-per-m", args.primary_spring_rate_n_per_m),
        ("--primary-preload-mm", args.primary_preload_mm),
        ("--static-lambda-limit", args.static_lambda_limit),
        ("--kinetic-lambda", args.kinetic_lambda),
    ):
        if not isfinite(value):
            parser.error(f"{name} must be finite.")
    if args.target_lower_stop_release_rpm is not None:
        if not isfinite(args.target_lower_stop_release_rpm) or args.target_lower_stop_release_rpm <= 0.0:
            parser.error("--target-lower-stop-release-rpm must be finite and positive.")
    if args.shift_samples < 5:
        parser.error("--shift-samples must be at least five.")
    if not args.primary_rpm or any((not isfinite(value) or value <= 0.0) for value in args.primary_rpm):
        parser.error("--primary-rpm requires one or more finite positive values.")
    return args


def _build_evaluator(constants: BajaTrialConstants, *, static_limit: float, kinetic_lambda: float) -> EngagedCVTContactEvaluator:
    baseline = build_baja_trial_baseline(constants)
    law = ContactTractionLaw.symmetric(
        primary_static_lambda_limit=static_limit,
        secondary_static_lambda_limit=static_limit,
        primary_kinetic_lambda_magnitude=kinetic_lambda,
        secondary_kinetic_lambda_magnitude=kinetic_lambda,
    )
    return EngagedCVTContactEvaluator(
        model=baseline.model,
        traction_law=law,
        solve_settings=EngagedContactSolveSettings(
            lambda_search_bounds=LambdaSearchBounds.symmetric(
                primary_half_width=3.0,
                secondary_half_width=3.0,
            ),
            initial_guess=ContactTractionUtilization(primary_lambda=0.0, secondary_lambda=0.0),
            maximum_closure_condition_number=1.0e8,
        ),
    )


def _map_tuning(
    *,
    constants: BajaTrialConstants,
    primary_rpm: Iterable[float],
    shift_samples: int,
    static_limit: float,
    kinetic_lambda: float,
) -> TuningMap:
    evaluator = _build_evaluator(constants, static_limit=static_limit, kinetic_lambda=kinetic_lambda)
    shift = np.linspace(
        constants.deadzone_shift + 0.05e-3,
        constants.max_shift - 0.05e-3,
        shift_samples,
    )
    rpm_values = tuple(float(value) for value in primary_rpm)
    acceleration = np.full((len(rpm_values), shift_samples), np.nan)
    primary_lambda = np.full_like(acceleration, np.nan)
    primary_force = np.full_like(acceleration, np.nan)

    for rpm_index, rpm in enumerate(rpm_values):
        omega_p = rpm * RPM_TO_RAD_PER_SECOND
        for shift_index, s in enumerate(shift):
            geometry = evaluator.model.geometry.evaluate(float(s))
            omega_s = omega_p * geometry.primary.effective / geometry.secondary.effective
            state = CVTDynamicState(
                primary_angular_speed=omega_p,
                secondary_angular_speed=omega_s,
                belt_speed=omega_p * geometry.primary.effective,
                shift_position=float(s),
                shift_speed=0.0,
                secondary_shaft_angle=0.0,
            )
            try:
                evaluation = evaluator.evaluate_vector(
                    time=0.0,
                    vector=state.as_vector(),
                    regime=ContactRegime.stick_stick(),
                )
            except (RuntimeError, ValueError, FloatingPointError):
                continue
            if not evaluation.branch_result.accepted:
                continue
            acceleration[rpm_index, shift_index] = evaluation.closure_unknowns.shift_acceleration
            primary_lambda[rpm_index, shift_index] = evaluation.traction_utilization.primary_lambda
            primary_force[rpm_index, shift_index] = evaluation.snapshot.primary_actuation.bias_force

    return TuningMap(
        shift=shift,
        primary_rpm=rpm_values,
        shift_acceleration=acceleration,
        primary_lambda=primary_lambda,
        primary_actuation_force=primary_force,
    )


def _zero_crossings(shift: NDArray[np.float64], values: NDArray[np.float64]) -> tuple[tuple[float, bool], ...]:
    crossings: list[tuple[float, bool]] = []
    for left, right, f_left, f_right in zip(shift[:-1], shift[1:], values[:-1], values[1:], strict=True):
        if not all(np.isfinite((f_left, f_right))) or f_left == f_right:
            continue
        if f_left == 0.0 or f_left * f_right < 0.0:
            fraction = 0.0 if f_left == 0.0 else -f_left / (f_right - f_left)
            root = left + fraction * (right - left)
            slope = (f_right - f_left) / (right - left)
            crossings.append((float(root), bool(slope < 0.0)))
    return tuple(crossings)


def _plot_map(*, tuning: TuningMap, resolved: PrimaryTuningResult, static_limit: float) -> plt.Figure:
    figure, axes = plt.subplots(3, 1, figsize=(11, 11), sharex=True, constrained_layout=True)
    shift_mm = tuning.shift * 1.0e3
    for index, rpm in enumerate(tuning.primary_rpm):
        label = f"{rpm:.0f} rpm"
        axes[0].plot(shift_mm, tuning.shift_acceleration[index], label=label)
        axes[1].plot(shift_mm, tuning.primary_lambda[index], label=label)
        axes[2].plot(shift_mm, tuning.primary_actuation_force[index], label=label)

    axes[0].axhline(0.0, linestyle=":")
    axes[0].set_title(r"Forced stick--stick shift tendency $\ddot{s}(s)$")
    axes[0].set_ylabel(r"Shift acceleration [m/s$^2$]")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="best")

    axes[1].axhline(static_limit, linestyle="--", label="static limit")
    axes[1].axhline(-static_limit, linestyle="--")
    axes[1].set_title(r"Required primary traction utilization $\lambda_p$")
    axes[1].set_ylabel(r"$\lambda_p$ [-]")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(loc="best")

    axes[2].axhline(0.0, linestyle=":")
    axes[2].set_title("Primary actuator bias force")
    axes[2].set_xlabel("Engaged shift coordinate [mm]")
    axes[2].set_ylabel("Closing force [N]")
    axes[2].grid(True, alpha=0.25)
    axes[2].legend(loc="best")

    description = (
        f"m_f={resolved.request.flyweight_mass:.3f} kg, "
        f"ramp={resolved.request.ramp_angle_degrees:.1f} deg, "
        f"k_p={resolved.request.spring_rate:.0f} N/m, "
        f"preload={resolved.resolved_preload * 1e3:.2f} mm"
    )
    if resolved.target_lower_stop_release_rpm is not None:
        description += f", lower-stop release target={resolved.target_lower_stop_release_rpm:.0f} rpm"
    figure.suptitle("Primary shift-tuning map\n" + description, fontsize=14)
    return figure


def main() -> None:
    args = _parse_arguments()
    request = PrimaryTuningRequest(
        flyweight_mass=args.flyweight_mass_kg,
        ramp_angle_degrees=args.primary_ramp_angle_deg,
        spring_rate=args.primary_spring_rate_n_per_m,
        explicit_preload=args.primary_preload_mm * 1.0e-3,
        target_lower_stop_release_rpm=args.target_lower_stop_release_rpm,
    )
    resolved = resolve_primary_tuning(
        reference_constants=BajaTrialConstants(),
        request=request,
    )
    tuning = _map_tuning(
        constants=resolved.constants,
        primary_rpm=args.primary_rpm,
        shift_samples=args.shift_samples,
        static_limit=args.static_lambda_limit,
        kinetic_lambda=args.kinetic_lambda,
    )

    print("\nPrimary shift-tuning map")
    print("=" * 88)
    print(
        f"flyweight mass={request.flyweight_mass:.4f} kg; ramp={request.ramp_angle_degrees:.2f} deg; "
        f"spring rate={request.spring_rate:.2f} N/m; resolved preload={resolved.resolved_preload * 1e3:.4f} mm"
    )
    if resolved.target_lower_stop_release_rpm is not None:
        print(
            "lower-stop release target="
            f"{resolved.target_lower_stop_release_rpm:.2f} rpm; "
            f"recovered primary force={resolved.lower_stop_force_at_target:+.3e} N"
        )
    for index, rpm in enumerate(tuning.primary_rpm):
        crossings = _zero_crossings(tuning.shift, tuning.shift_acceleration[index])
        if not crossings:
            print(f"  {rpm:.0f} rpm: no in-range shift equilibrium in the forced stick map.")
            continue
        rendered = ", ".join(
            f"{location * 1e3:.3f} mm ({'restoring' if stable else 'diverging'})"
            for location, stable in crossings
        )
        print(f"  {rpm:.0f} rpm: equilibrium candidates: {rendered}")

    figure = _plot_map(tuning=tuning, resolved=resolved, static_limit=args.static_lambda_limit)
    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180)
        print(f"Saved {args.save}")
    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
