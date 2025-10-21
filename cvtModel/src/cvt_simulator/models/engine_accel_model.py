

from cvt_simulator.models.dataTypes import EngineForceBreakdown, SlipBreakdown
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.utils.system_state import SystemState


class EngineAccelModel:
    """Handles engine dynamics that depend on slip calculations."""
    
    def __init__(
        self,
        engine_model: EngineModel,
        inertia: float,  # kg*m^2
    ):
        self.engine_model = engine_model
        self.inertia = inertia

    def get_breakdown(self, state: SystemState, slip_breakdown: SlipBreakdown) -> EngineForceBreakdown:

        angular_velocity = state.engine_angular_velocity
        torque = self.engine_model.get_torque(angular_velocity)
        power = self.engine_model.get_power(angular_velocity)

        t_c = slip_breakdown.t_c
            
        angular_accel = (torque - t_c) / self.inertia

        return EngineForceBreakdown(
            torque=torque,
            power=power,
            angular_velocity=angular_velocity,
            angular_acceleration=angular_accel
        )
