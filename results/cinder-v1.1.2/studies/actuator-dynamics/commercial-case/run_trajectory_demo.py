"""OTS-secondary mechanism-transplant trajectory demonstration.

This is intentionally *not* a Sidewinder vehicle reconstruction.

The frozen Baja machine supplies the known primary, belt/pulley geometry,
secondary spring law, engine, final drive, vehicle and road boundary. Only:
  - the secondary helix profile, and
  - the secondary movable-member rotational inertia
are replaced by the provisional OTS Sidewinder/YSR31 estimates.

For each hardware estimate, two mechanically matched models are compared:
  - full dynamic helix;
  - quasi-static helix with the same movable-member absolute rotational inertia
    returned to the rigid secondary-shaft inertia.

A modest screen on the nominal hardware chooses one clean continuous secondary
load transient by a preregistered Pi_s,total rule. The same disturbance is then
replayed on low/nominal/high hardware estimates.
"""

from __future__ import annotations

from dataclasses import replace
import csv
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY_ROOT = HERE.parent
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from study_support import load_tagged_modules, materialize_tagged_upstream, verify_environment, write_rows  # noqa: E402

EXPERIMENTS = STUDY_ROOT / "experiments"
if str(EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTS))

import run_controlled_transients as ct  # noqa: E402
from trajectory_selection import select_demonstration_case  # noqa: E402

from cinder.model.cvt.actuation import HelicalTorqueReactionForce, PulleyActuator  # noqa: E402
from cinder.model.cvt.inertia import ResolvedSecondaryInertia, SecondaryFixedInertia  # noqa: E402
from cinder.model.cvt.profiles import HelixProfile, PiecewiseRamp, linear_helix_segment  # noqa: E402


OUT = HERE / "artifacts" / "trajectory-demo"
DERIVED = HERE / "derived"
INPUTS = HERE / "inputs" / "sidewinder_ysr31_provisional.json"
CONFIG = HERE / "trajectory_demo.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_commercial_derivation() -> dict[str, Any]:
    subprocess.run([sys.executable, str(HERE / "derive_parameters.py")], check=True)
    return load_json(DERIVED / "derived_parameters.json")


def identity_variant(ab, key: str, label: str):
    # dynamic flags True intentionally mean "do not transform this already-built
    # assembly again" inside the frozen tagged ablation runner.
    return ab.AblationVariant(
        key=key,
        label=label,
        dynamic_flyweight=True,
        dynamic_helix=True,
    )


def transplant_full_secondary(
    assembly,
    *,
    movable_inertia: float,
    helix_radius: float,
    helix_angle_deg: float,
):
    opening = float(assembly.geometry.secondary_opening_travel_at_max_shift)
    profile = HelixProfile(
        circumferential_profile=PiecewiseRamp(
            (
                linear_helix_segment(
                    length=opening,
                    helix_angle_degrees=float(helix_angle_deg),
                ),
            )
        ),
        radius=float(helix_radius),
    )

    secondary_pulley = assembly.pulleys.secondary
    old_coupling = secondary_pulley.helical_coupling
    if old_coupling is None:
        raise RuntimeError("Frozen Baja assembly unexpectedly has no secondary helix.")

    new_coupling = replace(old_coupling, profile=profile)
    new_secondary_pulley = replace(
        secondary_pulley,
        helical_coupling=new_coupling,
    )
    new_secondary_inertia = replace(
        assembly.inertias.secondary,
        movable_sheave_rotational_inertia=float(movable_inertia),
    )

    return replace(
        assembly,
        pulleys=replace(
            assembly.pulleys,
            secondary=new_secondary_pulley,
        ),
        inertias=replace(
            assembly.inertias,
            secondary=new_secondary_inertia,
        ),
    )


