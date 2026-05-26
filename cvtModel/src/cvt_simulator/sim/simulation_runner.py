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
from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY
from cvt_simulator.sim_utils.simulation_branches import (
    SimulationBranchManager,
    SimulationBranchTransition,
)


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
        branch_manager = SimulationBranchManager(
            contact_model=self.contact_model,
            mid_shift_min_hold_time=self.MID_SHIFT_MIN_HOLD_TIME,
            mid_shift_relock_delay=self.MID_SHIFT_RELOCK_DELAY,
            progress_tracker=self._print_progress,
        )

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

            ode_func = branch_manager.get_ode_function(mode, locked_shift_distance)
            events, event_names = branch_manager.get_events(
                mode,
                locked_shift_distance,
                mid_shift_enter_time,
                last_mid_shift_wake_time,
            )

            solution = self._solve(
                ode_func,
                current_time,
                current_state,
                time_eval_segment,
                events,
            )

            append_solution_segment(solution, mode)

            transition = branch_manager.get_transition(
                mode,
                solution,
                event_names,
                locked_shift_distance,
                mid_shift_enter_time,
                last_mid_shift_wake_time,
            )

            if transition.did_transition:
                self._emit_transition(
                    from_mode=mode,
                    to_mode=transition.next_mode,
                    t=transition.next_time,
                    state_array=transition.next_state,
                    reason=transition.reason,
                )
                mode = transition.next_mode
                current_time = transition.next_time
                current_state = transition.next_state
                locked_shift_distance = transition.locked_shift_distance
                mid_shift_enter_time = transition.mid_shift_enter_time
                last_mid_shift_wake_time = transition.last_mid_shift_wake_time
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

