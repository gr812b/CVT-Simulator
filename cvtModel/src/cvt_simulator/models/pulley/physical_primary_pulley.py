import math
import numpy as np
from cvt_simulator.models.pulley.primary_pulley_interface import PrimaryPulleyModel
from cvt_simulator.models.pulley.pulley_interface import get_kwarg
from cvt_simulator.models.dataTypes import (
    PrimaryForceBreakdown,
    flyweightForceBreakdown,
    springCompForceBreakdown,
)
from cvt_simulator.utils.conversions import inch_to_meter
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.models.ramps import (
    CircularSegment,
    CubicSpiralZeroK1,
    LinearSegment,
    PiecewiseRamp,
)
from cvt_simulator.constants.car_specs import (
    MAX_SHIFT,
    INITIAL_FLYWEIGHT_RADIUS,
    SHEAVE_ANGLE,
    BELT_CROSS_SECTIONAL_AREA,
)
from cvt_simulator.constants.constants import (
    RUBBER_DENSITY,
    RUBBER_ALUMINUM_STATIC_FRICTION,
)
from cvt_simulator.utils.system_state import SystemState


def create_default_flyweight_ramp() -> PiecewiseRamp:
    """
    Create the default (realistic) flyweight ramp geometry.
    
    This ramp has:
    - Linear start section (engagement)
    - Smooth cubic spiral transition
    - Circular finish (full shift)
    
    Returns:
        PiecewiseRamp with realistic geometry
    """
    length = inch_to_meter(1.125)
    curveLength = inch_to_meter(0.025)
    
    ramp = PiecewiseRamp()
    
    line = LinearSegment(
        x_start=0, 
        x_end=inch_to_meter(0.125), 
        slope=math.tan(math.radians(-25))
    )
    circle = CircularSegment(
        x_start=line.x_end + curveLength,
        x_end=length,
        radius=(inch_to_meter(5)) ** 2,
        theta_start=0.971816735418,
        theta_end=1.1984521248,
    )
    cubicCircleLine = CubicSpiralZeroK1(
        x_start=line.x_end,
        x_end=line.x_end + curveLength,
        slope_start=line.slope(line.x_end),
        slope_end=circle.slope(circle.x_start),
        target_curvature=1 / inch_to_meter(5),
    )
    
    ramp.add_segment(line)
    ramp.add_segment(cubicCircleLine)
    ramp.add_segment(circle)
    
    return ramp


