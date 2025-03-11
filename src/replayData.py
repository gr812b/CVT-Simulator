from matplotlib import pyplot as plt
import numpy as np
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
    WHEEL_RADIUS,
    MAX_SHIFT,
)
from constants.constants import AIR_DENSITY
from utils.conversions import deg_to_rad
from utils.argument_parser import get_arguments
from utils.theoretical_models import TheoreticalModels as tm

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


result = SimulationResult.from_csv("simulation_output.csv")

# result.plot("car_velocity")
# result.plot("car_position")
# result.plot("shift_distance")
# result.plot("shift_velocity")
# result.plot("engine_angular_velocity")


def plotVelocity(result: SimulationResult):
    vMax = (3277.6296 / (1 / 2 * FRONTAL_AREA * DRAG_COEFFICIENT * AIR_DENSITY)) ** (
        1 / 3
    )
    car_velocities = [state.car_velocity for state in result.states]
    plt.figure()
    plt.plot(result.time, car_velocities, label="Car Velocity")
    plt.axhline(y=vMax, color="r", linestyle="--", label="vMax")
    plt.xlabel("Time (s)")
    plt.ylabel("Car Velocity (m/s)")
    plt.title("Car Velocity vs Time")
    plt.legend()
    plt.grid()


def plotVehicleAccel(result: SimulationResult):
    vehicle_accels = []
    for state in result.states:
        engine_power = engine_simulator.get_power(state.engine_angular_velocity)
        car_acceleration = load_simulator.calculate_acceleration(
            state.car_velocity, engine_power
        )
        vehicle_accels.append(car_acceleration)
    plt.figure()
    plt.plot(result.time, vehicle_accels, label="Vehicle Acceleration")
    plt.xlabel("Time (s)")
    plt.ylabel("Vehicle Acceleration (m/s^2)")
    plt.title("Vehicle Acceleration vs Time")
    plt.legend()
    plt.grid()


def plotPrimaryClampingForce(result: SimulationResult):
    primary_clamping_forces = []
    engine_angular_velocities = []
    for state in result.states:
        cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
        wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
        actual_engine_velocity = state.car_velocity * wheel_to_engine_ratio
        primary_force = primary_simulator.calculate_net_force(
            state.shift_distance, actual_engine_velocity
        )
        primary_clamping_forces.append(primary_force)
        engine_angular_velocities.append(actual_engine_velocity)
    plt.figure()
    plt.plot(
        engine_angular_velocities,
        primary_clamping_forces,
        label="Primary Clamping Force",
    )
    plt.xlabel("Engine Angular Velocity (rad/s)")
    plt.ylabel("Primary Clamping Force (N)")
    plt.title("Primary Clamping Force vs Engine Angular Velocity")
    plt.legend()
    plt.grid()


def plotSecondaryClampingForce(result: SimulationResult):
    secondary_clamping_forces = []
    engine_angular_velocities = []
    for state in result.states:
        cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
        wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
        actual_engine_velocity = state.car_velocity * wheel_to_engine_ratio
        engine_power = engine_simulator.get_power(actual_engine_velocity)
        secondary_force = secondary_simulator.calculate_net_force(
            engine_power * cvt_ratio, state.shift_distance
        )
        secondary_clamping_forces.append(secondary_force)
        engine_angular_velocities.append(actual_engine_velocity)
    plt.figure()
    plt.plot(
        engine_angular_velocities,
        secondary_clamping_forces,
        label="Secondary Clamping Force",
    )
    plt.xlabel("Engine Angular Velocity (rad/s)")
    plt.ylabel("Secondary Clamping Force (N)")
    plt.title("Secondary Clamping Force vs Engine Angular Velocity")
    plt.legend()
    plt.grid()


def plotVehicleEngineSpeed(result: SimulationResult):
    cvt_ratios = []
    vehicle_speeds = []
    engine_speeds = []
    times = result.time

    # Loop through each state in the simulation stake and calculate metrics.
    for result in result.states:
        # Compute CVT ratio and related engine speed.
        cvt_ratio = tm.current_cvt_ratio(result.shift_distance)
        wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
        actual_engine_velocity = result.car_velocity * wheel_to_engine_ratio

        cvt_ratios.append(cvt_ratio)
        vehicle_speeds.append(result.car_velocity)
        engine_speeds.append(actual_engine_velocity)

    fig, ax1 = plt.subplots(figsize=(12, 8))

    # Plot Vehicle Speed on the primary y-axis.
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Vehicle Speed (m/s)", color="#DDDD40")
    ax1.plot(times, vehicle_speeds, label="Vehicle Speed", color="#DDDD40", linewidth=4)
    ax1.tick_params(axis="y", labelcolor="#DDDD40")

    # Create a twin axis for Engine Speed.
    ax2 = ax1.twinx()
    ax2.set_ylabel("Engine Speed (rad/s)", color="#000000")
    ax2.plot(times, engine_speeds, label="Engine Speed", color="#000000", linewidth=1.5)
    ax2.tick_params(axis="y", labelcolor="#000000")

    # Create a second twin axis for CVT Ratio and offset it.
    ax3 = ax1.twinx()
    ax3.spines["right"].set_position(("outward", 60))
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

    # Add title and grid.
    ax1.set_title("Vehicle Speed, Engine Speed, and CVT Ratio vs Time")
    ax1.grid()


