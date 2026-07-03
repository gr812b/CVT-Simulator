"""Diagnose mixed-slip and both-slip branches from one frozen engaged snapshot.

This is a branch diagnostic, not a contact-mode selector.  It calls the public
engaged-contact API directly:

* primary slip / secondary stick: one bounded lambda root;
* primary stick / secondary slip: one bounded lambda root;
* both slip: one direct 8x8 closure solve for each selected kinetic direction.

At an exactly no-slip frozen state, a kinetic direction is *incipient*: the
script checks it against the solved relative acceleration.  In a later time
integration, an established non-zero relative speed takes precedence when
selecting a kinetic direction.

Run from cvtModel/:

    python tools/diagnose_slip_branches.py
    python tools/diagnose_slip_branches.py --kinetic-utilization 0.45
    python tools/diagnose_slip_branches.py --scenario active-shift --no-scan

The default static and kinetic utilizations are diagnostic values.  They are
not yet a calibrated rubber-belt friction law.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import sys
from typing import Callable

import numpy as np

# Support both normal src/cinder repositories and direct-overlay layouts.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if (_candidate / "cinder").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import BajaTrialBaseline, build_baja_trial_baseline
from cinder.contact import (
    ContactInterface,
    EngagedContactMode,
    KineticSlipSpecification,
    SlipDirection,
)
from cinder.dynamics import (
    CVTDynamicState,
    EngagedContactSolveResult,
    EngagedContactSolveSettings,
    FrictionUtilizationBounds,
    TrialFrictionUtilization,
    evaluate_both_slip,
    solve_primary_slip_secondary_stick,
    solve_primary_stick_secondary_slip,
)

_DEFAULT_STATIC_LIMIT = 0.65
_DEFAULT_KINETIC_UTILIZATION = 0.55
_DEFAULT_SCAN_MINIMUM = 0.05
_DEFAULT_SCAN_SAMPLES = 13


@dataclass(frozen=True, slots=True)
class MixedBranchReport:
    """One mixed-branch solve plus full branch-admissibility checks."""

    label: str
    result: EngagedContactSolveResult
    slip: KineticSlipSpecification
    slip_direction_consistent: bool
    normal_resultants_positive: bool

    @property
    def root_exists(self) -> bool:
        """Whether the bounded 1D stick residual was actually closed."""

        return self.result.accepted

    @property
    def branch_admissible(self) -> bool:
        """Whether the diagnostic branch passes all checks available here."""

        return (
            self.root_exists
            and self.slip_direction_consistent
            and self.normal_resultants_positive
        )


@dataclass(frozen=True, slots=True)
class BothSlipReport:
    """One direct both-slip closure and the two direction checks."""

    label: str
    result: object

    @property
    def normal_resultants_positive(self) -> bool:
        unknowns = self.result.trial.closure.unknowns
        return (
            unknowns.primary_normal_resultant > 0.0
            and unknowns.secondary_normal_resultant > 0.0
        )

    @property
    def branch_admissible(self) -> bool:
        return (
            self.normal_resultants_positive
            and self.result.primary_direction_is_consistent
            and self.result.secondary_direction_is_consistent
        )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect the 1D mixed-slip and direct both-slip CINDER branches."
    )
    parser.add_argument(
        "--scenario",
        choices=("quasi-static", "active-shift"),
        default="quasi-static",
        help="Frozen engaged baseline state to inspect.",
    )
    parser.add_argument(
        "--static-limit",
        type=float,
        default=_DEFAULT_STATIC_LIMIT,
        help="Common positive static utilization limit for the sticking contact.",
    )
    parser.add_argument(
        "--kinetic-utilization",
        type=float,
        default=_DEFAULT_KINETIC_UTILIZATION,
        help="Positive kinetic-utilization magnitude imposed at a slipping contact.",
    )
    parser.add_argument(
        "--scan-minimum",
        type=float,
        default=_DEFAULT_SCAN_MINIMUM,
        help="Smallest kinetic utilization in the mixed-branch scan.",
    )
    parser.add_argument(
        "--scan-samples",
        type=int,
        default=_DEFAULT_SCAN_SAMPLES,
        help="Number of kinetic-utilization points in each mixed-branch scan.",
    )
    parser.add_argument(
        "--no-scan",
        action="store_true",
        help="Only evaluate the selected kinetic-utilization point.",
    )
    args = parser.parse_args()

    for name, value in (
        ("--static-limit", args.static_limit),
        ("--kinetic-utilization", args.kinetic_utilization),
        ("--scan-minimum", args.scan_minimum),
    ):
        if not isfinite(value) or value <= 0.0:
            parser.error(f"{name} must be finite and strictly positive.")
    if args.scan_minimum > args.kinetic_utilization:
        parser.error("--scan-minimum must not exceed --kinetic-utilization.")
    if args.scan_samples < 2:
        parser.error("--scan-samples must be at least 2.")
    return args


def main() -> None:
    args = parse_arguments()
    baseline = build_baja_trial_baseline()
    state = _select_state(baseline=baseline, scenario=args.scenario)
    snapshot = baseline.model.snapshot(state=state)
    settings = _settings(static_limit=args.static_limit)

    print("\n" + "=" * 104)
    print("CINDER mixed-slip / both-slip branch diagnostic")
    print("=" * 104)
    print(
        f"Scenario: {args.scenario}; static lambda box=[0, {args.static_limit:.6g}]^2; "
        f"kinetic magnitude={args.kinetic_utilization:.6g}"
    )
    print(
        f"State: omega_p={state.primary_angular_speed:.6f} rad/s, "
        f"omega_s={state.secondary_angular_speed:.6f} rad/s, "
        f"v_b={state.belt_speed:.6f} m/s, s={state.shift_position * 1_000.0:.6f} mm, "
        f"s_dot={state.shift_speed * 1_000.0:.6f} mm/s"
    )
    print(
        "Interpretation: a 1D result has a valid root only when its sticking "
        "acceleration residual closes. A kinetic branch is additionally "
        "admissible only if the solved relative motion agrees with the imposed "
        "slip direction and both normal resultants remain positive."
    )

    mixed_reports = _evaluate_mixed_reports(
        snapshot=snapshot,
        settings=settings,
        kinetic_utilization=args.kinetic_utilization,
    )
    _print_mixed_reports(mixed_reports)

    both_reports = _evaluate_both_slip_reports(
        snapshot=snapshot,
        kinetic_utilization=args.kinetic_utilization,
        tolerances=settings.contact_tolerances,
    )
    _print_both_slip_reports(both_reports)

    if not args.no_scan:
        _print_mixed_scan(
            snapshot=snapshot,
            static_limit=args.static_limit,
            kinetic_minimum=args.scan_minimum,
            kinetic_maximum=args.kinetic_utilization,
            samples=args.scan_samples,
        )


def _select_state(*, baseline: BajaTrialBaseline, scenario: str) -> CVTDynamicState:
    if scenario == "quasi-static":
        return baseline.quasi_static_state
    return baseline.active_shift_state


def _settings(*, static_limit: float) -> EngagedContactSolveSettings:
    return EngagedContactSolveSettings(
        static_bounds=FrictionUtilizationBounds.forward_drive(
            primary_static_limit=static_limit,
            secondary_static_limit=static_limit,
        ),
        initial_guess=TrialFrictionUtilization(
            primary_lambda=0.5 * static_limit,
            secondary_lambda=0.5 * static_limit,
        ),
    )


def _kinetic_specification(
    *,
    interface: ContactInterface,
    direction: SlipDirection,
    kinetic_utilization: float,
) -> KineticSlipSpecification:
    return KineticSlipSpecification(
        interface=interface,
        direction=direction,
        kinetic_utilization=kinetic_utilization,
    )


def _evaluate_mixed_reports(*, snapshot, settings, kinetic_utilization: float) -> tuple[MixedBranchReport, ...]:
    primary_positive = _kinetic_specification(
        interface=ContactInterface.PRIMARY,
        direction=SlipDirection.PULLEY_LEADS_BELT,
        kinetic_utilization=kinetic_utilization,
    )
    primary_negative = _kinetic_specification(
        interface=ContactInterface.PRIMARY,
        direction=SlipDirection.BELT_LEADS_PULLEY,
        kinetic_utilization=kinetic_utilization,
    )
    secondary_positive = _kinetic_specification(
        interface=ContactInterface.SECONDARY,
        direction=SlipDirection.BELT_LEADS_PULLEY,
        kinetic_utilization=kinetic_utilization,
    )
    secondary_negative = _kinetic_specification(
        interface=ContactInterface.SECONDARY,
        direction=SlipDirection.PULLEY_LEADS_BELT,
        kinetic_utilization=kinetic_utilization,
    )

    reports: list[MixedBranchReport] = []
    for label, solver, slip in (
        (
            "primary slip / secondary stick, primary pulley leads belt",
            solve_primary_slip_secondary_stick,
            primary_positive,
        ),
        (
            "primary slip / secondary stick, belt leads primary pulley",
            solve_primary_slip_secondary_stick,
            primary_negative,
        ),
        (
            "primary stick / secondary slip, belt leads secondary pulley",
            solve_primary_stick_secondary_slip,
            secondary_positive,
        ),
        (
            "primary stick / secondary slip, secondary pulley leads belt",
            solve_primary_stick_secondary_slip,
            secondary_negative,
        ),
    ):
        if slip.interface is ContactInterface.PRIMARY:
            result = solver(snapshot=snapshot, primary_slip=slip, settings=settings)
        else:
            result = solver(snapshot=snapshot, secondary_slip=slip, settings=settings)
        unknowns = result.closure.unknowns
        reports.append(
            MixedBranchReport(
                label=label,
                result=result,
                slip=slip,
                slip_direction_consistent=slip.direction_is_consistent(
                    result.relative_motion,
                    tolerances=settings.contact_tolerances,
                ),
                normal_resultants_positive=(
                    unknowns.primary_normal_resultant > 0.0
                    and unknowns.secondary_normal_resultant > 0.0
                ),
            )
        )
    return tuple(reports)


def _evaluate_both_slip_reports(*, snapshot, kinetic_utilization: float, tolerances) -> tuple[BothSlipReport, ...]:
    primary_directions = (
        SlipDirection.PULLEY_LEADS_BELT,
        SlipDirection.BELT_LEADS_PULLEY,
    )
    secondary_directions = (
        SlipDirection.BELT_LEADS_PULLEY,
        SlipDirection.PULLEY_LEADS_BELT,
    )
    reports: list[BothSlipReport] = []
    for primary_direction in primary_directions:
        for secondary_direction in secondary_directions:
            primary_slip = _kinetic_specification(
                interface=ContactInterface.PRIMARY,
                direction=primary_direction,
                kinetic_utilization=kinetic_utilization,
            )
            secondary_slip = _kinetic_specification(
                interface=ContactInterface.SECONDARY,
                direction=secondary_direction,
                kinetic_utilization=kinetic_utilization,
            )
            result = evaluate_both_slip(
                snapshot=snapshot,
                primary_slip=primary_slip,
                secondary_slip=secondary_slip,
                contact_tolerances=tolerances,
            )
            reports.append(
                BothSlipReport(
                    label=(
                        f"primary={primary_direction.value}, "
                        f"secondary={secondary_direction.value}"
                    ),
                    result=result,
                )
            )
    return tuple(reports)


def _print_mixed_reports(reports: tuple[MixedBranchReport, ...]) -> None:
    print("\nMixed branches: one kinetic lambda plus one solved static lambda")
    print("-" * 104)
    for report in reports:
        result = report.result
        motion = result.relative_motion
        unknowns = result.closure.unknowns
        stick = result.sticking_interfaces[0]
        stick_residual = motion.relative_acceleration_at(stick)
        slip_residual = motion.relative_acceleration_at(report.slip.interface)
        print(report.label)
        print(
            f"  fixed lambda_{report.slip.interface.value[0]}={report.slip.signed_lambda:+.6f}; "
            f"solved (lambda_p, lambda_s)=({result.friction_utilization.primary_lambda:+.6f}, "
            f"{result.friction_utilization.secondary_lambda:+.6f})"
        )
        print(
            f"  sticking {stick.value} residual={stick_residual:+.6e} m/s^2; "
            f"slipping {report.slip.interface.value} a_rel={slip_residual:+.6e} m/s^2"
        )
        print(
            f"  root_exists={report.root_exists}; direction_consistent={report.slip_direction_consistent}; "
            f"N_p={unknowns.primary_normal_resultant:.6f} N; "
            f"N_s={unknowns.secondary_normal_resultant:.6f} N; "
            f"normal_positive={report.normal_resultants_positive}; "
            f"branch_admissible={report.branch_admissible}"
        )
        print(
            f"  tau_p={unknowns.primary_torque:.6f} N m; tau_s={unknowns.secondary_torque:.6f} N m; "
            f"s_ddot={unknowns.shift_acceleration:.6f} m/s^2; "
            f"cond(A)={result.closure.condition_number:.3e}; "
            f"active lower/upper={result.active_lower_bounds}/{result.active_upper_bounds}"
        )


def _print_both_slip_reports(reports: tuple[BothSlipReport, ...]) -> None:
    print("\nBoth-slip branches: direct fixed-lambda 8x8 evaluations")
    print("-" * 104)
    for report in reports:
        result = report.result
        unknowns = result.trial.closure.unknowns
        motion = result.trial.relative_motion
        print(report.label)
        print(
            f"  (lambda_p, lambda_s)=({result.trial.friction_utilization.primary_lambda:+.6f}, "
            f"{result.trial.friction_utilization.secondary_lambda:+.6f}); "
            f"a_rel,p={motion.primary_relative_acceleration:+.6e} m/s^2; "
            f"a_rel,s={motion.secondary_relative_acceleration:+.6e} m/s^2"
        )
        print(
            f"  primary direction consistent={result.primary_direction_is_consistent}; "
            f"secondary direction consistent={result.secondary_direction_is_consistent}; "
            f"N_p={unknowns.primary_normal_resultant:.6f} N; N_s={unknowns.secondary_normal_resultant:.6f} N; "
            f"normal_positive={report.normal_resultants_positive}; "
            f"branch_admissible={report.branch_admissible}"
        )
        print(
            f"  tau_p={unknowns.primary_torque:.6f} N m; tau_s={unknowns.secondary_torque:.6f} N m; "
            f"s_ddot={unknowns.shift_acceleration:.6f} m/s^2; "
            f"cond(A)={result.trial.closure.condition_number:.3e}"
        )


def _print_mixed_scan(*, snapshot, static_limit: float, kinetic_minimum: float, kinetic_maximum: float, samples: int) -> None:
    print("\nMixed-branch kinetic-utilization scan")
    print("-" * 104)
    print(
        "Each row solves only the opposite contact's sticking residual. "
        "A failed root means the required static lambda lies outside the configured box."
    )
    values = np.linspace(kinetic_minimum, kinetic_maximum, samples)
    _print_scan_family(
        title="Primary slip (pulley leads belt) / secondary stick",
        values=values,
        static_limit=static_limit,
        slip_factory=lambda value: _kinetic_specification(
            interface=ContactInterface.PRIMARY,
            direction=SlipDirection.PULLEY_LEADS_BELT,
            kinetic_utilization=float(value),
        ),
        solve=lambda settings, slip: solve_primary_slip_secondary_stick(
            snapshot=snapshot,
            primary_slip=slip,
            settings=settings,
        ),
    )
    _print_scan_family(
        title="Primary stick / secondary slip (belt leads pulley)",
        values=values,
        static_limit=static_limit,
        slip_factory=lambda value: _kinetic_specification(
            interface=ContactInterface.SECONDARY,
            direction=SlipDirection.BELT_LEADS_PULLEY,
            kinetic_utilization=float(value),
        ),
        solve=lambda settings, slip: solve_primary_stick_secondary_slip(
            snapshot=snapshot,
            secondary_slip=slip,
            settings=settings,
        ),
    )


def _print_scan_family(*, title: str, values: np.ndarray, static_limit: float, slip_factory: Callable[[float], KineticSlipSpecification], solve: Callable[[EngagedContactSolveSettings, KineticSlipSpecification], EngagedContactSolveResult]) -> None:
    print(f"\n{title}")
    print("  mu_k      lambda_p    lambda_s    a_rel,slip [m/s^2]  root  direction  static-bound")
    for value in values:
        settings = _settings(static_limit=static_limit)
        slip = slip_factory(float(value))
        result = solve(settings, slip)
        a_slip = result.relative_motion.relative_acceleration_at(slip.interface)
        direction_ok = slip.direction_is_consistent(
            result.relative_motion,
            tolerances=settings.contact_tolerances,
        )
        bound = "upper" if any(result.active_upper_bounds) else "-"
        print(
            f"  {value:6.3f}    {result.friction_utilization.primary_lambda:+.6f}  "
            f"{result.friction_utilization.secondary_lambda:+.6f}  {a_slip:+21.6e}  "
            f"{str(result.accepted):5s} {str(direction_ok):9s} {bound}"
        )


if __name__ == "__main__":
    main()
