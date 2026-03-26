import sys
import numpy as np
from typing import Callable, Optional, Any
from scipy.integrate import solve_ivp
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.utils.simulation_result import SimulationResult
from cvt_simulator.models.system_model import SystemModel
from cvt_simulator.constants.car_specs import (
    GEARBOX_RATIO,
    MAX_SHIFT,
)
from cvt_simulator.utils.conversions import rpm_to_rad_s
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.utils.simulation_constraints import (
    car_velocity_constraint_event,
    get_shift_steady_event,
    get_back_shift_event,
    get_mid_shift_steady_event,
    get_mid_shift_wake_event,
    shift_constraint_event,
)


# Helper class to wrap data
class CombinedSolution:
    def __init__(self, t, y):
        self.t = t
        self.y = y


class SimulationRunner:
    """Runs a two-phase CVT system simulation."""

    TOTAL_SIM_TIME = 15  # seconds
    # Hysteresis controls to prevent mid-shift lock/unlock chatter.
    MID_SHIFT_MIN_HOLD_TIME = 0.02  # seconds
    MID_SHIFT_RELOCK_DELAY = 0.05  # seconds
    INITIAL_STATE = SystemState(
        shift_distance=0.0,
        shift_velocity=0.0,
        # Initial secondary pulley angular velocity derived from initial car velocity
        secondary_pulley_angular_velocity=rpm_to_rad_s(0.1)
        / (GEARBOX_RATIO * tm.current_effective_cvt_ratio(0)),
        # Initial primary pulley angular velocity (engine speed)
        primary_pulley_angular_velocity=rpm_to_rad_s(1800),
        v_b=0.0,
    )

    def __init__(
        self,
        system_model: SystemModel,
        # Optional progress callback. Preferred signature:
        #   callback(progress_percent, sim_time_s, shift_distance)
        # Backward-compatible signature callback(progress_percent) is also supported.
        progress_callback: Optional[Callable[..., None]] = None,
        transition_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ):
        self.system_model = system_model
        self.progress_callback = progress_callback
        self.transition_callback = transition_callback
        self._last_callback_percent = -1.0

    def _emit_transition(
        self,
        from_mode: str,
        to_mode: str,
        t: float,
        state_array: np.ndarray,
        reason: str,
    ):
        if self.transition_callback is None:
            return
        state = SystemState.from_array(state_array)
        self.transition_callback(
            {
                "from_mode": from_mode,
                "to_mode": to_mode,
                "time": float(t),
                "reason": reason,
                "shift_distance": float(state.shift_distance),
                "shift_velocity": float(state.shift_velocity),
            }
        )

    def run_simulation(self) -> SimulationResult:
        """Run the simulation and return results."""
        self.system_model.belt_model.reset_mode_state()
        self.system_model.slip_model.reset_mode_state()
        cvt_system_ode = self._get_ode_function()
        # Use a single global time grid for the entire simulation
        time_eval = np.linspace(0, self.TOTAL_SIM_TIME, 10000)

        # Track all solution segments
        all_t = []
        all_y = []

        current_time = 0
        current_state = self.INITIAL_STATE.to_array()
        initial_state = SystemState.from_array(current_state)
        v_b_star, _, _, _, _ = self.system_model.belt_model.get_kinematic_terms(
            initial_state
        )
        current_state[4] = v_b_star

        mode = "normal"
        locked_shift_distance = None
        mid_shift_enter_time: float | None = None
        last_mid_shift_wake_time = -float("inf")
        transition_count = 0
        max_transitions = 20
        termination_context: dict[str, Any] = {
            "reason_code": "unknown",
            "reason": "Simulation ended without a classified termination reason.",
            "mode": mode,
            "event": None,
            "event_time": None,
            "transition_count": 0,
            "max_transitions": max_transitions,
            "details": {},
        }

        def append_solution_segment(solution):
            t_seg = np.asarray(solution.t)
            if t_seg.size == 0:
                return
            y_seg = np.asarray(solution.y)
            if y_seg.ndim == 1:
                y_seg = y_seg.reshape(-1, 1)
            all_t.append(t_seg)
            all_y.append(y_seg)

        while current_time < self.TOTAL_SIM_TIME and transition_count < max_transitions:
            time_eval_segment = (
                time_eval[time_eval >= current_time]
                if current_time == 0
                else time_eval[time_eval > current_time]
            )

            if time_eval_segment.size == 0:
                termination_context = {
                    "reason_code": "max_time",
                    "reason": "Simulation reached the configured maximum time.",
                    "mode": mode,
                    "event": None,
                    "event_time": None,
                    "transition_count": transition_count,
                    "max_transitions": max_transitions,
                    "details": {
                        "time_eval_exhausted": True,
                    },
                }
                break

            if mode == "normal":
                base_mid_shift_steady_event = get_mid_shift_steady_event(
                    self.system_model
                )

                def guarded_mid_shift_steady_event(t, y):
                    # After waking from a locked mid-shift state, require a short
                    # cooldown before allowing another mid-shift lock attempt.
                    if (t - last_mid_shift_wake_time) < self.MID_SHIFT_RELOCK_DELAY:
                        return 1.0
                    return base_mid_shift_steady_event(t, y)

                guarded_mid_shift_steady_event.terminal = True
                guarded_mid_shift_steady_event.direction = -1

                events = [
                    get_shift_steady_event(self.system_model),
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
                solution = self._solve(
                    cvt_system_ode,
                    current_time,
                    current_state,
                    time_eval_segment,
                    events,
                )

                append_solution_segment(solution)

                if solution.t_events[0].size > 0:
                    # Enter full-shift locked mode
                    current_time = solution.t_events[0][0]
                    current_state = solution.y_events[0][0]
                    self._emit_transition(
                        "normal",
                        "full_shift",
                        current_time,
                        current_state,
                        "shift_steady_event",
                    )
                    mode = "full_shift"
                    transition_count += 1
                    continue

                if solution.t_events[1].size > 0:
                    # Enter mid-shift locked mode
                    current_time = solution.t_events[1][0]
                    current_state = solution.y_events[1][0]
                    locked_shift_distance = float(current_state[0])
                    self._emit_transition(
                        "normal",
                        "mid_shift",
                        current_time,
                        current_state,
                        "mid_shift_steady_event",
                    )
                    mode = "mid_shift"
                    mid_shift_enter_time = float(current_time)
                    transition_count += 1
                    continue

                # No mode-transition event: finished (car stop, end of interval, etc.)
                termination_context = self._build_termination_context(
                    solution=solution,
                    mode=mode,
                    event_names=event_names,
                    transition_count=transition_count,
                    max_transitions=max_transitions,
                )
                break

            if mode == "full_shift":
                locked_ode = self._get_locked_shift_ode_function(MAX_SHIFT)
                events = [
                    get_back_shift_event(self.system_model),
                    car_velocity_constraint_event,
                ]
                event_names = [
                    "back_shift_event",
                    "car_velocity_constraint_event",
                ]
                solution = self._solve(
                    locked_ode,
                    current_time,
                    current_state,
                    time_eval_segment,
                    events,
                )

                append_solution_segment(solution)

                if solution.t_events[0].size > 0:
                    # Resume normal shifting dynamics
                    current_time = solution.t_events[0][0]
                    current_state = solution.y_events[0][0]
                    self._emit_transition(
                        "full_shift",
                        "normal",
                        current_time,
                        current_state,
                        "back_shift_event",
                    )
                    mode = "normal"
                    transition_count += 1
                    continue

                termination_context = self._build_termination_context(
                    solution=solution,
                    mode=mode,
                    event_names=event_names,
                    transition_count=transition_count,
                    max_transitions=max_transitions,
                )
                break

            if mode == "mid_shift":
                if locked_shift_distance is None:
                    break

                locked_ode = self._get_locked_shift_ode_function(locked_shift_distance)

                base_mid_shift_wake_event = get_mid_shift_wake_event(self.system_model)

                def guarded_mid_shift_wake_event(t, y):
                    # Once we lock into mid-shift, keep that mode for a minimum
                    # dwell time before evaluating wake logic.
                    if (
                        mid_shift_enter_time is not None
                        and (t - mid_shift_enter_time) < self.MID_SHIFT_MIN_HOLD_TIME
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
                solution = self._solve(
                    locked_ode,
                    current_time,
                    current_state,
                    time_eval_segment,
                    events,
                )

                append_solution_segment(solution)

                if solution.t_events[0].size > 0:
                    # Resume normal shifting dynamics when imbalance grows again
                    current_time = solution.t_events[0][0]
                    current_state = solution.y_events[0][0]
                    self._emit_transition(
                        "mid_shift",
                        "normal",
                        current_time,
                        current_state,
                        "mid_shift_wake_event",
                    )
                    mode = "normal"
                    mid_shift_enter_time = None
                    last_mid_shift_wake_time = float(current_time)
                    transition_count += 1
                    continue

                termination_context = self._build_termination_context(
                    solution=solution,
                    mode=mode,
                    event_names=event_names,
                    transition_count=transition_count,
                    max_transitions=max_transitions,
                )
                break

        if transition_count >= max_transitions and current_time < self.TOTAL_SIM_TIME:
            termination_context = {
                "reason_code": "max_transitions",
                "reason": "Simulation stopped after hitting the mode-transition safety limit.",
                "mode": mode,
                "event": None,
                "event_time": None,
                "transition_count": transition_count,
                "max_transitions": max_transitions,
                "details": {
                    "safety_limit_reached": True,
                },
            }

        # Combine all solution segments
        if not all_t or not all_y:
            combined_t = np.array([current_time], dtype=float)
            combined_y = np.array(current_state, dtype=float).reshape(-1, 1)
        else:
            combined_t = np.concatenate(all_t)
            combined_y = np.hstack(all_y)

        combined_solution = CombinedSolution(combined_t, combined_y)

        final_state = SystemState.from_array(combined_y[:, -1])
        final_time = float(combined_t[-1])
        termination_context["mode"] = mode
        termination_context["final_time"] = final_time
        termination_context["reached_max_time"] = final_time >= (
            self.TOTAL_SIM_TIME - 1e-6
        )
        termination_context["transition_count"] = transition_count
        termination_context.setdefault("details", {})
        termination_context["details"].update(
            {
                "final_shift_distance": float(final_state.shift_distance),
                "final_shift_velocity": float(final_state.shift_velocity),
                "final_primary_pulley_angular_velocity": float(
                    final_state.primary_pulley_angular_velocity
                ),
                "final_secondary_pulley_angular_velocity": float(
                    final_state.secondary_pulley_angular_velocity
                ),
            }
        )

        if (
            termination_context.get("reason_code") == "unknown"
            and termination_context["reached_max_time"]
        ):
            termination_context["reason_code"] = "max_time"
            termination_context["reason"] = (
                "Simulation reached the configured maximum time."
            )

        return SimulationResult(
            combined_solution, termination_context=termination_context
        )

    def _build_termination_context(
        self,
        solution,
        mode: str,
        event_names: list[str],
        transition_count: int,
        max_transitions: int,
    ) -> dict[str, Any]:
        triggered_events: list[tuple[float, str]] = []
        for idx, event_name in enumerate(event_names):
            if idx >= len(solution.t_events):
                continue
            event_times = np.asarray(solution.t_events[idx])
            if event_times.size > 0:
                triggered_events.append((float(event_times[0]), event_name))

        if triggered_events:
            event_time, event_name = min(triggered_events, key=lambda item: item[0])
            return {
                "reason_code": "event",
                "reason": f"Simulation stopped because terminal event '{event_name}' fired.",
                "mode": mode,
                "event": event_name,
                "event_time": event_time,
                "transition_count": transition_count,
                "max_transitions": max_transitions,
                "details": {
                    "solver_status": int(solution.status),
                    "solver_message": str(solution.message),
                },
            }

        final_time = float(solution.t[-1]) if np.asarray(solution.t).size > 0 else 0.0
        reached_max_time = final_time >= (self.TOTAL_SIM_TIME - 1e-6)
        if reached_max_time:
            return {
                "reason_code": "max_time",
                "reason": "Simulation reached the configured maximum time.",
                "mode": mode,
                "event": None,
                "event_time": None,
                "transition_count": transition_count,
                "max_transitions": max_transitions,
                "details": {
                    "solver_status": int(solution.status),
                    "solver_message": str(solution.message),
                },
            }

        return {
            "reason_code": "solver_ended",
            "reason": "Simulation ended because the integrator finished without a terminal event.",
            "mode": mode,
            "event": None,
            "event_time": None,
            "transition_count": transition_count,
            "max_transitions": max_transitions,
            "details": {
                "solver_status": int(solution.status),
                "solver_message": str(solution.message),
            },
        }

    # Get the function without self for scipy
    def _get_ode_function(self):
        def ode_func(t: float, y: list[float]):
            return self._evaluate_cvt_system(t, y)

        return ode_func

    def _get_full_shift_ode_function(self):
        def ode_func(t: float, y: list[float]):
            return self._evaluate_full_shift_system(t, y)

        return ode_func

    def _get_locked_shift_ode_function(self, locked_shift_distance: float):
        def ode_func(t: float, y: list[float]):
            return self._evaluate_locked_shift_system(t, y, locked_shift_distance)

        return ode_func

    def _solve(
        self,
        ode_func: Callable[[float, list[float]], list[float]],  # (t, y) -> dydt
        start_time: float,
        initial_state: list[float],
        time_eval: np.ndarray,
        events: list,
    ):
        return solve_ivp(
            ode_func,
            (start_time, self.TOTAL_SIM_TIME),
            initial_state,
            t_eval=time_eval,
            events=events,
            atol=1e-6,
            rtol=1e-4,
        )

    def _print_progress(self, t: float, shift_distance: float):
        # Print progress
        progress_percent = (t / self.TOTAL_SIM_TIME) * 100
        # Print every 0.1% progress
        if progress_percent % 0.1 < 0.01:
            sys.stdout.write(
                f"\rProgress: {progress_percent:.1f}% [{'=' * int(progress_percent // 2)}{' ' * (50 - int(progress_percent // 2))}]"
            )
            sys.stdout.flush()

        # Call callback whenever progress changes by at least 0.1%
        if self.progress_callback:
            rounded_percent = round(progress_percent, 1)
            if rounded_percent != self._last_callback_percent:
                self._last_callback_percent = rounded_percent
                try:
                    self.progress_callback(
                        progress_percent, float(t), float(shift_distance)
                    )
                except TypeError:
                    # Backward compatibility for older single-argument callbacks.
                    self.progress_callback(progress_percent)

    def _evaluate_cvt_system(self, t: float, y: list[float]):
        """Evaluate system dynamics (phase 1: not at full shift).

        Returns derivatives of the state vector:
        dy[0] = d(shift_distance)/dt = shift_velocity
        dy[1] = d(shift_velocity)/dt = shift_acceleration
        dy[2] = d(primary_pulley_angular_velocity)/dt = primary_pulley_angular_accel
        dy[3] = d(secondary_pulley_angular_velocity)/dt = secondary_pulley_angular_accel
        dy[4] = d(v_b)/dt
        """
        state = SystemState.from_array(y)

        # Do not mutate the solver state in normal mode. Use a constrained copy
        # for geometry/force evaluation while preserving continuous integration.
        raw_shift_distance = state.shift_distance
        raw_shift_velocity = state.shift_velocity
        eval_shift_distance = float(np.clip(raw_shift_distance, 0.0, MAX_SHIFT))
        eval_shift_velocity = raw_shift_velocity
        if raw_shift_distance <= 0.0 and raw_shift_velocity < 0.0:
            eval_shift_velocity = 0.0
        elif raw_shift_distance >= MAX_SHIFT and raw_shift_velocity > 0.0:
            eval_shift_velocity = 0.0

        eval_state = SystemState(
            shift_distance=eval_shift_distance,
            shift_velocity=eval_shift_velocity,
            primary_pulley_angular_velocity=state.primary_pulley_angular_velocity,
            secondary_pulley_angular_velocity=state.secondary_pulley_angular_velocity,
            v_b=state.v_b,
        )
        self._print_progress(t, eval_state.shift_distance)

        # Get system breakdown (this calculates everything in correct order)
        drivetrain_breakdown = self.system_model.get_breakdown(eval_state)

        # Extract accelerations
        secondary_pulley_angular_accel_from_torques = (
            drivetrain_breakdown.secondary_pulley.secondary_pulley_angular_acceleration
        )
        primary_pulley_angular_accel = (
            drivetrain_breakdown.primary_pulley.primary_pulley_angular_acceleration
        )
        shift_acceleration = drivetrain_breakdown.cvt_dynamics.acceleration

        # Prevent acceleration from pushing past boundaries (metal hitting metal)
        if eval_shift_distance <= 0 and shift_acceleration < 0:
            shift_acceleration = 0
        elif eval_shift_distance >= MAX_SHIFT and shift_acceleration > 0:
            shift_acceleration = 0

        v_b_dot = drivetrain_breakdown.belt_state.v_b_dot

        return [
            eval_shift_velocity,
            shift_acceleration,
            primary_pulley_angular_accel,
            secondary_pulley_angular_accel_from_torques,
            v_b_dot,
        ]

    def _evaluate_full_shift_system(self, t: float, y: list[float]):
        """Evaluate system dynamics (phase 2: at full shift).

        At full shift, shift_distance and shift_velocity are held constant.
        Only the pulley angular velocities continue to evolve.
        """
        state = SystemState.from_array(y)
        self._print_progress(t, MAX_SHIFT)
        # Force the shifting variables to remain constant at full shift.
        state.shift_distance = MAX_SHIFT
        state.shift_velocity = 0

        # CRITICAL: Update the actual y array that scipy saves
        constrained_y = state.to_array()
        for i in range(len(y)):
            y[i] = constrained_y[i]

        # Get system breakdown for full shift case
        drivetrain_breakdown = self.system_model.get_breakdown(state)

        secondary_pulley_angular_accel_from_torques = (
            drivetrain_breakdown.secondary_pulley.secondary_pulley_angular_acceleration
        )
        primary_pulley_angular_accel = (
            drivetrain_breakdown.primary_pulley.primary_pulley_angular_acceleration
        )

        return [
            0,  # shift_distance held constant
            0,  # shift_velocity held constant
            primary_pulley_angular_accel,  # primary pulley continues to evolve
            secondary_pulley_angular_accel_from_torques,  # secondary pulley continues to evolve
            drivetrain_breakdown.belt_state.v_b_dot,
        ]

    def _evaluate_locked_shift_system(
        self,
        t: float,
        y: list[float],
        locked_shift_distance: float,
    ):
        """Evaluate system dynamics with shift DOF locked at an interior position."""
        state = SystemState.from_array(y)
        self._print_progress(t, locked_shift_distance)

        state.shift_distance = locked_shift_distance
        state.shift_velocity = 0

        constrained_y = state.to_array()
        for i in range(len(y)):
            y[i] = constrained_y[i]

        drivetrain_breakdown = self.system_model.get_breakdown(state)
        secondary_pulley_angular_accel_from_torques = (
            drivetrain_breakdown.secondary_pulley.secondary_pulley_angular_acceleration
        )
        primary_pulley_angular_accel = (
            drivetrain_breakdown.primary_pulley.primary_pulley_angular_acceleration
        )

        return [
            0,
            0,
            primary_pulley_angular_accel,
            secondary_pulley_angular_accel_from_torques,
            drivetrain_breakdown.belt_state.v_b_dot,
        ]
