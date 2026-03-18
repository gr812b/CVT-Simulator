import argparse
from pathlib import Path

from matplotlib import pyplot as plt
import numpy as np

from cvt_simulator.constants.car_specs import GEARBOX_RATIO, MAX_SHIFT, WHEEL_RADIUS
from cvt_simulator.utils.simulation_result import SimulationResult
from cvt_simulator.utils.state_computations import (
    integrate_positions_trapezoidal,
    secondary_pulley_angular_velocity_to_car_velocity,
)
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm


def _build_series(result: SimulationResult) -> dict[str, np.ndarray]:
    time = np.asarray(result.time)
    shift_distance = np.asarray([state.shift_distance for state in result.states])
    shift_velocity = np.asarray([state.shift_velocity for state in result.states])
    primary_omega = np.asarray(
        [state.primary_pulley_angular_velocity for state in result.states]
    )
    secondary_omega = np.asarray(
        [state.secondary_pulley_angular_velocity for state in result.states]
    )

    car_velocity = np.asarray(
        [
            secondary_pulley_angular_velocity_to_car_velocity(
                state.secondary_pulley_angular_velocity
            )
            for state in result.states
        ]
    )
    car_position = integrate_positions_trapezoidal(time, car_velocity)
    cvt_ratio = np.asarray([tm.current_effective_cvt_ratio(d) for d in shift_distance])

    return {
        "time": time,
        "shift_distance": shift_distance,
        "shift_velocity": shift_velocity,
        "primary_omega": primary_omega,
        "secondary_omega": secondary_omega,
        "car_velocity": car_velocity,
        "car_position": car_position,
        "cvt_ratio": cvt_ratio,
    }


def plot_kinematics(series: dict[str, np.ndarray]):
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    t = series["time"]

    axes[0, 0].plot(t, series["shift_distance"], color="tab:purple")
    axes[0, 0].set_title("Shift Distance vs Time")
    axes[0, 0].set_xlabel("Time (s)")
    axes[0, 0].set_ylabel("Shift Distance (m)")
    axes[0, 0].grid(True, alpha=0.3)

    axes[0, 1].plot(t, series["shift_velocity"], color="tab:cyan")
    axes[0, 1].set_title("Shift Velocity vs Time")
    axes[0, 1].set_xlabel("Time (s)")
    axes[0, 1].set_ylabel("Shift Velocity (m/s)")
    axes[0, 1].grid(True, alpha=0.3)

    axes[1, 0].plot(t, series["car_velocity"], color="tab:blue", label="Car Velocity")
    axes[1, 0].plot(t, series["car_position"], color="tab:green", label="Car Position")
    axes[1, 0].set_title("Vehicle Kinematics vs Time")
    axes[1, 0].set_xlabel("Time (s)")
    axes[1, 0].legend()
    axes[1, 0].grid(True, alpha=0.3)

    axes[1, 1].plot(t, series["primary_omega"], label="Primary Pulley")
    axes[1, 1].plot(t, series["secondary_omega"], label="Secondary Pulley")
    axes[1, 1].set_title("Pulley Angular Velocities vs Time")
    axes[1, 1].set_xlabel("Time (s)")
    axes[1, 1].set_ylabel("Angular Velocity (rad/s)")
    axes[1, 1].legend()
    axes[1, 1].grid(True, alpha=0.3)

    fig.tight_layout()
    return fig


def plot_ratio_and_shift_curve(series: dict[str, np.ndarray]):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    axes[0].plot(series["time"], series["cvt_ratio"], color="tab:orange")
    axes[0].set_title("Effective CVT Ratio vs Time")
    axes[0].set_xlabel("Time (s)")
    axes[0].set_ylabel("CVT Ratio")
    axes[0].grid(True, alpha=0.3)

    vehicle_speed = series["car_velocity"]
    engine_speed = series["primary_omega"]
    axes[1].plot(vehicle_speed, engine_speed, label="Simulated Shift Curve", linewidth=2)

    min_ratio = tm.current_effective_cvt_ratio(0.0) * GEARBOX_RATIO / WHEEL_RADIUS
    max_ratio = tm.current_effective_cvt_ratio(MAX_SHIFT) * GEARBOX_RATIO / WHEEL_RADIUS
    x_vals = np.linspace(0, max(float(np.max(vehicle_speed)), 1e-6), 100)

    axes[1].plot(x_vals, min_ratio * x_vals, "--", alpha=0.8, label="Min Ratio Line")
    axes[1].plot(x_vals, max_ratio * x_vals, "--", alpha=0.8, label="Max Ratio Line")
    axes[1].set_title("Engine Speed vs Vehicle Speed")
    axes[1].set_xlabel("Vehicle Speed (m/s)")
    axes[1].set_ylabel("Engine Speed (rad/s)")
    axes[1].set_xlim(left=0)
    axes[1].set_ylim(bottom=0)
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    return fig


def generate_graphs_from_csv(csv_path: Path, out_dir: Path, show: bool = False) -> list[Path]:
    result = SimulationResult.from_csv(str(csv_path))
    series = _build_series(result)

    out_dir.mkdir(parents=True, exist_ok=True)

    kinematics_fig = plot_kinematics(series)
    kinematics_path = out_dir / "kinematics_overview.png"
    kinematics_fig.savefig(kinematics_path, dpi=150)

    ratio_fig = plot_ratio_and_shift_curve(series)
    ratio_path = out_dir / "ratio_and_shift_curve.png"
    ratio_fig.savefig(ratio_path, dpi=150)

    if show:
        plt.show()
    else:
        plt.close(kinematics_fig)
        plt.close(ratio_fig)

    return [kinematics_path, ratio_path]


def main():
    parser = argparse.ArgumentParser(
        description="Generate validation plots from an existing simulation CSV."
    )
    parser.add_argument(
        "--csv",
        default="simulation_output.csv",
        help="Path to simulation CSV (default: simulation_output.csv)",
    )
    parser.add_argument(
        "--out-dir",
        default="generated_graphs",
        help="Output directory for generated graph images",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Also show graphs interactively",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    output_paths = generate_graphs_from_csv(
        csv_path=csv_path,
        out_dir=Path(args.out_dir),
        show=args.show,
    )

    print("Generated graph files:")
    for path in output_paths:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
