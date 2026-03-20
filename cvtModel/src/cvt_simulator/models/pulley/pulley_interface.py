"""
Abstract interfaces for CVT pulley models.

This module defines the core contracts that all pulley implementations must satisfy,
allowing different control strategies (physical models, PID controllers, lookup tables, etc.)
to be swapped without changing the rest of the simulation.

Key Design Principles:
- Each pulley must provide: clamping force and max torque
- Implementation details (flyweights, helix, PID, etc.) are encapsulated
- Breakdowns provide detailed internal state for debugging/visualization
- **kwargs pattern allows flexible, future-proof parameter passing

Design Pattern Notes:
- **kwargs: Maximum flexibility for implementation-specific parameters
- Common kwargs: 'torque', 'target_rpm', 'target_ratio', 'load_factor'
- Use get_kwarg() helper for safe extraction with defaults
- Trade-off: Flexibility vs type safety (document expected kwargs well)
"""

from abc import ABC, abstractmethod
from typing import Any
import numpy as np
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.constants.car_specs import (
    SHEAVE_ANGLE,
    BELT_CROSS_SECTIONAL_AREA,
    BELT_HEIGHT,
    BELT_WIDTH_TOP,
    BELT_WIDTH_BOTTOM,
)
from cvt_simulator.constants.constants import (
    RUBBER_DENSITY,
    RUBBER_ALUMINUM_STATIC_FRICTION,
)
from cvt_simulator.models.dataTypes import PulleyState, PulleyForces, PulleyBreakdowns


