"""
Plot CVT pulley torque bounds and bound-term breakdowns.

This utility runs two independent sweeps:
- Primary sweep plotted against primary speed (RPM)
- Secondary sweep plotted against secondary speed (RPM)

No CSV is produced. The script is plot-first for quick model inspection.
"""

from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from cvt_simulator.constants.car_specs import ENGINE_INERTIA, HELIX_RADIUS, MAX_SHIFT, SECONDARY_INERTIA
from cvt_simulator.models.pulley.primary_pulley_flyweight import PhysicalPrimaryPulley
from cvt_simulator.models.pulley.secondary_pulley_torque_reactive import PhysicalSecondaryPulley
from cvt_simulator.models.ramps.piecewise_ramp import PiecewiseRamp
from cvt_simulator.models.ramps.theta_ramp import ThetaRamp
from cvt_simulator.utils.conversions import deg_to_rad, rpm_to_rad_s
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm


def _linspace(minimum: float, maximum: float, count: int) -> np.ndarray:
    if count <= 0:
        raise ValueError("count must be positive")
    return np.linspace(minimum, maximum, count)


def _build_models(args: SimulationArgs) -> tuple[PhysicalPrimaryPulley, PhysicalSecondaryPulley]:
    primary = PhysicalPrimaryPulley(
        spring_coeff_comp=args.primary_spring_rate,
        initial_compression=args.primary_spring_pretension,
        flyweight_mass=args.flyweight_mass,
        ramp=PiecewiseRamp.from_config(args.primary_ramp_config),
    )

    secondary = PhysicalSecondaryPulley(
        spring_coeff_tors=args.secondary_torsion_spring_rate,
        spring_coeff_comp=args.secondary_compression_spring_rate,
        initial_rotation=deg_to_rad(args.secondary_rotational_spring_pretension),
        initial_compression=args.secondary_linear_spring_pretension,
        ramp=ThetaRamp(PiecewiseRamp.from_config(args.secondary_ramp_config), HELIX_RADIUS),
    )

    return primary, secondary


