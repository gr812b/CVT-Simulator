"""Shared physical fixed-pivot Baja default used by launch/grade tools.

The route tools historically called their tuning field ``tip_hardware_mass_per_flyweight_kg``.
For this fixed-pivot default that field has one explicit meaning:

    total concentrated tip-hardware mass PER FLYWEIGHT [kg]

The separately measured 13.646 g arm/body mass is always added as a uniform
slender arm.  The tip mass represents roller/bearing + bolt + nut/washer +
fixed tip hardware + tuning weight, all concentrated at the roller-centre
station.  This is the explicit simplified mass model documented in the
fixed-pivot appendix handoff.
"""

from __future__ import annotations

import inspect
from math import radians

from cinder.model.boundaries.engine import (
    EngineTorquePoint,
    FullThrottleTorqueCurve,
    TorqueCurveSpec,
)
from cinder.model.boundaries.vehicle import (
    FixedFinalDrive,
    RoadLoadModel,
    VehicleInertia,
    VehicleRoadLoadSpec,
)
from cinder.model.cvt.actuation import (
    FixedPivotCentrifugalActuatorSpec,
    FixedPivotFlyweightForceSpec,
    FlyweightMassGeometry,
    PivotedRollerFollowerFlyweightMap,
    PivotedRollerFollowerGeometrySpec,
    TorqueReactiveActuatorSpec,
    build_fixed_pivot_centrifugal_actuator,
    build_torque_reactive_actuator,
)
from cinder.model.cvt.actuation.forces import (
    AxialSpringForceSpec,
    HelicalTorqueReactionSpec,
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
    C3TransitionSegment,
    CircularSegment,
    HelixProfile,
    LinearSegment,
    PiecewiseRamp,
    linear_helix_segment,
)
from cad_drivetrain_inertias import (
    PCVT_TOTAL_MOI_KG_M2,
    SCVT_FIXED_SIDE_MOI_KG_M2,
    SCVT_MOVABLE_SHEAVE_MOI_KG_M2,
)

from cinder.model.system import (
    BeltContactSpec,
    CVTAssemblySpec,
    HelicalPulleyCoupling,
    PulleyPairSpec,
    PulleySpec,
)

INCH_TO_METRE = 0.0254
MILLIMETRE = 1.0e-3
FOOT_POUND_TO_NEWTON_METRE = 1.3558179483
RPM_TO_RAD_PER_SECOND = 2.0 * 3.141592653589793 / 60.0

# Measured / intentionally fixed mechanism dimensions.
FIXED_PIVOT_RADIUS_M = 1.675 * INCH_TO_METRE
FIXED_ARM_LENGTH_M = 1.241 * INCH_TO_METRE
FIXED_ROLLER_RADIUS_M = 6.5 * MILLIMETRE
FIXED_POINT_A_AXIAL_FROM_PIVOT_M = 1.5 * INCH_TO_METRE
FIXED_POINT_A_RADIAL_FROM_PIVOT_M = 0.2776 * INCH_TO_METRE
FIXED_ARM_MASS_PER_FLYWEIGHT_KG = 13.646e-3
FIXED_NUMBER_OF_FLYWEIGHTS = 3

# Small idealized C3 curvature transition.  This is a modeling input, not a
# measured dimension.
DEFAULT_LINEAR_LENGTH_M = 5.0 * MILLIMETRE
DEFAULT_C3_BLEND_LENGTH_M = 3.0 * MILLIMETRE
DEFAULT_CIRCULAR_LENGTH_M = 30.0 * MILLIMETRE


def build_primary_physical_ramp(c) -> PiecewiseRamp:
    """Build the provisional hard-to-soft physical roller ramp.

    Fixed-pivot physical geometry fields mean:
      primary_linear_ramp_angle_degrees       -> initial straight-ramp angle
      primary_circular_ramp_start_angle_degrees -> circular-section start angle
      primary_circular_ramp_end_angle_degrees   -> circular-section end angle

    All angles use the physical fixed-pivot convention: 0 deg is axial.
    """

    linear = LinearSegment(
        length=DEFAULT_LINEAR_LENGTH_M,
        angle_degrees=c.primary_linear_ramp_angle_degrees,
    )
    circular = CircularSegment(
        length=DEFAULT_CIRCULAR_LENGTH_M,
        angle_start_degrees=c.primary_circular_ramp_start_angle_degrees,
        angle_end_degrees=c.primary_circular_ramp_end_angle_degrees,
        quadrant=2,
    )
    blend = C3TransitionSegment.between_segments(
        left=linear,
        right=circular,
        length=DEFAULT_C3_BLEND_LENGTH_M,
    )
    ramp = PiecewiseRamp((linear, blend, circular))
    ramp.require_continuity(order=3)
    return ramp