def make_qs_helix_assembly(ab, full):
    """Remove relative helix dynamics without deleting absolute rotating inertia."""
    laws = []
    count = 0
    for law in full.pulleys.secondary.actuator.force_laws:
        if isinstance(law, HelicalTorqueReactionForce):
            count += 1
            laws.append(ab.QuasiStaticHelicalTorqueReactionForce(spec=law.spec))
        else:
            laws.append(law)
    if count != 1:
        raise RuntimeError(f"Expected one secondary helix law; found {count}.")

    qs_actuator = PulleyActuator(*laws)
    secondary = full.inertias.secondary
    rigid_total = (
        secondary.fixed_side.total
        + secondary.movable_sheave_rotational_inertia
    )
    qs_secondary_inertia = ResolvedSecondaryInertia(
        fixed_side=SecondaryFixedInertia(
            fixed_rotating_hardware_inertia=rigid_total
        ),
        movable_sheave_rotational_inertia=0.0,
    )

    return replace(
        full,
        pulleys=replace(
            full.pulleys,
            secondary=replace(
                full.pulleys.secondary,
                actuator=qs_actuator,
            ),
        ),
        inertias=replace(
            full.inertias,
            secondary=qs_secondary_inertia,
        ),
    )


def find_helix_law(model):
    laws = [
        law for law in model.secondary_actuator.force_laws
        if isinstance(law, HelicalTorqueReactionForce)
    ]
    if len(laws) != 1:
        raise RuntimeError(f"Expected one helix law; found {len(laws)}.")
    return laws[0]


def secondary_dynamic_trace(result, onset_s: float) -> list[dict[str, Any]]:
    """Reconstruct the exact secondary component ratios using the model's own I."""
    model = result.system.cvt.model
    law = find_helix_law(model)
    coupling = model.secondary_helical_coupling
    if coupling is None:
        raise RuntimeError("Secondary helix coupling missing.")
    inertia = float(model.inertias.secondary.movable_sheave_rotational_inertia)
    gain = float(coupling.opening_per_axial_position)

    rows = []
    for sample in result.samples:
        if sample.time < onset_s or sample.closure is None:
            continue

        scoord = sample.geometry.secondary_axial_coordinate
        hk = coupling.evaluate_from_local_coordinate(
            axial_position=scoord.value,
            d_axial_position_ds=scoord.d_value_ds,
            d2_axial_position_ds2=scoord.d2_value_ds2,
        )
        H = gain * float(hk.dtheta_dopening)
        Hprime = gain * gain * float(hk.d2theta_dopening2)

        sdot = float(sample.cvt_state.shift_speed)
        sddot = float(sample.closure.shift_acceleration)
        xdot = float(scoord.d_value_ds) * sdot
        xddot = (
            float(scoord.d_value_ds) * sddot
            + float(scoord.d2_value_ds2) * sdot * sdot
        )

        alpha_s = float(sample.closure.secondary_angular_acceleration)
        tau_s = float(sample.closure.secondary_torque)
        spring_torque = float(law.spec.torsional_stiffness) * (
            float(law.spec.initial_twist) - float(hk.theta)
        )
        tau_qs = (
            float(law.spec.movable_member_torque_fraction) * tau_s
            + spring_torque
        )

        t_omega = inertia * alpha_s
        t_axial = inertia * H * xddot
        t_curvature = inertia * Hprime * xdot * xdot
        t_total = t_omega + t_axial + t_curvature

        denom = abs(tau_qs)
        rows.append(
            {
                "time_s": float(sample.time),
                "tau_secondary_belt_Nm": tau_s,
                "tau_helix_qs_Nm": tau_qs,
                "helix_motion_ratio_rad_per_m": H,
                "helix_motion_ratio_gradient_rad_per_m2": Hprime,
                "secondary_alpha_rad_s2": alpha_s,
                "secondary_axial_speed_m_s": xdot,
                "secondary_axial_acceleration_m_s2": xddot,
                "dynamic_torque_omega_Nm": t_omega,
                "dynamic_torque_axial_Nm": t_axial,
                "dynamic_torque_curvature_Nm": t_curvature,
                "dynamic_torque_total_Nm": t_total,
                "pi_s_omega": abs(t_omega) / denom if denom > 1e-12 else float("nan"),
                "pi_s_axial": abs(t_axial) / denom if denom > 1e-12 else float("nan"),
                "pi_s_curvature": abs(t_curvature) / denom if denom > 1e-12 else float("nan"),
                "pi_s_total": abs(t_total) / denom if denom > 1e-12 else float("nan"),
                "helix_qs_force_N": H * tau_qs,
                "helix_full_force_N": H * (tau_qs - t_total),
                "helix_dynamic_force_correction_N": -H * t_total,
            }
        )
    return rows


