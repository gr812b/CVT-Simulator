"""Diagnose one bounded stick--stick closure root in the current 8x8 model.

This is a debugging tool, not production branch-selection logic. It solves the
current normal-resultant closure against both acceleration-level stick residuals
inside a deliberately wide signed-lambda box, then prints the force, torque,
wrap-tension, and affine-row ledgers behind the selected root.

Default use from the repository root::

    python tools/diagnose_stick_stick_closure.py

The default diagnostic domain is ``lambda_p, lambda_s in [-2, 2]``. Signed
negative lambdas are allowed only so the current algebraic system can be
examined broadly while its physical contact policy is still under development.
They are not a claim that negative utilizations are valid for ordinary forward
Baja drive.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import isfinite, sqrt, tan
from pathlib import Path
import sys
from typing import Iterable

import numpy as np

# Support either a normal src/cinder repository or a direct cinder overlay.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if (_candidate / "cinder").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from baja_trial_baseline import BajaTrialBaseline, build_baja_trial_baseline
from cinder.closure import ClosureUnknown
from cinder.contact import evaluate_contact_relative_motion
from cinder.dynamics import (
    CVTDynamicState,
    EngagedContactClosure,
    EngagedContactSolveSettings,
    FrictionUtilizationBounds,
    TrialFrictionUtilization,
)
from cinder.dynamics.equation_context import TrialEquationContext

_DEFAULT_LAMBDA_MIN = -2.0
_DEFAULT_LAMBDA_MAX = 2.0
_DEFAULT_INITIAL_LAMBDA = 0.0
_DEFAULT_RESTART_GRID = 3
_DEFAULT_MAX_NFEV = 300
_DEFAULT_ROOT_DEDUPLICATION_TOLERANCE = 1.0e-7
_DEFAULT_FINITE_DIFFERENCE_STEP = 1.0e-5

_UNKNOWN_LABELS = (
    ("alpha_p", "rad/s^2"),
    ("alpha_s", "rad/s^2"),
    ("v_b_dot", "m/s^2"),
    ("s_ddot", "m/s^2"),
    ("tau_p", "N m"),
    ("tau_s", "N m"),
    ("N_p", "N"),
    ("N_s", "N"),
)


@dataclass(frozen=True, slots=True)
class RootCandidate:
    """One successful bounded stick--stick solve from one initial seed."""

    initial_guess: TrialFrictionUtilization
    solve_result: object

    @property
    def lambda_primary(self) -> float:
        return self.solve_result.friction_utilization.primary_lambda

    @property
    def lambda_secondary(self) -> float:
        return self.solve_result.friction_utilization.secondary_lambda

    @property
    def residual_norm(self) -> float:
        return float(np.linalg.norm(self.solve_result.sticking_residuals))


@dataclass(frozen=True, slots=True)
class WrapEndpointDiagnostic:
    """Reconstructed endpoint tensions for one selected stick root."""

    primary_radial_offset: float
    secondary_radial_offset: float
    primary_tangential_offset: float
    secondary_tangential_offset: float
    primary_upper_tension: float
    primary_lower_tension: float
    secondary_lower_tension: float
    secondary_upper_tension: float
    straight_span_length: float
    upper_span_residual: float
    lower_span_residual: float
    tension_loop_residual: float


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Solve and audit one or more bounded stick--stick roots in the "
            "current 8x8 normal-resultant closure."
        )
    )
    parser.add_argument(
        "--scenario",
        choices=("quasi-static", "active-shift"),
        default="quasi-static",
        help="Frozen engaged baseline state to inspect.",
    )
    parser.add_argument(
        "--lambda-min",
        type=float,
        default=_DEFAULT_LAMBDA_MIN,
        help="Common lower bound for lambda_p and lambda_s.",
    )
    parser.add_argument(
        "--lambda-max",
        type=float,
        default=_DEFAULT_LAMBDA_MAX,
        help="Common upper bound for lambda_p and lambda_s.",
    )
    parser.add_argument(
        "--initial-lambda-p",
        type=float,
        default=_DEFAULT_INITIAL_LAMBDA,
        help="First primary-lambda seed. The default is the box centre.",
    )
    parser.add_argument(
        "--initial-lambda-s",
        type=float,
        default=_DEFAULT_INITIAL_LAMBDA,
        help="First secondary-lambda seed. The default is the box centre.",
    )
    parser.add_argument(
        "--restart-grid",
        type=int,
        default=_DEFAULT_RESTART_GRID,
        help=(
            "Number of interior seeds per lambda direction, in addition to "
            "the explicit initial seed. Use 1 to skip the interior grid."
        ),
    )
    parser.add_argument(
        "--max-nfev",
        type=int,
        default=_DEFAULT_MAX_NFEV,
        help="Maximum nonlinear residual evaluations per restart.",
    )
    parser.add_argument(
        "--finite-difference-step",
        type=float,
        default=_DEFAULT_FINITE_DIFFERENCE_STEP,
        help="Lambda step for local solved-state sensitivity estimates.",
    )
    args = parser.parse_args()

    for name, value in (
        ("--lambda-min", args.lambda_min),
        ("--lambda-max", args.lambda_max),
        ("--initial-lambda-p", args.initial_lambda_p),
        ("--initial-lambda-s", args.initial_lambda_s),
        ("--finite-difference-step", args.finite_difference_step),
    ):
        if not isfinite(value):
            parser.error(f"{name} must be finite.")

    if args.lambda_min >= args.lambda_max:
        parser.error("--lambda-min must be strictly below --lambda-max.")
    if not args.lambda_min <= args.initial_lambda_p <= args.lambda_max:
        parser.error("--initial-lambda-p must lie inside the lambda box.")
    if not args.lambda_min <= args.initial_lambda_s <= args.lambda_max:
        parser.error("--initial-lambda-s must lie inside the lambda box.")
    if args.restart_grid < 1:
        parser.error("--restart-grid must be at least 1.")
    if args.max_nfev < 1:
        parser.error("--max-nfev must be at least 1.")
    if args.finite_difference_step <= 0.0:
        parser.error("--finite-difference-step must be positive.")
    return args


def main() -> None:
    args = parse_arguments()
    baseline = build_baja_trial_baseline()
    state = _select_state(baseline=baseline, scenario=args.scenario)
    snapshot = baseline.model.snapshot(state=state)

    bounds = FrictionUtilizationBounds(
        primary_lower=args.lambda_min,
        primary_upper=args.lambda_max,
        secondary_lower=args.lambda_min,
        secondary_upper=args.lambda_max,
    )
    closure = EngagedContactClosure(snapshot=snapshot)
    seeds = _build_restart_seeds(
        lower=args.lambda_min,
        upper=args.lambda_max,
        first=TrialFrictionUtilization(
            primary_lambda=args.initial_lambda_p,
            secondary_lambda=args.initial_lambda_s,
        ),
        grid_size=args.restart_grid,
    )
    candidates = _solve_from_seeds(
        closure=closure,
        bounds=bounds,
        seeds=seeds,
        maximum_function_evaluations=args.max_nfev,
    )

    _print_header(
        scenario=args.scenario,
        state=state,
        snapshot=snapshot,
        bounds=bounds,
        seed_count=len(seeds),
    )
    _print_root_search_summary(candidates=candidates)

    if not candidates:
        print("\nNo accepted stick--stick root was found in the requested box.")
        raise SystemExit(2)

    selected = _select_best_root(candidates)
    _print_selected_root(selected=selected)
    _print_contact_kinematics(snapshot=snapshot, selected=selected)
    _print_closure_unknowns(selected=selected)
    _print_rotational_and_transport_ledgers(snapshot=snapshot, selected=selected)
    _print_axial_ledgers(snapshot=snapshot, selected=selected)
    _print_unused_belt_axial_diagnostic(snapshot=snapshot, selected=selected)
    _print_traction_and_wrap_diagnostics(
        snapshot=snapshot,
        selected=selected,
        center_distance=baseline.model.geometry.spec.center_distance,
    )
    _print_affine_row_breakdown(selected=selected)
    _print_local_sensitivity(
        closure=closure,
        bounds=bounds,
        selected=selected,
        requested_step=args.finite_difference_step,
    )
    _print_interpretation(snapshot=snapshot, selected=selected)


def _select_state(*, baseline: BajaTrialBaseline, scenario: str) -> CVTDynamicState:
    if scenario == "quasi-static":
        return baseline.quasi_static_state
    return baseline.active_shift_state


def _build_restart_seeds(
    *,
    lower: float,
    upper: float,
    first: TrialFrictionUtilization,
    grid_size: int,
) -> tuple[TrialFrictionUtilization, ...]:
    """Return unique bounded seeds, avoiding exactly singular-looking edges."""

    margin = 0.02 * (upper - lower)
    interior_lower = lower + margin
    interior_upper = upper - margin
    grid_values = (
        () if grid_size == 1 else np.linspace(interior_lower, interior_upper, grid_size)
    )

    seeds = [first]
    for lambda_secondary in grid_values:
        for lambda_primary in grid_values:
            seeds.append(
                TrialFrictionUtilization(
                    primary_lambda=float(lambda_primary),
                    secondary_lambda=float(lambda_secondary),
                )
            )

    unique: list[TrialFrictionUtilization] = []
    for seed in seeds:
        if any(
            abs(seed.primary_lambda - previous.primary_lambda) <= 1.0e-14
            and abs(seed.secondary_lambda - previous.secondary_lambda) <= 1.0e-14
            for previous in unique
        ):
            continue
        unique.append(seed)
    return tuple(unique)


def _solve_from_seeds(
    *,
    closure: EngagedContactClosure,
    bounds: FrictionUtilizationBounds,
    seeds: Iterable[TrialFrictionUtilization],
    maximum_function_evaluations: int,
) -> tuple[RootCandidate, ...]:
    """Solve from several starts and retain distinct accepted roots only."""

    distinct: list[RootCandidate] = []
    for seed in seeds:
        settings = EngagedContactSolveSettings(
            static_bounds=bounds,
            initial_guess=seed,
            maximum_function_evaluations=maximum_function_evaluations,
        )
        try:
            result = closure.solve_stick_stick(settings=settings)
        except (ArithmeticError, RuntimeError, ValueError):
            continue

        candidate = RootCandidate(initial_guess=seed, solve_result=result)
        if not result.accepted:
            continue
        if any(_same_root(candidate, previous) for previous in distinct):
            continue
        distinct.append(candidate)

    return tuple(
        sorted(
            distinct,
            key=lambda candidate: (
                candidate.residual_norm,
                candidate.solve_result.closure.condition_number,
            ),
        )
    )


def _same_root(left: RootCandidate, right: RootCandidate) -> bool:
    return (
        abs(left.lambda_primary - right.lambda_primary)
        <= _DEFAULT_ROOT_DEDUPLICATION_TOLERANCE
        and abs(left.lambda_secondary - right.lambda_secondary)
        <= _DEFAULT_ROOT_DEDUPLICATION_TOLERANCE
    )


def _select_best_root(candidates: tuple[RootCandidate, ...]) -> RootCandidate:
    return min(
        candidates,
        key=lambda candidate: (
            candidate.residual_norm,
            candidate.solve_result.closure.condition_number,
        ),
    )


def _print_header(*, scenario, state, snapshot, bounds, seed_count) -> None:
    geometry = snapshot.geometry
    print("\n" + "=" * 96)
    print("CINDER stick--stick closure diagnostic")
    print("=" * 96)
    print(f"Scenario: {scenario}")
    print(
        "Lambda diagnostic box: "
        f"lambda_p, lambda_s in [{bounds.primary_lower:.6g}, {bounds.primary_upper:.6g}]"
    )
    print(f"Restart seeds attempted: {seed_count}")
    print(
        "State: "
        f"omega_p={state.primary_angular_speed:.6f} rad/s, "
        f"omega_s={state.secondary_angular_speed:.6f} rad/s, "
        f"v_b={state.belt_speed:.6f} m/s, "
        f"s={state.shift_position * 1_000.0:.6f} mm, "
        f"s_dot={state.shift_speed * 1_000.0:.6f} mm/s"
    )
    print(
        "Geometry: "
        f"r_p,eff={geometry.primary.effective * 1_000.0:.6f} mm, "
        f"r_s,eff={geometry.secondary.effective * 1_000.0:.6f} mm, "
        f"phi_p={geometry.primary_wrap_angle:.6f} rad, "
        f"phi_s={geometry.secondary_wrap_angle:.6f} rad"
    )
    print(
        "Known loads: "
        f"tau_engine={snapshot.engine_torque:.6f} N m, "
        f"tau_secondary,external={snapshot.secondary_external_torque:.6f} N m"
    )
    print(
        "Masses: "
        f"m_p,movable={snapshot.axial_translation_inertias.primary.mass:.6f} kg, "
        f"m_s,movable={snapshot.axial_translation_inertias.secondary.mass:.6f} kg, "
        f"m_b={snapshot.belt_transport_mass:.6f} kg"
    )


def _print_root_search_summary(*, candidates: tuple[RootCandidate, ...]) -> None:
    print("\nDistinct accepted roots")
    print("-" * 96)
    if not candidates:
        print("None.")
        return
    print(
        f"{'#':>2}  {'seed (p,s)':>22}  {'lambda_p':>12}  {'lambda_s':>12}  "
        f"{'||R_stick|| [m/s^2]':>22}  {'cond(A)':>12}"
    )
    for index, candidate in enumerate(candidates, start=1):
        closure = candidate.solve_result.closure
        print(
            f"{index:2d}  "
            f"({candidate.initial_guess.primary_lambda: .4f}, "
            f"{candidate.initial_guess.secondary_lambda: .4f})  "
            f"{candidate.lambda_primary:12.9f}  "
            f"{candidate.lambda_secondary:12.9f}  "
            f"{candidate.residual_norm:22.6e}  "
            f"{closure.condition_number:12.6e}"
        )


def _print_selected_root(*, selected: RootCandidate) -> None:
    result = selected.solve_result
    print("\nSelected root")
    print("-" * 96)
    print(
        f"lambda_p={selected.lambda_primary:.12f}, "
        f"lambda_s={selected.lambda_secondary:.12f}"
    )
    print(
        f"optimizer: success={result.optimizer_success}, accepted={result.accepted}, "
        f"nfev={result.function_evaluations}, cost={result.optimizer_cost:.6e}"
    )
    print(f"optimizer message: {result.optimizer_message}")
    print(
        "stick residual Jacobian: "
        f"det={result.jacobian_determinant:.6e}, "
        f"cond={result.jacobian_condition_number:.6e}"
    )
    print("d(R_p, R_s)/d(lambda_p, lambda_s):")
    print(np.array2string(result.jacobian, precision=7, suppress_small=False))
    print(
        "closure matrix: "
        f"rank={result.closure.matrix_rank}, "
        f"cond(A)={result.closure.condition_number:.6e}, "
        f"max imposed-row residual={result.closure.max_abs_equation_residual:.6e}"
    )


def _print_contact_kinematics(*, snapshot, selected: RootCandidate) -> None:
    relative_motion = evaluate_contact_relative_motion(
        state=snapshot.state,
        geometry=snapshot.geometry,
        unknowns=selected.solve_result.closure.unknowns,
    )
    print("\nContact kinematics")
    print("-" * 96)
    print(
        f"primary:   v_rel={relative_motion.primary_relative_speed:.6e} m/s, "
        f"a_rel={relative_motion.primary_relative_acceleration:.6e} m/s^2"
    )
    print(
        f"secondary: v_rel={relative_motion.secondary_relative_speed:.6e} m/s, "
        f"a_rel={relative_motion.secondary_relative_acceleration:.6e} m/s^2"
    )


def _print_closure_unknowns(*, selected: RootCandidate) -> None:
    unknowns = selected.solve_result.closure.unknowns
    print("\nSolved closure unknowns")
    print("-" * 96)
    for (label, unit), value in zip(_UNKNOWN_LABELS, unknowns.as_tuple(), strict=True):
        print(f"{label:>10} = {value: .12e} {unit}")


def _print_rotational_and_transport_ledgers(
    *, snapshot, selected: RootCandidate
) -> None:
    unknowns = selected.solve_result.closure.unknowns
    state = snapshot.state
    geometry = snapshot.geometry
    movable_inertia = snapshot.movable_secondary_rotational_inertia
    helix = snapshot.secondary_helix

    print("\nRotational and belt-transport ledgers")
    print("-" * 96)

    primary_terms = (
        (
            "I_p alpha_p",
            snapshot.primary_rotational_inertia * unknowns.primary_angular_acceleration,
        ),
        ("+ tau_p", unknowns.primary_torque),
        ("- tau_engine", -snapshot.engine_torque),
    )
    _print_ledger(
        "primary rotation: I_p alpha_p + tau_p - tau_engine = 0", primary_terms
    )

    belt_terms = (
        ("m_b v_b_dot", snapshot.belt_transport_mass * unknowns.belt_acceleration),
        ("- tau_p / r_p", -unknowns.primary_torque / geometry.primary.effective),
        ("+ tau_s / r_s", unknowns.secondary_torque / geometry.secondary.effective),
    )
    _print_ledger("belt transport: m_b v_b_dot - tau_p/r_p + tau_s/r_s = 0", belt_terms)

    secondary_terms = (
        (
            "I_s,abs alpha_s",
            snapshot.secondary_absolute_rotational_inertia
            * unknowns.secondary_angular_acceleration,
        ),
        (
            "- I_M H s_ddot",
            -movable_inertia * helix.dtheta_ds * unknowns.shift_acceleration,
        ),
        ("- tau_s", -unknowns.secondary_torque),
        ("- tau_secondary,external", -snapshot.secondary_external_torque),
        (
            "- I_M H_prime s_dot^2",
            -movable_inertia * helix.d2theta_ds2 * state.shift_speed**2,
        ),
    )
    _print_ledger(
        "secondary rotation: I_s,abs alpha_s - I_M H s_ddot - tau_s - tau_ext - I_M H' s_dot^2 = 0",
        secondary_terms,
    )


def _print_axial_ledgers(*, snapshot, selected: RootCandidate) -> None:
    unknowns = selected.solve_result.closure.unknowns
    state = snapshot.state
    beta_tangent = tan(snapshot.sheave_half_angle)
    primary_inertia = snapshot.axial_translation_inertias.primary
    secondary_inertia = snapshot.axial_translation_inertias.secondary

    primary_x_ddot = (
        primary_inertia.d_coordinate_ds * unknowns.shift_acceleration
        + primary_inertia.d2_coordinate_ds2 * state.shift_speed**2
    )
    secondary_x_ddot = (
        secondary_inertia.d_coordinate_ds * unknowns.shift_acceleration
        + secondary_inertia.d2_coordinate_ds2 * state.shift_speed**2
    )
    primary_actuation_force = snapshot.primary_actuation.force(unknowns)
    secondary_actuation_force = snapshot.secondary_actuation.force(unknowns)
    primary_wedge_opening_force = unknowns.primary_normal_resultant / (
        2.0 * beta_tangent
    )
    secondary_wedge_opening_force = unknowns.secondary_normal_resultant / (
        2.0 * beta_tangent
    )

    print("\nAxial force ledgers")
    print("-" * 96)
    print("Primary local coordinate: x_p = s")
    print(
        f"  x_p_dot={primary_inertia.d_coordinate_ds * state.shift_speed:.6e} m/s, "
        f"x_p_ddot={primary_x_ddot:.6e} m/s^2"
    )
    _print_ledger(
        "primary axial: m_p x_p_ddot + N_p/(2 tan beta) - F_p = 0",
        (
            ("m_p x_p_ddot", primary_inertia.mass * primary_x_ddot),
            ("+ primary wedge opening", primary_wedge_opening_force),
            ("- primary actuator force", -primary_actuation_force),
        ),
    )
    print(
        "  rearranged: "
        f"F_p - N_p/(2 tan beta) = "
        f"{primary_actuation_force - primary_wedge_opening_force:.6e} N, "
        f"so x_p_ddot = {primary_x_ddot:.6e} m/s^2."
    )
    _print_affine_force_relation(
        title="primary actuator force F_p",
        relation=snapshot.primary_actuation.relation,
        unknowns=unknowns,
    )

    print("\nSecondary local coordinate: x_s = x_s(s)")
    print(
        f"  x_s'={secondary_inertia.d_coordinate_ds:.6e}, "
        f"x_s''={secondary_inertia.d2_coordinate_ds2:.6e} 1/m, "
        f"x_s_dot={secondary_inertia.d_coordinate_ds * state.shift_speed:.6e} m/s, "
        f"x_s_ddot={secondary_x_ddot:.6e} m/s^2"
    )
    _print_ledger(
        "secondary axial: m_s x_s_ddot + N_s/(2 tan beta) - F_s = 0",
        (
            ("m_s x_s_ddot", secondary_inertia.mass * secondary_x_ddot),
            ("+ secondary wedge opening", secondary_wedge_opening_force),
            ("- secondary actuator force", -secondary_actuation_force),
        ),
    )
    print(
        "  rearranged: "
        f"F_s - N_s/(2 tan beta) = "
        f"{secondary_actuation_force - secondary_wedge_opening_force:.6e} N, "
        f"so x_s_ddot = {secondary_x_ddot:.6e} m/s^2 and "
        f"s_ddot = {unknowns.shift_acceleration:.6e} m/s^2."
    )
    _print_affine_force_relation(
        title="secondary actuator force F_s",
        relation=snapshot.secondary_actuation.relation,
        unknowns=unknowns,
    )


def _print_unused_belt_axial_diagnostic(*, snapshot, selected: RootCandidate) -> None:
    """Show the present belt axial-mass relation without placing it in a row."""

    belt_inertia = snapshot.axial_translation_inertias.belt
    unknowns = selected.solve_result.closure.unknowns
    state = snapshot.state
    belt_x_ddot = (
        belt_inertia.d_coordinate_ds * unknowns.shift_acceleration
        + belt_inertia.d2_coordinate_ds2 * state.shift_speed**2
    )
    local_force = belt_inertia.mass * belt_x_ddot
    generalized_force = (
        belt_inertia.reflected_mass * unknowns.shift_acceleration
        + belt_inertia.generalized_curvature_coefficient * state.shift_speed**2
    )

    print(
        "\nRepresentative belt axial-mass diagnostic (not yet assigned to a physical row)"
    )
    print("-" * 96)
    print(
        f"x_b'={belt_inertia.d_coordinate_ds:.6e}, "
        f"x_b''={belt_inertia.d2_coordinate_ds2:.6e} 1/m, "
        f"x_b_ddot={belt_x_ddot:.6e} m/s^2"
    )
    print(
        f"m_b x_b_ddot={local_force:.6e} N; "
        f"generalized equivalent Q_b={generalized_force:.6e} N."
    )
    print(
        "This is printed only to show scale. It is deliberately not added to "
        "either pulley-local axial balance, so the same belt mass is not double-counted."
    )


def _print_traction_and_wrap_diagnostics(
    *, snapshot, selected: RootCandidate, center_distance: float
) -> None:
    unknowns = selected.solve_result.closure.unknowns
    lambda_primary = selected.lambda_primary
    lambda_secondary = selected.lambda_secondary
    primary_radius = snapshot.geometry.primary.effective
    secondary_radius = snapshot.geometry.secondary.effective

    print("\nTraction and reconstructed wrap-tension diagnostics")
    print("-" * 96)
    print(
        "primary traction: "
        f"tau_p/r_p={unknowns.primary_torque / primary_radius:.6e} N, "
        f"lambda_p N_p={lambda_primary * unknowns.primary_normal_resultant:.6e} N"
    )
    print(
        "secondary traction: "
        f"tau_s/r_s={unknowns.secondary_torque / secondary_radius:.6e} N, "
        f"lambda_s N_s={lambda_secondary * unknowns.secondary_normal_resultant:.6e} N"
    )

    wrap = _reconstruct_wrap_endpoints(
        snapshot=snapshot,
        selected=selected,
        center_distance=center_distance,
    )
    print(
        f"C_p={wrap.primary_radial_offset:.6e} N, "
        f"A_p={wrap.primary_tangential_offset:.6e} N/rad"
    )
    print(
        f"C_s={wrap.secondary_radial_offset:.6e} N, "
        f"A_s={wrap.secondary_tangential_offset:.6e} N/rad"
    )
    print(
        f"T_u,p={wrap.primary_upper_tension:.6e} N, "
        f"T_l,p={wrap.primary_lower_tension:.6e} N"
    )
    print(
        f"T_l,s={wrap.secondary_lower_tension:.6e} N, "
        f"T_u,s={wrap.secondary_upper_tension:.6e} N"
    )
    print(
        f"tension-loop residual T_u,p + T_l,p - T_u,s - T_l,s = "
        f"{wrap.tension_loop_residual:.6e} N"
    )
    print(
        "span checks against q D v_b_dot: "
        f"upper={wrap.upper_span_residual:.6e} N, "
        f"lower={wrap.lower_span_residual:.6e} N"
    )
    print(
        "The span checks are intentionally exposed: they should be near zero "
        "only when the global belt-transport row and the wrap maps use fully "
        "consistent mass/reference-line conventions."
    )


def _reconstruct_wrap_endpoints(
    *, snapshot, selected: RootCandidate, center_distance: float
) -> WrapEndpointDiagnostic:
    """Reconstruct endpoint tensions using the same regular maps as the row."""

    unknowns = selected.solve_result.closure.unknowns
    state = snapshot.state
    geometry = snapshot.geometry
    context = TrialEquationContext(
        snapshot=snapshot,
        friction_utilization=TrialFrictionUtilization(
            primary_lambda=selected.lambda_primary,
            secondary_lambda=selected.lambda_secondary,
        ),
    )
    contact = context.contact_terms
    q = snapshot.belt_linear_density

    def radial_offset(radius) -> float:
        radius_acceleration = (
            radius.d_effective_ds * unknowns.shift_acceleration
            + radius.d2_effective_ds2 * state.shift_speed**2
        )
        return q * (state.belt_speed**2 - radius.effective * radius_acceleration)

    def tangential_offset(radius) -> float:
        return q * (
            radius.effective * unknowns.belt_acceleration
            + radius.d_effective_ds * state.shift_speed * state.belt_speed
        )

    primary_c = radial_offset(geometry.primary)
    secondary_c = radial_offset(geometry.secondary)
    primary_a = tangential_offset(geometry.primary)
    secondary_a = tangential_offset(geometry.secondary)

    primary_phi = geometry.primary_wrap_angle
    secondary_phi = geometry.secondary_wrap_angle

    primary_upper = (
        primary_c
        + unknowns.primary_normal_resultant / (primary_phi * contact.primary_phi_minus)
        - primary_a
        * primary_phi
        * contact.primary_psi_minus
        / contact.primary_phi_minus
    )
    primary_lower = (
        primary_c
        + contact.primary_exp_neg * (primary_upper - primary_c)
        + primary_a * primary_phi * contact.primary_phi_minus
    )

    secondary_lower = (
        secondary_c
        + unknowns.secondary_normal_resultant
        / (secondary_phi * contact.secondary_phi_plus)
        - secondary_a
        * secondary_phi
        * contact.secondary_psi_plus
        / contact.secondary_phi_plus
    )
    secondary_upper = (
        secondary_c
        + contact.secondary_exp_pos * (secondary_lower - secondary_c)
        + secondary_a * secondary_phi * contact.secondary_phi_plus
    )

    straight_span_length = sqrt(
        center_distance**2 - (geometry.secondary.outer - geometry.primary.outer) ** 2
    )
    span_acceleration_force = q * straight_span_length * unknowns.belt_acceleration

    return WrapEndpointDiagnostic(
        primary_radial_offset=primary_c,
        secondary_radial_offset=secondary_c,
        primary_tangential_offset=primary_a,
        secondary_tangential_offset=secondary_a,
        primary_upper_tension=primary_upper,
        primary_lower_tension=primary_lower,
        secondary_lower_tension=secondary_lower,
        secondary_upper_tension=secondary_upper,
        straight_span_length=straight_span_length,
        upper_span_residual=(primary_upper - secondary_upper - span_acceleration_force),
        lower_span_residual=(secondary_lower - primary_lower - span_acceleration_force),
        tension_loop_residual=(
            primary_upper + primary_lower - secondary_lower - secondary_upper
        ),
    )


def _print_affine_force_relation(*, title: str, relation, unknowns) -> None:
    print(f"  {title} decomposition:")
    print(f"    known bias = {relation.bias: .6e} N")
    for (label, _unit), gain, value in zip(
        _UNKNOWN_LABELS,
        relation.gains.as_tuple(),
        unknowns.as_tuple(),
        strict=True,
    ):
        if gain == 0.0:
            continue
        print(f"    {gain: .6e} * {label} ({value: .6e}) = " f"{gain * value: .6e} N")
    print(f"    total = {relation.evaluate(unknowns): .6e} N")


def _print_affine_row_breakdown(*, selected: RootCandidate) -> None:
    result = selected.solve_result.closure
    unknowns = result.unknowns
    print("\nFull affine row breakdown")
    print("-" * 96)
    for equation in result.equations:
        residual = equation.residual
        print(f"{equation.name}:")
        print(f"  bias = {residual.bias: .6e}")
        for (label, _unit), gain, value in zip(
            _UNKNOWN_LABELS,
            residual.gains.as_tuple(),
            unknowns.as_tuple(),
            strict=True,
        ):
            if gain == 0.0:
                continue
            print(f"  {gain: .6e} * {label} ({value: .6e}) = " f"{gain * value: .6e}")
        print(f"  residual = {equation.evaluate(unknowns): .6e}\n")


def _print_local_sensitivity(
    *, closure, bounds, selected, requested_step: float
) -> None:
    """Report central finite-difference sensitivities of selected root outputs."""

    root = selected.solve_result.friction_utilization
    step_primary = _bounded_difference_step(
        value=root.primary_lambda,
        lower=bounds.primary_lower,
        upper=bounds.primary_upper,
        requested=requested_step,
    )
    step_secondary = _bounded_difference_step(
        value=root.secondary_lambda,
        lower=bounds.secondary_lower,
        upper=bounds.secondary_upper,
        requested=requested_step,
    )
    if step_primary is None or step_secondary is None:
        print(
            "\nLocal lambda sensitivity skipped: selected root is too close to a bound."
        )
        return

    plus_primary = closure.evaluate_trial(
        friction_utilization=TrialFrictionUtilization(
            primary_lambda=root.primary_lambda + step_primary,
            secondary_lambda=root.secondary_lambda,
        )
    )
    minus_primary = closure.evaluate_trial(
        friction_utilization=TrialFrictionUtilization(
            primary_lambda=root.primary_lambda - step_primary,
            secondary_lambda=root.secondary_lambda,
        )
    )
    plus_secondary = closure.evaluate_trial(
        friction_utilization=TrialFrictionUtilization(
            primary_lambda=root.primary_lambda,
            secondary_lambda=root.secondary_lambda + step_secondary,
        )
    )
    minus_secondary = closure.evaluate_trial(
        friction_utilization=TrialFrictionUtilization(
            primary_lambda=root.primary_lambda,
            secondary_lambda=root.secondary_lambda - step_secondary,
        )
    )

    derivative_primary = (
        np.asarray(plus_primary.closure.unknowns.as_tuple())
        - np.asarray(minus_primary.closure.unknowns.as_tuple())
    ) / (2.0 * step_primary)
    derivative_secondary = (
        np.asarray(plus_secondary.closure.unknowns.as_tuple())
        - np.asarray(minus_secondary.closure.unknowns.as_tuple())
    ) / (2.0 * step_secondary)

    print("\nLocal solved-state sensitivity near selected root")
    print("-" * 96)
    print(
        f"central steps: d_lambda_p={step_primary:.3e}, "
        f"d_lambda_s={step_secondary:.3e}"
    )
    print(f"{'quantity':>10}  {'d/d lambda_p':>18}  {'d/d lambda_s':>18}")
    for (label, _unit), primary_value, secondary_value in zip(
        _UNKNOWN_LABELS,
        derivative_primary,
        derivative_secondary,
        strict=True,
    ):
        print(f"{label:>10}  {primary_value:18.6e}  {secondary_value:18.6e}")
    print(
        "These are closure-output sensitivities at fixed state, not time-domain "
        "trajectory sensitivities. Large values flag a lambda-sensitive algebraic root."
    )


def _bounded_difference_step(
    *, value: float, lower: float, upper: float, requested: float
) -> float | None:
    available = min(value - lower, upper - value)
    if available <= 0.0:
        return None
    return min(requested, 0.25 * available)


def _print_interpretation(*, snapshot, selected: RootCandidate) -> None:
    unknowns = selected.solve_result.closure.unknowns
    beta_tangent = tan(snapshot.sheave_half_angle)
    primary_net = snapshot.primary_actuation.force(
        unknowns
    ) - unknowns.primary_normal_resultant / (2.0 * beta_tangent)
    secondary_net = snapshot.secondary_actuation.force(
        unknowns
    ) - unknowns.secondary_normal_resultant / (2.0 * beta_tangent)

    print("\nReading the shift acceleration")
    print("-" * 96)
    print(
        "In the present sign convention, negative s_ddot is immediate primary "
        "opening / backshift acceleration. The primary ledger gives a net "
        f"closing force F_p - wedge_p = {primary_net:.6e} N."
    )
    print(
        "Dividing that net force by the currently modeled primary movable mass "
        f"({snapshot.axial_translation_inertias.primary.mass:.6e} kg) produces "
        f"s_ddot = {unknowns.shift_acceleration:.6e} m/s^2."
    )
    print(
        "The secondary is consistent with the same global coordinate through "
        f"x_s'={snapshot.axial_translation_inertias.secondary.d_coordinate_ds:.6e}; "
        f"its local net closing force is {secondary_net:.6e} N."
    )
    print(
        "Therefore this diagnostic answers 'which current force balance is "
        "driving the large acceleration?' It does not yet certify that the "
        "wide signed-lambda root is physically admissible under the eventual "
        "traction law, nor that the presently unassigned belt axial mass has "
        "been modeled completely."
    )


def _print_ledger(title: str, terms: Iterable[tuple[str, float]]) -> None:
    print(f"{title}")
    total = 0.0
    for label, value in terms:
        total += value
        print(f"  {label:<34} {value: .9e}")
    print(f"  {'sum':<34} {total: .9e}")


if __name__ == "__main__":
    main()
