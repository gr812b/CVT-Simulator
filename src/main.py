from matplotlib import pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp
from simulations.car_simulation import CarSimulator
from simulations.load_simulation import LoadSimulator
from utils.system_state import SystemState
from utils.simulation_result import SimulationResult
from simulations.engine_simulation import EngineSimulator
from simulations.primary_pulley import PrimaryPulley
from simulations.secondary_pulley import SecondaryPulley
from constants.engine_specs import torque_curve
from constants.car_specs import (
    ENGINE_INERTIA,
    GEARBOX_RATIO,
    FRONTAL_AREA,
    DRAG_COEFFICIENT,
    CAR_MASS,
    WHEEL_RADIUS,
    INITIAL_FLYWEIGHT_RADIUS,
    HELIX_RADIUS,
)
from utils.conversions import rpm_to_rad_s, deg_to_rad
from utils.argument_parser import get_arguments
from utils.theoretical_models import TheoreticalModels as tm

# Parse arguments
args = get_arguments()

# Pass arguments and constants into the simulators
engine_simulator = EngineSimulator(torque_curve=torque_curve, inertia=ENGINE_INERTIA)
load_simulator = LoadSimulator(
    frontal_area=FRONTAL_AREA,
    drag_coefficient=DRAG_COEFFICIENT,
    car_mass=CAR_MASS,
    wheel_radius=WHEEL_RADIUS,
    gearbox_ratio=GEARBOX_RATIO,
    incline_angle=deg_to_rad(args.angle_of_incline),
)
car_simulator = CarSimulator(car_mass=CAR_MASS)
primary_simulator = PrimaryPulley(
    spring_coeff_comp=500,  # TODO: Use args
    initial_compression=0.2,  # TODO: Use args
    flyweight_mass=0.05,  # TODO: Use args
    initial_flyweight_radius=INITIAL_FLYWEIGHT_RADIUS,
)
secondary_simulator = SecondaryPulley(
    spring_coeff_tors=5,  # TODO: Use args
    spring_coeff_comp=100,  # TODO: Use args
    initial_rotation=np.pi/12,  # TODO: Use args
    initial_compression=0.1,  # TODO: Use args
    helix_radius=HELIX_RADIUS,
)

# Define the system of differential equations
def angular_velocity_and_position_derivative(t, y):
    state = SystemState.from_array(y)

    # Load from external forces
    gearbox_load = load_simulator.calculate_gearbox_load(state.car_velocity)

    engine_torque = engine_simulator.get_torque(state.engine_angular_velocity)

    primary_force = primary_simulator.calculate_net_force(
        state.shift_distance,
        state.engine_angular_velocity,
    )
    secondary_force = secondary_simulator.calculate_net_force(
        engine_torque,
        state.shift_distance,
        0,
    )

    # TODO: Remove
    cvt_ratio = tm.current_cvt_ratio(
        state.shift_distance,
        30,  # TODO: Use args
        0.05,  # TODO: Use args
        0.1,  # TODO: Use args
        0.2,  # TODO: Use args
    )

    # print(f"CVT ratio: {cvt_ratio}")

    cvt_moving_mass = 1000  # TODO: Use constants
    shift_acceleration = (primary_force - secondary_force) / cvt_moving_mass

    # Engines angular acceleration due to engine torque
    # TODO: Update to be torque seen through the CVT
    engine_angular_acceleration = engine_simulator.calculate_angular_acceleration(
        state.engine_angular_velocity,
        gearbox_load,
    )

    # Net force on the car
    net_torque = engine_torque / cvt_ratio - gearbox_load
    force_at_wheel = net_torque * GEARBOX_RATIO / WHEEL_RADIUS

    # Vehicle acceleration
    car_acceleration = car_simulator.calculate_acceleration(force_at_wheel)

    # print(
    #     f"Primary force: {primary_force}, Secondary force: {secondary_force}, engine torque: {engine_torque}"
    # )
    # TODO: Next steps
    # Difference in clamping forces causes shifting up to the CVTs limit.
    # Needs to accelerate both secondary and primary moving components + ?belt?
    # Include updated CVT ratio in force at wheel calcs

    # Also consider the actual difference in forces based on how much clamping force is being transferred through it
    # Also consider the amount of torque that the belt can transfer due to friction, which limits torque at wheels, bogging down of engine, etc.

    # Maximum car velocity at the current engine speed (Wheels can't spin faster than the engine + gearbox)
    max_car_velocity = state.engine_angular_velocity / GEARBOX_RATIO * WHEEL_RADIUS

    if abs(state.car_velocity) > max_car_velocity:
        car_acceleration = 0

    # TODO: Remove temporary solution to act as limiter for engine speed
    if abs(state.engine_angular_velocity) > 400:
        engine_angular_acceleration = 0

    return [engine_angular_acceleration, car_acceleration, state.car_velocity, shift_acceleration, state.shift_velocity]


time_span = (0, 15)
time_eval = np.linspace(*time_span, 10000)
initial_state = SystemState(
    engine_angular_velocity=rpm_to_rad_s(2400), 
    car_velocity=0.0, 
    car_position=0.0,
    shift_velocity=0.0,
    shift_distance=0.0,
)

# Constraints
def shift_constraint_event(t, y):
    shift_velocity = y[3]
    shift_distance = y[4]

    if shift_distance < 0:
        y[3] = max(0, shift_velocity) 
        y[4] = 0
        
    elif shift_distance > 0.075:
        y[3] = min(0, shift_velocity)
        y[4] = 0.075

    return 1

# Solve the system over the desired time span
solution = solve_ivp(
    angular_velocity_and_position_derivative,
    time_span,
    initial_state.to_array(),
    t_eval=time_eval,
    events=shift_constraint_event,
    rtol=1e-6,
    atol=1e-9,
)

result = SimulationResult(solution)

result.write_csv("simulation_output.csv")
result.plot("car_velocity")
result.plot("shift_distance")
result.plot("shift_velocity")
result.plot("engine_angular_velocity")

# Loop through the solution and recalculate the primary and secondary forces, then plot it
primary_forces = []
secondary_forces = []

for state in result.states:
    primary_forces.append(
        primary_simulator.calculate_net_force(
            0,
            state.engine_angular_velocity,
        )
    )
    secondary_forces.append(
        secondary_simulator.calculate_net_force(
            engine_simulator.get_torque(state.engine_angular_velocity),
            0,
            0,
        )
    )

plt.plot(result.time, primary_forces, label="Primary Force")
plt.plot(result.time, secondary_forces, label="Secondary Force")
plt.xlabel("Time (s)")
plt.ylabel("Force (N)")
plt.title("Primary and Secondary Forces Over Time")
plt.legend()
plt.grid()
plt.show()
