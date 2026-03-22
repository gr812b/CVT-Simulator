import numpy as np
from cvt_simulator.models.pulley.secondary_pulley_interface import SecondaryPulleyModel
from cvt_simulator.models.pulley.pulley_interface import get_kwarg, get_required_kwarg
from cvt_simulator.models.dataTypes import (
    HelixForceBreakdown,
    SecondaryForceBreakdown,
    SecondaryTorqueBoundsBreakdown,
    SecondaryTorqueDenominatorBreakdown,
    SecondaryTorqueNumeratorBreakdown,
    SpringTorsForceBreakdown,
    springCompForceBreakdown,
)
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.constants.car_specs import (
    BELT_CROSS_SECTIONAL_AREA,
    MAX_SHIFT,
    HELIX_RADIUS,
    SHEAVE_ANGLE,
)
from cvt_simulator.constants.constants import RUBBER_DENSITY
from cvt_simulator.models.ramps import LinearSegment, PiecewiseRamp, ThetaRamp
from cvt_simulator.utils.system_state import SystemState


def create_default_helix_ramp() -> ThetaRamp:
    """
    Create the default helix geometry as a theta ramp.

    New convention:
    - s is axial shift distance [m]
    - u(s) = r_h * theta(s) is circumferential displacement [m]
    - tan(alpha_s) = 1 / (r_h * dtheta/ds)
    - equivalently: du/ds = cot(alpha_s)

    Segment angles passed to ThetaRamp are helix angles from circumferential.
    Default helix angle is alpha_s = 36°.

    Returns:
        ThetaRamp using a PiecewiseRamp that stores u(s)
    """
    helix_angle_deg = 36.0
    angle_ramp = PiecewiseRamp()
    angle_ramp.add_segment(LinearSegment(length=MAX_SHIFT, angle=helix_angle_deg))
    return ThetaRamp(angle_ramp, HELIX_RADIUS)


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
        ramp: ThetaRamp,  # Helix cam geometry
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
        self.theta_ramp = ramp

    def calculate_axial_clamping_force(
        self, state: SystemState, **kwargs
    ) -> tuple[float, SecondaryForceBreakdown]:
        """
        Calculate mechanism axial clamping force from helix torque feedback + spring forces.

        Implements equation 8.16:
        F_s,ax(s, τ_s) = [τ_s + k_s,0(θ_s,0 + θ_s(s)) * dθ_s/ds] / 2 + k_s,x(x_s,0 - s)

        Args:
            state: Current system state
            **kwargs: Expected key:
                - torque (float): Transmitted torque through CVT [N⋅m]

        Returns:
            tuple: (axial_clamping_force, detailed_breakdown)
        """
        shift_distance = np.clip(state.shift_distance, 0, MAX_SHIFT)

        # Extract torque from kwargs (required for torque-reactive secondary)
        torque = get_required_kwarg(
            kwargs,
            "torque",
            error_msg=(
                "PhysicalSecondaryPulley requires 'torque' parameter in kwargs. "
                "This is a torque-reactive pulley that needs transmitted torque to calculate clamping force."
            ),
        )

        # Calculate helix force from torque feedback (Eq. 8.16 helix term)
        helix_force_breakdown = self._calculate_helix_force(torque, shift_distance)

        # Calculate compression spring force (Eq. 8.16 axial spring term)
        spring_comp_force_breakdown = self._calculate_spring_comp_force(shift_distance)

        # Total axial clamping force
        axial_clamping_force = helix_force_breakdown.net + spring_comp_force_breakdown.net

        breakdown = SecondaryForceBreakdown(
            spring_comp_force_breakdown,
            helix_force_breakdown,
            axial_clamping_force,
        )

        return axial_clamping_force, breakdown

    def calculate_torque_bounds(
        self,
        state: SystemState,
        **kwargs,
    ) -> SecondaryTorqueBoundsBreakdown:
        """
        Calculate secondary traction torque bounds.

        Returns:
            SecondaryTorqueBoundsBreakdown with:
            - tau_negative / tau_positive limits [N·m]
            - numerator term decomposition
            - denominator decomposition for both +/- branches
        """
        shift_distance = np.clip(state.shift_distance, 0, MAX_SHIFT)
        angular_velocity = self._get_angular_velocity(state)

        # Geometry terms
        r_eff = self._get_radius(shift_distance)
        r_cm = self._get_belt_centroid_radius(shift_distance)
        cvt_ratio = tm.current_effective_cvt_ratio(shift_distance)

        # _get_radius_rate_of_change() gives dr/ds, so multiply by s_dot
        # to obtain the actual time derivative r_dot.
        r_cm_dot = (
            self._get_radius_rate_of_change(shift_distance) * state.shift_velocity
        )

        phi = self._get_wrap_angle(shift_distance)
        beta = SHEAVE_ANGLE / 2

        # Runtime dynamics terms
        tau_load = get_kwarg(kwargs, "external_load_torque", None)
        I_s = get_kwarg(kwargs, "secondary_inertia", None)
        if I_s is None or tau_load is None:
            raise ValueError("Both 'secondary_inertia' and 'external_load_torque' are required for secondary traction bounds")

        # Helix / spring terms
        dtheta_ds = self.theta_ramp.dtheta_dx(shift_distance)
        theta_total = self.initial_rotation + self.theta_ramp.theta(shift_distance)
        x_total = self.initial_compression - shift_distance

        spring_term = (
            dtheta_ds * self.spring_coeff_tors * theta_total
            + 2.0 * self.spring_coeff_comp * x_total
        )

        belt_mass_term = (
            RUBBER_DENSITY * BELT_CROSS_SECTIONAL_AREA * r_cm * phi
        )

        spring_numerator_term = self.μ * np.tan(beta) * spring_term
        load_numerator_term = belt_mass_term * ((r_cm * tau_load) / I_s)
        shift_numerator_term = belt_mass_term * (-2.0 * r_cm_dot * angular_velocity)
        common_numerator = (
            spring_numerator_term + load_numerator_term + shift_numerator_term
        )

        denominator_inverse_radius = 1.0 / r_eff
        denominator_helix_feedback = self.μ * np.tan(beta) * dtheta_ds
        denominator_inertial_feedback = belt_mass_term * r_cm / I_s

        positive_denominator = (
            denominator_inverse_radius
            - denominator_helix_feedback
            + denominator_inertial_feedback
        )

        negative_denominator = (
            denominator_inverse_radius
            + denominator_helix_feedback
            - denominator_inertial_feedback
        )

        tau_positive = (common_numerator / positive_denominator) / cvt_ratio
        tau_negative = (-common_numerator / negative_denominator) / cvt_ratio

        numerator_breakdown = SecondaryTorqueNumeratorBreakdown(
            spring_term=spring_numerator_term,
            load_term=load_numerator_term,
            shift_term=shift_numerator_term,
            net=common_numerator,
        )

        denominator_positive_breakdown = SecondaryTorqueDenominatorBreakdown(
            inverse_radius_term=denominator_inverse_radius,
            helix_feedback_term=-denominator_helix_feedback,
            inertial_feedback_term=denominator_inertial_feedback,
            net=positive_denominator,
        )

        denominator_negative_breakdown = SecondaryTorqueDenominatorBreakdown(
            inverse_radius_term=denominator_inverse_radius,
            helix_feedback_term=denominator_helix_feedback,
            inertial_feedback_term=-denominator_inertial_feedback,
            net=negative_denominator,
        )

        return SecondaryTorqueBoundsBreakdown(
            tau_negative=tau_negative,
            tau_positive=tau_positive,
            numerator=numerator_breakdown,
            denominator_positive=denominator_positive_breakdown,
            denominator_negative=denominator_negative_breakdown,
        )

    # Private helper methods

    def _calculate_helix_force(
        self, torque: float, shift_distance: float
    ) -> HelixForceBreakdown:
        """
        Calculate helix cam force from transmitted torque.

        Uses Eq. 8.16 helix term:
            F_s,helix,ax = [τ_s + k_s,0(θ_s,0 + θ_s(s)) * dθ_s/ds] / 2
        """
        shift_distance = np.clip(shift_distance, 0, MAX_SHIFT)

        spring_torque_breakdown = self._calculate_spring_tors_torque(shift_distance)
        angle_multiplier = self.theta_ramp.angle_multiplier(shift_distance)
        dtheta_ds = self.theta_ramp.dtheta_dx(shift_distance)
        helix_angle = np.arctan2(1.0, self.helix_radius * dtheta_ds)

        net = (torque + spring_torque_breakdown.net) * dtheta_ds / 2

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
        shift_distance = np.clip(shift_distance, 0, MAX_SHIFT)
        total_compression = self.initial_compression + shift_distance
        net = tm.hookes_law_comp(self.spring_coeff_comp, total_compression)

        return springCompForceBreakdown(
            compression=shift_distance,
            net=net,
        )

    def _calculate_spring_tors_torque(
        self, shift_distance: float
    ) -> SpringTorsForceBreakdown:
        """Calculate torsion spring torque from preload + ramp rotation."""
        shift_distance = np.clip(shift_distance, 0, MAX_SHIFT)

        rotation_from_shift = self.theta_ramp.theta(shift_distance)
        total_rotation = self.initial_rotation + rotation_from_shift
        net = tm.hookes_law_tors(self.spring_coeff_tors, total_rotation)

        return SpringTorsForceBreakdown(
            rotation=total_rotation,
            net=net,
        )
