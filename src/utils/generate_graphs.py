from matplotlib import pyplot as plt
import numpy as np
from simulations.load_simulation import LoadSimulator
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

result = SimulationResult.from_csv("simulation_output.csv")


def plotVelocity(result: SimulationResult, ax=None):
    vMax = (3277.6296 / (0.5 * FRONTAL_AREA * DRAG_COEFFICIENT * AIR_DENSITY)) ** (
        1 / 3
    )
    car_velocities = [state.car_velocity for state in result.states]
    if ax is None:
        ax = plt.gca()
    ax.plot(result.time, car_velocities, label="Car Velocity")
    ax.axhline(y=vMax, color="r", linestyle="--", label="vMax")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Car Velocity (m/s)")
    ax.set_title("Car Velocity vs Time")
    ax.legend()
    ax.grid()


def plotPosition(result: SimulationResult, ax=None):
    car_positions = [state.car_position for state in result.states]
    if ax is None:
        ax = plt.gca()
    ax.plot(result.time, car_positions, label="Car Position")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Car Position (m)")
    ax.set_title("Car Position vs Time")
    ax.legend()
    ax.grid()


def plotVehicleAccel(result: SimulationResult, ax=None):
    vehicle_accels = []
    for state in result.states:
        cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
        wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
        actual_engine_velocity = state.car_velocity * wheel_to_engine_ratio
        engine_power = engine_simulator.get_power(actual_engine_velocity)
        car_acceleration = load_simulator.calculate_acceleration(
            state.car_velocity, engine_power
        )
        vehicle_accels.append(car_acceleration)
    if ax is None:
        ax = plt.gca()
    ax.plot(result.time, vehicle_accels, label="Vehicle Acceleration")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Vehicle Acceleration (m/s²)")
    ax.set_title("Vehicle Acceleration vs Time")
    ax.legend()
    ax.grid()


def plotPrimaryClampingForce(result: SimulationResult, ax=None):
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
    if ax is None:
        ax = plt.gca()
    ax.plot(
        engine_angular_velocities,
        primary_clamping_forces,
        label="Primary Clamping Force",
    )
    ax.set_xlabel("Engine Angular Velocity (rad/s)")
    ax.set_ylabel("Primary Clamping Force (N)")
    ax.set_title("Primary Clamping Force vs Engine Angular Velocity")
    ax.legend()
    ax.grid()


def plotSecondaryClampingForce(result: SimulationResult, ax=None):
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
    if ax is None:
        ax = plt.gca()
    ax.plot(
        engine_angular_velocities,
        secondary_clamping_forces,
        label="Secondary Clamping Force",
    )
    ax.set_xlabel("Engine Angular Velocity (rad/s)")
    ax.set_ylabel("Secondary Clamping Force (N)")
    ax.set_title("Secondary Clamping Force vs Engine Angular Velocity")
    ax.legend()
    ax.grid()


def plotVehicleEngineSpeed(result: SimulationResult, ax=None):
    cvt_ratios = []
    vehicle_speeds = []
    engine_speeds = []
    times = result.time

    for state in result.states:
        cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
        wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
        actual_engine_velocity = state.car_velocity * wheel_to_engine_ratio
        cvt_ratios.append(cvt_ratio)
        vehicle_speeds.append(state.car_velocity)
        engine_speeds.append(actual_engine_velocity)

    if ax is None:
        fig, ax = plt.subplots(figsize=(12, 8))
    # Plot Vehicle Speed on the primary axis.
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Vehicle Speed (m/s)", color="#DDDD40")
    ax.plot(times, vehicle_speeds, label="Vehicle Speed", color="#DDDD40", linewidth=4)
    ax.tick_params(axis="y", labelcolor="#DDDD40")

    # Create twin axis for Engine Speed.
    ax2 = ax.twinx()
    ax2.set_ylabel("Engine Speed (rad/s)", color="#000000")
    ax2.plot(times, engine_speeds, label="Engine Speed", color="#000000", linewidth=1.5)
    ax2.tick_params(axis="y", labelcolor="#000000")

    # Create second twin axis for CVT Ratio.
    ax3 = ax.twinx()
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

    ax.set_title("Vehicle Speed, Engine Speed, and CVT Ratio vs Time")
    ax.grid()


