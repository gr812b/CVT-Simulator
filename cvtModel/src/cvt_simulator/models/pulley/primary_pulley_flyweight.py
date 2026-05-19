import numpy as np
from cvt_simulator.models.pulley.primary_pulley_interface import PrimaryPulleyModel
from cvt_simulator.models.pulley.pulley_interface import get_required_kwarg
from cvt_simulator.models.dataTypes import (
    PrimaryForceBreakdown,
    PrimaryTorqueBoundsBreakdown,
    PrimaryTorqueDenominatorBreakdown,
    PrimaryTorqueNumeratorBreakdown,
    flyweightForceBreakdown,
    springCompForceBreakdown,
)
from cvt_simulator.utils.conversions import inch_to_meter
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.models.ramps import (
    CircularSegment,
    LinearSegment,
    PiecewiseRamp,
)
from cvt_simulator.constants.car_specs import (
    BELT_CROSS_SECTIONAL_AREA,
    MAX_SHIFT,
    INITIAL_FLYWEIGHT_RADIUS,
    SHEAVE_ANGLE,
)
from cvt_simulator.constants.constants import RUBBER_DENSITY
from cvt_simulator.core.system_state import SystemState


# TODO: Remove this code
def create_default_flyweight_ramp() -> PiecewiseRamp:
    """
    Create the default (realistic) flyweight ramp geometry.

    This ramp has:
    - Linear start section (engagement)
    - Circular finish section (full shift)

    Returns:
        PiecewiseRamp with realistic geometry
    """
    ramp = PiecewiseRamp()

    # This is the default "Enman" ramp at McMaster baja

    # Linear section: ~0.125 inches at 25 degrees (from horizontal)
    line = LinearSegment(length=inch_to_meter(0.125), angle=25)

    # Circular section: remaining length
    # Approximating the original curve with a circular arc
    circle = CircularSegment(
        length=inch_to_meter(1.0),
        angle_start=33.4248111826,  # degrees (steeper at circle start)
        angle_end=20.8067910127,  # degrees
        quadrant=2,  # Mirrored Q3: positive slope while keeping steep-to-gentle shape
    )

    ramp.add_segment(line)
    ramp.add_segment(circle)

    return ramp


