from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.models.dataTypes import CarForceBreakdown
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.models.engine_slip_model import slip_model
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
        engine_slip_model: slip_model
    ):
        self.car_mass = car_mass
        self.load_model = load_model
        self.engine_model = engine_model
        self.engine_slip_model = engine_slip_model

    def get_breakdown(self, state: SystemState):
        driveline_inertia = 5 # TODO: Replace with real value

        load_torque = self.load_model.get_breakdown(state.car_velocity).net
        t_c = self.engine_slip_model.get_tc(state)

        engine_to_wheel_ratio = tm.current_cvt_ratio(state.shift_distance) * GEARBOX_RATIO
        accel = WHEEL_RADIUS * (t_c * engine_to_wheel_ratio - load_torque) / (driveline_inertia + self.car_mass * WHEEL_RADIUS ** 2)

        return CarForceBreakdown(self.load_model.get_breakdown(state.car_velocity), accel)

    def _get_engine_velocity(self, shift_distance, car_velocity):
        cvt_ratio = tm.current_cvt_ratio(shift_distance)
        wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
        engine_angular_velocity = car_velocity * wheel_to_engine_ratio
        return engine_angular_velocity
