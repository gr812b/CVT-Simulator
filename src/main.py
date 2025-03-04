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
from utils.ramp_representation import LinearSegment, PiecewiseRamp, CircularSegment

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
    incline_angle=deg_to_rad(0),
)
car_simulator = CarSimulator(car_mass=CAR_MASS + args.driver_weight)
primary_simulator = PrimaryPulley(
    spring_coeff_comp=args.primary_spring_rate,
    initial_compression=args.primary_spring_pretension,
    flyweight_mass=args.flyweight_mass,
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

    # ---------------------------
    # CAR + ENGINE DYNAMICS BELOW
    # ---------------------------

    # Some ratios
    cvt_ratio = tm.current_cvt_ratio(
        state.shift_distance,
        SHEAVE_ANGLE,
        BELT_WIDTH,
        INNER_PRIMARY_PULLEY_RADIUS,
        INNER_SECONDARY_PULLEY_RADIUS,
    )
    wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
    engine_velocity = state.car_velocity * wheel_to_engine_ratio

    # Vehicle acceleration
    engine_power = engine_simulator.get_power(engine_velocity)
    car_acceleration = load_simulator.calculate_acceleration(state.car_velocity, engine_power)

    # Override engine velocity
    

    # ------------------
    # PULLEY STUFF BELOW
    # ------------------

    # Get torque feedback
    engine_torque = engine_simulator.get_torque(engine_velocity)

    primary_force = primary_simulator.calculate_net_force(
        state.shift_distance,
        engine_velocity,
    )
    secondary_force = secondary_simulator.calculate_net_force(
        engine_torque * cvt_ratio,
        state.shift_distance,
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
        engine_velocity,
        state.shift_distance,
        primary_wrap_angle,
        primary_force,
    )
    secondary_belt_radial = secondary_belt.calculate_radial_force(
        engine_velocity,
        state.shift_distance,
        secondary_wrap_angle,
        secondary_force,
    )

    cvt_moving_mass = 1000000  # TODO: Use constants
    shift_acceleration = (
        primary_belt_radial - secondary_belt_radial
    ) / cvt_moving_mass  # TODO: See if this belt acceleration is actually equal to shift accel

    return [
        0, # This forces the engine to match the car's acceleration i.e. no slip
        engine_velocity,
        car_acceleration,
        state.car_velocity,
        shift_acceleration,
        state.shift_velocity,
    ]


time_span = (0, 30)
time_eval = np.linspace(*time_span, 10000)
initial_state = SystemState(
    engine_angular_velocity=rpm_to_rad_s(2400),
    engine_angular_position=0.0,
    car_velocity=rpm_to_rad_s(2400)/(GEARBOX_RATIO * 3.338941738205263) * WHEEL_RADIUS,
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
    rtol=1e-5,
    atol=1e-9,
)

result = SimulationResult(solution)

result.write_csv("simulation_output.csv")
result.plot("car_velocity")
# result.plot("car_position")
# result.plot("shift_distance")
# result.plot("shift_velocity")
# result.plot("engine_angular_velocity")

# Loop through the solution and recalculate the primary and secondary forces, then plot it
vehicle_accels = []
engine_angular_velocities = []
air_resistance = []
engine_powers = []
cvt_ratios = []
vehicle_speeds = []
engine_speeds = []
times = result.time

for state in result.states:
    # Vehicle acceleration
    cvt_ratio = tm.current_cvt_ratio(
        state.shift_distance,
        SHEAVE_ANGLE,
        BELT_WIDTH,
        INNER_PRIMARY_PULLEY_RADIUS,
        INNER_SECONDARY_PULLEY_RADIUS,
    )
    wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
    actual_engine_velocity = state.car_velocity * wheel_to_engine_ratio

    engine_power = engine_simulator.get_power(state.engine_angular_velocity)
    car_acceleration = load_simulator.calculate_acceleration(state.car_velocity, engine_power)
    air_resis = load_simulator.calculate_drag_force(state.car_velocity)/load_simulator.car_mass

    vehicle_accels.append(car_acceleration + air_resis)
    engine_angular_velocities.append(actual_engine_velocity)
    air_resistance.append(air_resis)
    engine_powers.append(engine_power)

    cvt_ratio = tm.current_cvt_ratio(
        state.shift_distance,
        SHEAVE_ANGLE,
        BELT_WIDTH,
        INNER_PRIMARY_PULLEY_RADIUS,
        INNER_SECONDARY_PULLEY_RADIUS,
    )
    cvt_ratios.append(cvt_ratio)
    vehicle_speeds.append(state.car_velocity)
    engine_speeds.append(actual_engine_velocity)
    

# Plot the vehicle speed, engine speed, and CVT ratio against time
fig, ax1 = plt.subplots()

ax1.set_xlabel("Time (s)")
ax1.set_ylabel("Vehicle Speed (m/s)", color="#DDDD40")
ax1.plot(times, vehicle_speeds, label="Vehicle Speed", color="#DDDD40", linewidth=4)
ax1.tick_params(axis="y", labelcolor="#DDDD40")

# Create a second y-axis for the engine speed
ax2 = ax1.twinx()
ax2.set_ylabel("Engine Speed (rad/s)", color="#000000")
ax2.plot(times, engine_speeds, label="Engine Speed", color="#000000", linewidth=1.5)
ax2.tick_params(axis="y", labelcolor="#000000")

# Create a third y-axis for the CVT ratio
ax3 = ax1.twinx()
ax3.spines["right"].set_position(("outward", 60))  # Offset the third axis
ax3.set_ylabel("CVT Ratio", color="tab:green")
ax3.plot(times, cvt_ratios, label="CVT Ratio", color="tab:green", linestyle='dashdot', linewidth=2)
ax3.tick_params(axis="y", labelcolor="tab:green")

fig.tight_layout()
plt.title("Vehicle Speed, Engine Speed, and CVT Ratio vs Time")
plt.grid()
plt.show()
    
