import numpy as np
from cvt_simulator.models.pulley.secondary_pulley_interface import SecondaryPulleyModel
from cvt_simulator.models.pulley.pulley_interface import get_required_kwarg
from cvt_simulator.models.dataTypes import (
    HelixForceBreakdown,
    SecondaryForceBreakdown,
    SpringTorsForceBreakdown,
    springCompForceBreakdown,
)
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.constants.car_specs import (
    BELT_HEIGHT,
    MAX_SHIFT,
    HELIX_RADIUS,
    SHEAVE_ANGLE,
)
from cvt_simulator.models.ramps import LinearSegment, PiecewiseRamp
from cvt_simulator.utils.system_state import SystemState

def create_default_helix_ramp() -> PiecewiseRamp:
    """
    Create the default (linear) helix cam ramp geometry.
    
    This ramp has a constant angle throughout the shift range,
    providing consistent torque-to-force conversion.
    
    Returns:
        PiecewiseRamp with linear helix geometry
    """
    ramp = PiecewiseRamp()
    ramp.add_segment(
        LinearSegment(x_start=0, x_end=MAX_SHIFT, slope=-0.3)
    )
    return ramp


class PhysicalSecondaryPulley(SecondaryPulleyModel[SecondaryForceBreakdown]):
    """
    Helix-based secondary pulley implementation.
    
    This is the traditional torque-reactive secondary found in most mechanical CVTs.
    Torque transmitted through the CVT causes the helix cam to rotate, converting
    rotational torque into axial clamping force through the cam angle.
    
    Physics:
    - Transmitted torque causes cam rotation: τ → θ
    - Helix cam converts torque to axial force: F_axial = τ / (r * tan(helix_angle))
    - Torsion spring resists cam rotation and adds base clamping
    - Compression spring adds static clamping force
    - Net clamping: F_clamp = F_helix + F_torsion_spring + F_comp_spring
    
    This provides automatic torque feedback: more load = more clamping = better grip.
    """
    
    def __init__(
        self,
        spring_coeff_tors: float,  # Nm/rad - Torsion spring stiffness
        spring_coeff_comp: float,  # N/m - Compression spring stiffness
        initial_rotation: float,  # rad - Torsion spring preload
        initial_compression: float,  # m - Compression spring preload
        ramp: PiecewiseRamp = None,  # Helix cam geometry
    ):
        """
        Initialize physical secondary pulley with helix mechanism.
        
        Args:
            spring_coeff_tors: Torsion spring stiffness [N⋅m/rad]
            spring_coeff_comp: Compression spring stiffness [N/m]
            initial_rotation: Initial torsion spring preload [rad]
            initial_compression: Initial compression spring preload [m]
            ramp: Helix cam geometry (defaults to linear helix if None)
        """
        super().__init__()
        
        self.spring_coeff_tors = spring_coeff_tors
        self.spring_coeff_comp = spring_coeff_comp
        self.initial_rotation = initial_rotation
        self.initial_compression = initial_compression
        self.helix_radius = HELIX_RADIUS
        
        # Use provided ramp or create default
        self.ramp = ramp if ramp is not None else create_default_helix_ramp()
    
    def calculate_clamping_force(
        self, 
        state: SystemState, 
        **kwargs
    ) -> tuple[float, SecondaryForceBreakdown]:
        """
        Calculate clamping force from helix torque feedback + spring forces.
        
        Args:
            state: Current system state
            **kwargs: Expected key:
                - torque (float): Transmitted torque through CVT [N⋅m]
        
        Returns:
            tuple: (net_clamping_force, detailed_breakdown)
        """
        shift_distance = state.shift_distance
        
        # Extract torque from kwargs (required for torque-reactive secondary)
        torque = get_required_kwarg(
            kwargs, 
            'torque',
            error_msg=(
                "PhysicalSecondaryPulley requires 'torque' parameter in kwargs. "
                "This is a torque-reactive pulley that needs transmitted torque to calculate clamping force."
            )
        )
        
        # Calculate helix force from torque feedback
        helix_force_breakdown = self._calculate_helix_force(torque, shift_distance)
        
        # Calculate compression spring force (static clamping)
        spring_comp_force_breakdown = self._calculate_spring_comp_force(shift_distance)
        
        # Net clamping force (helix + compression spring)
        net_clamping_force = helix_force_breakdown.net + spring_comp_force_breakdown.net
        
        # Package detailed breakdown
        breakdown = SecondaryForceBreakdown(
            spring_comp_force_breakdown,
            helix_force_breakdown,
            net_clamping_force,
        )
        
        return net_clamping_force, breakdown
    
    def calculate_max_torque(
        self,
        state: SystemState,
    ) -> float:
        """
        Calculate maximum transferable torque using modified Capstan equation.
        
        For secondary, this is more complex because of torque feedback loop:
        - Torque creates clamping → clamping creates capacity → capacity limits torque
        - Must solve for equilibrium where T_max satisfies torque feedback
        
        See: docs/Kai's folder of derivations/t_maxSecondaryDerivation.png
        
        Args:
            state: Current system state
        
        Returns:
            max_torque: Maximum torque before slip [N⋅m]
        """
        shift_distance = state.shift_distance
        wrap_angle = self._get_wrap_angle(shift_distance)
        radius = self._get_radius(shift_distance)
        
        # Get spring forces (independent of torque)
        spring_comp_force = self._calculate_spring_comp_force(shift_distance).net

        # Use helix force calculation with zero torque to get torsion spring torque
        helix_breakdown = self._calculate_helix_force(0, shift_distance)
        spring_tors_torque = helix_breakdown.net

        # Convert to radial force contribution
        spring_force_term = (spring_comp_force + spring_tors_torque) * np.tan(SHEAVE_ANGLE / 2)
        
        # Centrifugal force contribution, used built in calc with 0 clamp (since we only need centrifugal)
        _, radial_from_centrifugal, _ = self.calculate_radial_force(state, 0)
        centrifugal_force = radial_from_centrifugal * wrap_angle / 2
        
        # Capstan term
        exp_term = np.exp(self.μ * wrap_angle)
        capstan_term = (wrap_angle / (4 * radius)) * (exp_term + 1) / (exp_term - 1)
        
        # Torque transmission term (feedback loop)
        cvt_ratio = tm.current_cvt_ratio(shift_distance)
        helix_angle = helix_breakdown.angle
        transmission_term = (
            2 * cvt_ratio * (HELIX_RADIUS * np.tan(helix_angle)) 
            * np.tan(SHEAVE_ANGLE / 2)
        )
        
        # Solve for max torque (equilibrium of torque feedback loop)
        numerator = centrifugal_force + spring_force_term
        denominator = capstan_term - transmission_term
        max_torque = numerator / denominator
        
        return max(0.0, max_torque)  # Ensure non-negative
    
    # Private helper methods for force calculations
    
    def _calculate_helix_force(
        self, torque: float, shift_distance: float
    ) -> HelixForceBreakdown:
        """
        Calculate helix cam force from transmitted torque.
        
        Helix converts rotational torque to axial force through cam angle.
        """
        # Clamp shift distance to valid range
        # TODO: Remove
        shift_distance = np.clip(shift_distance, 0, MAX_SHIFT)
        
        # Calculate torsion spring torque (resists cam rotation)
        spring_torque_breakdown = self._calculate_spring_tors_torque(shift_distance)
        
        # Effective radius at current shift position
        secondary_radius = tm.outer_sec_radius(shift_distance) - BELT_HEIGHT / 2
        
        # Helix angle at current position
        helix_angle = np.arctan(self.ramp.slope(shift_distance))
        
        # Convert torque to axial force through helix geometry
        # F = (τ + τ_spring) / (2 * tan(α) * r)
        angle_multiplier = 2 * np.tan(helix_angle) * secondary_radius
        
        # Net
        net = (torque + spring_torque_breakdown.net) / angle_multiplier
        
        return HelixForceBreakdown(
            feedbackTorque=torque,
            springTorque=spring_torque_breakdown,
            angle=helix_angle,
            radius=secondary_radius,
            angle_multiplier=angle_multiplier,
            net=net,
        )
    
    def _calculate_spring_comp_force(
        self, shift_distance: float
    ) -> springCompForceBreakdown:
        """Calculate compression spring force (static clamping)."""
        # Total compression = preload + shift distance
        total_compression = self.initial_compression + shift_distance
        
        # Hooke's law: F = k * x
        net = tm.hookes_law_comp(self.spring_coeff_comp, total_compression)
        
        return springCompForceBreakdown(
            compression=shift_distance,
            net=net,
        )
    
    def _calculate_spring_tors_torque(
        self, shift_distance: float
    ) -> SpringTorsForceBreakdown:
        """Calculate torsion spring torque (resists helix cam rotation)."""
        # Clamp shift distance to valid range
        # TODO: Remove
        shift_distance = np.clip(shift_distance, 0, MAX_SHIFT)
        
        # Calculate cam rotation from shift distance (approximation)
        # TODO: Improve relationship between shift and rotation
        rotation_from_shift = self._calculate_rotation(shift_distance)
        
        # Total rotation = preload + rotation from shift
        total_rotation = self.initial_rotation + rotation_from_shift
        
        # Hooke's law for torsion: τ = k * θ
        net = tm.hookes_law_tors(self.spring_coeff_tors, total_rotation)
        
        return SpringTorsForceBreakdown(
            rotation=total_rotation,
            net=net,
        )
    
    def _calculate_rotation(self, shift_distance: float) -> float:
        """
        Calculate helix cam rotation from shift distance.
        
        This is an approximation: rotation ≈ (shift * slope * 2) / helix_radius
        TODO: Improve this relationship based on actual cam geometry
        """
        return shift_distance * self.ramp.slope(shift_distance) * 2 / HELIX_RADIUS
