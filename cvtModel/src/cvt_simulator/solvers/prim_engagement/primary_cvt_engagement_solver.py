"""
Solver for finding the minimum angular velocity at which primary pulley can transmit torque.

This solver determines the engagement point - the lowest engine speed at which
the primary pulley generates enough clamping force to transmit torque through the belt.

All internal calculations use SI units (rad/s, N⋅m). Conversion to RPM happens only
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
from cvt_simulator.constants.car_specs import ENGINE_INERTIA


class PrimaryCVTEngagementSolver(SolverBase):
    """
    Finds the minimum RPM at which the primary pulley's t_max > 0.

    This represents the CVT engagement point - below this RPM, the flyweights
    don't generate enough centrifugal force to overcome the spring preload
    and clamp the belt.

    The solver:
    1. Creates a primary pulley model from SimulationArgs
    2. Evaluates t_max at the lowest shift position (engagement position)
    3. Uses root-finding to determine the RPM where t_max crosses zero
    """

    # Solver configuration constants (SI units)
    MIN_OMEGA = 41.89  # Minimum angular velocity: 400 RPM in rad/s
    MAX_OMEGA = 418.88  # Maximum angular velocity: 4000 RPM in rad/s
    TORQUE_THRESHOLD = 0.01  # Threshold for "positive" torque (N⋅m)
    SAMPLE_POINTS = 200  # Number of points to sample when finding crossings

    def __init__(self, args: SimulationArgs):
        """
        Initialize the primary torque threshold solver.

        Args:
            args: Simulation parameters defining the CVT configuration
        """
        super().__init__(args)

        # Initialize models to get the primary pulley and engine
        system_model = get_models(args)
        self.primary_pulley = system_model.cvt_shift_model.primary_pulley
        self.engine_model = system_model.slip_model.engine_model
        self.primary_inertia = ENGINE_INERTIA

    @property
    def solver_name(self) -> str:
        return "CVT Engagement Threshold Solver"

    @property
    def solver_description(self) -> str:
        return (
            "Finds the minimum engine RPM at which the primary pulley "
            "can transmit torque (t_max > 0). This is the CVT engagement point."
        )

    def solve(self) -> SolverResult:
        """
        Solve for the minimum RPM where t_max > 0 (actually positive).

        Finds the FIRST point where t_max crosses the threshold from below,
        even if it decreases again later.

        Returns:
            SolverResult containing the engagement RPM or failure info
        """
        try:
            # Sample the curve to find the first crossing region
            omega_samples, t_max_samples = self.get_engagement_curve(
                omega_range=(self.MIN_OMEGA, self.MAX_OMEGA),
                num_points=self.SAMPLE_POINTS,
            )

            # Check if already engaged at minimum
            if t_max_samples[0] > self.TORQUE_THRESHOLD:
                return SolverResult(
                    success=True,
                    value=self.MIN_OMEGA,
                    units="rad/s",
                    description=f"Primary pulley engaged below {self.MIN_OMEGA:.2f} rad/s",
                )

            # Find the FIRST transition from below to above threshold
            for i in range(len(t_max_samples) - 1):
                below_threshold = t_max_samples[i] <= self.TORQUE_THRESHOLD
                above_threshold = t_max_samples[i + 1] > self.TORQUE_THRESHOLD

                if below_threshold and above_threshold:
                    # Found the first crossing! Refine using root finding
                    omega_left = omega_samples[i]
                    omega_right = omega_samples[i + 1]

                    def threshold_function(omega):
                        return self._evaluate_t_max(omega) - self.TORQUE_THRESHOLD

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
                        description=f"Primary pulley engages at {omega_solution:.2f} rad/s",
                    )

            # No crossing found - never engages in range
            return SolverResult(
                success=False,
                value=None,
                units="rad/s",
                description=f"Primary pulley does not engage up to {self.MAX_OMEGA:.2f} rad/s",
            )

        except Exception as e:
            return SolverResult(
                success=False,
                value=None,
                units="RPM",
                description=f"Solver failed: {str(e)}",
            )

    def _evaluate_t_max(self, angular_velocity: float) -> float:
        """
        Evaluate t_max at a given angular velocity.

        Args:
            angular_velocity: Engine angular velocity [rad/s]

        Returns:
            t_max: Maximum transmittable torque [N⋅m]
        """
        # Create a mock system state at minimum shift position (engagement)
        # At engagement, the CVT is at its lowest ratio (largest primary radius)
        state = SystemState(
            primary_pulley_angular_velocity=angular_velocity,
            secondary_pulley_angular_velocity=0.0,  # Stationary
            shift_distance=0.0,  # Minimum shift position
            shift_velocity=0.0,  # Static evaluation
        )

        # Get engine torque at this angular velocity
        engine_torque = self.engine_model.get_torque(angular_velocity)

        # Calculate torque bounds using the primary pulley model
        # For primary pulley, we want tau_upper (the positive bound)
        torque_bounds = self.primary_pulley.calculate_torque_bounds(
            state,
            engine_drive_torque=engine_torque,
            primary_inertia=self.primary_inertia,
            is_stick=True,
            v_b_star=0.0,
            T_b=1.0,
        )

        # extract tau_upper from the bounds object
        tau_upper = torque_bounds.tau_upper

        return tau_upper

    def get_engagement_curve(
        self,
        omega_range: tuple[float, float] = None,
        num_points: int = 100,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Generate a curve of t_max vs angular velocity for visualization.

        Useful for understanding engagement behavior and verifying the solution.

        Args:
            omega_range: (min_omega, max_omega) range in rad/s to evaluate.
                        Defaults to (MIN_OMEGA, MAX_OMEGA)
            num_points: Number of points to evaluate

        Returns:
            tuple: (omega_array, t_max_array) in rad/s and N⋅m
        """
        if omega_range is None:
            omega_range = (self.MIN_OMEGA, self.MAX_OMEGA)

        min_omega, max_omega = omega_range
        omega_array = np.linspace(min_omega, max_omega, num_points)

        t_max_array = np.array([self._evaluate_t_max(omega) for omega in omega_array])

        return omega_array, t_max_array


