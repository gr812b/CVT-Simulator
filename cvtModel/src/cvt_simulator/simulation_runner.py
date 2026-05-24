import sys
import numpy as np
from typing import Callable, Optional, Any
from scipy.integrate import solve_ivp
from cvt_simulator.sim_utils.system_state import SystemState
from cvt_simulator.sim_utils.simulation_result import SimulationResult
from cvt_simulator.core.dynamics.contact_dynamics_model import ContactDynamicsModel
from cvt_simulator.constants.car_specs import (
    GEARBOX_RATIO,
    MAX_SHIFT,
    ENGINE_INERTIA,
    SECONDARY_INERTIA,
    HELIX_RADIUS,
)
from cvt_simulator.core.components.engine import EngineModel
from cvt_simulator.core.components.primary_pulley import PrimaryPulley
from cvt_simulator.core.components.secondary_pulley import SecondaryPulley
from cvt_simulator.core.components.vehicle_load import LoadModel
from cvt_simulator.ramps.piecewise_ramp import PiecewiseRamp
from cvt_simulator.ramps.theta_ramp import ThetaRamp
from cvt_simulator.utils.conversions import rpm_to_rad_s, deg_to_rad
from cvt_simulator.constants.engine_specs import safe_torque_curve
from cvt_simulator.sim_utils.simulation_args import SimulationArgs
from cvt_simulator.sim_utils.simulation_constraints import (
    car_velocity_constraint_event,
    get_shift_steady_event,
    get_back_shift_event,
    get_mid_shift_steady_event,
    get_mid_shift_wake_event,
    shift_constraint_event,
)
from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY


# Helper class to wrap data
class CombinedSolution:
    def __init__(self, t, y, modes=None):
        self.t = t
        self.y = y
        self.modes = modes