def _aggregate_mean(x_values: np.ndarray, y_values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    unique_x = np.unique(x_values)
    means = np.array([y_values[x_values == x].mean() for x in unique_x], dtype=float)
    return unique_x, means


def _run_primary_sweep(
    model: PhysicalPrimaryPulley,
    args: argparse.Namespace,
) -> dict[str, np.ndarray]:
    primary_rpm_values = _linspace(args.primary_rpm_min, args.primary_rpm_max, args.primary_rpm_points)
    shift_values = _linspace(args.shift_min, args.shift_max, args.shift_points)
    shift_velocity_values = _linspace(
        args.shift_velocity_min,
        args.shift_velocity_max,
        args.shift_velocity_points,
    )
    engine_torque_values = _linspace(
        args.primary_engine_torque_min,
        args.primary_engine_torque_max,
        args.primary_engine_torque_points,
    )

    data: dict[str, list[float]] = {
        "primary_rpm": [],
        "tau_max": [],
        "tau_min": [],
        "numerator_clamping": [],
        "numerator_load": [],
        "numerator_shift": [],
        "numerator_net": [],
        "den_up_inv_radius": [],
        "den_up_inertial_feedback": [],
        "den_up_net": [],
        "den_low_inv_radius": [],
        "den_low_inertial_feedback": [],
        "den_low_net": [],
    }

    for primary_rpm, shift_distance, shift_velocity, engine_torque in product(
        primary_rpm_values,
        shift_values,
        shift_velocity_values,
        engine_torque_values,
    ):
        primary_omega = rpm_to_rad_s(float(primary_rpm))
        ratio = float(tm.current_effective_cvt_ratio(float(shift_distance)))
        secondary_omega = primary_omega * ratio

        state = SystemState(
            shift_distance=float(shift_distance),
            shift_velocity=float(shift_velocity),
            primary_pulley_angular_velocity=float(primary_omega),
            secondary_pulley_angular_velocity=float(secondary_omega),
        )

        bounds = model.calculate_torque_bounds(
            state,
            engine_drive_torque=float(engine_torque),
            primary_inertia=float(args.primary_inertia),
        )

        data["primary_rpm"].append(float(primary_rpm))
        data["tau_max"].append(float(bounds.tau_upper))
        data["tau_min"].append(float(bounds.tau_lower))
        data["numerator_clamping"].append(float(bounds.numerator.clamping_term))
        data["numerator_load"].append(float(bounds.numerator.load_term))
        data["numerator_shift"].append(float(bounds.numerator.shift_term))
        data["numerator_net"].append(float(bounds.numerator.net))
        data["den_up_inv_radius"].append(
            float(bounds.denominator_upper.inverse_radius_term)
        )
        data["den_up_inertial_feedback"].append(
            float(bounds.denominator_upper.inertial_feedback_term)
        )
        data["den_up_net"].append(float(bounds.denominator_upper.net))
        data["den_low_inv_radius"].append(
            float(bounds.denominator_lower.inverse_radius_term)
        )
        data["den_low_inertial_feedback"].append(
            float(bounds.denominator_lower.inertial_feedback_term)
        )
        data["den_low_net"].append(float(bounds.denominator_lower.net))

    return {k: np.array(v, dtype=float) for k, v in data.items()}


def _run_secondary_sweep(
    model: PhysicalSecondaryPulley,
    args: argparse.Namespace,
) -> dict[str, np.ndarray]:
    secondary_rpm_values = _linspace(
        args.secondary_rpm_min,
        args.secondary_rpm_max,
        args.secondary_rpm_points,
    )
    shift_values = _linspace(args.shift_min, args.shift_max, args.shift_points)
    shift_velocity_values = _linspace(
        args.shift_velocity_min,
        args.shift_velocity_max,
        args.shift_velocity_points,
    )
    load_torque_values = _linspace(
        args.secondary_load_torque_min,
        args.secondary_load_torque_max,
        args.secondary_load_torque_points,
    )

    data: dict[str, list[float]] = {
        "secondary_rpm": [],
        "tau_max": [],
        "tau_min": [],
        "numerator_spring": [],
        "numerator_load": [],
        "numerator_shift": [],
        "numerator_net": [],
        "den_pos_inv_radius": [],
        "den_pos_helix_feedback": [],
        "den_pos_inertial_feedback": [],
        "den_pos_net": [],
        "den_neg_inv_radius": [],
        "den_neg_helix_feedback": [],
        "den_neg_inertial_feedback": [],
        "den_neg_net": [],
    }

    for secondary_rpm, shift_distance, shift_velocity, load_torque in product(
        secondary_rpm_values,
        shift_values,
        shift_velocity_values,
        load_torque_values,
    ):
        secondary_omega = rpm_to_rad_s(float(secondary_rpm))
        ratio = float(tm.current_effective_cvt_ratio(float(shift_distance)))
        ratio_safe = ratio if abs(ratio) > 1e-9 else 1e-9
        primary_omega = secondary_omega / ratio_safe

        state = SystemState(
            shift_distance=float(shift_distance),
            shift_velocity=float(shift_velocity),
            primary_pulley_angular_velocity=float(primary_omega),
            secondary_pulley_angular_velocity=float(secondary_omega),
        )

        torque_bounds = model.calculate_torque_bounds(
            state,
            external_load_torque=float(load_torque),
            secondary_inertia=float(args.secondary_inertia),
        )

        data["secondary_rpm"].append(float(secondary_rpm))
        data["tau_max"].append(float(torque_bounds.tau_positive))
        data["tau_min"].append(float(torque_bounds.tau_negative))
        data["numerator_spring"].append(float(torque_bounds.numerator.spring_term))
        data["numerator_load"].append(float(torque_bounds.numerator.load_term))
        data["numerator_shift"].append(float(torque_bounds.numerator.shift_term))
        data["numerator_net"].append(float(torque_bounds.numerator.net))
        data["den_pos_inv_radius"].append(
            float(torque_bounds.denominator_positive.inverse_radius_term)
        )
        data["den_pos_helix_feedback"].append(
            float(torque_bounds.denominator_positive.helix_feedback_term)
        )
        data["den_pos_inertial_feedback"].append(
            float(torque_bounds.denominator_positive.inertial_feedback_term)
        )
        data["den_pos_net"].append(float(torque_bounds.denominator_positive.net))
        data["den_neg_inv_radius"].append(
            float(torque_bounds.denominator_negative.inverse_radius_term)
        )
        data["den_neg_helix_feedback"].append(
            float(torque_bounds.denominator_negative.helix_feedback_term)
        )
        data["den_neg_inertial_feedback"].append(
            float(torque_bounds.denominator_negative.inertial_feedback_term)
        )
        data["den_neg_net"].append(float(torque_bounds.denominator_negative.net))

    return {k: np.array(v, dtype=float) for k, v in data.items()}


def _plot_primary(primary: dict[str, np.ndarray]) -> plt.Figure:
    x = primary["primary_rpm"]

    x_u, tau_max = _aggregate_mean(x, primary["tau_max"])
    _, tau_min = _aggregate_mean(x, primary["tau_min"])
    _, numerator_clamping = _aggregate_mean(x, primary["numerator_clamping"])
    _, numerator_load = _aggregate_mean(x, primary["numerator_load"])
    _, numerator_shift = _aggregate_mean(x, primary["numerator_shift"])
    _, numerator_net = _aggregate_mean(x, primary["numerator_net"])
    _, den_up_inv = _aggregate_mean(x, primary["den_up_inv_radius"])
    _, den_up_inertial = _aggregate_mean(x, primary["den_up_inertial_feedback"])
    _, den_up_net = _aggregate_mean(x, primary["den_up_net"])
    _, den_low_inv = _aggregate_mean(x, primary["den_low_inv_radius"])
    _, den_low_inertial = _aggregate_mean(x, primary["den_low_inertial_feedback"])
    _, den_low_net = _aggregate_mean(x, primary["den_low_net"])

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)

    ax = axes[0, 0]
    ax.plot(x_u, tau_max, linewidth=2, label="tau_max (tau_upper)")
    ax.plot(x_u, tau_min, linewidth=2, label="tau_min (tau_lower)")
    ax.set_title("Primary Torque Limits")
    ax.set_xlabel("Primary speed (RPM)")
    ax.set_ylabel("Torque (N m)")
    ax.grid(True, alpha=0.3)
    ax.legend()

    ax = axes[0, 1]
    ax.plot(x_u, numerator_clamping, linewidth=2, label="Clamping numerator term")
    ax.plot(x_u, numerator_load, linewidth=2, label="Load numerator term")
    ax.plot(x_u, numerator_shift, linewidth=2, label="Shift numerator term")
    ax.plot(x_u, numerator_net, linewidth=2, label="Numerator net")
    ax.set_title("tau_max Numerator Breakdown")
    ax.set_xlabel("Primary speed (RPM)")
    ax.set_ylabel("Numerator terms")
    ax.grid(True, alpha=0.3)
    ax.legend()

    ax = axes[1, 0]
    ax.plot(x_u, den_up_inv, linewidth=2, label="+ inv radius term")
    ax.plot(x_u, den_up_inertial, linewidth=2, label="+ inertial feedback term")
    ax.plot(x_u, den_up_net, linewidth=2, label="D_upper net")
    ax.set_title("tau_max Denominator (D_upper)")
    ax.set_xlabel("Primary speed (RPM)")
    ax.set_ylabel("Denominator terms")
    ax.grid(True, alpha=0.3)
    ax.legend()

    ax = axes[1, 1]
    ax.plot(x_u, den_low_inv, linewidth=2, label="- inv radius term")
    ax.plot(x_u, den_low_inertial, linewidth=2, label="- inertial feedback term")
    ax.plot(x_u, den_low_net, linewidth=2, label="D_lower net")
    ax.set_title("tau_min Denominator (D_lower)")
    ax.set_xlabel("Primary speed (RPM)")
    ax.set_ylabel("Denominator terms")
    ax.grid(True, alpha=0.3)
    ax.legend()

    fig.suptitle("Primary Pulley Sweep", fontsize=14)
    return fig


