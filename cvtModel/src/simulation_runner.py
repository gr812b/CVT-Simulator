
import sys
import numpy as np
from scipy.integrate import solve_ivp
from models.external_load_model import LoadModel
from utils.system_state import SystemState
from utils.simulation_result import SimulationResult
from models.engine_model import EngineModel
from models.cvt_shift_model import CvtShiftModel
from constants.car_specs import (
    GEARBOX_RATIO,
    WHEEL_RADIUS,
    MAX_SHIFT,
)
from utils.conversions import rpm_to_rad_s
from utils.theoretical_models import TheoreticalModels as tm
from utils.simulation_constraints import (
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
    )

    def __init__(
        self,
        engine_model: EngineModel,
        load_model: LoadModel,
        cvt_shift_model: CvtShiftModel,
    ):
        self.engine_model = engine_model
        self.load_model = load_model
        self.cvt_shift_model = cvt_shift_model

    def run_simulation(self) -> SimulationResult:
        """Run the simulation and return results."""
        cvt_system_ode = self._get_ode_function()
        time_eval_phase1 = np.linspace(0, self.TOTAL_SIM_TIME, 10000)
        events = [
            get_shift_steady_event(self.cvt_shift_model),
            car_velocity_constraint_event,
            shift_constraint_event,
        ]

        solution_phase1 = self._solve(
            cvt_system_ode,
            0,
            self.INITIAL_STATE,
            time_eval_phase1,
            events,
        )

        # This will be true if we hit full shift
        if solution_phase1.t_events[0].size > 0:
            event_time = solution_phase1.t_events[0][0]
            event_state = solution_phase1.y_events[0][0]

            # Define a new t_eval for phase 2 (you can adjust the number of points as needed)
            time_eval_phase2 = np.linspace(event_time, self.TOTAL_SIM_TIME, 1000)

            cvt_system_full_shift_ode = self._get_full_shift_ode_function()

            solution_phase2 = self._solve(
                cvt_system_full_shift_ode,
                event_time,
                event_state,
                time_eval_phase2,
                [car_velocity_constraint_event],
            )

            phase1_indices = solution_phase1.t <= event_time
            combined_t = np.concatenate(
                [solution_phase1.t[phase1_indices], solution_phase2.t[1:]]
            )
            combined_y = np.hstack(
                [solution_phase1.y[:, phase1_indices], solution_phase2.y[:, 1:]]
            )
        else:
            # Otherwise, use the phase 1 solution entirely.
            combined_t = solution_phase1.t
            combined_y = solution_phase1.y

        combined_solution = CombinedSolution(combined_t, combined_y)
        return SimulationResult(combined_solution)

    # Get the function without self for scipy
    def _get_ode_function(self):
        def ode_func(t, y):
            return self._evaluate_cvt_system(t, y)
        return ode_func
    
    def _get_full_shift_ode_function(self):
        def ode_func(t, y):
            return self._evaluate_full_shift_system(t, y)
        return ode_func
    
    def _solve(
            self, 
            ode_func,
            start_time,
            initial_state,
            time_eval,
            events,
        ):
        return solve_ivp(
            ode_func,
            (start_time, self.TOTAL_SIM_TIME),
            initial_state,
            time_eval,
            events=[
                events
            ],
            atol=1e-6,
            rtol=1e-4,
        )

    def _evaluate_cvt_system(self, t, y):
        """Evaluate system dynamics (phase 1: not at full shift)."""
        state = SystemState.from_array(y)

        # TODO: Update lethis
        # Print progress
        progress_percent = (t / self.TOTAL_SIM_TIME) * 100
        # Print every 0.1% progress
        if progress_percent % 0.1 < 0.01:
            sys.stdout.write(
                f"\rProgress: {progress_percent:.1f}% [{'=' * int(progress_percent // 2)}{' ' * (50 - int(progress_percent // 2))}]"
            )
            sys.stdout.flush()

        # TODO: Remove this (should be handled by constraints)
        shift_velocity = state.shift_velocity
        shift_distance = state.shift_distance
        if shift_distance < 0:
            state.shift_distance = 0
            state.shift_velocity = max(0, shift_velocity)

        elif shift_distance > MAX_SHIFT:
            state.shift_distance = MAX_SHIFT
            state.shift_velocity = min(0, shift_velocity)

        # ---------------------------
        # CAR + ENGINE DYNAMICS BELOW
        # ---------------------------

        # Some ratios
        # print(tm.outer_prim_radius(state.shift_distance), state.shift_distance)
        cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
        wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
        engine_velocity = state.car_velocity * wheel_to_engine_ratio

        # Vehicle acceleration
        engine_power = self.engine_model.get_power(engine_velocity)
        car_acceleration = self.load_model.calculate_acceleration(
            state.car_velocity, engine_power
        )

        # ------------------
        # PULLEY STUFF BELOW
        # ------------------
        shift_acceleration = self.cvt_shift_model.calculate_shift_acceleration(state)

        return [
            car_acceleration,
            state.car_velocity,
            shift_acceleration,
            state.shift_velocity,
        ]

    def _evaluate_full_shift_system(self, t, y):
        """Evaluate system dynamics (phase 2: at full shift)."""
        state = SystemState.from_array(y)
        # Force the shifting variables to remain constant at full shift.
        state.shift_distance = MAX_SHIFT
        state.shift_velocity = 0

        # Use constant CVT ratio for full shift
        cvt_ratio = tm.current_cvt_ratio(MAX_SHIFT)
        wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
        engine_velocity = state.car_velocity * wheel_to_engine_ratio

        engine_power = self.engine_model.get_power(engine_velocity)
        car_acceleration = self.load_model.calculate_acceleration(
            state.car_velocity, engine_power
        )

        return [
            car_acceleration,
            state.car_velocity,
            0,
            0,
        ]
