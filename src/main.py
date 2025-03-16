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
from utils.simulation_constraints import constraints
import sys

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
)
secondary_simulator = SecondaryPulley(
    spring_coeff_tors=args.secondary_torsion_spring_rate,
    spring_coeff_comp=args.secondary_compression_spring_rate,
    initial_rotation=deg_to_rad(args.secondary_spring_pretension),
    initial_compression=0.1,  # TODO: Use constants
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

    if progress_percent % 0.1 < 0.01:
        sys.stdout.write(f"\rProgress: {progress_percent:.1f}%")
        sys.stdout.flush()
        pass

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


time_span = (0, total_sim_time)
time_eval = np.linspace(*time_span, 10000)
initial_state = SystemState(
    car_velocity=rpm_to_rad_s(1800)
    / (GEARBOX_RATIO * tm.current_cvt_ratio(0))
    * WHEEL_RADIUS,
    car_position=0.0,
    shift_velocity=0.0,
    shift_distance=0.0,
)

# Solve the system over the desired time span
solution = solve_ivp(
    evaluate_cvt_system,
    time_span,
    initial_state.to_array(),
    events=constraints,
    t_eval=time_eval,
)

result = SimulationResult(solution)
result.write_result_csv("simulation_output.csv")
result.write_frontend_csv("frontend_data.csv")
