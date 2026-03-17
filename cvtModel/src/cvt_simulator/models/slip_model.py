import numpy as np
from cvt_simulator.models.dataTypes import SlipBreakdown
from cvt_simulator.models.external_load_model import LoadModel
from cvt_simulator.models.engine_model import EngineModel
from cvt_simulator.models.pulley.primary_pulley_interface import PrimaryPulleyModel
from cvt_simulator.models.pulley.secondary_pulley_interface import SecondaryPulleyModel
from cvt_simulator.models.primary_pulley_model import (
    PrimaryPulleyModel as PrimaryPulleyDynamicsModel,
)
from cvt_simulator.models.secondary_pulley_model import (
    SecondaryPulleyModel as SecondaryPulleyDynamicsModel,
)
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.utils.state_computations import (
    secondary_pulley_angular_velocity_to_car_velocity,
)
from cvt_simulator.constants.car_specs import (
    WHEEL_RADIUS,
    GEARBOX_RATIO,
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
        primary_pulley_model: PrimaryPulleyDynamicsModel,
        secondary_pulley_model: SecondaryPulleyDynamicsModel,
    ):
        self.load_model = load_model
        self.engine_model = engine_model
        self.car_mass = car_mass
        self.primary_pulley = primary_pulley
        self.secondary_pulley = secondary_pulley
        self.primary_pulley_model = primary_pulley_model
        self.secondary_pulley_model = secondary_pulley_model
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
        effective_cvt_ratio_time_derivative = tm.current_effective_cvt_ratio_time_derivative(
            state.shift_distance, state.shift_velocity
        )
        t_max_prim, t_max_sec = self.calculate_t_max(state)
        t_max_capacity = min(t_max_prim, t_max_sec)
        torque_demand = self.get_torque_demand(state)

        wheel_to_sec_ratio = GEARBOX_RATIO / WHEEL_RADIUS
        # Primary pulley angular velocity is the engine-side speed
        # Secondary pulley linear velocity at the wheel: v = ω_s * r_wheel
        secondary_car_velocity = secondary_pulley_angular_velocity_to_car_velocity(
            state.secondary_pulley_angular_velocity
        )
        relative_speed = self._relative_speed(
            state.primary_pulley_angular_velocity,
            secondary_car_velocity * wheel_to_sec_ratio,
            tm.current_effective_cvt_ratio(state.shift_distance),
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
            torque_demand=torque_demand,
            effective_cvt_ratio_time_derivative=effective_cvt_ratio_time_derivative,
            t_max_prim=t_max_prim,
            t_max_sec=t_max_sec,
            is_slipping=is_slipping,
        )

    def get_torque_demand(self, state: SystemState):
        # Match the normalized closed-form torque-demand equation:
        # tau_p = [tau_eng + (I_p/I_s) * R * tau_load - I_p * omega_s * R_dot]
        #         / [1 + (I_p/I_s) * R^2]
        I_p = self.primary_pulley_model.inertia
        I_s = self.secondary_pulley_model.inertia

        tau_eng = self.engine_model.get_torque(state.primary_pulley_angular_velocity)
        tau_load = self.load_model.get_breakdown(state).net

        R = tm.current_effective_cvt_ratio(state.shift_distance) * GEARBOX_RATIO
        R_dot = (
            tm.current_effective_cvt_ratio_time_derivative(
                state.shift_distance, state.shift_velocity
            )
            * GEARBOX_RATIO
        )

        omega_s = state.secondary_pulley_angular_velocity
        inertia_ratio = I_p / I_s

        numerator = tau_eng + inertia_ratio * R * tau_load - I_p * omega_s * R_dot
        denominator = 1 + inertia_ratio * (R**2)

        return numerator / denominator

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
        load_torque = self.load_model.get_breakdown(state).net
        secondary_t_max = self.secondary_pulley.calculate_max_torque(
            state,
            external_load_torque=load_torque,
            secondary_inertia=self.secondary_pulley_model.inertia,
        )

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
