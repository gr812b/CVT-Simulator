"""
3D visualization of theta ramp geometry for secondary helix cam.

Plots the relationship between:
- x: axial shift position
- θ: cam rotation angle
- u: circumferential displacement

This reveals the helix geometry and how radius affects the θ(x) profile.
"""

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from cvt_simulator.models.ramps import LinearSegment, PiecewiseRamp
from cvt_simulator.models.ramps.theta_ramp import ThetaRamp
from cvt_simulator.constants.car_specs import HELIX_RADIUS, MAX_SHIFT


def visualize_theta_ramp_3d(
    theta_ramp: ThetaRamp,
    num_points: int = 500,
    figsize: tuple = (12, 9),
    start_on_bottom: bool = True,
):
    """
    Create true 3D visualization of helix ramp geometry in physical space.

    The helix path is traced as:
    - z-axis: axial position (shift distance), rises from bottom to top
    - x, y-axes: form circle at each z with radius r, rotated by θ(x)

    Draws vertical lines from helix to bottom circle, and fills the cylindrical
    region below the ramp with a transparent surface.

    Note:
        ThetaRamp is defined relative to +x. The optional
        start_on_bottom flag only changes visualization orientation.

    Args:
        theta_ramp: ThetaRamp instance to visualize
        num_points: Number of points to sample
        figsize: Figure size (width, height)
        start_on_bottom: If True, apply a -π/2 visual offset so the plotted
            helix starts at the bottom of the circle.
    """
    # Generate sample points
    x_min, x_max = theta_ramp.get_x_range()
    x_axial = np.linspace(x_min, x_max, num_points)

    # Compute theta and convert to 3D coordinates
    theta_points = np.array([theta_ramp.theta(x) for x in x_axial])
    
    # Optional visual offset so the curve can start at bottom for display.
    # Core ThetaRamp math remains referenced to +x.
    theta_plot = theta_points - np.pi / 2 if start_on_bottom else theta_points
    
    # 3D helix parameterization (vertical orientation)
    z_helix = x_axial  # axial direction (vertical)
    x_helix = theta_ramp.r * np.cos(theta_plot)  # circumferential x
    y_helix = theta_ramp.r * np.sin(theta_plot)  # circumferential y

    # Bottom circle
    z_bottom = z_helix[0]

    # Create figure
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, projection="3d")

    # ========== Plot the helix curve ==========
    ax.plot(x_helix, y_helix, z_helix, "b-", linewidth=3, label="Helix path", zorder=10)

    # ========== Plot start and end points ==========
    ax.scatter([x_helix[0]], [y_helix[0]], [z_helix[0]], color="green", s=200, marker="o", label="Start (bottom)", zorder=10)
    ax.scatter([x_helix[-1]], [y_helix[-1]], [z_helix[-1]], color="red", s=200, marker="s", label="End (top)", zorder=10)

    # ========== Draw vertical lines from each helix point down to bottom circle ==========
    for i in range(0, len(x_helix), max(1, len(x_helix) // 20)):  # Draw every ~5% of points for clarity
        ax.plot(
            [x_helix[i], x_helix[i]],
            [y_helix[i], y_helix[i]],
            [z_helix[i], z_bottom],
            "b--", alpha=0.4, linewidth=0.8
        )
    
    # ========== Draw prominent vertical line from endpoint ==========
    ax.plot(
        [x_helix[-1], x_helix[-1]],
        [y_helix[-1], y_helix[-1]],
        [z_helix[-1], z_bottom],
        "r-", linewidth=2.5, alpha=0.8, label="Vertical drop from end"
    )

    # ========== Create ruled surface (cylinder fill below ramp) ==========
    # Top edge: helix points
    # Bottom edge: projections of helix points onto bottom circle (radially outward at same angle)
    x_bottom_proj = theta_ramp.r * np.cos(theta_plot)
    y_bottom_proj = theta_ramp.r * np.sin(theta_plot)
    z_bottom_proj = np.full_like(z_helix, z_bottom)
    
    # Create mesh for the ruled surface
    x_surf = np.vstack([x_helix, x_bottom_proj])
    y_surf = np.vstack([y_helix, y_bottom_proj])
    z_surf = np.vstack([z_helix, z_bottom_proj])
    
    # Plot surface
    ax.plot_surface(
        x_surf, y_surf, z_surf,
        alpha=0.2,
        color="cyan",
        edgecolor="none"
    )

    # ========== Add reference circles ==========
    # Bottom circle (at z_min)
    circle_angles = np.linspace(0, 2*np.pi, 100)
    circle_phase = -np.pi / 2 if start_on_bottom else 0.0
    x_circle_bot = theta_ramp.r * np.cos(circle_angles + circle_phase)
    y_circle_bot = theta_ramp.r * np.sin(circle_angles + circle_phase)
    z_circle_bot = np.full(len(circle_angles), z_bottom)
    ax.plot(x_circle_bot, y_circle_bot, z_circle_bot, "g-", alpha=0.7, linewidth=2, label="Bottom circle")

    # Top circle (at z_max)
    z_top = z_helix[-1]
    z_circle_top = np.full(len(circle_angles), z_top)
    ax.plot(x_circle_bot, y_circle_bot, z_circle_top, "r--", alpha=0.5, linewidth=1.5, label="Top reference circle")

    # ========== Formatting ==========
    ax.set_xlabel("x [m]", fontsize=11, fontweight="bold")
    ax.set_ylabel("y [m]", fontsize=11, fontweight="bold")
    ax.set_zlabel("Axial Position (Height) [m]", fontsize=11, fontweight="bold")
    ax.set_title(f"3D Helix Ramp with Cylindrical Fill Below\n(Helix Radius = {theta_ramp.r:.4f} m)", fontsize=13, fontweight="bold")

    # Enforce true 1:1 data scaling using full cylinder bounds.
    # Use full radius bounds (not helix-visited arc bounds) so circles stay circles.
    z_top = float(np.max(z_helix))
    z_bottom = float(np.min(z_helix))
    ax.set_xlim(-theta_ramp.r, theta_ramp.r)
    ax.set_ylim(-theta_ramp.r, theta_ramp.r)
    ax.set_zlim(z_bottom, z_top)

    x_range = 2.0 * theta_ramp.r
    y_range = 2.0 * theta_ramp.r
    z_range = z_top - z_bottom
    ax.set_box_aspect((x_range, y_range, z_range))
    ax.set_proj_type("ortho")

    ax.legend(fontsize=10, loc="upper left")
    ax.view_init(elev=20, azim=45)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    return fig


def visualize_theta_profiles(
    theta_ramp: ThetaRamp,
    num_points: int = 500,
    figsize: tuple = (20, 5),
):
    """Plot theta(x), dtheta/dx(x), angle multiplier, and helix angle beta(x)."""
    x_min, x_max = theta_ramp.get_x_range()
    x_axial = np.linspace(x_min, x_max, num_points)

    theta_values = np.array([theta_ramp.theta(x) for x in x_axial])
    dtheta_dx_values = np.array([theta_ramp.dtheta_dx(x) for x in x_axial])
    angle_multiplier_values = np.array([theta_ramp.angle_multiplier(x) for x in x_axial])
    beta_values_deg = np.degrees(np.arctan2(1.0, theta_ramp.r * dtheta_dx_values))

    fig, (ax1, ax2, ax3, ax4) = plt.subplots(1, 4, figsize=figsize)

    ax1.plot(x_axial, theta_values, "b-", linewidth=2.5)
    ax1.set_xlabel("Axial Position x [m]")
    ax1.set_ylabel("Theta θ [rad]")
    ax1.set_title("Theta vs Axial Position")
    ax1.grid(True, alpha=0.3)

    ax2.plot(x_axial, dtheta_dx_values, "r-", linewidth=2.5)
    ax2.set_xlabel("Axial Position x [m]")
    ax2.set_ylabel("dθ/dx [rad/m]")
    ax2.set_title("Theta Gradient vs Axial Position")
    ax2.grid(True, alpha=0.3)

    ax3.plot(x_axial, angle_multiplier_values, color="tab:orange", linewidth=2.5)
    ax3.set_xlabel("Axial Position x [m]")
    ax3.set_ylabel("du/dx [unitless]")
    ax3.set_title("Angle Multiplier vs Axial Position")
    ax3.grid(True, alpha=0.3)

    ax4.plot(x_axial, beta_values_deg, "g-", linewidth=2.5)
    ax4.set_xlabel("Axial Position x [m]")
    ax4.set_ylabel("β [deg]")
    ax4.set_title("Helix Angle vs Axial Position")
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    return fig


def main():
    """Example usage: create and visualize a theta ramp in 3D."""
    print("=" * 70)
    print("Theta Ramp 3D Visualization")
    print("=" * 70)

    # Create a linear helix ramp that rotates halfway around the circle
    # Goal: θ goes from 0 to π (180°) over MAX_SHIFT
    # For linear: dθ/dx = π / MAX_SHIFT
    # Since dθ/dx = (du/dx) / r:
    # => du/dx = r * π / MAX_SHIFT = cot(β)
    # => angle = arctan(du/dx)

    target_rotation_rad = np.pi  # 180 degrees around the circle
    cot_beta = HELIX_RADIUS * target_rotation_rad / MAX_SHIFT
    angle_deg = np.degrees(np.arctan(cot_beta))

    print(f"\nHelix Parameters:")
    print(f"  Helix radius r = {HELIX_RADIUS:.4f} m")
    print(f"  Max shift = {MAX_SHIFT:.4f} m")
    print(f"  Target rotation = {np.degrees(target_rotation_rad):.1f}° (halfway around)")
    print(f"  cot(β) = {cot_beta:.4f}")
    print(f"  LinearSegment angle = {angle_deg:.2f}°")

    # Create the angle ramp (angle defined directly)
    angle_ramp = PiecewiseRamp()
    angle_ramp.add_segment(LinearSegment(length=MAX_SHIFT, angle=angle_deg))

    # Wrap in theta ramp
    theta_ramp = ThetaRamp(angle_ramp, HELIX_RADIUS)

    x_min, x_max = theta_ramp.get_x_range()
    theta_min, theta_max = theta_ramp.get_theta_range()

    print(f"\nRamp Ranges:")
    print(f"  Axial position: [{x_min:.4f}, {x_max:.4f}] m")
    print(f"  Rotation: [{np.degrees(theta_min):.2f}°, {np.degrees(theta_max):.2f}°]")
    print(f"  Rotation: [{theta_min:.4f}, {theta_max:.4f}] rad")

    # Create visualizations
    print("\nGenerating 3D helix visualization...")
    visualize_theta_ramp_3d(theta_ramp, num_points=500)

    print("Generating theta profile plots...")
    visualize_theta_profiles(theta_ramp, num_points=500)

    # -----------------------------------------------------------------
    # Example 2: Set helix angle to 36° (direct reference)
    # -----------------------------------------------------------------
    helix_angle_deg = 36.0
    print("\n" + "-" * 70)
    print("Example 2: Helix Angle Set Directly")
    print("-" * 70)

    angle_ramp_direct = PiecewiseRamp()
    angle_ramp_direct.add_segment(
        LinearSegment(length=MAX_SHIFT, angle=90 - helix_angle_deg)
    )
    theta_ramp_direct = ThetaRamp(angle_ramp_direct, HELIX_RADIUS)

    x2_min, x2_max = theta_ramp_direct.get_x_range()
    theta2_min, theta2_max = theta_ramp_direct.get_theta_range()
    dtheta_dx_direct = theta_ramp_direct.dtheta_dx(x2_min)

    print(f"\nDirect-Angle Parameters:")
    print(f"  Helix angle β = {helix_angle_deg:.1f}°")
    print(f"  Helix radius r = {HELIX_RADIUS:.4f} m")
    print(f"  Max shift = {MAX_SHIFT:.4f} m")
    print(f"  dθ/dx = {dtheta_dx_direct:.4f} rad/m")
    print(
        f"  Equivalent helix β = {np.degrees(np.arctan(1.0 / (HELIX_RADIUS * dtheta_dx_direct))):.2f}°"
    )

    print(f"\nDirect-Angle Ramp Ranges:")
    print(f"  Axial position: [{x2_min:.4f}, {x2_max:.4f}] m")
    print(f"  Rotation: [{np.degrees(theta2_min):.2f}°, {np.degrees(theta2_max):.2f}°]")
    print(f"  Rotation: [{theta2_min:.4f}, {theta2_max:.4f}] rad")

    print("Generating 3D helix visualization (direct 36° angle)...")
    visualize_theta_ramp_3d(theta_ramp_direct, num_points=500)

    print("Generating theta profile plots (direct 36° angle)...")
    visualize_theta_profiles(theta_ramp_direct, num_points=500)

    print("Displaying plot...")
    plt.show()

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
