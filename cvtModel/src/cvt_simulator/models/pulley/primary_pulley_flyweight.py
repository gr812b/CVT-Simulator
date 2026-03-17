import math
import numpy as np
from cvt_simulator.models.pulley.primary_pulley_interface import PrimaryPulleyModel
from cvt_simulator.models.dataTypes import (
    PrimaryForceBreakdown,
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
    MAX_SHIFT,
    INITIAL_FLYWEIGHT_RADIUS,
)
from cvt_simulator.utils.system_state import SystemState


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

    # Linear section: ~0.125 inches at -25 degrees
    line = LinearSegment(length=inch_to_meter(0.125), angle=-25)

    # Circular section: remaining length
    # Approximating the original curve with a circular arc
    circle = CircularSegment(
        length=inch_to_meter(1.0),
        angle_start=33.4248111826,  # degrees
        angle_end=20.8067910127,  # degrees
        quadrant=3,  # Negative slopes
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
        shift_distance = state.shift_distance
        # Primary pulley angular velocity is the engine speed
        primary_pulley_angular_velocity = state.primary_pulley_angular_velocity

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
    def calculate_max_torque(
        self,
        state: SystemState,
        **kwargs,
    ) -> float:
        """
        Calculate maximum transferable torque using Capstan equation.

        Calculates torque capacity directly from current axial clamping force.

        Args:
            state: Current system state

        Returns:
            max_torque: Maximum torque before slip [N⋅m]
        """
        # Calculate axial force components internally
        axial_clamping_force, _ = self.calculate_axial_clamping_force(state)
        axial_force_total = (
            axial_clamping_force + self.axial_centrifugal_from_belt(state)
        )

        # Get geometric properties
        wrap_angle = self._get_wrap_angle(state.shift_distance)
        radius = self._get_radius(state.shift_distance)

        # Capstan equation with axial normal-load formulation
        # N_phi = 2 * F_ax * tan(beta)
        n_phi = self.calculate_integrated_normal_load(axial_force_total)
        exp_term = math.exp(self.μ * wrap_angle)
        capstan_term = (exp_term - 1) / (exp_term + 1)
        max_torque = capstan_term * (2 * radius / wrap_angle) * n_phi

        return max(0.0, max_torque)  # Ensure non-negative

    # Private helper methods for force calculations

    def _calculate_flyweight_force(
        self, shift_distance: float, angular_velocity: float
    ) -> flyweightForceBreakdown:
        """Calculate flyweight centrifugal force and conversion through ramp."""
        # Clamp shift distance to valid range
        # TODO: Remove extra clamp
        shift_distance = np.clip(shift_distance, 0, MAX_SHIFT)

        # Calculate flyweight radius at current shift position
        # Ramp starts at 0 and goes negative, so subtract
        flyweight_radius = self.initial_flyweight_radius - self.ramp.height(
            shift_distance
        )

        # Centrifugal force on flyweight: F = m * ω² * r
        centrifugal_force = tm.centrifugal_force(
            self.flyweight_mass,
            angular_velocity,
            flyweight_radius,
        )

        # Ramp derivative dr_f/ds at current position.
        # For current ramp representation r_f(s) = -height(s), so dr_f/ds = -slope(s).
        ramp_gradient = -self.ramp.slope(shift_distance)

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
