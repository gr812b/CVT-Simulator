"""E1: map the quasi-static selected-flank zero-reaction boundary."""
from __future__ import annotations

import json
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

from study_support import (  # noqa: E402
    ARTIFACTS,
    build_reference_components,
    load_json,
    load_tagged_modules,
    verify_environment,
    write_reference_provenance,
    write_rows,
)


def main() -> int:
    verify_environment()
    _, _ab, route = load_tagged_modules()
    cfg = load_json(STUDY_ROOT / "study.json")["experiments"]["reaction_map"]

    _, resolved, assembly, _engine, _road_load = build_reference_components(
        route, duration_s=1.0
    )

    from cinder.model.cvt.actuation import HelicalTorqueReactionForce
    from cinder.model.system import MechanicalCVTPlant
    from support.reference_model import use_slotted_secondary_helix

    plant = MechanicalCVTPlant.from_assembly(assembly)
    use_slotted_secondary_helix(plant)
    laws = [
        law for law in plant.secondary_actuator.force_laws
        if isinstance(law, HelicalTorqueReactionForce)
    ]
    if len(laws) != 1:
        raise RuntimeError(f"Expected one secondary helix law; found {len(laws)}")
    helix = laws[0]
    coupling = plant.secondary_helical_coupling
    if coupling is None:
        raise RuntimeError("Secondary helical coupling is missing")

    spec = plant.geometry.spec
    shifts = np.linspace(
        spec.deadzone_shift,
        spec.max_shift,
        int(cfg["shift_percent_samples"]),
    )
    torque_lo, torque_hi = map(float, cfg["secondary_belt_torque_range_Nm"])
    torques = np.linspace(torque_lo, torque_hi, int(cfg["secondary_belt_torque_samples"]))

    boundary_rows = []
    grid_rows = []
    span = spec.max_shift - spec.deadzone_shift
    fraction = float(helix.spec.movable_member_torque_fraction)
    if fraction == 0.0:
        raise RuntimeError("Cannot define a torque zero-boundary with zero movable-member torque fraction")

    for shift in shifts:
        geometry = plant.geometry.evaluate_engaged(float(shift))
        scoord = geometry.secondary_axial_coordinate
        hk = coupling.evaluate_from_local_coordinate(
            axial_position=scoord.value,
            d_axial_position_ds=scoord.d_value_ds,
            d2_axial_position_ds2=scoord.d2_value_ds2,
        )
        spring_torque = helix.spec.torsional_stiffness * (
            helix.spec.initial_twist - hk.theta
        )
        zero_torque = -spring_torque / fraction
        motion_ratio = hk.dtheta_dopening * coupling.opening_per_axial_position
        shift_percent = 100.0 * (float(shift) - spec.deadzone_shift) / span
        boundary_rows.append(
            {
                "shift_percent": shift_percent,
                "shift_m": float(shift),
                "shift_mm": 1000.0 * float(shift),
                "secondary_axial_position_m": scoord.value,
                "helix_theta_rad": hk.theta,
                "helix_motion_ratio_rad_per_m": motion_ratio,
                "helix_torsional_spring_torque_Nm": spring_torque,
                "movable_member_torque_fraction": fraction,
                "zero_margin_secondary_belt_torque_Nm": zero_torque,
            }
        )
        for tau_s in torques:
            margin = fraction * float(tau_s) + spring_torque
            grid_rows.append(
                {
                    "shift_percent": shift_percent,
                    "shift_m": float(shift),
                    "secondary_belt_torque_Nm": float(tau_s),
                    "helix_reacted_torque_margin_Nm": margin,
                    "helix_axial_force_N": margin * motion_ratio,
                    "opposite_flank_required": int(margin < 0.0),
                }
            )

    out = ARTIFACTS / "reaction-map"
    out.mkdir(parents=True, exist_ok=True)
    write_rows(out / "zero_boundary.csv", boundary_rows)
    write_rows(out / "reaction_grid.csv", grid_rows)

    zero_values = np.asarray(
        [r["zero_margin_secondary_belt_torque_Nm"] for r in boundary_rows],
        dtype=float,
    )
    summary = {
        "stage": "E1",
        "interpretation": "quasi-static geometry/spring contact boundary; not a vehicle simulation",
        "zero_boundary_secondary_belt_torque_min_Nm": float(np.min(zero_values)),
        "zero_boundary_secondary_belt_torque_max_Nm": float(np.max(zero_values)),
        "zero_boundary_secondary_belt_torque_at_low_shift_Nm": float(zero_values[0]),
        "zero_boundary_secondary_belt_torque_at_high_shift_Nm": float(zero_values[-1]),
        "resolved_primary_preload_mm": float(resolved.resolved_primary_preload_mm),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.plot(
        [r["shift_percent"] for r in boundary_rows],
        zero_values,
        linewidth=2.0,
    )
    ax.axhline(0.0, linewidth=1.0)
    ax.set_xlabel("Engaged shift position [%]")
    ax.set_ylabel("Secondary belt torque at $M_h=0$ [N m]")
    ax.set_title("Helix selected-flank zero-reaction boundary")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out / "zero_boundary_vs_shift.png", dpi=180)
    plt.close(fig)

    matrix = np.asarray(
        [r["helix_reacted_torque_margin_Nm"] for r in grid_rows], dtype=float
    ).reshape(len(shifts), len(torques))
    fig, ax = plt.subplots(figsize=(8.0, 5.2))
    image = ax.imshow(
        matrix,
        origin="lower",
        aspect="auto",
        extent=(torques[0], torques[-1], 0.0, 100.0),
    )
    ax.contour(
        torques,
        np.linspace(0.0, 100.0, len(shifts)),
        matrix,
        levels=[0.0],
        linewidths=2.0,
    )
    ax.set_xlabel("Secondary belt torque $\\tau_s$ [N m]")
    ax.set_ylabel("Engaged shift position [%]")
    ax.set_title("Quasi-static reacted torque margin $M_h$")
    fig.colorbar(image, ax=ax, label="$M_h$ [N m]")
    fig.tight_layout()
    fig.savefig(out / "reaction_margin_map.png", dpi=180)
    plt.close(fig)

    write_reference_provenance(
        out / "provenance",
        plant=plant,
        extra={
            "study_stage": "E1_reaction_map",
            "dynamic_terms": "zero",
            "contact_quantity": "helix reacted torque margin M_h",
        },
    )
    print(f"Wrote E1 reaction map to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