class PhysicalPrimaryPulley(PrimaryPulleyModel[PrimaryForceBreakdown]):
    """
    Flyweight-based primary pulley implementation.
    
    This is the traditional mechanical CVT primary found in most scooters and ATVs.
    Clamping force is generated purely from centrifugal force on flyweights,
    modulated by the ramp geometry.
    
    Physics:
    - Flyweights experience centrifugal force: F_c = m * ω² * r
    - Ramp converts radial force to axial: F_axial = F_c * tan(ramp_angle)
    - Spring opposes shift: F_spring = k * x
    - Net clamping: F_clamp = F_flyweight - F_spring
    """
    
    def __init__(
        self,
        spring_coeff_comp: float,  # N/m - Spring stiffness
        initial_compression: float,  # m - Spring preload
        flyweight_mass: float,  # kg - Mass of each flyweight
        ramp: PiecewiseRamp = None,  # Flyweight ramp geometry
    ):
        """
        Initialize physical primary pulley with flyweight mechanism.
        
        Args:
            spring_coeff_comp: Spring compression stiffness [N/m]
            initial_compression: Initial spring preload [m]
            flyweight_mass: Mass of each flyweight [kg]
            ramp: Flyweight ramp geometry (defaults to realistic ramp if None)
        """
        super().__init__()
        
        self.spring_coeff_comp = spring_coeff_comp
        self.initial_compression = initial_compression
        self.flyweight_mass = flyweight_mass
        self.initial_flyweight_radius = INITIAL_FLYWEIGHT_RADIUS
        
        # Use provided ramp or create default
        self.ramp = ramp if ramp is not None else create_default_flyweight_ramp()
    
    def calculate_clamping_force(
        self, 
        state: SystemState, 
        **kwargs
    ) -> tuple[float, PrimaryForceBreakdown]:
        """
        Calculate clamping force from flyweight centrifugal force minus spring force.
        
        Args:
            state: Current system state
            **kwargs: Not used for physical primary (speed-reactive only)
        
        Returns:
            tuple: (net_clamping_force, detailed_breakdown)
        """
        shift_distance = state.shift_distance
        angular_velocity = state.engine_angular_velocity
        
        # Calculate flyweight centrifugal force on ramp
        flyweight_force_breakdown = self._calculate_flyweight_force(
            shift_distance, angular_velocity
        )
        
        # Calculate spring resistance
        spring_force_breakdown = self._calculate_spring_comp_force(shift_distance)
        
        # Net clamping force (flyweight pushes, spring resists)
        net_clamping_force = flyweight_force_breakdown.net - spring_force_breakdown.net
        
        # Package detailed breakdown
        breakdown = PrimaryForceBreakdown(
            flyweight_force_breakdown,
            spring_force_breakdown,
            net_clamping_force,
        )
        
        return net_clamping_force, breakdown
    
    def calculate_max_torque(
        self,
        state: SystemState,
        radial_force: float,
    ) -> float:
        """
        Calculate maximum transferable torque using Capstan equation.
        
        Args:
            state: Current system state
            radial_force: Total radial force on belt [N]
        
        Returns:
            max_torque: Maximum torque before slip [N⋅m]
        """
        wrap_angle = self._get_wrap_angle(state.shift_distance)
        radius = self._get_radius(state.shift_distance)
        
        # Capstan equation with V-belt friction enhancement
        exp_term = math.exp(self.μ * wrap_angle)
        capstan_term = (exp_term - 1) / (exp_term + 1)
        radial_force_term = radial_force * radius / np.sin(wrap_angle / 2)
        
        max_torque = capstan_term * radial_force_term
        
        return max(0.0, max_torque)  # Ensure non-negative
    
    # Private helper methods for force calculations
    
    def _calculate_flyweight_force(
        self, shift_distance: float, angular_velocity: float
    ) -> flyweightForceBreakdown:
        """Calculate flyweight centrifugal force and conversion through ramp."""
        # Clamp shift distance to valid range
        shift_distance = np.clip(shift_distance, 0, MAX_SHIFT)
        
        # Calculate flyweight radius at current shift position
        flyweight_radius = self.initial_flyweight_radius + self.ramp.height(shift_distance)
        
        # Centrifugal force on flyweight: F = m * ω² * r
        centrifugal_force = tm.centrifugal_force(
            self.flyweight_mass,
            angular_velocity,
            flyweight_radius,
        )
        
        # Ramp angle at current position
        angle = np.arctan(self.ramp.slope(shift_distance))
        
        # Convert centrifugal force to axial clamping force through ramp angle
        net = centrifugal_force * np.tan(angle)
        
        return flyweightForceBreakdown(
            radius=flyweight_radius,
            angular_velocity=angular_velocity,
            angle=angle,
            centrifugal_force=centrifugal_force,
            angle_multiplier=np.tan(angle),
            net=net,
        )
    
    def _calculate_spring_comp_force(
        self, shift_distance: float
    ) -> springCompForceBreakdown:
        """Calculate spring resistance force (opposes shifting)."""
        # Total compression = preload + shift distance
        total_compression = self.initial_compression + shift_distance
        
        # Hooke's law: F = k * x
        net = tm.hookes_law_comp(self.spring_coeff_comp, total_compression)
        
        return springCompForceBreakdown(
            compression=shift_distance,
            net=net,
        )
