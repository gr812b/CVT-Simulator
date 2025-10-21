

from cvt_simulator.models.dataTypes import EngineForceBreakdown
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.models.slip_model import SlipModel


class EngineAccelModel:
    """Handles engine dynamics that depend on slip calculations."""
    
    def __init__(
        self,
        engine_model: EngineModel,
        inertia: float,  # kg*m^2
        slip_model: SlipModel
    ):
        self.engine_model = engine_model
        self.inertia = inertia
        self.slip_model = slip_model

    def get_breakdown(self, state: SystemState) -> EngineForceBreakdown:
        """Get complete engine force breakdown including slip effects."""
        angular_velocity = state.engine_angular_velocity
        torque = self.engine_model.get_torque(angular_velocity)
        power = self.engine_model.get_power(angular_velocity)

        t_c = self.slip_model.get_breakdown(state).t_c
        engine_angular_accel = (torque - t_c) / self.inertia

        return EngineForceBreakdown(
            torque=torque,
            power=power,
            angular_velocity=angular_velocity,
            engine_angular_acceleration=engine_angular_accel
        )
