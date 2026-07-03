"""Probe established-slip contact branches at deliberately slipped states.

This diagnostic constructs engaged states with prescribed non-zero contact
relative speeds, then calls the public branch solvers directly:

* primary slip / secondary stick: one bounded scalar root for lambda_s;
* primary stick / secondary slip: one bounded scalar root for lambda_p;
* both slip: one direct 8x8 closure solve because both kinetic lambdas are known.

The primary purpose is sign and energy interpretation, not contact-law
calibration.  The default symmetric static box [-1.4, 1.4] is deliberately
wider than a forward-drive production traction bound so that reverse-torque
and forward-torque diagnostic cases can both be inspected.

Alongside the detailed console trace, the default run opens a compact
matplotlib summary window with branch status, lambdas, torques, normal
resultants, dissipation, and the local relative-speed dynamics.

Run from cvtModel/:

    python tools/probe_established_slip_states.py
    python tools/probe_established_slip_states.py --relative-speed 0.10
    python tools/probe_established_slip_states.py --save artifacts/slip_probe.png
    python tools/probe_established_slip_states.py --no-show

For a slipping contact, a non-zero relative speed fixes the friction direction
before the closure solve.  The script reports the contact force on the belt and

    P_diss = -F_belt * v_rel.

A physically dissipative kinetic contact has P_diss > 0.  The sign of
v_rel * a_rel is reported separately: it says whether the current dynamics
are reducing or increasing the existing slip speed, and is not itself a
friction-direction validity test because external driving can maintain/grow
slip despite dissipative friction.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np

# Support normal src/cinder repositories and direct-overlay layouts.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if (_candidate / "cinder").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import BajaTrialBaseline, build_baja_trial_baseline
from cinder.contact import (
    ContactInterface,
    KineticSlipSpecification,
    SlipDirection,
)
from cinder.dynamics import (
    CVTDynamicState,
    EngagedContactSolveSettings,
    FrictionUtilizationBounds,
    TrialFrictionUtilization,
    evaluate_both_slip,
    solve_primary_slip_secondary_stick,
    solve_primary_stick_secondary_slip,
)

_DEFAULT_RELATIVE_SPEED = 0.25
_DEFAULT_STATIC_LIMIT = 1.4
_DEFAULT_KINETIC_UTILIZATION = 0.55


@dataclass(frozen=True, slots=True)
class StateCase:
    """One deliberately constructed velocity-level contact state."""

    label: str
    short_label: str
    primary_relative_speed: float
    secondary_relative_speed: float
    mode: str
    primary_direction: SlipDirection | None = None
    secondary_direction: SlipDirection | None = None


@dataclass(frozen=True, slots=True)
class ContactSummary:
    """One interface's local kinematic and energy quantities."""

    relative_speed: float
    relative_acceleration: float
    force_on_belt: float
    dissipation: float


@dataclass(frozen=True, slots=True)
class CaseSummary:
    """Compact top-level record used by the popup figure."""

    case: StateCase
    closure_kind: str
    lambda_primary: float
    lambda_secondary: float
    primary_torque: float
    secondary_torque: float
    primary_normal: float
    secondary_normal: float
    belt_acceleration: float
    shift_acceleration: float
    condition_number: float
    root_accepted: bool
    direction_consistent: bool
    normal_positive: bool
    root_residual: float | None
    primary: ContactSummary
    secondary: ContactSummary

    @property
    def branch_admissible(self) -> bool:
        return self.root_accepted and self.direction_consistent and self.normal_positive


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe mixed-slip and both-slip branches at established relative speeds."
    )
    parser.add_argument(
        "--scenario",
        choices=("quasi-static", "active-shift"),
        default="quasi-static",
        help="Engaged baseline state used for geometry, shift position, and loads.",
    )
    parser.add_argument(
        "--relative-speed",
        type=float,
        default=_DEFAULT_RELATIVE_SPEED,
        help="Magnitude of each deliberately imposed established relative speed [m/s].",
    )
    parser.add_argument(
        "--static-limit",
        type=float,
        default=_DEFAULT_STATIC_LIMIT,
        help="Magnitude of the diagnostic static-lambda box.",
    )
    parser.add_argument(
        "--kinetic-utilization",
        type=float,
        default=_DEFAULT_KINETIC_UTILIZATION,
        help="Positive kinetic-utilization magnitude at each slipping interface.",
    )
    parser.add_argument(
        "--forward-static-box",
        action="store_true",
        help="Use [0, static-limit] rather than the default signed [-static-limit, static-limit] static box.",
    )
    parser.add_argument(
        "--save",
        type=Path,
        help="Optional PNG/PDF/SVG destination for the popup summary figure.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Generate the summary figure without opening its matplotlib window.",
    )
    args = parser.parse_args()
    for option, value in (
        ("--relative-speed", args.relative_speed),
        ("--static-limit", args.static_limit),
        ("--kinetic-utilization", args.kinetic_utilization),
    ):
        if not isfinite(value) or value <= 0.0:
            parser.error(f"{option} must be finite and strictly positive.")
    return args


