"""Exercise CINDER's four engaged contact closures with one self-contained baseline.

Run from ``cvtModel/``::

    python tools/preview_engaged_contact_modes.py
    python tools/preview_engaged_contact_modes.py --mode stick-stick
    python tools/preview_engaged_contact_modes.py --mode primary-slip-secondary-stick
    python tools/preview_engaged_contact_modes.py --mode both-slip --show-matrix
    python tools/preview_engaged_contact_modes.py --strict

This is a diagnostic tool, not a regime selector.  It deliberately constructs
states with a small established relative belt/pulley speed for the slip cases,
so the requested kinetic-slip direction can be checked directly.  The
production selector will later decide *which* mode is active from history,
traction bounds, relative speed, and event hysteresis.

The baseline keeps the legacy / project / placeholder annotations near the
constants so this one file can remain useful after older exploratory tools are
removed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from math import isfinite, radians
from pathlib import Path
import sys
from typing import Callable, Final, Iterable

import numpy as np

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPOSITORY_ROOT / "src", _REPOSITORY_ROOT):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from cinder.actuation import (
    CentrifugalPrimarySpec,
    TorqueReactiveSecondarySpec,
    build_centrifugal_primary,
    build_torque_reactive_secondary,
)
from cinder.actuation.forces import (
    AxialSpringForceSpec,
    CentrifugalRampForceSpec,
    SecondaryHelixForceSpec,
)
from cinder.contact import (
    ContactInterface,
    KineticSlipSpecification,
    SlipDirection,
)
from cinder.dynamics import (
    CVTDynamicState,
    CVTDynamicsModel,
    EngagedContactClosure,
    EngagedContactSolveSettings,
    FrictionUtilizationBounds,
    TrialFrictionUtilization,
)
from cinder.engine import EngineTorquePoint, FullThrottleTorqueCurve, TorqueCurveSpec
from cinder.geometry import BeltPulleyGeometry, BeltPulleyGeometrySpec, BeltSectionSpec
from cinder.inertia import (
    BeltMass,
    DrivetrainInertias,
    PrimaryInertia,
    SecondaryInertia,
    VehicleInertia,
    resolve_inertias,
)
from cinder.profiles import HelixProfile, LinearSegment, PiecewiseRamp, linear_helix_segment
from cinder.vehicle import (
    ConstantGradeRoadProfile,
    FixedFinalDrive,
    RoadLoadModel,
    VehicleRoadLoadSpec,
)


INCH_TO_METRE: Final[float] = 0.0254
FOOT_POUND_TO_NEWTON_METRE: Final[float] = 1.3558179483
RPM_TO_RAD_PER_SECOND: Final[float] = 2.0 * np.pi / 60.0

DEFAULT_STATIC_UTILIZATION: Final[float] = 0.65
DEFAULT_KINETIC_UTILIZATION: Final[float] = 0.51
DEFAULT_MINIMUM_UTILIZATION: Final[float] = 0.01
DEFAULT_SLIP_SPEED_OFFSET: Final[float] = 0.20
DEFAULT_MATRIX_RESIDUAL_TOLERANCE: Final[float] = 1.0e-8
DEFAULT_ROOT_AGREEMENT_TOLERANCE: Final[float] = 1.0e-8


@dataclass(frozen=True, slots=True)
class BajaDiagnosticConstants:
    """One transparent Baja-ish parameter set for closure diagnostics."""

    # Geometry and belt -----------------------------------------------------
    belt_height: float = 0.613 * INCH_TO_METRE  # legacy belt dimension
    belt_outer_width: float = 0.840 * INCH_TO_METRE  # legacy belt dimension
    belt_inner_width: float = 0.662 * INCH_TO_METRE  # legacy belt dimension
    belt_outer_length: float = 37.53 * INCH_TO_METRE  # legacy belt length
    belt_cord_depth_from_outer: float = 0.5 * 0.613 * INCH_TO_METRE
    # placeholder: prior defaults did not specify the cord-depth location.

    sheave_half_angle_degrees: float = 11.5  # legacy 23 degree included angle
    primary_effective_radius_at_low: float = (1.625 / 2.0) * INCH_TO_METRE
    secondary_effective_radius_at_low: float = 4.0 * INCH_TO_METRE
    # legacy geometry values interpreted as effective cord radii.

    deadzone_shift: float = (0.088 + 0.010) * INCH_TO_METRE  # legacy value
    max_shift: float = 0.75 * INCH_TO_METRE  # legacy value

    primary_ramp_angle_degrees: float = 30.0  # requested constant diagnostic ramp
    helix_angle_degrees: float = 26.0  # requested constant diagnostic helix
    initial_flyweight_radius: float = 0.04878  # legacy value
    helix_radius: float = 0.04445  # legacy value

    # Actuation -------------------------------------------------------------
    flyweight_mass: float = 0.5  # legacy equivalent flyweight mass, kg
    primary_spring_rate: float = 12_784.0  # legacy N/m
    primary_spring_initial_compression: float = 0.1
    # legacy default retained; verify preload semantics against hardware.

    secondary_torsional_spring_rate: float = 3.476  # legacy N m/rad
    secondary_torsional_initial_twist: float = radians(200.0)  # legacy 200 deg
    secondary_compression_spring_rate: float = 3_532.0  # legacy N/m
    secondary_spring_initial_compression: float = 0.1
    # legacy default retained; verify preload semantics against hardware.

    # Inertia ---------------------------------------------------------------
    engine_rotational_inertia: float = 0.1  # legacy kg m^2
    primary_cvt_rotational_inertia: float = 0.005
    # placeholder: prior model did not split primary pulley spin inertia.
    primary_moving_sheave_mass: float = 1.0681  # project/CAD estimate, kg

    secondary_fixed_rotational_inertia: float = 0.1  # legacy kg m^2
    gearbox_input_rotational_inertia: float = 0.05  # legacy kg m^2
    secondary_movable_sheave_rotational_inertia: float = 0.0025139
    # project/CAD estimate, kg m^2; confirm with final CAD mass properties.
    secondary_moving_sheave_mass: float = 0.705141  # project/CAD estimate, kg

    rubber_density: float = 1100.0  # legacy material density, kg/m^3
    vehicle_mass: float = 225.0 + 75.0  # legacy vehicle + driver masses, kg
    driven_wheel_rotational_inertia: float = 0.2
    # legacy value was labelled all wheels; temporarily treated as driven total.

    # Vehicle / road --------------------------------------------------------
    final_drive_ratio: float = 7.556  # legacy gearbox ratio
    wheel_radius: float = 11.0 * INCH_TO_METRE  # legacy 22 inch tire diameter
    frontal_area: float = 1.11484  # legacy m^2
    drag_coefficient: float = 0.6  # legacy
    rolling_resistance_coefficient: float = 0.015  # legacy

    # Representative state --------------------------------------------------
    active_secondary_speed: float = 180.0  # rad/s
    deadzone_secondary_speed: float = 60.0  # rad/s
    active_shift_speed: float = 0.012  # m/s, deliberate nonzero diagnostic case
    deadzone_shift_speed: float = 0.006  # m/s, deliberate nonzero diagnostic case
    secondary_shaft_angle: float = 250.0  # rad, arbitrary road-profile position


@dataclass(frozen=True, slots=True)
class DiagnosticBaseline:
    constants: BajaDiagnosticConstants
    model: CVTDynamicsModel
    active_state: CVTDynamicState
    quasi_static_state: CVTDynamicState
    deadzone_state: CVTDynamicState


def build_diagnostic_baseline(
    constants: BajaDiagnosticConstants | None = None,
) -> DiagnosticBaseline:
    """Build one self-contained model and velocity-compatible base states."""

    c = constants or BajaDiagnosticConstants()

    belt = BeltSectionSpec(
        height=c.belt_height,
        outer_width=c.belt_outer_width,
        inner_width=c.belt_inner_width,
        cord_depth_from_outer=c.belt_cord_depth_from_outer,
    )
    geometry_spec = BeltPulleyGeometrySpec(
        belt=belt,
        belt_outer_length=c.belt_outer_length,
        primary_outer_radius_at_zero_shift=(
            c.primary_effective_radius_at_low + c.belt_cord_depth_from_outer
        ),
        secondary_outer_radius_at_zero_shift=(
            c.secondary_effective_radius_at_low + c.belt_cord_depth_from_outer
        ),
        sheave_half_angle=radians(c.sheave_half_angle_degrees),
        deadzone_shift=c.deadzone_shift,
        max_shift=c.max_shift,
    )
    geometry = BeltPulleyGeometry(geometry_spec)

    primary_ramp = PiecewiseRamp(
        (LinearSegment(length=c.max_shift, angle_degrees=c.primary_ramp_angle_degrees),)
    )
    primary_actuator = build_centrifugal_primary(
        CentrifugalPrimarySpec(
            centrifugal_ramp=CentrifugalRampForceSpec(
                flyweight_mass=c.flyweight_mass,
                radius_at_zero_position=c.initial_flyweight_radius,
                radial_displacement_profile=primary_ramp,
            ),
            axial_spring=AxialSpringForceSpec(
                stiffness=c.primary_spring_rate,
                initial_compression=c.primary_spring_initial_compression,
                compression_per_axial_position=1.0,
            ),
        )
    )

    terminal_geometry = geometry.evaluate(c.max_shift)
    secondary_opening_travel = -terminal_geometry.secondary_axial_coordinate.value
    if secondary_opening_travel <= 0.0:
        raise RuntimeError("Baseline geometry did not produce positive secondary opening.")

    helix_profile = HelixProfile(
        circumferential_profile=PiecewiseRamp(
            (
                linear_helix_segment(
                    length=secondary_opening_travel,
                    helix_angle_degrees=c.helix_angle_degrees,
                ),
            )
        ),
        radius=c.helix_radius,
    )
    secondary_actuator = build_torque_reactive_secondary(
        spec=TorqueReactiveSecondarySpec(
            axial_spring=AxialSpringForceSpec(
                stiffness=c.secondary_compression_spring_rate,
                initial_compression=c.secondary_spring_initial_compression,
                compression_per_axial_position=-1.0,
            ),
            helix_force=SecondaryHelixForceSpec(
                torsional_stiffness=c.secondary_torsional_spring_rate,
                initial_twist=c.secondary_torsional_initial_twist,
                movable_sheave_rotational_inertia=(
                    c.secondary_movable_sheave_rotational_inertia
                ),
                movable_sheave_torque_fraction=0.5,
            ),
        )
    )

    final_drive = FixedFinalDrive(
        reduction_ratio=c.final_drive_ratio,
        wheel_radius=c.wheel_radius,
    )
    vehicle = VehicleInertia(
        mass=c.vehicle_mass,
        wheel_rotational_inertia=c.driven_wheel_rotational_inertia,
    )
    inertias = resolve_inertias(
        drivetrain=DrivetrainInertias(
            primary=PrimaryInertia(
                engine_rotational_inertia=c.engine_rotational_inertia,
                cvt_rotational_inertia=c.primary_cvt_rotational_inertia,
                moving_sheave_mass=c.primary_moving_sheave_mass,
            ),
            secondary=SecondaryInertia(
                fixed_rotational_inertia=c.secondary_fixed_rotational_inertia,
                gearbox_input_rotational_inertia=c.gearbox_input_rotational_inertia,
                movable_sheave_rotational_inertia=(
                    c.secondary_movable_sheave_rotational_inertia
                ),
                moving_sheave_mass=c.secondary_moving_sheave_mass,
            ),
            belt=BeltMass(density=c.rubber_density),
        ),
        vehicle=vehicle,
        final_drive=final_drive,
        belt_section=belt,
        belt_outer_length=c.belt_outer_length,
    )

    engine = FullThrottleTorqueCurve(
        TorqueCurveSpec(
            points=tuple(
                EngineTorquePoint(
                    angular_speed=rpm * RPM_TO_RAD_PER_SECOND,
                    torque=foot_pounds * FOOT_POUND_TO_NEWTON_METRE,
                )
                for rpm, foot_pounds in (
                    (1000.0, 0.0),
                    (1800.0, 18.0),
                    (2400.0, 18.5),
                    (2600.0, 18.1),
                    (2800.0, 17.4),
                    (3000.0, 16.6),
                    (3200.0, 15.4),
                    (3400.0, 14.5),
                    (3600.0, 13.5),
                    (4000.0, 0.0),
                )
            ),
            low_speed_braking_torque=-5.0,
            low_speed_braking_peak_speed=500.0 * RPM_TO_RAD_PER_SECOND,
            high_speed_braking_torque=-5.0,
            high_speed_braking_transition_width=500.0 * RPM_TO_RAD_PER_SECOND,
            # placeholder tails: old model bounded net torque at -5 N m.
        )
    )

    road_load = RoadLoadModel(
        spec=VehicleRoadLoadSpec(
            rolling_resistance_coefficient=c.rolling_resistance_coefficient,
            drag_coefficient=c.drag_coefficient,
            frontal_area=c.frontal_area,
        ),
        vehicle=vehicle,
        final_drive=final_drive,
    )
    model = CVTDynamicsModel(
        geometry=geometry,
        primary_actuator=primary_actuator,
        secondary_actuator=secondary_actuator,
        secondary_helix_profile=helix_profile,
        inertias=inertias,
        engine=engine,
        road_load=road_load,
        road_profile=ConstantGradeRoadProfile(),
    )

    active_shift_position = c.deadzone_shift + 0.60 * (
        c.max_shift - c.deadzone_shift
    )
    deadzone_shift_position = 0.50 * c.deadzone_shift

    active_state = _make_velocity_compatible_state(
        geometry=geometry,
        shift_position=active_shift_position,
        secondary_speed=c.active_secondary_speed,
        shift_speed=c.active_shift_speed,
        secondary_shaft_angle=c.secondary_shaft_angle,
    )
    return DiagnosticBaseline(
        constants=c,
        model=model,
        active_state=active_state,
        quasi_static_state=replace(active_state, shift_speed=0.0),
        deadzone_state=_make_velocity_compatible_state(
            geometry=geometry,
            shift_position=deadzone_shift_position,
            secondary_speed=c.deadzone_secondary_speed,
            shift_speed=c.deadzone_shift_speed,
            secondary_shaft_angle=c.secondary_shaft_angle,
        ),
    )


def _make_velocity_compatible_state(
    *,
    geometry: BeltPulleyGeometry,
    shift_position: float,
    secondary_speed: float,
    shift_speed: float,
    secondary_shaft_angle: float,
) -> CVTDynamicState:
    """Build a state with both interfaces velocity-compatible initially."""

    position = geometry.evaluate(shift_position)
    primary_speed = (
        secondary_speed * position.secondary.effective / position.primary.effective
    )
    belt_speed = primary_speed * position.primary.effective
    return CVTDynamicState(
        primary_angular_speed=primary_speed,
        secondary_angular_speed=secondary_speed,
        belt_speed=belt_speed,
        shift_position=shift_position,
        shift_speed=shift_speed,
        secondary_shaft_angle=secondary_shaft_angle,
    )


@dataclass(slots=True)
class CheckBook:
    """Collect baseline-specific expectations without hiding the raw diagnostics."""

    checks: list[tuple[str, bool, str]]

    def expect(self, name: str, condition: bool, detail: str) -> None:
        self.checks.append((name, bool(condition), detail))

    @property
    def passed(self) -> bool:
        return all(passed for _, passed, _ in self.checks)

    def print_summary(self) -> None:
        print("\n" + "=" * 112)
        print("Baseline checks")
        for name, passed, detail in self.checks:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {name}: {detail}")
        print(f"  Overall: {'PASS' if self.passed else 'FAIL'} ({len(self.checks)} checks)")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exercise CINDER stick and kinetic-slip engaged closures."
    )
    parser.add_argument(
        "--mode",
        choices=(
            "all",
            "stick-stick",
            "primary-slip-secondary-stick",
            "primary-stick-secondary-slip",
            "both-slip",
            "deadzone",
        ),
        default="all",
        help="Run one diagnostic section or all baseline checks.",
    )
    parser.add_argument(
        "--kinetic-utilization",
        type=float,
        default=DEFAULT_KINETIC_UTILIZATION,
        help="Positive kinetic-utilization magnitude used by slip specifications.",
    )
    parser.add_argument(
        "--static-utilization",
        type=float,
        default=DEFAULT_STATIC_UTILIZATION,
        help="Positive static-utilization upper limit for the sticking lambda(s).",
    )
    parser.add_argument(
        "--minimum-utilization",
        type=float,
        default=DEFAULT_MINIMUM_UTILIZATION,
        help="Positive lower lambda bound until lambda-to-zero limiting forms exist.",
    )
    parser.add_argument(
        "--slip-speed-offset",
        type=float,
        default=DEFAULT_SLIP_SPEED_OFFSET,
        help="Established signed belt/surface speed separation for slip tests [m/s].",
    )
    parser.add_argument(
        "--show-matrix",
        action="store_true",
        help="Print the six-by-six A matrix and right-hand side for every solved branch.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a nonzero exit code if a baseline expectation fails.",
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


def main() -> int:
    args = parse_arguments()
    baseline = build_diagnostic_baseline()
    checks = CheckBook(checks=[])

    settings = _build_settings(args)
    if args.mode in ("all", "stick-stick"):
        _run_stick_stick_reference(
            baseline=baseline,
            settings=settings,
            checks=checks,
            show_matrix=args.show_matrix,
        )
    if args.mode in ("all", "primary-slip-secondary-stick"):
        _run_primary_slip_secondary_stick(
            baseline=baseline,
            settings=settings,
            kinetic_utilization=args.kinetic_utilization,
            slip_speed_offset=args.slip_speed_offset,
            checks=checks,
            show_matrix=args.show_matrix,
        )
    if args.mode in ("all", "primary-stick-secondary-slip"):
        _run_primary_stick_secondary_slip(
            baseline=baseline,
            settings=settings,
            kinetic_utilization=args.kinetic_utilization,
            slip_speed_offset=args.slip_speed_offset,
            checks=checks,
            show_matrix=args.show_matrix,
        )
    if args.mode in ("all", "both-slip"):
        _run_both_slip(
            baseline=baseline,
            settings=settings,
            kinetic_utilization=args.kinetic_utilization,
            slip_speed_offset=args.slip_speed_offset,
            checks=checks,
            show_matrix=args.show_matrix,
        )
    if args.mode in ("all", "deadzone"):
        _run_deadzone_geometry_check(baseline=baseline, checks=checks)

    checks.print_summary()
    if args.strict and not checks.passed:
        return 1
    return 0


def _build_settings(args: argparse.Namespace) -> EngagedContactSolveSettings:
    return EngagedContactSolveSettings(
        static_bounds=FrictionUtilizationBounds.forward_drive(
            primary_static_limit=args.static_utilization,
            secondary_static_limit=args.static_utilization,
            minimum_utilization=args.minimum_utilization,
        ),
        initial_guess=TrialFrictionUtilization(
            primary_lambda=0.50,
            secondary_lambda=0.36,
        ),
    )


def _run_stick_stick_reference(
    *,
    baseline: DiagnosticBaseline,
    settings: EngagedContactSolveSettings,
    checks: CheckBook,
    show_matrix: bool,
) -> None:
    print("\n" + "=" * 112)
    print("1. Engaged stick--stick: multi-seed quasi-static root")
    print(
        "The same snapshot is used for each solve.  All seeds should converge "
        "to one interior positive static-utilization pair."
    )

    seeds = (
        (0.48, 0.35),
        (0.498, 0.362),
        (0.52, 0.38),
        (0.54, 0.39),
        (0.56, 0.40),
    )
    snapshot = baseline.model.snapshot(state=baseline.quasi_static_state)
    closure = EngagedContactClosure(snapshot=snapshot)
    roots: list[np.ndarray] = []

    print(
        "  seed_p   seed_s | accepted | lambda_p lambda_s | ||R_stick|| [m/s^2] | "
        "tau_p [N m] tau_s [N m] | cond(A) cond(J)"
    )
    print("  " + "-" * 108)

    for seed_primary, seed_secondary in seeds:
        seeded_settings = replace(
            settings,
            initial_guess=TrialFrictionUtilization(
                primary_lambda=seed_primary,
                secondary_lambda=seed_secondary,
            ),
        )
        result = closure.solve_stick_stick(settings=seeded_settings)
        trial = result.trial
        residual_norm = float(np.linalg.norm(result.sticking_residuals))
        unknowns = trial.six_by_six.unknowns
        utilization = trial.friction_utilization
        print(
            f"  {seed_primary:7.4f} {seed_secondary:7.4f} | "
            f"{str(result.accepted):^8s} | "
            f"{utilization.primary_lambda:8.5f} {utilization.secondary_lambda:8.5f} | "
            f"{residual_norm:19.6e} | "
            f"{unknowns.primary_torque:11.6f} {unknowns.secondary_torque:11.6f} | "
            f"{trial.six_by_six.condition_number:7.3e} {result.jacobian_condition_number:7.3e}"
        )
        _record_common_trial_checks(
            checks=checks,
            label=f"stick--stick seed ({seed_primary:.3f}, {seed_secondary:.3f})",
            trial=trial,
        )
        checks.expect(
            f"stick--stick accepted from seed ({seed_primary:.3f}, {seed_secondary:.3f})",
            result.accepted,
            f"||R||={residual_norm:.3e} m/s^2",
        )
        roots.append(
            np.array(
                (utilization.primary_lambda, utilization.secondary_lambda), dtype=float
            )
        )

        if show_matrix and seed_primary == seeds[0][0]:
            _print_matrix(trial=trial)

    mean_root = np.mean(np.vstack(roots), axis=0)
    max_separation = max(float(np.linalg.norm(root - mean_root)) for root in roots)
    reference = closure.solve_stick_stick(settings=settings)
    unknowns = reference.trial.six_by_six.unknowns
    geometry = snapshot.geometry
    tangential_force_primary = unknowns.primary_torque / geometry.primary.effective
    tangential_force_secondary = unknowns.secondary_torque / geometry.secondary.effective
    torque_balance_error = abs(tangential_force_primary - tangential_force_secondary)

    print("\n  Root agreement and physical checks")
    print(
        f"  mean root: lambda_p={mean_root[0]:.10f}, lambda_s={mean_root[1]:.10f}; "
        f"maximum seed separation={max_separation:.3e}"
    )
    print(
        "  equal belt traction at zero shift speed: "
        f"tau_p/r_p={tangential_force_primary:.6f} N, "
        f"tau_s/r_s={tangential_force_secondary:.6f} N, "
        f"difference={torque_balance_error:.3e} N"
    )
    print(
        f"  transmitted primary torque / engine torque: "
        f"{unknowns.primary_torque:.6f} / {snapshot.engine_torque:.6f} N m"
    )

    checks.expect(
        "stick--stick multi-seed root agreement",
        max_separation <= DEFAULT_ROOT_AGREEMENT_TOLERANCE,
        f"maximum separation={max_separation:.3e}",
    )
    checks.expect(
        "stick--stick held-ratio tangential-force equality",
        torque_balance_error <= 1.0e-8,
        f"difference={torque_balance_error:.3e} N",
    )
    checks.expect(
        "stick--stick root is interior to static box",
        _is_interior_static_root(reference, margin=1.0e-6),
        (
            f"lambda=({reference.trial.friction_utilization.primary_lambda:.5f}, "
            f"{reference.trial.friction_utilization.secondary_lambda:.5f})"
        ),
    )


def _run_primary_slip_secondary_stick(
    *,
    baseline: DiagnosticBaseline,
    settings: EngagedContactSolveSettings,
    kinetic_utilization: float,
    slip_speed_offset: float,
    checks: CheckBook,
    show_matrix: bool,
) -> None:
    print("\n" + "=" * 112)
    print("2. Primary-slip / secondary-stick: one-dimensional secondary-lambda solve")
    print(
        "The belt is initialized below the primary surface by the requested offset, "
        "while the secondary is initially velocity-compatible with the belt."
    )

    base_state = replace(baseline.active_state, shift_speed=0.003)
    geometry = baseline.model.geometry.evaluate(base_state.shift_position)
    state = replace(
        base_state,
        primary_angular_speed=(
            (base_state.belt_speed + slip_speed_offset) / geometry.primary.effective
        ),
    )
    primary_slip = KineticSlipSpecification(
        interface=ContactInterface.PRIMARY,
        direction=SlipDirection.PULLEY_LEADS_BELT,
        kinetic_utilization=kinetic_utilization,
    )
    closure = EngagedContactClosure(snapshot=baseline.model.snapshot(state=state))
    result = closure.solve_primary_slip_secondary_stick(
        primary_slip=primary_slip,
        settings=settings,
    )
    _print_mixed_result(
        title="primary slip / secondary stick",
        result=result,
        slip_specification=primary_slip,
        show_matrix=show_matrix,
    )

    trial = result.trial
    checks.expect(
        "primary-slip / secondary-stick accepted",
        result.accepted,
        f"secondary stick residual={trial.relative_motion.secondary_relative_acceleration:.3e} m/s^2",
    )
    checks.expect(
        "primary-slip fixed lambda equals +mu_k",
        abs(trial.friction_utilization.primary_lambda - primary_slip.signed_lambda)
        <= 1.0e-12,
        f"lambda_p={trial.friction_utilization.primary_lambda:.6f}",
    )
    checks.expect(
        "primary-slip established direction is consistent",
        primary_slip.direction_is_consistent(
            trial.relative_motion,
            tolerances=settings.contact_tolerances,
        ),
        f"v_rel,p={trial.relative_motion.primary_relative_speed:.6f} m/s",
    )

    wrong_direction = KineticSlipSpecification(
        interface=ContactInterface.PRIMARY,
        direction=SlipDirection.BELT_LEADS_PULLEY,
        kinetic_utilization=kinetic_utilization,
    )
    wrong = closure.solve_primary_slip_secondary_stick(
        primary_slip=wrong_direction,
        settings=settings,
    )
    wrong_consistent = wrong_direction.direction_is_consistent(
        wrong.trial.relative_motion,
        tolerances=settings.contact_tolerances,
    )
    print(
        "\n  Opposite-direction negative control: "
        f"accepted={wrong.accepted}, direction_consistent={wrong_consistent}, "
        f"secondary residual={wrong.trial.relative_motion.secondary_relative_acceleration:.3e} m/s^2"
    )
    checks.expect(
        "primary-slip wrong-direction negative control is rejected or inconsistent",
        (not wrong.accepted) or (not wrong_consistent),
        f"accepted={wrong.accepted}, consistent={wrong_consistent}",
    )


def _run_primary_stick_secondary_slip(
    *,
    baseline: DiagnosticBaseline,
    settings: EngagedContactSolveSettings,
    kinetic_utilization: float,
    slip_speed_offset: float,
    checks: CheckBook,
    show_matrix: bool,
) -> None:
    print("\n" + "=" * 112)
    print("3. Primary-stick / secondary-slip: one-dimensional primary-lambda solve")
    print(
        "The belt is initialized above the secondary surface by the requested offset, "
        "while the primary is initially velocity-compatible with the belt."
    )

    base_state = replace(baseline.active_state, shift_speed=-0.012)
    geometry = baseline.model.geometry.evaluate(base_state.shift_position)
    state = replace(
        base_state,
        secondary_angular_speed=(
            (base_state.belt_speed - slip_speed_offset) / geometry.secondary.effective
        ),
    )
    secondary_slip = KineticSlipSpecification(
        interface=ContactInterface.SECONDARY,
        direction=SlipDirection.BELT_LEADS_PULLEY,
        kinetic_utilization=kinetic_utilization,
    )
    closure = EngagedContactClosure(snapshot=baseline.model.snapshot(state=state))
    result = closure.solve_primary_stick_secondary_slip(
        secondary_slip=secondary_slip,
        settings=settings,
    )
    _print_mixed_result(
        title="primary stick / secondary slip",
        result=result,
        slip_specification=secondary_slip,
        show_matrix=show_matrix,
    )

    trial = result.trial
    checks.expect(
        "primary-stick / secondary-slip accepted",
        result.accepted,
        f"primary stick residual={trial.relative_motion.primary_relative_acceleration:.3e} m/s^2",
    )
    checks.expect(
        "secondary-slip fixed lambda equals +mu_k",
        abs(trial.friction_utilization.secondary_lambda - secondary_slip.signed_lambda)
        <= 1.0e-12,
        f"lambda_s={trial.friction_utilization.secondary_lambda:.6f}",
    )
    checks.expect(
        "secondary-slip established direction is consistent",
        secondary_slip.direction_is_consistent(
            trial.relative_motion,
            tolerances=settings.contact_tolerances,
        ),
        f"v_rel,s={trial.relative_motion.secondary_relative_speed:.6f} m/s",
    )

    wrong_direction = KineticSlipSpecification(
        interface=ContactInterface.SECONDARY,
        direction=SlipDirection.PULLEY_LEADS_BELT,
        kinetic_utilization=kinetic_utilization,
    )
    wrong = closure.solve_primary_stick_secondary_slip(
        secondary_slip=wrong_direction,
        settings=settings,
    )
    wrong_consistent = wrong_direction.direction_is_consistent(
        wrong.trial.relative_motion,
        tolerances=settings.contact_tolerances,
    )
    print(
        "\n  Opposite-direction negative control: "
        f"accepted={wrong.accepted}, direction_consistent={wrong_consistent}, "
        f"primary residual={wrong.trial.relative_motion.primary_relative_acceleration:.3e} m/s^2"
    )
    checks.expect(
        "secondary-slip wrong-direction negative control is rejected or inconsistent",
        (not wrong.accepted) or (not wrong_consistent),
        f"accepted={wrong.accepted}, consistent={wrong_consistent}",
    )


def _run_both_slip(
    *,
    baseline: DiagnosticBaseline,
    settings: EngagedContactSolveSettings,
    kinetic_utilization: float,
    slip_speed_offset: float,
    checks: CheckBook,
    show_matrix: bool,
) -> None:
    print("\n" + "=" * 112)
    print("4. Both-slip: one direct six-by-six solve with both lambdas fixed kinetically")
    print(
        "The state has primary surface speed above the belt and secondary surface speed below the belt, "
        "so forward-drive kinetic directions are established before the solve."
    )

    base_state = baseline.quasi_static_state
    geometry = baseline.model.geometry.evaluate(base_state.shift_position)
    state = replace(
        base_state,
        primary_angular_speed=(
            (base_state.belt_speed + slip_speed_offset) / geometry.primary.effective
        ),
        secondary_angular_speed=(
            (base_state.belt_speed - slip_speed_offset) / geometry.secondary.effective
        ),
    )
    primary_slip = KineticSlipSpecification(
        interface=ContactInterface.PRIMARY,
        direction=SlipDirection.PULLEY_LEADS_BELT,
        kinetic_utilization=kinetic_utilization,
    )
    secondary_slip = KineticSlipSpecification(
        interface=ContactInterface.SECONDARY,
        direction=SlipDirection.BELT_LEADS_PULLEY,
        kinetic_utilization=kinetic_utilization,
    )
    closure = EngagedContactClosure(snapshot=baseline.model.snapshot(state=state))
    result = closure.evaluate_both_slip(
        primary_slip=primary_slip,
        secondary_slip=secondary_slip,
        contact_tolerances=settings.contact_tolerances,
    )
    trial = result.trial
    print(f"  fixed lambda_p={trial.friction_utilization.primary_lambda:.6f}")
    print(f"  fixed lambda_s={trial.friction_utilization.secondary_lambda:.6f}")
    _print_trial(trial=trial, show_matrix=show_matrix)
    print(
        "  direction checks: "
        f"primary={result.primary_direction_is_consistent}, "
        f"secondary={result.secondary_direction_is_consistent}"
    )
    print(
        "  Note: neither acceleration-level stick residual is constrained in this mode; "
        "their nonzero values are expected."
    )

    checks.expect(
        "both-slip primary lambda is fixed kinetically",
        abs(trial.friction_utilization.primary_lambda - primary_slip.signed_lambda)
        <= 1.0e-12,
        f"lambda_p={trial.friction_utilization.primary_lambda:.6f}",
    )
    checks.expect(
        "both-slip secondary lambda is fixed kinetically",
        abs(trial.friction_utilization.secondary_lambda - secondary_slip.signed_lambda)
        <= 1.0e-12,
        f"lambda_s={trial.friction_utilization.secondary_lambda:.6f}",
    )
    checks.expect(
        "both-slip primary direction is consistent",
        result.primary_direction_is_consistent,
        f"v_rel,p={trial.relative_motion.primary_relative_speed:.6f} m/s",
    )
    checks.expect(
        "both-slip secondary direction is consistent",
        result.secondary_direction_is_consistent,
        f"v_rel,s={trial.relative_motion.secondary_relative_speed:.6f} m/s",
    )
    _record_common_trial_checks(checks=checks, label="both-slip", trial=trial)


def _run_deadzone_geometry_check(
    *,
    baseline: DiagnosticBaseline,
    checks: CheckBook,
) -> None:
    print("\n" + "=" * 112)
    print("5. Deadzone / disengaged-contact geometry gate")
    print(
        "This section intentionally does not instantiate EngagedContactClosure.  Deadzone is the "
        "separate fifth system state: no lambda variables, wrap rows, or belt torque transfer."
    )

    state = baseline.deadzone_state
    snapshot = baseline.model.snapshot(state=state)
    geometry = snapshot.geometry
    primary = geometry.primary_axial_coordinate
    secondary = geometry.secondary_axial_coordinate
    belt = geometry.belt_axial_coordinate

    inactive = (
        state.shift_position < baseline.constants.deadzone_shift
        and abs(secondary.value) <= 1.0e-12
        and abs(secondary.d_value_ds) <= 1.0e-12
        and abs(belt.d_value_ds) <= 1.0e-12
        and abs(snapshot.secondary_helix.dtheta_ds) <= 1.0e-12
    )
    print(
        f"  s={state.shift_position * 1_000.0:.6f} mm; deadzone limit="
        f"{baseline.constants.deadzone_shift * 1_000.0:.6f} mm"
    )
    print(
        f"  x_p={primary.value * 1_000.0:.6f} mm, "
        f"x_s={secondary.value * 1_000.0:.6f} mm, "
        f"x_b={belt.value * 1_000.0:.6f} mm"
    )
    print(
        f"  dx_p/ds={primary.d_value_ds:.6f}, dx_s/ds={secondary.d_value_ds:.6f}, "
        f"dx_b/ds={belt.d_value_ds:.6f}, H={snapshot.secondary_helix.dtheta_ds:.6f} rad/m"
    )
    print(f"  inactive-contact geometry: {'PASS' if inactive else 'FAIL'}")

    primary_free = snapshot.engine_torque / snapshot.primary_rotational_inertia
    secondary_free = (
        snapshot.secondary_external_torque / snapshot.secondary_absolute_rotational_inertia
    )
    print("\n  Future disengaged RHS expectation")
    print("    tau_p=tau_s=0; belt_acceleration=0 without an added belt-drag model.")
    print(f"    primary free alpha=tau_eng/I_p={primary_free:.6f} rad/s^2")
    print(f"    secondary free alpha=tau_ext/I_s={secondary_free:.6f} rad/s^2")
    checks.expect(
        "deadzone removes secondary/belt/helix engaged coupling",
        inactive,
        "x_s'=x_b'=H=0 inside deadzone",
    )


def _print_mixed_result(*, title: str, result, slip_specification, show_matrix: bool) -> None:
    trial = result.trial
    print(
        f"  fixed {slip_specification.interface.value} lambda="
        f"{slip_specification.signed_lambda:+.6f}; accepted={result.accepted}; "
        f"optimizer={result.optimizer_message}"
    )
    print(
        f"  free sticking interface(s): {', '.join(interface.value for interface in result.sticking_interfaces)}; "
        f"||R_stick||={np.linalg.norm(result.sticking_residuals):.3e} m/s^2; "
        f"cond(J)={result.jacobian_condition_number:.3e}"
    )
    _print_trial(trial=trial, show_matrix=show_matrix)
    direction_ok = slip_specification.direction_is_consistent(
        trial.relative_motion,
        tolerances=result.settings.contact_tolerances,
    )
    print(
        f"  requested slip direction={slip_specification.direction.value}; "
        f"direction-consistent={direction_ok}"
    )


def _print_trial(*, trial, show_matrix: bool) -> None:
    unknowns = trial.six_by_six.unknowns
    motion = trial.relative_motion
    derivative = trial.state_derivative
    six_by_six = trial.six_by_six
    print(
        "  lambdas: "
        f"lambda_p={trial.friction_utilization.primary_lambda:+.8f}, "
        f"lambda_s={trial.friction_utilization.secondary_lambda:+.8f}"
    )
    print(
        "  closure unknowns: "
        f"alpha_p={unknowns.primary_angular_acceleration:.6f} rad/s^2, "
        f"alpha_s={unknowns.secondary_angular_acceleration:.6f} rad/s^2, "
        f"v_b_dot={unknowns.belt_acceleration:.6f} m/s^2, "
        f"s_ddot={unknowns.shift_acceleration:.6f} m/s^2"
    )
    print(
        f"  torque transfer: tau_p={unknowns.primary_torque:.6f} N m, "
        f"tau_s={unknowns.secondary_torque:.6f} N m"
    )
    print(
        "  relative motion: "
        f"v_rel,p={motion.primary_relative_speed:+.6f} m/s, "
        f"v_rel,s={motion.secondary_relative_speed:+.6f} m/s; "
        f"a_rel,p={motion.primary_relative_acceleration:+.6e} m/s^2, "
        f"a_rel,s={motion.secondary_relative_acceleration:+.6e} m/s^2"
    )
    print(
        "  derivative mapping: "
        f"[alpha_p={derivative.primary_angular_acceleration:.6f}, "
        f"alpha_s={derivative.secondary_angular_acceleration:.6f}, "
        f"v_b_dot={derivative.belt_acceleration:.6f}, "
        f"s_dot={derivative.shift_position_rate:.6f}, "
        f"s_ddot={derivative.shift_acceleration:.6f}, "
        f"psi_s_dot={derivative.secondary_shaft_angle_rate:.6f}]"
    )
    print(
        f"  six-by-six: rank={six_by_six.matrix_rank}, cond(A)={six_by_six.condition_number:.3e}, "
        f"max row residual={six_by_six.max_abs_equation_residual:.3e}"
    )
    if show_matrix:
        print("\n  A matrix [alpha_p, alpha_s, v_b_dot, s_ddot, tau_p, tau_s]:")
        print(np.array2string(six_by_six.matrix, precision=5, suppress_small=False))
        print("  b vector:")
        print(np.array2string(six_by_six.right_hand_side, precision=5, suppress_small=False))


def _record_common_trial_checks(*, checks: CheckBook, label: str, trial) -> None:
    six_by_six = trial.six_by_six
    derivative = trial.state_derivative
    unknowns = six_by_six.unknowns
    finite = all(
        np.isfinite(value)
        for value in (
            *unknowns.as_tuple(),
            trial.relative_motion.primary_relative_speed,
            trial.relative_motion.secondary_relative_speed,
            trial.relative_motion.primary_relative_acceleration,
            trial.relative_motion.secondary_relative_acceleration,
        )
    )
    derivative_matches = (
        abs(derivative.primary_angular_acceleration - unknowns.primary_angular_acceleration)
        <= 1.0e-12
        and abs(derivative.secondary_angular_acceleration - unknowns.secondary_angular_acceleration)
        <= 1.0e-12
        and abs(derivative.belt_acceleration - unknowns.belt_acceleration) <= 1.0e-12
        and abs(derivative.shift_acceleration - unknowns.shift_acceleration) <= 1.0e-12
    )
    checks.expect(
        f"{label}: full-rank finite six-by-six",
        six_by_six.matrix_rank == 6 and finite,
        f"rank={six_by_six.matrix_rank}, cond(A)={six_by_six.condition_number:.3e}",
    )
    checks.expect(
        f"{label}: imposed six-row residuals",
        six_by_six.max_abs_equation_residual <= DEFAULT_MATRIX_RESIDUAL_TOLERANCE,
        f"max={six_by_six.max_abs_equation_residual:.3e}",
    )
    checks.expect(
        f"{label}: state-derivative mapping",
        derivative_matches,
        "closure accelerations map directly to the derivative object",
    )


def _is_interior_static_root(result, *, margin: float) -> bool:
    utilization = result.trial.friction_utilization
    bounds = result.settings.static_bounds
    return (
        bounds.primary_lower + margin
        < utilization.primary_lambda
        < bounds.primary_upper - margin
        and bounds.secondary_lower + margin
        < utilization.secondary_lambda
        < bounds.secondary_upper - margin
    )


def _print_matrix(*, trial) -> None:
    _print_trial(trial=trial, show_matrix=True)


if __name__ == "__main__":
    raise SystemExit(main())
