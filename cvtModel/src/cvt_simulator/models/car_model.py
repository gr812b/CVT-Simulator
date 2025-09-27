from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.models.dataTypes import CarForceBreakdown
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.constants.car_specs import (
    GEARBOX_RATIO,
    WHEEL_RADIUS,
)


class CarModel:
    def __init__(
        self,
        car_mass: float,
        load_model: LoadModel,
        engine_model: EngineModel,
    ):
        self.car_mass = car_mass
        self.load_model = load_model
        self.engine_model = engine_model

    def get_breakdown(self, state: SystemState):
        engine_angular_velocity = self._get_engine_velocity(
            state.shift_distance, state.car_velocity
        )

        engineForces = self.engine_model.get_breakdown(engine_angular_velocity)
        load_force = self.load_model.get_breakdown(state.car_velocity)

        engine = engineForces.power / state.car_velocity
        accel = (engine - load_force.net) / self.car_mass

        return CarForceBreakdown(load_force, engineForces, accel)

    def _get_engine_velocity(self, shift_distance, car_velocity):
        cvt_ratio = tm.current_cvt_ratio(shift_distance)
        wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
        engine_angular_velocity = car_velocity * wheel_to_engine_ratio
        return engine_angular_velocity