def main() -> None:
    args = parse_arguments()
    baseline = build_baja_trial_baseline()
    reference_state = _select_state(baseline=baseline, scenario=args.scenario)
    settings = _settings(
        static_limit=args.static_limit,
        forward_static_box=args.forward_static_box,
    )

    print("\n" + "=" * 112)
    print("CINDER established-slip branch probe")
    print("=" * 112)
    print(
        f"Scenario: {args.scenario}; imposed |v_rel|={args.relative_speed:.6f} m/s; "
        f"kinetic utilization={args.kinetic_utilization:.6f}"
    )
    print(
        "Static lambda box: "
        f"[{settings.static_bounds.primary_lower:.6f}, "
        f"{settings.static_bounds.primary_upper:.6f}] at both interfaces"
    )
    print(
        "Reference state: "
        f"omega_p={reference_state.primary_angular_speed:.6f} rad/s, "
        f"omega_s={reference_state.secondary_angular_speed:.6f} rad/s, "
        f"v_b={reference_state.belt_speed:.6f} m/s, "
        f"s={reference_state.shift_position * 1_000.0:.6f} mm"
    )
    print(
        "The state construction keeps v_b, s, s_dot, and psi_s fixed, then adjusts "
        "omega_p and/or omega_s so the requested interface relative speeds are exact."
    )

    summaries: list[CaseSummary] = []
    for case in _cases(relative_speed=args.relative_speed):
        state = _state_with_relative_speeds(
            model=baseline.model,
            reference=reference_state,
            primary_relative_speed=case.primary_relative_speed,
            secondary_relative_speed=case.secondary_relative_speed,
        )
        snapshot = baseline.model.snapshot(state=state)
        _print_case_header(case=case, state=state, snapshot=snapshot)
        if case.mode == "primary_slip_secondary_stick":
            assert case.primary_direction is not None
            summary = _run_primary_slip_secondary_stick(
                case=case,
                snapshot=snapshot,
                direction=case.primary_direction,
                kinetic_utilization=args.kinetic_utilization,
                settings=settings,
            )
        elif case.mode == "primary_stick_secondary_slip":
            assert case.secondary_direction is not None
            summary = _run_primary_stick_secondary_slip(
                case=case,
                snapshot=snapshot,
                direction=case.secondary_direction,
                kinetic_utilization=args.kinetic_utilization,
                settings=settings,
            )
        elif case.mode == "both_slip":
            assert case.primary_direction is not None
            assert case.secondary_direction is not None
            summary = _run_both_slip(
                case=case,
                snapshot=snapshot,
                primary_direction=case.primary_direction,
                secondary_direction=case.secondary_direction,
                kinetic_utilization=args.kinetic_utilization,
                settings=settings,
            )
        else:
            raise RuntimeError(f"Unsupported state case mode: {case.mode!r}")
        summaries.append(summary)

    figure = plot_branch_summary(
        summaries=summaries,
        scenario=args.scenario,
        relative_speed=args.relative_speed,
        kinetic_utilization=args.kinetic_utilization,
        static_limit=args.static_limit,
    )
    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180)
        print(f"\nSaved summary figure to {args.save}")
    if not args.no_show:
        plt.show()


def _select_state(*, baseline: BajaTrialBaseline, scenario: str) -> CVTDynamicState:
    if scenario == "quasi-static":
        return baseline.quasi_static_state
    return baseline.active_shift_state


