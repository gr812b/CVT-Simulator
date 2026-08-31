"""CINDER 1.0.0 reconstruction of Ballew's simulated acceleration case."""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, isclose, pi, radians, sqrt, tan
from pathlib import Path

from scipy.optimize import brentq

from cinder import (
    BeltContactSpec,
    CVTAssemblySpec,
    CVTState,
    ConstantGradeRoadProfile,
    FixedFinalDrive,
    FixedShaftBoundary,
    LockedFinalDriveShaftBoundary,
    PulleyPairSpec,
    PulleySpec,
    RoadLoadModel,
    SecondaryShaftAngleHost,
    VehicleInertia,
    VehicleRoadLoadSpec,
)
from cinder.hosts import CVTHost
from cinder.model.cvt.actuation import PulleyActuator
from cinder.model.cvt.geometry import BeltPulleyGeometry, BeltPulleyGeometrySpec, BeltSectionSpec
from cinder.model.cvt.inertia import (
    BeltMass,
    DrivetrainInertias,
    PrimaryInertia,
    ResolvedInertias,
    SecondaryInertia,
    resolve_inertias,
)

from .actuation import ConstantAxialForce, TabulatedAxialForce
from .constants import (
    CINDER_KINETIC_TRACTION_LAMBDA_MAGNITUDE,
    CINDER_STATIC_TRACTION_LAMBDA_LIMIT,
    DIRECT_SECONDARY_BOUNDARY_INERTIA_KG_M2,
    PUBLISHED,
    RECONSTRUCTED_AIR_DENSITY_KG_PER_M3,
    RECONSTRUCTED_GRAVITY_M_PER_S2,
    RECONSTRUCTED_ROLLING_SPEED_REGULARIZATION_M_PER_S,
)

_ROOT_TOLERANCE = 1.0e-12


@dataclass(frozen=True, slots=True)
class BallewEquivalentBeltMapping:
    section: BeltSectionSpec
    reference_effective_length_m: float
    cinder_outer_length_m: float
    equivalent_cross_sectional_area_m2: float
    effective_density_kg_per_m3: float
    primary_effective_radius_at_zero_shift_m: float
    secondary_effective_radius_at_zero_shift_m: float
    maximum_shift_m: float

    @property
    def resolved_mass_kg(self) -> float:
        return (
            self.effective_density_kg_per_m3
            * self.equivalent_cross_sectional_area_m2
            * self.cinder_outer_length_m
        )


@dataclass(frozen=True, slots=True)
class BallewBoundarySetup:
    primary: FixedShaftBoundary
    secondary: LockedFinalDriveShaftBoundary
    host: CVTHost
    road_load: RoadLoadModel


def _open_belt_length(
    *, center_distance: float, primary_radius: float, secondary_radius: float
) -> float:
    difference = secondary_radius - primary_radius
    alpha = asin(difference / center_distance)
    primary_wrap = pi - 2.0 * alpha
    secondary_wrap = pi + 2.0 * alpha
    span = sqrt(center_distance**2 - difference**2)
    return primary_radius * primary_wrap + secondary_radius * secondary_wrap + 2.0 * span


