import math
import numpy as np
from cvt_simulator.models.dataTypes import SlipBreakdown, RadialPulleyForceBreakdown
from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.models.sec_max_torque_model import SecondaryMaxTorqueModel
from cvt_simulator.constants.car_specs import (
    WHEEL_RADIUS,
    GEARBOX_RATIO,
    ENGINE_INERTIA,
    DRIVELINE_INERTIA,
    SHEAVE_ANGLE,
)
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.constants.constants import (
    RUBBER_ALUMINUM_STATIC_FRICTION,
)


class SlipModel:
    def __init__(
        self,
        load_model: LoadModel,
        engine_model: EngineModel,
        car_mass: float,
        sec_max_torque_model: SecondaryMaxTorqueModel,
    ):
        self.load_model = load_model
        self.engine_model = engine_model
        self.car_mass = car_mass
        self.sec_max_torque_model = sec_max_torque_model
        self.μ = RUBBER_ALUMINUM_STATIC_FRICTION / np.sin(
            SHEAVE_ANGLE / 2
        )  # V-belt groove friction enhancement

    def get_breakdown(
        self, state: SystemState, primary_radial_breakdown: RadialPulleyForceBreakdown
    ) -> SlipBreakdown:
        t_max_prim, t_max_sec = self.calculate_t_max(state, primary_radial_breakdown)
        t_c_before_clamp = self.get_tc(state)

        wheel_to_sec_ratio = GEARBOX_RATIO / WHEEL_RADIUS
        is_slipping = self._is_slipping(
            state.engine_angular_velocity,
            state.car_velocity * wheel_to_sec_ratio,
            tm.current_cvt_ratio(state.shift_distance),
        )

        t_c = min(t_c_before_clamp, t_max_prim, t_max_sec)

        if is_slipping:
            # TODO: Consider sign
            t_c = min(t_max_prim, t_max_sec)

        cvt_ratio_derivative = tm.current_cvt_ratio_rate_of_change(
            state.shift_distance, state.shift_velocity
        )

        return SlipBreakdown(
            t_c=t_c,
            t_c_before_clamp=t_c_before_clamp,
            cvt_ratio_derivative=cvt_ratio_derivative,
            t_max_prim=t_max_prim,
            t_max_sec=t_max_sec,
            is_slipping=is_slipping,
        )

    def get_tc(self, state: SystemState):
        wheel_inertia = DRIVELINE_INERTIA + self.car_mass * (
            WHEEL_RADIUS**2
        )  # This is the driveline + car's translational mass at wheels

        engine_torque = self.engine_model.get_torque(state.engine_angular_velocity)
        load_force = self.load_model.get_breakdown(state.car_velocity).net
        load_torque = load_force * WHEEL_RADIUS
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

        return t_c

    def get_wheel_speed(self, car_velocity: float):
        return car_velocity / WHEEL_RADIUS

    def calculate_t_max(
        self, state: SystemState, primary_radial_breakdown: RadialPulleyForceBreakdown
    ) -> float:
        """
        Calculate maximum transferable torque using CVT breakdown data.

        Uses the more restrictive (smaller) T_MAX from either primary or secondary pulley.
        This ensures we don't exceed the slip limit of either pulley.
        """
        # Extract data from primary pulley breakdown
        primary_radial_force = primary_radial_breakdown.net
        primary_wrap_angle = primary_radial_breakdown.wrap_angle
        primary_radius = primary_radial_breakdown.radius

        # Calculate slack tension for both pulleys
        primary_t_max = self._get_max_torque(
            primary_radial_force, primary_wrap_angle, primary_radius, self.μ
        )
        secondary_t_max = self.sec_max_torque_model.get_max_torque_sec(state)

        # Use the more restrictive (smaller) T_MAX
        # TODO: Consider direction for engine braking scenarios
        primary_t_max = max(0.0, primary_t_max)
        secondary_t_max = max(0.0, secondary_t_max)
        return primary_t_max, secondary_t_max

    def _get_max_torque(
        self, radial_force: float, wrap_angle: float, radius: float, μ: float
    ):
        exp_term = math.exp(μ * wrap_angle)
        capstan_term = (exp_term - 1) / (exp_term + 1)
        radial_force_term = radial_force * radius / np.sin(wrap_angle / 2)
        return capstan_term * radial_force_term

    def _is_slipping(
        self,
        primary_angular_velocity: float,
        secondary_angular_velocity: float,
        cvt_ratio: float,
        tolerance: float = 2,
    ) -> bool:
        expected_secondary_velocity = primary_angular_velocity / cvt_ratio
        return abs(expected_secondary_velocity - secondary_angular_velocity) > tolerance
