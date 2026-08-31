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
from math import radians
from typing import Final

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
from cinder.dynamics import CVTDynamicsModel
from cinder.integration import CVTDynamicState
from cinder.contact import ContactTractionUtilization
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
from cinder.profiles import (
    HelixProfile,
    LinearSegment,
    PiecewiseRamp,
    linear_helix_segment,
)
from cinder.vehicle import (
    ConstantGradeRoadProfile,
    FixedFinalDrive,
    RoadLoadModel,
    VehicleRoadLoadSpec,
)


INCH_TO_METRE: Final[float] = 0.0254
FOOT_POUND_TO_NEWTON_METRE: Final[float] = 1.3558179483
RPM_TO_RAD_PER_SECOND: Final[float] = 2.0 * 3.141592653589793 / 60.0


@dataclass(frozen=True, slots=True)
class BajaTrialConstants:
    """One transparent collection of constants for the diagnostic baseline."""

    # Geometry and belt -----------------------------------------------------
    belt_height: float = 0.613 * INCH_TO_METRE  # legacy belt dimension
    belt_outer_width: float = 0.840 * INCH_TO_METRE  # legacy belt dimension
    belt_inner_width: float = 0.662 * INCH_TO_METRE  # legacy belt dimension
    belt_outer_length: float = 37.53 * INCH_TO_METRE  # legacy belt length
    belt_cord_depth_from_outer: float = 0.1 * INCH_TO_METRE
    # placeholder: old defaults did not specify cord-depth location.

    sheave_half_angle_degrees: float = 11.5  # legacy 23 degree included angle
    primary_inner_radius_at_low: float = (1.625 / 2.0) * INCH_TO_METRE
    secondary_outer_radius_at_low: float = 4.0 * INCH_TO_METRE
    # legacy primary value is the groove-bottom/inner radius; the 4 in secondary value is the outer belt-surface radius.

    deadzone_shift: float = (0.088 + 0.010) * INCH_TO_METRE  # legacy value
    max_shift: float = 0.75 * INCH_TO_METRE  # legacy value

    primary_ramp_angle_degrees: float = 30.0  # requested constant test ramp
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

    # Inertia ---------------------------------------------------------------
    engine_rotational_inertia: float = 0.1  # legacy kg m^2
    primary_cvt_rotational_inertia: float = 0.005
    # placeholder: the old system did not split primary pulley spin inertia.
    primary_moving_sheave_mass: float = 1.0681  # project/CAD estimate, kg

    secondary_fixed_rotational_inertia: float = 0.1  # legacy kg m^2
    gearbox_input_rotational_inertia: float = 0.05  # legacy kg m^2
    secondary_movable_sheave_rotational_inertia: float = 0.0025139
    # project/CAD estimate, kg m^2; confirm against final CAD mass properties.
    secondary_moving_sheave_mass: float = 0.705141  # project/CAD estimate, kg

    rubber_density: float = 1100.0  # legacy material-density constant, kg/m^3
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
    model: CVTDynamicsModel
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
            c.primary_inner_radius_at_low + c.belt_height
        ),
        secondary_outer_radius_at_zero_shift=(
            c.secondary_outer_radius_at_low
        ),
        sheave_half_angle=radians(c.sheave_half_angle_degrees),
        deadzone_shift=c.deadzone_shift,
        max_shift=c.max_shift,
    )
    geometry = BeltPulleyGeometry(geometry_spec)

    primary_ramp = PiecewiseRamp(
        (
            LinearSegment(
                length=c.max_shift,
                angle_degrees=c.primary_ramp_angle_degrees,
            ),
        )
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

    active_shift_position = c.deadzone_shift + 0.60 * (c.max_shift - c.deadzone_shift)
    deadzone_shift_position = 0.50 * c.deadzone_shift

    return BajaTrialBaseline(
        constants=c,
        model=model,
        active_shift_state=_no_slip_state_at_shift(
            geometry=geometry,
            shift_position=active_shift_position,
            secondary_speed=c.active_secondary_speed,
            shift_speed=c.active_shift_speed,
            secondary_shaft_angle=c.secondary_shaft_angle,
        ),
        quasi_static_state=_no_slip_state_at_shift(
            geometry=geometry,
            shift_position=active_shift_position,
            secondary_speed=c.active_secondary_speed,
            shift_speed=c.quasi_static_shift_speed,
            secondary_shaft_angle=c.secondary_shaft_angle,
        ),
        deadzone_state=_no_slip_state_at_shift(
            geometry=geometry,
            shift_position=deadzone_shift_position,
            secondary_speed=c.deadzone_secondary_speed,
            shift_speed=c.deadzone_shift_speed,
            secondary_shaft_angle=c.secondary_shaft_angle,
        ),
        default_trial=ContactTractionUtilization(
            primary_lambda=0.10,
            secondary_lambda=-0.10,
        ),
        lambda_sweep=(
            ContactTractionUtilization(primary_lambda=0.05, secondary_lambda=-0.05),
            ContactTractionUtilization(primary_lambda=0.10, secondary_lambda=-0.10),
            ContactTractionUtilization(primary_lambda=0.15, secondary_lambda=-0.10),
            ContactTractionUtilization(primary_lambda=0.10, secondary_lambda=-0.15),
            ContactTractionUtilization(primary_lambda=0.20, secondary_lambda=-0.20),
        ),
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