# Function to plot primary and secondary forces over time
def plot_forces_over_time(result: SimulationResult):
    # Unpack the observables for plotting or further processing
    observables = [get_pulley_forces(state) for state in result.states]
    prim_radial = [obs["primary_radial"] for obs in observables]
    sec_radial = [obs["secondary_radial"] for obs in observables]
    shift_distances = [state.shift_distance for state in result.states]
    shift_velocities = [state.shift_velocity for state in result.states]

    # Create a new figure for the plot
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Primary Y-axis (left) for forces
    ax1.plot(result.time, prim_radial, label="Primary Radial", color="tab:green")
    ax1.plot(result.time, sec_radial, label="Secondary Radial", color="tab:red")
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Force (N)")
    ax1.set_title("Primary and Secondary Forces Over Time")
    ax1.legend(loc="upper left")
    ax1.grid()

    # Secondary Y-axis (right) for shift distance
    ax2 = ax1.twinx()
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
    ax3 = ax1.twinx()
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


def plotShiftDistance(result: SimulationResult):
    shift_distances = [state.shift_distance for state in result.states]
    # Compute the engine angular velocity
    cvt_ratios = [tm.current_cvt_ratio(state.shift_distance) for state in result.states]
    wheel_to_engine_ratios = [
        (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS for cvt_ratio in cvt_ratios
    ]
    engine_angular_velocities = [
        state.car_velocity * wheel_to_engine_ratio
        for state, wheel_to_engine_ratio in zip(result.states, wheel_to_engine_ratios)
    ]
    plt.figure()
    plt.plot(engine_angular_velocities, shift_distances, label="Shift Distance")
    plt.xlabel("Engine Angular Velocity (rad/s)")
    plt.ylabel("Shift Distance (units)")
    plt.title("Shift Distance vs Engine Angular Velocity")
    plt.legend()
    plt.grid()


plotShiftDistance(result)
plt.show()


def plotShiftCurve(result: SimulationResult):
    # Extract vehicle speeds and compute engine angular velocities.
    vehicle_speeds = [state.car_velocity for state in result.states]
    cvt_ratios = [tm.current_cvt_ratio(state.shift_distance) for state in result.states]
    wheel_to_engine_ratios = [
        (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS for cvt_ratio in cvt_ratios
    ]
    engine_angular_velocities = [
        state.car_velocity * wheel_to_engine_ratio
        for state, wheel_to_engine_ratio in zip(result.states, wheel_to_engine_ratios)
    ]

    # Compute constant ratios for the minimum and maximum cvt ratios.
    min_ratio = tm.current_cvt_ratio(0) * GEARBOX_RATIO / WHEEL_RADIUS
    max_ratio = tm.current_cvt_ratio(MAX_SHIFT) * GEARBOX_RATIO / WHEEL_RADIUS

    # Find the maximum engine angular velocity to use as an upper bound.
    max_engine = max(engine_angular_velocities)

    vehicle_speeds_arr = np.array(vehicle_speeds)

    # Create masks for plotting the dashed lines only where they don't exceed the maximum engine speed.
    mask_min = (min_ratio * vehicle_speeds_arr) <= max_engine
    mask_max = (max_ratio * vehicle_speeds_arr) <= max_engine

    # Plot the main engine speed curve.
    plt.figure()
    plt.plot(
        vehicle_speeds, engine_angular_velocities, label="Engine Speed", linewidth=2
    )

    # Get masked arrays for the dashed lines.
    x_min = vehicle_speeds_arr[mask_min]
    y_min = min_ratio * x_min
    x_max = vehicle_speeds_arr[mask_max]
    y_max = max_ratio * x_max

    # Insert (0, 0) so the dashed lines extend all the way to zero.
    x_min = np.insert(x_min, 0, 0)
    y_min = np.insert(y_min, 0, 0)
    x_max = np.insert(x_max, 0, 0)
    y_max = np.insert(y_max, 0, 0)

    # Plot the dashed lines.
    plt.plot(
        x_min,
        y_min,
        label="Min Ratio",
        linestyle="--",
        alpha=0.8,
    )
    plt.plot(
        x_max,
        y_max,
        label="Max Ratio",
        linestyle="--",
        alpha=0.8,
    )

    plt.xlabel("Vehicle Speed (m/s)")
    plt.ylabel("Engine Angular Velocity (rad/s)")
    plt.title("Engine Speed vs Vehicle Speed")
    plt.legend()
    plt.grid()
    plt.xlim(left=0)
    plt.ylim(bottom=0)


plotShiftCurve(result)
plt.show()
