# cvtModel/tools/preview_profiles.py
"""
Visualize CINDER normal-ramp and conventional secondary-helix geometry.

Run from cvtModel/:

    python tools/preview_profiles.py helix
    python tools/preview_profiles.py ramp

Useful variants:

    python tools/preview_profiles.py helix --scenario linear --helix-start-angle 36
    python tools/preview_profiles.py helix --scenario circular --helix-start-angle 36 --helix-end-angle 20
    python tools/preview_profiles.py helix --scenario piecewise --radius 0.030 --repeats 3
    python tools/preview_profiles.py ramp --scenario linear --ramp-start-angle 25
    python tools/preview_profiles.py ramp --scenario linear-circular --ramp-start-angle 25 --ramp-end-angle 15
    python tools/preview_profiles.py ramp --ramp-width 0.040 --ramp-base-thickness 0.004

For a non-interactive image instead of a window:

    python tools/preview_profiles.py helix --save artifacts/helix_preview.png --no-show

Each command creates one composite figure. The helix preview uses the
conventional secondary opening-travel coordinate q: q = 0 at the closed
reference and q > 0 as the secondary opens and winds the torsional spring.
The profile builders near the bottom are intentionally compact so they are
easy to replace with a real hardware ramp once its dimensions are known.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import pi
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from cinder.profiles import (
    CircularSegment,
    HelixProfile,
    LinearSegment,
    PiecewiseRamp,
    circular_helix_segment,
    linear_helix_segment,
)


DEFAULT_LENGTH = 0.01905
DEFAULT_HELIX_RADIUS = 0.030
DEFAULT_HELIX_START_ANGLE_DEGREES = 36.0
DEFAULT_HELIX_END_ANGLE_DEGREES = 20.0
DEFAULT_RAMP_START_ANGLE_DEGREES = 25.0
DEFAULT_RAMP_END_ANGLE_DEGREES = 15.0
DEFAULT_LINEAR_FRACTION = 0.25
DEFAULT_SAMPLES = 500
DEFAULT_REPEATS = 3
DEFAULT_RAMP_WIDTH = 0.005
DEFAULT_RAMP_BASE_THICKNESS = 0.003
DEFAULT_RAMP_SOLID_ALPHA = 0.55


@dataclass(frozen=True, slots=True)
class SampledRamp:
    x: np.ndarray
    value: np.ndarray
    first_derivative: np.ndarray
    second_derivative: np.ndarray


@dataclass(frozen=True, slots=True)
class SampledHelix:
    opening_travel: np.ndarray
    circumferential_displacement: np.ndarray
    theta: np.ndarray
    dtheta_dopening: np.ndarray
    d2theta_dopening2: np.ndarray
    helix_angle_degrees: np.ndarray


def sample_ramp(ramp: PiecewiseRamp, sample_count: int) -> SampledRamp:
    x = np.linspace(ramp.x_min, ramp.x_max, sample_count)
    samples = [ramp.evaluate(float(value)) for value in x]

    return SampledRamp(
        x=x,
        value=np.array([sample.value for sample in samples]),
        first_derivative=np.array([sample.first_derivative for sample in samples]),
        second_derivative=np.array([sample.second_derivative for sample in samples]),
    )


def sample_helix(
    helix: HelixProfile,
    sample_count: int,
) -> SampledHelix:
    opening_travel = np.linspace(
        helix.opening_travel_min,
        helix.opening_travel_max,
        sample_count,
    )
    samples = [helix.evaluate(float(value)) for value in opening_travel]

    return SampledHelix(
        opening_travel=opening_travel,
        circumferential_displacement=np.array(
            [sample.circumferential_displacement for sample in samples]
        ),
        theta=np.array([sample.theta for sample in samples]),
        dtheta_dopening=np.array([sample.dtheta_dopening for sample in samples]),
        d2theta_dopening2=np.array([sample.d2theta_dopening2 for sample in samples]),
        helix_angle_degrees=np.degrees(
            np.array([sample.helix_angle_magnitude for sample in samples])
        ),
    )


def ramp_boundaries(ramp: PiecewiseRamp) -> tuple[float, ...]:
    """Return internal global x coordinates where one segment ends."""

    boundary = 0.0
    boundaries: list[float] = []

    for segment in ramp.segments[:-1]:
        boundary += segment.length
        boundaries.append(boundary)

    return tuple(boundaries)


def add_segment_boundaries(ax, ramp: PiecewiseRamp) -> None:
    for boundary in ramp_boundaries(ramp):
        ax.axvline(boundary * 1_000.0, linestyle="--", linewidth=1.0)


def build_helix_ramp(args: argparse.Namespace) -> PiecewiseRamp:
    """
    Construct an editable conventional-secondary u(q) profile.

    Replace this function with a design-specific list of segments when a real
    helix path is ready.  The current examples are intentionally simple:

    linear:
        constant helix angle across the full travel;

    circular:
        a single circular physical (x, u) segment that matches the requested
        start and end helix angles;

    piecewise:
        a constant-angle lead-in followed by the circular transition.
    """

    if args.scenario == "linear":
        return PiecewiseRamp(
            (
                linear_helix_segment(
                    length=args.length,
                    helix_angle_degrees=args.helix_start_angle,
                ),
            )
        )

    if args.scenario == "circular":
        return PiecewiseRamp(
            (
                circular_helix_segment(
                    length=args.length,
                    start_helix_angle_degrees=args.helix_start_angle,
                    end_helix_angle_degrees=args.helix_end_angle,
                ),
            )
        )

    if args.scenario == "piecewise":
        linear_length = args.length * args.linear_fraction
        circular_length = args.length - linear_length

        return PiecewiseRamp(
            (
                linear_helix_segment(
                    length=linear_length,
                    helix_angle_degrees=args.helix_start_angle,
                ),
                circular_helix_segment(
                    length=circular_length,
                    start_helix_angle_degrees=args.helix_start_angle,
                    end_helix_angle_degrees=args.helix_end_angle,
                ),
            )
        )

    raise ValueError(f"Unknown helix scenario: {args.scenario!r}")


def build_normal_ramp(args: argparse.Namespace) -> PiecewiseRamp:
    """
    Construct an editable normal ramp profile y(x).

    This is deliberately independent from HelixProfile.  A centrifugal ramp
    can use this curve directly as, for example, its flyweight-radius profile.
    """

    if args.scenario == "linear":
        return PiecewiseRamp(
            (
                LinearSegment(
                    length=args.length,
                    angle_degrees=args.ramp_start_angle,
                ),
            )
        )

    if args.scenario == "linear-circular":
        linear_length = args.length * args.linear_fraction
        circular_length = args.length - linear_length

        return PiecewiseRamp(
            (
                LinearSegment(
                    length=linear_length,
                    angle_degrees=args.ramp_start_angle,
                ),
                CircularSegment(
                    length=circular_length,
                    angle_start_degrees=args.ramp_start_angle,
                    angle_end_degrees=args.ramp_end_angle,
                    quadrant=2,
                ),
            )
        )

    raise ValueError(f"Unknown normal-ramp scenario: {args.scenario!r}")


def plot_helix(
    helix: HelixProfile,
    ramp: PiecewiseRamp,
    *,
    title: str,
    repeats: int,
    sample_count: int,
    surface_alpha: float,
):
    samples = sample_helix(helix, sample_count)
    opening_travel_mm = samples.opening_travel * 1_000.0

    figure = plt.figure(figsize=(17, 10), constrained_layout=True)
    grid = figure.add_gridspec(3, 4)

    ax_3d = figure.add_subplot(grid[:, :2], projection="3d")
    ax_u = figure.add_subplot(grid[0, 2])
    ax_theta = figure.add_subplot(grid[0, 3])
    ax_dtheta = figure.add_subplot(grid[1, 2])
    ax_d2theta = figure.add_subplot(grid[1, 3])
    ax_beta = figure.add_subplot(grid[2, 2:])

    z_bottom = float(samples.opening_travel[0])
    z_top = float(samples.opening_travel[-1])

    # The reference circles show the physical cylinder on which the helix
    # paths lie. The shaded surfaces are ruled surfaces down to the lower
    # reference circle, matching the old visualisation convention.
    circle_angles = np.linspace(0.0, 2.0 * pi, 240)
    circle_x = helix.radius * np.cos(circle_angles)
    circle_y = helix.radius * np.sin(circle_angles)

    ax_3d.plot(
        circle_x,
        circle_y,
        np.full_like(circle_angles, z_bottom),
        linestyle="--",
        linewidth=1.4,
        label="Bottom reference circle",
    )
    ax_3d.plot(
        circle_x,
        circle_y,
        np.full_like(circle_angles, z_top),
        linestyle="--",
        linewidth=1.4,
        label="Top reference circle",
    )

    for repeat_index, phase_offset in enumerate(
        np.linspace(0.0, 2.0 * pi, repeats, endpoint=False)
    ):
        theta = samples.theta + phase_offset
        circumferential_x = helix.radius * np.cos(theta)
        circumferential_y = helix.radius * np.sin(theta)

        ax_3d.plot_surface(
            np.vstack((circumferential_x, circumferential_x)),
            np.vstack((circumferential_y, circumferential_y)),
            np.vstack(
                (
                    samples.opening_travel,
                    np.full_like(samples.opening_travel, z_bottom),
                )
            ),
            alpha=surface_alpha,
            linewidth=0.0,
        )

        label = "Helix path" if repeat_index == 0 else None
        ax_3d.plot(
            circumferential_x,
            circumferential_y,
            samples.opening_travel,
            linewidth=2.0,
            label=label,
        )

        if repeat_index == 0:
            ax_3d.scatter(
                [circumferential_x[0]],
                [circumferential_y[0]],
                [z_bottom],
                marker="o",
                label="Closed reference ($q=0$)",
            )
            ax_3d.scatter(
                [circumferential_x[-1]],
                [circumferential_y[-1]],
                [z_top],
                marker="s",
                label=r"Opened reference ($q=q_{\max}$)",
            )

    z_extent = max(z_top - z_bottom, 1e-12)
    ax_3d.set_xlim(-helix.radius, helix.radius)
    ax_3d.set_ylim(-helix.radius, helix.radius)
    ax_3d.set_zlim(z_bottom, z_top)
    ax_3d.set_box_aspect((2.0 * helix.radius, 2.0 * helix.radius, z_extent))
    ax_3d.set_proj_type("ortho")
    ax_3d.set_xlabel("Circumferential x [m]")
    ax_3d.set_ylabel("Circumferential y [m]")
    ax_3d.set_zlabel("Secondary opening travel q [m]")
    ax_3d.set_title("Physical secondary-helix path")
    ax_3d.plot(
        [],
        [],
        [],
        linewidth=6.0,
        alpha=surface_alpha,
        label="Ruled surface to bottom circle",
    )
    ax_3d.legend(loc="upper left")
    ax_3d.view_init(elev=20.0, azim=45.0)

    ax_u.plot(
        opening_travel_mm,
        samples.circumferential_displacement * 1_000.0,
    )
    ax_u.set_title("Circumferential displacement")
    ax_u.set_xlabel("Secondary opening travel q [mm]")
    ax_u.set_ylabel("u(q) [mm]")

    ax_theta.plot(opening_travel_mm, samples.theta)
    ax_theta.set_title("Spring-winding rotation")
    ax_theta.set_xlabel("Secondary opening travel q [mm]")
    ax_theta.set_ylabel("θ(q) [rad]")

    ax_dtheta.plot(opening_travel_mm, samples.dtheta_dopening)
    ax_dtheta.set_title("Winding gradient")
    ax_dtheta.set_xlabel("Secondary opening travel q [mm]")
    ax_dtheta.set_ylabel("dθ/dq [rad/m]")

    ax_d2theta.plot(opening_travel_mm, samples.d2theta_dopening2)
    ax_d2theta.set_title("Winding curvature")
    ax_d2theta.set_xlabel("Secondary opening travel q [mm]")
    ax_d2theta.set_ylabel("d²θ/dq² [rad/m²]")

    ax_beta.plot(opening_travel_mm, samples.helix_angle_degrees)
    ax_beta.set_title("Local helix-angle magnitude")
    ax_beta.set_xlabel("Secondary opening travel q [mm]")
    ax_beta.set_ylabel("β(q) [deg]")

    for axis in (ax_u, ax_theta, ax_dtheta, ax_d2theta, ax_beta):
        add_segment_boundaries(axis, ramp)
        axis.grid(True, alpha=0.3)

    figure.suptitle(title)
    return figure


def plot_normal_ramp(
    ramp: PiecewiseRamp,
    *,
    title: str,
    sample_count: int,
    ramp_width: float,
    base_thickness: float,
    solid_alpha: float,
):
    """
    Show a scalar ramp as an extruded physical profile.

    The x-y profile is extruded through `ramp_width`; the side walls extend
    down to a base placed `base_thickness` beneath the lowest sampled profile
    value. This is only a visualization solid, not an assertion about the
    eventual manufactured ramp body.
    """

    samples = sample_ramp(ramp, sample_count)
    x_mm = samples.x * 1_000.0
    y_mm = samples.value * 1_000.0

    figure = plt.figure(figsize=(17, 10), constrained_layout=True)
    grid = figure.add_gridspec(3, 4)

    ax_3d = figure.add_subplot(grid[:, :2], projection="3d")
    ax_profile = figure.add_subplot(grid[0, 2:])
    ax_slope = figure.add_subplot(grid[1:, 2])
    ax_curvature = figure.add_subplot(grid[1:, 3])

    half_width = ramp_width / 2.0
    base_height = float(samples.value.min() - base_thickness)

    # Top ramp surface: the physical x-y profile extruded through the
    # out-of-plane width coordinate.
    x_surface = np.vstack((samples.x, samples.x))
    width_surface = np.vstack(
        (
            np.full_like(samples.x, -half_width),
            np.full_like(samples.x, half_width),
        )
    )
    top_surface = np.vstack((samples.value, samples.value))
    base_surface = np.full_like(top_surface, base_height)

    ax_3d.plot_surface(
        x_surface,
        width_surface,
        top_surface,
        alpha=solid_alpha,
        linewidth=0.0,
    )

    # The base and the two long side walls make the profile read as a solid
    # extrusion rather than a free-floating sheet.
    ax_3d.plot_surface(
        x_surface,
        width_surface,
        base_surface,
        alpha=solid_alpha * 0.55,
        linewidth=0.0,
    )

    for side_width in (-half_width, half_width):
        ax_3d.plot_surface(
            np.vstack((samples.x, samples.x)),
            np.full((2, samples.x.size), side_width),
            np.vstack(
                (
                    np.full_like(samples.value, base_height),
                    samples.value,
                )
            ),
            alpha=solid_alpha,
            linewidth=0.0,
        )

    # Close the two end caps.
    for x_end, y_end in (
        (samples.x[0], samples.value[0]),
        (samples.x[-1], samples.value[-1]),
    ):
        ax_3d.plot_surface(
            np.full((2, 2), x_end),
            np.array(
                (
                    (-half_width, half_width),
                    (-half_width, half_width),
                )
            ),
            np.array(
                (
                    (base_height, base_height),
                    (y_end, y_end),
                )
            ),
            alpha=solid_alpha,
            linewidth=0.0,
        )

    # Crisp top edges retain the actual profile shape even when the solid is
    # rendered semi-transparently.
    for side_width in (-half_width, half_width):
        ax_3d.plot(
            samples.x,
            np.full_like(samples.x, side_width),
            samples.value,
            linewidth=2.0,
        )

    ax_3d.plot(
        [samples.x[0], samples.x[0]],
        [-half_width, half_width],
        [samples.value[0], samples.value[0]],
        linewidth=1.5,
    )
    ax_3d.plot(
        [samples.x[-1], samples.x[-1]],
        [-half_width, half_width],
        [samples.value[-1], samples.value[-1]],
        linewidth=1.5,
    )

    x_extent = max(float(samples.x[-1] - samples.x[0]), 1e-12)
    vertical_extent = max(
        float(samples.value.max() - base_height),
        1e-12,
    )

    ax_3d.set_xlim(float(samples.x[0]), float(samples.x[-1]))
    ax_3d.set_ylim(-half_width, half_width)
    ax_3d.set_zlim(base_height, float(samples.value.max()))
    ax_3d.set_box_aspect((x_extent, ramp_width, vertical_extent))
    ax_3d.set_proj_type("ortho")
    ax_3d.set_xlabel("Axial position x [m]")
    ax_3d.set_ylabel("Ramp width [m]")
    ax_3d.set_zlabel("Profile value y [m]")
    ax_3d.set_title("Extruded physical ramp profile")
    ax_3d.plot(
        [],
        [],
        [],
        linewidth=6.0,
        alpha=solid_alpha,
        label="Extruded ramp body",
    )
    ax_3d.legend(loc="upper left")
    ax_3d.view_init(elev=24.0, azim=-58.0)

    ax_profile.plot(x_mm, y_mm, linewidth=2.0)
    ax_profile.set_title("Side-profile geometry")
    ax_profile.set_xlabel("Axial position x [mm]")
    ax_profile.set_ylabel("Profile value y(x) [mm]")
    ax_profile.set_aspect("equal", adjustable="datalim")

    ax_slope.plot(x_mm, samples.first_derivative)
    ax_slope.set_title("Local slope")
    ax_slope.set_xlabel("Axial position x [mm]")
    ax_slope.set_ylabel("dy/dx [-]")

    ax_curvature.plot(x_mm, samples.second_derivative)
    ax_curvature.set_title("Local curvature")
    ax_curvature.set_xlabel("Axial position x [mm]")
    ax_curvature.set_ylabel("d²y/dx² [1/m]")

    for axis in (ax_profile, ax_slope, ax_curvature):
        add_segment_boundaries(axis, ramp)
        axis.grid(True, alpha=0.3)

    figure.suptitle(title)
    return figure


def print_helix_summary(helix: HelixProfile, sample_count: int) -> None:
    samples = sample_helix(helix, sample_count)

    print("Secondary helix profile summary")
    print(
        "  opening range:     "
        f"{samples.opening_travel[0]:.9f} to "
        f"{samples.opening_travel[-1]:.9f} m"
    )
    print(
        "  u range:           "
        f"{samples.circumferential_displacement[0]:.9f} to "
        f"{samples.circumferential_displacement[-1]:.9f} m"
    )
    print(
        "  theta range:       " f"{samples.theta[0]:.9f} to {samples.theta[-1]:.9f} rad"
    )
    print(
        "  helix angle range: "
        f"{samples.helix_angle_degrees.min():.6f} to "
        f"{samples.helix_angle_degrees.max():.6f} deg"
    )
    print(
        "  dtheta/dq range:   "
        f"{samples.dtheta_dopening.min():.9f} to "
        f"{samples.dtheta_dopening.max():.9f} rad/m"
    )
    print(
        "  d2theta/dq2 range: "
        f"{samples.d2theta_dopening2.min():.9f} to "
        f"{samples.d2theta_dopening2.max():.9f} rad/m^2"
    )


def print_ramp_summary(ramp: PiecewiseRamp, sample_count: int) -> None:
    samples = sample_ramp(ramp, sample_count)

    print("Normal ramp profile summary")
    print(f"  axial range:  {samples.x[0]:.9f} to {samples.x[-1]:.9f} m")
    print(
        "  value range:  " f"{samples.value.min():.9f} to {samples.value.max():.9f} m"
    )
    print(
        "  slope range:  "
        f"{samples.first_derivative.min():.9f} to "
        f"{samples.first_derivative.max():.9f}"
    )
    print(
        "  curvature:    "
        f"{samples.second_derivative.min():.9f} to "
        f"{samples.second_derivative.max():.9f} 1/m"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize CINDER ramp and helix profiles."
    )
    parser.add_argument(
        "mode",
        choices=("helix", "ramp"),
        help="Choose a helix or normal scalar-ramp preview.",
    )
    parser.add_argument(
        "--scenario",
        help=(
            "Helix: linear, circular, or piecewise. " "Ramp: linear or linear-circular."
        ),
    )
    parser.add_argument("--length", type=float, default=DEFAULT_LENGTH)
    parser.add_argument(
        "--linear-fraction",
        type=float,
        default=DEFAULT_LINEAR_FRACTION,
        help="Fraction of total travel assigned to the first linear segment.",
    )
    parser.add_argument(
        "--helix-start-angle",
        type=float,
        default=DEFAULT_HELIX_START_ANGLE_DEGREES,
        help="Start helix angle beta [degrees].",
    )
    parser.add_argument(
        "--helix-end-angle",
        type=float,
        default=DEFAULT_HELIX_END_ANGLE_DEGREES,
        help="End helix angle beta [degrees].",
    )
    parser.add_argument(
        "--radius",
        type=float,
        default=DEFAULT_HELIX_RADIUS,
        help="Helix radius [m]. Used only in helix mode.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEATS,
        help="Number of repeated helix paths around the cylinder.",
    )
    parser.add_argument(
        "--surface-alpha",
        type=float,
        default=0.18,
        help=(
            "Opacity of the ruled surfaces from each helix path down to "
            "the bottom reference circle."
        ),
    )
    parser.add_argument(
        "--ramp-start-angle",
        type=float,
        default=DEFAULT_RAMP_START_ANGLE_DEGREES,
        help="Start normal-ramp angle [degrees].",
    )
    parser.add_argument(
        "--ramp-end-angle",
        type=float,
        default=DEFAULT_RAMP_END_ANGLE_DEGREES,
        help="End normal-ramp angle [degrees].",
    )
    parser.add_argument(
        "--ramp-width",
        type=float,
        default=DEFAULT_RAMP_WIDTH,
        help="Out-of-plane width used to extrude the normal-ramp preview [m].",
    )
    parser.add_argument(
        "--ramp-base-thickness",
        type=float,
        default=DEFAULT_RAMP_BASE_THICKNESS,
        help=(
            "Visualization-only material depth beneath the lowest ramp "
            "profile value [m]."
        ),
    )
    parser.add_argument(
        "--ramp-solid-alpha",
        type=float,
        default=DEFAULT_RAMP_SOLID_ALPHA,
        help="Opacity of the extruded normal-ramp body.",
    )
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument(
        "--save",
        type=Path,
        help="Optional output PNG/PDF/SVG path.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Create and optionally save the figure without opening a window.",
    )

    args = parser.parse_args()

    if args.scenario is None:
        args.scenario = "piecewise" if args.mode == "helix" else "linear-circular"

    if args.length <= 0.0:
        parser.error("--length must be positive.")

    if not 0.0 < args.linear_fraction < 1.0:
        parser.error("--linear-fraction must lie strictly between 0 and 1.")

    if args.samples < 3:
        parser.error("--samples must be at least 3.")

    if args.repeats < 1:
        parser.error("--repeats must be at least 1.")

    if not 0.0 <= args.surface_alpha <= 1.0:
        parser.error("--surface-alpha must lie between 0 and 1.")

    if args.ramp_width <= 0.0:
        parser.error("--ramp-width must be positive.")

    if args.ramp_base_thickness <= 0.0:
        parser.error("--ramp-base-thickness must be positive.")

    if not 0.0 <= args.ramp_solid_alpha <= 1.0:
        parser.error("--ramp-solid-alpha must lie between 0 and 1.")

    return args


def main() -> None:
    args = parse_arguments()

    if args.mode == "helix":
        ramp = build_helix_ramp(args)
        helix = HelixProfile(
            circumferential_profile=ramp,
            radius=args.radius,
        )

        print_helix_summary(helix, args.samples)
        figure = plot_helix(
            helix,
            ramp,
            title=(
                "CINDER conventional secondary helix profile "
                f"({args.scenario}; positive opening travel q)"
            ),
            repeats=args.repeats,
            sample_count=args.samples,
            surface_alpha=args.surface_alpha,
        )
    else:
        ramp = build_normal_ramp(args)
        print_ramp_summary(ramp, args.samples)
        figure = plot_normal_ramp(
            ramp,
            title=f"CINDER normal ramp profile ({args.scenario})",
            sample_count=args.samples,
            ramp_width=args.ramp_width,
            base_thickness=args.ramp_base_thickness,
            solid_alpha=args.ramp_solid_alpha,
        )

    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.save, dpi=180)
        print(f"Saved {args.save}")

    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