def build_equivalent_belt_mapping() -> BallewEquivalentBeltMapping:
    """A4: map Ballew's 1-D nodal path to CINDER's effective/cord-line path."""

    section = BeltSectionSpec(
        height=PUBLISHED.figure39_core_height_m,
        outer_width=PUBLISHED.figure39_core_outer_width_m,
        inner_width=PUBLISHED.figure39_core_inner_width_m,
        cord_depth_from_outer=PUBLISHED.figure39_cord_depth_from_outer_m,
    )
    area = 0.5 * section.height * (section.outer_width + section.inner_width)
    reference_length = PUBLISHED.belt_length_m
    outer_length = reference_length + 2.0 * pi * section.cord_depth_from_outer
    effective_density = PUBLISHED.belt_mass_kg / (area * outer_length)

    primary_zero = brentq(
        lambda primary_radius: (
            _open_belt_length(
                center_distance=PUBLISHED.center_distance_m,
                primary_radius=primary_radius,
                secondary_radius=PUBLISHED.output_radius_max_m,
            )
            - reference_length
        ),
        PUBLISHED.input_radius_min_m,
        PUBLISHED.input_radius_max_m,
        xtol=_ROOT_TOLERANCE,
    )
    secondary_zero = PUBLISHED.output_radius_max_m
    maximum_shift = 2.0 * tan(radians(PUBLISHED.sheave_half_angle_deg)) * (
        PUBLISHED.input_radius_max_m - primary_zero
    )

    mapping = BallewEquivalentBeltMapping(
        section=section,
        reference_effective_length_m=reference_length,
        cinder_outer_length_m=outer_length,
        equivalent_cross_sectional_area_m2=area,
        effective_density_kg_per_m3=effective_density,
        primary_effective_radius_at_zero_shift_m=primary_zero,
        secondary_effective_radius_at_zero_shift_m=secondary_zero,
        maximum_shift_m=maximum_shift,
    )
    if not isclose(mapping.resolved_mass_kg, PUBLISHED.belt_mass_kg, abs_tol=2.0e-12):
        raise RuntimeError("Equivalent Ballew mapping no longer preserves 1 kg belt mass.")
    return mapping


def build_ballew_geometry(
    mapping: BallewEquivalentBeltMapping | None = None,
) -> BeltPulleyGeometry:
    mapping = mapping or build_equivalent_belt_mapping()
    cord_depth = mapping.section.cord_depth_from_outer
    geometry = BeltPulleyGeometry(
        BeltPulleyGeometrySpec(
            belt=mapping.section,
            belt_outer_length=mapping.cinder_outer_length_m,
            primary_outer_radius_at_zero_shift=(
                mapping.primary_effective_radius_at_zero_shift_m + cord_depth
            ),
            secondary_outer_radius_at_zero_shift=(
                mapping.secondary_effective_radius_at_zero_shift_m + cord_depth
            ),
            sheave_half_angle=radians(PUBLISHED.sheave_half_angle_deg),
            deadzone_shift=0.0,
            max_shift=mapping.maximum_shift_m,
        )
    )
    if not isclose(
        geometry.spec.center_distance,
        PUBLISHED.center_distance_m,
        rel_tol=0.0,
        abs_tol=2.0e-12,
    ):
        raise RuntimeError("Ballew geometry no longer preserves published center distance.")
    return geometry


def solve_initial_shift_from_published_speeds(geometry: BeltPulleyGeometry) -> float:
    target_speed_ratio = PUBLISHED.initial_input_rpm / PUBLISHED.initial_output_rpm

    def residual(shift: float) -> float:
        position = geometry.evaluate(shift)
        return position.secondary.effective / position.primary.effective - target_speed_ratio

    lo = residual(0.0)
    hi = residual(geometry.spec.max_shift)
    if lo == 0.0:
        return 0.0
    if hi == 0.0:
        return geometry.spec.max_shift
    if lo * hi > 0.0:
        raise RuntimeError("Published initial shaft-speed ratio lies outside geometry range.")
    return brentq(residual, 0.0, geometry.spec.max_shift, xtol=_ROOT_TOLERANCE)


def build_ballew_inertias(
    mapping: BallewEquivalentBeltMapping | None = None,
) -> ResolvedInertias:
    mapping = mapping or build_equivalent_belt_mapping()
    return resolve_inertias(
        drivetrain=DrivetrainInertias(
            primary=PrimaryInertia(
                fixed_rotating_hardware_inertia=0.0,
                movable_sheave_rotational_inertia=0.0,
                moving_sheave_mass=0.0,
            ),
            secondary=SecondaryInertia(
                fixed_rotating_hardware_inertia=PUBLISHED.output_pulley_inertia_kg_m2,
                movable_sheave_rotational_inertia=0.0,
                moving_sheave_mass=0.0,
            ),
            belt=BeltMass(density=mapping.effective_density_kg_per_m3),
        ),
        belt_section=mapping.section,
        belt_outer_length=mapping.cinder_outer_length_m,
    )


