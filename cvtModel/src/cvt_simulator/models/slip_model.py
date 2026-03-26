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
from cvt_simulator.models.belt_model import BeltModel
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.utils.blending import SignalBlendController
from cvt_simulator.constants.car_specs import (
    GEARBOX_RATIO,
    MAX_SHIFT,
)
from cvt_simulator.constants.tuning import (
    SLIP_CORRECTION_GAIN,
    SLIP_HIGH_SPEED_LOCK_THRESHOLD,
    SLIP_LOW_SPEED_BLEND_DEADZONE,
    SLIP_LOW_SPEED_BLEND_TRANSITION,
    SLIP_SHIFT_STOP_BLEND_DISTANCE,
    SLIP_SPEED_SMOOTHING,
    SLIP_TORQUE_EXIT_MARGIN,
    SLIP_TORQUE_REENTER_MARGIN,
)
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm


class SlipModel:
    def __init__(
        self,
        load_model: LoadModel,
        engine_model: EngineModel,
        car_mass: float,
        primary_pulley: PrimaryPulleyModel,
        secondary_pulley: SecondaryPulleyModel,
        primary_pulley_model: PrimaryPulleyDynamicsModel,
        secondary_pulley_model: SecondaryPulleyDynamicsModel,
        belt_model: BeltModel,
    ):
        self.load_model = load_model
        self.engine_model = engine_model
        self.car_mass = car_mass
        self.primary_pulley = primary_pulley
        self.secondary_pulley = secondary_pulley
        self.primary_pulley_model = primary_pulley_model
        self.secondary_pulley_model = secondary_pulley_model
        self.belt_model = belt_model
        self._last_is_stick: bool | None = None
        self.slip_speed_smoothing = SLIP_SPEED_SMOOTHING
        self.slip_correction_gain = SLIP_CORRECTION_GAIN
        self.shift_stop_blend_distance = SLIP_SHIFT_STOP_BLEND_DISTANCE
        # Hysteresis around torque feasibility to avoid boundary chatter.
        self.torque_exit_margin = SLIP_TORQUE_EXIT_MARGIN
        self.torque_reenter_margin = SLIP_TORQUE_REENTER_MARGIN
        # In slip mode, stay near demand only at very low relative speed.
        # Around 0.5 km/h (0.1389 m/s) and below, blend toward no-slip demand.
        # Above this region, enforce traction-bound saturation.
        self.slip_blend_controller = SignalBlendController(
            deadzone=SLIP_LOW_SPEED_BLEND_DEADZONE,
            transition_width=SLIP_LOW_SPEED_BLEND_TRANSITION,
        )
        # High-slip engagement lock: above 5 km/h relative speed, force the
        # coupling torque to the active traction bound.
        self.high_slip_bound_controller = SignalBlendController(
            deadzone=SLIP_HIGH_SPEED_LOCK_THRESHOLD,
            transition_width=0.0,
            hard_threshold=True,
        )

    def reset_mode_state(self) -> None:
        self._last_is_stick = None

    def get_breakdown(self, state: SystemState) -> SlipBreakdown:
        """
        Calculate slip breakdown using pulley models directly.

        Args:
            state: Current system state

        Returns:
            SlipBreakdown with slip analysis
        """
        effective_cvt_ratio_time_derivative = (
            tm.current_effective_cvt_ratio_time_derivative(
                state.shift_distance, state.shift_velocity
            )
        )

        (
            v_b_star,
            T_b,
            v_delta,
            primary_belt_speed,
            secondary_belt_speed,
        ) = self.belt_model.get_kinematic_terms(state)
        stick_enter_tolerance, stick_exit_tolerance = (
            self.belt_model.get_stick_speed_tolerances(
                primary_belt_speed,
                secondary_belt_speed,
            )
        )

        (
            tau_lower_stick,
            tau_upper_stick,
            primary_bounds_stick,
            secondary_bounds_stick,
        ) = self.calculate_coupling_torque_bounds(
            state,
            is_stick=True,
            v_b_star=v_b_star,
            T_b=T_b,
        )

        tau_ns = self.get_no_slip_torque(state)
        is_stick = self._select_stick_mode(
            tau_ns=tau_ns,
            tau_lower=tau_lower_stick,
            tau_upper=tau_upper_stick,
            relative_speed=v_delta,
            stick_enter_tolerance=stick_enter_tolerance,
            stick_exit_tolerance=stick_exit_tolerance,
        )

        if is_stick:
            tau_lower = tau_lower_stick
            tau_upper = tau_upper_stick
            primary_bounds = primary_bounds_stick
            secondary_bounds = secondary_bounds_stick
        else:
            (
                tau_lower,
                tau_upper,
                primary_bounds,
                secondary_bounds,
            ) = self.calculate_coupling_torque_bounds(
                state,
                is_stick=False,
                v_b_star=v_b_star,
                T_b=T_b,
            )

        coupling_torque = self._traction_limited_coupling_torque(
            v_delta=v_delta,
            tau_ns=tau_ns,
            tau_lower=tau_lower,
            tau_upper=tau_upper,
            is_stick=is_stick,
        )

        # 3) Define is_slipping for diagnostics (no effect on dynamics)
        is_slipping = not is_stick

        return SlipBreakdown(
            coupling_torque=coupling_torque,
            torque_demand=tau_ns,
            tau_upper=tau_upper,
            tau_lower=tau_lower,
            primary_tau_bounds=primary_bounds,
            secondary_tau_bounds=secondary_bounds,
            effective_cvt_ratio_time_derivative=effective_cvt_ratio_time_derivative,
            is_slipping=is_slipping,
        )

    def _select_stick_mode(
        self,
        tau_ns: float,
        tau_lower: float,
        tau_upper: float,
        relative_speed: float,
        stick_enter_tolerance: float,
        stick_exit_tolerance: float,
    ) -> bool:
        if tau_lower > tau_upper:
            self._last_is_stick = False
            return False

        rel_abs = abs(relative_speed)

        if self._last_is_stick is None:
            is_stick = (
                (tau_lower <= tau_ns <= tau_upper)
                and (rel_abs <= stick_enter_tolerance)
            )
        elif self._last_is_stick:
            is_stick = (
                (tau_lower - self.torque_exit_margin)
                <= tau_ns
                <= (tau_upper + self.torque_exit_margin)
                and (rel_abs <= stick_exit_tolerance)
            )
        else:
            is_stick = (
                (tau_lower + self.torque_reenter_margin)
                <= tau_ns
                <= (tau_upper - self.torque_reenter_margin)
                and (rel_abs <= stick_enter_tolerance)
            )

        self._last_is_stick = is_stick
        return is_stick

    def get_no_slip_torque(self, state: SystemState):
        # Match the normalized closed-form torque-demand equation:
        # tau_p = [tau_eng + (I_p/I_s) * R * tau_load - I_p * omega_s * R_dot]
        #         / [1 + (I_p/I_s) * R^2]
        I_p = self.primary_pulley_model.inertia
        I_s = self.secondary_pulley_model.inertia

        tau_eng = self.engine_model.get_torque(state.primary_pulley_angular_velocity)
        tau_load = self.load_model.get_breakdown(state).net_torque_at_secondary

        R = tm.current_effective_cvt_ratio(state.shift_distance) * GEARBOX_RATIO
        shift_velocity = state.shift_velocity
        shift_distance = state.shift_distance
        if shift_velocity > 0.0:
            distance_to_max = max(MAX_SHIFT - shift_distance, 0.0)
            if distance_to_max < self.shift_stop_blend_distance:
                blend = distance_to_max / self.shift_stop_blend_distance
                shift_velocity *= blend * blend
        elif shift_velocity < 0.0:
            distance_to_min = max(shift_distance, 0.0)
            if distance_to_min < self.shift_stop_blend_distance:
                blend = distance_to_min / self.shift_stop_blend_distance
                shift_velocity *= blend * blend

        R_dot = (
            tm.current_effective_cvt_ratio_time_derivative(
                shift_distance,
                shift_velocity,
            )
            * GEARBOX_RATIO
        )

        omega_s = state.secondary_pulley_angular_velocity
        inertia_ratio = I_p / I_s

        numerator = tau_eng + inertia_ratio * R * tau_load - I_p * omega_s * R_dot
        denominator = 1 + inertia_ratio * (R**2)

        return numerator / denominator

    def calculate_coupling_torque_bounds(
        self,
        state: SystemState,
        is_stick: bool,
        v_b_star: float,
        T_b: float,
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
        primary_bounds = self.primary_pulley.calculate_torque_bounds(
            state,
            engine_drive_torque=self.engine_model.get_torque(
                state.primary_pulley_angular_velocity
            ),
            primary_inertia=self.primary_pulley_model.inertia,
            is_stick=is_stick,
            v_b_star=v_b_star,
            T_b=T_b,
        )

        load_torque = self.load_model.get_breakdown(state).net_torque_at_secondary
        secondary_bounds = self.secondary_pulley.calculate_torque_bounds(
            state,
            external_load_torque=load_torque,
            secondary_inertia=self.secondary_pulley_model.inertia,
            is_stick=is_stick,
            v_b_star=v_b_star,
            T_b=T_b,
        )

        coupling_tau_lower = max(primary_bounds.tau_lower, secondary_bounds.tau_negative)
        coupling_tau_upper = min(primary_bounds.tau_upper, secondary_bounds.tau_positive)

        return (
            coupling_tau_lower,
            coupling_tau_upper,
            primary_bounds,
            secondary_bounds,
        )

    def _traction_limited_coupling_torque(
        self,
        v_delta: float,
        tau_ns: float,
        tau_lower: float,
        tau_upper: float,
        is_stick: bool,
    ) -> float:
        if tau_lower > tau_upper:
            return 0.0

        tau_ns_clamped = np.clip(tau_ns, tau_lower, tau_upper)
        if is_stick:
            # In stick, static friction enforces no-slip demand up to traction limits.
            return float(tau_ns_clamped)

        tau_amp = 0.5 * (tau_upper - tau_lower)
        # Slip correction is continuous at v_delta=0 and bounded by traction.
        slip_correction = (
            self.slip_correction_gain * tau_amp * np.tanh(v_delta / self.slip_speed_smoothing)
        )
        tau_low_speed = tau_ns_clamped + slip_correction

        tau_bound = tau_upper if v_delta >= 0.0 else tau_lower
        tau = self.high_slip_bound_controller.blend(
            low_value=tau_low_speed,
            high_value=tau_bound,
            signal=v_delta,
        )
        return float(np.clip(tau, tau_lower, tau_upper))

