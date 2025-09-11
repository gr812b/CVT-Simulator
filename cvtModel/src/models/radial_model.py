
from typing import Union
import numpy as np
from constants.car_specs import SHEAVE_ANGLE
from models.dataTypes import RadialPulleyForceBreakdown
from models.belt_model import BeltModel
from models.primary_pulley_model import PrimaryPulleyModel
from models.secondary_pulley_model import SecondaryPulleyModel
from utils.theoretical_models import TheoreticalModels as tm

# Gets the overall radial force per pulley
class RadialPulleyModel:
    def __init__(
        self,
        primary: bool,
        pulley_model: Union[PrimaryPulleyModel, SecondaryPulleyModel],
        belt_model: BeltModel,
    ):
        self.primary = primary
        self.pulley_model = pulley_model
        self.belt_model = belt_model

    def get_breakdown(self, shift_distance, *, angular_velocity=None, torque=None):
        if self.primary:
            assert angular_velocity is not None, "Primary requires angular_velocity"
            pulley_breakdown = self.pulley_model.get_breakdown(shift_distance, angular_velocity)
        else:
            assert torque is not None, "Secondary requires torque"
            pulley_breakdown = self.pulley_model.get_breakdown(shift_distance, torque)
        
        belt_breakdown = self.belt_model.get_breakdown(angular_velocity, shift_distance)

        wrap_angle = self._get_wrap_angle(shift_distance)
        radial_force = self._radial_force_from_clamping(pulley_breakdown.net)
        net = self._calculate_net_radial_force(belt_breakdown.net, radial_force, wrap_angle)

        return RadialPulleyForceBreakdown(
            pulley_breakdown,
            belt_breakdown,
            radial_force,
            net
        )

    def _radial_force_from_clamping(self, clamping_force: float) -> float:
        return 2 * clamping_force * np.tan(SHEAVE_ANGLE / 2)

    def _calculate_net_radial_force(
        self,
        centrifugal_force: float,
        radial_force: float,
        wrap_angle: float,
    ) -> float:
        # factor comes from the integral based on the force distribution
        return (centrifugal_force + radial_force) * 2 * np.sin(wrap_angle / 2)
    
    def _get_wrap_angle(self, shift_distance):
        if self.primary:
            return tm.primary_wrap_angle(shift_distance)
        else:
            return tm.secondary_wrap_angle(shift_distance)