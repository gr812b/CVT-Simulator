# cvtModel/tools/preview_actuation_forces.py
"""
Preview the signed net local axial force of the default CINDER primary and
secondary actuator assemblies.

Run from cvtModel/:

    python tools/preview_actuation_forces.py

Optional plot-range controls:

    python tools/preview_actuation_forces.py \
        --primary-rpm-max 8000 \
        --secondary-torque-min -30 \
        --secondary-torque-max 80

    python tools/preview_actuation_forces.py \
        --primary-travel-mm 19.05 \
        --secondary-travel-mm 19.05 \
        --samples 121

    python tools/preview_actuation_forces.py \
        --save artifacts/actuation_forces.png \
        --no-show

Important coordinate note
-------------------------
The primary uses x_p = s, so its horizontal axis is the global shift
coordinate directly.

The secondary plot uses its own local closing coordinate x_s. It is not yet
the global s coordinate because the secondary coordinate adapter x_s(s) has
not been implemented. Once that adapter exists, the same force law can be
sampled against global s without changing the actuator itself.

Sign convention
---------------
Positive force closes/clamps the pulley.
Negative force opens the pulley.

The numbers in PreviewParameters are deliberately collected in one place.
They are editable example hardware values, not claimed CINDER defaults.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from math import pi
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm

from cinder.actuation.forces import (
    AxialSpringForceSpec,
    CentrifugalRampForceSpec,
    HelixTorqueReactionForceSpec,
    TorsionalSpringForceSpec,
)
from cinder.actuation.primary import (
    CentrifugalPrimarySpec,
    build_centrifugal_primary,
)
from cinder.actuation.secondary import (
    TorqueReactiveSecondarySpec,
    build_torque_reactive_secondary,
)
from cinder.actuation.types import PulleyActuationState
from cinder.profiles import (
    HelixProfile,
    LinearSegment,
    PiecewiseRamp,
    linear_helix_segment,
)


@dataclass(frozen=True, slots=True)
class PreviewParameters:
    """
    Editable example mechanism values.

    Keep all units SI:
        length [m]
        mass [kg]
        stiffness [N/m]
        torsional stiffness [N m/rad]
        torque [N m]
        angle [deg]
    """

    primary_travel: float = 0.01905
    secondary_travel: float = 0.01905

    # Primary: conventional centrifugal ramp plus an opening return spring.
    primary_flyweight_mass: float = 0.120
    primary_flyweight_radius_at_zero: float = 0.035
    primary_ramp_angle_degrees: float = 30.0
    primary_spring_stiffness: float = 25_000.0
    primary_initial_spring_compression: float = 0.004

    # Secondary: closing axial and torsional springs plus torque reaction.
    secondary_axial_spring_stiffness: float = 25_000.0
    secondary_initial_spring_compression: float = 0.025

    secondary_helix_radius: float = 0.030
    secondary_helix_angle_degrees: float = 28.0
    secondary_helix_handedness: int = 1

    secondary_torsional_stiffness: float = 8.0
    secondary_initial_twist: float = 1.40
    secondary_twist_per_helix_rotation: float = -1.0

    # With the selected helix handedness, +1 makes positive tau_s add closing
    # force. Change this only when matching a different torque convention or
    # mechanical hand.
    secondary_torque_to_helix_sign: int = 1


DEFAULT_PARAMETERS = PreviewParameters()


def radians_per_second_from_rpm(rpm: np.ndarray | float) -> np.ndarray | float:
    return np.asarray(rpm) * 2.0 * pi / 60.0


def build_primary(parameters: PreviewParameters):
    radial_profile = PiecewiseRamp(
        (
            LinearSegment(
                length=parameters.primary_travel,
                angle_degrees=parameters.primary_ramp_angle_degrees,
            ),
        )
    )

    return build_centrifugal_primary(
        CentrifugalPrimarySpec(
            centrifugal_ramp=CentrifugalRampForceSpec(
                flyweight_mass=parameters.primary_flyweight_mass,
                radius_at_zero_position=(
                    parameters.primary_flyweight_radius_at_zero
                ),
                radial_displacement_profile=radial_profile,
            ),
            axial_spring=AxialSpringForceSpec(
                stiffness=parameters.primary_spring_stiffness,
                initial_compression=(
                    parameters.primary_initial_spring_compression
                ),
                compression_per_axial_position=1.0,
            ),
        )
    )


def build_secondary(parameters: PreviewParameters):
    helix_profile = HelixProfile(
        circumferential_profile=PiecewiseRamp(
            (
                linear_helix_segment(
                    length=parameters.secondary_travel,
                    helix_angle_degrees=(
                        parameters.secondary_helix_angle_degrees
                    ),
                    handedness=parameters.secondary_helix_handedness,
                ),
            )
        ),
        radius=parameters.secondary_helix_radius,
    )

    return build_torque_reactive_secondary(
        TorqueReactiveSecondarySpec(
            torque_reaction=HelixTorqueReactionForceSpec(
                helix_profile=helix_profile,
                torque_to_helix_sign=(
                    parameters.secondary_torque_to_helix_sign
                ),
            ),
            axial_spring=AxialSpringForceSpec(
                stiffness=parameters.secondary_axial_spring_stiffness,
                initial_compression=(
                    parameters.secondary_initial_spring_compression
                ),
                compression_per_axial_position=-1.0,
            ),
            torsional_spring=TorsionalSpringForceSpec(
                torsional_stiffness=(
                    parameters.secondary_torsional_stiffness
                ),
                initial_twist=parameters.secondary_initial_twist,
                twist_per_helix_rotation=(
                    parameters.secondary_twist_per_helix_rotation
                ),
                helix_profile=helix_profile,
            ),
        )
    )


def evaluate_local_force(
    actuator,
    *,
    axial_position: float,
    shaft_speed_rpm: float,
    pulley_torque: float,
) -> float:
    relation = actuator.evaluate(
        PulleyActuationState(
            axial_position=axial_position,
            axial_speed=0.0,
            shaft_speed=float(radians_per_second_from_rpm(shaft_speed_rpm)),
        )
    )
    return relation.force_at_torque(pulley_torque)


def force_surface(
    actuator,
    *,
    positions: np.ndarray,
    varying_values: np.ndarray,
    shaft_speed_from_value,
    torque_from_value,
) -> np.ndarray:
    """
    Evaluate net local axial force over one actuator-position grid.

    Rows correspond to ``varying_values``; columns correspond to positions.
    """

    surface = np.empty((varying_values.size, positions.size))

    for row, varying_value in enumerate(varying_values):
        shaft_speed_rpm = shaft_speed_from_value(float(varying_value))
        pulley_torque = torque_from_value(float(varying_value))

        for column, axial_position in enumerate(positions):
            surface[row, column] = evaluate_local_force(
                actuator,
                axial_position=float(axial_position),
                shaft_speed_rpm=shaft_speed_rpm,
                pulley_torque=pulley_torque,
            )

    return surface


def signed_norm(values: np.ndarray) -> TwoSlopeNorm:
    largest_magnitude = max(float(np.max(np.abs(values))), 1.0)
    return TwoSlopeNorm(
        vmin=-largest_magnitude,
        vcenter=0.0,
        vmax=largest_magnitude,
    )


def add_zero_contour(
    axis,
    *,
    positions_mm: np.ndarray,
    varying_values: np.ndarray,
    forces: np.ndarray,
) -> None:
    if float(np.min(forces)) <= 0.0 <= float(np.max(forces)):
        axis.contour(
            positions_mm,
            varying_values,
            forces,
            levels=(0.0,),
            linewidths=1.3,
        )


def plot_surface(
    axis,
    *,
    positions_mm: np.ndarray,
    varying_values: np.ndarray,
    forces: np.ndarray,
    title: str,
    x_label: str,
    y_label: str,
):
    mesh = axis.pcolormesh(
        positions_mm,
        varying_values,
        forces,
        shading="auto",
        cmap="coolwarm",
        norm=signed_norm(forces),
    )
    add_zero_contour(
        axis,
        positions_mm=positions_mm,
        varying_values=varying_values,
        forces=forces,
    )

    axis.set_title(title)
    axis.set_xlabel(x_label)
    axis.set_ylabel(y_label)
    axis.grid(True, alpha=0.25)

    colorbar = axis.figure.colorbar(mesh, ax=axis)
    colorbar.set_label("Net local axial force [N]\n(closing +, opening −)")


def plot_slices(
    axis,
    *,
    actuator,
    axial_positions: tuple[float, ...],
    varying_values: np.ndarray,
    shaft_speed_from_value,
    torque_from_value,
    title: str,
    x_label: str,
    position_label: str,
):
    """
    Plot force against the actuator's main varying input at several fixed
    local axial positions.

    For the primary: x-axis is shaft speed, with one line per shift s.
    For the secondary: x-axis is transmitted torque, with one line per
    local closing coordinate x_s.
    """

    for axial_position in axial_positions:
        force_values = [
            evaluate_local_force(
                actuator,
                axial_position=axial_position,
                shaft_speed_rpm=shaft_speed_from_value(float(varying_value)),
                pulley_torque=torque_from_value(float(varying_value)),
            )
            for varying_value in varying_values
        ]

        axis.plot(
            varying_values,
            force_values,
            label=(
                f"{position_label} = {axial_position * 1_000.0:.2f} mm"
            ),
        )

    axis.axhline(0.0, linewidth=1.0)
    axis.set_title(title)
    axis.set_xlabel(x_label)
    axis.set_ylabel("Net local axial force [N]")
    axis.grid(True, alpha=0.3)
    axis.legend()

def plot_force_maps(
    *,
    parameters: PreviewParameters,
    primary_rpm_max: float,
    secondary_torque_min: float,
    secondary_torque_max: float,
    samples: int,
):
    primary = build_primary(parameters)
    secondary = build_secondary(parameters)

    primary_positions = np.linspace(
        0.0,
        parameters.primary_travel,
        samples,
    )
    secondary_positions = np.linspace(
        0.0,
        parameters.secondary_travel,
        samples,
    )

    primary_rpm = np.linspace(0.0, primary_rpm_max, samples)
    secondary_torque = np.linspace(
        secondary_torque_min,
        secondary_torque_max,
        samples,
    )

    primary_surface = force_surface(
        primary,
        positions=primary_positions,
        varying_values=primary_rpm,
        shaft_speed_from_value=lambda rpm: rpm,
        torque_from_value=lambda _: 0.0,
    )
    secondary_surface = force_surface(
        secondary,
        positions=secondary_positions,
        varying_values=secondary_torque,
        shaft_speed_from_value=lambda _: 0.0,
        torque_from_value=lambda torque: torque,
    )

    figure, axes = plt.subplots(
        2,
        2,
        figsize=(17, 11),
        constrained_layout=True,
        height_ratios=(1.15, 0.85),
    )

    plot_surface(
        axes[0, 0],
        positions_mm=primary_positions * 1_000.0,
        varying_values=primary_rpm,
        forces=primary_surface,
        title="Primary: net force over shift and shaft speed",
        x_label=r"Primary local coordinate $x_p=s$ [mm]",
        y_label="Primary speed [rpm]",
    )
    plot_surface(
        axes[0, 1],
        positions_mm=secondary_positions * 1_000.0,
        varying_values=secondary_torque,
        forces=secondary_surface,
        title="Secondary: net force over local closure and torque",
        x_label=r"Secondary local coordinate $x_s$ [mm]",
        y_label=r"Secondary torque $\tau_s$ [N m]",
    )

    primary_slice_positions = tuple(
        np.linspace(
            primary_positions[0],
            primary_positions[-1],
            4,
        )
    )
    secondary_slice_positions = tuple(
        np.linspace(
            secondary_positions[0],
            secondary_positions[-1],
            4,
        )
    )

    plot_slices(
        axes[1, 0],
        actuator=primary,
        axial_positions=primary_slice_positions,
        varying_values=primary_rpm,
        shaft_speed_from_value=lambda rpm: rpm,
        torque_from_value=lambda _: 0.0,
        title="Primary: force versus shaft speed",
        x_label="Primary speed [rpm]",
        position_label=r"$s$",
    )
    plot_slices(
        axes[1, 1],
        actuator=secondary,
        axial_positions=secondary_slice_positions,
        varying_values=secondary_torque,
        shaft_speed_from_value=lambda _: 0.0,
        torque_from_value=lambda torque: torque,
        title="Secondary: force versus transmitted torque",
        x_label=r"Secondary torque $\tau_s$ [N m]",
        position_label=r"$x_s$",
    )

    figure.suptitle(
        "CINDER actuator preview: signed local force "
        "(positive = pulley closing)"
    )

    return figure, primary_surface, secondary_surface


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot net signed local force of the default CINDER primary and "
            "secondary actuator assemblies."
        )
    )

    parser.add_argument(
        "--primary-rpm-max",
        type=float,
        default=8_000.0,
        help="Maximum primary shaft speed shown [rpm].",
    )
    parser.add_argument(
        "--secondary-torque-min",
        type=float,
        default=-30.0,
        help="Minimum signed secondary torque shown [N m].",
    )
    parser.add_argument(
        "--secondary-torque-max",
        type=float,
        default=80.0,
        help="Maximum signed secondary torque shown [N m].",
    )
    parser.add_argument(
        "--primary-travel-mm",
        type=float,
        default=DEFAULT_PARAMETERS.primary_travel * 1_000.0,
        help="Primary local travel used for this preview [mm].",
    )
    parser.add_argument(
        "--secondary-travel-mm",
        type=float,
        default=DEFAULT_PARAMETERS.secondary_travel * 1_000.0,
        help="Secondary local travel used for this preview [mm].",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=121,
        help="Number of samples along each plotted axis.",
    )
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        help="Optional output image path.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Build and optionally save the figure without opening a window.",
    )

    args = parser.parse_args()

    if args.primary_rpm_max <= 0.0:
        parser.error("--primary-rpm-max must be positive.")

    if args.secondary_torque_min >= args.secondary_torque_max:
        parser.error(
            "--secondary-torque-min must be smaller than "
            "--secondary-torque-max."
        )

    if args.primary_travel_mm <= 0.0:
        parser.error("--primary-travel-mm must be positive.")

    if args.secondary_travel_mm <= 0.0:
        parser.error("--secondary-travel-mm must be positive.")

    if args.samples < 3:
        parser.error("--samples must be at least 3.")

    return args


def main() -> None:
    args = parse_args()

    parameters = replace(
        DEFAULT_PARAMETERS,
        primary_travel=args.primary_travel_mm / 1_000.0,
        secondary_travel=args.secondary_travel_mm / 1_000.0,
    )

    figure, primary_surface, secondary_surface = plot_force_maps(
        parameters=parameters,
        primary_rpm_max=args.primary_rpm_max,
        secondary_torque_min=args.secondary_torque_min,
        secondary_torque_max=args.secondary_torque_max,
        samples=args.samples,
    )

    print("Preview parameters")
    print(
        f"  primary travel:   {parameters.primary_travel * 1_000.0:.3f} mm"
    )
    print(
        f"  secondary travel: {parameters.secondary_travel * 1_000.0:.3f} mm"
    )
    print(
        "  primary force range: "
        f"[{primary_surface.min():.1f}, {primary_surface.max():.1f}] N"
    )
    print(
        "  secondary force range: "
        f"[{secondary_surface.min():.1f}, {secondary_surface.max():.1f}] N"
    )
    print("  positive force closes the corresponding pulley.")

    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180)
        print(f"Saved {args.save}")

    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
