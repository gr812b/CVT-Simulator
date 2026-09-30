"""Reproduce the main-text moving-state comparison from retained force samples.

Default: use the compact, hash-checked samples; no simulation is run.
--prepare-from-raw: recreate that compact input from the frozen publication CSVs.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

STUDY = Path(__file__).resolve().parents[1]
INPUTS = STUDY / "publication_inputs"
import sys
if str(STUDY.parents[1]) not in sys.path:
    sys.path.insert(0, str(STUDY.parents[1]))
from results_health.prep_support import moving_source_hashes
TERMS = ("normal_contact", "tangential_belt_acceleration",
         "radial_shift_acceleration", "radial_geometry_curvature",
         "tangential_shifting_radius")
COLUMNS = (
    "time_s", "segment_index", "shift_speed", "belt_speed",
    "contact.primary_lambda", "contact.secondary_lambda",
    "boundary.primary_power_W", "boundary.secondary_power_W",
    "coefficient.primary_H", "coefficient.secondary_H",
    "geometry.primary_d_radius_ds", "geometry.secondary_d_radius_ds",
    "geometry.primary_radius_cm_m", "geometry.secondary_radius_cm_m",
    "geometry.primary_d2_radius_ds2_per_m", "geometry.secondary_d2_radius_ds2_per_m",
    "loop.response_coefficient.radial_geometry_curvature_N_per_m2ps2",
    "loop.response_coefficient.tangential_shifting_radius_N_per_m2ps2",
) + tuple(f"loop.{t}_N" for t in TERMS)
WINDOWS = {
    "unloading_rise": ("unloading", 1.5, 1.55),
    "combined_tune_rise": ("contact_combined", 1.8, 1.9),
    "strong_torque_rise": ("overrun_strong", 2.0, 2.2),
    "mild_reverse_power": ("overrun_mild", 2.25, 5.0),
    "strong_reverse_power": ("overrun_strong", 2.25, 5.0),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(path, raw=None, audit_path=None):
    path = Path(path)
    raw_root = Path(raw) if raw is not None else STUDY / "artifacts/publication"
    audit_path = Path(audit_path) if audit_path is not None else path.parent / "belt_publication_audit.json"
    frozen = json.loads(audit_path.read_text())
    expected_sources = moving_source_hashes(frozen)
    arrays, sources, modes = {}, {}, {}
    for name, (case, start, end) in WINDOWS.items():
        for setting in ("nominal", "tight"):
            key = f"{name}__{setting}"
            source = f"{case}_{setting}_full/terms.csv.gz"
            raw_file = raw_root / source
            actual = digest(raw_file)
            if source not in expected_sources:
                raise ValueError(f"Main audit omits required moving-state source: {source}; audit={audit_path}")
            if actual != expected_sources[source]:
                raise ValueError(f"Frozen raw hash mismatch: {source}")
            sources[source] = actual
            with gzip.open(raw_file, "rt") as stream:
                interval = [r for r in csv.DictReader(stream)
                            if start - 1e-10 <= float(r["time_s"]) <= end + 1e-10]
            rows = [r for r in interval if "CVTShiftConstraint.FREE" in r["mode"]]
            # Verify continuous free motion, not merely a filter that hides a hold.
            last_free = float(rows[-1]["time_s"]) if rows else start
            interior = [r for r in interval if float(r["time_s"]) < last_free - 1e-10]
            assert all("CVTShiftConstraint.FREE" in r["mode"] for r in interior)
            if not rows or not all("EngagedContactMode.STICK_STICK" in r["mode"]
                                   for r in rows):
                raise ValueError(f"Expected free, stick-stick samples: {key}")
            if "reverse_power" not in name:
                assert abs(float(rows[0]["time_s"]) - start) < 1e-8
                assert abs(float(rows[-1]["time_s"]) - end) < 1e-8
            modes[key] = "FREE:STICK_STICK"
            arrays[key] = np.array([[float(r[c]) for c in COLUMNS] for r in rows])
    arrays["columns"] = np.array(COLUMNS)
    arrays["metadata"] = np.array(json.dumps({
        "raw_sha256": sources, "modes": modes,
        "selection": "Stated interval, free shift only; event sides kept by segment.",
        "reverse_power_window": "2.25 s to the incoming side of the first upper-stop capture.",
    }, sort_keys=True))
    np.savez_compressed(path, **arrays)


def analyse(path):
    out = {"input_sha256": digest(path), "cases": {}}
    with np.load(path, allow_pickle=False) as data:
        out["provenance"] = json.loads(str(data["metadata"]))
        assert tuple(data["columns"]) == COLUMNS
        for name in WINDOWS:
            for setting in ("nominal", "tight"):
                a = data[f"{name}__{setting}"]
                col = lambda key: a[:, COLUMNS.index(key)]
                time, segment = col("time_s"), col("segment_index")
                force = np.stack([col(f"loop.{t}_N") for t in TERMS], axis=1)
                integral = np.zeros(len(TERMS))
                for seg in np.unique(segment):
                    ix = segment == seg
                    assert np.all(np.diff(time[ix]) >= 0)
                    integral += np.trapezoid(np.abs(force[ix]), time[ix], axis=0)
                q = 0.32670857238799994
                driver = col("shift_speed") * col("belt_speed")
                primary = q * col("coefficient.primary_H") * col("geometry.primary_d_radius_ds") * driver
                secondary = -q * col("coefficient.secondary_H") * col("geometry.secondary_d_radius_ds") * driver
                assert np.max(np.abs(primary + secondary - force[:, 4])) < 1e-12
                assert np.max(np.abs(col("loop.response_coefficient.radial_geometry_curvature_N_per_m2ps2") * col("shift_speed")**2 - force[:, 3])) < 1e-12
                if "reverse_power" in name:
                    assert np.all(col("contact.primary_lambda") < 0)
                    assert np.all(col("contact.secondary_lambda") > 0)
                    assert np.all(col("boundary.primary_power_W") < 0)
                    assert np.all(col("boundary.secondary_power_W") > 0)
                peak_curvature = int(np.argmax(np.abs(force[:, 3])))
                peak_moving = int(np.argmax(np.abs(force[:, 4])))
                out["cases"][f"{name}__{setting}"] = {
                    "sample_count": len(time), "window_s": [float(time[0]), float(time[-1])],
                    "shift_speed_mm_s": [float(col("shift_speed").min()*1000), float(col("shift_speed").max()*1000)],
                    "belt_speed_m_s": [float(col("belt_speed").min()), float(col("belt_speed").max())],
                    "integrated_share_percent": dict(zip(TERMS, (100*integral/integral.sum()).tolist())),
                    "peak_absolute_mN": dict(zip(TERMS, (1000*np.abs(force).max(axis=0)).tolist())),
                    "peak_curvature": {
                        "time_s": float(time[peak_curvature]),
                        "coefficient_kg_m": float(col("loop.response_coefficient.radial_geometry_curvature_N_per_m2ps2")[peak_curvature]),
                        "shift_speed_m_s": float(col("shift_speed")[peak_curvature]),
                        "force_mN": float(force[peak_curvature, 3]*1000)},
                    "peak_moving_radius": {
                        "time_s": float(time[peak_moving]),
                        "primary_signed_mN": float(primary[peak_moving]*1000),
                        "secondary_signed_mN": float(secondary[peak_moving]*1000),
                        "sum_mN": float(force[peak_moving, 4]*1000)},
                    "traction_range": {key: [float(col(key).min()), float(col(key).max())]
                                       for key in ("contact.primary_lambda", "contact.secondary_lambda")},
                }
    out["max_share_refinement_change_percentage_points"] = max(
        abs(out["cases"][f"{name}__tight"]["integrated_share_percent"][term]
            - out["cases"][f"{name}__nominal"]["integrated_share_percent"][term])
        for name in WINDOWS for term in TERMS[3:])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-from-raw", action="store_true")
    parser.add_argument("--input-dir", type=Path, default=INPUTS)
    parser.add_argument("--raw-dir", type=Path, default=STUDY / "artifacts/publication")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    path = args.input_dir / "belt_moving_state_samples.npz"
    if args.prepare_from_raw:
        prepare(path, raw=args.raw_dir, audit_path=args.input_dir / "belt_publication_audit.json")
    result = analyse(path)
    (args.output or args.input_dir / "belt_moving_state_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    for key, row in result["cases"].items():
        if key.endswith("__tight"):
            print(key, row["window_s"], row["shift_speed_mm_s"],
                  {t: row["integrated_share_percent"][t] for t in TERMS[3:]})
    print("Maximum small-term share change on refinement:",
          result["max_share_refinement_change_percentage_points"], "percentage points")


if __name__ == "__main__":
    main()
