"""Audit kinetic-slip branch candidates for physical direction consistency.

Run from ``cvtModel/`` after placing this beside
``preview_engaged_contact_modes.py``::

    python tools/diagnose_slip_branch_physics.py
    python tools/diagnose_slip_branch_physics.py --strict

Why this exists
---------------
The generic engaged-contact solvers deliberately solve only the equations that
belong to their declared mode:

* stick--stick: both acceleration-level stick residuals;
* mixed slip: the one residual belonging to the sticking interface;
* both slip: no stick residual.

That is necessary, but it is not sufficient to declare a *kinetic* slip
candidate physically admissible.  A slipping interface must also:

1. retain a compressive contact force under the current signed-lambda
   convention; and
2. dissipate, rather than create, mechanical energy at its nonzero relative
   speed.

This tool does not alter CINDER's solver or choose a branch.  It computes
those independent sign checks around the exact branch candidates presently
returned by the repository, then enumerates the four signed kinetic-lambda
pairs for the both-slip diagnostic state.  The enumeration distinguishes a
true sign-convention error from a state/mode combination that has no
physically admissible solution under the current six-row closure.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from math import isfinite, tan
from pathlib import Path
import sys
from typing import Final, Iterable

import numpy as np

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (
    _REPOSITORY_ROOT / "src",
    _REPOSITORY_ROOT,
    Path(__file__).resolve().parent,
):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

# Reuse the exact transparent Baja diagnostic baseline already used by the
# four-mode preview.  Keeping one baseline avoids accidentally diagnosing a
# changed parameter set rather than the branch logic itself.
from preview_engaged_contact_modes import build_diagnostic_baseline

from cinder.contact import (
    ContactInterface,
    ContactKinematicTolerances,
    KineticSlipSpecification,
    SlipDirection,
)
from cinder.dynamics import (
    EngagedContactClosure,
    EngagedContactSolveSettings,
    FrictionUtilizationBounds,
    TrialFrictionUtilization,
)

DEFAULT_STATIC_UTILIZATION: Final[float] = 0.65
DEFAULT_KINETIC_UTILIZATION: Final[float] = 0.51
DEFAULT_MINIMUM_UTILIZATION: Final[float] = 0.01
DEFAULT_SLIP_SPEED_OFFSET: Final[float] = 0.20

# These thresholds are only for reporting sign violations.  They intentionally
# sit far below the representative forces and powers in this diagnostic.
FORCE_SIGN_TOLERANCE: Final[float] = 1.0e-9
POWER_SIGN_TOLERANCE: Final[float] = 1.0e-10


@dataclass(frozen=True, slots=True)
class InterfacePhysicsAudit:
    """Independent physical sign audit for one solved belt--pulley interface.

    Under the present signed-lambda row-1 construction, the axial contact
    contribution is

        F_ax,j = tau_j / (2 lambda_j r_j tan(beta)).

    It must be positive for an engaged, compressive V-groove contact.  The
    total friction-contact mechanical power supplied to the two bodies at the
    interface is

        P_p = tau_p (v_b/r_p - omega_p) = tau_p v_rel,p / r_p,
        P_s = tau_s (omega_s - v_b/r_s) = -tau_s v_rel,s / r_s.

    Kinetic friction is dissipative only when that total is non-positive.
    ``dissipation_power = -contact_power`` is therefore expected to be
    non-negative for a slipping interface.
    """

    interface: ContactInterface
    signed_lambda: float
    torque: float
    effective_radius: float
    relative_speed: float
    axial_contact_force_proxy: float
    contact_power: float
    dissipation_power: float

    @property
    def has_compressive_contact(self) -> bool:
        return self.axial_contact_force_proxy > FORCE_SIGN_TOLERANCE

    @property
    def is_dissipative(self) -> bool:
        return self.dissipation_power >= -POWER_SIGN_TOLERANCE


def main() -> int:
    args = _parse_arguments()
    baseline = build_diagnostic_baseline()
    settings = EngagedContactSolveSettings(
        static_bounds=FrictionUtilizationBounds.forward_drive(
            primary_static_limit=args.static_utilization,
            secondary_static_limit=args.static_utilization,
            minimum_utilization=args.minimum_utilization,
        ),
        initial_guess=TrialFrictionUtilization(
            primary_lambda=0.50,
            secondary_lambda=-0.36,
        ),
    )

    failures: list[str] = []

    print("\n" + "=" * 116)
    print("Kinetic-slip physical-admissibility audit")
    print(
        "The ordinary branch solvers check kinematics and declared stick residuals. "
        "This tool separately checks contact compression and frictional dissipation."
    )
    print("\nSign rules used here")
    print(
        "  contact axial-force proxy: F_ax,j = tau_j / (2 lambda_j r_j tan(beta)) > 0"
    )
    print("  primary kinetic dissipation: Q_p = -tau_p v_rel,p / r_p >= 0")
    print("  secondary kinetic dissipation: Q_s = +tau_s v_rel,s / r_s >= 0")
    print(
        "  These follow directly from the present tau conventions: tau_p is primary -> belt, "
        "tau_s is belt -> secondary."
    )

    failures.extend(
        _audit_primary_slip_secondary_stick(
            baseline=baseline,
            settings=settings,
            kinetic_utilization=args.kinetic_utilization,
            slip_speed_offset=args.slip_speed_offset,
        )
    )
    failures.extend(
        _audit_primary_stick_secondary_slip(
            baseline=baseline,
            settings=settings,
            kinetic_utilization=args.kinetic_utilization,
            slip_speed_offset=args.slip_speed_offset,
        )
    )
    failures.extend(
        _audit_both_slip_and_sign_enumeration(
            baseline=baseline,
            settings=settings,
            kinetic_utilization=args.kinetic_utilization,
            slip_speed_offset=args.slip_speed_offset,
        )
    )

    if args.scan_shift_speed:
        _scan_mixed_mode_shift_speed(
            baseline=baseline,
            settings=settings,
            kinetic_utilization=args.kinetic_utilization,
            slip_speed_offset=args.slip_speed_offset,
        )

    print("\n" + "=" * 116)
    print("Interpretation")
    if not failures:
        print(
            "  All audited slipping contacts are compressive and dissipative for this baseline."
        )
    else:
        print(f"  Found {len(failures)} physical-admissibility violation(s):")
        for failure in failures:
            print(f"    - {failure}")
        print(
            "\n  This does not by itself prove that KineticSlipSpecification has the wrong sign map. "
            "It proves that the current candidate is not admissible under the signed-lambda six-row model. "
            "The both-slip sign enumeration below tells us whether merely flipping a lambda sign repairs it."
        )
        print(
            "  A future regime selector must require these checks in addition to solver convergence and "
            "relative-velocity direction before accepting a kinetic branch."
        )

    if args.strict and failures:
        return 1
    return 0


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit compression and dissipation of CINDER kinetic-slip candidates."
    )
    parser.add_argument(
        "--kinetic-utilization", type=float, default=DEFAULT_KINETIC_UTILIZATION
    )
    parser.add_argument(
        "--static-utilization", type=float, default=DEFAULT_STATIC_UTILIZATION
    )
    parser.add_argument(
        "--minimum-utilization", type=float, default=DEFAULT_MINIMUM_UTILIZATION
    )
    parser.add_argument(
        "--slip-speed-offset", type=float, default=DEFAULT_SLIP_SPEED_OFFSET
    )
    parser.add_argument(
        "--scan-shift-speed",
        action="store_true",
        help="Also sweep imposed shift speed for both mixed modes to distinguish a sign issue from a state-dependent incompatibility.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero when any physical-admissibility check fails.",
    )
    args = parser.parse_args()
    for name in (
        "kinetic_utilization",
        "static_utilization",
        "minimum_utilization",
        "slip_speed_offset",
    ):
        value = getattr(args, name)
        if not isfinite(value) or value <= 0.0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive.")
    if args.minimum_utilization >= args.static_utilization:
        parser.error("--minimum-utilization must be smaller than --static-utilization.")
    return args


def _audit_primary_slip_secondary_stick(
    *, baseline, settings, kinetic_utilization: float, slip_speed_offset: float
) -> list[str]:
    print("\n" + "=" * 116)
    print("1. Primary slip / secondary stick")
    print("  Same state construction as preview_engaged_contact_modes.py.")

    base_state = replace(baseline.active_state, shift_speed=0.003)
    geometry = baseline.model.geometry.evaluate(base_state.shift_position)
    state = replace(
        base_state,
        primary_angular_speed=(base_state.belt_speed + slip_speed_offset)
        / geometry.primary.effective,
    )
    specification = KineticSlipSpecification(
        interface=ContactInterface.PRIMARY,
        direction=SlipDirection.PULLEY_LEADS_BELT,
        kinetic_utilization=kinetic_utilization,
    )
    closure = EngagedContactClosure(snapshot=baseline.model.snapshot(state=state))
    result = closure.solve_primary_slip_secondary_stick(
        primary_slip=specification,
        settings=settings,
    )
    return _print_and_collect_branch_audit(
        label="primary-slip / secondary-stick",
        snapshot=closure.snapshot,
        result=result,
        slipping_specifications=(specification,),
        tolerances=settings.contact_tolerances,
    )


def _audit_primary_stick_secondary_slip(
    *, baseline, settings, kinetic_utilization: float, slip_speed_offset: float
) -> list[str]:
    print("\n" + "=" * 116)
    print("2. Primary stick / secondary slip")
    print("  Same state construction as preview_engaged_contact_modes.py.")

    base_state = replace(baseline.active_state, shift_speed=-0.012)
    geometry = baseline.model.geometry.evaluate(base_state.shift_position)
    state = replace(
        base_state,
        secondary_angular_speed=(base_state.belt_speed - slip_speed_offset)
        / geometry.secondary.effective,
    )
    specification = KineticSlipSpecification(
        interface=ContactInterface.SECONDARY,
        direction=SlipDirection.BELT_LEADS_PULLEY,
        kinetic_utilization=kinetic_utilization,
    )
    closure = EngagedContactClosure(snapshot=baseline.model.snapshot(state=state))
    result = closure.solve_primary_stick_secondary_slip(
        secondary_slip=specification,
        settings=settings,
    )
    return _print_and_collect_branch_audit(
        label="primary-stick / secondary-slip",
        snapshot=closure.snapshot,
        result=result,
        slipping_specifications=(specification,),
        tolerances=settings.contact_tolerances,
    )


def _audit_both_slip_and_sign_enumeration(
    *, baseline, settings, kinetic_utilization: float, slip_speed_offset: float
) -> list[str]:
    print("\n" + "=" * 116)
    print("3. Both slip, plus all four signed-lambda combinations")

    base_state = baseline.quasi_static_state
    geometry = baseline.model.geometry.evaluate(base_state.shift_position)
    state = replace(
        base_state,
        primary_angular_speed=(base_state.belt_speed + slip_speed_offset)
        / geometry.primary.effective,
        secondary_angular_speed=(base_state.belt_speed - slip_speed_offset)
        / geometry.secondary.effective,
    )
    primary_specification = KineticSlipSpecification(
        interface=ContactInterface.PRIMARY,
        direction=SlipDirection.PULLEY_LEADS_BELT,
        kinetic_utilization=kinetic_utilization,
    )
    secondary_specification = KineticSlipSpecification(
        interface=ContactInterface.SECONDARY,
        direction=SlipDirection.BELT_LEADS_PULLEY,
        kinetic_utilization=kinetic_utilization,
    )
    closure = EngagedContactClosure(snapshot=baseline.model.snapshot(state=state))
    result = closure.evaluate_both_slip(
        primary_slip=primary_specification,
        secondary_slip=secondary_specification,
        contact_tolerances=settings.contact_tolerances,
    )
    failures = _print_and_collect_direct_trial_audit(
        label="both-slip requested mapping",
        snapshot=closure.snapshot,
        trial=result.trial,
        slipping_specifications=(primary_specification, secondary_specification),
        tolerances=settings.contact_tolerances,
    )

    print("\n  Signed kinetic-lambda enumeration for the exact same state")
    print(
        "  lambda_p lambda_s | tau_p [Nm] tau_s [Nm] | F_ax,p [N] F_ax,s [N] | "
        "Q_p [W] Q_s [W] | all physical"
    )
    print("  " + "-" * 111)
    physically_admissible_pairs = 0
    for lambda_primary in (kinetic_utilization, -kinetic_utilization):
        for lambda_secondary in (kinetic_utilization, -kinetic_utilization):
            trial = closure.evaluate_trial(
                friction_utilization=TrialFrictionUtilization(
                    primary_lambda=lambda_primary,
                    secondary_lambda=lambda_secondary,
                )
            )
            audits = _audit_interfaces(trial=trial, snapshot=closure.snapshot)
            primary, secondary = audits
            all_physical = (
                primary.has_compressive_contact
                and secondary.has_compressive_contact
                and primary.is_dissipative
                and secondary.is_dissipative
            )
            physically_admissible_pairs += int(all_physical)
            print(
                f"  {lambda_primary:+8.3f} {lambda_secondary:+8.3f} | "
                f"{primary.torque:+10.4f} {secondary.torque:+10.4f} | "
                f"{primary.axial_contact_force_proxy:+10.3f} {secondary.axial_contact_force_proxy:+10.3f} | "
                f"{primary.dissipation_power:+8.3f} {secondary.dissipation_power:+8.3f} | "
                f"{str(all_physical):^12s}"
            )

    if physically_admissible_pairs == 0:
        failures.append(
            "both-slip sign enumeration: no +/- kinetic-lambda pair is simultaneously compressive and dissipative at both contacts"
        )
        print(
            "\n  Result: flipping one or both lambda signs does not repair this state. "
            "That points beyond a simple KineticSlipSpecification sign-map typo."
        )
    else:
        print(
            f"\n  Result: {physically_admissible_pairs} signed pair(s) pass both physical checks."
        )
    return failures


def _scan_mixed_mode_shift_speed(
    *, baseline, settings, kinetic_utilization: float, slip_speed_offset: float
) -> None:
    """Continue both mixed branches through shift speed without changing slip speed.

    This is optional because it is a diagnostic continuation, not a future
    event policy.  It helps answer whether a failed branch is a universal sign
    error or only incompatible with a particular imposed shift state.
    """

    print("\n" + "=" * 116)
    print("4. Optional mixed-mode continuation versus imposed shift speed")
    print(
        "  Each row retains its established +/- relative slip speed and varies only s_dot. "
        "'physical' requires the solver root, positive contact compression at both interfaces, "
        "and positive kinetic dissipation at the declared slipping contact."
    )

    base_state = baseline.quasi_static_state
    geometry = baseline.model.geometry.evaluate(base_state.shift_position)
    speeds = np.linspace(-0.012, 0.012, 9)

    def print_header(name: str) -> None:
        print(f"\n  {name}")
        print(
            "  s_dot [mm/s] | solver | lambda_p lambda_s | tau_p tau_s [Nm] | "
            "F_ax,p F_ax,s [N] | Q_slip [W] | physical"
        )
        print("  " + "-" * 112)

    primary_specification = KineticSlipSpecification(
        interface=ContactInterface.PRIMARY,
        direction=SlipDirection.PULLEY_LEADS_BELT,
        kinetic_utilization=kinetic_utilization,
    )
    print_header("primary slip / secondary stick")
    for shift_speed in speeds:
        state = replace(
            base_state,
            shift_speed=float(shift_speed),
            primary_angular_speed=(base_state.belt_speed + slip_speed_offset)
            / geometry.primary.effective,
        )
        closure = EngagedContactClosure(snapshot=baseline.model.snapshot(state=state))
        result = closure.solve_primary_slip_secondary_stick(
            primary_slip=primary_specification,
            settings=settings,
        )
        primary, secondary = _audit_interfaces(
            trial=result.trial,
            snapshot=closure.snapshot,
        )
        physical = (
            result.accepted
            and primary.has_compressive_contact
            and secondary.has_compressive_contact
            and primary.is_dissipative
        )
        print(
            f"  {shift_speed * 1_000.0:+12.3f} | {str(result.accepted):^6s} | "
            f"{primary.signed_lambda:+8.4f} {secondary.signed_lambda:+8.4f} | "
            f"{primary.torque:+8.3f} {secondary.torque:+8.3f} | "
            f"{primary.axial_contact_force_proxy:+8.1f} {secondary.axial_contact_force_proxy:+8.1f} | "
            f"{primary.dissipation_power:+9.3f} | {str(physical):^8s}"
        )

    secondary_specification = KineticSlipSpecification(
        interface=ContactInterface.SECONDARY,
        direction=SlipDirection.BELT_LEADS_PULLEY,
        kinetic_utilization=kinetic_utilization,
    )
    print_header("primary stick / secondary slip")
    for shift_speed in speeds:
        state = replace(
            base_state,
            shift_speed=float(shift_speed),
            secondary_angular_speed=(base_state.belt_speed - slip_speed_offset)
            / geometry.secondary.effective,
        )
        closure = EngagedContactClosure(snapshot=baseline.model.snapshot(state=state))
        result = closure.solve_primary_stick_secondary_slip(
            secondary_slip=secondary_specification,
            settings=settings,
        )
        primary, secondary = _audit_interfaces(
            trial=result.trial,
            snapshot=closure.snapshot,
        )
        physical = (
            result.accepted
            and primary.has_compressive_contact
            and secondary.has_compressive_contact
            and secondary.is_dissipative
        )
        print(
            f"  {shift_speed * 1_000.0:+12.3f} | {str(result.accepted):^6s} | "
            f"{primary.signed_lambda:+8.4f} {secondary.signed_lambda:+8.4f} | "
            f"{primary.torque:+8.3f} {secondary.torque:+8.3f} | "
            f"{primary.axial_contact_force_proxy:+8.1f} {secondary.axial_contact_force_proxy:+8.1f} | "
            f"{secondary.dissipation_power:+9.3f} | {str(physical):^8s}"
        )


def _print_and_collect_branch_audit(
    *,
    label: str,
    snapshot,
    result,
    slipping_specifications: tuple[KineticSlipSpecification, ...],
    tolerances: ContactKinematicTolerances,
) -> list[str]:
    print(
        f"  solver accepted={result.accepted}; lambda_p={result.trial.friction_utilization.primary_lambda:+.8f}; "
        f"lambda_s={result.trial.friction_utilization.secondary_lambda:+.8f}; "
        f"||R_stick||={np.linalg.norm(result.sticking_residuals):.3e} m/s^2"
    )
    return _print_and_collect_direct_trial_audit(
        label=label,
        snapshot=snapshot,
        trial=result.trial,
        slipping_specifications=slipping_specifications,
        tolerances=tolerances,
    )


def _print_and_collect_direct_trial_audit(
    *,
    label: str,
    snapshot,
    trial,
    slipping_specifications: tuple[KineticSlipSpecification, ...],
    tolerances: ContactKinematicTolerances,
) -> list[str]:
    audits = _audit_interfaces(trial=trial, snapshot=snapshot)
    failures: list[str] = []
    slipping_by_interface = {spec.interface: spec for spec in slipping_specifications}

    print(
        "  interface | lambda | tau [Nm] | v_rel [m/s] | F_ax proxy [N] | Q_diss [W] | checks"
    )
    print("  " + "-" * 105)
    for audit in audits:
        specification = slipping_by_interface.get(audit.interface)
        kinematic_ok = (
            specification.direction_is_consistent(
                trial.relative_motion,
                tolerances=tolerances,
            )
            if specification is not None
            else True
        )
        dissipative_ok = audit.is_dissipative if specification is not None else True
        compression_ok = audit.has_compressive_contact
        check_text = (
            f"speed={'ok' if kinematic_ok else 'FAIL'}, "
            f"compression={'ok' if compression_ok else 'FAIL'}, "
            f"dissipation={'ok' if dissipative_ok else 'FAIL'}"
        )
        print(
            f"  {audit.interface.value:9s} | {audit.signed_lambda:+6.3f} | "
            f"{audit.torque:+9.4f} | {audit.relative_speed:+12.6f} | "
            f"{audit.axial_contact_force_proxy:+13.4f} | {audit.dissipation_power:+9.4f} | {check_text}"
        )

        # Compression is required at both engaged interfaces.  Dissipation is
        # checked only where the mode explicitly declares kinetic slip.
        if not compression_ok:
            failures.append(
                f"{label}: {audit.interface.value} contact has negative axial-force proxy "
                f"({audit.axial_contact_force_proxy:+.3f} N)"
            )
        if specification is not None and not kinematic_ok:
            failures.append(
                f"{label}: {audit.interface.value} solved relative speed conflicts with requested slip direction"
            )
        if specification is not None and not dissipative_ok:
            failures.append(
                f"{label}: {audit.interface.value} kinetic contact creates energy "
                f"(Q={audit.dissipation_power:+.3f} W)"
            )
    return failures


def _audit_interfaces(
    *, trial, snapshot
) -> tuple[InterfacePhysicsAudit, InterfacePhysicsAudit]:
    """Evaluate the two contact power and compression identities once."""

    geometry = snapshot.geometry
    beta_tangent = tan(snapshot.sheave_half_angle)
    if beta_tangent <= 0.0:
        raise ValueError("sheave_half_angle must have a positive tangent.")

    unknowns = trial.six_by_six.unknowns
    relative_motion = trial.relative_motion
    utilization = trial.friction_utilization

    primary = InterfacePhysicsAudit(
        interface=ContactInterface.PRIMARY,
        signed_lambda=utilization.primary_lambda,
        torque=unknowns.primary_torque,
        effective_radius=geometry.primary.effective,
        relative_speed=relative_motion.primary_relative_speed,
        axial_contact_force_proxy=(
            unknowns.primary_torque
            / (
                2.0
                * utilization.primary_lambda
                * geometry.primary.effective
                * beta_tangent
            )
        ),
        contact_power=(
            unknowns.primary_torque
            * relative_motion.primary_relative_speed
            / geometry.primary.effective
        ),
        dissipation_power=(
            -unknowns.primary_torque
            * relative_motion.primary_relative_speed
            / geometry.primary.effective
        ),
    )
    secondary = InterfacePhysicsAudit(
        interface=ContactInterface.SECONDARY,
        signed_lambda=utilization.secondary_lambda,
        torque=unknowns.secondary_torque,
        effective_radius=geometry.secondary.effective,
        relative_speed=relative_motion.secondary_relative_speed,
        axial_contact_force_proxy=(
            unknowns.secondary_torque
            / (
                2.0
                * utilization.secondary_lambda
                * geometry.secondary.effective
                * beta_tangent
            )
        ),
        contact_power=(
            -unknowns.secondary_torque
            * relative_motion.secondary_relative_speed
            / geometry.secondary.effective
        ),
        dissipation_power=(
            unknowns.secondary_torque
            * relative_motion.secondary_relative_speed
            / geometry.secondary.effective
        ),
    )
    return primary, secondary


if __name__ == "__main__":
    raise SystemExit(main())