class SimulationRunner:
    """Runs a two-phase CVT system simulation."""

    TOTAL_SIM_TIME = 15  # seconds
    # Hysteresis controls to prevent mid-shift lock/unlock chatter.
    MID_SHIFT_MIN_HOLD_TIME = 0.02  # seconds
    MID_SHIFT_RELOCK_DELAY = 0.05  # seconds
    INITIAL_STATE = SystemState(
        s=0.0,
        s_dot=0.0,
        # Initial secondary pulley angular velocity derived from initial car velocity
        ω_s=rpm_to_rad_s(0.1)
        / (GEARBOX_RATIO * CVT_GEOMETRY.effective_cvt_ratio(0)),
        # Initial primary pulley angular velocity (engine speed)
        ω_p=rpm_to_rad_s(1800),
        v_b=0.0,
    )

    def __init__(
        self,
        contact_model: ContactDynamicsModel,
        # Optional progress callback. Preferred signature:
        #   callback(progress_percent, sim_time_s, shift_distance)
        # Backward-compatible signature callback(progress_percent) is also supported.
        progress_callback: Optional[Callable[..., None]] = None,
        transition_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ):
        self.contact_model = contact_model
        self.progress_callback = progress_callback
        self.transition_callback = transition_callback
        self._last_callback_percent = -1.0

    @classmethod
    def from_simulation_args(
        cls,
        args: SimulationArgs,
        progress_callback: Optional[Callable[..., None]] = None,
        transition_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> "SimulationRunner":
        primary_ramp = PiecewiseRamp.from_config(args.primary_ramp_config)
        secondary_ramp = PiecewiseRamp.from_config(args.secondary_ramp_config)

        primary_pulley = PrimaryPulley(
            spring_coeff_comp=args.primary_spring_rate,
            initial_compression=args.primary_spring_pretension,
            flyweight_mass=args.flyweight_mass,
            ramp=primary_ramp,
        )
        secondary_pulley = SecondaryPulley(
            spring_coeff_tors=args.secondary_torsion_spring_rate,
            spring_coeff_comp=args.secondary_compression_spring_rate,
            initial_rotation=deg_to_rad(args.secondary_rotational_spring_pretension),
            initial_compression=args.secondary_linear_spring_pretension,
            helix_ramp=ThetaRamp(secondary_ramp, HELIX_RADIUS),
            helix_radius=HELIX_RADIUS,
        )
        engine_model = EngineModel(safe_torque_curve)
        load_model = LoadModel(
            car_mass=args.vehicle_weight + args.driver_weight,
            incline_angle=deg_to_rad(args.angle_of_incline),
        )
        contact_model = ContactDynamicsModel(
            primary_pulley=primary_pulley,
            secondary_pulley=secondary_pulley,
            primary_inertia=ENGINE_INERTIA,
            secondary_inertia=SECONDARY_INERTIA,
            belt_mass=ContactDynamicsModel.compute_belt_mass(),
            engine_model=engine_model,
            load_model=load_model,
        )
        return cls(
            contact_model=contact_model,
            progress_callback=progress_callback,
            transition_callback=transition_callback,
        )

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
                "shift_distance": float(state.s),
                "shift_velocity": float(state.s_dot),
            }
        )

    def run_simulation(self) -> SimulationResult:
        """Run the simulation and return results."""
        cvt_system_ode = self._get_ode_function()
        # Use a single global time grid for the entire simulation
        time_eval = np.linspace(0, self.TOTAL_SIM_TIME, 10000)

        # Track all solution segments
        all_t = []
        all_y = []
        all_modes = []

        current_time = 0
        current_state = self.INITIAL_STATE.to_array()

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

        def append_solution_segment(solution, segment_mode: str):
            t_seg = np.asarray(solution.t)
            if t_seg.size == 0:
                return
            y_seg = np.asarray(solution.y)
            if y_seg.ndim == 1:
                y_seg = y_seg.reshape(-1, 1)
            all_t.append(t_seg)
            all_y.append(y_seg)
            all_modes.extend([segment_mode] * int(t_seg.size))

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
                    self.contact_model
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
                solution = self._solve(
                    cvt_system_ode,
                    current_time,
                    current_state,
                    time_eval_segment,
                    events,
                )

                append_solution_segment(solution, mode)

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
                    get_back_shift_event(self.contact_model),
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

                append_solution_segment(solution, mode)

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

                base_mid_shift_wake_event = get_mid_shift_wake_event(self.contact_model)

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

                append_solution_segment(solution, mode)

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

        combined_solution = CombinedSolution(combined_t, combined_y, all_modes)

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
                "final_shift_distance": float(final_state.s),
                "final_shift_velocity": float(final_state.s_dot),
                "final_primary_pulley_angular_velocity": float(
                    final_state.ω_p
                ),
                "final_secondary_pulley_angular_velocity": float(
                    final_state.ω_s
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
        self._print_progress(t, eval_state.s)

        # Get system breakdown (this calculates everything in correct order)
        contact_breakdown = self.contact_model.get_breakdown(eval_state)

        # Extract acceleration
        shift_acceleration = contact_breakdown.shift.acceleration

        # Prevent acceleration from pushing past boundaries (metal hitting metal)
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

    def _evaluate_full_shift_system(self, t: float, y: list[float]):
        """Evaluate system dynamics (phase 2: at full shift).

        At full shift, shift_distance and shift_velocity are held constant.
        Only the pulley angular velocities continue to evolve.
        """
        state = SystemState.from_array(y)
        self._print_progress(t, MAX_SHIFT)
        # Force the shifting variables to remain constant at full shift.
        state.s = MAX_SHIFT
        state.s_dot = 0

        # CRITICAL: Update the actual y array that scipy saves
        constrained_y = state.to_array()
        for i in range(len(y)):
            y[i] = constrained_y[i]

        # Get system breakdown for full shift case
        contact_breakdown = self.contact_model.get_breakdown(state)

        return [
            0,  # shift_distance held constant
            0,  # shift_velocity held constant
            contact_breakdown.drivetrain.ω_p_dot,  # primary pulley continues to evolve
            contact_breakdown.drivetrain.ω_s_dot,  # secondary pulley continues to evolve
            contact_breakdown.drivetrain.v_b_dot,
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

        state.s = locked_shift_distance
        state.s_dot = 0

        constrained_y = state.to_array()
        for i in range(len(y)):
            y[i] = constrained_y[i]

        contact_breakdown = self.contact_model.get_breakdown(state)

        return [
            0,
            0,
            contact_breakdown.drivetrain.ω_p_dot,
            contact_breakdown.drivetrain.ω_s_dot,
            contact_breakdown.drivetrain.v_b_dot,
        ]
