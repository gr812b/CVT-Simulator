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
from simulations.belt_simulator import BeltSimulator
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
    BELT_WIDTH,
    SHEAVE_ANGLE,
    INNER_PRIMARY_PULLEY_RADIUS,
    INNER_SECONDARY_PULLEY_RADIUS,
    CENTER_TO_CENTER,
)
from utils.conversions import rpm_to_rad_s, deg_to_rad
from utils.argument_parser import get_arguments
from utils.theoretical_models import TheoreticalModels as tm
from utils.simulation_constraints import constraints

# Parse arguments
args = get_arguments()

# Pass arguments and constants into the simulators
engine_simulator = EngineSimulator(torque_curve=torque_curve, inertia=ENGINE_INERTIA)
load_simulator = LoadSimulator(
    frontal_area=FRONTAL_AREA,
    drag_coefficient=DRAG_COEFFICIENT,
    car_mass=CAR_MASS + args.driver_weight,
    wheel_radius=WHEEL_RADIUS,
    gearbox_ratio=GEARBOX_RATIO,
    incline_angle=deg_to_rad(args.angle_of_incline),
)
car_simulator = CarSimulator(car_mass=CAR_MASS + args.driver_weight)
primary_simulator = PrimaryPulley(
    spring_coeff_comp=args.primary_spring_rate,
    initial_compression=args.primary_spring_pretension,
    flyweight_mass=args.primary_weight,
    initial_flyweight_radius=INITIAL_FLYWEIGHT_RADIUS,
)
secondary_simulator = SecondaryPulley(
    spring_coeff_tors=args.secondary_torsion_spring_rate,
    spring_coeff_comp=args.secondary_compression_spring_rate,
    initial_rotation=deg_to_rad(args.secondary_spring_pretension),
    initial_compression=0.1,  # TODO: Use constants
    helix_radius=HELIX_RADIUS,
)
primary_belt = BeltSimulator(
    μ_static=1.2,  # TODO: Use constants
    μ_kinetic=0.9,  # TODO: Use constants
    primary=True,
)
secondary_belt = BeltSimulator(
    μ_static=1.2,  # TODO: Use constants
    μ_kinetic=0.9,  # TODO: Use constants
    primary=False,
)


# Define the system of differential equations
def angular_velocity_and_position_derivative(t, y):
    state = SystemState.from_array(y)

    # Get sources of torque
    gearbox_load = load_simulator.calculate_gearbox_load(state.car_velocity)
    engine_torque = engine_simulator.get_torque(state.engine_angular_velocity)

    # Get pulley forces
    primary_force = primary_simulator.calculate_net_force(
        state.shift_distance,
        state.engine_angular_velocity,
    )
    secondary_force = secondary_simulator.calculate_net_force(
        engine_torque,
        state.shift_distance,
        0,  # TODO: Add rotation
    )

    # Convert direct clamping to radial forces
    primary_wrap_angle = tm.primary_wrap_angle(
        state.shift_distance,
        CENTER_TO_CENTER,
    )
    secondary_wrap_angle = tm.secondary_wrap_angle(
        state.shift_distance,
        CENTER_TO_CENTER,
    )
    primary_belt_radial = primary_belt.calculate_radial_force(
        state.engine_angular_velocity,
        state.shift_distance,
        primary_wrap_angle,
        primary_force,
    )
    secondary_belt_radial = secondary_belt.calculate_radial_force(
        state.engine_angular_velocity,
        state.shift_distance,
        secondary_wrap_angle,
        secondary_force,
    )

    cvt_moving_mass = 100000  # TODO: Use constants
    shift_acceleration = (
        primary_belt_radial - secondary_belt_radial
    ) / cvt_moving_mass  # TODO: See if this belt acceleration is actually equal to shift accel

    cvt_ratio = tm.current_cvt_ratio(
        state.shift_distance,
        SHEAVE_ANGLE,
        BELT_WIDTH,
        INNER_PRIMARY_PULLEY_RADIUS,
        INNER_SECONDARY_PULLEY_RADIUS,
    )

    # Engines angular acceleration due to engine torque
    # TODO: Update to be torque seen through the CVT
    engine_angular_acceleration = engine_simulator.calculate_angular_acceleration(
        state.engine_angular_velocity,
        gearbox_load / cvt_ratio,
    )

    # Net force on the car
    net_torque = (engine_torque * cvt_ratio) - gearbox_load
    force_at_wheel = net_torque * GEARBOX_RATIO / WHEEL_RADIUS

    # Vehicle acceleration
    car_acceleration = car_simulator.calculate_acceleration(force_at_wheel)

    # TODO: Next steps

    # Also consider the amount of torque that the belt can transfer due to friction, which limits torque at wheels, bogging down of engine, etc.

    # Maximum car velocity at the current engine speed (Wheels can't spin faster than the engine + gearbox)
    max_car_velocity = state.engine_angular_velocity / GEARBOX_RATIO * WHEEL_RADIUS

    if abs(state.car_velocity) > max_car_velocity:
        car_acceleration = 0

    # TODO: Remove temporary solution to act as limiter for engine speed
    if abs(state.engine_angular_velocity) > 400:
        engine_angular_acceleration = 0

    # if abs(state.shift_distance) > BELT_WIDTH:
    #     shift_acceleration = 0

    return [
        engine_angular_acceleration,
        state.engine_angular_velocity,
        car_acceleration,
        state.car_velocity,
        shift_acceleration,
        state.shift_velocity,
    ]


