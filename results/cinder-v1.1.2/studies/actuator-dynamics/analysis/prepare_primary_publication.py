"""Derive compact, hashed plot inputs and checks from the primary raw runs."""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

STUDY = Path(__file__).resolve().parents[1]


def rows(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as f:
        return list(csv.DictReader(f))


def col(data, key):
    return np.array([float(r[key]) for r in data])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, default=STUDY/"artifacts/primary-publication")
    p.add_argument("--output-dir", type=Path, default=STUDY/"publication_inputs")
    args = p.parse_args()
    out = args.output_dir; out.mkdir(parents=True, exist_ok=True)
    arrays, checks, data = {}, {}, {}
    reference=json.loads((STUDY.parents[1]/'defaults/baja/simulation_case.json').read_text())['assembly']
    mu_static=reference['contact']['static_friction_coefficient']
    beta=reference['geometry']['sheave_half_angle_rad']
    translating_mass=reference['inertias']['primary']['moving_sheave_mass_kg']
    for path in sorted(args.raw_dir.rglob("trajectory.csv.gz")):
        name = "_".join(path.relative_to(args.raw_dir).parts[:-1])
        d = rows(path); data[name] = d
        for k in ["time_s", "segment_index", "shift_mm", "shift_speed_mm_s", "primary_rpm",
                  "fly_dynamic_total_correction_N", "fly_qs_centrifugal_force_N",
                  "primary_actuator_closing_force_N", "fly_dynamic_axial_inertia_force_N",
                  "fly_dynamic_curvature_force_N", "rhs_shift_acceleration_m_s2"]:
            arrays[f"{name}__{k}"] = col(d, k)
        f = col(d, "fly_dynamic_total_correction_N")
        qs = col(d, "fly_qs_centrifugal_force_N")
        t = col(d, "time_s")
        good = np.isfinite(f) & np.isfinite(qs) & (qs > 0)
        mass = col(d, "flyweight_pivot_inertia_kg_m2")*col(d, "flyweight_q_prime_rad_per_m")**2
        accel = -mass*col(d,"shift_acceleration_closure_m_s2")
        curve = -col(d,"flyweight_pivot_inertia_kg_m2")*col(d,"flyweight_q_prime_rad_per_m")*col(d,"flyweight_q_second_rad_per_m2")*col(d,"shift_speed_m_s")**2
        events = json.loads(path.with_name("events.json").read_text())
        sticking = np.array(["STICK_STICK" in x["cvt_mode"] for x in d]) & good
        free=np.array(['CVTShiftConstraint.FREE' in x['cvt_mode'] for x in d]) & good
        primary_balance=col(d,'primary_actuator_closing_force_N')-.5*np.cos(beta)*col(d,'normal_primary_N')-translating_mass*col(d,'shift_acceleration_closure_m_s2')
        checks[name] = {
            "rows": len(d), "event_count": len(events),
            "force_reconstruction_max_error_N": float(np.max(np.abs((accel+curve-f)[good]))),
            "minimum_centrifugal_denominator_N": float(qs[good].min()),
            "minimum_primary_normal_N": float(np.nanmin(col(d,"normal_primary_N"))),
            "minimum_secondary_normal_N": float(np.nanmin(col(d,"normal_secondary_N"))),
            "minimum_stick_stick_traction_margin": float(min(np.min(mu_static-np.abs(col(d,"lambda_primary")[sticking])),np.min(mu_static-np.abs(col(d,"lambda_secondary")[sticking])))),
            "free_primary_axial_balance_max_residual_N": float(np.max(abs(primary_balance[free]))),
            "engaged_reflected_pivot_mass_range_kg": [float(mass[good].min()),float(mass[good].max())],
            "all_modes": sorted(set(x["cvt_mode"] for x in d)),
        }
        for label, mask in [("engaged_all",good), ("after_0_1_s",good&(t>=.1)), ("post_onset",good&(t>=.05))]:
            idx = np.flatnonzero(mask)[np.argmax(np.abs(f[mask])/qs[mask])]
            checks[name][label] = {
                "max_abs_force_N": float(np.max(np.abs(f[mask]))),
                "peak_percent": float(100*abs(f[idx])/qs[idx]),
                "peak_time_s": float(t[idx]), "signed_force_at_peak_N": float(f[idx]),
                "centrifugal_at_peak_N": float(qs[idx]),
                "curvature_at_peak_N": float(col(d,"fly_dynamic_curvature_force_N")[idx]),
                "shaft_correction_min_Nm": float(np.nanmin(col(d,"fly_dynamic_shaft_torque_correction_vs_constant_Nm")[mask])),
                "shaft_correction_max_Nm": float(np.nanmax(col(d,"fly_dynamic_shaft_torque_correction_vs_constant_Nm")[mask])),
            }
        if name.startswith("baseline"):
            e = next(x for x in events if x["fired_events"] == "cvt:engagement_reached")
            checks[name]["first_engagement"] = {k: e[k] for k in ["time_s","pre_shift_speed_mm_s","post_shift_speed_mm_s"]}
            i = np.flatnonzero(good)[0]
            spring = col(d,"primary_actuator_closing_force_N")[i] - (qs[i]+f[i])
            if name.endswith("full"):
                checks[name]["first_outgoing_budget_N"] = {"centrifugal": float(qs[i]),"spring":float(spring),"dynamic":float(f[i]),"total":float(qs[i]+spring+f[i]),"quasi_static_total":float(qs[i]+spring)}
                arrays[f"{name}__budget_N"] = np.array([qs[i],spring,f[i],qs[i]+spring+f[i]])
            arrays[f"{name}__engagement"] = np.array([e["time_s"],e["pre_shift_speed_mm_s"],e["post_shift_speed_mm_s"]])
    # All selected response runs have one smooth segment; interpolation does
    # not cross a contact/support event. Keep the exact common-time mask.
    grid=np.arange(.05,.355,.0001)
    arrays["response_time_s"] = grid-.05
    for level in ["nominal","tight"]:
        checks[f"response_{level}"]={}
        for field in ["shift_mm","primary_rpm","primary_actuator_closing_force_N"]:
            vals=[]
            for variant in ["full","qs"]:
                roles=[]
                for role in ["stress","control"]:
                    key=f"transient_{level}_{variant}_{role}"
                    assert checks[key]["event_count"]==0, "Do not interpolate through hybrid events"
                    d=data[key]
                    roles.append(np.interp(grid,col(d,"time_s"),col(d,field)))
                response=roles[0]-roles[1];vals.append(response)
                arrays[f"response_{level}_{variant}__{field}"]=response
            delta=vals[1]-vals[0]
            arrays[f"response_{level}_difference__{field}"]=delta
            checks[f"response_{level}"][field]={"max_abs_difference":float(np.max(abs(delta))),"rms_difference":float(np.sqrt(np.mean(delta**2))),"full_response_max_abs":float(np.max(abs(vals[0])))}
    checks["refinement_response_max_change"]={}
    for field in ["shift_mm","primary_rpm","primary_actuator_closing_force_N"]:
        change=arrays[f"response_tight_difference__{field}"]-arrays[f"response_nominal_difference__{field}"]
        checks["refinement_response_max_change"][field]=float(abs(change).max())
    stress=data['transient_tight_full_stress'];control=data['transient_tight_full_control']
    peak=checks['transient_tight_full_stress']['post_onset']['peak_time_s']
    index=int(np.argmin(abs(col(stress,'time_s')-peak)))
    delta=lambda key: float(col(stress,key)[index]-np.interp(peak,col(control,'time_s'),col(control,key)))
    checks['selected_force_response_at_peak']={
        'time_s':peak,'actuator_force_change_N':delta('primary_actuator_closing_force_N'),
        'belt_opening_force_change_N':.5*np.cos(beta)*delta('normal_primary_N'),
        'shift_acceleration_change_m_s2':delta('shift_acceleration_closure_m_s2')}
    sweep=rows(STUDY/"publication_inputs/primary_screen.csv")
    assert len(sweep)==72 and all(x["status"]=="completed" and x["response_class"]=="clean_continuous" for x in sweep)
    travel=[20.,50.,80.]; ramps=[.005,.02,.1,.25]
    arrays["sweep_travel_percent"]=np.array(travel);arrays["sweep_ramp_ms"]=1000*np.array(ramps)
    arrays["sweep_maximum_percent"]=np.array([[100*max(float(x["peak_dynamic_number"]) for x in sweep if float(x["restart_target_shift_percent"])==s and float(x["ramp_s"])==t) for t in ramps] for s in travel])
    np.savez_compressed(out/"primary_publication.npz",**arrays)
    manifest={"release_commit":"7637a38b4fb9ec21dfb953c1c80a27ec5f389654",
              "raw_sha256":{str(p.relative_to(args.raw_dir)):sha(p) for p in sorted(args.raw_dir.rglob('*')) if p.is_file()},
              "run_provenance":{str(p.parent.relative_to(args.raw_dir)):json.loads(p.read_text()) for p in sorted(args.raw_dir.rglob('provenance.json'))},
              "screen_sha256":sha(STUDY/"publication_inputs/primary_screen.csv"),
              "config_sha256":sha(STUDY/"publication_inputs/primary_publication.json"),
              "plot_inputs_sha256":sha(out/"primary_publication.npz"),
              "publication_trace_level":"tight", "checks":checks}
    (out/"primary_publication_audit.json").write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"baseline":checks["baseline_tight_full"]["first_outgoing_budget_N"],"response":checks["response_tight"],"refinement":checks["refinement_response_max_change"]},indent=2))


if __name__=="__main__":main()
