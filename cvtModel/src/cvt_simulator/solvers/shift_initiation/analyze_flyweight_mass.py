"""
Analyze the effect of flyweight mass on CVT shift initiation.

This script varies the flyweight mass from 0 to 2 kg
and shows how it affects the shift initiation RPM.
"""

import numpy as np
import matplotlib.pyplot as plt
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.solvers.shift_initiation.shift_initiation_solver import (
    ShiftInitiationSolver,
)
from cvt_simulator.utils.conversions import rad_s_to_rpm


def analyze_flyweight_mass(
    mass_range=(0.0, 2.0),
    num_points=20,
    args_base=None,
):
    """
    Analyze how flyweight mass affects shift initiation.

    Args:
        mass_range: (min, max) mass values in kg
        num_points: Number of points to sample
        args_base: Base SimulationArgs to modify. If None, uses defaults.

    Returns:
        tuple: (mass_array, shift_rpm_array)
    """
    if args_base is None:
        args_base = SimulationArgs()

    mass_values = np.linspace(mass_range[0], mass_range[1], num_points)

    shift_rpm_values = []

    print("Analyzing flyweight mass effect on shift initiation...")
    print("=" * 60)
    print("Base configuration:")
    print(f"  Primary spring rate: {args_base.primary_spring_rate} N/m")
    print(f"  Primary spring pretension: {args_base.primary_spring_pretension} m")
    print(
        f"  Secondary torsion spring rate: {args_base.secondary_torsion_spring_rate} Nm/rad"
    )
    print(
        f"  Secondary compression spring rate: {args_base.secondary_compression_spring_rate} N/m"
    )
    print(
        f"  Secondary rotational pretension: {args_base.secondary_rotational_spring_pretension} deg"
    )
    print(
        f"  Secondary linear pretension: {args_base.secondary_linear_spring_pretension} m"
    )
    print()
    print(f"Varying flyweight mass from {mass_range[0]} to {mass_range[1]} kg")
    print()

    for i, mass in enumerate(mass_values):
        # Skip mass = 0 as it would cause issues
        if mass < 0.01:
            shift_rpm_values.append(np.nan)
            print(
                f"  [{i + 1:2d}/{num_points}] Mass: {mass:.3f} kg → Skipped (too small)"
            )
            continue

        # Create modified args with new flyweight mass
        args = SimulationArgs(
            flyweight_mass=mass,
            primary_spring_rate=args_base.primary_spring_rate,
            primary_spring_pretension=args_base.primary_spring_pretension,
            secondary_torsion_spring_rate=args_base.secondary_torsion_spring_rate,
            secondary_compression_spring_rate=args_base.secondary_compression_spring_rate,
            secondary_rotational_spring_pretension=args_base.secondary_rotational_spring_pretension,
            secondary_linear_spring_pretension=args_base.secondary_linear_spring_pretension,
        )

        solver = ShiftInitiationSolver(args)
        result = solver.solve()

        if result.success:
            shift_rpm = rad_s_to_rpm(result.value)
            shift_rpm_values.append(shift_rpm)
            print(
                f"  [{i + 1:2d}/{num_points}] Mass: {mass:.3f} kg → Shift at {shift_rpm:.1f} RPM"
            )
        else:
            shift_rpm_values.append(np.nan)
            print(f"  [{i + 1:2d}/{num_points}] Mass: {mass:.3f} kg → Solver failed")

    print()
    print("Analysis complete!")

    return mass_values, np.array(shift_rpm_values)


def plot_results(mass_values, shift_rpm_values, args_base):
    """Create visualization of the analysis results."""
    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot the relationship
    ax.plot(
        mass_values * 1000,
        shift_rpm_values,
        "b-",
        linewidth=2,
        marker="o",
        markersize=4,
    )

    # Styling
    ax.set_xlabel("Flyweight Mass (g)", fontsize=12)
    ax.set_ylabel("Shift Initiation RPM", fontsize=12)
    ax.set_title(
        "Effect of Flyweight Mass on CVT Shift Initiation", fontsize=14, weight="bold"
    )
    ax.grid(True, alpha=0.3)

    # Add info box with fixed configuration
    info_text = (
        f"Fixed Configuration:\n"
        f"Primary Spring: {args_base.primary_spring_rate:.0f} N/m\n"
        f"Primary Pretension: {args_base.primary_spring_pretension:.2f} m\n"
        f"Secondary Torsion: {args_base.secondary_torsion_spring_rate:.0f} Nm/rad\n"
        f"Secondary Compression: {args_base.secondary_compression_spring_rate:.0f} N/m\n"
        f"Secondary Rot. Pretension: {args_base.secondary_rotational_spring_pretension:.0f}°\n"
        f"Secondary Lin. Pretension: {args_base.secondary_linear_spring_pretension:.2f} m"
    )
    ax.text(
        0.02,
        0.98,
        info_text,
        transform=ax.transAxes,
        fontsize=9,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )

    # Add statistics (excluding NaN values)
    valid_rpm = shift_rpm_values[~np.isnan(shift_rpm_values)]
    if len(valid_rpm) > 0:
        rpm_range = np.nanmax(shift_rpm_values) - np.nanmin(shift_rpm_values)
        stats_text = (
            f"Range: {np.nanmin(shift_rpm_values):.0f} - {np.nanmax(shift_rpm_values):.0f} RPM\n"
            f"Span: {rpm_range:.0f} RPM"
        )
        ax.text(
            0.98,
            0.02,
            stats_text,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment="bottom",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="lightblue", alpha=0.5),
        )

    plt.tight_layout()
    return fig, ax


def main():
    """Run the analysis and display results."""
    # Use default configuration
    args_base = SimulationArgs()

    # Run analysis
    mass_values, shift_rpm_values = analyze_flyweight_mass(
        mass_range=(0.0, 2.0),
        num_points=20,
        args_base=args_base,
    )

    # Plot results
    fig, ax = plot_results(mass_values, shift_rpm_values, args_base)

    print("✓ Plot ready! Close the window to exit.")
    plt.show()


if __name__ == "__main__":
    main()
