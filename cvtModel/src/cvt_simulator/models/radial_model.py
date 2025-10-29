from typing import Union
import numpy as np
from cvt_simulator.constants.car_specs import (
    SHEAVE_ANGLE,
    BELT_HEIGHT,
    BELT_CROSS_SECTIONAL_AREA,
    GEARBOX_RATIO,
    WHEEL_RADIUS,
)
from cvt_simulator.constants.constants import RUBBER_DENSITY
from cvt_simulator.models.dataTypes import RadialPulleyForceBreakdown
from cvt_simulator.models.primary_pulley_model import PrimaryPulleyModel
from cvt_simulator.models.secondary_pulley_model import SecondaryPulleyModel
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.utils.system_state import SystemState


# Gets the overall radial force per pulley
class RadialPulleyModel:
    def __init__(
        self,
        primary: bool,
        pulley_model: Union[PrimaryPulleyModel, SecondaryPulleyModel],
    ):
        self.primary = primary
        self.pulley_model = pulley_model

    def get_breakdown(self, state: SystemState, torque: float):
        if self.primary:
            pulley_breakdown = self.pulley_model.get_breakdown(
                state.shift_distance, state.engine_angular_velocity
            )
        else:
            pulley_breakdown = self.pulley_model.get_breakdown(
                state.shift_distance, torque
            )

        (
            wrap_angle,
            radius,
            angular_velocity,
            radial_from_clamping,
            radial_from_centrifugal,
            net,
        ) = self._calculate_summed_radial_force(state, pulley_breakdown.net)

        return RadialPulleyForceBreakdown(
            pulleyForce=pulley_breakdown,
            wrap_angle=wrap_angle,
            radius=radius,
            angular_velocity=angular_velocity,
            radial_from_clamping=radial_from_clamping,
            radial_from_centrifugal=radial_from_centrifugal,
            net=net,
        )

    def _calculate_summed_radial_force(
        self,
        state: SystemState,
        clamp_force: float,
    ) -> float:
        wrap_angle = self._get_wrap_angle(state.shift_distance)
        radius = self._get_radius(state.shift_distance)
        angular_velocity = self._get_angular_velocity(state)

        radial_from_clamping = 2 * (clamp_force * np.tan(SHEAVE_ANGLE / 2)) / wrap_angle
        radial_from_centrifugal = (
            angular_velocity**2 * radius**2 * BELT_CROSS_SECTIONAL_AREA * RUBBER_DENSITY
        )

        net = (
            2
            * np.sin(wrap_angle / 2)
            * (radial_from_clamping + radial_from_centrifugal)
        )

        return (
            wrap_angle,
            radius,
            angular_velocity,
            radial_from_clamping,
            radial_from_centrifugal,
            net,
        )

    def _get_wrap_angle(self, shift_distance):
        if self.primary:
            return tm.primary_wrap_angle(shift_distance)
        else:
            return tm.secondary_wrap_angle(shift_distance)

    def _get_radius(self, shift_distance):
        if self.primary:
            return tm.outer_prim_radius(shift_distance) - BELT_HEIGHT / 2
        else:
            return tm.outer_sec_radius(shift_distance) - BELT_HEIGHT / 2

    def _get_angular_velocity(self, state: SystemState):
        if self.primary:
            return state.engine_angular_velocity
        else:
            wheel_to_sec_ratio = GEARBOX_RATIO / WHEEL_RADIUS
            return state.car_velocity * wheel_to_sec_ratio
