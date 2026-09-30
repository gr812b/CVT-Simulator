"""Recover continuous-backshift force evidence from the frozen E3 archive.

Postprocessing only, with no simulator import. Uses the local-wrap reconstruction
documented in audit_secondary_windows.py. No interpolation or dynamics rerun.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np

from audit_secondary_windows import wrap_loading

STUDY = Path(__file__).resolve().parents[1]
CASES = ("s50_m120_r10ms", "s50_m240_r10ms", "s50_m480_r10ms", "s90_m480_r10ms")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    digest = hashlib.sha256(args.archive.read_bytes()).hexdigest()
    if digest != "e8878e17baf209d70d821c4254a6b043aefdbe2b077f32cea51613d303ad1f9a":
        raise ValueError("Expected the recovered helix_topology_discovery_artifacts(3).zip")
    assembly = json.loads((STUDY.parents[1] / "defaults/baja/simulation_case.json").read_text())["assembly"]
    with zipfile.ZipFile(args.archive) as z:
        provenance = json.loads(z.read("artifacts/provenance/upstream_manifest.json"))
        if provenance["release_commit_sha"] != "7637a38b4fb9ec21dfb953c1c80a27ec5f389654":
            raise ValueError("Unexpected mechanics release")
        summaries = {r["case_id"]: r for r in csv.DictReader(io.StringIO(z.read("artifacts/stress-screen/screen_summary.csv").decode()))}
        selected = {case: [] for case in CASES}
        with z.open("artifacts/stress-screen/screen_trace.csv") as stream:
            for row in csv.DictReader(io.TextIOWrapper(stream)):
                if row["case_id"] in selected:
                    selected[row["case_id"]].append(row)
    result = {"archive_sha256": digest, "release_commit": provenance["release_commit_sha"],
              "scope": "Archived E3 full trajectories; newly reconstructed wrap loading; no refinement or independent full/QS response run.", "cases": {}}
    for case, rows in selected.items():
        d = {}
        for key in rows[0]:
            try:
                d[key] = np.array([float(r[key]) if r[key] else np.nan for r in rows])
            except ValueError:
                d[key] = np.array([r[key] for r in rows])
        d.update(wrap_loading(d, assembly))
        d["active_travel_percent"] = 100 * (d["shift_m"] - assembly["geometry"]["deadzone_shift_m"]) / (assembly["geometry"]["max_shift_m"] - assembly["geometry"]["deadzone_shift_m"])
        onset = float(summaries[case]["onset_s"])
        mask = (d["segment_index"] == 0) & (d["time_s"] >= onset)
        i = int(np.argmax(np.where(mask, abs(d["helix_dynamic_total_correction_N"]), -np.inf)))
        if "STICK_STICK" not in d["cvt_mode"][i] or d["shift_speed_m_s"][i] >= 0:
            raise ValueError("Expected continuous sticking backshift")
        keys = ["time_s", "sample_location", "cvt_mode", "active_travel_percent", "shift_speed_m_s",
                "helix_qs_reaction_force_N", "helix_dynamic_total_correction_N", "helix_dynamic_correction_pct_of_qs_force",
                "helix_full_reaction_force_N", "helix_shaft_accel_reaction_torque_Nm", "helix_shift_accel_reaction_torque_Nm",
                "helix_curvature_reaction_torque_Nm", "primary_min_local_normal_N_per_rad", "secondary_min_local_normal_N_per_rad"]
        result["cases"][case] = {"added_secondary_torque_Nm": float(summaries[case]["added_secondary_torque_Nm"]),
            "onset_s": onset, "ramp_s": float(summaries[case]["ramp_s"]),
            "first_transition_s": float(np.max(d["time_s"][d["segment_index"] == 0])),
            "peak_in_first_segment": {k: d[k][i].item() for k in keys},
            "all_saved_engaged_minimum_helix_torque_Nm": float(np.nanmin(d["helix_reacted_torque_margin_Nm"])),
            "all_saved_engaged_minimum_local_loading_N_per_rad": {side: float(np.nanmin(d[side+"_min_local_normal_N_per_rad"])) for side in ("primary", "secondary")}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
