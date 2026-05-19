from cvt_simulator.constants.car_specs import (
    BELT_HEIGHT,
    BELT_WIDTH_BOTTOM,
    BELT_WIDTH_TOP,
)
from cvt_simulator.constants.tuning import (
    BELT_RELAXATION_GAIN,
    BELT_STICK_HYSTERESIS_RATIO,
    BELT_STICK_SPEED_RELATIVE_TOLERANCE,
    BELT_STICK_SPEED_THRESHOLD,
)
from cvt_simulator.core.system_state import SystemState
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.models.dataTypes import BeltStateBreakdown


class BeltModel:
    """Belt transport-speed model for stick/slip regularization."""

    def __init__(
        self,
        stick_speed_threshold: float = BELT_STICK_SPEED_THRESHOLD,
        stick_speed_relative_tolerance: float = BELT_STICK_SPEED_RELATIVE_TOLERANCE,
        stick_hysteresis_ratio: float = BELT_STICK_HYSTERESIS_RATIO,
        relaxation_gain: float = BELT_RELAXATION_GAIN,
    ):
        self.stick_speed_threshold = stick_speed_threshold
        self.stick_speed_relative_tolerance = stick_speed_relative_tolerance
        self.stick_hysteresis_ratio = stick_hysteresis_ratio
        self.relaxation_gain = relaxation_gain
        self._last_is_stick: bool | None = None

    def reset_mode_state(self) -> None:
        """Reset Schmitt-trigger memory used for stick/slip hysteresis."""
        self._last_is_stick = None

    def _centroid_offset(self) -> float:
        return (
            BELT_HEIGHT
            * (BELT_WIDTH_TOP + 2 * BELT_WIDTH_BOTTOM)
            / (3 * (BELT_WIDTH_TOP + BELT_WIDTH_BOTTOM))
        )

    def _primary_centroid_radius(self, shift_distance: float) -> float:
        r_eff = tm.primary_effective_radius(shift_distance)
        return r_eff + BELT_HEIGHT / 2 - self._centroid_offset()

    def _secondary_centroid_radius(self, shift_distance: float) -> float:
        r_eff = tm.secondary_effective_radius(shift_distance)
        return r_eff + BELT_HEIGHT / 2 - self._centroid_offset()

    def get_stick_speed_tolerances(
        self,
        primary_belt_speed: float,
        secondary_belt_speed: float,
    ) -> tuple[float, float]:
        speed_scale = max(abs(primary_belt_speed), abs(secondary_belt_speed), 1.0)
        stick_enter_tolerance = max(
            self.stick_speed_threshold,
            self.stick_speed_relative_tolerance * speed_scale,
        )
        stick_exit_tolerance = stick_enter_tolerance * self.stick_hysteresis_ratio
        return stick_enter_tolerance, stick_exit_tolerance

    def get_kinematic_terms(
        self,
        state: SystemState,
    ) -> tuple[float, float, float, float, float]:
        """
        Compute kinematic terms used by both slip and belt-state models.

        Returns:
            (v_b_star, T_b, relative_speed, v_p_cm, v_s_cm)
        """
        shift_distance = state.s
        r_p_cm = self._primary_centroid_radius(shift_distance)
        r_s_cm = self._secondary_centroid_radius(shift_distance)

        v_p_cm = r_p_cm * state.ω_p
        v_s_cm = r_s_cm * state.ω_s

        relative_speed = v_p_cm - v_s_cm
        v_b_star = 0.5 * (v_p_cm + v_s_cm)
        T_b = 1.0 / self.relaxation_gain

        return v_b_star, T_b, relative_speed, v_p_cm, v_s_cm

    def get_branch_inputs(
        self,
        state: SystemState,
        is_stick_override: bool | None = None,
    ) -> tuple[bool, float, float, float, float, float]:
        """
        Compute shared branch inputs used by traction bounds and slip logic.

        Returns:
            (is_stick, v_b_star, T_b, relative_speed, v_p_cm, v_s_cm)
        """
        v_b_star, T_b, relative_speed, v_p_cm, v_s_cm = self.get_kinematic_terms(state)

        if is_stick_override is not None:
            is_stick = bool(is_stick_override)
            self._last_is_stick = is_stick
            return is_stick, v_b_star, T_b, relative_speed, v_p_cm, v_s_cm

        stick_enter_tolerance, stick_exit_tolerance = self.get_stick_speed_tolerances(
            v_p_cm,
            v_s_cm,
        )

        rel_abs = abs(relative_speed)
        if self._last_is_stick is None:
            is_stick = rel_abs <= stick_enter_tolerance
        elif self._last_is_stick:
            is_stick = rel_abs <= stick_exit_tolerance
        else:
            is_stick = rel_abs <= stick_enter_tolerance
        self._last_is_stick = is_stick

        return is_stick, v_b_star, T_b, relative_speed, v_p_cm, v_s_cm

    def get_breakdown(
        self,
        state: SystemState,
        primary_pulley_angular_accel: float,
        secondary_pulley_angular_accel: float,
        is_stick_override: bool | None = None,
    ) -> BeltStateBreakdown:
        """Compute belt state breakdown and v_b derivative law."""
        shift_distance = state.s
        shift_velocity = state.s_dot

        r_p_cm = self._primary_centroid_radius(shift_distance)
        r_s_cm = self._secondary_centroid_radius(shift_distance)

        dr_p_ds = tm.primary_radius_rate_of_change(shift_distance)
        dr_s_ds = tm.secondary_radius_rate_of_change(shift_distance)
        r_p_cm_dot = dr_p_ds * shift_velocity
        r_s_cm_dot = dr_s_ds * shift_velocity

        is_stick, v_b_star, T_b, relative_speed, v_p_cm, v_s_cm = (
            self.get_branch_inputs(
                state,
                is_stick_override=is_stick_override,
            )
        )
        v_b_compatible = v_b_star

        if is_stick:
            v_b_dot_primary = (
                r_p_cm_dot * state.ω_p
                + r_p_cm * primary_pulley_angular_accel
            )
            v_b_dot_secondary = (
                r_s_cm_dot * state.ω_s
                + r_s_cm * secondary_pulley_angular_accel
            )
            # Kinematic evolution from pulley accelerations.
            v_b_dot_kinematic = 0.5 * (v_b_dot_primary + v_b_dot_secondary)
            # Enforce no-slip compatibility in stick so v_b does not drift from v_b*.
            v_b_dot = v_b_dot_kinematic + (v_b_compatible - state.v_b) / T_b
        else:
            v_b_dot = (v_b_star - state.v_b) / T_b

        return BeltStateBreakdown(
            is_stick=is_stick,
            relative_speed=relative_speed,
            primary_belt_speed=v_p_cm,
            secondary_belt_speed=v_s_cm,
            v_b_star=v_b_star,
            T_b=T_b,
            v_b=state.v_b,
            v_b_compatible=v_b_compatible,
            v_b_dot=v_b_dot,
        )
