import sys
from typing import Any, Callable, Optional

import numpy as np
from scipy.integrate import solve_ivp

from cvt_simulator.core.data_types import SlipBranch
from cvt_simulator.core.dynamics.contact_dynamics_model import ContactDynamicsModel
from cvt_simulator.core.components.engine import EngineModel
from cvt_simulator.core.components.primary_pulley import PrimaryPulley
from cvt_simulator.core.components.secondary_pulley import SecondaryPulley
from cvt_simulator.core.components.vehicle_load import LoadModel
from cvt_simulator.constants.car_specs import (
    GEARBOX_RATIO,
    ENGINE_INERTIA,
    SECONDARY_INERTIA,
    HELIX_RADIUS,
)
from cvt_simulator.constants.engine_specs import safe_torque_curve
from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY
from cvt_simulator.ramps.piecewise_ramp import PiecewiseRamp
from cvt_simulator.ramps.theta_ramp import ThetaRamp
from cvt_simulator.sim.simulation_branches import SimulationBranchManager
from cvt_simulator.sim.system_state import SystemState
from cvt_simulator.sim_utils.simulation_args import SimulationArgs
from cvt_simulator.sim_utils.simulation_result import SimulationResult
from cvt_simulator.utils.conversions import deg_to_rad, rpm_to_rad_s


class CombinedSolution:
    """Small wrapper matching the shape expected by SimulationResult."""

    def __init__(self, t, y, modes=None):
        self.t = t
        self.y = y
        self.modes = modes


