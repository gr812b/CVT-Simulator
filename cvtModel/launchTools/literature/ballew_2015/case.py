"""CINDER reconstruction of Ballew's simulated vehicle-acceleration case."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, pi
from pathlib import Path

from cinder.hosts import CVTHost, SecondaryShaftAngleHost
from cinder.model.boundaries.shaft import (
    FixedShaftBoundary,
    LockedFinalDriveShaftBoundary,
)
from cinder.model.boundaries.vehicle import (
    ConstantGradeRoadProfile,
    FixedFinalDrive,
    RoadLoadModel,
    VehicleInertia,
    VehicleRoadLoadSpec,
)
from cinder.model.cvt.actuation import PulleyActuator
from cinder.model.cvt.inertia import (
    BeltMass,
    DrivetrainInertias,
    PrimaryInertia,
    ResolvedInertias,
    SecondaryInertia,
    resolve_inertias,
)
from cinder.model.system import (
    BeltContactSpec,
    CVTAssemblySpec,
    CVTState,
    PulleyPairSpec,
    PulleySpec,
)

from actuation import ConstantAxialForce, TabulatedAxialForce
from belt import (
    BallewEquivalentBeltMapping,
    build_ballew_geometry,
    build_equivalent_belt_mapping,
    solve_initial_shift_from_published_speeds,
)
from constants import (
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
    """Published shaft forcing plus reconstructed simulated-vehicle boundary."""

    primary: FixedShaftBoundary
    secondary: LockedFinalDriveShaftBoundary
    host: CVTHost
    road_load: RoadLoadModel


def build_secondary_actuator() -> PulleyActuator:
    """Build Ballew's published constant 2000 N output closing-force input."""

    return PulleyActuator(ConstantAxialForce(PUBLISHED.output_axial_force_n))


def build_primary_replay_actuator(force_csv: str | Path) -> PulleyActuator:
    """Build the Figure 45 primary-force replay actuator.

    Reconstruction A6 defines the digitized force history as a piecewise-linear
    boundary input rather than a reconstruction of Ballew's controller.
    """

    force = TabulatedAxialForce.from_csv(force_csv)
    if force.times_s[0] > 0.0 or force.times_s[-1] < PUBLISHED.simulation_duration_s:
        raise ValueError(
            "Figure 45 force replay must cover the complete 0-5 s benchmark interval."
        )
    return PulleyActuator(force)


def build_ballew_inertias(
    mapping: BallewEquivalentBeltMapping | None = None,
) -> ResolvedInertias:
    """Build the CVT-owned inertia set faithful to Ballew's model structure."""

    mapping = mapping or build_equivalent_belt_mapping()

    # Reconstruction A5: Ballew has no movable-sheave axial EOM. His numerical
    # search enforces applied clamp force against the summed belt reaction
    # algebraically. Setting both literal moving-sheave masses to zero makes
    # CINDER's local primary/secondary axial rows the corresponding algebraic
    # clamp balances. No special dynamics mode is needed.
    #
    # The full 0.008 kg m^2 input-pulley + engine inertia remains at the primary
    # shaft boundary (A1), so no part of it is duplicated in the CVT core. The
    # published 0.002 kg m^2 output-pulley inertia stays in the CVT core.
    return resolve_inertias(
        drivetrain=DrivetrainInertias(
            primary=PrimaryInertia(
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
            # Reconstruction A4: this density is an effective mass-preserving
            # parameter for the equivalent smooth section, not a physical
            # material density of the cogged belt.
            belt=BeltMass(density=mapping.effective_density_kg_per_m3),
        ),
        belt_section=mapping.section,
        belt_outer_length=mapping.cinder_outer_length_m,
    )


def build_ballew_assembly(
    *, primary_actuator: PulleyActuator
) -> tuple[CVTAssemblySpec, BallewEquivalentBeltMapping]:
    """Build the complete CVT assembly once a Figure 45 replay is available."""

    mapping = build_equivalent_belt_mapping()
    geometry = build_ballew_geometry(mapping)
    inertias = build_ballew_inertias(mapping)

    assembly = CVTAssemblySpec(
        geometry=geometry,
        pulleys=PulleyPairSpec(
            # Reconstruction A5: neither pulley has a helical coupling in this
            # benchmark. Both actuators apply known local axial closing force.
            primary=PulleySpec(actuator=primary_actuator),
            secondary=PulleySpec(actuator=build_secondary_actuator()),
        ),
        inertias=inertias,
        contact=BeltContactSpec(
            # Reconstruction A10: these fields feed CINDER's reduced lambda
            # traction limits. Ballew's published 0.55/0.40 multiply node F_Z
            # directly, so the benchmark translates them before construction.
            static_friction_coefficient=CINDER_STATIC_TRACTION_LAMBDA_LIMIT,
            kinetic_friction_coefficient=CINDER_KINETIC_TRACTION_LAMBDA_MAGNITUDE,
        ),
    )
    return assembly, mapping


def build_initial_cvt_state(geometry=None) -> CVTState:
    """Build CINDER's initial state from Ballew's explicitly tabulated RPMs."""

    if geometry is None:
        geometry = build_ballew_geometry()

    # Reconstruction A3: use the two exact Table B1 shaft speeds. The separately
    # listed ratio 2.2 is treated as a rounded description, not as an additional
    # exact constraint.
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
            "Ballew initial geometry is not consistent with the published shaft speeds."
        )

    # Ballew places the initial node velocities along the initialized belt path;
    # there is no separate sheave-velocity state. CINDER therefore starts from
    # zero ratio-change rate while preserving the exact no-slip belt-line speed.
    # See A3/A5.
    return CVTState(
        primary_angular_speed=omega_primary,
        secondary_angular_speed=omega_secondary,
        belt_speed=belt_speed_primary,
        shift_position=shift,
        shift_speed=0.0,
    )


def build_boundary_setup(*, host: CVTHost | None = None) -> BallewBoundarySetup:
    """Build Ballew's fixed input torque and simulated ATV output boundary."""

    # Reconstruction A1: the combined 0.008 kg m^2 input pulley + engine inertia
    # is kept on the primary boundary because Ballew does not publish a split.
    primary = FixedShaftBoundary(
        external_torque=PUBLISHED.engine_torque_nm,
        equivalent_inertia=PUBLISHED.input_pulley_and_engine_inertia_kg_m2,
    )

    # Ballew does not prescribe a fixed output/brake torque in this case.
    # Reconstruction A9 treats Table A1's generic "Transmission Ratio" as the
    # fixed CVT-output-to-wheel reduction used by the simulated ATV load.
    # See RECONSTRUCTION.md.
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
            # Reconstruction A2: air density is not reported by Ballew.
            # See RECONSTRUCTION.md.
            air_density=RECONSTRUCTED_AIR_DENSITY_KG_PER_M3,
            # Reconstruction A2: these are explicit rather than inherited
            # from CINDER defaults. See RECONSTRUCTION.md.
            gravity=RECONSTRUCTED_GRAVITY_M_PER_S2,
            rolling_speed_regularization=(
                RECONSTRUCTED_ROLLING_SPEED_REGULARIZATION_M_PER_S
            ),
        ),
        vehicle=vehicle,
        final_drive=final_drive,
    )

    # The secondary resistance remains vehicle-generated, not a fixed torque.
    # Reconstruction A1: preserve Ballew's stated 1.275 kg m^2 total output
    # pulley + ATV inertia after CINDER separately carries the 0.002 kg m^2
    # output pulley inertia. See RECONSTRUCTION.md.
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
