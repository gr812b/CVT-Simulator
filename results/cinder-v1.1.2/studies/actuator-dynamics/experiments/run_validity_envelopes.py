"""Equation-derived quasi-static validity envelopes for both actuator couplings.

No arbitrary hardware scaling is used. The exact dynamic force correction is
normalized by the corresponding quasi-static mechanism force:

    Pi_fw = |Delta F_fw,dyn| / |F_fw,QS|
    Pi_h  = |Delta F_h,dyn|  / |F_h,QS|

For the helix, dtheta/dx cancels exactly, leaving an especially transparent
ratio of inertial torque to quasi-static reacted torque.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY_ROOT = HERE.parent
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from study_support import ARTIFACTS, load_json, load_tagged_modules, verify_environment, write_rows  # noqa: E402


def _find_one(actuator, cls):
    matches = [law for law in actuator.force_laws if isinstance(law, cls)]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {cls.__name__}; found {len(matches)}.")
    return matches[0]


def _build_baseline():
    _, ab, route = load_tagged_modules()
    preset = route.DEFAULT_FIXED_PIVOT_PRESET
    candidate = route.load_candidate(preset)
    programme, _ = ab.programme_for_scenario("launch", 10.0)
    resolved = route.resolve_primary_preload(
        candidate,
        target_engagement_rpm=2000.0,
        programme=programme,
    )
    assembly, engine, road = route.build_components(resolved.constants)
    model = __import__("cinder.model.system", fromlist=["MechanicalCVTPlant"]).MechanicalCVTPlant.from_assembly(assembly)
    return ab, route, resolved, model


def main() -> int:
    verify_environment()
    spec = load_json(STUDY_ROOT / "study.json")
    cfg = spec["experiments"]["validity_envelopes"]
    out = ARTIFACTS / "validity-envelopes"
    out.mkdir(parents=True, exist_ok=True)

    ab, route, resolved, model = _build_baseline()
    from cinder.model.cvt.actuation import FixedPivotFlyweightForce, HelicalTorqueReactionForce

    fly = _find_one(model.primary_actuator, FixedPivotFlyweightForce)
    helix = _find_one(model.secondary_actuator, HelicalTorqueReactionForce)
    coupling = model.secondary_helical_coupling
    if coupling is None:
        raise RuntimeError("Secondary helical coupling missing.")

    geom_spec = model.geometry.spec
    span = geom_spec.max_shift - geom_spec.deadzone_shift
    thresholds = [float(x) for x in cfg["threshold_fractions"]]

    # ------------------------------------------------------------------
    # Primary: exact acceleration-only and curvature-only thresholds.
    # ------------------------------------------------------------------
    rpm_grid = np.linspace(
        float(cfg["primary_rpm_range"][0]),
        float(cfg["primary_rpm_range"][1]),
        int(cfg["primary_rpm_samples"]),
    )
    primary_rows = []

    for pct in cfg["shift_percent_samples"]:
        s = geom_spec.deadzone_shift + (float(pct) / 100.0) * span
        geometry = model.geometry.evaluate_engaged(float(s))
        pcoord = geometry.primary_axial_coordinate
        fw = fly.spec.mechanism_map.evaluate(pcoord.value)
        qx = fw.angle_gradient
        qxx = fw.angle_curvature
        inertia = fw.pivot_inertia

        for rpm in rpm_grid:
            omega = rpm * 2.0 * math.pi / 60.0
            f_qs = 0.5 * omega**2 * fw.shaft_inertia_gradient
            row = {
                "shift_percent": float(pct),
                "shift_m": float(s),
                "primary_rpm": float(rpm),
                "omega_primary_rad_s": float(omega),
                "flyweight_q_rad": float(fw.angle),
                "flyweight_qx_rad_per_m": float(qx),
                "flyweight_qxx_rad_per_m2": float(qxx),
                "flyweight_pivot_inertia_kg_m2": float(inertia),
                "flyweight_shaft_inertia_gradient_kg_m": float(fw.shaft_inertia_gradient),
                "quasi_static_flyweight_force_N": float(f_qs),
            }
            for eps in thresholds:
                key = f"{100*eps:g}pct"
                denom_a = inertia * qx**2
                row[f"shift_acceleration_for_{key}_correction_m_s2"] = (
                    eps * abs(f_qs) / denom_a if denom_a > 0.0 else float("nan")
                )
                denom_v = inertia * abs(qx * qxx)
                row[f"shift_speed_for_{key}_curvature_correction_m_s"] = (
                    math.sqrt(eps * abs(f_qs) / denom_v)
                    if denom_v > 0.0
                    else float("inf")
                )
            primary_rows.append(row)

    write_rows(out / "primary_validity_thresholds.csv", primary_rows)

    # Figure: acceleration-only threshold for all levels and positions.
    for eps in thresholds:
        fig, ax = plt.subplots(figsize=(8.8, 5.6))
        key = f"shift_acceleration_for_{100*eps:g}pct_correction_m_s2"
        for pct in cfg["shift_percent_samples"]:
            rows = [r for r in primary_rows if r["shift_percent"] == float(pct)]
            ax.plot(
                [r["primary_rpm"] for r in rows],
                [r[key] for r in rows],
                label=f"{pct:g}% engaged shift",
            )
        ax.set_xlabel("Primary speed [rpm]")
        ax.set_ylabel(r"Required $|\ddot{x}_p|$ [m/s$^2$]")
        ax.set_title(
            f"Primary flyweight: acceleration producing {100*eps:g}% dynamic force correction"
        )
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out / f"primary_acceleration_{100*eps:g}pct_threshold.png", dpi=180)
        plt.close(fig)

    # One curvature-speed figure at all thresholds, midshift, plus CSV retains all states.
    mid_pct = min(cfg["shift_percent_samples"], key=lambda x: abs(float(x) - 50.0))
    mid = [r for r in primary_rows if r["shift_percent"] == float(mid_pct)]
    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    for eps in thresholds:
        key = f"shift_speed_for_{100*eps:g}pct_curvature_correction_m_s"
        ax.plot(
            [r["primary_rpm"] for r in mid],
            [1000.0*r[key] for r in mid],
            label=f"{100*eps:g}% correction",
        )
    ax.set_xlabel("Primary speed [rpm]")
    ax.set_ylabel(r"Required $|\dot{x}_p|$ [mm/s]")
    ax.set_title(f"Primary flyweight curvature term: quasi-static validity at {mid_pct:g}% shift")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "primary_curvature_speed_thresholds_midshift.png", dpi=180)
    plt.close(fig)

    # ------------------------------------------------------------------
    # Secondary: exact angular-acceleration threshold.
    #
    # Pi_h = I_M |alpha_s + theta_ddot| /
    #        |f tau_s + k(theta_pre-theta)|
    #
    # dtheta/dx cancels exactly.
    # ------------------------------------------------------------------
    tau_grid = np.linspace(
        float(cfg["secondary_belt_torque_range_Nm"][0]),
        float(cfg["secondary_belt_torque_range_Nm"][1]),
        int(cfg["secondary_belt_torque_samples"]),
    )
    I_M = model.inertias.secondary.movable_sheave_rotational_inertia
    secondary_rows = []

    for pct in cfg["shift_percent_samples"]:
        s = geom_spec.deadzone_shift + (float(pct) / 100.0) * span
        geometry = model.geometry.evaluate_engaged(float(s))
        scoord = geometry.secondary_axial_coordinate
        hk = coupling.evaluate_from_local_coordinate(
            axial_position=scoord.value,
            d_axial_position_ds=scoord.d_value_ds,
            d2_axial_position_ds2=scoord.d2_value_ds2,
        )
        spring_torque = helix.spec.torsional_stiffness * (
            helix.spec.initial_twist - hk.theta
        )
        f = helix.spec.movable_member_torque_fraction

        for tau in tau_grid:
            t_qs = f * float(tau) + spring_torque
            row = {
                "shift_percent": float(pct),
                "shift_m": float(s),
                "secondary_belt_torque_Nm": float(tau),
                "helix_theta_rad": float(hk.theta),
                "helix_dtheta_ds_rad_per_m": float(hk.dtheta_ds),
                "helix_d2theta_ds2_rad_per_m2": float(hk.d2theta_ds2),
                "torsional_spring_reaction_torque_Nm": float(spring_torque),
                "movable_member_torque_fraction": float(f),
                "quasi_static_reacted_torque_Nm": float(t_qs),
                "movable_member_inertia_kg_m2": float(I_M),
            }
            for eps in thresholds:
                key = f"{100*eps:g}pct"
                row[f"movable_angular_acceleration_for_{key}_correction_rad_s2"] = (
                    eps * abs(t_qs) / I_M if I_M > 0.0 else float("inf")
                )
            secondary_rows.append(row)

    write_rows(out / "secondary_validity_thresholds.csv", secondary_rows)

    for eps in thresholds:
        fig, ax = plt.subplots(figsize=(8.8, 5.6))
        key = f"movable_angular_acceleration_for_{100*eps:g}pct_correction_rad_s2"
        for pct in cfg["shift_percent_samples"]:
            rows = [r for r in secondary_rows if r["shift_percent"] == float(pct)]
            ax.plot(
                [r["secondary_belt_torque_Nm"] for r in rows],
                [r[key] for r in rows],
                label=f"{pct:g}% engaged shift",
            )
        ax.set_xlabel(r"Secondary belt torque $\tau_s$ [N m]")
        ax.set_ylabel(
            r"Required $|\alpha_s+\ddot{\theta}|$ [rad/s$^2$]"
        )
        ax.set_title(
            f"Secondary helix: movable-member acceleration producing {100*eps:g}% correction"
        )
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out / f"secondary_acceleration_{100*eps:g}pct_threshold.png", dpi=180)
        plt.close(fig)

    metadata = {
        "primary_measure": spec["dimensionless_measures"]["primary"],
        "secondary_measure": spec["dimensionless_measures"]["secondary"],
        "interpretation": {
            "primary": (
                "Acceleration and curvature thresholds are shown separately because their "
                "signed contributions can reinforce or cancel on a real trajectory."
            ),
            "secondary": (
                "The helix motion-ratio multiplier cancels from the fractional force correction. "
                "Geometry still enters through theta, theta_ddot, and the torsional spring state."
            ),
        },
        "resolved_baseline_constants": {
            "secondary_movable_inertia_kg_m2": float(I_M),
            "release": "cinder-v1.1.2",
        },
    }
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Wrote equation-derived validity envelopes to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
