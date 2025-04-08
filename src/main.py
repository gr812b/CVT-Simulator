import sys
import numpy as np
from scipy.integrate import solve_ivp
from simulations.load_simulation import LoadSimulator
from utils.system_state import SystemState
from utils.simulation_result import SimulationResult
from simulations.engine_simulation import EngineSimulator
from simulations.primary_pulley import PrimaryPulley
from simulations.secondary_pulley import SecondaryPulley
from simulations.belt_simulator import BeltSimulator
from simulations.cvt_shift import CvtShift
from constants.engine_specs import torque_curve
from constants.car_specs import (
    ENGINE_INERTIA,
    GEARBOX_RATIO,
    WHEEL_RADIUS,
    MAX_SHIFT,
)
from utils.conversions import rpm_to_rad_s, deg_to_rad
from utils.argument_parser import get_arguments
from utils.theoretical_models import TheoreticalModels as tm
from utils.simulation_constraints import (
    car_velocity_constraint_event,
    get_shift_steady_event,
    shift_constraint_event,
)
from utils.frontend_output import FormattedSimulationResult


# Parse arguments
args = get_arguments()

# Initialize simulators
engine_simulator = EngineSimulator(torque_curve=torque_curve, inertia=ENGINE_INERTIA)
load_simulator = LoadSimulator(
    car_mass=args.vehicle_weight + args.driver_weight,
    incline_angle=deg_to_rad(args.angle_of_incline),
)
primary_simulator = PrimaryPulley(
    spring_coeff_comp=args.primary_spring_rate,
    initial_compression=args.primary_spring_pretension,
    flyweight_mass=args.flyweight_mass,
    ramp_type=args.primary_ramp_geometry,
)
secondary_simulator = SecondaryPulley(
    spring_coeff_tors=args.secondary_torsion_spring_rate,
    spring_coeff_comp=args.secondary_compression_spring_rate,
    initial_rotation=deg_to_rad(args.secondary_rotational_spring_pretension),
    initial_compression=args.secondary_linear_spring_pretension,
    ramp_type=args.secondary_helix_geometry,
)
primary_belt = BeltSimulator(primary=True)
secondary_belt = BeltSimulator(primary=False)
cvt_shift = CvtShift(
    engine_simulator,
    primary_simulator,
    secondary_simulator,
    primary_belt,
    secondary_belt,
)

total_sim_time = 15  # seconds


# Define the system of differential equations
def evaluate_cvt_system(t, y):
    state = SystemState.from_array(y)

    # Print progress
    progress_percent = (t / total_sim_time) * 100
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
    engine_power = engine_simulator.get_power(engine_velocity)
    car_acceleration = load_simulator.calculate_acceleration(
        state.car_velocity, engine_power
    )

    # ------------------
    # PULLEY STUFF BELOW
    # ------------------
    shift_acceleration = cvt_shift.calculate_shift_acceleration(state)

    return [
        car_acceleration,
        state.car_velocity,
        shift_acceleration,
        state.shift_velocity,
    ]


# PHASE 2: Simplified model (shift is locked at full shift)
def evaluate_full_shift_system(t, y):
    state = SystemState.from_array(y)
    # Force the shifting variables to remain constant at full shift.
    state.shift_distance = MAX_SHIFT
    state.shift_velocity = 0

    # Use constant CVT ratio for full shift
    cvt_ratio = tm.current_cvt_ratio(MAX_SHIFT)
    wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
    engine_velocity = state.car_velocity * wheel_to_engine_ratio

    engine_power = engine_simulator.get_power(engine_velocity)
    car_acceleration = load_simulator.calculate_acceleration(
        state.car_velocity, engine_power
    )

    return [
        car_acceleration,
        state.car_velocity,
        0,
        0,
    ]


time_eval_phase1 = np.linspace(0, total_sim_time, 10000)
initial_state = SystemState(
    car_velocity=rpm_to_rad_s(1800)
    / (GEARBOX_RATIO * tm.current_cvt_ratio(0))
    * WHEEL_RADIUS,
    car_position=0.0,
    shift_velocity=0.0,
    shift_distance=0.0,
)

# Solve the system over the desired time span
solution_phase1 = solve_ivp(
    evaluate_cvt_system,
    (0, total_sim_time),
    initial_state.to_array(),
    t_eval=time_eval_phase1,
    events=[
        get_shift_steady_event(cvt_shift),
        car_velocity_constraint_event,
        shift_constraint_event,
    ],
)

if solution_phase1.t_events[0].size > 0:
    # The full shift steady event was triggered.
    event_time = solution_phase1.t_events[0][0]
    event_state = solution_phase1.y_events[0][0]

    # Define a new t_eval for phase 2 (you can adjust the number of points as needed)
    num_phase2_points = 1000
    time_eval_phase2 = np.linspace(event_time, total_sim_time, num_phase2_points)

    # -----------------------------------------------------------
    # PHASE 2: Run simulation with shifting dynamics turned off
    # -----------------------------------------------------------
    solution_phase2 = solve_ivp(
        evaluate_full_shift_system,
        (event_time, total_sim_time),
        event_state,
        t_eval=time_eval_phase2,
        events=[car_velocity_constraint_event],
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


class CombinedSolution:
    def __init__(self, t, y):
        self.t = t
        self.y = y


combined_solution = CombinedSolution(combined_t, combined_y)

result = SimulationResult(combined_solution)
result.write_csv("simulation_output.csv")
FormattedSimulationResult.from_csv().write_formatted_csv()
