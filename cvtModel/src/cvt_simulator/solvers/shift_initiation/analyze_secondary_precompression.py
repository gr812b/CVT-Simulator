"""
Analyze the effect of secondary precompression on CVT shift initiation.

This script varies the secondary linear spring pretension from 0 to 0.4 m
and shows how it affects the shift initiation RPM.
"""

import numpy as np
import matplotlib.pyplot as plt
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.solvers.shift_initiation.shift_initiation_solver import ShiftInitiationSolver
from cvt_simulator.utils.conversions import rad_s_to_rpm


def analyze_secondary_precompression(
    precompression_range=(0.0, 0.4),
    num_points=20,
    args_base=None,
):
    """
    Analyze how secondary linear spring pretension affects shift initiation.
    
    Args:
        precompression_range: (min, max) pretension values in meters
        num_points: Number of points to sample
        args_base: Base SimulationArgs to modify. If None, uses defaults.
    
    Returns:
        tuple: (precompression_array, shift_rpm_array)
    """
    if args_base is None:
        args_base = SimulationArgs()
    
    precompression_values = np.linspace(
        precompression_range[0], 
        precompression_range[1], 
        num_points
    )
    
    shift_rpm_values = []
    
    print("Analyzing secondary precompression effect on shift initiation...")
    print("=" * 60)
    print(f"Base configuration:")
    print(f"  Flyweight mass: {args_base.flyweight_mass} kg")
    print(f"  Primary spring rate: {args_base.primary_spring_rate} N/m")
    print(f"  Primary spring pretension: {args_base.primary_spring_pretension} m")
    print(f"  Secondary torsion spring rate: {args_base.secondary_torsion_spring_rate} Nm/rad")
    print(f"  Secondary compression spring rate: {args_base.secondary_compression_spring_rate} N/m")
    print(f"  Secondary rotational pretension: {args_base.secondary_rotational_spring_pretension} deg")
    print()
    print(f"Varying secondary linear pretension from {precompression_range[0]} to {precompression_range[1]} m")
    print()
    
    for i, precomp in enumerate(precompression_values):
        # Create modified args with new precompression
        args = SimulationArgs(
            flyweight_mass=args_base.flyweight_mass,
            primary_spring_rate=args_base.primary_spring_rate,
            primary_spring_pretension=args_base.primary_spring_pretension,
            secondary_torsion_spring_rate=args_base.secondary_torsion_spring_rate,
            secondary_compression_spring_rate=args_base.secondary_compression_spring_rate,
            secondary_rotational_spring_pretension=args_base.secondary_rotational_spring_pretension,
            secondary_linear_spring_pretension=precomp,
        )
        
        solver = ShiftInitiationSolver(args)
        result = solver.solve()
        
        if result.success:
            shift_rpm = rad_s_to_rpm(result.value)
            shift_rpm_values.append(shift_rpm)
            print(f"  [{i+1:2d}/{num_points}] Precomp: {precomp:.3f} m → Shift at {shift_rpm:.1f} RPM")
        else:
            shift_rpm_values.append(np.nan)
            print(f"  [{i+1:2d}/{num_points}] Precomp: {precomp:.3f} m → Solver failed")
    
    print()
    print("Analysis complete!")
    
    return precompression_values, np.array(shift_rpm_values)


def plot_results(precompression_values, shift_rpm_values, args_base):
    """Create visualization of the analysis results."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot the relationship
    ax.plot(precompression_values * 1000, shift_rpm_values, 'b-', linewidth=2, marker='o', markersize=4)
    
    # Styling
    ax.set_xlabel('Secondary Linear Spring Pretension (mm)', fontsize=12)
    ax.set_ylabel('Shift Initiation RPM', fontsize=12)
    ax.set_title('Effect of Secondary Precompression on CVT Shift Initiation', 
                fontsize=14, weight='bold')
    ax.grid(True, alpha=0.3)
    
    # Add info box with fixed configuration
    info_text = (
        f"Fixed Configuration:\n"
        f"Flyweight: {args_base.flyweight_mass:.2f} kg\n"
        f"Primary Spring: {args_base.primary_spring_rate:.0f} N/m\n"
        f"Primary Pretension: {args_base.primary_spring_pretension:.2f} m\n"
        f"Secondary Torsion: {args_base.secondary_torsion_spring_rate:.0f} Nm/rad\n"
        f"Secondary Compression: {args_base.secondary_compression_spring_rate:.0f} N/m\n"
        f"Secondary Rot. Pretension: {args_base.secondary_rotational_spring_pretension:.0f}°"
    )
    ax.text(
        0.02, 0.98, info_text,
        transform=ax.transAxes,
        fontsize=9,
        verticalalignment='top',
        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5)
    )
    
    # Add statistics
    rpm_range = np.nanmax(shift_rpm_values) - np.nanmin(shift_rpm_values)
    stats_text = (
        f"Range: {np.nanmin(shift_rpm_values):.0f} - {np.nanmax(shift_rpm_values):.0f} RPM\n"
        f"Span: {rpm_range:.0f} RPM"
    )
    ax.text(
        0.98, 0.02, stats_text,
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment='bottom',
        horizontalalignment='right',
        bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5)
    )
    
    plt.tight_layout()
    return fig, ax


def main():
    """Run the analysis and display results."""
    # Use default configuration
    args_base = SimulationArgs()
    
    # Run analysis
    precompression_values, shift_rpm_values = analyze_secondary_precompression(
        precompression_range=(0.0, 0.4),
        num_points=20,
        args_base=args_base,
    )
    
    # Plot results
    fig, ax = plot_results(precompression_values, shift_rpm_values, args_base)
    
    print("✓ Plot ready! Close the window to exit.")
    plt.show()


if __name__ == "__main__":
    main()