class SimulationRunner:
    """Runs the segmented CVT simulation.

    The runner owns the accepted simulation modes and the solve loop.

    It does not evaluate derivatives directly.
    It does not decide event formulas directly.
    It delegates those to SimulationBranchManager.
    """

    TOTAL_SIM_TIME = 15.0

    # Hysteresis controls to prevent mid-shift lock/unlock chatter.
    MID_SHIFT_MIN_HOLD_TIME = 0.02
    MID_SHIFT_RELOCK_DELAY = 0.05

    INITIAL_STATE = SystemState(
        s=0.0,
        s_dot=0.0,
        # Initial secondary pulley angular velocity derived from initial car velocity.
        ω_s=rpm_to_rad_s(0.1)
        / (GEARBOX_RATIO * CVT_GEOMETRY.effective_cvt_ratio(0)),
        # Initial primary pulley angular velocity.
        ω_p=rpm_to_rad_s(1800),
        v_b=0.0,
    )

    def __init__(
        self,
        contact_model: ContactDynamicsModel,
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

    def run_simulation(self) -> SimulationResult:
        """Run the simulation and return results."""

        branch_manager = SimulationBranchManager(
            contact_model=self.contact_model,
            mid_shift_min_hold_time=self.MID_SHIFT_MIN_HOLD_TIME,
            mid_shift_relock_delay=self.MID_SHIFT_RELOCK_DELAY,
            progress_tracker=self._print_progress,
        )

        time_eval = np.linspace(0.0, self.TOTAL_SIM_TIME, 10000)

        all_t: list[np.ndarray] = []
        all_y: list[np.ndarray] = []
        all_modes: list[str] = []

        current_time = 0.0
        current_state = self.INITIAL_STATE.to_array()

        shift_mode = "normal"

        # With v_b initially zero while the primary is spinning, the initial
        # contact state is a slip state. This can later be replaced by
        # an initial-branch helper if desired.
        contact_branch = SlipBranch.PRIMARY_SLIP

        locked_shift_distance: float | None = None
        mid_shift_enter_time: float | None = None
        last_mid_shift_wake_time = -float("inf")

        transition_count = 0

        # Contact events can add many valid segment boundaries, so this should
        # be higher than the old shift-only limit.
        max_transitions = 200

        termination_context: dict[str, Any] = self._initial_termination_context(
            mode=self._mode_label(shift_mode, contact_branch),
            max_transitions=max_transitions,
        )

        while current_time < self.TOTAL_SIM_TIME and transition_count < max_transitions:
            time_eval_segment = self._time_eval_after(
                time_eval=time_eval,
                current_time=current_time,
            )

            if time_eval_segment.size == 0:
                termination_context = self._time_eval_exhausted_context(
                    mode=self._mode_label(shift_mode, contact_branch),
                    transition_count=transition_count,
                    max_transitions=max_transitions,
                )
                break

            segment_mode = self._mode_label(shift_mode, contact_branch)

            ode_func = branch_manager.get_ode_function(
                shift_mode=shift_mode,
                contact_branch=contact_branch,
                locked_shift_distance=locked_shift_distance,
            )

            events, event_names = branch_manager.get_events(
                shift_mode=shift_mode,
                contact_branch=contact_branch,
                locked_shift_distance=locked_shift_distance,
                mid_shift_enter_time=mid_shift_enter_time,
                last_mid_shift_wake_time=last_mid_shift_wake_time,
            )

            solution = self._solve(
                ode_func=ode_func,
                start_time=current_time,
                initial_state=current_state,
                time_eval=time_eval_segment,
                events=events,
            )

            self._append_solution_segment(
                solution=solution,
                segment_mode=segment_mode,
                all_t=all_t,
                all_y=all_y,
                all_modes=all_modes,
            )

            transition = branch_manager.get_transition(
                shift_mode=shift_mode,
                contact_branch=contact_branch,
                solution=solution,
                event_names=event_names,
                locked_shift_distance=locked_shift_distance,
                mid_shift_enter_time=mid_shift_enter_time,
                last_mid_shift_wake_time=last_mid_shift_wake_time,
            )

            if transition.did_transition:
                if transition.next_time is None or transition.next_state is None:
                    raise RuntimeError(
                        "Branch transition was marked as active, but no event "
                        "time/state was provided."
                    )

                next_mode = self._mode_label(
                    transition.next_shift_mode,
                    transition.next_contact_branch,
                )

                self._emit_transition(
                    from_mode=segment_mode,
                    to_mode=next_mode,
                    t=transition.next_time,
                    state_array=transition.next_state,
                    reason=transition.reason or "mode_transition",
                )

                shift_mode = transition.next_shift_mode
                contact_branch = transition.next_contact_branch

                current_time = transition.next_time
                current_state = transition.next_state

                locked_shift_distance = transition.locked_shift_distance
                mid_shift_enter_time = transition.mid_shift_enter_time
                last_mid_shift_wake_time = transition.last_mid_shift_wake_time

                transition_count += 1
                continue

            termination_context = self._build_termination_context(
                solution=solution,
                mode=segment_mode,
                event_names=event_names,
                transition_count=transition_count,
                max_transitions=max_transitions,
            )
            break

        if transition_count >= max_transitions and current_time < self.TOTAL_SIM_TIME:
            termination_context = {
                "reason_code": "max_transitions",
                "reason": (
                    "Simulation stopped after hitting the mode-transition "
                    "safety limit."
                ),
                "mode": self._mode_label(shift_mode, contact_branch),
                "event": None,
                "event_time": None,
                "transition_count": transition_count,
                "max_transitions": max_transitions,
                "details": {
                    "safety_limit_reached": True,
                },
            }

        combined_solution = self._combine_solution_segments(
            all_t=all_t,
            all_y=all_y,
            all_modes=all_modes,
            fallback_time=current_time,
            fallback_state=current_state,
        )

        self._finalize_termination_context(
            termination_context=termination_context,
            combined_solution=combined_solution,
            shift_mode=shift_mode,
            contact_branch=contact_branch,
            transition_count=transition_count,
        )

        return SimulationResult(
            combined_solution,
            termination_context=termination_context,
        )

    def _solve(
        self,
        ode_func: Callable[[float, list[float]], list[float]],
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

    def _print_progress(self, t: float, shift_distance: float):
        progress_percent = (t / self.TOTAL_SIM_TIME) * 100.0

        if progress_percent % 0.1 < 0.01:
            sys.stdout.write(
                f"\rProgress: {progress_percent:.1f}% "
                f"[{'=' * int(progress_percent // 2)}"
                f"{' ' * (50 - int(progress_percent // 2))}]"
            )
            sys.stdout.flush()

        if self.progress_callback:
            rounded_percent = round(progress_percent, 1)

            if rounded_percent != self._last_callback_percent:
                self._last_callback_percent = rounded_percent

                try:
                    self.progress_callback(
                        progress_percent,
                        float(t),
                        float(shift_distance),
                    )
                except TypeError:
                    self.progress_callback(progress_percent)

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
                "reason": (
                    f"Simulation stopped because terminal event "
                    f"'{event_name}' fired."
                ),
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
            "reason": (
                "Simulation ended because the integrator finished without a "
                "terminal event."
            ),
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

    def _initial_termination_context(
        self,
        mode: str,
        max_transitions: int,
    ) -> dict[str, Any]:
        return {
            "reason_code": "unknown",
            "reason": "Simulation ended without a classified termination reason.",
            "mode": mode,
            "event": None,
            "event_time": None,
            "transition_count": 0,
            "max_transitions": max_transitions,
            "details": {},
        }

    def _time_eval_exhausted_context(
        self,
        mode: str,
        transition_count: int,
        max_transitions: int,
    ) -> dict[str, Any]:
        return {
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

    def _finalize_termination_context(
        self,
        termination_context: dict[str, Any],
        combined_solution: CombinedSolution,
        shift_mode: str,
        contact_branch: SlipBranch,
        transition_count: int,
    ) -> None:
        final_state = SystemState.from_array(combined_solution.y[:, -1])
        final_time = float(combined_solution.t[-1])

        termination_context["mode"] = self._mode_label(shift_mode, contact_branch)
        termination_context["final_time"] = final_time
        termination_context["reached_max_time"] = final_time >= (
            self.TOTAL_SIM_TIME - 1e-6
        )
        termination_context["transition_count"] = transition_count
        termination_context.setdefault("details", {})
        termination_context["details"].update(
            {
                "final_shift_mode": shift_mode,
                "final_contact_branch": contact_branch.name,
                "final_shift_distance": float(final_state.s),
                "final_shift_velocity": float(final_state.s_dot),
                "final_primary_pulley_angular_velocity": float(final_state.ω_p),
                "final_secondary_pulley_angular_velocity": float(final_state.ω_s),
                "final_belt_speed": float(final_state.v_b),
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

    def _append_solution_segment(
        self,
        solution,
        segment_mode: str,
        all_t: list[np.ndarray],
        all_y: list[np.ndarray],
        all_modes: list[str],
    ) -> None:
        t_seg = np.asarray(solution.t)

        if t_seg.size == 0:
            return

        y_seg = np.asarray(solution.y)

        if y_seg.ndim == 1:
            y_seg = y_seg.reshape(-1, 1)

        all_t.append(t_seg)
        all_y.append(y_seg)
        all_modes.extend([segment_mode] * int(t_seg.size))

    def _combine_solution_segments(
        self,
        all_t: list[np.ndarray],
        all_y: list[np.ndarray],
        all_modes: list[str],
        fallback_time: float,
        fallback_state: np.ndarray,
    ) -> CombinedSolution:
        if not all_t or not all_y:
            combined_t = np.array([fallback_time], dtype=float)
            combined_y = np.array(fallback_state, dtype=float).reshape(-1, 1)
            return CombinedSolution(combined_t, combined_y, all_modes)

        combined_t = np.concatenate(all_t)
        combined_y = np.hstack(all_y)

        return CombinedSolution(combined_t, combined_y, all_modes)

    @staticmethod
    def _time_eval_after(
        time_eval: np.ndarray,
        current_time: float,
    ) -> np.ndarray:
        if current_time == 0:
            return time_eval[time_eval >= current_time]

        return time_eval[time_eval > current_time]

    @staticmethod
    def _mode_label(
        shift_mode: str,
        contact_branch: SlipBranch,
    ) -> str:
        return f"{shift_mode}:{contact_branch.name}"