def _settings(
    *, static_limit: float, forward_static_box: bool
) -> EngagedContactSolveSettings:
    if forward_static_box:
        bounds = FrictionUtilizationBounds.forward_drive(
            primary_static_limit=static_limit,
            secondary_static_limit=static_limit,
        )
        initial = 0.5 * static_limit
    else:
        bounds = FrictionUtilizationBounds(
            primary_lower=-static_limit,
            primary_upper=static_limit,
            secondary_lower=-static_limit,
            secondary_upper=static_limit,
        )
        initial = 0.0
    return EngagedContactSolveSettings(
        static_bounds=bounds,
        initial_guess=TrialFrictionUtilization(
            primary_lambda=initial,
            secondary_lambda=initial,
        ),
    )


def _cases(*, relative_speed: float) -> tuple[StateCase, ...]:
    v = relative_speed
    return (
        StateCase(
            label="primary-only slip: primary pulley leads belt",
            short_label="P slip\nP→belt",
            primary_relative_speed=-v,
            secondary_relative_speed=0.0,
            mode="primary_slip_secondary_stick",
            primary_direction=SlipDirection.PULLEY_LEADS_BELT,
        ),
        StateCase(
            label="primary-only slip: belt leads primary pulley",
            short_label="P slip\nbelt→P",
            primary_relative_speed=+v,
            secondary_relative_speed=0.0,
            mode="primary_slip_secondary_stick",
            primary_direction=SlipDirection.BELT_LEADS_PULLEY,
        ),
        StateCase(
            label="secondary-only slip: belt leads secondary pulley",
            short_label="S slip\nbelt→S",
            primary_relative_speed=0.0,
            secondary_relative_speed=+v,
            mode="primary_stick_secondary_slip",
            secondary_direction=SlipDirection.BELT_LEADS_PULLEY,
        ),
        StateCase(
            label="secondary-only slip: secondary pulley leads belt",
            short_label="S slip\nS→belt",
            primary_relative_speed=0.0,
            secondary_relative_speed=-v,
            mode="primary_stick_secondary_slip",
            secondary_direction=SlipDirection.PULLEY_LEADS_BELT,
        ),
        StateCase(
            label="both slip: primary pulley leads belt; belt leads secondary pulley",
            short_label="both\nP→belt→S",
            primary_relative_speed=-v,
            secondary_relative_speed=+v,
            mode="both_slip",
            primary_direction=SlipDirection.PULLEY_LEADS_BELT,
            secondary_direction=SlipDirection.BELT_LEADS_PULLEY,
        ),
        StateCase(
            label="both slip: belt leads primary pulley; secondary pulley leads belt",
            short_label="both\nP←belt←S",
            primary_relative_speed=+v,
            secondary_relative_speed=-v,
            mode="both_slip",
            primary_direction=SlipDirection.BELT_LEADS_PULLEY,
            secondary_direction=SlipDirection.PULLEY_LEADS_BELT,
        ),
    )


def _state_with_relative_speeds(
    *,
    model,
    reference: CVTDynamicState,
    primary_relative_speed: float,
    secondary_relative_speed: float,
) -> CVTDynamicState:
    """Construct a state satisfying v_rel,j = v_b - r_j omega_j exactly."""

    geometry = model.geometry.evaluate(reference.shift_position)
    primary_speed = (
        reference.belt_speed - primary_relative_speed
    ) / geometry.primary.effective
    secondary_speed = (
        reference.belt_speed - secondary_relative_speed
    ) / geometry.secondary.effective
    return replace(
        reference,
        primary_angular_speed=primary_speed,
        secondary_angular_speed=secondary_speed,
    )


def _print_case_header(*, case: StateCase, state: CVTDynamicState, snapshot) -> None:
    print("\n" + "-" * 112)
    print(case.label)
    print("-" * 112)
    print(
        f"constructed state: omega_p={state.primary_angular_speed:.6f} rad/s, "
        f"omega_s={state.secondary_angular_speed:.6f} rad/s, v_b={state.belt_speed:.6f} m/s"
    )
    print(
        f"input relative speeds: v_rel,p={case.primary_relative_speed:+.6f} m/s, "
        f"v_rel,s={case.secondary_relative_speed:+.6f} m/s"
    )
    print(
        f"known loads after the state change: tau_engine={snapshot.engine_torque:+.6f} N m, "
        f"tau_secondary,external={snapshot.secondary_external_torque:+.6f} N m"
    )


