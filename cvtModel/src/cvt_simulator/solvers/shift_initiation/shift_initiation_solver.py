"""
Solver for finding the minimum angular velocity at which CVT begins to shift.

This solver determines the shift initiation point - the lowest engine speed at which
the primary pulley's axial force overcomes the secondary pulley's axial force,
causing the CVT to begin shifting toward higher ratio.

All internal calculations use SI units (rad/s, N). Conversion to RPM happens only
for user-facing results and plots.
"""

import numpy as np
from scipy.optimize import brentq
import matplotlib.pyplot as plt
from cvt_simulator.solvers.solver_interface import SolverBase, SolverResult
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.models.model_initializer import get_models
from cvt_simulator.utils.conversions import rad_s_to_rpm


class ShiftInitiationSolver(SolverBase):
    """
    Finds the minimum angular velocity at which primary axial force > secondary axial force.

    This represents the shift initiation point - the engine speed where the CVT
    begins to shift from low ratio toward high ratio.

    The solver:
    1. Creates primary and secondary pulley models from SimulationArgs
    2. Calculates torque_demand from road load using slip model (no-slip assumption)
    3. Evaluates axial forces at minimum shift position (shift_distance = 0)
    4. Uses root-finding to determine the omega where forces cross
    """

    # Solver configuration constants (SI units)
    MIN_OMEGA = 41.89  # Minimum angular velocity: 400 RPM in rad/s
    MAX_OMEGA = 418.88  # Maximum angular velocity: 4000 RPM in rad/s
    FORCE_THRESHOLD = 0.1  # Small threshold for numerical stability (N)
    SAMPLE_POINTS = 200  # Number of points to sample when finding crossings

    def __init__(self, args: SimulationArgs):
        """
        Initialize the shift initiation solver.

        Args:
            args: Simulation parameters defining the CVT configuration
        """
        super().__init__(args)

        # Initialize models to get both pulleys and the shift model
        system_model = get_models(args)
        self.cvt_shift_model = system_model.cvt_shift_model
        self.primary_pulley = system_model.cvt_shift_model.primary_pulley
        self.secondary_pulley = system_model.cvt_shift_model.secondary_pulley

        # Get slip model for computing torque demand
        self.slip_model = system_model.slip_model

    @property
    def solver_name(self) -> str:
        return "CVT Shift Initiation Solver"

    @property
    def solver_description(self) -> str:
        return (
            "Finds the minimum engine angular velocity at which the primary "
            "axial force overcomes the secondary axial force, initiating shift."
        )

    def solve(self) -> SolverResult:
        """
        Solve for the minimum omega where primary_axial > secondary_axial.

        Finds the FIRST point where the force difference crosses from negative to positive.

        Returns:
            SolverResult containing the shift initiation omega or failure info
        """
        try:
            # Sample the curve to find the first crossing region
            omega_samples, force_diff_samples = self.get_force_difference_curve(
                omega_range=(self.MIN_OMEGA, self.MAX_OMEGA),
                num_points=self.SAMPLE_POINTS,
            )

            # Check if already shifting at minimum
            if force_diff_samples[0] > self.FORCE_THRESHOLD:
                return SolverResult(
                    success=True,
                    value=self.MIN_OMEGA,
                    units="rad/s",
                    description=f"CVT already shifting below {self.MIN_OMEGA:.2f} rad/s",
                )

            # Find the FIRST transition from below to above threshold
            for i in range(len(force_diff_samples) - 1):
                below_threshold = force_diff_samples[i] <= self.FORCE_THRESHOLD
                above_threshold = force_diff_samples[i + 1] > self.FORCE_THRESHOLD

                if below_threshold and above_threshold:
                    # Found the first crossing! Refine using root finding
                    omega_left = omega_samples[i]
                    omega_right = omega_samples[i + 1]

                    def threshold_function(omega):
                        return (
                            self._evaluate_force_difference(omega)
                            - self.FORCE_THRESHOLD
                        )

                    # Use Brent's method to find precise crossing point
                    omega_solution = brentq(
                        threshold_function,
                        omega_left,
                        omega_right,
                        xtol=0.1,  # 0.1 rad/s tolerance
                        rtol=1e-6,
                    )

                    return SolverResult(
                        success=True,
                        value=omega_solution,
                        units="rad/s",
                        description=f"CVT begins shifting at {omega_solution:.2f} rad/s",
                    )

            # No crossing found - never shifts in range
            return SolverResult(
                success=False,
                value=None,
                units="rad/s",
                description=f"CVT does not shift up to {self.MAX_OMEGA:.2f} rad/s",
            )

        except Exception as e:
            return SolverResult(
                success=False,
                value=None,
                units="rad/s",
                description=f"Solver failed: {str(e)}",
            )

    def _evaluate_force_difference(self, angular_velocity: float) -> float:
        """
        Evaluate the force difference (primary_axial - secondary_axial).

        Args:
            angular_velocity: Engine angular velocity [rad/s]

        Returns:
            force_diff: Primary axial force - Secondary axial force [N]
        """
        # Create a system state at minimum shift position and stationary
        state = SystemState(
            engine_angular_velocity=angular_velocity,
            engine_angular_position=0.0,
            shift_distance=0.0,  # Minimum shift position
            shift_velocity=0.0,  # Static evaluation
            car_velocity=0.0,  # Stationary (as specified)
        )

        # Calculate torque demand from road load (before slip limiting)
        torque_demand = self.slip_model.get_torque_demand(state)

        # Get the CVT breakdown which includes both pulley states
        # Use torque_demand to properly account for secondary torque feedback
        cvt_breakdown = self.cvt_shift_model.get_breakdown(
            state, coupling_torque=torque_demand
        )

        # Extract axial clamping forces
        primary_axial_force = cvt_breakdown.primaryPulleyState.forces.axial_force_total
        secondary_axial_force = cvt_breakdown.secondaryPulleyState.forces.axial_force_total

        # Return difference (positive means primary is winning, shift will occur)
        return primary_axial_force - secondary_axial_force

    def get_force_difference_curve(
        self,
        omega_range: tuple[float, float] = None,
        num_points: int = 100,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Generate a curve of force difference vs angular velocity.

        Args:
            omega_range: (min_omega, max_omega) range in rad/s to evaluate.
                        Defaults to (MIN_OMEGA, MAX_OMEGA)
            num_points: Number of points to evaluate

        Returns:
            tuple: (omega_array, force_diff_array) in rad/s and N
        """
        if omega_range is None:
            omega_range = (self.MIN_OMEGA, self.MAX_OMEGA)

        min_omega, max_omega = omega_range
        omega_array = np.linspace(min_omega, max_omega, num_points)

        force_diff_array = np.array(
            [self._evaluate_force_difference(omega) for omega in omega_array]
        )

        return omega_array, force_diff_array


def main():
    """Plot shift initiation curve with default configuration."""
    print("CVT Shift Initiation Solver")
    print("=" * 50)
    print()

    # Create solver with default configuration
    args = SimulationArgs()

    print("Configuration:")
    print(f"  Flyweight mass: {args.flyweight_mass} kg")
    print(f"  Primary spring rate: {args.primary_spring_rate} N/m")
    print(f"  Primary spring pretension: {args.primary_spring_pretension} m")
    print(
        f"  Secondary torsion spring rate: {args.secondary_torsion_spring_rate} Nm/rad"
    )
    print(
        f"  Secondary compression spring rate: {args.secondary_compression_spring_rate} N/m"
    )
    print(
        f"  Secondary rotational pretension: {args.secondary_rotational_spring_pretension} deg"
    )
    print(f"  Secondary linear pretension: {args.secondary_linear_spring_pretension} m")
    print()

    solver = ShiftInitiationSolver(args)

    # Solve for shift initiation point (returns omega in rad/s)
    result = solver.solve()

    if result.success:
        # Convert to RPM for display
        shift_rpm = rad_s_to_rpm(result.value)
        print(
            f"✓ CVT begins shifting at {shift_rpm:.1f} RPM ({result.value:.2f} rad/s)"
        )
    else:
        print(f"✗ {result.description}")

    print()
    print("Generating plot...")

    # Get force difference curve data in SI units (rad/s, N)
    omega_array, force_diff_array = solver.get_force_difference_curve(num_points=200)

    # Convert to RPM for plotting
    rpm_array = rad_s_to_rpm(omega_array)

    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot the curve
    ax.plot(
        rpm_array,
        force_diff_array,
        "b-",
        linewidth=2,
        label="Force Difference (Primary - Secondary)",
    )

    # Add zero line
    ax.axhline(y=0, color="k", linestyle="--", alpha=0.3, label="Zero Force Difference")

    # Mark shift initiation point if successful
    if result.success and result.value is not None:
        shift_rpm = rad_s_to_rpm(result.value)
        ax.axvline(x=shift_rpm, color="r", linestyle="--", alpha=0.5)
        ax.plot(
            shift_rpm,
            0,
            "ro",
            markersize=10,
            label=f"Shift Initiation\n({shift_rpm:.1f} RPM)",
        )

        # Add annotation
        ax.annotate(
            f"{shift_rpm:.1f} RPM",
            xy=(shift_rpm, 0),
            xytext=(shift_rpm - 600, max(force_diff_array) * 0.3),
            arrowprops=dict(arrowstyle="->", color="red", lw=1.5),
            fontsize=12,
            color="red",
            weight="bold",
        )

    # Styling
    ax.set_xlabel("Engine Speed (RPM)", fontsize=12)
    ax.set_ylabel("Axial Force Difference (N)", fontsize=12)
    ax.set_title(
        "CVT Shift Initiation Curve\n(Primary - Secondary Axial Force vs Engine Speed)",
        fontsize=14,
        weight="bold",
    )
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=10)

    # Add info box with configuration
    info_text = (
        f"Configuration:\n"
        f"Flyweight: {args.flyweight_mass:.2f} kg\n"
        f"Primary Spring: {args.primary_spring_rate:.0f} N/m\n"
        f"Primary Pretension: {args.primary_spring_pretension:.2f} m\n"
        f"Secondary Torsion: {args.secondary_torsion_spring_rate:.0f} Nm/rad\n"
        f"Secondary Compression: {args.secondary_compression_spring_rate:.0f} N/m\n"
        f"Secondary Rot. Pretension: {args.secondary_rotational_spring_pretension:.0f}°\n"
        f"Secondary Lin. Pretension: {args.secondary_linear_spring_pretension:.2f} m"
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

    plt.tight_layout()

    print("✓ Plot ready! Close the window to exit.")
    plt.show()


if __name__ == "__main__":
    main()