def dynamic_summary(trace: list[dict[str, Any]]) -> dict[str, float]:
    if not trace:
        return {
            "peak_pi_total": float("nan"),
            "peak_pi_omega": float("nan"),
            "peak_pi_axial": float("nan"),
            "peak_pi_curvature": float("nan"),
            "minimum_qs_torque_fraction_of_onset": float("nan"),
            "peak_abs_dynamic_helix_force_correction_N": float("nan"),
        }

    onset_mag = abs(float(trace[0]["tau_helix_qs_Nm"]))
    mags = np.asarray([abs(float(r["tau_helix_qs_Nm"])) for r in trace])
    floor = float(np.min(mags) / onset_mag) if onset_mag > 1e-12 else float("nan")

    def peak(key):
        vals = np.asarray(
            [float(r[key]) for r in trace if math.isfinite(float(r[key]))],
            dtype=float,
        )
        return float(np.max(vals)) if vals.size else float("nan")

    return {
        "peak_pi_total": peak("pi_s_total"),
        "peak_pi_omega": peak("pi_s_omega"),
        "peak_pi_axial": peak("pi_s_axial"),
        "peak_pi_curvature": peak("pi_s_curvature"),
        "minimum_qs_torque_fraction_of_onset": floor,
        "peak_abs_dynamic_helix_force_correction_N": peak(
            "helix_dynamic_force_correction_N"
        ),
    }


def final_shift_response_mm(stress, control) -> float:
    ts, ys = ct._series(stress, "shift_mm")
    tc, yc = ct._series(control, "shift_mm")
    end = min(float(ts[-1]), float(tc[-1]))
    return float(np.interp(end, ts, ys) - np.interp(end, tc, yc))


def condition_one(
    ab,
    route,
    variant,
    assembly,
    engine,
    road_load,
    constants,
    *,
    duration_s,
    target_percent,
    rtol,
    atol,
):
    programme = ct.flat_programme(route, duration_s)
    result = ab.run_variant(
        variant=variant,
        full_assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        programme=programme,
        duration_s=duration_s,
        sample_step_s=0.001,
        rtol=rtol,
        atol=atol,
        max_step_s=0.005,
    )
    restart = ct.select_restart(result, target_percent)
    return result, restart


def run_from_restart(
    ab,
    route,
    variant,
    restart,
    *,
    assembly,
    engine,
    road_load,
    constants,
    amplitude,
    ramp_s,
    onset_s,
    hold_s,
    rtol,
    atol,
    sample_step_s,
):
    candidate = ct.Candidate(
        actuator="secondary",
        shift_percent=restart.shift_percent,
        amplitude_Nm=float(amplitude),
        ramp_s=float(ramp_s),
        onset_s=float(onset_s),
        hold_s=float(hold_s),
    )
    result, error = ct.run_from_restart(
        ab,
        route,
        variant,
        restart,
        full_assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        candidate=candidate,
        amplitude_override=None,
        rtol=rtol,
        atol=atol,
        sample_step=sample_step_s,
        screening=False,
    )
    if result is None:
        raise RuntimeError(error)
    return candidate, result


def run_control(
    ab,
    route,
    variant,
    restart,
    *,
    assembly,
    engine,
    road_load,
    constants,
    ramp_s,
    onset_s,
    hold_s,
    rtol,
    atol,
    sample_step_s,
):
    candidate = ct.Candidate(
        actuator="secondary",
        shift_percent=restart.shift_percent,
        amplitude_Nm=0.0,
        ramp_s=float(ramp_s),
        onset_s=float(onset_s),
        hold_s=float(hold_s),
    )
    result, error = ct.run_from_restart(
        ab,
        route,
        variant,
        restart,
        full_assembly=assembly,
        engine=engine,
        road_load=road_load,
        constants=constants,
        candidate=candidate,
        amplitude_override=0.0,
        rtol=rtol,
        atol=atol,
        sample_step=sample_step_s,
        screening=False,
    )
    if result is None:
        raise RuntimeError(error)
    return result


def response_series(stress, control, key: str, grid: np.ndarray) -> np.ndarray:
    ts, ys = ct._series(stress, key)
    tc, yc = ct._series(control, key)
    return np.interp(grid, ts, ys) - np.interp(grid, tc, yc)


