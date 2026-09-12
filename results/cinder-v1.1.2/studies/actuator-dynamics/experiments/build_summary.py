from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY_ROOT = HERE.parent
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from study_support import ARTIFACTS, load_json, read_rows


def f(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):
        return None


def arr(rows,key,pred=None):
    out=[]
    for r in rows:
        if pred and not pred(r): continue
        x=f(r.get(key))
        if x is not None: out.append(x)
    return np.asarray(out,dtype=float)


def main():
    spec=load_json(STUDY_ROOT/"study.json")
    base=ARTIFACTS/"baseline-ablation"
    direct=read_rows(base/"direct_clamp_on_full_trajectory.csv")
    traj=read_rows(base/"trajectory_diagnostics.csv")
    masses=read_rows(base/"effective_mass_map.csv")
    variants=read_rows(base/"summary.csv")
    coupling=read_rows(ARTIFACTS/"coupling-energy"/"coupling_energy_flow.csv")
    controlled_path=ARTIFACTS/"controlled-transients"/"summary.json"
    controlled=json.loads(controlled_path.read_text()) if controlled_path.is_file() else None
    components_dir=ARTIFACTS/"dimensionless-components"
    components_all_path=components_dir/"summary_all.json"
    components_post_path=components_dir/"summary_post_capture.json"
    components_all=json.loads(components_all_path.read_text()) if components_all_path.is_file() else None
    components_post=json.loads(components_post_path.read_text()) if components_post_path.is_file() else None
    commercial_path=STUDY_ROOT/"commercial-case"/"artifacts"/"summary.json"
    commercial=json.loads(commercial_path.read_text()) if commercial_path.is_file() else None

    t0=float(spec["experiments"]["baseline_ablation"]["post_capture_report_start_s"])
    post=lambda r: f(r.get("time_s")) is not None and float(r["time_s"])>=t0

    def ratio_stats(num,den,pred=None):
        values=[]
        for r in direct:
            if pred and not pred(r): continue
            n=f(r.get(num)); d=f(r.get(den))
            if n is not None and d is not None and abs(d)>1e-9:
                values.append(abs(n/d))
        a=np.asarray(values)
        return {
            "max": float(np.max(a)) if a.size else None,
            "p99": float(np.percentile(a,99)) if a.size else None,
            "median": float(np.median(a)) if a.size else None,
        }

    headline={
        "baseline_dynamic_numbers": {
            "primary_all": ratio_stats("fly_dynamic_total_correction_N","fly_qs_centrifugal_force_N"),
            "primary_post_capture": ratio_stats("fly_dynamic_total_correction_N","fly_qs_centrifugal_force_N",post),
            "secondary_all": ratio_stats("helix_dynamic_total_correction_N","helix_qs_reaction_force_N"),
            "secondary_post_capture": ratio_stats("helix_dynamic_total_correction_N","helix_qs_reaction_force_N",post),
        },
        "total_clamp_corrections": {
            "primary_peak_all_N": float(np.max(np.abs(arr(direct,"primary_dynamic_correction_to_total_clamp_N")))),
            "primary_peak_post_capture_N": float(np.max(np.abs(arr(direct,"primary_dynamic_correction_to_total_clamp_N",post)))),
            "secondary_peak_all_N": float(np.max(np.abs(arr(direct,"secondary_dynamic_correction_to_total_clamp_N")))),
            "secondary_peak_post_capture_N": float(np.max(np.abs(arr(direct,"secondary_dynamic_correction_to_total_clamp_N",post)))),
        },
        "energy_and_inertia": {
            "flyweight_pivot_energy_peak_J": float(np.max(arr(coupling,"flyweight_pivot_energy_J"))),
            "flyweight_config_power_peak_abs_W": float(np.max(np.abs(arr(coupling,"flyweight_config_power_to_axial_W"))),
            ),
            "helix_cross_energy_peak_abs_J": float(np.max(np.abs(arr(coupling,"secondary_helix_cross_energy_J"))),
            ),
            "helix_relative_energy_peak_J": float(np.max(arr(coupling,"secondary_helix_relative_energy_J")),
            ),
            "helix_reflected_shift_mass_peak_kg": float(np.max(arr(coupling,"helix_reflected_shift_mass_kg")),
            ),
        },
    }

    payload={
        "study": spec["study"],
        "cinder_version": spec["cinder_version"],
        "headline": headline,
        "baseline_variants": variants,
        "component_dynamic_numbers": {"all": components_all, "post_capture": components_post},
        "commercial_secondary": commercial,
        "controlled_transients": controlled,
        "interpretation_notes": [
            (
                "The global baseline maxima occur during the initial engagement/capture transient. "
                f"Post-capture statistics are reported separately for t >= {t0:.2f} s."
            ),
            (
                "The component Pi metrics normalize each retained actuator correction by the corresponding "
                "quasi-static mechanism force. Secondary shaft, axial-reflection and curvature components "
                "are reported separately so cancellation or reinforcement is visible."
            ),
            (
                "The large direct helix generalized shift-mass contribution is not by itself a "
                "trajectory-error metric because the shaft and shift coordinates are coupled. "
                "Independent ablation trajectories and controlled-transient response differences "
                "are the consequence metrics."
            ),
        ],
    }
    (ARTIFACTS/"summary.json").write_text(json.dumps(payload,indent=2,allow_nan=False)+"\n")

    p=headline["baseline_dynamic_numbers"]
    lines=[
        "# CINDER 1.1.2 actuator-dynamics — official study summary",
        "",
        "## Baseline dimensionless actuator corrections",
        "",
        f"- primary flyweight max Pi_fw (all): `{p['primary_all']['max']:.6g}`",
        f"- primary flyweight max Pi_fw after {t0:.2f} s: `{p['primary_post_capture']['max']:.6g}`",
        f"- secondary helix max Pi_h (all): `{p['secondary_all']['max']:.6g}`",
        f"- secondary helix max Pi_h after {t0:.2f} s: `{p['secondary_post_capture']['max']:.6g}`",
        "",
        "The all-time peaks include the rigid engagement/capture transient. The post-capture "
        "values characterize ordinary continuous operation in the baseline launch.",
        "",
        "## Study logic",
        "",
        "1. baseline ablation quantifies actual Baja consequence;",
        "2. component Pi metrics separate the individual dynamic terms;",
        "3. coupling-energy decomposition explains the retained mechanisms;",
        "4. equation-derived validity envelopes define quasi-static departure directly;",
        "5. the source-registered commercial secondary anchors machine generality;",
        "6. controlled torque-ramp cases map achieved dynamic number to trajectory consequence.",
        "",
    ]
    if commercial is not None:
        nom=[r for r in commercial.get("angle_sensitivity",[]) if r.get("estimate_level")=="high" and float(r.get("helix_angle_deg",0))==28.0]
        lines += [
            "## Provisional commercial-secondary scaling",
            "",
            "- hardware anchor: Yamaha Sidewinder YSRC + Dalton YSR31;",
        ]
        if nom:
            lines.append(f"- high-estimate local YSR36/28 28-degree segment reflected inertia: `{nom[0]['relative_to_baja_reflected_axial_inertia']:.3g}x Baja`.")
        lines.append("")
    if controlled is not None:
        lines += [
            "## Controlled-transient status",
            "",
            f"- screened candidates: `{controlled['screen_candidate_count']}`",
            f"- completed screens: `{controlled['completed_screen_count']}`",
            f"- clean-continuous candidates: `{controlled['clean_continuous_count']}`",
            "",
        ]
    (ARTIFACTS/"summary.md").write_text("\n".join(lines),encoding="utf-8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
