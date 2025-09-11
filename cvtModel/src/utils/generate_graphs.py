from matplotlib import pyplot as plt
import numpy as np
from models.model_initializer import get_models
from utils.simulation_result import SimulationResult
from constants.car_specs import (
    GEARBOX_RATIO,
    FRONTAL_AREA,
    DRAG_COEFFICIENT,
    WHEEL_RADIUS,
    MAX_SHIFT,
)
from constants.constants import AIR_DENSITY
from utils.argument_parser import get_arguments
from utils.theoretical_models import TheoreticalModels as tm

# Parse arguments
args = get_arguments()

# Initialize models with args
car_model, cvt_model = get_models(args)


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
        car_acceleration = car_model.get_breakdown(state).acceleration
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
    primary_radial_forces = []
    engine_angular_velocities = []
    for state in result.states:
        shift_breakdown = cvt_model.get_breakdown(state)
        car_breakdown = car_model.get_breakdown(state)

        primary_force = shift_breakdown.primaryRadialForce.pulleyForce.net
        primary_radial_force = shift_breakdown.primaryRadialForce.net
        actual_engine_velocity = car_breakdown.engine_forces.angular_velocity

        primary_clamping_forces.append(primary_force)
        primary_radial_forces.append(primary_radial_force)
        engine_angular_velocities.append(actual_engine_velocity)
    if ax is None:
        ax = plt.gca()
    ax.plot(
        engine_angular_velocities,
        primary_clamping_forces,
        label="Primary Clamping Force",
    )
    ax.plot(
        engine_angular_velocities, primary_radial_forces, label="Primary Radial Force"
    )
    ax.set_xlabel("Engine Angular Velocity (rad/s)")
    ax.set_ylabel("Primary Clamping Force (N)")
    ax.set_title("Primary Clamping Force vs Engine Angular Velocity")
    ax.legend()
    ax.grid()