def plot_pair_response(full_stress, full_control, qs_stress, qs_control, *, key, ylabel, title, path):
    t_end = min(
        full_stress.hybrid_result.final_time,
        full_control.hybrid_result.final_time,
        qs_stress.hybrid_result.final_time,
        qs_control.hybrid_result.final_time,
    )
    grid = np.linspace(0.0, t_end, 1200)
    full = response_series(full_stress, full_control, key, grid)
    qs = response_series(qs_stress, qs_control, key, grid)

    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    ax.plot(grid, full, label="Full dynamic helix")
    ax.plot(grid, qs, label="Quasi-static helix")
    ax.set_xlabel("Time from restart [s]")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_dynamic_trace(trace, path):
    t = [r["time_s"] for r in trace]
    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    ax.plot(t, [100*r["pi_s_omega"] for r in trace], label=r"$\Pi_{s,\omega}$")
    ax.plot(t, [100*r["pi_s_axial"] for r in trace], label=r"$\Pi_{s,x}$")
    ax.plot(t, [100*r["pi_s_curvature"] for r in trace], label=r"$\Pi_{s,c}$")
    ax.plot(t, [100*r["pi_s_total"] for r in trace], label=r"$\Pi_{s,\mathrm{total}}$")
    ax.set_xlabel("Time from restart [s]")
    ax.set_ylabel("Dynamic correction [% of QS helix reaction]")
    ax.set_title("OTS secondary: naturally generated dynamic helix corrections")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_helix_force(trace, path):
    t = [r["time_s"] for r in trace]
    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    ax.plot(t, [r["helix_qs_force_N"] for r in trace], label="QS helix force on full trajectory")
    ax.plot(t, [r["helix_full_force_N"] for r in trace], label="Dynamic helix force")
    ax.set_xlabel("Time from restart [s]")
    ax.set_ylabel("Helix axial force [N]")
    ax.set_title("OTS secondary: quasi-static vs dynamic helix force")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_uncertainty(rows, metric, ylabel, title, path):
    ordered = [r for level in ("low", "nominal", "high") for r in rows if r["estimate_level"] == level]
    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    ax.plot(
        [r["estimate_level"] for r in ordered],
        [r[metric] for r in ordered],
        marker="o",
    )
    ax.set_xlabel("Commercial mass-property estimate")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> int:
    verify_environment()
    materialize_tagged_upstream(clean=True)
    _, ab, route = load_tagged_modules()

    cfg = load_json(CONFIG)
    derived = ensure_commercial_derivation()
    estimate_by_level = {
        row["estimate_level"]: row for row in derived["estimates"]
    }

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.iterdir():
        if old.is_file():
            old.unlink()
        elif old.is_dir():
            import shutil
            shutil.rmtree(old)

    cond = cfg["conditioning"]
    screen_cfg = cfg["disturbance_screen"]
    screen_solver = cfg["screen_solver"]
    val_solver = cfg["validation_solver"]

    programme = ct.flat_programme(route, float(cond["duration_s"]))
    candidate = route.load_candidate(route.DEFAULT_FIXED_PIVOT_PRESET)
    resolved = route.resolve_primary_preload(
        candidate,
        target_engagement_rpm=2000.0,
        programme=programme,
    )
    baja_assembly, engine, road_load = route.build_components(resolved.constants)

    # --------------------------------------------------------------
    # Screen nominal commercial hardware.
    # --------------------------------------------------------------
    nominal = estimate_by_level[cfg["machine_definition"]["headline_hardware_level"]]
    nominal_full_assembly = transplant_full_secondary(
        baja_assembly,
        movable_inertia=float(nominal["movable_member_polar_inertia_kg_m2"]),
        helix_radius=float(nominal["helix_radius_m"]),
        helix_angle_deg=float(nominal["helix_angle_deg"]),
    )
    nominal_variant = identity_variant(ab, "ots_nominal_full", "OTS nominal — full dynamic helix")
    print("Conditioning nominal OTS-secondary transplant...")
    _, nominal_restart = condition_one(
        ab, route, nominal_variant, nominal_full_assembly,
        engine, road_load, resolved.constants,
        duration_s=float(cond["duration_s"]),
        target_percent=float(cond["target_engaged_shift_percent"]),
        rtol=float(val_solver["relative_tolerance"]),
        atol=float(val_solver["absolute_tolerance"]),
    )
    print(
        f"Restart: target {cond['target_engaged_shift_percent']}%, "
        f"actual {nominal_restart.shift_percent:.3f}% at t={nominal_restart.time_s:.4f}s"
    )

    # Zero controls cached by ramp duration so selection can report whether
    # the perturbation produces a backshift relative to the undisturbed path.
    controls = {}
    screen_rows = []
    amplitudes = [float(x) for x in screen_cfg["added_secondary_torques_Nm"]]
    ramps = [float(x) for x in screen_cfg["ramp_times_s"]]
    total = len(amplitudes) * len(ramps)
    index = 0

    for ramp in ramps:
        controls[ramp] = run_control(
            ab, route, nominal_variant, nominal_restart,
            assembly=nominal_full_assembly,
            engine=engine, road_load=road_load, constants=resolved.constants,
            ramp_s=ramp,
            onset_s=float(screen_cfg["onset_s"]),
            hold_s=float(screen_cfg["hold_s"]),
            rtol=float(screen_solver["relative_tolerance"]),
            atol=float(screen_solver["absolute_tolerance"]),
            sample_step_s=float(screen_solver["sample_step_s"]),
        )

        for amplitude in amplitudes:
            index += 1
            print(f"[screen {index}/{total}] added secondary torque={amplitude:g} N m, ramp={1000*ramp:g} ms")
            try:
                case, stress = run_from_restart(
                    ab, route, nominal_variant, nominal_restart,
                    assembly=nominal_full_assembly,
                    engine=engine, road_load=road_load, constants=resolved.constants,
                    amplitude=amplitude, ramp_s=ramp,
                    onset_s=float(screen_cfg["onset_s"]),
                    hold_s=float(screen_cfg["hold_s"]),
                    rtol=float(screen_solver["relative_tolerance"]),
                    atol=float(screen_solver["absolute_tolerance"]),
                    sample_step_s=float(screen_solver["sample_step_s"]),
                )
                trace = secondary_dynamic_trace(stress, float(screen_cfg["onset_s"]))
                summary = dynamic_summary(trace)
                row = {
                    "status": "completed",
                    "case_id": case.case_id,
                    "added_secondary_torque_Nm": amplitude,
                    "ramp_s": ramp,
                    "restart_shift_percent": nominal_restart.shift_percent,
                    "response_class": ct.response_class(stress, float(screen_cfg["onset_s"])),
                    "final_shift_response_vs_control_mm": final_shift_response_mm(stress, controls[ramp]),
                    **summary,
                }
            except Exception as exc:
                row = {
                    "status": "failed",
                    "added_secondary_torque_Nm": amplitude,
                    "ramp_s": ramp,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            screen_rows.append(row)

    write_rows(OUT / "screen.csv", screen_rows)
    lower, upper = [float(x) for x in screen_cfg["target_peak_pi_total_band"]]
    selected = select_demonstration_case(
        screen_rows,
        target_lower=lower,
        target_upper=upper,
        minimum_denominator_fraction=float(
            screen_cfg["minimum_qs_torque_fraction_of_onset"]
        ),
    )
    (OUT / "selected_case.json").write_text(
        json.dumps(selected, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    if selected["selection_status"] == "no_eligible_clean_case":
        raise RuntimeError(
            "No eligible clean-continuous OTS trajectory case was found. "
            "See screen.csv; no paper-facing trajectory was manufactured."
        )

    chosen_amp = float(selected["added_secondary_torque_Nm"])
    chosen_ramp = float(selected["ramp_s"])
    print(
        f"Selected {selected['selection_status']}: "
        f"{chosen_amp:g} N m over {1000*chosen_ramp:g} ms, "
        f"peak Pi={100*float(selected['peak_pi_total']):.3f}%"
    )

    # --------------------------------------------------------------
    # Validate identical selected disturbance over low/nominal/high.
    # --------------------------------------------------------------
    validation_rows = []
    headline_results = None
    for level in cfg["machine_definition"]["uncertainty_levels"]:
        estimate = estimate_by_level[level]
        full_assembly = transplant_full_secondary(
            baja_assembly,
            movable_inertia=float(estimate["movable_member_polar_inertia_kg_m2"]),
            helix_radius=float(estimate["helix_radius_m"]),
            helix_angle_deg=float(estimate["helix_angle_deg"]),
        )
        qs_assembly = make_qs_helix_assembly(ab, full_assembly)

        full_variant = identity_variant(ab, f"ots_{level}_full", f"OTS {level} — full dynamic helix")
        qs_variant = identity_variant(ab, f"ots_{level}_qs", f"OTS {level} — quasi-static helix")

        print(f"Conditioning {level} full and QS comparators...")
        _, full_restart = condition_one(
            ab, route, full_variant, full_assembly,
            engine, road_load, resolved.constants,
            duration_s=float(cond["duration_s"]),
            target_percent=float(cond["target_engaged_shift_percent"]),
            rtol=float(val_solver["relative_tolerance"]),
            atol=float(val_solver["absolute_tolerance"]),
        )
        _, qs_restart = condition_one(
            ab, route, qs_variant, qs_assembly,
            engine, road_load, resolved.constants,
            duration_s=float(cond["duration_s"]),
            target_percent=float(cond["target_engaged_shift_percent"]),
            rtol=float(val_solver["relative_tolerance"]),
            atol=float(val_solver["absolute_tolerance"]),
        )

        full_control = run_control(
            ab, route, full_variant, full_restart,
            assembly=full_assembly,
            engine=engine, road_load=road_load, constants=resolved.constants,
            ramp_s=chosen_ramp, onset_s=float(screen_cfg["onset_s"]),
            hold_s=float(screen_cfg["hold_s"]),
            rtol=float(val_solver["relative_tolerance"]),
            atol=float(val_solver["absolute_tolerance"]),
            sample_step_s=float(val_solver["sample_step_s"]),
        )
        _, full_stress = run_from_restart(
            ab, route, full_variant, full_restart,
            assembly=full_assembly,
            engine=engine, road_load=road_load, constants=resolved.constants,
            amplitude=chosen_amp, ramp_s=chosen_ramp,
            onset_s=float(screen_cfg["onset_s"]),
            hold_s=float(screen_cfg["hold_s"]),
            rtol=float(val_solver["relative_tolerance"]),
            atol=float(val_solver["absolute_tolerance"]),
            sample_step_s=float(val_solver["sample_step_s"]),
        )
        qs_control = run_control(
            ab, route, qs_variant, qs_restart,
            assembly=qs_assembly,
            engine=engine, road_load=road_load, constants=resolved.constants,
            ramp_s=chosen_ramp, onset_s=float(screen_cfg["onset_s"]),
            hold_s=float(screen_cfg["hold_s"]),
            rtol=float(val_solver["relative_tolerance"]),
            atol=float(val_solver["absolute_tolerance"]),
            sample_step_s=float(val_solver["sample_step_s"]),
        )
        _, qs_stress = run_from_restart(
            ab, route, qs_variant, qs_restart,
            assembly=qs_assembly,
            engine=engine, road_load=road_load, constants=resolved.constants,
            amplitude=chosen_amp, ramp_s=chosen_ramp,
            onset_s=float(screen_cfg["onset_s"]),
            hold_s=float(screen_cfg["hold_s"]),
            rtol=float(val_solver["relative_tolerance"]),
            atol=float(val_solver["absolute_tolerance"]),
            sample_step_s=float(val_solver["sample_step_s"]),
        )

        trace = secondary_dynamic_trace(full_stress, float(screen_cfg["onset_s"]))
        dsum = dynamic_summary(trace)
        metrics = ct.paired_metric(
            full_stress, full_control, qs_stress, qs_control,
            onset=float(screen_cfg["onset_s"]),
            sample_step=float(val_solver["sample_step_s"]),
        )
        row = {
            "estimate_level": level,
            "movable_member_inertia_kg_m2": float(estimate["movable_member_polar_inertia_kg_m2"]),
            "helix_radius_m": float(estimate["helix_radius_m"]),
            "helix_angle_deg": float(estimate["helix_angle_deg"]),
            "reflected_axial_inertia_kg": float(estimate["reflected_axial_inertia_kg"]),
            "relative_to_baja_reflected_axial_inertia": float(
                estimate["relative_to_baja_reflected_axial_inertia"]
            ),
            "added_secondary_torque_Nm": chosen_amp,
            "ramp_s": chosen_ramp,
            "full_response_class": ct.response_class(full_stress, float(screen_cfg["onset_s"])),
            "qs_response_class": ct.response_class(qs_stress, float(screen_cfg["onset_s"])),
            "full_restart_shift_percent": full_restart.shift_percent,
            "qs_restart_shift_percent": qs_restart.shift_percent,
            **dsum,
            **metrics,
        }
        validation_rows.append(row)

        case_dir = OUT / level
        case_dir.mkdir(parents=True, exist_ok=True)
        write_rows(case_dir / "full_dynamic_component_trace.csv", trace)

        # Save raw sampled rows from all four integrations.
        raw_rows = []
        for role, result in (
            ("full_stress", full_stress),
            ("full_control", full_control),
            ("qs_stress", qs_stress),
            ("qs_control", qs_control),
        ):
            for sample in result.samples:
                rr = dict(sample.row)
                rr["run_role"] = role
                raw_rows.append(rr)
        write_rows(case_dir / "trajectory_samples.csv", raw_rows)

        if level == cfg["machine_definition"]["headline_hardware_level"]:
            headline_results = (
                full_stress, full_control, qs_stress, qs_control, trace
            )

    write_rows(OUT / "validation_summary.csv", validation_rows)

    if headline_results is not None:
        fs, fc, qs, qc, trace = headline_results
        plot_pair_response(
            fs, fc, qs, qc,
            key="shift_mm",
            ylabel="Perturbation-induced shift response [mm]",
            title="OTS-secondary transplant: dynamic vs quasi-static shift response",
            path=OUT / "nominal_shift_response.png",
        )
        plot_pair_response(
            fs, fc, qs, qc,
            key="primary_rpm",
            ylabel="Perturbation-induced primary-speed response [rpm]",
            title="OTS-secondary transplant: dynamic vs quasi-static primary response",
            path=OUT / "nominal_primary_speed_response.png",
        )
        plot_pair_response(
            fs, fc, qs, qc,
            key="secondary_rpm",
            ylabel="Perturbation-induced secondary-speed response [rpm]",
            title="OTS-secondary transplant: dynamic vs quasi-static secondary response",
            path=OUT / "nominal_secondary_speed_response.png",
        )
        plot_dynamic_trace(trace, OUT / "nominal_dynamic_components.png")
        plot_helix_force(trace, OUT / "nominal_helix_force.png")

    plot_uncertainty(
        validation_rows,
        "max_abs_paired_delta_shift_mm",
        "Max dynamic-vs-QS perturbation-response difference [mm]",
        "OTS-secondary trajectory sensitivity to provisional hardware estimate",
        OUT / "uncertainty_shift_difference.png",
    )
    plot_uncertainty(
        validation_rows,
        "max_abs_paired_delta_primary_rpm",
        "Max dynamic-vs-QS perturbation-response difference [rpm]",
        "OTS-secondary primary-speed consequence vs hardware estimate",
        OUT / "uncertainty_primary_speed_difference.png",
    )

    payload = {
        "status": "complete",
        "study_type": "mechanism-transplant trajectory demonstration",
        "not_a_sidewinder_reconstruction": True,
        "selection": selected,
        "validation": validation_rows,
        "machine_definition": cfg["machine_definition"],
        "interpretation_boundaries": cfg["interpretation_boundaries"],
    }
    (OUT / "summary.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# OTS-secondary trajectory demonstration",
        "",
        f"Selection status: **{selected['selection_status']}**",
        "",
        f"- selected added secondary torque: `{chosen_amp:g} N m`",
        f"- selected ramp duration: `{1000*chosen_ramp:g} ms`",
        f"- screen peak Pi_s,total: `{100*float(selected['peak_pi_total']):.4g}%`",
        "",
        "The selected disturbance is replayed without change on low/nominal/high "
        "commercial mass-property estimates. The full-dynamic and quasi-static "
        "models retain identical absolute secondary rotating inertia; only relative "
        "helix dynamics are removed in the QS comparator.",
        "",
        "| estimate | peak Pi total | max shift-response difference | max primary-rpm difference |",
        "|---|---:|---:|---:|",
    ]
    for row in validation_rows:
        lines.append(
            f"| {row['estimate_level']} | "
            f"{100*float(row['peak_pi_total']):.3g}% | "
            f"{float(row['max_abs_paired_delta_shift_mm']):.4g} mm | "
            f"{float(row['max_abs_paired_delta_primary_rpm']):.4g} rpm |"
        )
    lines += [
        "",
        "Interpretation boundary: this demonstrates the system-level consequence of "
        "transplanting a physically anchored commercial-secondary inertia/helix scale "
        "into the otherwise frozen reference machine. It is not a prediction of an "
        "actual Yamaha Sidewinder trajectory.",
        "",
    ]
    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Trajectory demonstration complete: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
