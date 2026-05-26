from dataclasses import dataclass
from typing import Optional, Any, Callable, List, Tuple
import numpy as np

from cvt_simulator.constants.car_specs import MAX_SHIFT
from cvt_simulator.sim_utils.system_state import SystemState
from cvt_simulator.sim_utils.simulation_constraints import (
    car_velocity_constraint_event,
    get_shift_steady_event,
    get_back_shift_event,
    get_mid_shift_steady_event,
    get_mid_shift_wake_event,
    shift_constraint_event,
)

@dataclass
class SimulationBranchTransition:
    did_transition: bool
    next_mode: str
    next_time: Optional[float]
    next_state: Optional[np.ndarray]
    reason: Optional[str]
    locked_shift_distance: Optional[float]
    mid_shift_enter_time: Optional[float]
    last_mid_shift_wake_time: Optional[float]

class SimulationBranchManager:
    def __init__(
        self,
        contact_model: Any,
        mid_shift_min_hold_time: float,
        mid_shift_relock_delay: float,
        progress_tracker: Callable[[float, float], None],
    ):
        self.contact_model = contact_model
        self.mid_shift_min_hold_time = mid_shift_min_hold_time
        self.mid_shift_relock_delay = mid_shift_relock_delay
        self.progress_tracker = progress_tracker

    def get_ode_function(
        self, mode: str, locked_shift_distance: Optional[float] = None
    ) -> Callable[[float, List[float]], List[float]]:
        if mode == "normal":
            return self._evaluate_normal
        elif mode == "full_shift":
            return self._evaluate_full_shift
        elif mode == "mid_shift":
            if locked_shift_distance is None:
                raise ValueError("locked_shift_distance required for mid_shift mode")
            def locked_ode(t: float, y: List[float]):
                return self._evaluate_locked_shift(t, y, locked_shift_distance)
            return locked_ode
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def get_events(
        self,
        mode: str,
        locked_shift_distance: Optional[float] = None,
        mid_shift_enter_time: Optional[float] = None,
        last_mid_shift_wake_time: Optional[float] = -float("inf"),
    ) -> Tuple[List[Callable], List[str]]:
        if last_mid_shift_wake_time is None:
            last_mid_shift_wake_time = -float("inf")

        if mode == "normal":
            base_mid_shift_steady_event = get_mid_shift_steady_event(self.contact_model)

            def guarded_mid_shift_steady_event(t, y):
                if (t - last_mid_shift_wake_time) < self.mid_shift_relock_delay:
                    return 1.0
                return base_mid_shift_steady_event(t, y)

            guarded_mid_shift_steady_event.terminal = True
            guarded_mid_shift_steady_event.direction = -1

            events = [
                get_shift_steady_event(self.contact_model),
                guarded_mid_shift_steady_event,
                car_velocity_constraint_event,
                shift_constraint_event,
            ]
            event_names = [
                "shift_steady_event",
                "mid_shift_steady_event",
                "car_velocity_constraint_event",
                "shift_constraint_event",
            ]
            return events, event_names

        elif mode == "full_shift":
            events = [
                get_back_shift_event(self.contact_model),
                car_velocity_constraint_event,
            ]
            event_names = [
                "back_shift_event",
                "car_velocity_constraint_event",
            ]
            return events, event_names

        elif mode == "mid_shift":
            base_mid_shift_wake_event = get_mid_shift_wake_event(self.contact_model)

            def guarded_mid_shift_wake_event(t, y):
                if (
                    mid_shift_enter_time is not None
                    and (t - mid_shift_enter_time) < self.mid_shift_min_hold_time
                ):
                    return -1.0
                return base_mid_shift_wake_event(t, y)

            guarded_mid_shift_wake_event.terminal = True
            guarded_mid_shift_wake_event.direction = 1

            events = [
                guarded_mid_shift_wake_event,
                car_velocity_constraint_event,
            ]
            event_names = [
                "mid_shift_wake_event",
                "car_velocity_constraint_event",
            ]
            return events, event_names
        
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def get_transition(
        self,
        mode: str,
        solution: Any,
        event_names: List[str],
        locked_shift_distance: Optional[float] = None,
        mid_shift_enter_time: Optional[float] = None,
        last_mid_shift_wake_time: Optional[float] = None,
    ) -> SimulationBranchTransition:
        if mode == "normal":
            if solution.t_events[0].size > 0:
                new_time = float(solution.t_events[0][0])
                new_state = solution.y_events[0][0]
                return SimulationBranchTransition(
                    did_transition=True,
                    next_mode="full_shift",
                    next_time=new_time,
                    next_state=new_state,
                    reason="shift_steady_event",
                    locked_shift_distance=locked_shift_distance,
                    mid_shift_enter_time=mid_shift_enter_time,
                    last_mid_shift_wake_time=last_mid_shift_wake_time,
                )

            if solution.t_events[1].size > 0:
                new_time = float(solution.t_events[1][0])
                new_state = solution.y_events[1][0]
                new_locked_shift_distance = float(new_state[0])
                return SimulationBranchTransition(
                    did_transition=True,
                    next_mode="mid_shift",
                    next_time=new_time,
                    next_state=new_state,
                    reason="mid_shift_steady_event",
                    locked_shift_distance=new_locked_shift_distance,
                    mid_shift_enter_time=new_time,
                    last_mid_shift_wake_time=last_mid_shift_wake_time,
                )

        elif mode == "full_shift":
            if solution.t_events[0].size > 0:
                new_time = float(solution.t_events[0][0])
                new_state = solution.y_events[0][0]
                return SimulationBranchTransition(
                    did_transition=True,
                    next_mode="normal",
                    next_time=new_time,
                    next_state=new_state,
                    reason="back_shift_event",
                    locked_shift_distance=locked_shift_distance,
                    mid_shift_enter_time=mid_shift_enter_time,
                    last_mid_shift_wake_time=last_mid_shift_wake_time,
                )

        elif mode == "mid_shift":
            if solution.t_events[0].size > 0:
                new_time = float(solution.t_events[0][0])
                new_state = solution.y_events[0][0]
                return SimulationBranchTransition(
                    did_transition=True,
                    next_mode="normal",
                    next_time=new_time,
                    next_state=new_state,
                    reason="mid_shift_wake_event",
                    locked_shift_distance=locked_shift_distance,
                    mid_shift_enter_time=None,
                    last_mid_shift_wake_time=new_time,
                )

        return SimulationBranchTransition(
            did_transition=False,
            next_mode=mode,
            next_time=None,
            next_state=None,
            reason=None,
            locked_shift_distance=locked_shift_distance,
            mid_shift_enter_time=mid_shift_enter_time,
            last_mid_shift_wake_time=last_mid_shift_wake_time,
        )

    def _evaluate_normal(self, t: float, y: List[float]) -> List[float]:
        state = SystemState.from_array(y)

        raw_shift_distance = state.s
        raw_shift_velocity = state.s_dot
        eval_shift_distance = float(np.clip(raw_shift_distance, 0.0, MAX_SHIFT))
        eval_shift_velocity = raw_shift_velocity
        if raw_shift_distance <= 0.0 and raw_shift_velocity < 0.0:
            eval_shift_velocity = 0.0
        elif raw_shift_distance >= MAX_SHIFT and raw_shift_velocity > 0.0:
            eval_shift_velocity = 0.0

        eval_state = SystemState(
            s=eval_shift_distance,
            s_dot=eval_shift_velocity,
            ω_p=state.ω_p,
            ω_s=state.ω_s,
            v_b=state.v_b,
        )
        self.progress_tracker(t, eval_state.s)

        contact_breakdown = self.contact_model.get_breakdown(eval_state)

        shift_acceleration = contact_breakdown.shift.acceleration

        if eval_shift_distance <= 0 and shift_acceleration < 0:
            shift_acceleration = 0
        elif eval_shift_distance >= MAX_SHIFT and shift_acceleration > 0:
            shift_acceleration = 0

        return [
            eval_shift_velocity,
            shift_acceleration,
            contact_breakdown.drivetrain.ω_p_dot,
            contact_breakdown.drivetrain.ω_s_dot,
            contact_breakdown.drivetrain.v_b_dot,
        ]

    def _evaluate_full_shift(self, t: float, y: List[float]) -> List[float]:
        state = SystemState.from_array(y)
        self.progress_tracker(t, MAX_SHIFT)

        eval_state = SystemState(
            s=MAX_SHIFT,
            s_dot=0.0,
            ω_p=state.ω_p,
            ω_s=state.ω_s,
            v_b=state.v_b,
        )

        contact_breakdown = self.contact_model.get_breakdown(eval_state)

        return [
            0.0,
            0.0,
            contact_breakdown.drivetrain.ω_p_dot,
            contact_breakdown.drivetrain.ω_s_dot,
            contact_breakdown.drivetrain.v_b_dot,
        ]

    def _evaluate_locked_shift(
        self, t: float, y: List[float], locked_shift_distance: float
    ) -> List[float]:
        state = SystemState.from_array(y)
        self.progress_tracker(t, locked_shift_distance)

        eval_state = SystemState(
            s=locked_shift_distance,
            s_dot=0.0,
            ω_p=state.ω_p,
            ω_s=state.ω_s,
            v_b=state.v_b,
        )

        contact_breakdown = self.contact_model.get_breakdown(eval_state)

        return [
            0.0,
            0.0,
            contact_breakdown.drivetrain.ω_p_dot,
            contact_breakdown.drivetrain.ω_s_dot,
            contact_breakdown.drivetrain.v_b_dot,
        ]
