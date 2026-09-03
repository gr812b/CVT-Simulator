"""CINDER 1.0.0 reconstruction of Ballew's simulated acceleration case."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, pi
from pathlib import Path

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
from cinder.model.cvt.inertia import (
    BeltMass,
    DrivetrainInertias,
    PrimaryInertia,
    ResolvedInertias,
    SecondaryInertia,
    resolve_inertias,
)

from .actuation import ConstantAxialForce, TabulatedAxialForce
from .belt import (
    BallewEquivalentBeltMapping,
    build_ballew_geometry,
    build_equivalent_belt_mapping,
    solve_initial_shift_from_published_speeds,
)
from .constants import (
    CINDER_KINETIC_TRACTION_LAMBDA_MAGNITUDE,
    CINDER_STATIC_TRACTION_LAMBDA_LIMIT,
    DIRECT_SECONDARY_BOUNDARY_INERTIA_KG_M2,
    PUBLISHED,
    RECONSTRUCTED_AIR_DENSITY_KG_PER_M3,
    RECONSTRUCTED_GRAVITY_M_PER_S2,
    RECONSTRUCTED_ROLLING_SPEED_REGULARIZATION_M_PER_S,
)


@dataclass(frozen=True, slots=True)
class BallewBoundarySetup:
    primary: FixedShaftBoundary
    secondary: LockedFinalDriveShaftBoundary
    host: CVTHost
    road_load: RoadLoadModel


def build_ballew_inertias(
    mapping: BallewEquivalentBeltMapping | None = None,
) -> ResolvedInertias:
    """Map Ballew's published inertias into CINDER ownership conventions."""

    mapping = mapping or build_equivalent_belt_mapping()
    return resolve_inertias(
        drivetrain=DrivetrainInertias(
            primary=PrimaryInertia(
                # The published 0.008 kg m^2 combines engine + input pulley and
                # is owned by the primary shaft boundary (Reconstruction A1).
                fixed_rotating_hardware_inertia=0.0,
                movable_sheave_rotational_inertia=0.0,
                moving_sheave_mass=0.0,
            ),
            secondary=SecondaryInertia(
                fixed_rotating_hardware_inertia=(
                    PUBLISHED.output_pulley_inertia_kg_m2
                ),
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
            # These are CINDER traction-lambda values after the documented A10
            # convention translation; they are not copied raw from Ballew.
            static_friction_coefficient=CINDER_STATIC_TRACTION_LAMBDA_LIMIT,
            kinetic_friction_coefficient=CINDER_KINETIC_TRACTION_LAMBDA_MAGNITUDE,
        ),
    )


def build_initial_cvt_state(geometry) -> CVTState:
    """Build the exact Table B1 rotational state and compatible belt state."""

    shift = solve_initial_shift_from_published_speeds(geometry)
    position = geometry.evaluate(shift)
    omega_primary = PUBLISHED.initial_input_rpm * 2.0 * pi / 60.0
    omega_secondary = PUBLISHED.initial_output_rpm * 2.0 * pi / 60.0
    belt_speed_primary = omega_primary * position.primary.effective
    belt_speed_secondary = omega_secondary * position.secondary.effective
    if not isclose(
        belt_speed_primary,
        belt_speed_secondary,
        rel_tol=0.0,
        abs_tol=2.0e-10,
    ):
        raise RuntimeError(
            "Initial geometry is inconsistent with the exact Ballew shaft speeds."
        )
    return CVTState(
        primary_angular_speed=omega_primary,
        secondary_angular_speed=omega_secondary,
        belt_speed=belt_speed_primary,
        shift_position=shift,
        shift_speed=0.0,
    )


def build_boundary_setup(*, host: CVTHost | None = None) -> BallewBoundarySetup:
    """Build the engine/input and reconstructed vehicle/output boundaries."""

    primary = FixedShaftBoundary(
        external_torque=PUBLISHED.engine_torque_nm,
        equivalent_inertia=PUBLISHED.input_pulley_and_engine_inertia_kg_m2,
    )
    final_drive = FixedFinalDrive(
        reduction_ratio=PUBLISHED.transmission_ratio,
        wheel_radius=PUBLISHED.tire_radius_m,
    )
    vehicle = VehicleInertia(
        mass=PUBLISHED.atv_mass_kg,
        wheel_rotational_inertia=0.0,
    )
    road_load = RoadLoadModel(
        spec=VehicleRoadLoadSpec(
            rolling_resistance_coefficient=PUBLISHED.rolling_resistance_coefficient,
            drag_coefficient=PUBLISHED.aerodynamic_drag_coefficient,
            frontal_area=PUBLISHED.frontal_area_m2,
            air_density=RECONSTRUCTED_AIR_DENSITY_KG_PER_M3,
            gravity=RECONSTRUCTED_GRAVITY_M_PER_S2,
            rolling_speed_regularization=(
                RECONSTRUCTED_ROLLING_SPEED_REGULARIZATION_M_PER_S
            ),
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
