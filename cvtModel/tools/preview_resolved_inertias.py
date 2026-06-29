"""Print CINDER's fixed and shift-position-dependent inertia quantities.

Place this file in cvtModel/tools/ and run from cvtModel/ with:

    PYTHONPATH=src python tools/preview_resolved_inertias.py

The values below are illustrative SI inputs. Replace the constants in
build_demo_system() with the measured values for the CVT being studied.
"""

from __future__ import annotations

from cinder.geometry import BeltPulleyGeometry, BeltPulleyGeometrySpec, BeltSectionSpec
from cinder.inertia import (
    BeltMass,
    DrivetrainInertias,
    PrimaryInertia,
    SecondaryInertia,
    VehicleInertia,
    resolve_inertias,
)
from cinder.vehicle import FixedFinalDrive

INCH = 0.0254


def build_demo_system() -> tuple[BeltPulleyGeometry, object]:
    """Construct one complete geometry + resolved-inertia example."""
    belt_section = BeltSectionSpec(
        height=0.613 * INCH,
        outer_width=0.840 * INCH,
        inner_width=0.662 * INCH,
        cord_depth_from_outer=0.0040,
    )

    geometry = BeltPulleyGeometry(
        BeltPulleyGeometrySpec(
            belt=belt_section,
            belt_outer_length=37.53 * INCH,
            primary_outer_radius_at_zero_shift=0.040,
            secondary_outer_radius_at_zero_shift=0.080,
            sheave_half_angle=15.0 * 3.141592653589793 / 180.0,
            deadzone_shift=0.004,
            max_shift=0.012,
        )
    )

    drivetrain = DrivetrainInertias(
        primary=PrimaryInertia(
            engine_rotational_inertia=0.0150,
            cvt_rotational_inertia=0.0850,
            moving_sheave_mass=1.068,
        ),
        secondary=SecondaryInertia(
            fixed_rotational_inertia=0.1000,
            gearbox_input_rotational_inertia=0.0200,
            movable_sheave_rotational_inertia=0.002514,
            moving_sheave_mass=0.705,
        ),
        belt=BeltMass(density=1100.0),
    )

    vehicle = VehicleInertia(
        mass=281.0,
        wheel_rotational_inertia=0.400,
    )
    final_drive = FixedFinalDrive(
        reduction_ratio=7.556,
        wheel_radius=0.2794,
    )

    inertias = resolve_inertias(
        drivetrain=drivetrain,
        vehicle=vehicle,
        final_drive=final_drive,
        belt_section=belt_section,
        belt_outer_length=geometry.spec.belt_outer_length,
    )
    return geometry, inertias


def print_fixed_inertias(inertias: object) -> None:
    """Print terms that are constant for the whole simulation."""
    primary = inertias.primary
    secondary = inertias.secondary
    fixed = secondary.fixed_side
    belt = inertias.belt
    shift_masses = inertias.shift

    print("\nFIXED ROTATIONAL INERTIAS [kg m^2]")
    print(f"  primary engine inertia                 {primary.engine_rotational_inertia: .8f}")
    print(f"  primary CVT inertia                    {primary.cvt_rotational_inertia: .8f}")
    print(f"  I_p = engine + primary CVT             {primary.rotational_inertia: .8f}")
    print(f"  secondary fixed-sheave inertia         {fixed.secondary_fixed_rotational_inertia: .8f}")
    print(f"  gearbox input inertia                  {fixed.gearbox_input_rotational_inertia: .8f}")
    print(f"  driven-wheel inertia @ secondary       {fixed.driven_wheel_rotational_inertia: .8f}")
    print(f"  vehicle translation @ secondary        {fixed.vehicle_translational_inertia: .8f}")
    print(f"  I_s,F = fixed secondary-side total     {fixed.total: .8f}")
    print(f"  movable secondary sheave I_M           {secondary.movable_sheave_rotational_inertia: .8f}")
    print(f"  I_s,F + I_M                            {secondary.absolute_rotation_inertia: .8f}")

    print("\nFIXED BELT / TRANSLATING MASSES [kg]")
    print(f"  belt cross-sectional area              {belt.cross_sectional_area: .8e}")
    print(f"  belt outer length                      {belt.outer_length: .8f}")
    print(f"  belt mass m_b                          {belt.mass: .8f}")
    print(f"  primary movable-sheave mass            {shift_masses.primary_moving_sheave_mass: .8f}")
    print(f"  secondary movable-sheave mass          {shift_masses.secondary_moving_sheave_mass: .8f}")


def print_at_shift(*, label: str, geometry: BeltPulleyGeometry, inertias: object, shift: float) -> None:
    """Print geometry-coordinates and generalized translation inertia at one s."""
    position = geometry.evaluate(shift)
    translation = inertias.shift.evaluate(
        primary_axial_coordinate=position.primary_axial_coordinate,
        secondary_axial_coordinate=position.secondary_axial_coordinate,
        belt_axial_coordinate=position.belt_axial_coordinate,
    )

    def fmt_coordinate(name: str, coordinate: object) -> None:
        print(
            f"  {name:<10} x={coordinate.value: .8f} m"
            f"  x'={coordinate.d_value_ds: .8f}"
            f"  x''={coordinate.d2_value_ds2: .8f} 1/m"
        )

    print(f"\n{label}: s = {shift:.8f} m")
    print("  axial coordinates")
    fmt_coordinate("primary", position.primary_axial_coordinate)
    fmt_coordinate("secondary", position.secondary_axial_coordinate)
    fmt_coordinate("belt", position.belt_axial_coordinate)

    print("  translation-inertia contributions [kg]")
    print(f"  primary movable sheave                {translation.primary_moving_sheave_contribution: .8f}")
    print(f"  secondary movable sheave              {translation.secondary_moving_sheave_contribution: .8f}")
    print(f"  belt representative axial motion      {translation.belt_contribution: .8f}")
    print(f"  M_trans(s)                            {translation.mass: .8f}")
    print(f"  C_trans(s)                            {translation.coordinate_curvature_coefficient: .8f} kg/m")

    print("  selected belt geometry")
    print(f"  r_p,eff                               {position.primary.effective: .8f} m")
    print(f"  r_s,eff                               {position.secondary.effective: .8f} m")
    print(f"  phi_p                                 {position.primary_wrap_angle: .8f} rad")
    print(f"  phi_s                                 {position.secondary_wrap_angle: .8f} rad")


def main() -> None:
    geometry, inertias = build_demo_system()
    deadzone = geometry.spec.deadzone_shift
    max_shift = geometry.spec.max_shift

    print_fixed_inertias(inertias)
    print_at_shift(
        label="DEADZONE",
        geometry=geometry,
        inertias=inertias,
        shift=0.5 * deadzone,
    )
    print_at_shift(
        label="JUST ACTIVE",
        geometry=geometry,
        inertias=inertias,
        shift=deadzone + 1.0e-6,
    )
    print_at_shift(
        label="MAX SHIFT",
        geometry=geometry,
        inertias=inertias,
        shift=max_shift,
    )


if __name__ == "__main__":
    main()
