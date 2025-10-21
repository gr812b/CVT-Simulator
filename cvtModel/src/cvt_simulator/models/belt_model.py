import numpy as np
import math
from cvt_simulator.models.dataTypes import BeltCentrifugalForceBreakdown
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.constants.car_specs import BELT_CROSS_SECTIONAL_AREA, BELT_HEIGHT
from cvt_simulator.constants.constants import (
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

        # TODO: If this is secondary, multiple by CVT ratio for new angular velocity
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