def plotSecondaryClampingForce(result: SimulationResult, ax=None):
    secondary_clamping_forces = []
    secondary_radial_forces = []
    engine_angular_velocities = []
    for state in result.states:
        shift_breakdown = cvt_model.get_breakdown(state)
        car_breakdown = car_model.get_breakdown(state)

        secondary_force = shift_breakdown.secondaryRadialForce.pulleyForce.net
        secondary_radial = shift_breakdown.secondaryRadialForce.net
        actual_engine_velocity = car_breakdown.engine_forces.angular_velocity

        secondary_clamping_forces.append(secondary_force)
        secondary_radial_forces.append(secondary_radial)
        engine_angular_velocities.append(actual_engine_velocity)
    if ax is None:
        ax = plt.gca()
    ax.plot(
        engine_angular_velocities,
        secondary_clamping_forces,
        label="Secondary Clamping Force",
    )
    ax.plot(
        engine_angular_velocities,
        secondary_radial_forces,
        label="Secondary Radial Force",
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
        car_breakdown = car_model.get_breakdown(state)

        # TODO: This shoud be in a data field somewhere
        cvt_ratio = tm.current_cvt_ratio(state.shift_distance)

        cvt_ratios.append(cvt_ratio)
        vehicle_speeds.append(state.car_velocity)
        engine_speeds.append(car_breakdown.engine_forces.angular_velocity)

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
    prim_radial = []
    sec_radial = []

    for state in result.states:
        shift_breakdown = cvt_model.get_breakdown(state)

        prim_radial.append(shift_breakdown.primaryRadialForce.net)
        sec_radial.append(shift_breakdown.secondaryRadialForce.net)

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
    shift_distances = []
    engine_angular_velocities = []

    for state in result.states:
        car_breakdown = car_model.get_breakdown(state)

        shift_distances.append(state.shift_distance)
        engine_angular_velocities.append(car_breakdown.engine_forces.angular_velocity)

    if ax is None:
        ax = plt.gca()
    ax.plot(engine_angular_velocities, shift_distances, label="Shift Distance")
    ax.set_xlabel("Engine Angular Velocity (rad/s)")
    ax.set_ylabel("Shift Distance (units)")
    ax.set_title("Shift Distance vs Engine Angular Velocity")
    ax.legend()
    ax.grid()


def plotShiftCurves(results: list[SimulationResult], ax=None):
    if ax is None:
        ax = plt.gca()

    # Plot each simulation's engine speed curve.
    for i, result in enumerate(results):
        vehicle_speeds = []
        engine_angular_velocities = []
        
        for state in result.states:
            car_breakdown = car_model.get_breakdown(state)

            vehicle_speeds.append(state.car_velocity)
            engine_angular_velocities.append(car_breakdown.engine_forces.angular_velocity)

        ax.plot(
            vehicle_speeds,
            engine_angular_velocities,
            label=f"Engine Speed {i}",
            linewidth=2,
        )

    # Combine vehicle speeds and engine speeds from all results to determine common limits.
    all_vehicle_speeds = []
    all_engine_velocities = []
    for result in results:
        vehicle_speeds = []
        engine_angular_velocities = []
        
        for state in result.states:
            car_breakdown = car_model.get_breakdown(state)

            vehicle_speeds.append(state.car_velocity)
            engine_angular_velocities.append(car_breakdown.engine_forces.angular_velocity)

        all_vehicle_speeds.extend(vehicle_speeds)
        all_engine_velocities.extend(engine_angular_velocities)

    # Use the global maximum values for the x-range and engine speed limit.
    max_x = max(all_vehicle_speeds) if all_vehicle_speeds else 0
    max_engine = max(all_engine_velocities) if all_engine_velocities else 0

    # Compute constant ratios (they are independent of the simulation result).
    min_ratio = tm.current_cvt_ratio(0) * GEARBOX_RATIO / WHEEL_RADIUS
    max_ratio = tm.current_cvt_ratio(MAX_SHIFT) * GEARBOX_RATIO / WHEEL_RADIUS

    # Create a common x-axis for the dashed lines.
    x_vals = np.linspace(0, max_x, 100)
    y_min = min_ratio * x_vals
    y_max = max_ratio * x_vals

    # Only keep the portions of the dashed lines that are below the maximum engine speed.
    mask_min = y_min <= max_engine
    mask_max = y_max <= max_engine
    x_min = x_vals[mask_min]
    y_min = y_min[mask_min]
    x_max = x_vals[mask_max]
    y_max = y_max[mask_max]

    # Ensure the lines start at zero.
    if x_min[0] != 0:
        x_min = np.insert(x_min, 0, 0)
        y_min = np.insert(y_min, 0, 0)
    if x_max[0] != 0:
        x_max = np.insert(x_max, 0, 0)
        y_max = np.insert(y_max, 0, 0)

    # Plot the min and max ratio lines once.
    ax.plot(x_min, y_min, label="Min Ratio", linestyle="--", alpha=0.8)
    ax.plot(x_max, y_max, label="Max Ratio", linestyle="--", alpha=0.8)

    # Set up plot labels and grid.
    ax.set_xlabel("Vehicle Speed (m/s)")
    ax.set_ylabel("Engine Angular Velocity (rad/s)")
    ax.set_title("Engine Speed vs Vehicle Speed")
    ax.legend()
    ax.grid()
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)


if __name__ == "__main__":
    result = SimulationResult.from_csv("simulation_output.csv")
    # result2 = SimulationResult.from_csv("simulation_output_2.csv")
    # Create a grid of subplots: 2 rows x 4 columns for our eight plots.
    fig, axs = plt.subplots(2, 4, figsize=(24, 12))

    # Call each plotting function with its corresponding axis.
    plotVehicleEngineSpeed(result, ax=axs[0, 0])
    plotVehicleAccel(result, ax=axs[0, 1])
    plotVelocity(result, ax=axs[0, 2])
    plotPrimaryClampingForce(result, ax=axs[0, 3])
    plotSecondaryClampingForce(result, ax=axs[1, 0])
    plotPosition(result, ax=axs[1, 1])
    plotShiftDistance(result, ax=axs[1, 2])
    plotShiftCurves([result], ax=axs[1, 3])
    plt.tight_layout()
    plt.show()

    plotShiftCurves([result])
    plt.show()
