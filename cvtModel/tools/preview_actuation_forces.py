"""Preview signed local axial forces of CINDER's default actuator assemblies.

Run from the cvtModel directory:

    PYTHONPATH=src python tools/preview_actuation_forces.py

The primary map varies primary shift s and shaft RPM. The secondary map
varies the physical secondary closing coordinate x_s and transmitted torque
tau_s. The secondary relation is affine in tau_s, alpha_s, and s_ddot. The known
shift-speed and acceleration values are selected command-line slices so the
original force-map layout remains readable.

Positive local force closes/clamps the relevant pulley; negative force opens it.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from math import pi
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm

from cinder.actuation.forces import (
    AxialSpringForceSpec,
    CentrifugalRampForceSpec,
    SecondaryHelixActuationState,
    SecondaryHelixForceSpec,
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
from cinder.closure import ClosureUnknowns
from cinder.profiles.helix import HelixProfile, linear_helix_segment
from cinder.profiles.linear_segment import LinearSegment
from cinder.profiles.piecewise_ramp import PiecewiseRamp


@dataclass(frozen=True, slots=True)
class PreviewParameters:
    """Editable illustrative values, collected here rather than hidden in laws."""

    primary_travel: float = 0.01905
    secondary_travel: float = 0.01905

    primary_flyweight_mass: float = 0.120
    primary_flyweight_radius_at_zero: float = 0.035
    primary_ramp_angle_degrees: float = 30.0
    primary_spring_stiffness: float = 25_000.0
    primary_initial_spring_compression: float = 0.004

    secondary_axial_spring_stiffness: float = 25_000.0
    secondary_initial_spring_compression: float = 0.030

    secondary_helix_radius: float = 0.030
    secondary_helix_angle_degrees: float = 28.0
    secondary_torsional_stiffness: float = 8.0
    secondary_initial_twist: float = 1.40
    secondary_movable_sheave_inertia: float = 0.002


DEFAULT_PARAMETERS = PreviewParameters()


@dataclass(frozen=True, slots=True)
class SecondaryPreviewKinematics:
    """
    Chosen local-to-global kinematic slice for the secondary force preview.

    The actual RHS will obtain x_s', x_s'', and s_dot from geometry and
    state. This standalone plot keeps them explicit so the original
    x_s-versus-tau_s force-map layout remains useful before the full closure
    assembly exists.
    """

    global_shift_speed: float
    local_coordinate_slope: float
    local_coordinate_curvature: float


def radians_per_second_from_rpm(rpm: float) -> float:
    return rpm * 2.0 * pi / 60.0


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
                radius_at_zero_position=(parameters.primary_flyweight_radius_at_zero),
                radial_displacement_profile=radial_profile,
            ),
            axial_spring=AxialSpringForceSpec(
                stiffness=parameters.primary_spring_stiffness,
                initial_compression=(parameters.primary_initial_spring_compression),
                compression_per_axial_position=1.0,
            ),
        )
    )


def build_secondary(parameters: PreviewParameters):
    """
    Build the normal secondary PulleyActuator.

    The primary preview uses x_p in [0, travel]. The public secondary
    coordinate is x_s in [-travel, 0] during an upshift: x_s = 0 is
    low-ratio closed and negative x_s opens the secondary. The shared helix
    profile itself uses q = -x_s as its positive opening coordinate.
    """

    helix_profile = HelixProfile(
        circumferential_profile=PiecewiseRamp(
            (
                linear_helix_segment(
                    length=parameters.secondary_travel,
                    helix_angle_degrees=(parameters.secondary_helix_angle_degrees),
                ),
            )
        ),
        radius=parameters.secondary_helix_radius,
    )

    return build_torque_reactive_secondary(
        spec=TorqueReactiveSecondarySpec(
            axial_spring=AxialSpringForceSpec(
                stiffness=parameters.secondary_axial_spring_stiffness,
                initial_compression=(parameters.secondary_initial_spring_compression),
                compression_per_axial_position=-1.0,
            ),
            helix_force=SecondaryHelixForceSpec(
                torsional_stiffness=(parameters.secondary_torsional_stiffness),
                initial_twist=parameters.secondary_initial_twist,
                movable_sheave_rotational_inertia=(
                    parameters.secondary_movable_sheave_inertia
                ),
                movable_sheave_torque_fraction=0.5,
            ),
        ),
        helix_profile=helix_profile,
    )


def primary_state(
    *,
    axial_position: float,
    shaft_speed_rpm: float,
) -> PulleyActuationState:
    return PulleyActuationState(
        axial_position=axial_position,
        axial_speed=0.0,
        shaft_speed=radians_per_second_from_rpm(shaft_speed_rpm),
    )


def secondary_state(
    *,
    axial_position: float,
    shaft_speed_rpm: float,
    kinematics: SecondaryPreviewKinematics,
) -> SecondaryHelixActuationState:
    return SecondaryHelixActuationState(
        axial_position=axial_position,
        axial_speed=(kinematics.local_coordinate_slope * kinematics.global_shift_speed),
        shaft_speed=radians_per_second_from_rpm(shaft_speed_rpm),
        global_shift_speed=kinematics.global_shift_speed,
        local_axial_coordinate_slope=kinematics.local_coordinate_slope,
        local_axial_coordinate_curvature=(kinematics.local_coordinate_curvature),
    )


def evaluate_force(
    actuator,
    *,
    state: PulleyActuationState,
    unknowns: ClosureUnknowns,
) -> float:
    return actuator.evaluate(state).force(unknowns)


StateFromPosition = Callable[[float, float], PulleyActuationState]
UnknownsFromValue = Callable[[float], ClosureUnknowns]
SpeedFromValue = Callable[[float], float]


def force_surface(
    actuator,
    *,
    positions: np.ndarray,
    varying_values: np.ndarray,
    state_from_position: StateFromPosition,
    shaft_speed_from_value: SpeedFromValue,
    unknowns_from_value: UnknownsFromValue,
) -> np.ndarray:
    values = np.empty((varying_values.size, positions.size))

    for row, varying_value in enumerate(varying_values):
        unknowns = unknowns_from_value(float(varying_value))
        shaft_speed_rpm = shaft_speed_from_value(float(varying_value))

        for column, axial_position in enumerate(positions):
            values[row, column] = evaluate_force(
                actuator,
                state=state_from_position(
                    float(axial_position),
                    shaft_speed_rpm,
                ),
                unknowns=unknowns,
            )

    return values


def signed_norm(values: np.ndarray) -> TwoSlopeNorm:
    largest_magnitude = max(float(np.max(np.abs(values))), 1.0)
    return TwoSlopeNorm(
        vmin=-largest_magnitude,
        vcenter=0.0,
        vmax=largest_magnitude,
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
) -> None:
    mesh = axis.pcolormesh(
        positions_mm,
        varying_values,
        forces,
        shading="auto",
        cmap="coolwarm",
        norm=signed_norm(forces),
    )

    if float(np.min(forces)) <= 0.0 <= float(np.max(forces)):
        axis.contour(
            positions_mm,
            varying_values,
            forces,
            levels=(0.0,),
            linewidths=1.2,
        )

    axis.set_title(title)
    axis.set_xlabel(x_label)
    axis.set_ylabel(y_label)
    axis.grid(True, alpha=0.25)

    colorbar = axis.figure.colorbar(mesh, ax=axis)
    colorbar.set_label("Net local axial force [N]\n(closing +, opening −)")


def plot_input_slices(
    axis,
    *,
    actuator,
    axial_positions: tuple[float, ...],
    varying_values: np.ndarray,
    state_from_position: StateFromPosition,
    shaft_speed_from_value: SpeedFromValue,
    unknowns_from_value: UnknownsFromValue,
    title: str,
    x_label: str,
    position_label: str,
) -> None:
    for axial_position in axial_positions:
        forces = [
            evaluate_force(
                actuator,
                state=state_from_position(
                    axial_position,
                    shaft_speed_from_value(float(value)),
                ),
                unknowns=unknowns_from_value(float(value)),
            )
            for value in varying_values
        ]
        axis.plot(
            varying_values,
            forces,
            label=f"{position_label} = {axial_position * 1_000.0:.2f} mm",
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
    secondary_kinematics: SecondaryPreviewKinematics,
    secondary_angular_acceleration: float,
    shift_acceleration: float,
    samples: int,
):
    primary = build_primary(parameters)
    secondary = build_secondary(parameters)

    primary_positions = np.linspace(0.0, parameters.primary_travel, samples)

    # Physical secondary coordinate: 0 is closed low ratio; negative opens it.
    secondary_positions = np.linspace(
        -parameters.secondary_travel,
        0.0,
        samples,
    )

    primary_rpm = np.linspace(0.0, primary_rpm_max, samples)
    secondary_torque = np.linspace(
        secondary_torque_min,
        secondary_torque_max,
        samples,
    )

    primary_unknowns = ClosureUnknowns.zeros()

    def primary_state_from_position(
        axial_position: float,
        shaft_speed_rpm: float,
    ) -> PulleyActuationState:
        return primary_state(
            axial_position=axial_position,
            shaft_speed_rpm=shaft_speed_rpm,
        )

    def secondary_state_from_position(
        axial_position: float,
        shaft_speed_rpm: float,
    ) -> SecondaryHelixActuationState:
        return secondary_state(
            axial_position=axial_position,
            shaft_speed_rpm=shaft_speed_rpm,
            kinematics=secondary_kinematics,
        )

    def secondary_unknowns(torque: float) -> ClosureUnknowns:
        return ClosureUnknowns(
            secondary_angular_acceleration=secondary_angular_acceleration,
            shift_acceleration=shift_acceleration,
            secondary_torque=torque,
        )

    primary_surface = force_surface(
        primary,
        positions=primary_positions,
        varying_values=primary_rpm,
        state_from_position=primary_state_from_position,
        shaft_speed_from_value=lambda rpm: rpm,
        unknowns_from_value=lambda _: primary_unknowns,
    )
    secondary_surface = force_surface(
        secondary,
        positions=secondary_positions,
        varying_values=secondary_torque,
        state_from_position=secondary_state_from_position,
        shaft_speed_from_value=lambda _: 0.0,
        unknowns_from_value=secondary_unknowns,
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
        title=(
            "Secondary: net force over local closure and torque "
            r"(fixed $\dot{s}$, $\dot{\omega}_s$, $\ddot{s}$)"
        ),
        x_label=(
            r"Secondary local closing coordinate $x_s$ [mm] " r"(negative = opening)"
        ),
        y_label=r"Secondary torque $\tau_s$ [N m]",
    )

    primary_slice_positions = tuple(
        np.linspace(primary_positions[0], primary_positions[-1], 4)
    )
    secondary_slice_positions = tuple(
        np.linspace(secondary_positions[0], secondary_positions[-1], 4)
    )

    plot_input_slices(
        axes[1, 0],
        actuator=primary,
        axial_positions=primary_slice_positions,
        varying_values=primary_rpm,
        state_from_position=primary_state_from_position,
        shaft_speed_from_value=lambda rpm: rpm,
        unknowns_from_value=lambda _: primary_unknowns,
        title="Primary: force versus shaft speed",
        x_label="Primary speed [rpm]",
        position_label=r"$x_p$",
    )
    plot_input_slices(
        axes[1, 1],
        actuator=secondary,
        axial_positions=secondary_slice_positions,
        varying_values=secondary_torque,
        state_from_position=secondary_state_from_position,
        shaft_speed_from_value=lambda _: 0.0,
        unknowns_from_value=secondary_unknowns,
        title=(
            "Secondary: force versus transmitted torque "
            r"(fixed $\dot{s}$, $\dot{\omega}_s$, $\ddot{s}$)"
        ),
        x_label=r"Secondary torque $\tau_s$ [N m]",
        position_label=r"$x_s$",
    )

    figure.suptitle(
        "CINDER actuator preview: signed local force " "(positive = pulley closing)"
    )
    return figure, primary_surface, secondary_surface


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview CINDER primary and secondary actuator forces."
    )
    parser.add_argument("--primary-rpm-max", type=float, default=8_000.0)
    parser.add_argument("--secondary-torque-min", type=float, default=-30.0)
    parser.add_argument("--secondary-torque-max", type=float, default=80.0)
    parser.add_argument("--primary-travel-mm", type=float, default=19.05)
    parser.add_argument("--secondary-travel-mm", type=float, default=19.05)
    parser.add_argument("--samples", type=int, default=121)
    parser.add_argument(
        "--shift-speed",
        type=float,
        default=0.0,
        help=(
            "Fixed global shift speed s_dot [m/s] used in the secondary "
            "convective-inertia bias."
        ),
    )
    parser.add_argument(
        "--secondary-coordinate-slope",
        type=float,
        default=-1.0,
        help=(
            "Fixed dx_s/ds slice used by the standalone secondary preview. "
            "The full RHS obtains this from geometry."
        ),
    )
    parser.add_argument(
        "--secondary-coordinate-curvature",
        type=float,
        default=0.0,
        help=(
            "Fixed d²x_s/ds² slice used by the standalone secondary preview. "
            "The full RHS obtains this from geometry."
        ),
    )
    parser.add_argument(
        "--secondary-angular-acceleration",
        type=float,
        default=0.0,
        help=(
            "Fixed alpha_s [rad/s²] used to evaluate the affine secondary " "relation."
        ),
    )
    parser.add_argument(
        "--shift-acceleration",
        type=float,
        default=0.0,
        help=("Fixed s_ddot [m/s²] used to evaluate the affine secondary " "relation."),
    )
    parser.add_argument("--save", type=Path)
    parser.add_argument("--no-show", action="store_true")

    args = parser.parse_args()

    if args.primary_rpm_max <= 0.0:
        parser.error("--primary-rpm-max must be positive.")
    if args.secondary_torque_min >= args.secondary_torque_max:
        parser.error("--secondary-torque-min must be below --secondary-torque-max.")
    if args.primary_travel_mm <= 0.0 or args.secondary_travel_mm <= 0.0:
        parser.error("Both travel values must be positive.")
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

    secondary_kinematics = SecondaryPreviewKinematics(
        global_shift_speed=args.shift_speed,
        local_coordinate_slope=args.secondary_coordinate_slope,
        local_coordinate_curvature=args.secondary_coordinate_curvature,
    )

    figure, primary_surface, secondary_surface = plot_force_maps(
        parameters=parameters,
        primary_rpm_max=args.primary_rpm_max,
        secondary_torque_min=args.secondary_torque_min,
        secondary_torque_max=args.secondary_torque_max,
        secondary_kinematics=secondary_kinematics,
        secondary_angular_acceleration=(args.secondary_angular_acceleration),
        shift_acceleration=args.shift_acceleration,
        samples=args.samples,
    )

    print("Preview force ranges")
    print("  primary: " f"[{primary_surface.min():.1f}, {primary_surface.max():.1f}] N")
    print(
        "  secondary: "
        f"[{secondary_surface.min():.1f}, {secondary_surface.max():.1f}] N"
    )
    print("Secondary preview kinematic slice")
    print(f"  s_dot: {secondary_kinematics.global_shift_speed:.6g} m/s")
    print("  dx_s/ds: " f"{secondary_kinematics.local_coordinate_slope:.6g}")
    print("  d²x_s/ds²: " f"{secondary_kinematics.local_coordinate_curvature:.6g} 1/m")
    print("  alpha_s: " f"{args.secondary_angular_acceleration:.6g} rad/s²")
    print(f"  s_ddot: {args.shift_acceleration:.6g} m/s²")

    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180)
        print(f"Saved {args.save}")

    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
