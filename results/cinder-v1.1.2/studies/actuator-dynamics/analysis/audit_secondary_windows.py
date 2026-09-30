"""Audit omitted secondary-force windows using retained 1.1.2 outputs only.

No CINDER import, closure solve, integration, resampling or event interpolation.
The baseline wrap-loading reconstruction is algebraic postprocessing of saved
normal resultants, tractions, accelerations and geometry. Its equations are in
tag 7637a38b4fb9ec21dfb953c1c80a27ec5f389654:
  cvtModel/src/cinder/results/fields/belt.py:recover_belt_tension_boundaries
  cvtModel/src/cinder/model/cvt/dynamics/equation_context.py
  cvtModel/src/cinder/model/cvt/geometry/{spec,belt_pulley}.py

See provenance/SECONDARY_EVIDENCE_RESET.md for inputs and reproduction.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np

STUDY = Path(__file__).resolve().parents[1]
RELEASE_COMMIT = "7637a38b4fb9ec21dfb953c1c80a27ec5f389654"
PREFIX = "source/results/cinder-v1.1.2/"
PRIMARY = PREFIX + "studies/actuator-dynamics/"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require_equal(actual, expected, name):
    if actual != expected:
        raise ValueError(f"{name}: expected {expected}, found {actual}")


def csv_arrays(data):
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(data).decode())))
    result = {}
    for key in rows[0]:
        try:
            result[key] = np.array([float(r[key]) if r[key] else np.nan for r in rows])
        except ValueError:
            result[key] = np.array([r[key] for r in rows])
    return result


def wrap_loading(d, assembly):
    """Exact wrap minima: T is monotone, and the radial offset is constant.

    Recover T_in-C and T_out-C directly; n=(T-C)/sin(beta). This avoids
    subtracting two large radial offsets and uses the recorded one-sided
    geometry derivatives. No deadzone value is interpreted as zero loading.
    """
    belt = assembly["geometry"]["belt"]
    beta = assembly["geometry"]["sheave_half_angle_rad"]
    sb = np.sin(beta)
    height, wo, wi = (belt[k] for k in ("height_m", "outer_width_m", "inner_width_m"))
    q = assembly["inertias"]["belt_density_kg_per_m3"] * height * (wo + wi) / 2
    cm_depth = height * (wo + 2 * wi) / (3 * (wo + wi))
    result = {}
    for side in ("primary", "secondary"):
        wrap = d[f"{side}_wrap_rad"]
        z = d[f"lambda_{side}"] * wrap / sb
        small = abs(z) < 1e-4
        phi, psi = np.empty_like(z), np.empty_like(z)
        a = z[small]
        phi[small] = 1 - a / 2 + a**2 / 6 - a**3 / 24 + a**4 / 120
        psi[small] = .5 - a / 6 + a**2 / 24 - a**3 / 120 + a**4 / 720
        a = z[~small]
        phi[~small] = -np.expm1(-a) / a
        psi[~small] = (a + np.expm1(-a)) / a**2
        radius = d[f"{side}_effective_radius_m"] + belt["cord_depth_from_outer_m"] - cm_depth
        radius_derivative = d[f"{side}_dx_ds"] / (2 * np.tan(beta))
        offset = q * (radius * d["belt_acceleration_closure_m_s2"]
                      + radius_derivative * d["shift_speed_m_s"] * d["belt_speed_m_s"])
        tin_c = d[f"normal_{side}_N"] * sb / (wrap * phi) - offset * wrap * psi / phi
        tout_c = np.exp(-z) * tin_c + offset * wrap * phi
        result[side + "_min_local_normal_N_per_rad"] = np.minimum(tin_c, tout_c) / sb
    return result


def row(d, index, keys):
    return {key: d[key][index].item() for key in keys}


def baseline(z, level, audit):
    name = f"baseline_{level}_full"
    prefix = PRIMARY + "artifacts/primary-publication/" + name + "/"
    for filename in ("trajectory.csv.gz", "provenance.json", "events.json"):
        data = z.read(prefix + filename)
        require_equal(sha(data), audit["raw_sha256"][name + "/" + filename], name + "/" + filename)
    provenance = json.loads(z.read(prefix + "provenance.json"))
    require_equal(provenance["release_commit"], RELEASE_COMMIT, "baseline release")
    require_equal(provenance["cinder_version"], "1.1.2", "baseline version")
    config_bytes = z.read(PREFIX + "defaults/baja/simulation_case.json")
    require_equal(sha(config_bytes), provenance["source_sha256"]["defaults/baja/simulation_case.json"], "baseline geometry")
    assembly = json.loads(config_bytes)["assembly"]
    d = csv_arrays(z.read(prefix + "trajectory.csv.gz"))
    d.update(wrap_loading(d, assembly))
    engaged = np.isfinite(d["helix_qs_reaction_force_N"])
    correction = d["helix_dynamic_total_correction_N"]
    qs = d["helix_qs_reaction_force_N"]
    parts = sum(d["helix_dynamic_" + part + "_force_N"]
                for part in ("shaft_accel", "shift_accel", "curvature"))
    identity = np.nanmax(abs(parts - correction))
    if identity > 1e-8:
        raise ValueError("Baseline signed-force identity failed")
    keys = ["time_s", "segment_index", "sample_location", "cvt_mode",
            "shift_speed_m_s", "shift_acceleration_closure_m_s2", "alpha_secondary_rad_s2",
            "helix_qs_reaction_force_N", "helix_dynamic_shaft_accel_force_N",
            "helix_dynamic_shift_accel_force_N", "helix_dynamic_curvature_force_N",
            "helix_dynamic_total_correction_N", "helix_full_reaction_force_N",
            "helix_dynamic_correction_pct_of_qs_force",
            "mass_helix_reflected_active_kg", "mass_total_direct_active_kg",
            "primary_min_local_normal_N_per_rad", "secondary_min_local_normal_N_per_rad"]
    indices = {"first_engaged": int(np.flatnonzero(engaged)[0])}
    for label, mask in (("early_peak", engaged & (d["time_s"] < .1)),
                        ("later_peak", engaged & (d["time_s"] >= .1))):
        indices[label] = int(np.argmax(np.where(mask, abs(correction), -np.inf)))
    return {
        "raw_sha256": audit["raw_sha256"][name + "/trajectory.csv.gz"],
        "settings": provenance["settings"],
        **{name: row(d, i, keys) for name, i in indices.items()},
        "max_later_absolute_percent": float(np.nanmax(abs(100 * correction[d["time_s"] >= .1] / qs[d["time_s"] >= .1]))),
        "minimum_full_helix_force_N": float(np.nanmin(d["helix_full_reaction_force_N"])),
        "minimum_local_loading_N_per_rad": {side: float(np.nanmin(d[side + "_min_local_normal_N_per_rad"])) for side in ("primary", "secondary")},
        "max_signed_force_identity_error_N": float(identity),
        "engaged_direct_helix_inertia_share_percent_range": [
            float(op(100 * d["mass_helix_reflected_active_kg"][engaged] / d["mass_total_direct_active_kg"][engaged]))
            for op in (np.min, np.max)],
        "local_loading_method": "Algebraic reconstruction from retained fields; no new closure solve or integration.",
    }


def stock(npz, level, assembly, checks):
    prefix = "stock_" + level + "_full__"
    d = {key.removeprefix(prefix): npz[key] for key in npz.files if key.startswith(prefix)}
    qs = d["e58_helix_qs_margin_Nm"]
    actual = d["e58_helix_actual_margin_Nm"]
    correction = actual - qs
    index = int(np.nanargmax(abs(correction)))
    parts = sum(d["e58_helix_physical_" + part + "_term_Nm"] for part in ("shaft", "shift", "curvature"))
    if np.nanmax(abs(parts-correction)) > 1e-8:
        raise ValueError("Stock signed-torque identity failed")
    # Stored circumferential-ramp angle is the complement of the 20 degree
    # helix angle; the reference closing-coordinate derivative is positive.
    coupling = assembly["pulleys"]["secondary"]["helical_coupling"]
    profile = coupling["profile"]
    segments = profile["circumferential_profile"]["segments"]
    require_equal(len(segments), 1, "reference helix segments")
    require_equal(segments[0]["kind"], "linear_segment", "reference helix profile")
    require_equal(coupling["opening_per_axial_position"], -1.0, "reference helix coordinate")
    derivative = np.tan(segments[0]["angle_rad"]) / profile["radius_m"]
    keys = ["time_s", "segment_index", "sample_location", "mode", "shift_mm",
            "shift_acceleration_closure_m_s2", "e58_helix_qs_margin_Nm",
            "e58_helix_actual_margin_Nm", "e58_helix_physical_shaft_term_Nm",
            "e58_helix_physical_shift_term_Nm", "e58_helix_physical_curvature_term_Nm",
            "primary_min_local_normal_N_per_rad", "secondary_min_local_normal_N_per_rad"]
    return {"peak": row(d, index, keys), "net_peak_correction_Nm": float(correction[index]),
            "dtheta_dx_secondary_rad_per_m": float(derivative),
            "net_peak_correction_N": float(correction[index] * derivative),
            "peak_percent_of_simultaneous_qs": float(100 * correction[index] / qs[index]),
            "minimum_full_helix_torque_Nm": float(np.nanmin(actual)),
            "minimum_local_loading_N_per_rad": {side: float(np.nanmin(d[side+"_min_local_normal_N_per_rad"])) for side in ("primary", "secondary")},
            "prior_response_audit": checks["stock_response_" + level],
            "prior_local_audit": checks["stock_" + level + "_full"]["local_audit"],
            "interpretation": "Peak is an outgoing re-engagement state, not the initial 2 ms ramp or sustained stick-stick motion."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = STUDY / "publication_inputs"
    sa = json.loads((inputs / "secondary_publication_audit.json").read_text())
    compact = inputs / "secondary_publication.npz"
    require_equal(sha(compact.read_bytes()), sa["plot_inputs_sha256"], "secondary compact input")
    require_equal(sa["release_commit"], RELEASE_COMMIT, "secondary release")
    with zipfile.ZipFile(args.primary_package) as z, np.load(compact, allow_pickle=False) as npz:
        pa = json.loads(z.read(PRIMARY + "publication_inputs/primary_publication_audit.json"))
        require_equal(pa["release_commit"], RELEASE_COMMIT, "primary release")
        assembly = json.loads(z.read(PREFIX + "defaults/baja/simulation_case.json"))["assembly"]
        result = {
            "release_commit": RELEASE_COMMIT,
            "method": "Retained-output postprocessing only; no CINDER import or new simulation.",
            "primary_package_sha256": sha(args.primary_package.read_bytes()),
            "secondary_compact_sha256": sha(compact.read_bytes()),
            "baseline": {level: baseline(z, level, pa) for level in ("nominal", "tight")},
            "stock": {level: stock(npz, level, assembly, sa["checks"]) for level in ("nominal", "tight")},
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