def main():
    """Plot engagement curve with default configuration."""
    print("Primary CVT Engagement Solver")
    print("=" * 50)
    print()

    # Create solver with default configuration
    args = SimulationArgs()

    print("Configuration:")
    print(f"  Flyweight mass: {args.flyweight_mass} kg")
    print(f"  Primary spring rate: {args.primary_spring_rate} N/m")
    print(f"  Primary spring pretension: {args.primary_spring_pretension} m")
    print()

    solver = PrimaryCVTEngagementSolver(args)

    # Solve for engagement point (returns omega in rad/s)
    result = solver.solve()

    if result.success:
        # Convert to RPM for display
        engagement_rpm = rad_s_to_rpm(result.value)
        print(
            f"✓ Primary pulley engages at {engagement_rpm:.1f} RPM ({result.value:.2f} rad/s)"
        )
    else:
        print(f"✗ {result.description}")

    print()
    print("Generating plot...")

    # Get engagement curve data in SI units (rad/s)
    omega_array, t_max_array = solver.get_engagement_curve(num_points=200)

    # Convert to RPM for plotting
    rpm_array = rad_s_to_rpm(omega_array)

    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot the curve
    ax.plot(rpm_array, t_max_array, "b-", linewidth=2, label="Maximum Torque (t_max)")

    # Add zero line
    ax.axhline(y=0, color="k", linestyle="--", alpha=0.3, label="Zero Torque")

    # Mark engagement point if successful
    if result.success and result.value is not None:
        engagement_rpm = rad_s_to_rpm(result.value)
        ax.axvline(x=engagement_rpm, color="r", linestyle="--", alpha=0.5)
        ax.plot(
            engagement_rpm,
            0,
            "ro",
            markersize=10,
            label=f"Engagement Point\n({engagement_rpm:.1f} RPM)",
        )

        # Add annotation
        ax.annotate(
            f"{engagement_rpm:.1f} RPM",
            xy=(engagement_rpm, 0),
            xytext=(engagement_rpm - 600, max(t_max_array) * 0.3),
            arrowprops=dict(arrowstyle="->", color="red", lw=1.5),
            fontsize=12,
            color="red",
            weight="bold",
        )

    # Styling
    ax.set_xlabel("Engine Speed (RPM)", fontsize=12)
    ax.set_ylabel("Maximum Transmittable Torque (N⋅m)", fontsize=12)
    ax.set_title(
        "Primary Pulley Engagement Curve\n(Maximum Torque vs Engine Speed)",
        fontsize=14,
        weight="bold",
    )
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=10)

    # Add info box with configuration
    info_text = (
        f"Configuration:\n"
        f"Flyweight: {args.flyweight_mass:.2f} kg\n"
        f"Spring Rate: {args.primary_spring_rate:.0f} N/m\n"
        f"Pretension: {args.primary_spring_pretension:.2f} m"
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
