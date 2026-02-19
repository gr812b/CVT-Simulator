import sys
import math
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
    ENGINE_INERTIA,
    DRIVELINE_INERTIA,
)
from cvt_simulator.utils.conversions import rpm_to_rad_s
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.constants.engine_specs import safe_torque_curve
from cvt_simulator.utils.numba_kernels import (
    slip_relative_speed_kernel,
    slip_coupling_torque_kernel,
    torque_demand_kernel,
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
        car_velocity=rpm_to_rad_s(0.1)
        / (GEARBOX_RATIO * tm.current_cvt_ratio(0))
        * WHEEL_RADIUS,
        car_position=0.0,
        shift_velocity=0.0,
        shift_distance=0.0,
        engine_angular_velocity=rpm_to_rad_s(1800),
        engine_angular_position=0.0,
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

        # Cached model references for faster ODE RHS evaluation
        self._slip_model = system_model.slip_model
        self._cvt_shift_model = system_model.cvt_shift_model
        self._primary_pulley = self._slip_model.primary_pulley
        self._secondary_pulley = self._slip_model.secondary_pulley
        self._engine_model = self._slip_model.engine_model
        self._load_model = self._slip_model.load_model

        self._wheel_to_sec_ratio = GEARBOX_RATIO / WHEEL_RADIUS
        self._wheel_inertia = DRIVELINE_INERTIA + self._slip_model.car_mass * (
            WHEEL_RADIUS**2
        )
        self._cvt_moving_mass = self._cvt_shift_model.cvt_moving_mass
        self._slip_speed_smoothing = self._slip_model.slip_speed_smoothing

        self._incline_force = (
            self._load_model.car_mass
            * self._load_model.g
            * math.sin(self._load_model.incline_angle)
        )
        self._drag_force_coeff = (
            0.5
            * self._load_model.air_density
            * self._load_model.frontal_area
            * self._load_model.drag_coefficient
        )

        # Precompute CVT ratio and derivative lookup tables to avoid per-step root finding
        self._ratio_lut_shift = np.linspace(0.0, MAX_SHIFT, 1024)
        self._ratio_lut = np.array(
            [tm.current_cvt_ratio(d) for d in self._ratio_lut_shift], dtype=float
        )
        self._ratio_rate_per_vel_lut = np.array(
            [
                tm.current_cvt_ratio_rate_of_change(d, 1.0)
                for d in self._ratio_lut_shift
            ],
            dtype=float,
        )

        # Precompute torque lookup table to avoid repeated scipy interp1d overhead
        self._torque_lut_omega = np.linspace(0.0, rpm_to_rad_s(6000), 2048)
        self._torque_lut = np.asarray(safe_torque_curve(self._torque_lut_omega), dtype=float)

        # Reused mutable state object to minimize allocation churn
        self._scratch_state = SystemState()

        # Secondary ramp can have a slightly smaller usable max than MAX_SHIFT.
        # Clamp internal pulley calculations to avoid inverse-height edge errors.
        secondary_last_segment = self._secondary_pulley.ramp.segments[-1]
        secondary_max_shift = abs(
            self._secondary_pulley.ramp.height(secondary_last_segment.x_end)
        )
        self._pulley_calc_shift_max = min(MAX_SHIFT, secondary_max_shift)


    
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
            self._get_shift_steady_event(),
            self._get_car_velocity_constraint_event(),
            self._get_shift_constraint_event(),
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
                    self._get_back_shift_event(),
                    self._get_car_velocity_constraint_event(),
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
                        self._get_shift_steady_event(),
                        self._get_car_velocity_constraint_event(),
                        self._get_shift_constraint_event(),
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

    def _get_shift_constraint_event(self):
        def shift_constraint_event(t, y):
            shift_velocity = y[2]
            shift_distance = y[3]

            if shift_distance < 0:
                y[3] = 0.0
                y[2] = max(0.0, shift_velocity)
            elif shift_distance > MAX_SHIFT:
                y[3] = MAX_SHIFT
                y[2] = min(0.0, shift_velocity)

            return 1.0

        return shift_constraint_event

    def _get_car_velocity_constraint_event(self):
        def car_velocity_event(t, y):
            return y[0]

        car_velocity_event.terminal = True
        car_velocity_event.direction = -1
        return car_velocity_event

    def _get_shift_steady_event(self):
        def shift_steady_event(t, y):
            tol = 1e-5
            if y[3] < MAX_SHIFT - tol:
                return -tol

            shift_velocity = y[2]
            shift_distance = y[3]
            if shift_distance < 0:
                y[3] = 0.0
                y[2] = max(0.0, shift_velocity)
            elif shift_distance > MAX_SHIFT:
                y[3] = MAX_SHIFT
                y[2] = min(0.0, shift_velocity)

            _, _, shift_acceleration = self._compute_dynamics(y, full_shift=False)
            return shift_acceleration

        shift_steady_event.terminal = True
        shift_steady_event.direction = 1
        return shift_steady_event

    def _get_back_shift_event(self):
        def back_shift_event(t, y):
            if y[3] < MAX_SHIFT - 1e-5:
                return 1.0

            _, _, shift_acceleration = self._compute_dynamics(y, full_shift=False)
            return shift_acceleration + 5.0

        back_shift_event.terminal = True
        back_shift_event.direction = -1
        return back_shift_event

    def _clamp_shift_state(self, y: list[float], full_shift: bool) -> tuple[float, float]:
        if full_shift:
            y[3] = MAX_SHIFT
            y[2] = 0.0
            return MAX_SHIFT, 0.0

        shift_velocity = y[2]
        shift_distance = y[3]

        if shift_distance <= 0:
            y[3] = 0.0
            y[2] = max(0.0, shift_velocity)
        elif shift_distance > MAX_SHIFT:
            y[3] = MAX_SHIFT
            y[2] = min(0.0, shift_velocity)

        return y[3], y[2]

    def _lookup_cvt_ratio(self, shift_distance: float) -> float:
        return float(np.interp(shift_distance, self._ratio_lut_shift, self._ratio_lut))

    def _lookup_cvt_ratio_rate(self, shift_distance: float, shift_velocity: float) -> float:
        rate_per_velocity = float(
            np.interp(shift_distance, self._ratio_lut_shift, self._ratio_rate_per_vel_lut)
        )
        return rate_per_velocity * shift_velocity

    def _lookup_engine_torque(self, engine_angular_velocity: float) -> float:
        if engine_angular_velocity <= self._torque_lut_omega[0]:
            return float(self._torque_lut[0])
        if engine_angular_velocity >= self._torque_lut_omega[-1]:
            return float(self._torque_lut[-1])
        return float(
            np.interp(engine_angular_velocity, self._torque_lut_omega, self._torque_lut)
        )

    def _load_force(self, car_velocity: float) -> float:
        return self._incline_force + self._drag_force_coeff * car_velocity * abs(car_velocity)

    def _compute_dynamics(
        self, y: list[float], full_shift: bool
    ) -> tuple[float, float, float]:
        car_velocity = y[0]
        car_position = y[1]
        shift_distance, shift_velocity = self._clamp_shift_state(y, full_shift)
        engine_angular_velocity = y[4]
        engine_angular_position = y[5]

        shift_distance_for_calc = min(shift_distance, self._pulley_calc_shift_max)

        cvt_ratio = self._lookup_cvt_ratio(shift_distance_for_calc)
        cvt_ratio_derivative = self._lookup_cvt_ratio_rate(
            shift_distance_for_calc,
            shift_velocity,
        )

        engine_torque = self._lookup_engine_torque(engine_angular_velocity)
        load_torque = self._load_force(car_velocity) * WHEEL_RADIUS

        wheel_angular_velocity = car_velocity / WHEEL_RADIUS
        engine_to_wheel_ratio = cvt_ratio * GEARBOX_RATIO
        engine_to_wheel_ratio_rate_of_change = cvt_ratio_derivative * GEARBOX_RATIO

        torque_demand = torque_demand_kernel(
            engine_torque,
            load_torque,
            self._wheel_inertia,
            wheel_angular_velocity,
            engine_to_wheel_ratio,
            engine_to_wheel_ratio_rate_of_change,
            ENGINE_INERTIA,
        )

        state = self._scratch_state
        state.car_velocity = car_velocity
        state.car_position = car_position
        state.shift_velocity = shift_velocity
        state.shift_distance = shift_distance_for_calc
        state.engine_angular_velocity = engine_angular_velocity
        state.engine_angular_position = engine_angular_position

        t_max_prim = self._primary_pulley.calculate_max_torque(state)
        t_max_sec = self._secondary_pulley.calculate_max_torque(state)
        t_max_capacity = min(max(0.0, t_max_prim), max(0.0, t_max_sec))

        relative_speed = slip_relative_speed_kernel(
            engine_angular_velocity,
            car_velocity * self._wheel_to_sec_ratio,
            cvt_ratio,
        )
        coupling_torque, _ = slip_coupling_torque_kernel(
            relative_speed,
            torque_demand,
            t_max_capacity,
            self._slip_speed_smoothing,
        )

        car_acceleration = (
            WHEEL_RADIUS * (coupling_torque * engine_to_wheel_ratio - load_torque)
        ) / self._wheel_inertia

        engine_angular_accel = (engine_torque - coupling_torque) / ENGINE_INERTIA

        if full_shift:
            return car_acceleration, engine_angular_accel, 0.0

        primary_clamp, _ = self._primary_pulley.calculate_clamping_force(state)
        _, _, primary_radial = self._primary_pulley.calculate_radial_force(
            state, primary_clamp
        )
        secondary_clamp, _ = self._secondary_pulley.calculate_clamping_force(
            state,
            torque=coupling_torque * cvt_ratio,
        )
        _, _, secondary_radial = self._secondary_pulley.calculate_radial_force(
            state,
            secondary_clamp,
        )

        net_radial = primary_radial - secondary_radial
        friction = self._cvt_shift_model._frictional_force(net_radial, shift_velocity)
        shift_acceleration = (net_radial + friction) / self._cvt_moving_mass

        if shift_distance <= 0 and shift_acceleration < 0:
            shift_acceleration = 0.0
        elif shift_distance >= MAX_SHIFT and shift_acceleration > 0:
            shift_acceleration = 0.0

        return car_acceleration, engine_angular_accel, shift_acceleration

    def _evaluate_cvt_system(self, t: float, y: list[float]):
        """Evaluate system dynamics (phase 1: not at full shift)."""
        self._print_progress(t)
        car_acceleration, engine_angular_accel, shift_acceleration = self._compute_dynamics(
            y,
            full_shift=False,
        )

        return [
            car_acceleration,
            y[0],
            shift_acceleration,
            y[2],
            engine_angular_accel,
            y[4],
        ]

    def _evaluate_full_shift_system(self, t: float, y: list[float]):
        """Evaluate system dynamics (phase 2: at full shift)."""
        self._print_progress(t)
        car_acceleration, engine_angular_accel, _ = self._compute_dynamics(
            y,
            full_shift=True,
        )

        return [
            car_acceleration,
            y[0],
            0,
            0,
            engine_angular_accel,
            y[4],
        ]