def _slip_spec(
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


def _run_primary_slip_secondary_stick(
    *, case, snapshot, direction, kinetic_utilization, settings
) -> CaseSummary:
    slip = _slip_spec(
        interface=ContactInterface.PRIMARY,
        direction=direction,
        kinetic_utilization=kinetic_utilization,
    )
    result = solve_primary_slip_secondary_stick(
        snapshot=snapshot,
        primary_slip=slip,
        settings=settings,
    )
    return _print_mixed_result(
        case=case,
        snapshot=snapshot,
        result=result,
        slipping_interface=ContactInterface.PRIMARY,
        slip=slip,
        settings=settings,
    )


def _run_primary_stick_secondary_slip(
    *, case, snapshot, direction, kinetic_utilization, settings
) -> CaseSummary:
    slip = _slip_spec(
        interface=ContactInterface.SECONDARY,
        direction=direction,
        kinetic_utilization=kinetic_utilization,
    )
    result = solve_primary_stick_secondary_slip(
        snapshot=snapshot,
        secondary_slip=slip,
        settings=settings,
    )
    return _print_mixed_result(
        case=case,
        snapshot=snapshot,
        result=result,
        slipping_interface=ContactInterface.SECONDARY,
        slip=slip,
        settings=settings,
    )


def _run_both_slip(
    *,
    case,
    snapshot,
    primary_direction,
    secondary_direction,
    kinetic_utilization,
    settings,
) -> CaseSummary:
    primary_slip = _slip_spec(
        interface=ContactInterface.PRIMARY,
        direction=primary_direction,
        kinetic_utilization=kinetic_utilization,
    )
    secondary_slip = _slip_spec(
        interface=ContactInterface.SECONDARY,
        direction=secondary_direction,
        kinetic_utilization=kinetic_utilization,
    )
    result = evaluate_both_slip(
        snapshot=snapshot,
        primary_slip=primary_slip,
        secondary_slip=secondary_slip,
        contact_tolerances=settings.contact_tolerances,
    )
    unknowns = result.trial.closure.unknowns
    motion = result.trial.relative_motion
    normal_positive = (
        unknowns.primary_normal_resultant > 0.0
        and unknowns.secondary_normal_resultant > 0.0
    )
    direction_consistent = (
        result.primary_direction_is_consistent
        and result.secondary_direction_is_consistent
    )
    print("closure: direct 8x8 only; no nonlinear stick residual is solved")
    print(
        f"fixed lambdas: lambda_p={result.trial.friction_utilization.primary_lambda:+.6f}, "
        f"lambda_s={result.trial.friction_utilization.secondary_lambda:+.6f}; "
        f"cond(A)={result.trial.closure.condition_number:.3e}"
    )
    print(
        f"direction consistency: primary={result.primary_direction_is_consistent}; "
        f"secondary={result.secondary_direction_is_consistent}; normal_positive={normal_positive}"
    )
    _print_common_solution(
        snapshot=snapshot,
        unknowns=unknowns,
        motion=motion,
        slipping_interfaces=(ContactInterface.PRIMARY, ContactInterface.SECONDARY),
    )
    return _make_case_summary(
        case=case,
        closure_kind="direct 8x8",
        friction_utilization=result.trial.friction_utilization,
        unknowns=unknowns,
        motion=motion,
        root_accepted=True,
        direction_consistent=direction_consistent,
        normal_positive=normal_positive,
        root_residual=None,
        condition_number=result.trial.closure.condition_number,
        snapshot=snapshot,
    )


def _print_mixed_result(
    *, case, snapshot, result, slipping_interface, slip, settings
) -> CaseSummary:
    unknowns = result.closure.unknowns
    motion = result.relative_motion
    normal_positive = (
        unknowns.primary_normal_resultant > 0.0
        and unknowns.secondary_normal_resultant > 0.0
    )
    direction_consistent = slip.direction_is_consistent(
        motion,
        tolerances=settings.contact_tolerances,
    )
    sticking_interface = (
        ContactInterface.SECONDARY
        if slipping_interface is ContactInterface.PRIMARY
        else ContactInterface.PRIMARY
    )
    stick_speed = motion.relative_speed_at(sticking_interface)
    stick_acceleration = motion.relative_acceleration_at(sticking_interface)
    print("closure: one bounded scalar root for the sticking interface only")
    print(
        f"fixed kinetic lambda_{slipping_interface.value[0]}={slip.signed_lambda:+.6f}; "
        f"solved lambdas: lambda_p={result.friction_utilization.primary_lambda:+.6f}, "
        f"lambda_s={result.friction_utilization.secondary_lambda:+.6f}"
    )
    print(
        f"1D solver: accepted={result.accepted}; success={result.optimizer_success}; "
        f"nfev={result.function_evaluations}; root residual at {sticking_interface.value}="
        f"{stick_acceleration:+.3e} m/s^2; jacobian={result.jacobian[0, 0]:+.6e}"
    )
    print(
        f"slip direction consistent={direction_consistent}; normal_positive={normal_positive}; "
        f"sticking-interface v_rel={stick_speed:+.3e} m/s"
    )
    _print_common_solution(
        snapshot=snapshot,
        unknowns=unknowns,
        motion=motion,
        slipping_interfaces=(slipping_interface,),
    )
    return _make_case_summary(
        case=case,
        closure_kind="1D root",
        friction_utilization=result.friction_utilization,
        unknowns=unknowns,
        motion=motion,
        root_accepted=result.accepted and result.optimizer_success,
        direction_consistent=direction_consistent,
        normal_positive=normal_positive,
        root_residual=stick_acceleration,
        condition_number=result.closure.condition_number,
        snapshot=snapshot,
    )


def _print_common_solution(*, snapshot, unknowns, motion, slipping_interfaces) -> None:
    geometry = snapshot.geometry
    print(
        f"unknowns: tau_p={unknowns.primary_torque:+.6f} N m, "
        f"tau_s={unknowns.secondary_torque:+.6f} N m, "
        f"N_p={unknowns.primary_normal_resultant:+.6f} N, "
        f"N_s={unknowns.secondary_normal_resultant:+.6f} N"
    )
    print(
        f"          alpha_p={unknowns.primary_angular_acceleration:+.6f} rad/s^2, "
        f"alpha_s={unknowns.secondary_angular_acceleration:+.6f} rad/s^2, "
        f"v_b_dot={unknowns.belt_acceleration:+.6f} m/s^2, "
        f"s_ddot={unknowns.shift_acceleration:+.6f} m/s^2"
    )
    for interface in (ContactInterface.PRIMARY, ContactInterface.SECONDARY):
        v_rel = motion.relative_speed_at(interface)
        a_rel = motion.relative_acceleration_at(interface)
        force_on_belt = _contact_force_on_belt(
            interface=interface, unknowns=unknowns, geometry=geometry
        )
        dissipation = -force_on_belt * v_rel
        tendency = v_rel * a_rel
        tag = "SLIP" if interface in slipping_interfaces else "STICK"
        print(
            f"{interface.value:9s} {tag}: v_rel={v_rel:+.6f} m/s, "
            f"a_rel={a_rel:+.6f} m/s^2, F_on_belt={force_on_belt:+.6f} N, "
            f"P_diss={dissipation:+.6f} W, v_rel*a_rel={tendency:+.6f} m^2/s^3"
        )
    print(
        "Interpretation: P_diss > 0 means the imposed kinetic friction direction removes "
        "energy from the actual relative motion. v_rel*a_rel < 0 means that current "
        "relative speed is shrinking; > 0 means external dynamics are growing it."
    )


def _make_case_summary(
    *,
    case: StateCase,
    closure_kind: str,
    friction_utilization,
    unknowns,
    motion,
    root_accepted: bool,
    direction_consistent: bool,
    normal_positive: bool,
    root_residual: float | None,
    condition_number: float,
    snapshot,
) -> CaseSummary:
    geometry = snapshot.geometry
    primary = _contact_summary(
        interface=ContactInterface.PRIMARY,
        unknowns=unknowns,
        motion=motion,
        geometry=geometry,
    )
    secondary = _contact_summary(
        interface=ContactInterface.SECONDARY,
        unknowns=unknowns,
        motion=motion,
        geometry=geometry,
    )
    return CaseSummary(
        case=case,
        closure_kind=closure_kind,
        lambda_primary=friction_utilization.primary_lambda,
        lambda_secondary=friction_utilization.secondary_lambda,
        primary_torque=unknowns.primary_torque,
        secondary_torque=unknowns.secondary_torque,
        primary_normal=unknowns.primary_normal_resultant,
        secondary_normal=unknowns.secondary_normal_resultant,
        belt_acceleration=unknowns.belt_acceleration,
        shift_acceleration=unknowns.shift_acceleration,
        condition_number=condition_number,
        root_accepted=root_accepted,
        direction_consistent=direction_consistent,
        normal_positive=normal_positive,
        root_residual=root_residual,
        primary=primary,
        secondary=secondary,
    )


def _contact_summary(*, interface, unknowns, motion, geometry) -> ContactSummary:
    relative_speed = motion.relative_speed_at(interface)
    force_on_belt = _contact_force_on_belt(
        interface=interface,
        unknowns=unknowns,
        geometry=geometry,
    )
    return ContactSummary(
        relative_speed=relative_speed,
        relative_acceleration=motion.relative_acceleration_at(interface),
        force_on_belt=force_on_belt,
        dissipation=-force_on_belt * relative_speed,
    )


def plot_branch_summary(
    *,
    summaries: list[CaseSummary],
    scenario: str,
    relative_speed: float,
    kinetic_utilization: float,
    static_limit: float,
):
    """Create the compact popup view; detailed line items remain in the console."""

    indices = np.arange(len(summaries), dtype=float)
    labels = [summary.case.short_label for summary in summaries]
    width = 0.34

    figure, axes = plt.subplots(2, 3, figsize=(18, 10), constrained_layout=True)
    (
        axis_lambda,
        axis_torque,
        axis_normal,
        axis_dissipation,
        axis_kinematics,
        axis_status,
    ) = axes.flat

    figure.suptitle(
        "CINDER established-slip branch summary — "
        f"{scenario}; |v_rel|={relative_speed:g} m/s; "
        rf"$|\lambda_k|$={kinetic_utilization:g}",
        fontsize=15,
    )

    lambda_primary = np.array([summary.lambda_primary for summary in summaries])
    lambda_secondary = np.array([summary.lambda_secondary for summary in summaries])
    axis_lambda.axhline(0.0, linewidth=1.0)
    axis_lambda.axhline(static_limit, linewidth=1.0, linestyle="--")
    axis_lambda.axhline(-static_limit, linewidth=1.0, linestyle="--")
    axis_lambda.plot(indices, lambda_primary, marker="o", label=r"$\lambda_p$")
    axis_lambda.plot(indices, lambda_secondary, marker="s", label=r"$\lambda_s$")
    axis_lambda.set_title("Solved contact utilizations")
    axis_lambda.set_ylabel(r"$\lambda$ [-]")
    axis_lambda.legend(loc="best")
    _format_case_axis(axis_lambda, labels)

    primary_torque = np.array([summary.primary_torque for summary in summaries])
    secondary_torque = np.array([summary.secondary_torque for summary in summaries])
    axis_torque.axhline(0.0, linewidth=1.0)
    axis_torque.bar(indices - width / 2.0, primary_torque, width, label=r"$\tau_p$")
    axis_torque.bar(indices + width / 2.0, secondary_torque, width, label=r"$\tau_s$")
    axis_torque.set_title("Pulley torques")
    axis_torque.set_ylabel("torque [N m]")
    axis_torque.legend(loc="best")
    _format_case_axis(axis_torque, labels)

    primary_normal = np.array([summary.primary_normal for summary in summaries])
    secondary_normal = np.array([summary.secondary_normal for summary in summaries])
    axis_normal.axhline(0.0, linewidth=1.0)
    axis_normal.bar(indices - width / 2.0, primary_normal, width, label=r"$N_p$")
    axis_normal.bar(indices + width / 2.0, secondary_normal, width, label=r"$N_s$")
    axis_normal.set_title("Normal resultants")
    axis_normal.set_ylabel("normal resultant [N]")
    axis_normal.legend(loc="best")
    _format_case_axis(axis_normal, labels)

    primary_dissipation = np.array(
        [summary.primary.dissipation for summary in summaries]
    )
    secondary_dissipation = np.array(
        [summary.secondary.dissipation for summary in summaries]
    )
    axis_dissipation.axhline(0.0, linewidth=1.0)
    axis_dissipation.bar(
        indices - width / 2.0, primary_dissipation, width, label=r"$P_{{\rm diss},p}$"
    )
    axis_dissipation.bar(
        indices + width / 2.0, secondary_dissipation, width, label=r"$P_{{\rm diss},s}$"
    )
    axis_dissipation.set_title("Contact dissipation")
    axis_dissipation.set_ylabel("power [W]")
    axis_dissipation.legend(loc="best")
    _format_case_axis(axis_dissipation, labels)

    axis_kinematics.axhline(0.0, linewidth=1.0)
    axis_kinematics.axvline(0.0, linewidth=1.0)
    for index, summary in enumerate(summaries, start=1):
        axis_kinematics.scatter(
            summary.primary.relative_speed,
            summary.primary.relative_acceleration,
            marker="o",
            label="primary" if index == 1 else None,
        )
        axis_kinematics.annotate(
            f"P{index}",
            (summary.primary.relative_speed, summary.primary.relative_acceleration),
            xytext=(4, 4),
            textcoords="offset points",
        )
        axis_kinematics.scatter(
            summary.secondary.relative_speed,
            summary.secondary.relative_acceleration,
            marker="s",
            label="secondary" if index == 1 else None,
        )
        axis_kinematics.annotate(
            f"S{index}",
            (summary.secondary.relative_speed, summary.secondary.relative_acceleration),
            xytext=(4, 4),
            textcoords="offset points",
        )
    axis_kinematics.set_title("Local relative-speed dynamics")
    axis_kinematics.set_xlabel(r"$v_{\rm rel}$ [m/s]")
    axis_kinematics.set_ylabel(r"$a_{\rm rel}$ [m/s$^2$]")
    axis_kinematics.legend(loc="best")
    axis_kinematics.grid(True, alpha=0.25)

    _draw_status_table(axis=axis_status, summaries=summaries)
    return figure


def _format_case_axis(axis, labels: list[str]) -> None:
    axis.set_xticks(np.arange(len(labels)))
    axis.set_xticklabels(labels, fontsize=8)
    axis.grid(True, axis="y", alpha=0.25)


def _draw_status_table(*, axis, summaries: list[CaseSummary]) -> None:
    axis.axis("off")
    rows = []
    for index, summary in enumerate(summaries, start=1):
        status = "admissible" if summary.branch_admissible else "check"
        residual = (
            "—" if summary.root_residual is None else f"{summary.root_residual:.1e}"
        )
        rows.append(
            (
                str(index),
                summary.closure_kind,
                status,
                f"{summary.shift_acceleration:.1f}",
                f"{summary.belt_acceleration:.1f}",
                residual,
            )
        )
    table = axis.table(
        cellText=rows,
        colLabels=(
            "case",
            "closure",
            "status",
            r"$\ddot{s}$",
            r"$\dot v_b$",
            "stick R",
        ),
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1.08, 1.55)
    axis.set_title("Branch status and translational response")
    axis.text(
        0.5,
        0.035,
        "‘admissible’ here means the imposed slip direction, normal positivity,\n"
        "and—where relevant—the bounded 1D stick root all passed.",
        ha="center",
        va="bottom",
        transform=axis.transAxes,
        fontsize=8,
    )


def _contact_force_on_belt(*, interface: ContactInterface, unknowns, geometry) -> float:
    if interface is ContactInterface.PRIMARY:
        return unknowns.primary_torque / geometry.primary.effective
    if interface is ContactInterface.SECONDARY:
        return -unknowns.secondary_torque / geometry.secondary.effective
    raise ValueError(f"Unsupported interface: {interface!r}")


if __name__ == "__main__":
    main()
