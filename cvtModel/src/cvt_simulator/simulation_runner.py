import sys
import numpy as np
from typing import Callable, Optional
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
    get_back_shift_event,
    shift_constraint_event,
)


# Helper class to wrap data
class CombinedSolution:
    def __init__(self, t, y):
        self.t = t
        self.y = y


class SimulationRunner:
    """Runs a two-phase CVT system simulation."""

    TOTAL_SIM_TIME = 30  # seconds
    INITIAL_STATE = SystemState(
        shift_distance=0.0,
        shift_velocity=0.0,
        # Initial secondary pulley angular velocity derived from initial car velocity
        secondary_pulley_angular_velocity=rpm_to_rad_s(0.1)
        / (GEARBOX_RATIO * tm.current_effective_cvt_ratio(0)),
        # Initial primary pulley angular velocity (engine speed)
        primary_pulley_angular_velocity=rpm_to_rad_s(1800),
    )

    def __init__(
        self,
        system_model: SystemModel,
        # Optional progress callback function that takes a float percentage (0-100)
        progress_callback: Optional[Callable[[float], None]] = None,
    ):
        self.system_model = system_model
        self.progress_callback = progress_callback
        self._last_callback_percent = -1.0

    def run_simulation(self) -> SimulationResult:
        """Run the simulation and return results."""
        cvt_system_ode = self._get_ode_function()
        # Use a single global time grid for the entire simulation
        time_eval = np.linspace(0, self.TOTAL_SIM_TIME, 10000)

        # Track all solution segments
        all_t = []
        all_y = []

        current_time = 0
        current_state = self.INITIAL_STATE.to_array()

        # Phase 1: Normal shifting until full shift is reached
        events_phase1 = [
            get_shift_steady_event(self.system_model),
            car_velocity_constraint_event,
            shift_constraint_event,
        ]

        time_eval_phase1 = time_eval[time_eval >= current_time]
        solution_phase1 = self._solve(
            cvt_system_ode,
            current_time,
            current_state,
            time_eval_phase1,
            events_phase1,
        )

        all_t.append(solution_phase1.t)
        all_y.append(solution_phase1.y)

        # Check if we hit full shift (event 0)
        if solution_phase1.t_events[0].size > 0:
            current_time = solution_phase1.t_events[0][0]
            current_state = solution_phase1.y_events[0][0]

            # Phase 2: At full shift - loop to handle potential back-shifting
            max_phases = 10  # Prevent infinite loops
            phase_count = 0

            while phase_count < max_phases and current_time < self.TOTAL_SIM_TIME:
                cvt_system_full_shift_ode = self._get_full_shift_ode_function()
                time_eval_phase2 = time_eval[time_eval > current_time]

                if time_eval_phase2.size == 0:
                    break

                # At full shift, check for back-shift event
                events_phase2 = [
                    get_back_shift_event(self.system_model),
                    car_velocity_constraint_event,
                ]

                solution_phase2 = self._solve(
                    cvt_system_full_shift_ode,
                    current_time,
                    current_state,
                    time_eval_phase2,
                    events_phase2,
                )

                all_t.append(solution_phase2.t)
                all_y.append(solution_phase2.y)

                # Check if back-shift event occurred (event 0)
                if solution_phase2.t_events[0].size > 0:
                    current_time = solution_phase2.t_events[0][0]
                    current_state = solution_phase2.y_events[0][0]

                    # Phase 3: Back-shifting - return to normal dynamics
                    time_eval_phase3 = time_eval[time_eval > current_time]

                    if time_eval_phase3.size == 0:
                        break

                    events_phase3 = [
                        get_shift_steady_event(self.system_model),
                        car_velocity_constraint_event,
                        shift_constraint_event,
                    ]

                    solution_phase3 = self._solve(
                        cvt_system_ode,
                        current_time,
                        current_state,
                        time_eval_phase3,
                        events_phase3,
                    )

                    all_t.append(solution_phase3.t)
                    all_y.append(solution_phase3.y)

                    # Check if we reached full shift again (event 0)
                    if solution_phase3.t_events[0].size > 0:
                        current_time = solution_phase3.t_events[0][0]
                        current_state = solution_phase3.y_events[0][0]
                        phase_count += 1
                        # Continue loop to handle next full-shift phase
                    else:
                        # Simulation ended without reaching full shift again
                        break
                else:
                    # Stayed at full shift until end or car stopped
                    break

        # Combine all solution segments
        combined_t = np.concatenate(all_t)
        combined_y = np.hstack(all_y)

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

        # Call callback whenever progress changes by at least 0.1%
        if self.progress_callback:
            rounded_percent = round(progress_percent, 1)
            if rounded_percent != self._last_callback_percent:
                self._last_callback_percent = rounded_percent
                self.progress_callback(progress_percent)

    def _evaluate_cvt_system(self, t: float, y: list[float]):
        """Evaluate system dynamics (phase 1: not at full shift).
        
        Returns derivatives of the 4 DOF state vector:
        dy[0] = d(shift_distance)/dt = shift_velocity
        dy[1] = d(shift_velocity)/dt = shift_acceleration
        dy[2] = d(primary_pulley_angular_velocity)/dt = primary_pulley_angular_accel
        dy[3] = d(secondary_pulley_angular_velocity)/dt = secondary_pulley_angular_accel
        """
        state = SystemState.from_array(y)
        self._print_progress(t)

        # TODO: Remove this (should be handled by constraints)
        shift_velocity = state.shift_velocity
        shift_distance = state.shift_distance
        if shift_distance <= 0:
            state.shift_distance = 0
            state.shift_velocity = max(0, shift_velocity)

        elif shift_distance > MAX_SHIFT:
            state.shift_distance = MAX_SHIFT
            state.shift_velocity = min(0, shift_velocity)

        constrained_y = state.to_array()
        for i in range(len(y)):
            y[i] = constrained_y[i]

        # Get system breakdown (this calculates everything in correct order)
        system_breakdown = self.system_model.get_breakdown(state)

        # Extract accelerations
        secondary_pulley_angular_accel_from_torques = system_breakdown.car.secondary_pulley_angular_acceleration
        primary_pulley_angular_accel = system_breakdown.engine.primary_pulley_angular_acceleration
        shift_acceleration = system_breakdown.cvt.acceleration

        # Prevent acceleration from pushing past boundaries (metal hitting metal)
        if shift_distance <= 0 and shift_acceleration < 0:
            shift_acceleration = 0
        elif shift_distance >= MAX_SHIFT and shift_acceleration > 0:
            shift_acceleration = 0

        return [
            state.shift_velocity,
            shift_acceleration,
            primary_pulley_angular_accel,
            secondary_pulley_angular_accel_from_torques,
        ]

    def _evaluate_full_shift_system(self, t: float, y: list[float]):
        """Evaluate system dynamics (phase 2: at full shift).
        
        At full shift, shift_distance and shift_velocity are held constant.
        Only the pulley angular velocities continue to evolve.
        """
        state = SystemState.from_array(y)
        self._print_progress(t)
        # Force the shifting variables to remain constant at full shift.
        state.shift_distance = MAX_SHIFT
        state.shift_velocity = 0

        # CRITICAL: Update the actual y array that scipy saves
        constrained_y = state.to_array()
        for i in range(len(y)):
            y[i] = constrained_y[i]

        # Get system breakdown for full shift case
        system_breakdown = self.system_model.get_breakdown(state)

        secondary_pulley_angular_accel_from_torques = system_breakdown.car.secondary_pulley_angular_acceleration
        primary_pulley_angular_accel = system_breakdown.engine.primary_pulley_angular_acceleration

        return [
            0,                              # shift_distance held constant
            0,                              # shift_velocity held constant
            primary_pulley_angular_accel,   # primary pulley continues to evolve
            secondary_pulley_angular_accel_from_torques, # secondary pulley continues to evolve
        ]