def build_secondary_actuator() -> PulleyActuator:
    return PulleyActuator(ConstantAxialForce(PUBLISHED.output_axial_force_n))


def build_primary_replay_actuator(force_csv: str | Path) -> PulleyActuator:
    force = TabulatedAxialForce.from_csv(force_csv)
    if force.times_s[0] > 0.0 or force.times_s[-1] < PUBLISHED.simulation_duration_s:
        raise ValueError("Figure 45 force replay must cover the complete 0-5 s interval.")
    return PulleyActuator(force)


def build_ballew_assembly(*, primary_actuator: PulleyActuator) -> CVTAssemblySpec:
    mapping = build_equivalent_belt_mapping()
    return CVTAssemblySpec(
        geometry=build_ballew_geometry(mapping),
        pulleys=PulleyPairSpec(
            primary=PulleySpec(actuator=primary_actuator),
            secondary=PulleySpec(actuator=build_secondary_actuator()),
        ),
        inertias=build_ballew_inertias(mapping),
        contact=BeltContactSpec(
            static_friction_coefficient=CINDER_STATIC_TRACTION_LAMBDA_LIMIT,
            kinetic_friction_coefficient=CINDER_KINETIC_TRACTION_LAMBDA_MAGNITUDE,
        ),
    )


def build_initial_cvt_state(geometry: BeltPulleyGeometry) -> CVTState:
    shift = solve_initial_shift_from_published_speeds(geometry)
    position = geometry.evaluate(shift)
    omega_primary = PUBLISHED.initial_input_rpm * 2.0 * pi / 60.0
    omega_secondary = PUBLISHED.initial_output_rpm * 2.0 * pi / 60.0
    belt_speed_primary = omega_primary * position.primary.effective
    belt_speed_secondary = omega_secondary * position.secondary.effective
    if not isclose(belt_speed_primary, belt_speed_secondary, abs_tol=2.0e-10):
        raise RuntimeError("Initial geometry is inconsistent with the exact Ballew shaft speeds.")
    return CVTState(
        primary_angular_speed=omega_primary,
        secondary_angular_speed=omega_secondary,
        belt_speed=belt_speed_primary,
        shift_position=shift,
        shift_speed=0.0,
    )


def build_boundary_setup(*, host: CVTHost | None = None) -> BallewBoundarySetup:
    primary = FixedShaftBoundary(
        external_torque=PUBLISHED.engine_torque_nm,
        equivalent_inertia=PUBLISHED.input_pulley_and_engine_inertia_kg_m2,
    )
    final_drive = FixedFinalDrive(
        reduction_ratio=PUBLISHED.transmission_ratio,
        wheel_radius=PUBLISHED.tire_radius_m,
    )
    vehicle = VehicleInertia(mass=PUBLISHED.atv_mass_kg, wheel_rotational_inertia=0.0)
    road_load = RoadLoadModel(
        spec=VehicleRoadLoadSpec(
            rolling_resistance_coefficient=PUBLISHED.rolling_resistance_coefficient,
            drag_coefficient=PUBLISHED.aerodynamic_drag_coefficient,
            frontal_area=PUBLISHED.frontal_area_m2,
            air_density=RECONSTRUCTED_AIR_DENSITY_KG_PER_M3,
            gravity=RECONSTRUCTED_GRAVITY_M_PER_S2,
            rolling_speed_regularization=RECONSTRUCTED_ROLLING_SPEED_REGULARIZATION_M_PER_S,
        ),
        vehicle=vehicle,
        final_drive=final_drive,
    )
    secondary = LockedFinalDriveShaftBoundary(
        road_load=road_load,
        road_profile=ConstantGradeRoadProfile(),
        direct_secondary_shaft_inertia=DIRECT_SECONDARY_BOUNDARY_INERTIA_KG_M2,
    )
    return BallewBoundarySetup(
        primary=primary,
        secondary=secondary,
        host=host or SecondaryShaftAngleHost(),
        road_load=road_load,
    )
