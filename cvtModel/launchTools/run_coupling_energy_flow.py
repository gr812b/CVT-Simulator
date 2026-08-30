"""Visualize energy storage and coupling power in the physical flyweight and helix.

The diagnostic uses the same default route/hill system as the normal launch
tools.  It does not introduce a separate mechanism model.

Flyweight plots:
- shaft-axis kinetic energy: 1/2 J_f omega_p^2
- pivot kinetic energy: 1/2 I_f (q'_f xdot_p)^2
- exact configuration power delivered by centrifugal drive to the axial DOF:
      P_c = 1/2 omega_p^2 J'_f xdot_p
- the complementary J'(x) shaft-reaction/configuration power.

Secondary-helix plots:
- torsional spring potential energy;
- movable-sheave rotational kinetic energy
      1/2 I_m (omega_s + theta_dot)^2
- its decomposition into base shaft, cross/coupling, and relative-rotation
  terms;
- time rates of the spring and coupling-energy terms.

The cross term is a kinetic-energy decomposition term, not an independent
physical storage element; it is shown specifically to make the axial/rotational
coupling visible.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import run_route_grade_response as route  # noqa: E402
from cad_drivetrain_inertias import (  # noqa: E402
    ENGINE_EQUIVALENT_INERTIA_DEFAULT_KG_M2,
    PCVT_TOTAL_MOI_KG_M2,
    SCVT_TOTAL_MOI_KG_M2,
    TOTAL_WHEEL_ROTATIONAL_INERTIA_KG_M2,
)
from cinder.execution.hybrid import HybridIntegratorSettings, integrate_hybrid  # noqa: E402
from cinder.model.cvt.actuation import (  # noqa: E402
    FixedPivotFlyweightForce,
    HelicalTorqueReactionForce,
)
from cinder.model.system import CVTState  # noqa: E402

RPM_PER_RADIAN_PER_SECOND = 60.0 / (2.0 * np.pi)
MILLIMETRE = 1.0e-3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/coupling_energy_flow"),
    )
    parser.add_argument("--duration-s", type=float, default=10.0)
    parser.add_argument("--report-step-s", type=float, default=0.01)
    parser.add_argument("--rtol", type=float, default=1.0e-3)
    parser.add_argument("--atol", type=float, default=1.0e-6)
    parser.add_argument("--max-step-s", type=float, default=0.025)
    parser.add_argument("--no-show", action="store_true")
    return parser.parse_args()


def _default_candidate() -> route.TuneCandidate:
    preset = route.DEFAULT_FIXED_PIVOT_PRESET
    return route.load_candidate(preset)


def _find_law(actuator, law_type):
    matches = [
        law for law in actuator.force_laws
        if isinstance(law, law_type)
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one {law_type.__name__}; found {len(matches)}."
        )
    return matches[0]


def _geometry_position(model, cvt_state: CVTState):
    # Before engagement, the primary moves through the deadzone while the
    # secondary remains at its low-ratio seat.  Once the common shift reaches
    # the deadzone boundary, use the engaged geometry mapping.
    if cvt_state.shift_position < model.geometry.spec.deadzone_shift - 1.0e-10:
        return model.geometry.evaluate_deadzone(cvt_state.shift_position)
    return model.geometry.evaluate_engaged(cvt_state.shift_position)


def _gradient(values: np.ndarray, time: np.ndarray) -> np.ndarray:
    if len(values) < 3:
        return np.zeros_like(values)
    return np.gradient(values, time, edge_order=2)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    programme = route.GradeProgramme.default()
    candidate = _default_candidate()
    resolved = route.resolve_primary_preload(
        candidate,
        target_engagement_rpm=2000.0,
        programme=programme,
    )
    system, _engine, _road = route.build_composed_system(
        resolved.constants,
        programme,
    )

    initial_cvt = route.launch_cvt_state(primary_rpm=1800.0)
    initial_full = system.initial_state(
        cvt_state=initial_cvt,
        host_state=system.host.initial_state(
            secondary_shaft_angle=0.0
        ),
    )
    initial_mode = system.classify_initial_mode(initial_full)
    result = integrate_hybrid(
        system=system,
        time_span=(0.0, args.duration_s),
        initial_state=initial_full,
        initial_mode=initial_mode,
        settings=HybridIntegratorSettings(
            relative_tolerance=args.rtol,
            absolute_tolerance=args.atol,
            method="LSODA",
            max_step=args.max_step_s,
            maximum_transitions=100,
            retain_dense_output=True,
        ),
    )
    if not result.completed:
        raise RuntimeError(result.termination_reason)

    trace = route.sample_trace(
        system,
        result,
        programme,
        report_step_s=args.report_step_s,
    )

    model = system.cvt.model
    flyweight = _find_law(
        model.primary_actuator,
        FixedPivotFlyweightForce,
    )
    helix_force = _find_law(
        model.secondary_actuator,
        HelicalTorqueReactionForce,
    )
    helix_coupling = model.secondary_helical_coupling
    if helix_coupling is None:
        raise RuntimeError("Secondary helix force exists without coupling.")

    movable_secondary_inertia = (
        model.inertias.secondary.movable_sheave_rotational_inertia
    )

    n = trace.time.size
    q = np.empty(n)
    qdot = np.empty(n)
    theta = np.empty(n)
    theta_dot = np.empty(n)
    primary_xdot = np.empty(n)

    fly_shaft_energy = np.empty(n)
    fly_pivot_energy = np.empty(n)
    fly_config_power_axial = np.empty(n)
    fly_config_power_shaft = np.empty(n)
    fly_config_storage_power = np.empty(n)

    helix_spring_energy = np.empty(n)
    helix_movable_total_energy = np.empty(n)
    helix_base_shaft_energy = np.empty(n)
    helix_cross_energy = np.empty(n)
    helix_relative_energy = np.empty(n)

    # Direct generalized shift-inertia contributions.  These are the diagonal
    # M_ss terms before the coupled shaft rows are solved.  They are the
    # clearest at-a-glance measure of how large the axial/rotational correction
    # is relative to the literal translating masses.
    shift_mass_primary_axial = np.empty(n)
    shift_mass_secondary_axial = np.empty(n)
    shift_mass_flyweight = np.empty(n)
    shift_mass_helix = np.empty(n)

    for i, time_s in enumerate(trace.time):
        full_state = trace.state[:, i]
        cvt = CVTState.from_vector(
            system.layout.view(full_state, "cvt")
        )
        geometry = _geometry_position(model, cvt)

        pcoord = geometry.primary_axial_coordinate
        scoord = geometry.secondary_axial_coordinate

        axial_inertias = model.inertias.axial_translation.evaluate(
            primary_axial_coordinate=geometry.primary_axial_coordinate,
            secondary_axial_coordinate=geometry.secondary_axial_coordinate,
        )
        shift_mass_primary_axial[i] = (
            axial_inertias.primary.reflected_mass
        )
        shift_mass_secondary_axial[i] = (
            axial_inertias.secondary.reflected_mass
        )

        xdot_p = pcoord.d_value_ds * cvt.shift_speed
        primary_xdot[i] = xdot_p

        fw_sample = flyweight.spec.mechanism_map.evaluate(
            pcoord.value
        )
        q[i] = fw_sample.angle
        qdot[i] = fw_sample.angle_gradient * xdot_p
        dq_ds = (
            fw_sample.angle_gradient * pcoord.d_value_ds
        )
        shift_mass_flyweight[i] = (
            fw_sample.pivot_inertia * dq_ds**2
        )

        omega_p = cvt.primary_angular_speed
        fly_shaft_energy[i] = (
            0.5 * fw_sample.shaft_inertia * omega_p**2
        )
        fly_pivot_energy[i] = (
            0.5 * fw_sample.pivot_inertia * qdot[i] ** 2
        )

        # Pure configuration-power triad associated with J_f(x):
        # shaft reaction + axial centrifugal work + changing stored shaft-mode
        # kinetic energy = 0, excluding the ordinary J omega alpha term.
        fly_config_power_axial[i] = (
            0.5
            * omega_p**2
            * fw_sample.shaft_inertia_gradient
            * xdot_p
        )
        fly_config_power_shaft[i] = (
            -fw_sample.shaft_inertia_gradient
            * xdot_p
            * omega_p**2
        )
        fly_config_storage_power[i] = (
            0.5
            * fw_sample.shaft_inertia_gradient
            * xdot_p
            * omega_p**2
        )

        kin = helix_coupling.evaluate_from_local_coordinate(
            axial_position=scoord.value,
            d_axial_position_ds=scoord.d_value_ds,
            d2_axial_position_ds2=scoord.d2_value_ds2,
        )
        theta[i] = kin.theta
        theta_dot[i] = kin.dtheta_ds * cvt.shift_speed
        shift_mass_helix[i] = (
            movable_secondary_inertia * kin.dtheta_ds**2
        )

        omega_s = cvt.secondary_angular_speed
        movable_speed = omega_s + theta_dot[i]
        helix_movable_total_energy[i] = (
            0.5
            * movable_secondary_inertia
            * movable_speed**2
        )
        helix_base_shaft_energy[i] = (
            0.5
            * movable_secondary_inertia
            * omega_s**2
        )
        helix_cross_energy[i] = (
            movable_secondary_inertia
            * omega_s
            * theta_dot[i]
        )
        helix_relative_energy[i] = (
            0.5
            * movable_secondary_inertia
            * theta_dot[i] ** 2
        )

        twist = helix_force.spec.initial_twist - kin.theta
        helix_spring_energy[i] = (
            0.5
            * helix_force.spec.torsional_stiffness
            * twist**2
        )

    fly_total_energy = fly_shaft_energy + fly_pivot_energy
    fly_pivot_storage_power = _gradient(
        fly_pivot_energy,
        trace.time,
    )
    fly_total_storage_power = _gradient(
        fly_total_energy,
        trace.time,
    )

    helix_spring_power = _gradient(
        helix_spring_energy,
        trace.time,
    )
    helix_cross_power = _gradient(
        helix_cross_energy,
        trace.time,
    )
    helix_relative_power = _gradient(
        helix_relative_energy,
        trace.time,
    )
    helix_movable_total_power = _gradient(
        helix_movable_total_energy,
        trace.time,
    )

    shift_mass_base = (
        shift_mass_primary_axial
        + shift_mass_secondary_axial
    )
    shift_mass_coupled = (
        shift_mass_base
        + shift_mass_flyweight
        + shift_mass_helix
    )
    same_force_acceleration_fraction = np.divide(
        shift_mass_base,
        shift_mass_coupled,
        out=np.ones_like(shift_mass_base),
        where=shift_mass_coupled > 0.0,
    )
    shift_acceleration = _gradient(
        trace.state[4],
        trace.time,
    )
    direct_flyweight_inertial_force = (
        -shift_mass_flyweight * shift_acceleration
    )
    direct_helix_inertial_force = (
        -shift_mass_helix * shift_acceleration
    )

    primary_rpm = (
        trace.state[0] * RPM_PER_RADIAN_PER_SECOND
    )
    shift_mm = trace.state[3] / MILLIMETRE

    rows = []
    for i, time_s in enumerate(trace.time):
        rows.append(
            {
                "time_s": float(time_s),
                "mode": trace.mode[i],
                "primary_rpm": float(primary_rpm[i]),
                "shift_mm": float(shift_mm[i]),
                "flyweight_q_deg": float(np.rad2deg(q[i])),
                "flyweight_qdot_rad_s": float(qdot[i]),
                "flyweight_shaft_energy_J": float(
                    fly_shaft_energy[i]
                ),
                "flyweight_pivot_energy_J": float(
                    fly_pivot_energy[i]
                ),
                "flyweight_total_energy_J": float(
                    fly_total_energy[i]
                ),
                "flyweight_config_power_to_axial_W": float(
                    fly_config_power_axial[i]
                ),
                "flyweight_config_reaction_power_on_shaft_W": float(
                    fly_config_power_shaft[i]
                ),
                "flyweight_J_configuration_storage_power_W": float(
                    fly_config_storage_power[i]
                ),
                "flyweight_pivot_storage_power_W": float(
                    fly_pivot_storage_power[i]
                ),
                "flyweight_total_storage_power_W": float(
                    fly_total_storage_power[i]
                ),
                "helix_theta_deg": float(np.rad2deg(theta[i])),
                "helix_theta_dot_rad_s": float(theta_dot[i]),
                "helix_torsional_spring_energy_J": float(
                    helix_spring_energy[i]
                ),
                "secondary_movable_total_rotational_energy_J": float(
                    helix_movable_total_energy[i]
                ),
                "secondary_movable_base_shaft_energy_J": float(
                    helix_base_shaft_energy[i]
                ),
                "secondary_helix_cross_energy_J": float(
                    helix_cross_energy[i]
                ),
                "secondary_helix_relative_energy_J": float(
                    helix_relative_energy[i]
                ),
                "helix_spring_storage_power_W": float(
                    helix_spring_power[i]
                ),
                "secondary_helix_cross_power_W": float(
                    helix_cross_power[i]
                ),
                "secondary_helix_relative_power_W": float(
                    helix_relative_power[i]
                ),
                "secondary_movable_total_storage_power_W": float(
                    helix_movable_total_power[i]
                ),
                "base_axial_generalized_mass_kg": float(
                    shift_mass_base[i]
                ),
                "flyweight_reflected_shift_mass_kg": float(
                    shift_mass_flyweight[i]
                ),
                "helix_reflected_shift_mass_kg": float(
                    shift_mass_helix[i]
                ),
                "total_direct_shift_mass_kg": float(
                    shift_mass_coupled[i]
                ),
                "same_force_shift_acceleration_fraction": float(
                    same_force_acceleration_fraction[i]
                ),
                "direct_flyweight_inertial_force_N": float(
                    direct_flyweight_inertial_force[i]
                ),
                "direct_helix_inertial_force_N": float(
                    direct_helix_inertial_force[i]
                ),
            }
        )

    csv_path = args.output_dir / "coupling_energy_flow.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    # ------------------------------------------------------------------
    # At-a-glance coupling impact across the physical shift range.
    # ------------------------------------------------------------------
    shift_grid = np.linspace(
        model.geometry.spec.deadzone_shift,
        model.geometry.spec.max_shift,
        240,
    )
    grid_base = np.empty_like(shift_grid)
    grid_primary = np.empty_like(shift_grid)
    grid_secondary = np.empty_like(shift_grid)
    grid_fly = np.empty_like(shift_grid)
    grid_helix = np.empty_like(shift_grid)

    for index, shift_value in enumerate(shift_grid):
        geometry = model.geometry.evaluate_engaged(
            float(shift_value)
        )
        axial = model.inertias.axial_translation.evaluate(
            primary_axial_coordinate=geometry.primary_axial_coordinate,
            secondary_axial_coordinate=geometry.secondary_axial_coordinate,
        )
        grid_primary[index] = axial.primary.reflected_mass
        grid_secondary[index] = axial.secondary.reflected_mass
        grid_base[index] = (
            grid_primary[index]
            + grid_secondary[index]
        )

        fw = flyweight.spec.mechanism_map.evaluate(
            geometry.primary_axial_coordinate.value
        )
        dq_ds = (
            fw.angle_gradient
            * geometry.primary_axial_coordinate.d_value_ds
        )
        grid_fly[index] = fw.pivot_inertia * dq_ds**2

        hk = helix_coupling.evaluate_from_local_coordinate(
            axial_position=geometry.secondary_axial_coordinate.value,
            d_axial_position_ds=(
                geometry.secondary_axial_coordinate.d_value_ds
            ),
            d2_axial_position_ds2=(
                geometry.secondary_axial_coordinate.d2_value_ds2
            ),
        )
        grid_helix[index] = (
            movable_secondary_inertia * hk.dtheta_ds**2
        )

    grid_total = grid_base + grid_fly + grid_helix
    grid_accel_fraction = grid_base / grid_total
    shift_percent = (
        100.0
        * (shift_grid - model.geometry.spec.deadzone_shift)
        / (
            model.geometry.spec.max_shift
            - model.geometry.spec.deadzone_shift
        )
    )

    mid = len(shift_grid) // 2
    helix_to_base = grid_helix[mid] / grid_base[mid]
    fly_to_base = grid_fly[mid] / grid_base[mid]
    accel_percent_mid = 100.0 * grid_accel_fraction[mid]
    helix_share_mid = 100.0 * grid_helix[mid] / grid_total[mid]

    impact_figure, (impact_mass_ax, impact_accel_ax) = plt.subplots(
        2,
        1,
        figsize=(10.0, 7.5),
        sharex=True,
        constrained_layout=True,
    )
    impact_mass_ax.stackplot(
        shift_percent,
        grid_primary,
        grid_secondary,
        grid_fly,
        grid_helix,
        labels=(
            "primary translation",
            "secondary translation",
            "flyweight pivot reflection",
            "secondary helix rotation",
        ),
        alpha=0.82,
    )
    impact_mass_ax.plot(
        shift_percent,
        grid_total,
        linewidth=2.0,
        label="total direct generalized shift inertia",
    )
    impact_mass_ax.set_ylabel(r"$M_{ss}$ contribution [kg]")
    impact_mass_ax.set_title(
        "Axial/rotational coupling impact at a glance\n"
        f"mid-shift: helix = {grid_helix[mid]:.2f} kg "
        f"({helix_to_base:.1f}Ã— literal axial mass), "
        f"flyweight = {grid_fly[mid]:.2f} kg; "
        f"helix share = {helix_share_mid:.0f}%"
    )
    impact_mass_ax.legend(
        loc="upper left",
        fontsize=8,
        ncols=2,
    )
    impact_mass_ax.grid(True, alpha=0.25)

    impact_accel_ax.plot(
        shift_percent,
        100.0 * grid_accel_fraction,
        linewidth=2.2,
        label="full coupling",
    )
    impact_accel_ax.plot(
        shift_percent,
        100.0 * grid_base / (grid_base + grid_fly),
        linestyle="--",
        label="flyweight coupling only",
    )
    impact_accel_ax.plot(
        shift_percent,
        100.0 * grid_base / (grid_base + grid_helix),
        linestyle=":",
        label="helix coupling only",
    )
    impact_accel_ax.axhline(
        100.0,
        linewidth=0.8,
        label="ignore rotational coupling",
    )
    impact_accel_ax.set_xlabel("Engaged shift travel [%]")
    impact_accel_ax.set_ylabel(
        "same-force shift acceleration [% of uncoupled]"
    )
    impact_accel_ax.set_ylim(
        0.0,
        max(105.0, 1.05 * np.max(100.0 * grid_accel_fraction)),
    )
    impact_accel_ax.set_title(
        "Equivalent acceleration penalty from added generalized inertia\n"
        f"At mid-shift, the same generalized force gives only "
        f"{accel_percent_mid:.0f}% of the uncoupled shift acceleration."
    )
    impact_accel_ax.legend(fontsize=8)
    impact_accel_ax.grid(True, alpha=0.25)
    impact_figure.savefig(
        args.output_dir / "00_coupling_impact_at_a_glance.png",
        dpi=180,
    )

    # Context.
    fig1, ax = plt.subplots(figsize=(9.0, 5.0), constrained_layout=True)
    ax.plot(trace.time, primary_rpm, label="primary speed [rpm]")
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Primary speed [rpm]")
    ax2 = ax.twinx()
    ax2.plot(
        trace.time,
        shift_mm,
        linestyle="--",
        label="shift [mm]",
    )
    ax2.set_ylabel("Shift [mm]")
    handles, labels = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(handles + h2, labels + l2)
    ax.grid(True, alpha=0.25)
    ax.set_title("Launch context for coupling-energy diagnostic")
    fig1.savefig(
        args.output_dir / "01_launch_context.png",
        dpi=170,
    )

    # Flyweight.
    fig2, (ax21, ax22) = plt.subplots(
        2,
        1,
        figsize=(9.5, 7.0),
        sharex=True,
        constrained_layout=True,
    )
    ax21.plot(
        trace.time,
        fly_shaft_energy,
        label=r"$\frac{1}{2} J_f\omega_p^2$ shaft mode",
    )
    ax21.plot(
        trace.time,
        fly_pivot_energy,
        label=r"$\frac{1}{2} I_f\dot q_f^2$ pivot mode",
    )
    ax21.plot(
        trace.time,
        fly_total_energy,
        linewidth=2.0,
        label="total flyweight kinetic energy",
    )
    ax21.set_ylabel("Energy [J]")
    ax21.set_title("Fixed-pivot flyweight stored kinetic energy")
    ax21.legend()
    ax21.grid(True, alpha=0.25)

    ax22.plot(
        trace.time,
        fly_config_power_shaft,
        label="J'(x) reaction power on shaft",
    )
    ax22.plot(
        trace.time,
        fly_config_power_axial,
        label="centrifugal configuration power to axial DOF",
    )
    ax22.plot(
        trace.time,
        fly_config_storage_power,
        linestyle="--",
        label="configuration change of shaft-mode energy",
    )
    ax22.plot(
        trace.time,
        fly_pivot_storage_power,
        linestyle=":",
        label="pivot kinetic-energy storage rate",
    )
    ax22.axhline(0.0, linewidth=0.8)
    ax22.set_xlabel("Time [s]")
    ax22.set_ylabel("Power [W]")
    ax22.set_title("Fixed-pivot axial â†” rotational energy exchange")
    ax22.legend(fontsize=8)
    ax22.grid(True, alpha=0.25)
    fig2.savefig(
        args.output_dir / "02_flyweight_energy_flow.png",
        dpi=170,
    )

    # Helix.
    fig3, (ax31, ax32) = plt.subplots(
        2,
        1,
        figsize=(9.5, 7.0),
        sharex=True,
        constrained_layout=True,
    )
    ax31.plot(
        trace.time,
        helix_spring_energy,
        label="torsional spring potential",
    )
    ax31.plot(
        trace.time,
        helix_movable_total_energy,
        label="movable-sheave total rotational KE",
    )
    ax31.plot(
        trace.time,
        helix_base_shaft_energy,
        linestyle="--",
        label=r"base $\frac{1}{2} I_m\omega_s^2$",
    )
    ax31.plot(
        trace.time,
        helix_cross_energy,
        linestyle=":",
        label=r"cross term $I_m\omega_s\dot\theta$",
    )
    ax31.plot(
        trace.time,
        helix_relative_energy,
        linestyle="-.",
        label=r"relative $\frac{1}{2} I_m\dot\theta^2$",
    )
    ax31.set_ylabel("Energy [J]")
    ax31.set_title("Secondary helix energy decomposition")
    ax31.legend(fontsize=8)
    ax31.grid(True, alpha=0.25)

    ax32.plot(
        trace.time,
        helix_spring_power,
        label="torsional spring storage rate",
    )
    ax32.plot(
        trace.time,
        helix_cross_power,
        label="axial/shaft cross-term rate",
    )
    ax32.plot(
        trace.time,
        helix_relative_power,
        label="relative-rotation KE rate",
    )
    ax32.plot(
        trace.time,
        helix_movable_total_power,
        linewidth=2.0,
        label="movable-sheave total KE rate",
    )
    ax32.axhline(0.0, linewidth=0.8)
    ax32.set_xlabel("Time [s]")
    ax32.set_ylabel("Power [W]")
    ax32.set_title("Secondary helix coupling power")
    ax32.legend(fontsize=8)
    ax32.grid(True, alpha=0.25)
    fig3.savefig(
        args.output_dir / "03_secondary_helix_energy_flow.png",
        dpi=170,
    )

    # Mechanism coordinates.
    fig4, ax41 = plt.subplots(
        figsize=(9.0, 5.0),
        constrained_layout=True,
    )
    ax41.plot(
        trace.time,
        np.rad2deg(q),
        label=r"flyweight $q_f$",
    )
    ax41.plot(
        trace.time,
        np.rad2deg(theta),
        label=r"helix relative $\theta$",
    )
    ax41.set_xlabel("Time [s]")
    ax41.set_ylabel("Angle [deg]")
    ax41.set_title("Coupled mechanism coordinates")
    ax41.legend()
    ax41.grid(True, alpha=0.25)
    fig4.savefig(
        args.output_dir / "04_coupling_coordinates.png",
        dpi=170,
    )

    print(f"completed: {result.completed}")
    print(
        "CAD drivetrain: "
        f"PCVT={PCVT_TOTAL_MOI_KG_M2:.8f} kg m^2, "
        f"SCVT={SCVT_TOTAL_MOI_KG_M2:.8f} kg m^2, "
        f"wheels(total)={TOTAL_WHEEL_ROTATIONAL_INERTIA_KG_M2:.6f} kg m^2, "
        f"engine={ENGINE_EQUIVALENT_INERTIA_DEFAULT_KG_M2:.3f} kg m^2"
    )
    print(
        "mid-shift coupling impact: "
        f"base axial={grid_base[mid]:.3f} kg, "
        f"flyweight={grid_fly[mid]:.3f} kg, "
        f"helix={grid_helix[mid]:.3f} kg, "
        f"same-force acceleration={accel_percent_mid:.1f}%"
    )
    print(
        "max flyweight kinetic energy: "
        f"{np.max(fly_total_energy):.6g} J"
    )
    print(
        "max |flyweight centrifugal config power|: "
        f"{np.max(np.abs(fly_config_power_axial)):.6g} W"
    )
    print(
        "secondary helix torsional-energy range: "
        f"{np.min(helix_spring_energy):.6g} .. "
        f"{np.max(helix_spring_energy):.6g} J"
    )
    print(f"Wrote {csv_path}")

    if args.no_show:
        for figure in (
            impact_figure,
            fig1,
            fig2,
            fig3,
            fig4,
        ):
            plt.close(figure)
    else:
        plt.show()


if __name__ == "__main__":
    main()
