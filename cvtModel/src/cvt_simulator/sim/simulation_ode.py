from typing import Callable, List, Optional
from cvt_simulator.core.dynamics.contact_dynamics_model import ContactDynamicsModel
import numpy as np

from cvt_simulator.constants.car_specs import MAX_SHIFT
from cvt_simulator.core.data_types import SlipBranch
from cvt_simulator.sim.system_state import SystemState


class SimulationODE:
    """Builds the RHS function used by solve_ivp.

    This class only answers:

        Given the current accepted shift mode and contact branch,
        what are the derivatives of the five state variables?

    It does not choose branches.
    It does not create events.
    It does not update simulation mode.
    """

    def __init__(
        self,
        contact_model: ContactDynamicsModel,
        progress_tracker: Callable[[float, float], None],
    ) -> None:
        self.contact_model = contact_model
        self.progress_tracker = progress_tracker

    def make(
        self,
        shift_mode: str,
        contact_branch: SlipBranch,
        locked_shift_distance: Optional[float] = None,
    ) -> Callable[[float, List[float]], List[float]]:
        """Return an ODE function for the current accepted simulation modes."""

        if shift_mode == "mid_shift" and locked_shift_distance is None:
            raise ValueError("locked_shift_distance required for mid_shift mode")

        def ode(t: float, y: List[float]) -> List[float]:
            return self.evaluate(
                t=t,
                y=y,
                shift_mode=shift_mode,
                contact_branch=contact_branch,
                locked_shift_distance=locked_shift_distance,
            )

        return ode

    def evaluate(
        self,
        t: float,
        y: List[float],
        shift_mode: str,
        contact_branch: SlipBranch,
        locked_shift_distance: Optional[float] = None,
    ) -> List[float]:
        """Evaluate the derivative vector.

        State order:
            y[0] = s
            y[1] = s_dot
            y[2] = omega_p
            y[3] = omega_s
            y[4] = v_b
        """

        raw_state = SystemState.from_array(y)

        # 1. Shift distance is always clamped for force/geometry evaluation.
        #    This avoids asking the CVT geometry for impossible radii.
        eval_s = float(np.clip(raw_state.s, 0.0, MAX_SHIFT))
        eval_s_dot = raw_state.s_dot

        # 2. Shift mode overrides only the shift coordinate pieces.
        #    The rotational states and belt speed always continue evolving.
        if shift_mode == "normal":
            if raw_state.s <= 0.0 and raw_state.s_dot < 0.0:
                eval_s_dot = 0.0
            elif raw_state.s >= MAX_SHIFT and raw_state.s_dot > 0.0:
                eval_s_dot = 0.0

        elif shift_mode == "full_shift":
            eval_s = MAX_SHIFT
            eval_s_dot = 0.0

        elif shift_mode == "mid_shift":
            if locked_shift_distance is None:
                raise ValueError("locked_shift_distance required for mid_shift mode")

            eval_s = locked_shift_distance
            eval_s_dot = 0.0

        else:
            raise ValueError(f"Unknown shift mode: {shift_mode}")

        eval_state = SystemState(
            s=eval_s,
            s_dot=eval_s_dot,
            ω_p=raw_state.ω_p,
            ω_s=raw_state.ω_s,
            v_b=raw_state.v_b,
        )

        self.progress_tracker(t, eval_s)

        # 3. Contact dynamics are evaluated using the accepted contact branch.
        #    No branch selection should happen inside the RHS.
        breakdown = self.contact_model.get_breakdown(
            eval_state,
            contact_branch=contact_branch,
        )

        # 4. Build the derivative vector.
        if shift_mode == "normal":
            s_dot_rhs = eval_s_dot
            s_ddot_rhs = breakdown.shift.acceleration

            # Do not accelerate farther into hard shift stops.
            if eval_s <= 0.0 and s_ddot_rhs < 0.0:
                s_ddot_rhs = 0.0
            elif eval_s >= MAX_SHIFT and s_ddot_rhs > 0.0:
                s_ddot_rhs = 0.0

        else:
            # In full_shift and mid_shift, the shift DOF is locked.
            s_dot_rhs = 0.0
            s_ddot_rhs = 0.0

        return [
            s_dot_rhs,
            s_ddot_rhs,
            breakdown.drivetrain.ω_p_dot,
            breakdown.drivetrain.ω_s_dot,
            breakdown.drivetrain.v_b_dot,
        ]