def plot_forces_over_time(result: SimulationResult, ax=None):
    observables = [cvt_shift.get_pulley_forces(state) for state in result.states]
    prim_radial = [obs["primary_radial"] for obs in observables]
    sec_radial = [obs["secondary_radial"] for obs in observables]
    shift_distances = [state.shift_distance for state in result.states]
    shift_velocities = [state.shift_velocity for state in result.states]

    if ax is None:
        ax = plt.gca()
    ax.plot(result.time, prim_radial, label="Primary Radial", color="tab:green")
    ax.plot(result.time, sec_radial, label="Secondary Radial", color="tab:red")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Force (N)")
    ax.set_title("Primary and Secondary Forces Over Time")
    ax.legend(loc="upper left")
    ax.grid()

    # Create a twin axis for shift distance.
    ax2 = ax.twinx()
    ax2.plot(
        result.time,
        shift_distances,
        label="Shift Distance",
        color="tab:purple",
        linestyle="dashed",
    )
    ax2.set_ylabel("Shift Distance (units)")
    ax2.legend(loc="upper right")

    # Create a third y-axis for shift velocities.
    ax3 = ax.twinx()
    ax3.spines["right"].set_position(("outward", 60))
    ax3.plot(
        result.time,
        shift_velocities,
        label="Shift Velocity",
        color="tab:cyan",
        linestyle="dotted",
    )
    ax3.set_ylabel("Shift Velocity (units/s)")
    ax3.legend(loc="lower right")


def plotShiftDistance(result: SimulationResult, ax=None):
    shift_distances = [state.shift_distance for state in result.states]
    cvt_ratios = [tm.current_cvt_ratio(state.shift_distance) for state in result.states]
    wheel_to_engine_ratios = [
        (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS for cvt_ratio in cvt_ratios
    ]
    engine_angular_velocities = [
        state.car_velocity * wheel_to_engine_ratio
        for state, wheel_to_engine_ratio in zip(result.states, wheel_to_engine_ratios)
    ]
    if ax is None:
        ax = plt.gca()
    ax.plot(engine_angular_velocities, shift_distances, label="Shift Distance")
    ax.set_xlabel("Engine Angular Velocity (rad/s)")
    ax.set_ylabel("Shift Distance (units)")
    ax.set_title("Shift Distance vs Engine Angular Velocity")
    ax.legend()
    ax.grid()


def plotShiftCurve(result: SimulationResult, ax=None):
    vehicle_speeds = [state.car_velocity for state in result.states]
    cvt_ratios = [tm.current_cvt_ratio(state.shift_distance) for state in result.states]
    wheel_to_engine_ratios = [
        (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS for cvt_ratio in cvt_ratios
    ]
    engine_angular_velocities = [
        state.car_velocity * wheel_to_engine_ratio
        for state, wheel_to_engine_ratio in zip(result.states, wheel_to_engine_ratios)
    ]
    min_ratio = tm.current_cvt_ratio(0) * GEARBOX_RATIO / WHEEL_RADIUS
    max_ratio = tm.current_cvt_ratio(MAX_SHIFT) * GEARBOX_RATIO / WHEEL_RADIUS
    max_engine = max(engine_angular_velocities)
    vehicle_speeds_arr = np.array(vehicle_speeds)
    mask_min = (min_ratio * vehicle_speeds_arr) <= max_engine
    mask_max = (max_ratio * vehicle_speeds_arr) <= max_engine

    if ax is None:
        ax = plt.gca()
    ax.plot(
        vehicle_speeds, engine_angular_velocities, label="Engine Speed", linewidth=2
    )

    x_min = vehicle_speeds_arr[mask_min]
    y_min = min_ratio * x_min
    x_max = vehicle_speeds_arr[mask_max]
    y_max = max_ratio * x_max

    # Extend the dashed lines to zero.
    x_min = np.insert(x_min, 0, 0)
    y_min = np.insert(y_min, 0, 0)
    x_max = np.insert(x_max, 0, 0)
    y_max = np.insert(y_max, 0, 0)

    ax.plot(x_min, y_min, label="Min Ratio", linestyle="--", alpha=0.8)
    ax.plot(x_max, y_max, label="Max Ratio", linestyle="--", alpha=0.8)

    ax.set_xlabel("Vehicle Speed (m/s)")
    ax.set_ylabel("Engine Angular Velocity (rad/s)")
    ax.set_title("Engine Speed vs Vehicle Speed")
    ax.legend()
    ax.grid()
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)


if __name__ == "__main__":
    # Create a grid of subplots: 2 rows x 4 columns for our eight plots.
    fig, axs = plt.subplots(2, 4, figsize=(24, 12))

    # Call each plotting function with its corresponding axis.
    plotVehicleEngineSpeed(result, ax=axs[0, 0])
    plotVehicleAccel(result, ax=axs[0, 1])
    plotVelocity(result, ax=axs[0, 2])
    plotPrimaryClampingForce(result, ax=axs[0, 3])
    plotSecondaryClampingForce(result, ax=axs[1, 0])
    plot_forces_over_time(result, ax=axs[1, 1])
    plotShiftDistance(result, ax=axs[1, 2])
    plotShiftCurve(result, ax=axs[1, 3])
    plt.tight_layout()
    plt.show()
