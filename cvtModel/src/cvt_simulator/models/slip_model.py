import numpy as np
from cvt_simulator.models.dataTypes import (
    PrimaryTorqueBoundsBreakdown,
    SecondaryTorqueBoundsBreakdown,
    SlipBreakdown,
)
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
from cvt_simulator.constants.car_specs import (
    GEARBOX_RATIO,
)
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm


class SlipModel:
    slip_speed_threshold: float = 2  # rad/s
    relative_speed_zero_tolerance: float = 0.5  # rad/s
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
        (
            tau_lower,
            tau_upper,
            primary_bounds,
            secondary_bounds,
        ) = self.calculate_coupling_torque_bounds(state)
        tau_ns = self.get_no_slip_torque(state)

        v_delta = self._relative_speed(
            state.primary_pulley_angular_velocity,
            state.secondary_pulley_angular_velocity,
            tm.current_effective_cvt_ratio(state.shift_distance),
        )

        coupling_torque = self._traction_limited_coupling_torque(
            v_delta=v_delta,
            tau_ns=tau_ns,
            tau_lower=tau_lower,
            tau_upper=tau_upper,
        )

        # 3) Define is_slipping for diagnostics (no effect on dynamics)
        is_slipping = abs(v_delta) > self.slip_speed_threshold

        return SlipBreakdown(
            coupling_torque=coupling_torque,
            torque_demand=tau_ns,
            relative_velocity=v_delta,
            tau_upper=tau_upper,
            tau_lower=tau_lower,
            primary_tau_bounds=primary_bounds,
            secondary_tau_bounds=secondary_bounds,
            effective_cvt_ratio_time_derivative=effective_cvt_ratio_time_derivative,
            is_slipping=is_slipping,
        )

    def get_no_slip_torque(self, state: SystemState):
        # Match the normalized closed-form torque-demand equation:
        # tau_p = [tau_eng + (I_p/I_s) * R * tau_load - I_p * omega_s * R_dot]
        #         / [1 + (I_p/I_s) * R^2]
        I_p = self.primary_pulley_model.inertia
        I_s = self.secondary_pulley_model.inertia

        tau_eng = self.engine_model.get_torque(state.primary_pulley_angular_velocity)
        tau_load = self.load_model.get_breakdown(state).net_torque_at_secondary

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

    def calculate_coupling_torque_bounds(
        self, state: SystemState
    ) -> tuple[
        float,
        float,
        PrimaryTorqueBoundsBreakdown,
        SecondaryTorqueBoundsBreakdown,
    ]:
        """
        Calculate coupling torque limits from both pulleys.

        The coupled belt contact must satisfy both primary and secondary traction
        bounds. We therefore use:
        - Most restrictive positive bound: min(primary_upper, secondary_upper)
        - Most restrictive negative bound: max(primary_lower, secondary_lower)

        Args:
            state: Current system state

        Returns:
            tuple:
                (coupling_tau_lower, coupling_tau_upper,
                 primary_tau_bounds, secondary_tau_bounds)
        """
        primary_bounds = self._get_pulley_torque_bounds_breakdown(
            self.primary_pulley,
            state,
            engine_drive_torque=self.engine_model.get_torque(
                state.primary_pulley_angular_velocity
            ),
            primary_inertia=self.primary_pulley_model.inertia,
        )

        load_torque = self.load_model.get_breakdown(state).net_torque_at_secondary
        secondary_bounds = self._get_pulley_torque_bounds_breakdown(
            self.secondary_pulley,
            state,
            external_load_torque=load_torque,
            secondary_inertia=self.secondary_pulley_model.inertia,
        )

        primary_tau_lower = primary_bounds.tau_lower
        primary_tau_upper = primary_bounds.tau_upper
        secondary_tau_lower = secondary_bounds.tau_negative
        secondary_tau_upper = secondary_bounds.tau_positive

        coupling_tau_lower = max(primary_tau_lower, secondary_tau_lower)
        coupling_tau_upper = min(primary_tau_upper, secondary_tau_upper)

        return (
            coupling_tau_lower,
            coupling_tau_upper,
            primary_bounds,
            secondary_bounds,
        )

    def _get_pulley_torque_bounds_breakdown(
        self,
        pulley,
        state: SystemState,
        **kwargs,
    ) -> PrimaryTorqueBoundsBreakdown | SecondaryTorqueBoundsBreakdown:
        """Get a torque-bounds breakdown object from a pulley model across API variants."""
        if hasattr(pulley, "get_pulley_torque_bounds"):
            bounds = pulley.get_pulley_torque_bounds(state, **kwargs)
        elif hasattr(pulley, "calculate_torque_bounds"):
            bounds = pulley.calculate_torque_bounds(state, **kwargs)
        else:
            raise AttributeError(
                f"{type(pulley).__name__} does not implement a torque-bounds API"
            )

        if hasattr(bounds, "tau_lower") and hasattr(bounds, "tau_upper"):
            return bounds
        if hasattr(bounds, "tau_negative") and hasattr(bounds, "tau_positive"):
            return bounds

        raise TypeError(
            f"Unsupported torque-bounds return type from {type(pulley).__name__}: {type(bounds)}"
        )

    def _traction_limited_coupling_torque(
        self,
        v_delta: float,
        tau_ns: float,
        tau_lower: float,
        tau_upper: float,
    ) -> float:
        if tau_lower > tau_upper:
            return 0.0

        tau_ns_clamped = np.clip(tau_ns, tau_lower, tau_upper)
        tau_mid = 0.5 * (tau_upper + tau_lower)
        tau_amp = 0.5 * (tau_upper - tau_lower)
        smoothing = self.slip_speed_smoothing

        tau_sliding = tau_mid + tau_amp * np.tanh(v_delta / smoothing)

        # Blend from stick at v=0 to sliding away from zero
        alpha = np.tanh(abs(v_delta) / smoothing)
        return float((1.0 - alpha) * tau_ns_clamped + alpha * tau_sliding)

    def _relative_speed(
        self,
        primary_angular_velocity: float,
        secondary_angular_velocity: float,
        cvt_ratio: float,
    ) -> float:
        return primary_angular_velocity - (secondary_angular_velocity * cvt_ratio)

