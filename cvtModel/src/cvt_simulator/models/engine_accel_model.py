from cvt_simulator.models.dataTypes import EngineForceBreakdown
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.constants.car_specs import ENGINE_INERTIA


class EngineAccelModel:
    """Handles engine dynamics that depend on slip calculations."""

    def __init__(self, engine_model: EngineModel):
        self.engine_model = engine_model

    def get_breakdown(
        self, state: SystemState, coupling_torque: float
    ) -> EngineForceBreakdown:

        angular_velocity = state.engine_angular_velocity
        torque = self.engine_model.get_torque(angular_velocity)
        power = self.engine_model.get_power(angular_velocity)

        angular_accel = (torque - coupling_torque) / ENGINE_INERTIA

        return EngineForceBreakdown(
            torque=torque,
            power=power,
            angular_velocity=angular_velocity,
            angular_acceleration=angular_accel,
        )
