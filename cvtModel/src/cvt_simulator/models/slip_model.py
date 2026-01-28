import numpy as np
from cvt_simulator.models.dataTypes import SlipBreakdown
from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.models.pulley.primary_pulley_interface import PrimaryPulleyModel
from cvt_simulator.models.pulley.secondary_pulley_interface import SecondaryPulleyModel
from cvt_simulator.utils.system_state import SystemState
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
    slip_speed_threshold: float = 2  # rad/s
    slip_speed_smoothing: float = 5.0

    def __init__(
        self,
        load_model: LoadModel,
        engine_model: EngineModel,
        car_mass: float,
        primary_pulley: PrimaryPulleyModel,
        secondary_pulley: SecondaryPulleyModel,
    ):
        self.load_model = load_model
        self.engine_model = engine_model
        self.car_mass = car_mass
        self.primary_pulley = primary_pulley
        self.secondary_pulley = secondary_pulley
        self.μ = RUBBER_ALUMINUM_STATIC_FRICTION / np.sin(
            SHEAVE_ANGLE / 2
        )  # V-belt groove friction enhancement

    def get_breakdown(self, state: SystemState) -> SlipBreakdown:
        """
        Calculate slip breakdown using pulley models directly.

        Args:
            state: Current system state

        Returns:
            SlipBreakdown with slip analysis
        """
        cvt_ratio_derivative = tm.current_cvt_ratio_rate_of_change(
            state.shift_distance, state.shift_velocity
        )
        t_max_prim, t_max_sec = self.calculate_t_max(state)
        t_max_capacity = min(t_max_prim, t_max_sec)
        torque_demand = self.get_torque_demand(state)

        wheel_to_sec_ratio = GEARBOX_RATIO / WHEEL_RADIUS
        relative_speed = self._relative_speed(
            state.engine_angular_velocity,
            state.car_velocity * wheel_to_sec_ratio,
            tm.current_cvt_ratio(state.shift_distance),
        )

        # 1) Smooth Coulomb-like torque based on slip speed
        #    For large |relative_speed|, tanh -> ±1, so |coupling_torque| -> t_max_capacity
        #    For small |relative_speed|, torque ~ (t_max_capacity / slip_speed_smoothing) * relative_speed (viscous-ish)
        coulomb_torque = t_max_capacity * np.tanh(
            relative_speed / self.slip_speed_smoothing
        )

        # 2) Optionally respect torque_demand near zero slip by blending
        #    When relative_speed is small, use torque_demand (clamped);
        #    as slip grows, fade to the Coulomb model.
        v_blend = self.slip_speed_smoothing  # you can use same scale or a separate one
        alpha = np.clip(abs(relative_speed) / v_blend, 0.0, 1.0)

        torque_demand_clamped = np.clip(torque_demand, -t_max_capacity, t_max_capacity)

        coupling_torque = (1.0 - alpha) * torque_demand_clamped + alpha * coulomb_torque

        # 3) Define is_slipping for diagnostics (no effect on dynamics)
        is_slipping = abs(relative_speed) > self.slip_speed_threshold

        return SlipBreakdown(
            coupling_torque=coupling_torque,
            coupling_torque_unclamped=torque_demand,
            cvt_ratio_derivative=cvt_ratio_derivative,
            t_max_prim=t_max_prim,
            t_max_sec=t_max_sec,
            is_slipping=is_slipping,
        )

    def get_torque_demand(self, state: SystemState):
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

        coupling_torque = numerator / denominator

        return coupling_torque

    def get_wheel_speed(self, car_velocity: float):
        return car_velocity / WHEEL_RADIUS

    def calculate_t_max(self, state: SystemState) -> tuple[float, float]:
        """
        Calculate maximum transferable torque using pulley models directly.

        Uses the more restrictive (smaller) T_MAX from either primary or secondary pulley.
        This ensures we don't exceed the slip limit of either pulley.

        Args:
            state: Current system state

        Returns:
            tuple: (primary_t_max, secondary_t_max)
        """
        primary_t_max = self.primary_pulley.calculate_max_torque(state)
        secondary_t_max = self.secondary_pulley.calculate_max_torque(state)

        # Use the more restrictive (smaller) T_MAX
        primary_t_max = max(0, primary_t_max)
        secondary_t_max = max(0, secondary_t_max)
        return primary_t_max, secondary_t_max

    def _relative_speed(
        self,
        primary_angular_velocity: float,
        secondary_angular_velocity: float,
        cvt_ratio: float,
    ) -> float:
        return primary_angular_velocity - (secondary_angular_velocity * cvt_ratio)

    # def _is_slipping(
    #     self,
    #     primary_angular_velocity: float,
    #     secondary_angular_velocity: float,
    #     cvt_ratio: float,
    #     tolerance: float = 2,
    # ) -> bool:
    #     expected_secondary_velocity = primary_angular_velocity / cvt_ratio
    #     return abs(expected_secondary_velocity - secondary_angular_velocity) > tolerance
