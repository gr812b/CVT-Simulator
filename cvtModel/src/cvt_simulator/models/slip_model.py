from cvt_simulator.models.dataTypes import SlipBreakdown
from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.constants.car_specs import (
    WHEEL_RADIUS,
    GEARBOX_RATIO,
    ENGINE_INERTIA,
    DRIVELINE_INERTIA,
)
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm


class SlipModel:
    T_MAX = 50  # TODO: Replace with calculation

    def __init__(
        self, load_model: LoadModel, engine_model: EngineModel, car_mass: float
    ):
        self.load_model = load_model
        self.engine_model = engine_model
        self.car_mass = car_mass

    def get_breakdown(self, state: SystemState) -> SlipBreakdown:
        t_c = self.get_tc(state)
        cvt_ratio_derivative = tm.current_cvt_ratio_rate_of_change(
            state.shift_distance, state.shift_velocity
        )

        return SlipBreakdown(
            t_c=t_c,
            cvt_ratio_derivative=cvt_ratio_derivative,
        )

    def get_tc(self, state: SystemState):
        wheel_inertia = DRIVELINE_INERTIA + self.car_mass * (
            WHEEL_RADIUS**2
        )  # This is the driveline + car's translational mass at wheels

        engine_torque = self.engine_model.get_torque(state.engine_angular_velocity)
        load_torque = self.load_model.get_breakdown(state.car_velocity).net
        wheel_angular_velocity = self.get_wheel_speed(state.car_velocity)
        engine_to_wheel_ratio = (
            tm.current_cvt_ratio(state.shift_distance) * GEARBOX_RATIO
        )
        engine_to_wheel_ratio_rate_of_change = (
            tm.current_cvt_ratio_rate_of_change(
                state.shift_distance, state.shift_velocity
            )
            * GEARBOX_RATIO
        )

        # The secret butter
        eng_term = engine_torque * wheel_inertia
        load_term = ENGINE_INERTIA * load_torque * engine_to_wheel_ratio
        shift_term = (
            ENGINE_INERTIA
            * wheel_inertia
            * wheel_angular_velocity
            * engine_to_wheel_ratio_rate_of_change
        )

        numerator = eng_term + load_term - shift_term
        denominator = wheel_inertia + ENGINE_INERTIA * engine_to_wheel_ratio**2

        t_c = numerator / denominator
        t_c = max(-self.T_MAX, min(self.T_MAX, t_c))  # Apply coulomb slip law

        return t_c

    def get_wheel_speed(self, car_velocity: float):
        return car_velocity / WHEEL_RADIUS
