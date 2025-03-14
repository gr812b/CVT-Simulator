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
    MAX_SHIFT,
)
from utils.conversions import rpm_to_rad_s, deg_to_rad
from utils.argument_parser import get_arguments
from utils.theoretical_models import TheoreticalModels as tm
from utils.simulation_constraints import constraints
import sys
import os
import csv


# Parse arguments
args = get_arguments()

# Pass arguments and constants into the simulators
engine_simulator = EngineSimulator(torque_curve=torque_curve, inertia=ENGINE_INERTIA)
load_simulator = LoadSimulator(
    frontal_area=FRONTAL_AREA,
    drag_coefficient=DRAG_COEFFICIENT,
    car_mass=args.vehicle_weight + args.driver_weight,
    wheel_radius=WHEEL_RADIUS,
    gearbox_ratio=GEARBOX_RATIO,
    incline_angle=deg_to_rad(args.angle_of_incline),
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


def get_pulley_forces(state: SystemState) -> dict:
    # Compute CVT ratio and engine velocity
    cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
    wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
    engine_velocity = state.car_velocity * wheel_to_engine_ratio

    # Engine torque for secondary force calculation
    engine_torque = engine_simulator.get_torque(engine_velocity)

    # Calculate forces using your existing simulators
    primary_force = primary_simulator.calculate_net_force(
        state.shift_distance, engine_velocity
    )
    secondary_force = secondary_simulator.calculate_net_force(
        engine_torque * cvt_ratio, state.shift_distance
    )

    # Calculate wrap angles and convert to radial forces
    primary_wrap_angle = tm.primary_wrap_angle(state.shift_distance)
    secondary_wrap_angle = tm.secondary_wrap_angle(state.shift_distance)
    primary_radial = primary_belt.calculate_radial_force(
        engine_velocity, state.shift_distance, primary_wrap_angle, primary_force
    )
    secondary_radial = secondary_belt.calculate_radial_force(
        engine_velocity, state.shift_distance, secondary_wrap_angle, secondary_force
    )

    return {
        "primary_force": primary_force,
        "secondary_force": secondary_force,
        "primary_radial": primary_radial,
        "secondary_radial": secondary_radial,
    }


total_sim_time = 15  # seconds

current_progress = 0  # global variable to track progress

# delete temp csv file if it exists
try:
    os.remove("progress_percent_temp.csv")
except FileNotFoundError:
    pass

# create temp csv file
with open("progress_percent_temp.csv", "w", newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["Percent"])
    writer.writerow([current_progress])

os.replace("progress_percent_temp.csv", "progress_percent.csv")


# Define the system of differential equations
def angular_velocity_and_position_derivative(t, y):
    global current_progress
    state = SystemState.from_array(y)

    progress_percent = t / total_sim_time

    # Print every 1% progress
    if progress_percent > current_progress + 0.01:
        current_progress = progress_percent
        sys.stdout.write(f"\rProgress: {progress_percent:.1f}%")
        sys.stdout.flush()

        # write progress to temp csv file
        with open("progress_percent_temp.csv", "w", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Percent"])
            writer.writerow([f"{current_progress:.2f}"])
        
        os.replace("progress_percent_temp.csv", "progress_percent.csv")
        pass

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
    pulleyForces = get_pulley_forces(state)

    cvt_moving_mass = 10  # TODO: Use constants
    # TODO: See if this belt acceleration is actually equal to shift accel
    friction = min(
        20, abs(pulleyForces["primary_radial"] - pulleyForces["secondary_radial"])
    )
    if state.shift_velocity > 0:
        forces = (
            pulleyForces["primary_radial"] - pulleyForces["secondary_radial"] - friction
        )
    else:
        forces = (
            pulleyForces["primary_radial"] - pulleyForces["secondary_radial"] + friction
        )
    shift_acceleration = forces / cvt_moving_mass

    return [
        0,
        engine_velocity,
        car_acceleration,
        state.car_velocity,
        shift_acceleration,
        state.shift_velocity,
    ]


time_span = (0, total_sim_time)
time_eval = np.linspace(*time_span, 10000)
initial_state = SystemState(
    engine_angular_velocity=rpm_to_rad_s(1800),
    engine_angular_position=0.0,
    car_velocity=rpm_to_rad_s(1800)
    / (GEARBOX_RATIO * tm.current_cvt_ratio(0))
    * WHEEL_RADIUS,
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
    # rtol=1e-5,
    # atol=1e-9,
)

result = SimulationResult(solution)

result.write_csv("simulation_output.csv")
result.plot("car_velocity")
# result.plot("car_position")
result.plot("shift_distance")
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
    cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
    wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
    actual_engine_velocity = state.car_velocity * wheel_to_engine_ratio

    engine_power = engine_simulator.get_power(state.engine_angular_velocity)
    car_acceleration = load_simulator.calculate_acceleration(
        state.car_velocity, engine_power
    )
    air_resis = (
        load_simulator.calculate_drag_force(state.car_velocity)
        / load_simulator.car_mass
    )

    vehicle_accels.append(car_acceleration + air_resis)
    engine_angular_velocities.append(actual_engine_velocity)
    air_resistance.append(air_resis)
    engine_powers.append(engine_power)

    cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
    cvt_ratios.append(cvt_ratio)
    vehicle_speeds.append(state.car_velocity)
    engine_speeds.append(actual_engine_velocity)


# Create subplots
fig, axs = plt.subplots(3, 2, figsize=(15, 15))

# Plot the vehicle speed, engine speed, and CVT ratio against time
axs[0, 0].set_xlabel("Time (s)")
axs[0, 0].set_ylabel("Vehicle Speed (m/s)", color="#DDDD40")
axs[0, 0].plot(
    times, vehicle_speeds, label="Vehicle Speed", color="#DDDD40", linewidth=4
)
axs[0, 0].tick_params(axis="y", labelcolor="#DDDD40")

ax2 = axs[0, 0].twinx()
ax2.set_ylabel("Engine Speed (rad/s)", color="#000000")
ax2.plot(times, engine_speeds, label="Engine Speed", color="#000000", linewidth=1.5)
ax2.tick_params(axis="y", labelcolor="#000000")

ax3 = axs[0, 0].twinx()
ax3.spines["right"].set_position(("outward", 60))  # Offset the third axis
ax3.set_ylabel("CVT Ratio", color="tab:green")
ax3.plot(
    times,
    cvt_ratios,
    label="CVT Ratio",
    color="tab:green",
    linestyle="dashdot",
    linewidth=2,
)
ax3.tick_params(axis="y", labelcolor="tab:green")

axs[0, 0].set_title("Vehicle Speed, Engine Speed, and CVT Ratio vs Time")
axs[0, 0].grid()

# Loop through the solution and recalculate the primary and secondary forces, then plot it
ramp = primary_simulator.ramp
angles = []

for state in result.states:
    shift_distance = state.shift_distance
    if shift_distance < 0:
        shift_distance = 0
    if shift_distance > MAX_SHIFT:
        shift_distance = MAX_SHIFT

    angles.append(np.sin(np.arctan(ramp.slope(shift_distance))))

observables = [get_pulley_forces(state) for state in result.states]

# Unpack the observables for plotting or further processing
primary_forces = [obs["primary_force"] for obs in observables]
secondary_forces = [obs["secondary_force"] for obs in observables]
prim_radial = [obs["primary_radial"] for obs in observables]
sec_radial = [obs["secondary_radial"] for obs in observables]
shift_distances = [state.shift_distance for state in result.states]
shift_velocities = [state.shift_velocity for state in result.states]
# Clear console
sys.stdout.write("\r" + " " * 40 + "\r")
sys.stdout.flush()

last_force = 0
for i in range(len(primary_forces)):
    state = result.states[i]
    if times[i] > 0.47 and times[i] < 0.485:
        cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
        wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
        engine_velocity = state.car_velocity * wheel_to_engine_ratio
        print(
            f"Time: {times[i]:.3f}s, Engine Velocity: {engine_velocity:.3f} rad/s, shift_distance: {state.shift_distance:.3f}"
        )
        primary_force = primary_simulator.calculate_net_force(
            state.shift_distance, engine_velocity
        )
    last_force = primary_forces[i]

# Primary Y-axis (left) for forces
axs[0, 1].plot(result.time, prim_radial, label="Primary Radial", color="tab:green")
axs[0, 1].plot(result.time, sec_radial, label="Secondary Radial", color="tab:red")
axs[0, 1].set_xlabel("Time (s)")
axs[0, 1].set_ylabel("Force (N)")
axs[0, 1].set_title("Primary and Secondary Forces Over Time")
axs[0, 1].legend(loc="upper left")
axs[0, 1].grid()

# Secondary Y-axis (right) for shift distance
ax2 = axs[0, 1].twinx()
ax2.plot(
    result.time,
    shift_distances,
    label="Shift Distance",
    color="tab:purple",
    linestyle="dashed",
)
ax2.set_ylabel("Shift Distance (units)")
ax2.legend(loc="upper right")

# Create a third y-axis for the shift velocities
ax3 = axs[0, 1].twinx()
ax3.spines["right"].set_position(("outward", 60))  # Offset the third axis
ax3.plot(
    result.time,
    shift_velocities,
    label="Shift Velocity",
    color="tab:cyan",
    linestyle="dotted",
)
ax3.set_ylabel("Shift Velocity (units/s)")
ax3.legend(loc="lower right")

# Plot the vehicle speed against engine velocity
axs[1, 0].set_xlabel("Vehicle Speed (m/s)")
axs[1, 0].set_ylabel("Engine Velocity (rad/s)")
axs[1, 0].plot(
    vehicle_speeds,
    engine_angular_velocities,
    label="Engine Velocity vs Vehicle Speed",
    color="tab:blue",
)
axs[1, 0].tick_params(axis="y", labelcolor="tab:blue")
axs[1, 0].set_title("Engine Velocity vs Vehicle Speed")
axs[1, 0].grid()

fig.tight_layout()
plt.show()