def build_primary_mass_geometry(c) -> FlyweightMassGeometry:
    """Build the explicit uniform-arm + concentrated-tip mass approximation."""

    tip_hardware_mass_per_flyweight = float(c.tip_hardware_mass_per_flyweight)
    if tip_hardware_mass_per_flyweight <= 0.0:
        raise ValueError(
            "tip_hardware_mass_per_flyweight must be positive; for the fixed-pivot default it "
            "means concentrated tip-hardware mass per flyweight."
        )

    return FlyweightMassGeometry.uniform_arm_with_end_mass(
        number_of_flyweights=FIXED_NUMBER_OF_FLYWEIGHTS,
        arm_length=FIXED_ARM_LENGTH_M,
        arm_mass_per_flyweight=FIXED_ARM_MASS_PER_FLYWEIGHT_KG,
        end_mass_per_flyweight=tip_hardware_mass_per_flyweight,
        second_moment_z_per_flyweight=0.0,
    )


def build_primary_mechanism_map(c) -> PivotedRollerFollowerFlyweightMap:
    """Build and full-range validate the physical fixed-pivot map."""

    parameters = inspect.signature(
        PivotedRollerFollowerGeometrySpec
    ).parameters
    if "ramp_axial_direction" not in parameters:
        raise RuntimeError(
            "This checkout is missing the hardened fixed-pivot geometry "
            "(ramp_axial_direction). Apply the verified fixed-pivot recovery/"
            "hardening patch before installing this default."
        )

    geometry = PivotedRollerFollowerGeometrySpec(
        pivot_axial_position=0.0,
        pivot_radius=FIXED_PIVOT_RADIUS_M,
        arm_length=FIXED_ARM_LENGTH_M,
        roller_radius=FIXED_ROLLER_RADIUS_M,
        ramp_reference_axial_position=FIXED_POINT_A_AXIAL_FROM_PIVOT_M,
        ramp_reference_radius=(
            FIXED_PIVOT_RADIUS_M
            + FIXED_POINT_A_RADIAL_FROM_PIVOT_M
        ),
        ramp_profile=build_primary_physical_ramp(c),
        ramp_axial_direction=-1,
        axial_position_min=0.0,
        axial_position_max=c.max_shift,
        roller_side_sign=1,
        root_scan_points=513,
        validation_positions=129,
    )
    mechanism_map = PivotedRollerFollowerFlyweightMap(
        geometry_spec=geometry,
        mass_geometry=build_primary_mass_geometry(c),
        compilation_points=257,
    )

    report = getattr(mechanism_map, "validation_report", None)
    if report is not None:
        report.require_valid()
    return mechanism_map