def get_kwarg(kwargs: dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Helper function to safely extract optional kwargs with defaults.

    Usage in implementations:
        # Optional with default
        load_factor = get_kwarg(kwargs, 'load_factor', 1.0)

        # Optional with None default
        target_rpm = get_kwarg(kwargs, 'target_rpm')

    Args:
        kwargs: The kwargs dict from calculate_axial_clamping_force
        key: The parameter name to extract
        default: Default value if key not found (default: None)

    Returns:
        The value from kwargs or the default
    """
    return kwargs.get(key, default)


def get_required_kwarg(kwargs: dict[str, Any], key: str, error_msg: str = None) -> Any:
    """
    Helper function to extract required kwargs with validation.

    Usage in implementations:
        # Required parameter with auto-generated error
        torque = get_required_kwarg(kwargs, 'torque')

        # Required with custom error message
        torque = get_required_kwarg(
            kwargs, 'torque',
            error_msg="PhysicalSecondaryPulley requires 'torque' for torque-reactive operation"
        )

    Args:
        kwargs: The kwargs dict from calculate_axial_clamping_force
        key: The parameter name to extract
        error_msg: Custom error message (optional, auto-generated if not provided)

    Returns:
        The value from kwargs

    Raises:
        ValueError: If key is not in kwargs
    """
    if key not in kwargs:
        if error_msg is None:
            error_msg = f"Required parameter '{key}' not provided in kwargs"
        raise ValueError(error_msg)

    return kwargs[key]


class PulleyModel(ABC):
    """
    Abstract base class for all pulley control strategies.

    Subclasses implement specific mechanisms:
    - PhysicalPrimaryPulley: flyweight-based (centrifugal force on ramp)
    - PhysicalSecondaryPulley: helix-based (torque feedback through cam)
    - PIDPrimaryPulley: electronic control with target RPM
    - LookupTablePulley: pre-computed force maps
    - etc.

    The abstraction allows the simulation to work with any mechanism that
    can provide the required outputs (clamping force and max torque).
    """

    def __init__(self):
        """Initialize pulley model with V-belt friction coefficient."""
        # Calculate friction coefficient with V-belt wedging effect
        # The sheave angle enhances friction through wedging action
        self.μ = RUBBER_ALUMINUM_STATIC_FRICTION

    @abstractmethod
    def calculate_axial_clamping_force(
        self, state: SystemState, **kwargs
    ) -> tuple[float, PulleyBreakdowns]:
        """
        Calculate the axial clamping force pushing pulley halves together.

        This is the core mechanism-specific calculation.
        Supports different implementations (e.g., flyweights, helix, PID control).

        Args:
            state: Current system state (shift position, velocities, etc.)
            **kwargs: Implementation-specific parameters, may include:
                - torque (float): Torque at this pulley [N⋅m]
                    * Primary: typically unused (flyweights are speed-reactive)
                    * Secondary (helix): transmitted torque = primary_torque * cvt_ratio
                    * Secondary (non-reactive): ignored
                - target_rpm (float): Target engine RPM for PID control
                - target_ratio (float): Target CVT ratio for active control
                - load_factor (float): Load-based shift correction
                - Any future parameters needed by new implementations

        Returns:
            tuple: (axial_clamping_force, breakdown)
                - axial_clamping_force: Axial force from pulley hardware [N]
                - breakdown: Implementation-specific detailed breakdown
        """
        pass

    def axial_centrifugal_from_belt(self, state: SystemState) -> float:
        """
        Calculate centrifugal belt contribution projected into axial direction.

        Implements:
            F_c,ax = rho_b * A_b * omega^2 * r_cm^2 * phi / (2 * tan(beta))

        where beta is the sheave half-angle.
        """
        shift_distance = state.shift_distance
        wrap_angle = self._get_wrap_angle(shift_distance)
        angular_velocity = state.secondary_pulley_angular_velocity * tm.secondary_effective_radius(shift_distance) / self._get_radius(shift_distance)
        r_cm = self._get_belt_centroid_radius(shift_distance)
        beta = SHEAVE_ANGLE / 2

        return (
            RUBBER_DENSITY
            * BELT_CROSS_SECTIONAL_AREA
            * angular_velocity**2
            * r_cm**2
            * wrap_angle
            / (2 * np.tan(beta))
        )

    def _get_belt_centroid_radius(self, shift_distance: float) -> float:
        """Get belt mass-centroid radius r_cm at current shift position [m]."""
        # Delta from trapezoidal belt cross-section centroid (measured from outer face).
        delta_r_cm = BELT_HEIGHT * (BELT_WIDTH_TOP + 2 * BELT_WIDTH_BOTTOM) / (
            3 * (BELT_WIDTH_TOP + BELT_WIDTH_BOTTOM)
        )
        r_out = self._get_radius(shift_distance) + BELT_HEIGHT / 2
        return r_out - delta_r_cm

    def calculate_integrated_normal_load(self, axial_force_total: float) -> float:
        """
        Get integrated normal load over wrap from total axial force (N_phi).

        Uses N_phi = 2 * F_ax * tan(beta), where beta is sheave half-angle.
        """
        return 2 * axial_force_total * np.tan(SHEAVE_ANGLE / 2)

    @abstractmethod
    def calculate_torque_bounds(
        self,
        state: SystemState,
        **kwargs,
    ) -> tuple[float, float]:
        """
        Calculate maximum transferable torque before belt slip.

        Uses Capstan equation (or Eytelwein formula) in an axial-load formulation.
        The pulley calculates its own axial force internally based on
        current operating conditions.

        The limiting torque depends on:
        - Belt-pulley friction (enhanced by V-groove wedging)
        - Wrap angle (more wrap = more capacity)
        - Total axial loading (sheave clamp + belt centrifugal contribution)
        - Effective radius

        Args:
            state: Current system state
            **kwargs: Optional implementation-specific parameters used by
                some pulley models (for example external load torque or
                equivalent side inertia terms).

        Returns:
            max_torque: Maximum torque capacity [N⋅m]
        """
        pass

    def get_pulley_state(self, state: SystemState, **kwargs) -> PulleyState:
        """
        Calculate complete pulley state (main entry point).

        This orchestrates the three core calculations in sequence:
        1. Calculate axial clamping force from the pulley mechanism
        2. Calculate axial centrifugal belt contribution
        3. Form total axial force
        4. Calculate max torque (Capstan equation)

        Args:
            state: Current system state
            **kwargs: Implementation-specific parameters (see calculate_axial_clamping_force)

        Returns:
            PulleyState with all forces, geometry, and detailed breakdown
        """
        # Step 1: Get mechanism-generated axial clamping force and breakdown
        axial_clamping_force, breakdown = self.calculate_axial_clamping_force(
            state, **kwargs
        )

        # Step 2: Axial centrifugal belt contribution
        axial_centrifugal_from_belt = self.axial_centrifugal_from_belt(state)

        # Step 3: Total axial force
        axial_force_total = axial_clamping_force + axial_centrifugal_from_belt

        # Get geometric properties
        wrap_angle = self._get_wrap_angle(state.shift_distance)
        radius = self._get_radius(state.shift_distance)
        angular_velocity = self._get_angular_velocity(state)
        angular_position = self._get_angular_position(state)

        # Package into PulleyForces
        forces = PulleyForces(
            axial_clamping_force=axial_clamping_force,
            axial_centrifugal_from_belt=axial_centrifugal_from_belt,
            axial_force_total=axial_force_total,
        )

        # Return complete state
        return PulleyState(
            forces=forces,
            wrap_angle=wrap_angle,
            radius=radius,
            angular_velocity=angular_velocity,
            angular_position=angular_position,
            breakdown=breakdown,
        )

    # Geometric helper methods - implemented by Primary/Secondary base classes
    @abstractmethod
    def _get_wrap_angle(self, shift_distance: float) -> float:
        """Get belt wrap angle at current shift position [rad]."""
        pass

    @abstractmethod
    def _get_radius(self, shift_distance: float) -> float:
        """Get effective pitch radius at current shift position [m]."""
        pass

    @abstractmethod
    def _get_radius_rate_of_change(self, shift_distance: float) -> float:
        """Get dr/dt at current shift position [m/m]."""
        pass

    @abstractmethod
    def _get_angular_velocity(self, state: SystemState) -> float:
        """Get pulley angular velocity [rad/s]."""
        pass

    @abstractmethod
    def _get_angular_position(self, state: SystemState) -> float:
        """Get pulley angular position [rad]."""
        pass