def _plot_secondary(secondary: dict[str, np.ndarray], rpm_max: float) -> plt.Figure:
    x = secondary["secondary_rpm"]

    x_u, tau_max = _aggregate_mean(x, secondary["tau_max"])
    _, tau_min = _aggregate_mean(x, secondary["tau_min"])
    _, numerator_spring = _aggregate_mean(x, secondary["numerator_spring"])
    _, numerator_load = _aggregate_mean(x, secondary["numerator_load"])
    _, numerator_shift = _aggregate_mean(x, secondary["numerator_shift"])
    _, numerator_net = _aggregate_mean(x, secondary["numerator_net"])
    _, den_pos_inv = _aggregate_mean(x, secondary["den_pos_inv_radius"])
    _, den_pos_helix = _aggregate_mean(x, secondary["den_pos_helix_feedback"])
    _, den_pos_inertial = _aggregate_mean(x, secondary["den_pos_inertial_feedback"])
    _, den_pos_net = _aggregate_mean(x, secondary["den_pos_net"])
    _, den_neg_inv = _aggregate_mean(x, secondary["den_neg_inv_radius"])
    _, den_neg_helix = _aggregate_mean(x, secondary["den_neg_helix_feedback"])
    _, den_neg_inertial = _aggregate_mean(x, secondary["den_neg_inertial_feedback"])
    _, den_neg_net = _aggregate_mean(x, secondary["den_neg_net"])

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)

    ax = axes[0, 0]
    ax.plot(x_u, tau_max, linewidth=2, label="tau_max (tau_positive)")
    ax.plot(x_u, tau_min, linewidth=2, label="tau_min (tau_negative)")
    ax.set_title("Secondary Torque Limits")
    ax.set_xlabel("Secondary speed (RPM)")
    ax.set_ylabel("Torque (N m)")
    ax.set_xlim(0.0, rpm_max)
    ax.grid(True, alpha=0.3)
    ax.legend()

    ax = axes[0, 1]
    ax.plot(x_u, numerator_spring, linewidth=2, label="Spring numerator term")
    ax.plot(x_u, numerator_load, linewidth=2, label="Load numerator term")
    ax.plot(x_u, numerator_shift, linewidth=2, label="Shift numerator term")
    ax.plot(x_u, numerator_net, linewidth=2, label="Numerator net")
    ax.set_title("tau_max Numerator Breakdown")
    ax.set_xlabel("Secondary speed (RPM)")
    ax.set_ylabel("Numerator terms")
    ax.set_xlim(0.0, rpm_max)
    ax.grid(True, alpha=0.3)
    ax.legend()

    ax = axes[1, 0]
    ax.plot(x_u, den_pos_inv, linewidth=2, label="+ inv radius term")
    ax.plot(x_u, den_pos_helix, linewidth=2, label="+ helix feedback term")
    ax.plot(x_u, den_pos_inertial, linewidth=2, label="+ inertial feedback term")
    ax.plot(x_u, den_pos_net, linewidth=2, label="D_plus net")
    ax.set_title("tau_max Denominator (D_plus)")
    ax.set_xlabel("Secondary speed (RPM)")
    ax.set_ylabel("Denominator terms")
    ax.set_xlim(0.0, rpm_max)
    ax.grid(True, alpha=0.3)
    ax.legend()

    ax = axes[1, 1]
    ax.plot(x_u, den_neg_inv, linewidth=2, label="- inv radius term")
    ax.plot(x_u, den_neg_helix, linewidth=2, label="- helix feedback term")
    ax.plot(x_u, den_neg_inertial, linewidth=2, label="- inertial feedback term")
    ax.plot(x_u, den_neg_net, linewidth=2, label="D_minus net")
    ax.set_title("tau_min Denominator (D_minus)")
    ax.set_xlabel("Secondary speed (RPM)")
    ax.set_ylabel("Denominator terms")
    ax.set_xlim(0.0, rpm_max)
    ax.grid(True, alpha=0.3)
    ax.legend()

    fig.suptitle("Secondary tau_max/tau_min Term Breakdown", fontsize=14)
    return fig