time_span = (0, 15)
time_eval = np.linspace(*time_span, 10000)
initial_state = SystemState(
    engine_angular_velocity=rpm_to_rad_s(2400),
    engine_angular_position=0.0,
    car_velocity=0.0,
    car_position=0.0,
    shift_velocity=0.0,
    shift_distance=0.0,
)

# Solve the system over the desired time span
solution = solve_ivp(
    angular_velocity_and_position_derivative,
    time_span,
    initial_state.to_array(),
    t_eval=time_eval,
    events=constraints,
    rtol=1e-6,
    atol=1e-9,
)

result = SimulationResult(solution)

result.write_csv("simulation_output.csv")
# result.plot("car_velocity")
result.plot("shift_distance")
# result.plot("shift_velocity")
# result.plot("engine_angular_velocity")

# Loop through the solution and recalculate the primary and secondary forces, then plot it
primary_forces = []
secondary_forces = []
prim_radial = []
sec_radial = []

for state in result.states:
    primary_force = primary_simulator.calculate_net_force(
        state.shift_distance,
        state.engine_angular_velocity,
    )
    secondary_force = secondary_simulator.calculate_net_force(
        engine_simulator.get_torque(state.engine_angular_velocity),
        state.shift_distance,
        0,
    )
    primary_forces.append(primary_force)
    secondary_forces.append(secondary_force)
    primary_wrap_angle = tm.primary_wrap_angle(
        state.shift_distance,
        CENTER_TO_CENTER,
    )
    secondary_wrap_angle = tm.secondary_wrap_angle(
        state.shift_distance,
        CENTER_TO_CENTER,
    )
    prim_radial.append(
        primary_belt.calculate_radial_force(
            state.engine_angular_velocity,
            state.shift_distance,
            primary_wrap_angle,
            primary_force,
        )
    )
    sec_radial.append(
        secondary_belt.calculate_radial_force(
            state.engine_angular_velocity,
            state.shift_distance,
            secondary_wrap_angle,
            secondary_force,
        )
    )

plt.plot(result.time, primary_forces, label="Primary Force")
plt.plot(result.time, secondary_forces, label="Secondary Force")
plt.plot(result.time, prim_radial, label="Primary Radial")
plt.plot(result.time, sec_radial, label="Secondary Radial")
plt.xlabel("Time (s)")
plt.ylabel("Force (N)")
plt.title("Primary and Secondary Forces Over Time")
plt.legend()
plt.grid()
plt.show()
