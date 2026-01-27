from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.models.dataTypes import CarForceBreakdown
from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.constants.car_specs import (
    GEARBOX_RATIO,
    WHEEL_RADIUS,
    DRIVELINE_INERTIA,
)


class CarModel:
    def __init__(
        self,
        car_mass: float,
        load_model: LoadModel,
    ):
        self.car_mass = car_mass
        self.load_model = load_model

    def get_breakdown(self, state: SystemState, coupling_torque: float) -> CarForceBreakdown:
        load_force = self.load_model.get_breakdown(state.car_velocity).net
        load_torque = load_force * WHEEL_RADIUS

        engine_to_wheel_ratio = (
            tm.current_cvt_ratio(state.shift_distance) * GEARBOX_RATIO
        )
        accel = (
            WHEEL_RADIUS
            * (coupling_torque * engine_to_wheel_ratio - load_torque)
            / (DRIVELINE_INERTIA + self.car_mass * WHEEL_RADIUS**2)
        )

        return CarForceBreakdown(
            external_forces=self.load_model.get_breakdown(state.car_velocity),
            acceleration=accel,
        )
