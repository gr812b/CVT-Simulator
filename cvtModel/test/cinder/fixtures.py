"""Baja-ish physical baseline for six-by-six trial diagnostics.

This module intentionally centralizes the numerical values used by
``preview_trial_six_by_six.py`` and its regression tests.  It is not yet a
production vehicle configuration.  Values are tagged in comments as either:

* legacy: copied from the previous simulator defaults supplied with this repo;
* project: a currently available project/CAD estimate; or
* placeholder: selected only because the old model did not provide a value.

The test baseline uses a constant 30 degree primary radial ramp and a constant
26 degree secondary helix, as requested.  The purpose is to exercise every
six-by-six row at credible scales before the lambda root solver is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, radians
from typing import Final

from cinder.model.cvt.actuation import (
    CentrifugalActuatorSpec,
    TorqueReactiveActuatorSpec,
    build_centrifugal_actuator,
    build_torque_reactive_actuator,
)
from cinder.model.cvt.actuation.forces import (
    AxialSpringForceSpec,
    CentrifugalRampForceSpec,
    HelicalTorqueReactionSpec,
)
from cinder.model.boundaries.output import LockedFinalDriveVehicle
from cinder.model.system import (
    BeltContactSpec,
    CVTAssemblySpec,
    CVTSimulationCase,
    HelicalPulleyCoupling,
    OperatingScenario,
    PulleyPairSpec,
    PulleySpec,
)
from cinder.execution.hybrid import CVTDynamicState
from cinder.execution.hybrid.cvt_operating_hybrid import (
    CVTOperatingHybridSystem,
    CVTOperatingSystemConfig,
)
from cinder.execution.hybrid.cvt_operating_limits import CVTShiftOperatingLimits
from cinder.model.cvt.contact import ContactTractionLaw, ContactTractionUtilization
from cinder.model.cvt.dynamics import EngagedContactSolveSettings, LambdaSearchBounds
from cinder.model.boundaries.input.engine import (
    EngineTorquePoint,
    FullThrottleTorqueCurve,
    TorqueCurveSpec,
)
from cinder.model.cvt.geometry import (
    BeltPulleyGeometry,
    BeltPulleyGeometrySpec,
    BeltSectionSpec,
)
from cinder.model.cvt.inertia import (
    BeltMass,
    DrivetrainInertias,
    PrimaryInertia,
    SecondaryInertia,
    resolve_inertias,
)
from cinder.model.cvt.profiles import (
    CircularSegment,
    HelixProfile,
    LinearSegment,
    PiecewiseRamp,
    linear_helix_segment,
)
from cinder.model.boundaries.output.vehicle import (
    ConstantGradeRoadProfile,
    FixedFinalDrive,
    RoadLoadModel,
    VehicleInertia,
    VehicleRoadLoadSpec,
)

INCH_TO_METRE: Final[float] = 0.0254
FOOT_POUND_TO_NEWTON_METRE: Final[float] = 1.3558179483
RPM_TO_RAD_PER_SECOND: Final[float] = 2.0 * 3.141592653589793 / 60.0
WATTS_PER_MECHANICAL_HORSEPOWER: Final[float] = 745.6998715822702


@dataclass(frozen=True, slots=True)
class BajaTrialConstants:
    """One transparent collection of constants for the diagnostic baseline."""

    # Geometry and belt -----------------------------------------------------
    belt_height: float = 0.613 * INCH_TO_METRE  # legacy belt dimension
    belt_outer_width: float = 0.840 * INCH_TO_METRE  # legacy belt dimension
    belt_inner_width: float = 0.662 * INCH_TO_METRE  # legacy belt dimension
    belt_outer_length: float = 37.53 * INCH_TO_METRE  # legacy belt length
    belt_cord_depth_from_outer: float = 0.5 * 0.613 * INCH_TO_METRE
    # placeholder: old defaults did not specify cord-depth location.

    sheave_half_angle_degrees: float = 11.5  # legacy 23 degree included angle
    primary_effective_radius_at_low: float = (1.625 / 2.0) * INCH_TO_METRE
    secondary_effective_radius_at_low: float = 4.0 * INCH_TO_METRE
    # legacy geometry values interpreted as effective cord radii.

    deadzone_shift: float = (0.088 + 0.010) * INCH_TO_METRE  # legacy value
    max_shift: float = 0.75 * INCH_TO_METRE  # legacy value

    # The baseline still supports the original constant linear ramp, but the
    # launch tools may select a hard-to-soft circular profile.  The circular
    # profile has high initial slope (strong early clamp) which decays smoothly
    # with shift travel; it is only a profile choice, not a new force law.
    primary_ramp_kind: str = "linear"  # "linear" or "circular_hard_to_soft"
    primary_ramp_angle_degrees: float = 30.0  # linear-ramp tangent angle
    primary_ramp_start_angle_degrees: float = 42.0  # circular: strong low-ratio slope
    primary_ramp_end_angle_degrees: float = 12.0  # circular: gentler high-ratio slope
    helix_angle_degrees: float = 26.0  # requested constant test helix
    initial_flyweight_radius: float = 0.04878  # legacy value
    helix_radius: float = 0.04445  # legacy value

    # Actuation -------------------------------------------------------------
    flyweight_mass: float = 0.5  # legacy value, equivalent flyweight mass
    primary_spring_rate: float = 12_784.0  # legacy N/m
    primary_spring_initial_compression: float = 0.1
    # legacy default retained; verify its intended unit/preload against hardware.

    secondary_torsional_spring_rate: float = 3.476  # legacy N m/rad
    secondary_torsional_initial_twist: float = radians(200.0)  # legacy 200 deg
    secondary_compression_spring_rate: float = 3_532.0  # legacy N/m
    secondary_spring_initial_compression: float = 0.1
    # legacy default retained; verify its intended unit/preload against hardware.

    # Engine ---------------------------------------------------------------
    # The supplied positive running points below are the legacy full-throttle
    # Baja map.  Their PCHIP interpolation remains below the competition's
    # 10 hp limit; do not add a hard P = tau*omega clamp inside CINDER.
    #
    # Above the 4000 rpm governed end of that map, the existing torque-curve
    # implementation smoothly transitions from 0 N m to a finite negative
    # *governed net torque*.  This represents throttle closure by the governor
    # plus pumping/friction losses when the vehicle drives the engine faster
    # than its permitted WOT operating range.  It is intentionally a tunable
    # sensitivity assumption, not a measured coast-down curve.
    engine_power_limit_hp: float = 10.0
    engine_low_speed_braking_torque: float = -5.0
    engine_low_speed_braking_peak_rpm: float = 500.0
    engine_governed_overspeed_torque: float = -28.0
    engine_governed_overspeed_transition_width_rpm: float = 1500.0

    # Inertia ---------------------------------------------------------------
    input_equivalent_rotational_inertia: float = 0.1  # engine/flywheel, kg m^2
    primary_rotating_hardware_inertia: float = 0.005
    # placeholder: the old system did not split primary pulley spin inertia.
    primary_moving_sheave_mass: float = 1.0681  # project/CAD estimate, kg

    secondary_fixed_rotating_hardware_inertia: float = (
        0.1  # CVT secondary hardware, kg m^2
    )
    direct_secondary_shaft_inertia: float = 0.05  # gearbox/input shaft, kg m^2
    secondary_movable_sheave_rotational_inertia: float = 0.0025139
    # project/CAD estimate, kg m^2; confirm against final CAD mass properties.
    secondary_moving_sheave_mass: float = 0.705141  # project/CAD estimate, kg

    rubber_density: float = 1100.0  # legacy material-density constant, kg/m^3
    belt_friction_coefficient: float = 0.30
    # Assembly contact metadata. Current launch traction capacity remains
    # configured through ContactTractionLaw lambda limits.
    vehicle_mass: float = 225.0 + 75.0  # legacy vehicle + driver masses, kg
    driven_wheel_rotational_inertia: float = 0.2
    # legacy value was labelled "all wheels"; temporarily treated as total driven-wheel inertia.

    # Vehicle/road ----------------------------------------------------------
    final_drive_ratio: float = 7.556  # legacy gearbox ratio
    wheel_radius: float = 11.0 * INCH_TO_METRE  # legacy 22 inch tire diameter
    frontal_area: float = 1.11484  # legacy m^2
    drag_coefficient: float = 0.6  # legacy
    rolling_resistance_coefficient: float = 0.015  # legacy

    # Representative dynamic point ----------------------------------------
    active_secondary_speed: float = 180.0  # rad/s, ~1719 rpm
    deadzone_secondary_speed: float = 60.0  # rad/s, ~573 rpm
    active_shift_speed: float = 0.012  # m/s, deliberate nonzero test value
    quasi_static_shift_speed: float = 0.0
    # Deliberately zero: engaged, fixed-ratio diagnostic state. It isolates
    # torque-transfer and lambda closure from shift-rate / convective terms.
    deadzone_shift_speed: float = 0.006  # m/s, deliberate nonzero test value
    secondary_shaft_angle: float = 250.0  # rad, arbitrary route position


@dataclass(frozen=True, slots=True)
class BajaTrialBaseline:
    """Fully assembled diagnostic model and two kinematically consistent states."""

    constants: BajaTrialConstants
    assembly: CVTAssemblySpec
    case: CVTSimulationCase
    active_shift_state: CVTDynamicState
    quasi_static_state: CVTDynamicState
    deadzone_state: CVTDynamicState
    default_trial: ContactTractionUtilization
    lambda_sweep: tuple[ContactTractionUtilization, ...]


def build_baja_trial_baseline(
    constants: BajaTrialConstants | None = None,
) -> BajaTrialBaseline:
    """Build one repeatable Baja-ish diagnostic model.

    The two provided states are initialized with local no-slip belt speeds.
    They are not expected to remain no-slip after a trial six-by-six solve at
    arbitrary lambda values; that later mismatch becomes the outer lambda-root
    residual.
    """

    c = constants or BajaTrialConstants()

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

    if c.primary_ramp_kind == "linear":
        primary_ramp_segment = LinearSegment(
            length=c.max_shift,
            angle_degrees=c.primary_ramp_angle_degrees,
        )
    elif c.primary_ramp_kind == "circular_hard_to_soft":
        # Q2 gives positive radial displacement slope that decreases smoothly
        # from steep to gentle.  Therefore m*omega^2*r_f*dr_f/ds is large near
        # low ratio and falls away as the movable sheave shifts outward.
        primary_ramp_segment = CircularSegment(
            length=c.max_shift,
            angle_start_degrees=c.primary_ramp_start_angle_degrees,
            angle_end_degrees=c.primary_ramp_end_angle_degrees,
            quadrant=2,
        )
    else:
        raise ValueError(
            "primary_ramp_kind must be 'linear' or 'circular_hard_to_soft'; "
            f"received {c.primary_ramp_kind!r}."
        )
    primary_ramp = PiecewiseRamp((primary_ramp_segment,))
    primary_actuator = build_centrifugal_actuator(
        CentrifugalActuatorSpec(
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

    # The usable positive secondary-opening travel follows the actual
    # fixed-length belt geometry rather than assuming q_max == max_shift.
    terminal_geometry = geometry.evaluate(c.max_shift)
    secondary_opening_travel = -terminal_geometry.secondary_axial_coordinate.value
    if secondary_opening_travel <= 0.0:
        raise RuntimeError(
            "Baseline geometry did not produce positive secondary opening."
        )

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
    secondary_actuator = build_torque_reactive_actuator(
        spec=TorqueReactiveActuatorSpec(
            axial_spring=AxialSpringForceSpec(
                stiffness=c.secondary_compression_spring_rate,
                initial_compression=c.secondary_spring_initial_compression,
                compression_per_axial_position=-1.0,
            ),
            helical_reaction=HelicalTorqueReactionSpec(
                torsional_stiffness=c.secondary_torsional_spring_rate,
                initial_twist=c.secondary_torsional_initial_twist,
                movable_member_torque_fraction=0.5,
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
                rotating_hardware_inertia=c.primary_rotating_hardware_inertia,
                moving_sheave_mass=c.primary_moving_sheave_mass,
            ),
            secondary=SecondaryInertia(
                fixed_rotating_hardware_inertia=(
                    c.secondary_fixed_rotating_hardware_inertia
                ),
                movable_sheave_rotational_inertia=(
                    c.secondary_movable_sheave_rotational_inertia
                ),
                moving_sheave_mass=c.secondary_moving_sheave_mass,
            ),
            belt=BeltMass(density=c.rubber_density),
        ),
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
            low_speed_braking_torque=c.engine_low_speed_braking_torque,
            low_speed_braking_peak_speed=(
                c.engine_low_speed_braking_peak_rpm * RPM_TO_RAD_PER_SECOND
            ),
            high_speed_braking_torque=c.engine_governed_overspeed_torque,
            high_speed_braking_transition_width=(
                c.engine_governed_overspeed_transition_width_rpm * RPM_TO_RAD_PER_SECOND
            ),
            # The generic PCHIP tail therefore gives an increasing-magnitude
            # negative governed torque from 4000 rpm to 5500 rpm, then a
            # bounded -28 N m plateau.  No generic engine-source edit is
            # needed to express this curve.
        ),
        equivalent_rotational_inertia=c.input_equivalent_rotational_inertia,
    )

    _validate_full_throttle_power_limit(
        engine=engine,
        power_limit_hp=c.engine_power_limit_hp,
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
    output_boundary = LockedFinalDriveVehicle(
        road_load=road_load,
        road_profile=ConstantGradeRoadProfile(),
        direct_secondary_shaft_inertia=c.direct_secondary_shaft_inertia,
    )
    assembly = CVTAssemblySpec(
        geometry=geometry,
        pulleys=PulleyPairSpec(
            input=PulleySpec(actuator=primary_actuator),
            output=PulleySpec(
                actuator=secondary_actuator,
                helical_coupling=HelicalPulleyCoupling(profile=helix_profile),
            ),
        ),
        inertias=inertias,
        contact=BeltContactSpec(friction_coefficient=c.belt_friction_coefficient),
    )

    active_shift_position = c.deadzone_shift + 0.60 * (c.max_shift - c.deadzone_shift)
    deadzone_shift_position = 0.50 * c.deadzone_shift
    active_shift_state = _no_slip_state_at_shift(
        geometry=geometry,
        shift_position=active_shift_position,
        secondary_speed=c.active_secondary_speed,
        shift_speed=c.active_shift_speed,
        secondary_shaft_angle=c.secondary_shaft_angle,
    )
    quasi_static_state = _no_slip_state_at_shift(
        geometry=geometry,
        shift_position=active_shift_position,
        secondary_speed=c.active_secondary_speed,
        shift_speed=c.quasi_static_shift_speed,
        secondary_shaft_angle=c.secondary_shaft_angle,
    )
    deadzone_state = _no_slip_state_at_shift(
        geometry=geometry,
        shift_position=deadzone_shift_position,
        secondary_speed=c.deadzone_secondary_speed,
        shift_speed=c.deadzone_shift_speed,
        secondary_shaft_angle=c.secondary_shaft_angle,
    )
    case = CVTSimulationCase(
        cvt=assembly,
        input_boundary=engine,
        output_boundary=output_boundary,
        scenario=OperatingScenario(
            time_span=(0.0, 10.0),
            initial_state=active_shift_state,
        ),
    )
    return BajaTrialBaseline(
        constants=c,
        assembly=assembly,
        case=case,
        active_shift_state=active_shift_state,
        quasi_static_state=quasi_static_state,
        deadzone_state=deadzone_state,
        default_trial=ContactTractionUtilization(
            primary_lambda=0.10,
            secondary_lambda=0.10,
        ),
        lambda_sweep=(
            ContactTractionUtilization(primary_lambda=0.05, secondary_lambda=0.05),
            ContactTractionUtilization(primary_lambda=0.10, secondary_lambda=0.10),
            ContactTractionUtilization(primary_lambda=0.15, secondary_lambda=0.10),
            ContactTractionUtilization(primary_lambda=0.10, secondary_lambda=0.15),
            ContactTractionUtilization(primary_lambda=0.20, secondary_lambda=0.20),
        ),
    )


def _validate_full_throttle_power_limit(
    *,
    engine: FullThrottleTorqueCurve,
    power_limit_hp: float,
) -> None:
    """Reject a positive WOT curve that exceeds the diagnostic Baja cap.

    The check samples only the supplied positive-torque operating range.  It
    deliberately does *not* alter the curve, so the ODE still sees a smooth
    PCHIP mapping rather than a solver-facing ``min(P/omega)`` kink.
    """

    if not isfinite(power_limit_hp) or power_limit_hp <= 0.0:
        raise ValueError("engine_power_limit_hp must be finite and positive.")

    maximum_power_w = max(
        max(engine.torque_at(angular_speed), 0.0) * angular_speed
        for angular_speed in (
            engine.minimum_speed
            + (engine.maximum_speed - engine.minimum_speed) * index / 1000.0
            for index in range(1001)
        )
    )
    limit_w = power_limit_hp * WATTS_PER_MECHANICAL_HORSEPOWER
    if maximum_power_w > limit_w * (1.0 + 1.0e-9):
        raise ValueError(
            "Supplied positive full-throttle torque map exceeds the configured "
            f"{power_limit_hp:.6g} hp cap: {maximum_power_w / WATTS_PER_MECHANICAL_HORSEPOWER:.4f} hp."
        )


def _no_slip_state_at_shift(
    *,
    geometry: BeltPulleyGeometry,
    shift_position: float,
    secondary_speed: float,
    shift_speed: float,
    secondary_shaft_angle: float,
) -> CVTDynamicState:
    """Construct a kinematically compatible state before trial closure."""

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


# Test-only runtime construction -------------------------------------------------
# These helpers deliberately live under test/cinder, rather than in launchTools.
# They are a deterministic mechanical fixture for CINDER's own package tests and
# must not import plotting, project scripts, or repository-local tooling.


def build_operating_configuration(
    constants: BajaTrialConstants | None = None,
    *,
    static_lambda_limit: float = 0.65,
    kinetic_lambda_magnitude: float = 0.55,
) -> tuple[CVTOperatingSystemConfig, BajaTrialBaseline]:
    """Build deterministic test-only execution settings and one baseline case."""

    baseline = build_baja_trial_baseline(constants)
    traction_law = ContactTractionLaw.symmetric(
        primary_static_lambda_limit=static_lambda_limit,
        secondary_static_lambda_limit=static_lambda_limit,
        primary_kinetic_lambda_magnitude=kinetic_lambda_magnitude,
        secondary_kinetic_lambda_magnitude=kinetic_lambda_magnitude,
    )
    configuration = CVTOperatingSystemConfig(
        traction_law=traction_law,
        solve_settings=EngagedContactSolveSettings(
            lambda_search_bounds=LambdaSearchBounds.symmetric(
                primary_half_width=3.0,
                secondary_half_width=3.0,
            ),
            initial_guess=baseline.default_trial,
            maximum_closure_condition_number=1.0e8,
        ),
        operating_limits=CVTShiftOperatingLimits(
            lower_stop_shift=0.0,
            engagement_shift=baseline.constants.deadzone_shift,
            upper_stop_shift=baseline.constants.max_shift,
        ),
    )
    return configuration, baseline


def build_operating_system(
    constants: BajaTrialConstants | None = None,
    *,
    static_lambda_limit: float = 0.65,
    kinetic_lambda_magnitude: float = 0.55,
) -> tuple[CVTOperatingHybridSystem, BajaTrialBaseline]:
    """Build one runtime system from the test fixture case."""

    configuration, baseline = build_operating_configuration(
        constants,
        static_lambda_limit=static_lambda_limit,
        kinetic_lambda_magnitude=kinetic_lambda_magnitude,
    )
    return configuration.build(baseline.case), baseline


def launch_initial_state(*, primary_rpm: float = 1800.0) -> CVTDynamicState:
    """Return a rest-launch state: spinning primary and stationary driven side."""

    if not isfinite(primary_rpm) or primary_rpm < 0.0:
        raise ValueError("primary_rpm must be finite and non-negative.")
    return CVTDynamicState(
        primary_angular_speed=primary_rpm * RPM_TO_RAD_PER_SECOND,
        secondary_angular_speed=0.0,
        belt_speed=0.0,
        shift_position=0.0,
        shift_speed=0.0,
        secondary_shaft_angle=0.0,
    )


def case_with_output_road_profile(
    case: CVTSimulationCase,
    road_profile: ConstantGradeRoadProfile,
) -> CVTSimulationCase:
    """Return a test case differing only in its locked-vehicle route."""

    if not isinstance(case.output_boundary, LockedFinalDriveVehicle):
        raise TypeError("fixture case must use a LockedFinalDriveVehicle boundary.")
    return case.with_output_boundary(
        case.output_boundary.with_road_profile(road_profile)
    )


def build_system_from_case(
    case: CVTSimulationCase,
    *,
    configuration: CVTOperatingSystemConfig,
) -> CVTOperatingHybridSystem:
    """Build the runtime system through CINDER's normal case/config boundary."""

    return configuration.build(case)