class PhysicalPrimaryPulley(PrimaryPulleyModel):
    """
    Flyweight-based primary pulley implementation.

    This is the traditional mechanical CVT primary found in most scooters and ATVs.
    Clamping force is generated purely from centrifugal force on flyweights,
    modulated by the ramp geometry.

    Physics:
    - Flyweights experience centrifugal force: F_c = m * ω² * r
    - Ramp converts flyweight motion directly to axial force through dr_f/ds
    - Spring opposes shift: F_spring = k * x
    - Net clamping: F_clamp = F_flyweight - F_spring
    """

    def __init__(
        self,
        spring_coeff_comp: float,  # N/m - Spring stiffness
        initial_compression: float,  # m - Spring preload
        flyweight_mass: float,  # kg - Mass of each flyweight
        ramp: PiecewiseRamp,  # Flyweight ramp geometry
    ):
        """
        Initialize physical primary pulley with flyweight mechanism.

        Args:
            spring_coeff_comp: Spring compression stiffness [N/m]
            initial_compression: Initial spring preload [m]
            flyweight_mass: Mass of each flyweight [kg]
            ramp: Flyweight ramp geometry
        """
        super().__init__()

        self.spring_coeff_comp = spring_coeff_comp
        self.initial_compression = initial_compression
        self.flyweight_mass = flyweight_mass
        self.initial_flyweight_radius = INITIAL_FLYWEIGHT_RADIUS
        self.ramp = ramp
        self._validate_primary_ramp_admissibility()

    def calculate_axial_clamping_force(
        self, state: SystemState, **kwargs
    ) -> tuple[float, PrimaryForceBreakdown]:
        """
        Calculate mechanism axial clamping force from flyweight force minus spring force.

        Args:
            state: Current system state
            **kwargs: Not used for physical primary (speed-reactive only)

        Returns:
            tuple: (axial_clamping_force, detailed_breakdown)
        """
        shift_distance = state.s
        # Primary pulley angular velocity is the engine speed
        primary_pulley_angular_velocity = state.ω_p

        # Calculate flyweight centrifugal force on ramp
        flyweight_force_breakdown = self._calculate_flyweight_force(
            shift_distance, primary_pulley_angular_velocity
        )

        # Calculate spring resistance
        spring_force_breakdown = self._calculate_spring_comp_force(shift_distance)

        # Mechanism-only axial clamping force (flyweight pushes, spring resists)
        axial_clamping_force = (
            flyweight_force_breakdown.net - spring_force_breakdown.net
        )

        # Package detailed breakdown
        breakdown = PrimaryForceBreakdown(
            flyweight_force_breakdown,
            spring_force_breakdown,
            axial_clamping_force,
        )

        return axial_clamping_force, breakdown

    # TODO: Use updated math here
    def calculate_torque_bounds(
        self,
        state: SystemState,
        is_stick: bool,
        v_b_star: float,
        T_b: float,
        **kwargs,
    ) -> PrimaryTorqueBoundsBreakdown:
        """
        Calculate primary traction torque bounds.

        Returns:
            PrimaryTorqueBoundsBreakdown with:
            - tau_lower / tau_upper limits [N·m]
            - numerator term decomposition
            - denominator decomposition for upper/lower branches
        """
        shift_distance = np.clip(state.s, 0, MAX_SHIFT)
        primary_angular_velocity = state.ω_p

        # Geometry terms
        r_eff = self._get_radius(shift_distance)
        r_cm = self._get_belt_centroid_radius(shift_distance)
        r_dot = self._get_radius_rate_of_change(shift_distance) * state.s_dot
        phi = self._get_wrap_angle(shift_distance)
        beta = SHEAVE_ANGLE / 2

        # Dynamic terms
        tau_eng = get_required_kwarg(kwargs, "engine_drive_torque")
        I_p = get_required_kwarg(kwargs, "primary_inertia")

        # This must be ONLY the mechanism clamping force term, not total force with belt corrections
        axial_clamping_force, _ = self.calculate_axial_clamping_force(state)

        belt_mass_term = RUBBER_DENSITY * BELT_CROSS_SECTIONAL_AREA * r_cm * phi
        μ_branch = self.μ_static if is_stick else self.μ_kinetic
        clamping_term = 2.0 * μ_branch * np.tan(beta) * axial_clamping_force

        if is_stick:
            load_term = -belt_mass_term * ((r_cm**2 * tau_eng) / I_p)
            shift_term = -belt_mass_term * (
                2.0 * r_cm * r_dot * primary_angular_velocity
            )
            numerator_net = r_eff * (clamping_term + load_term + shift_term)

            denominator_feedback = r_eff * belt_mass_term * ((r_cm**2) / I_p)
            upper_denominator = 1.0 - denominator_feedback
            lower_denominator = 1.0 + denominator_feedback

            tau_upper = numerator_net / upper_denominator
            tau_lower = -numerator_net / lower_denominator

            denominator_upper_breakdown = PrimaryTorqueDenominatorBreakdown(
                inverse_radius_term=1.0,
                inertial_feedback_term=-denominator_feedback,
                net=upper_denominator,
            )

            denominator_lower_breakdown = PrimaryTorqueDenominatorBreakdown(
                inverse_radius_term=1.0,
                inertial_feedback_term=denominator_feedback,
                net=lower_denominator,
            )
        else:
            load_term = -belt_mass_term * (r_cm * ((v_b_star - state.v_b) / T_b))
            shift_term = -belt_mass_term * (r_dot * state.v_b)
            numerator_net = r_eff * (clamping_term + load_term + shift_term)

            tau_upper = numerator_net
            tau_lower = -numerator_net

            denominator_upper_breakdown = PrimaryTorqueDenominatorBreakdown(
                inverse_radius_term=1.0,
                inertial_feedback_term=0.0,
                net=1.0,
            )

            denominator_lower_breakdown = PrimaryTorqueDenominatorBreakdown(
                inverse_radius_term=1.0,
                inertial_feedback_term=0.0,
                net=1.0,
            )

        numerator_breakdown = PrimaryTorqueNumeratorBreakdown(
            clamping_term=r_eff * clamping_term,
            load_term=r_eff * load_term,
            shift_term=r_eff * shift_term,
            net=numerator_net,
        )

        return PrimaryTorqueBoundsBreakdown(
            tau_lower=tau_lower,
            tau_upper=tau_upper,
            numerator=numerator_breakdown,
            denominator_upper=denominator_upper_breakdown,
            denominator_lower=denominator_lower_breakdown,
        )

    # Private helper methods for force calculations

    def _calculate_flyweight_force(
        self, shift_distance: float, angular_velocity: float
    ) -> flyweightForceBreakdown:
        """Calculate flyweight centrifugal force and conversion through ramp."""
        # Clamp shift distance to valid range
        # TODO: Remove extra clamp
        shift_distance = np.clip(shift_distance, 0, MAX_SHIFT)

        # Height is modeled as additional radial displacement from center.
        flyweight_radius = self.initial_flyweight_radius + self.ramp.height(
            shift_distance
        )

        # Centrifugal force on flyweight: F = m * ω² * r
        centrifugal_force = tm.centrifugal_force(
            self.flyweight_mass,
            angular_velocity,
            flyweight_radius,
        )

        # Ramp derivative dr_f/ds at current position.
        ramp_gradient = self.ramp.slope(shift_distance)

        # F_p,ax = m_f * omega_p^2 * (r_f,0 + r_f(s)) * dr_f/ds
        net = centrifugal_force * ramp_gradient

        # Retain angle output for debug/plots while using derivative for force law.
        angle = np.arctan(ramp_gradient)

        return flyweightForceBreakdown(
            radius=flyweight_radius,
            angular_velocity=angular_velocity,
            angle=angle,
            centrifugal_force=centrifugal_force,
            angle_multiplier=ramp_gradient,
            net=net,
        )

    def _validate_primary_ramp_admissibility(self) -> None:
        """Validate primary ramp profile constraints for r_f(s)."""
        if not self.ramp.segments:
            raise ValueError("Primary ramp must contain at least one segment")

        for segment in self.ramp.segments:
            sample_points = [
                segment.x_start,
                (segment.x_start + segment.x_end) / 2,
                segment.x_end,
            ]
            for x in sample_points:
                slope = self.ramp.slope(x)
                if not np.isfinite(slope):
                    raise ValueError(
                        f"Primary ramp slope must be finite on [0, {MAX_SHIFT}], got {slope} at x={x}."
                    )
                if slope < 0:
                    raise ValueError(
                        f"Primary ramp slope must be non-negative on [0, {MAX_SHIFT}], got {slope} at x={x}."
                    )

                angle_deg = np.degrees(np.arctan(slope))
                if angle_deg < 0 or angle_deg >= 90:
                    raise ValueError(
                        "Primary ramp angle must be in [0, 90) degrees from horizontal; "
                        f"got {angle_deg} degrees at x={x}."
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
