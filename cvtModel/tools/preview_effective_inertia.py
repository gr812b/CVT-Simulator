"""Plot stationary-shift rotational inertia referred to the primary shaft.

This diagnostic keeps the CVT at a fixed ratio, zero shift speed, and no
slip. The actual solver retains primary rotation, secondary rotation, belt
transport, and shift as separate coordinates.

Shift translation is intentionally not printed here: it is evaluated from
the current GeometryPosition inside the RHS, not resolved as a constant.
"""

from __future__ import annotations

import argparse

import matplotlib.pyplot as plt
import numpy as np

from cinder.geometry.spec import BeltSectionSpec
from cinder.inertia import (
    BeltMass,
    DrivetrainInertias,
    PrimaryInertia,
    SecondaryInertia,
    VehicleInertia,
    resolve_inertias,
)
from cinder.vehicle import FixedFinalDrive


# Illustrative SI values. Replace with measured component values.
_INERTIAS = DrivetrainInertias(
    primary=PrimaryInertia(
        engine_rotational_inertia=0.015,
        cvt_rotational_inertia=0.085,
        moving_sheave_mass=1.068,
    ),
    secondary=SecondaryInertia(
        fixed_rotational_inertia=0.100,
        gearbox_input_rotational_inertia=0.020,
        movable_sheave_rotational_inertia=0.002514,
        moving_sheave_mass=0.705,
    ),
    belt=BeltMass(density=1100.0),
)

_VEHICLE = VehicleInertia(
    mass=281.0,
    wheel_rotational_inertia=0.400,
)

_FINAL_DRIVE = FixedFinalDrive(
    reduction_ratio=7.556,
    wheel_radius=0.2794,
)

_BELT_SECTION = BeltSectionSpec(
    height=0.613 * 0.0254,
    outer_width=0.840 * 0.0254,
    inner_width=0.662 * 0.0254,
    cord_depth_from_outer=0.004,
)
_BELT_OUTER_LENGTH = 37.53 * 0.0254


def main() -> None:
    arguments = _parse_arguments()

    inertias = resolve_inertias(
        drivetrain=_INERTIAS,
        vehicle=_VEHICLE,
        final_drive=_FINAL_DRIVE,
        belt_section=_BELT_SECTION,
        belt_outer_length=_BELT_OUTER_LENGTH,
    )

    ratios = np.linspace(
        arguments.maximum_ratio,
        arguments.minimum_ratio,
        600,
    )

    primary_rotating = np.full_like(
        ratios,
        inertias.primary.rotational_inertia,
    )
    belt_transport = np.full_like(
        ratios,
        inertias.belt.mass * arguments.primary_effective_radius**2,
    )

    secondary_fixed = (
        inertias.secondary.fixed_side.total / ratios**2
    )
    secondary_movable = (
        inertias.secondary.movable_sheave_rotational_inertia / ratios**2
    )
    secondary_rotating = secondary_fixed + secondary_movable

    total = primary_rotating + belt_transport + secondary_rotating

    _print_rotational_breakdown(
        inertias=inertias,
        sample_ratios=_sample_ratios(
            maximum_ratio=arguments.maximum_ratio,
            minimum_ratio=arguments.minimum_ratio,
        ),
        primary_effective_radius=arguments.primary_effective_radius,
    )

    figure, axis = plt.subplots()
    axis.plot(
        ratios,
        primary_rotating,
        label="Primary rotating (engine + primary CVT)",
    )
    axis.plot(ratios, belt_transport, label="Belt transport")
    axis.plot(
        ratios,
        secondary_rotating,
        label="Secondary rotating (all secondary-side parts)",
    )
    axis.plot(ratios, total, linewidth=2.0, label="Total")

    axis.set_xlabel(r"CVT ratio $R = \omega_p / \omega_s$")
    axis.set_ylabel(r"Primary-equivalent inertia [kg m$^2$]")
    axis.set_title("Stationary-shift inertia referred to the primary")
    axis.grid(True, alpha=0.3)
    axis.legend()
    figure.tight_layout()
    plt.show()


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--minimum-ratio",
        type=float,
        default=0.5,
    )
    parser.add_argument(
        "--maximum-ratio",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--primary-effective-radius",
        type=float,
        default=0.050,
        help="Representative primary effective radius [m] for belt transport.",
    )
    arguments = parser.parse_args()

    if arguments.minimum_ratio <= 0.0:
        raise ValueError("minimum_ratio must be positive.")

    if arguments.maximum_ratio <= arguments.minimum_ratio:
        raise ValueError("maximum_ratio must exceed minimum_ratio.")

    if arguments.primary_effective_radius <= 0.0:
        raise ValueError("primary_effective_radius must be positive.")

    return arguments


def _sample_ratios(
    *,
    maximum_ratio: float,
    minimum_ratio: float,
) -> tuple[float, ...]:
    candidates = (maximum_ratio, 1.0, minimum_ratio)
    return tuple(
        ratio
        for index, ratio in enumerate(candidates)
        if minimum_ratio <= ratio <= maximum_ratio
        and ratio not in candidates[:index]
    )


def _print_rotational_breakdown(
    *,
    inertias,
    sample_ratios: tuple[float, ...],
    primary_effective_radius: float,
) -> None:
    belt_transport = inertias.belt.mass * primary_effective_radius**2
    fixed = inertias.secondary.fixed_side

    print("\nPrimary-equivalent stationary-shift inertia [kg m^2]")
    print(
        " ratio | engine | primary CVT | belt | secondary fixed | gearbox | "
        "vehicle | wheels | secondary movable | total"
    )
    print("-" * 131)

    for ratio in sample_ratios:
        scale = 1.0 / ratio**2

        engine = inertias.primary.engine_rotational_inertia
        primary_cvt = inertias.primary.cvt_rotational_inertia
        secondary_fixed = fixed.secondary_fixed_rotational_inertia * scale
        gearbox = fixed.gearbox_input_rotational_inertia * scale
        vehicle = fixed.vehicle_translational_inertia * scale
        wheels = fixed.driven_wheel_rotational_inertia * scale
        secondary_movable = (
            inertias.secondary.movable_sheave_rotational_inertia * scale
        )
        total = (
            engine
            + primary_cvt
            + belt_transport
            + secondary_fixed
            + gearbox
            + vehicle
            + wheels
            + secondary_movable
        )

        print(
            f"{ratio:6.2f} | "
            f"{engine:6.4f} | "
            f"{primary_cvt:11.4f} | "
            f"{belt_transport:5.4f} | "
            f"{secondary_fixed:15.4f} | "
            f"{gearbox:7.4f} | "
            f"{vehicle:7.4f} | "
            f"{wheels:6.4f} | "
            f"{secondary_movable:17.4f} | "
            f"{total:6.4f}"
        )


if __name__ == "__main__":
    main()
