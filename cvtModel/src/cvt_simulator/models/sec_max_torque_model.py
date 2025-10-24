import numpy as np
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.models.secondary_pulley_model import SecondaryPulleyModel
from cvt_simulator.models.radial_model import RadialPulleyModel
from cvt_simulator.constants.car_specs import SHEAVE_ANGLE
from cvt_simulator.constants.constants import RUBBER_ALUMINUM_STATIC_FRICTION
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm

class SecondaryMaxTorqueModel:
    def __init__(
        self,
        sec_model: SecondaryPulleyModel,
        radial_model: RadialPulleyModel
    ):
        self.sec_model = sec_model
        self.radial_model = radial_model
        self.μ = RUBBER_ALUMINUM_STATIC_FRICTION / np.sin(SHEAVE_ANGLE / 2)

    # TODO: Only need radial model
    def get_max_torque_sec(self, state: SystemState):
        # Needs
        # density, cross sectional area
        # Torsional and compressive spring force
        # Half groove angle
        # Coefficient of friction
        # CVT Ratio
        sec_breakdown = self.sec_model.get_breakdown(state.shift_distance, 0)  # Torque not needed for this calc
        spring_forces = (sec_breakdown.helix_force.net + sec_breakdown.springCompForce.net) * np.tan(SHEAVE_ANGLE / 2)

        # Only some of these forces will be correct
        radial_breakdown = self.radial_model.get_breakdown(state, 0)

        radial_from_centrifugal = radial_breakdown.radial_from_centrifugal
        wrap_angle = radial_breakdown.wrap_angle
        radius = radial_breakdown.radius
        centrifugal_force = radial_from_centrifugal * wrap_angle * (1/2)

        # Capstan portion e^
        mini_cap = np.exp(self.μ * wrap_angle)
        capstan_term = (wrap_angle / (4 * radius)) * (mini_cap + 1) / (mini_cap - 1)

        # Transmission portion
        cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
        ramp_angle = sec_breakdown.helix_force.angle
        transmission_term = 2 * cvt_ratio * (self.sec_model.helix_radius * np.tan(ramp_angle)) * np.tan(SHEAVE_ANGLE / 2)

        t_max = (centrifugal_force + spring_forces) / (capstan_term - transmission_term)
        return t_max
    