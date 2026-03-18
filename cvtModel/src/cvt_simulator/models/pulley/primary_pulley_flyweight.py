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
        shift_distance = np.clip(state.shift_distance, 0, MAX_SHIFT)
        angular_velocity = self._get_angular_velocity(state)

        # Geometry terms in the updated relation.
        # - r_eff: effective pitch radius
        # - r_cm: belt centroid radius (all other r terms)
        r_eff = self._get_radius(shift_distance)
        r_cm = self._get_belt_centroid_radius(shift_distance)
        r_dot = self._get_radius_rate_of_change(shift_distance)
        phi = self._get_wrap_angle(shift_distance)
        beta = SHEAVE_ANGLE / 2

        # Runtime dynamics terms supplied by system models.
        tau_eng = get_kwarg(kwargs, "engine_drive_torque", 0.0)
        I_p = get_kwarg(kwargs, "primary_inertia", 1.0)

        # Mechanism clamping contribution F_ax in the updated primary equation.
        axial_clamping_force, _ = self.calculate_axial_clamping_force(state)

        belt_mass_term = RUBBER_DENSITY * BELT_CROSS_SECTIONAL_AREA * r_cm * phi

        numerator = (2 * self.μ * axial_clamping_force * np.tan(beta)) - (
            belt_mass_term * (((r_cm * tau_eng) / I_p) - (2 * r_dot * angular_velocity))
        )

        denominator = (1.0 / r_eff) - (belt_mass_term * r_cm / I_p)

        return numerator / denominator

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
            sample_points = [segment.x_start, (segment.x_start + segment.x_end) / 2, segment.x_end]
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
