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
    MAX_SHIFT,
    HELIX_RADIUS,
)
from cvt_simulator.models.ramps import LinearSegment, PiecewiseRamp
from cvt_simulator.utils.system_state import SystemState


# TODO: Remove this code
def create_default_helix_ramp() -> PiecewiseRamp:
    """
    Create the default (linear) helix cam ramp geometry.

    For the helix ramp, the HEIGHT (y) represents shift distance,
    and we need to be able to invert it to find x for a given height.

    This means the ramp should span from height 0 to MAX_SHIFT.

    Returns:
        PiecewiseRamp with linear helix geometry
    """
    ramp = PiecewiseRamp()
    # Create a linear segment where y goes from 0 to MAX_SHIFT
    # Using negative angle so slope is negative (helix ramps down)
    ramp.add_segment(LinearSegment(length=MAX_SHIFT / 0.3, angle=-16.699))
    return ramp


class PhysicalSecondaryPulley(SecondaryPulleyModel):
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
        ramp: PiecewiseRamp,  # Helix cam geometry
    ):
        """
        Initialize physical secondary pulley with helix mechanism.

        Args:
            spring_coeff_tors: Torsion spring stiffness [N⋅m/rad]
            spring_coeff_comp: Compression spring stiffness [N/m]
            initial_rotation: Initial torsion spring preload [rad]
            initial_compression: Initial compression spring preload [m]
            ramp: Helix cam geometry
        """
        super().__init__()

        self.spring_coeff_tors = spring_coeff_tors
        self.spring_coeff_comp = spring_coeff_comp
        self.initial_rotation = initial_rotation
        self.initial_compression = initial_compression
        self.helix_radius = HELIX_RADIUS
        # This ramp needs to have a unique x for every height
        self.ramp = ramp

    def calculate_axial_clamping_force(
        self, state: SystemState, **kwargs
    ) -> tuple[float, SecondaryForceBreakdown]:
        """
        Calculate mechanism axial clamping force from helix torque feedback + spring forces.

        Args:
            state: Current system state
            **kwargs: Expected key:
                - torque (float): Transmitted torque through CVT [N⋅m]

        Returns:
            tuple: (axial_clamping_force, detailed_breakdown)
        """
        shift_distance = state.shift_distance

        # Extract torque from kwargs (required for torque-reactive secondary)
        torque = get_required_kwarg(
            kwargs,
            "torque",
            error_msg=(
                "PhysicalSecondaryPulley requires 'torque' parameter in kwargs. "
                "This is a torque-reactive pulley that needs transmitted torque to calculate clamping force."
            ),
        )

        # Calculate helix force from torque feedback
        helix_force_breakdown = self._calculate_helix_force(torque, shift_distance)

        # Calculate compression spring force (static clamping)
        spring_comp_force_breakdown = self._calculate_spring_comp_force(shift_distance)

        # Mechanism-only axial clamping force (helix + compression spring)
        axial_clamping_force = (
            helix_force_breakdown.net
            + spring_comp_force_breakdown.net
        )

        # Package detailed breakdown
        breakdown = SecondaryForceBreakdown(
            spring_comp_force_breakdown,
            helix_force_breakdown,
            axial_clamping_force,
        )

        return axial_clamping_force, breakdown

    # TODO: Use updated math here
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
        cvt_ratio = tm.current_cvt_ratio(shift_distance)

        # Solve T = T_capacity(T) because secondary clamping is torque-reactive.
        torque_guess = 0.0
        for _ in range(40):
            sec_torque = torque_guess * cvt_ratio
            axial_clamping_force, _ = self.calculate_axial_clamping_force(
                state, torque=sec_torque
            )
            axial_force_total = (
                axial_clamping_force + self.axial_centrifugal_from_belt(state)
            )
            n_phi = self.calculate_integrated_normal_load(axial_force_total)

            exp_term = np.exp(self.μ * wrap_angle)
            capstan_term = (exp_term - 1) / (exp_term + 1)
            sec_torque_capacity = max(0.0, capstan_term * (2 * radius / wrap_angle) * n_phi)
            prim_torque_capacity = (
                sec_torque_capacity / cvt_ratio if cvt_ratio > 1e-9 else sec_torque_capacity
            )

            # Damped fixed-point update for stability.
            next_guess = 0.5 * torque_guess + 0.5 * prim_torque_capacity
            if abs(next_guess - torque_guess) < 1e-6:
                torque_guess = next_guess
                break
            torque_guess = next_guess

        return max(0.0, torque_guess)

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

        # Helix rotation gradient dtheta_s/ds at current shift.
        theta_gradient = self._calculate_theta_gradient(shift_distance)

        # Helix angle is retained for debug outputs.
        helix_angle = np.arctan2(1.0, HELIX_RADIUS * theta_gradient)

        # F_s,helix,ax = ((tau_s + tau_spring) / 2) * dtheta_s/ds
        angle_multiplier = theta_gradient
        net = ((torque + spring_torque_breakdown.net) / 2) * angle_multiplier

        return HelixForceBreakdown(
            feedbackTorque=torque,
            springTorque=spring_torque_breakdown,
            angle=helix_angle,
            radius=self.helix_radius,
            angle_multiplier=angle_multiplier,
            net=net,
        )

    def _calculate_spring_comp_force(
        self, shift_distance: float
    ) -> springCompForceBreakdown:
        """Calculate compression spring force (static clamping)."""
        # Axial spring weakens as shift increases: x = x_0 - s
        total_compression = self.initial_compression - shift_distance

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

    def _calculate_theta_gradient(self, shift_distance: float) -> float:
        """Calculate dtheta_s/ds from current helix ramp mapping."""
        shift_distance = np.clip(shift_distance, 0, MAX_SHIFT)

        x_position = self.ramp.find_x_at_height(-shift_distance)
        slope_at_x = self.ramp.slope(x_position)
        if abs(slope_at_x) < 1e-9:
            return 0.0

        # y = height(x) = -s => ds/dx = -dy/dx = -slope, so dx/ds = -1/slope.
        return (-1.0 / slope_at_x) / HELIX_RADIUS

    def _calculate_rotation(self, shift_distance: float) -> float:
        """
        Calculate helix cam rotation from shift distance.

        Args:
            shift_distance: Current shift distance [m] (this is the ramp HEIGHT)

        Returns:
            Rotation angle [rad]
        """
        # Find x position that corresponds to this height
        x_position = self.ramp.find_x_at_height(-shift_distance)
        # Get slope at that x position
        return x_position / HELIX_RADIUS
