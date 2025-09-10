import numpy as np
import math
from models.dataTypes import BeltCentrifugalForceBreakdown
from utils.theoretical_models import TheoreticalModels as tm
from constants.car_specs import BELT_CROSS_SECTIONAL_AREA, BELT_HEIGHT
from constants.constants import (
    RUBBER_DENSITY,
    RUBBER_ALUMINUM_STATIC_FRICTION,
    RUBBER_ALUMINUM_KINETIC_FRICTION,
)

# Centrifugal force of the belt
class BeltModel:
    def __init__(
        self,
        primary: bool,
    ):
        self.primary = primary
        self.μ_static = RUBBER_ALUMINUM_STATIC_FRICTION
        self.μ_kinetic = RUBBER_ALUMINUM_KINETIC_FRICTION

    def get_breakdown(
        self, ω: float, shift_distance: float
    ) -> BeltCentrifugalForceBreakdown:
        radius = self._get_radius(shift_distance)
        wrap_angle = self._get_wrap_angle(shift_distance)
        length = radius * wrap_angle
        mass = RUBBER_DENSITY * BELT_CROSS_SECTIONAL_AREA * length

        # print(f"Primary: {self.primary}, Length: {length}, Wrap angle: {wrap_angle}, Radius: {radius}, Mass: {mass}, Total Mass:")
        net = tm.centrifugal_force(mass, ω, radius)
        return BeltCentrifugalForceBreakdown(
            mass,
            radius,
            wrap_angle,
            ω,
            net,
        )
    
    def _get_radius(self, shift_distance):
        if self.primary:
            return tm.outer_prim_radius(shift_distance) - BELT_HEIGHT / 2
        else:
            return tm.outer_sec_radius(shift_distance) - BELT_HEIGHT / 2

    def _get_wrap_angle(self, shift_distance):
        if self.primary:
            return tm.primary_wrap_angle(shift_distance)
        else:
            return tm.secondary_wrap_angle(shift_distance)



    ## TODO: UNUSED METHODS
    def calculate_slack_tension(
        self,
        radial_force: float,
        wrap_angle: float,
        μ: float,
    ) -> float:
        θ = abs((wrap_angle - np.pi) / 2)
        denominator = np.cos(θ) * (
            1 + math.exp(μ * wrap_angle)
        )  # Derived from tension, angles and capstan equation
        return radial_force / denominator

    def calculate_max_transferable_torque(
        self, tension: float, μ: float, wrap_angle: float, radius: float
    ) -> float:
        return tension * radius * (np.exp(μ * wrap_angle) - 1)
