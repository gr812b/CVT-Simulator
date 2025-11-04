"""
Abstract interfaces for CVT pulley models.

This module defines the core contracts that all pulley implementations must satisfy,
allowing different control strategies (physical models, PID controllers, lookup tables, etc.)
to be swapped without changing the rest of the simulation.

Key Design Principles:
- Each pulley must provide: clamping force, radial force, and max torque
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
from cvt_simulator.constants.car_specs import (
    SHEAVE_ANGLE,
    BELT_CROSS_SECTIONAL_AREA,
)
from cvt_simulator.constants.constants import RUBBER_DENSITY, RUBBER_ALUMINUM_STATIC_FRICTION
from cvt_simulator.models.dataTypes import PulleyState, PulleyForces, PulleyBreakdowns

def get_kwarg(
    kwargs: dict[str, Any], 
    key: str, 
    default: Any = None
) -> Any:
    """
    Helper function to safely extract optional kwargs with defaults.
    
    Usage in implementations:
        # Optional with default
        load_factor = get_kwarg(kwargs, 'load_factor', 1.0)
        
        # Optional with None default
        target_rpm = get_kwarg(kwargs, 'target_rpm')
    
    Args:
        kwargs: The kwargs dict from calculate_clamping_force
        key: The parameter name to extract
        default: Default value if key not found (default: None)
    
    Returns:
        The value from kwargs or the default
    """
    return kwargs.get(key, default)


def get_required_kwarg(
    kwargs: dict[str, Any], 
    key: str,
    error_msg: str = None
) -> Any:
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
        kwargs: The kwargs dict from calculate_clamping_force
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
    can provide the required outputs (clamping force, radial force, max torque).
    """
    
    def __init__(self):
        """Initialize pulley model with V-belt friction coefficient."""
        # Calculate friction coefficient with V-belt wedging effect
        # The sheave angle enhances friction through wedging action
        self.μ = RUBBER_ALUMINUM_STATIC_FRICTION / np.sin(SHEAVE_ANGLE / 2)
    
    @abstractmethod
    def calculate_clamping_force(
        self, 
        state: SystemState,
        **kwargs
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
            tuple: (clamping_force, breakdown)
                - clamping_force: Net axial force [N]
                - breakdown: Implementation-specific detailed breakdown
        """
        pass
    
    def calculate_radial_force(
        self,
        state: SystemState,
        clamping_force: float,
    ) -> tuple[float, float, float]:
        """
        Calculate total radial force on belt from clamping and centrifugal effects.
        
        This implements the fundamental physics of V-belt operation (same for all pulleys):
        1. Clamping force → radial force through sheave angle
        2. Belt centrifugal tension adds to radial force
        3. Combined radial force determines friction and torque capacity
        
        See: docs/Kai's folder of derivations/ShiftingAndSlip.png
        
        Args:
            state: Current system state
            clamping_force: Axial clamping force [N]
        
        Returns:
            tuple: (radial_from_clamping, radial_from_centrifugal, total_radial)
                - radial_from_clamping: Radial force from pulley clamping [N]
                - radial_from_centrifugal: Radial force from belt rotation [N]
                - total_radial: Sum of both components [N]
        """
        wrap_angle = self._get_wrap_angle(state.shift_distance)
        radius = self._get_radius(state.shift_distance)
        angular_velocity = self._get_angular_velocity(state)
        
        # Radial force from pulley clamping (through V-belt wedging)
        radial_from_clamping = 2 * (clamping_force * np.tan(SHEAVE_ANGLE / 2)) / wrap_angle
        
        # Radial force from belt centrifugal tension
        radial_from_centrifugal = (
            angular_velocity**2 * radius**2 * BELT_CROSS_SECTIONAL_AREA * RUBBER_DENSITY
        )
        
        # Total radial force (determines friction capacity)
        total_radial = (
            2 * np.sin(wrap_angle / 2) * (radial_from_clamping + radial_from_centrifugal)
        )
        
        return radial_from_clamping, radial_from_centrifugal, total_radial
    
    @abstractmethod
    def calculate_max_torque(
        self,
        state: SystemState,
    ) -> float:
        """
        Calculate maximum transferable torque before belt slip.
        
        Uses Capstan equation (or Eytelwein formula) modified for V-belts.
        The pulley calculates its own radial force internally based on
        its current clamping force and operating conditions.
        
        The limiting torque depends on:
        - Belt-pulley friction (enhanced by V-groove wedging)
        - Wrap angle (more wrap = more capacity)
        - Radial tension (from clamping + centrifugal)
        - Effective radius
        
        Args:
            state: Current system state
        
        Returns:
            max_torque: Maximum torque capacity [N⋅m]
        """
        pass
    
    def get_pulley_state(
        self,
        state: SystemState,
        **kwargs
    ) -> PulleyState:
        """
        Calculate complete pulley state (main entry point).
        
        This orchestrates the three core calculations in sequence:
        1. Calculate clamping force (mechanism-specific)
        2. Calculate radial force (physics-based)
        3. Calculate max torque (Capstan equation)
        
        Args:
            state: Current system state
            **kwargs: Implementation-specific parameters (see calculate_clamping_force)
        
        Returns:
            PulleyState with all forces, geometry, and detailed breakdown
        """
        # Step 1: Get clamping force and breakdown
        clamping_force, breakdown = self.calculate_clamping_force(state, **kwargs)
        
        # Step 2: Calculate radial force components
        radial_from_clamping, radial_from_centrifugal, total_radial = \
            self.calculate_radial_force(state, clamping_force)
        
        # Step 3: Calculate max transferable torque (pulley calculates its own radial force)
        max_torque = self.calculate_max_torque(state)
        
        # Get geometric properties
        wrap_angle = self._get_wrap_angle(state.shift_distance)
        radius = self._get_radius(state.shift_distance)
        angular_velocity = self._get_angular_velocity(state)
        
        # Package into PulleyForces
        forces = PulleyForces(
            clamping_force=clamping_force,
            radial_force=total_radial,
            max_torque=max_torque,
        )
        
        # Return complete state
        return PulleyState(
            forces=forces,
            wrap_angle=wrap_angle,
            radius=radius,
            angular_velocity=angular_velocity,
            radial_from_clamping=radial_from_clamping,
            radial_from_centrifugal=radial_from_centrifugal,
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
    def _get_angular_velocity(self, state: SystemState) -> float:
        """Get pulley angular velocity [rad/s]."""
        pass