def build_components(c):
    """Build the Baja route assembly with the physical fixed-pivot primary."""

    belt = BeltSectionSpec(
        height=c.belt_height,
        outer_width=c.belt_outer_width,
        inner_width=c.belt_inner_width,
        cord_depth_from_outer=c.belt_cord_depth_from_outer,
    )
    geometry = BeltPulleyGeometry(
        BeltPulleyGeometrySpec(
            belt=belt,
            belt_outer_length=c.belt_outer_length,
            primary_outer_radius_at_zero_shift=(
                c.primary_inner_radius_at_low + c.belt_height
            ),
            secondary_outer_radius_at_zero_shift=c.secondary_outer_radius_at_low,
            sheave_half_angle=radians(c.sheave_half_angle_degrees),
            deadzone_shift=c.deadzone_shift,
            max_shift=c.max_shift,
        )
    )

    primary_mechanism_map = build_primary_mechanism_map(c)

    primary_actuator = build_fixed_pivot_centrifugal_actuator(
        FixedPivotCentrifugalActuatorSpec(
            fixed_pivot_flyweight=FixedPivotFlyweightForceSpec(
                mechanism_map=primary_mechanism_map
            ),
            axial_spring=AxialSpringForceSpec(
                stiffness=c.primary_spring_rate,
                initial_compression=c.primary_spring_initial_compression,
                compression_per_axial_position=1.0,
            ),
        )
    )

    secondary_opening_travel = (
        geometry.secondary_opening_travel_at_max_shift
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
        TorqueReactiveActuatorSpec(
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

    # The CAD PCVT number is a complete rotating-assembly inertia.  The
    # fixed-pivot flyweights now contribute their own configuration-dependent
    # J_f(q), so using the complete CAD value as fixed hardware would double
    # count them.  Anchor the complete CAD total at the zero-shift CAD/reference
    # configuration and let J_f(q) vary dynamically away from that point.
    flyweight_reference_inertia = (
        primary_mechanism_map.evaluate(0.0).shaft_inertia
    )
    primary_fixed_hardware_inertia = (
        PCVT_TOTAL_MOI_KG_M2 - flyweight_reference_inertia
    )
    if primary_fixed_hardware_inertia < 0.0:
        raise ValueError(
            "Fixed-pivot flyweight J_f(0) exceeds the complete PCVT CAD MOI; "
            "the PCVT CAD inertia/flyweight mass interpretation is inconsistent."
        )

    inertias = resolve_inertias(
        drivetrain=DrivetrainInertias(
            primary=PrimaryInertia(
                fixed_rotating_hardware_inertia=(
                    primary_fixed_hardware_inertia
                ),
                movable_sheave_rotational_inertia=0.0,
                moving_sheave_mass=c.primary_moving_sheave_mass,
            ),
            secondary=SecondaryInertia(
                # The supplied SCVT CAD total is split rather than added:
                # fixed-side remainder + movable sheave == CAD total.
                fixed_rotating_hardware_inertia=(
                    SCVT_FIXED_SIDE_MOI_KG_M2
                ),
                movable_sheave_rotational_inertia=(
                    SCVT_MOVABLE_SHEAVE_MOI_KG_M2
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
                    torque=ftlb * FOOT_POUND_TO_NEWTON_METRE,
                )
                for rpm, ftlb in (
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
                c.engine_low_speed_braking_peak_rpm
                * RPM_TO_RAD_PER_SECOND
            ),
            high_speed_braking_torque=c.engine_governed_overspeed_torque,
            high_speed_braking_transition_width=(
                c.engine_governed_overspeed_transition_width_rpm
                * RPM_TO_RAD_PER_SECOND
            ),
        )
    )

    final_drive = FixedFinalDrive(
        reduction_ratio=c.final_drive_ratio,
        wheel_radius=c.wheel_radius,
    )
    vehicle = VehicleInertia(
        mass=c.vehicle_mass,
        wheel_rotational_inertia=c.wheel_rotational_inertia,
    )
    road_load = RoadLoadModel(
        spec=VehicleRoadLoadSpec(
            rolling_resistance_coefficient=(
                c.rolling_resistance_coefficient
            ),
            drag_coefficient=c.drag_coefficient,
            frontal_area=c.frontal_area,
        ),
        vehicle=vehicle,
        final_drive=final_drive,
    )

    assembly = CVTAssemblySpec(
        geometry=geometry,
        pulleys=PulleyPairSpec(
            primary=PulleySpec(actuator=primary_actuator),
            secondary=PulleySpec(
                actuator=secondary_actuator,
                helical_coupling=HelicalPulleyCoupling(
                    profile=helix_profile
                ),
            ),
        ),
        inertias=inertias,
        contact=BeltContactSpec(
            static_friction_coefficient=(
                c.belt_static_friction_coefficient
            ),
            kinetic_friction_coefficient=(
                c.belt_kinetic_friction_coefficient
            ),
        ),
    )
    return assembly, engine, road_load


def fixed_pivot_summary(c) -> dict[str, float | str]:
    """Small JSON-safe summary for CLI diagnostics."""

    mechanism_map = build_primary_mechanism_map(c)
    zero = mechanism_map.evaluate(0.0)
    full = mechanism_map.evaluate(c.max_shift)
    total_mass = (
        FIXED_NUMBER_OF_FLYWEIGHTS
        * (
            FIXED_ARM_MASS_PER_FLYWEIGHT_KG
            + float(c.tip_hardware_mass_per_flyweight)
        )
    )
    return {
        "tip_mass_per_flyweight_kg": float(c.tip_hardware_mass_per_flyweight),
        "pcvt_cad_total_inertia_kg_m2": PCVT_TOTAL_MOI_KG_M2,
        "flyweight_reference_inertia_kg_m2": zero.shaft_inertia,
        "primary_fixed_hardware_remainder_kg_m2": (
            PCVT_TOTAL_MOI_KG_M2 - zero.shaft_inertia
        ),
        "scvt_cad_total_inertia_kg_m2": (
            SCVT_FIXED_SIDE_MOI_KG_M2
            + SCVT_MOVABLE_SHEAVE_MOI_KG_M2
        ),
        "scvt_movable_helix_inertia_kg_m2": (
            SCVT_MOVABLE_SHEAVE_MOI_KG_M2
        ),
        "total_modeled_tip_hardware_mass_per_flyweight_kg": total_mass,
        "arm_length_mm": FIXED_ARM_LENGTH_M / MILLIMETRE,
        "roller_radius_mm": FIXED_ROLLER_RADIUS_M / MILLIMETRE,
        "q_at_zero_deg": zero.angle * 180.0 / 3.141592653589793,
        "q_at_full_deg": full.angle * 180.0 / 3.141592653589793,
        "Jprime_at_zero_kg_m": zero.shaft_inertia_gradient,
        "Jprime_at_full_kg_m": full.shaft_inertia_gradient,
    }