def _print_secondary_single_value(model: PhysicalSecondaryPulley, args: argparse.Namespace) -> None:
    secondary_rpm = 0.0
    secondary_omega = rpm_to_rad_s(secondary_rpm)

    # Use a single reference operating point for secondary diagnostics.
    shift_distance = float(args.shift_min)
    shift_velocity = 0.0
    load_torque = float(args.secondary_load_torque_min)

    ratio = float(tm.current_effective_cvt_ratio(shift_distance))
    ratio_safe = ratio if abs(ratio) > 1e-9 else 1e-9
    primary_omega = secondary_omega / ratio_safe

    state = SystemState(
        shift_distance=shift_distance,
        shift_velocity=shift_velocity,
        primary_pulley_angular_velocity=float(primary_omega),
        secondary_pulley_angular_velocity=float(secondary_omega),
    )

    bounds = model.calculate_torque_bounds(
        state,
        external_load_torque=load_torque,
        secondary_inertia=float(args.secondary_inertia),
    )

    print("\nSecondary single-point diagnostic (RPM = 0)")
    print("-" * 64)
    print(f"secondary_rpm: {secondary_rpm}")
    print(f"shift_distance: {shift_distance}")
    print(f"shift_velocity: {shift_velocity}")
    print(f"load_torque: {load_torque}")

    print("\nTorque bound terms")
    print(f"tau_min (tau_negative): {bounds.tau_negative}")
    print(f"tau_max (tau_positive): {bounds.tau_positive}")

    print("\nNumerator terms")
    print(f"numerator_spring_term: {bounds.numerator.spring_term}")
    print(f"numerator_load_term: {bounds.numerator.load_term}")
    print(f"numerator_shift_term: {bounds.numerator.shift_term}")
    print(f"numerator_net: {bounds.numerator.net}")

    print("\nPositive denominator terms (D_plus)")
    print(
        f"inverse_radius_term: {bounds.denominator_positive.inverse_radius_term}"
    )
    print(
        f"helix_feedback_term: {bounds.denominator_positive.helix_feedback_term}"
    )
    print(
        f"inertial_feedback_term: {bounds.denominator_positive.inertial_feedback_term}"
    )
    print(f"denominator_plus_net: {bounds.denominator_positive.net}")

    print("\nNegative denominator terms (D_minus)")
    print(
        f"inverse_radius_term: {bounds.denominator_negative.inverse_radius_term}"
    )
    print(
        f"helix_feedback_term: {bounds.denominator_negative.helix_feedback_term}"
    )
    print(
        f"inertial_feedback_term: {bounds.denominator_negative.inertial_feedback_term}"
    )
    print(f"denominator_minus_net: {bounds.denominator_negative.net}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plot CVT primary/secondary torque bounds and bound terms")

    parser.add_argument("--primary-rpm-min", type=float, default=1500.0)
    parser.add_argument("--primary-rpm-max", type=float, default=4000.0)
    parser.add_argument("--primary-rpm-points", type=int, default=25)

    parser.add_argument("--secondary-rpm-min", type=float, default=0.0)
    parser.add_argument("--secondary-rpm-max", type=float, default=1000.0)
    parser.add_argument("--secondary-rpm-points", type=int, default=25)

    parser.add_argument("--shift-min", type=float, default=0.0)
    parser.add_argument("--shift-max", type=float, default=MAX_SHIFT)
    parser.add_argument("--shift-points", type=int, default=12)

    parser.add_argument("--shift-velocity-min", type=float, default=-0.3)
    parser.add_argument("--shift-velocity-max", type=float, default=0.3)
    parser.add_argument("--shift-velocity-points", type=int, default=5)

    parser.add_argument("--primary-engine-torque-min", type=float, default=10.0)
    parser.add_argument("--primary-engine-torque-max", type=float, default=60.0)
    parser.add_argument("--primary-engine-torque-points", type=int, default=6)

    parser.add_argument("--secondary-load-torque-min", type=float, default=5.0)
    parser.add_argument("--secondary-load-torque-max", type=float, default=80.0)
    parser.add_argument("--secondary-load-torque-points", type=int, default=6)

    parser.add_argument("--primary-inertia", type=float, default=ENGINE_INERTIA)
    parser.add_argument("--secondary-inertia", type=float, default=SECONDARY_INERTIA)

    parser.add_argument(
        "--plot-prefix",
        type=str,
        default="pulley_torque_force_sweep",
        help="Optional base file name for saving PNGs: <prefix>_primary.png and <prefix>_secondary.png",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save PNG files",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open plot windows",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()
    sim_args = SimulationArgs()
    primary_model, secondary_model = _build_models(sim_args)

    primary_data = _run_primary_sweep(primary_model, args)
    secondary_data = _run_secondary_sweep(secondary_model, args)
    _print_secondary_single_value(secondary_model, args)

    primary_fig = _plot_primary(primary_data)
    secondary_fig = _plot_secondary(secondary_data, rpm_max=float(args.secondary_rpm_max))

    if not args.no_save:
        prefix = Path(args.plot_prefix)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        primary_png = str(prefix.with_name(f"{prefix.name}_primary.png"))
        secondary_png = str(prefix.with_name(f"{prefix.name}_secondary.png"))
        primary_fig.savefig(primary_png, dpi=150)
        secondary_fig.savefig(secondary_png, dpi=150)
        print(f"Saved primary plot to {primary_png}")
        print(f"Saved secondary plot to {secondary_png}")

    if args.no_show:
        plt.close(primary_fig)
        plt.close(secondary_fig)
    else:
        plt.show()


if __name__ == "__main__":
    main()
