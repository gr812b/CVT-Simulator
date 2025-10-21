import sys
import numpy as np
from typing import Callable
from scipy.integrate import solve_ivp
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.utils.simulation_result import SimulationResult
from cvt_simulator.models.system_model import SystemModel
from cvt_simulator.constants.car_specs import (
    GEARBOX_RATIO,
    WHEEL_RADIUS,
    MAX_SHIFT,
)
from cvt_simulator.utils.conversions import rpm_to_rad_s
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.utils.simulation_constraints import (
    car_velocity_constraint_event,
    get_shift_steady_event,
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
    INITIAL_STATE = SystemState(
        car_velocity=rpm_to_rad_s(1800)
        / (GEARBOX_RATIO * tm.current_cvt_ratio(0))
        * WHEEL_RADIUS,
        car_position=0.0,
        shift_velocity=0.0,
        shift_distance=0.0,
        engine_angular_velocity=rpm_to_rad_s(1800),
    )
    slip_breakdowns = []

    def __init__(
        self,
        system_model: SystemModel,
    ):
        self.system_model = system_model

    def run_simulation(self) -> SimulationResult:
        """Run the simulation and return results."""
        cvt_system_ode = self._get_ode_function()
        # Use a single global time grid for the entire simulation
        time_eval = np.linspace(0, self.TOTAL_SIM_TIME, 10000)
        events = [
            get_shift_steady_event(self.system_model.cvt_shift_model),
            car_velocity_constraint_event,
            shift_constraint_event,
        ]

        solution_phase1 = self._solve(
            cvt_system_ode,
            0,
            self.INITIAL_STATE.to_array(),
            time_eval,
            events,
        )

        # This will be true if we hit full shift
        if solution_phase1.t_events[0].size > 0:
            event_time = solution_phase1.t_events[0][0]
            event_state = solution_phase1.y_events[0][0]

            cvt_system_full_shift_ode = self._get_full_shift_ode_function()

            # Use the remaining portion of the original time grid for phase 2
            time_eval_phase2 = time_eval[time_eval > event_time]

            if time_eval_phase2.size > 0:
                solution_phase2 = self._solve(
                    cvt_system_full_shift_ode,
                    event_time,
                    event_state,
                    time_eval_phase2,
                    [car_velocity_constraint_event],
                )

                # Phase 1 output is already truncated by the event; just append phase 2
                combined_t = np.concatenate([solution_phase1.t, solution_phase2.t])
                combined_y = np.hstack(
                    [
                        solution_phase1.y,
                        solution_phase2.y,
                    ]
                )
            else:
                # No remaining time points to evaluate in phase 2
                combined_t = solution_phase1.t
                combined_y = solution_phase1.y
        else:
            # Otherwise, use the phase 1 solution entirely.
            combined_t = solution_phase1.t
            combined_y = solution_phase1.y

        combined_solution = CombinedSolution(combined_t, combined_y)
        return SimulationResult(combined_solution)

    # Get the function without self for scipy
    def _get_ode_function(self):
        def ode_func(t: float, y: list[float]):
            return self._evaluate_cvt_system(t, y)

        return ode_func

    def _get_full_shift_ode_function(self):
        def ode_func(t: float, y: list[float]):
            return self._evaluate_full_shift_system(t, y)

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

    def _print_progress(self, t):
        # Print progress
        progress_percent = (t / self.TOTAL_SIM_TIME) * 100
        # Print every 0.1% progress
        if progress_percent % 0.1 < 0.01:
            sys.stdout.write(
                f"\rProgress: {progress_percent:.1f}% [{'=' * int(progress_percent // 2)}{' ' * (50 - int(progress_percent // 2))}]"
            )
            sys.stdout.flush()

    def _evaluate_cvt_system(self, t: float, y: list[float]):
        """Evaluate system dynamics (phase 1: not at full shift)."""
        state = SystemState.from_array(y)
        self._print_progress(t)

        # TODO: Remove this (should be handled by constraints)
        shift_velocity = state.shift_velocity
        shift_distance = state.shift_distance
        if shift_distance < 0:
            state.shift_distance = 0
            state.shift_velocity = max(0, shift_velocity)

        elif shift_distance > MAX_SHIFT:
            state.shift_distance = MAX_SHIFT
            state.shift_velocity = min(0, shift_velocity)

        # Get system breakdown (this calculates everything in correct order)
        system_breakdown = self.system_model.get_breakdown(state)

        # Extract accelerations from breakdown
        car_acceleration = system_breakdown.car.acceleration
        engine_angular_accel = system_breakdown.engine.angular_acceleration
        shift_acceleration = system_breakdown.cvt.acceleration

        return [
            car_acceleration,
            state.car_velocity,
            shift_acceleration,
            state.shift_velocity,
            engine_angular_accel,
        ]

    def _evaluate_full_shift_system(self, t: float, y: list[float]):
        """Evaluate system dynamics (phase 2: at full shift)."""
        state = SystemState.from_array(y)
        self._print_progress(t)
        # Force the shifting variables to remain constant at full shift.
        state.shift_distance = MAX_SHIFT
        state.shift_velocity = 0

        # Get system breakdown for full shift case
        system_breakdown = self.system_model.get_breakdown(state)

        car_acceleration = system_breakdown.car.acceleration
        engine_angular_accel = system_breakdown.engine.angular_acceleration

        return [
            car_acceleration,
            state.car_velocity,
            0,
            0,
            engine_angular_accel,
        ]
