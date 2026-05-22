"""Primary pulley clamping helper (focused, no abstracts).

Exposes `PrimaryPulley.calculate_axial_clamping_force(shift, ω)` which returns
`(axial_force, PrimaryForceBreakdown)` and uses the existing datatypes.
"""
from cvt_simulator.ramps.piecewise_ramp import PiecewiseRamp
import numpy as np
from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY
from cvt_simulator.constants.car_specs import MAX_SHIFT, INITIAL_FLYWEIGHT_RADIUS
from cvt_simulator.sim_utils.system_state import SystemState
from cvt_simulator.core.data_types import (
    flyweightForceBreakdown,
    springCompForceBreakdown,
    PrimaryForceBreakdown,
    PulleyForces,
)
from cvt_simulator.core.components.belt_wrap import BeltWrap


class PrimaryPulley:
    """Compute primary pulley clamping (flyweight + spring).

    Parameters mirror the original component: spring coefficient, initial
    compression, flyweight mass, and a `ramp` providing `height()` and `slope()`.
    """

    def __init__(
        self,
        spring_coeff_comp: float,
        initial_compression: float,
        flyweight_mass: float,
        ramp: PiecewiseRamp,
        initial_flyweight_radius: float = INITIAL_FLYWEIGHT_RADIUS,
    ) -> None:
        self.spring_coeff_comp = spring_coeff_comp
        self.initial_compression = initial_compression
        self.flyweight_mass = flyweight_mass
        self.ramp = ramp
        self.initial_flyweight_radius = initial_flyweight_radius
        self.cvt = CVT_GEOMETRY
        # Initialize belt wrap helper once per pulley instance
        from cvt_simulator.core.components.belt_wrap import BeltWrap
        self.belt_wrap = BeltWrap(is_primary=True)

    def calculate_axial_clamping_force(self, state: SystemState) -> PulleyForces:
        s = float(np.clip(state.s, 0.0, MAX_SHIFT))

        ω_p = state.ω_p

        fly = self._calculate_flyweight_force(s, ω_p)
        spring = self._calculate_spring_comp_force(s)

        # belt wrap contribution (use initialized belt_wrap)
        belt = self.belt_wrap.axial_centrifugal_force(state)

        axial_pulley = fly.net - spring.net
        axial_total = axial_pulley + belt.axial_belt_force

        pulley_breakdown = PrimaryForceBreakdown(
            flyweightForce=fly, springForce=spring, net=axial_pulley
        )

        return PulleyForces(pulley_breakdown=pulley_breakdown, belt_wrap=belt, net=axial_total)

    def _calculate_flyweight_force(self, s: float, ω: float) -> flyweightForceBreakdown:
        """Compute flyweight centrifugal conversion using ramp slope.

        F_c = m * ω^2 * r_f
        axial contribution = F_c * dr_f/ds
        """
        flyweight_radius = self.initial_flyweight_radius + self.ramp.height(s)
        centrifugal_force = self.flyweight_mass * ω**2 * flyweight_radius
        ramp_gradient = self.ramp.slope(s)
        net = centrifugal_force * ramp_gradient
        angle = float(np.arctan(ramp_gradient))

        return flyweightForceBreakdown(
            radius=flyweight_radius,
            angular_velocity=ω,
            angle=angle,
            centrifugal_force=centrifugal_force,
            angle_multiplier=ramp_gradient,
            net=net,
        )

    def _calculate_spring_comp_force(self, s: float) -> springCompForceBreakdown:
        """Hooke's-law spring force resisting shift: F = k * (x0 + s)."""
        total_compression = self.initial_compression + s
        net = self.spring_coeff_comp * total_compression
        return springCompForceBreakdown(compression=s, net=net)

