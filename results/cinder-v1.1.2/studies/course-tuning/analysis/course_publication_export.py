"""Export the nine current Section 4.5 manuscript figures from the accepted prepared course bundle.

This module performs plotting/post-processing only.  It never constructs a CINDER
system and never integrates a trajectory.  It deliberately materializes the
prepared, unresampled course arrays into the input shapes used by the recovered
paper-specific plotting scripts so the established cases, windows, masks,
segment breaks, event sides and appearance are retained.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = Path(__file__).resolve().parent
REF = HERE / "course_export_reference"

EXPECTED_COURSE_NPZ_SHA256 = "990c70ea87f3a42f0e941952a2f700abf479a5a0909f5c2505f2f6daff571266"

CURRENT_PNGS = (
    "common_course_profile.png",
    "opening_free_shift_characteristics.png",
    "shift_curve_mechanical_causes.png",
    "severe_hill_response.png",
    "d02_traction_power.png",
    "d02_hill_repairs.png",
    "cyclic_shift_and_support.png",
    "moderate_hill_operating_conditions.png",
    "descent_reverse_power.png",
)

LAUNCH_CASES = ("R00", "W85", "P300", "RC10", "R26B7", "RC40L")
HILL_CASES = ("R00", "D01", "D02", "D02_M", "D02_P", "D02_M170")
CYCLIC_CASES = ("R00", "P300", "R26B7", "RC10")
MODERATE_CASES = ("R00", "W85", "H28", "RC40L", "D01", "D02_P")

LAUNCH_COLUMNS = (
    "time_s", "distance_m", "primary_rpm", "secondary_rpm", "shift_mm",
    "shift_constraint", "engagement", "contact_mode",
)
HILL_COLUMNS = (
    "time_s", "distance_m", "speed_m_s", "primary_rpm", "secondary_rpm", "shift_mm",
    "grade_deg", "shift_constraint", "contact_mode", "primary_static_utilization",
    "secondary_static_utilization", "normal_primary_N", "normal_secondary_N",
    "primary.fixed_pivot_flyweight_centrifugal_N", "primary.axial_spring_N",
    "low_ratio_seat_reaction_N", "primary_boundary_power_W", "secondary_boundary_power_W",
    "primary_slip_loss_W", "primary_vrel_m_s", "secondary_actuator_closing_N",
)
MODERATE_COLUMNS = (
    "time_s", "distance_m", "shift_mm", "primary_rpm", "speed_m_s", "grade_deg",
    "segment_id", "engagement", "shift_constraint", "contact_mode",
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_bundle(bundle_dir: Path) -> dict:
    bundle_dir = bundle_dir.resolve()
    manifest = load_json(bundle_dir / "course_bundle.json")
    if manifest.get("schema") != 1:
        raise ValueError("Unsupported course bundle schema")
    if manifest.get("row_order_and_event_sides_preserved") is not True:
        raise ValueError("Course bundle does not declare event-side preservation")
    if manifest.get("smoothing_or_resampling") is not False:
        raise ValueError("Course bundle is not the unresampled accepted preparation")
    expected_npz = EXPECTED_COURSE_NPZ_SHA256
    recorded = manifest.get("files", {}).get("course_plot_inputs.npz")
    actual = sha(bundle_dir / "course_plot_inputs.npz")
    if recorded != actual:
        raise ValueError("course_plot_inputs.npz differs from course_bundle.json")
    # This is the accepted prep_20260929T205331850596Z plotting bundle identity.
    if actual != expected_npz:
        raise ValueError(f"Unexpected course_plot_inputs.npz identity: {actual}")
    for rel, expected in manifest.get("files", {}).items():
        p = bundle_dir / rel
        if not p.is_file():
            raise FileNotFoundError(f"Prepared course input missing: {p}")
        if sha(p) != expected:
            raise ValueError(f"Prepared course input hash mismatch: {rel}")
    return manifest


def frames(bundle_dir: Path) -> dict[str, dict[str, np.ndarray]]:
    with np.load(bundle_dir / "course_plot_inputs.npz", allow_pickle=False) as z:
        desc = json.loads(str(z["schema_json"]))
        result = {}
        for name, meta in desc.items():
            prefix = meta["array_prefix"] + "__"
            cols = {}
            for col in meta["columns"]:
                cols[col] = np.array(z[prefix + col], copy=True)
            result[name] = cols
    return result


def first_ge(a, value):
    q = np.flatnonzero(np.asarray(a, float) >= value)
    if not len(q):
        return None
    return int(q[0])


def chronological_slice(cols, start_m, end_m, *, include_end=False):
    d = np.asarray(cols["distance_m"], float)
    i0 = first_ge(d, start_m)
    if i0 is None:
        raise ValueError(f"Trajectory never reaches {start_m} m")
    tail = np.flatnonzero(d[i0:] >= end_m)
    i1 = i0 + int(tail[0]) + (1 if include_end else 0) if len(tail) else len(d)
    return {k: v[i0:i1] for k, v in cols.items()}


def before_first_crossing(cols, end_m):
    d = np.asarray(cols["distance_m"], float)
    q = np.flatnonzero(d >= end_m)
    i1 = int(q[0]) if len(q) else len(d)
    return {k: v[:i1] for k, v in cols.items()}


def write_csv(path: Path, cols: dict[str, np.ndarray], names=None):
    names = list(names or cols.keys())
    missing = [x for x in names if x not in cols]
    if missing:
        raise KeyError(f"Missing plotting columns for {path.name}: {missing}")
    n = len(cols[names[0]])
    if any(len(cols[x]) != n for x in names):
        raise ValueError("Column length mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(names)
        for i in range(n):
            row = []
            for name in names:
                value = cols[name][i]
                if isinstance(value, np.generic):
                    value = value.item()
                if isinstance(value, float) and not np.isfinite(value):
                    value = ""
                row.append(value)
            w.writerow(row)


def copy_ref(section: str, target: Path):
    src = REF / section
    if not src.is_dir():
        raise FileNotFoundError(f"Recovered plotting source missing: {src}")
    target.mkdir(parents=True, exist_ok=True)
    for p in src.iterdir():
        if p.is_file():
            shutil.copy2(p, target / p.name)


def materialize_inputs(bundle_dir: Path, work: Path, all_frames: dict):
    # 4.5.1 opening and hardware explanation.
    fs = work / "451" / "figure_source"; copy_ref("451", fs)
    for case in LAUNCH_CASES:
        cols = before_first_crossing(all_frames[f"unified_course/{case}"], 120.0)
        write_csv(fs / f"launch_{case}.csv", cols, LAUNCH_COLUMNS)
    for case in ("R00", "P300", "RC10", "R26B7", "RC40L"):
        case_dir = bundle_dir / "cases" / "unified_course" / case
        # Section 4.5.1 was built from the case-specific *shape* mechanism map,
        # not the lower-level geometry mechanism_map.csv.  The shape map carries
        # the resolved spring/ramp quantities used by the paper figure, including
        # primary_spring_opening_N and centrifugal_force_3000rpm_N.
        source = case_dir / "shape_mechanism_map.csv"
        with source.open(encoding="utf-8-sig", newline="") as stream:
            fields = set(next(csv.reader(stream)))
        required = {"active_shift_fraction", "primary_spring_opening_N",
                    "centrifugal_force_3000rpm_N"}
        missing = sorted(required - fields)
        if missing:
            raise ValueError(f"Prepared 4.5.1 shape mechanism map omits {missing}: {source}")
        shutil.copy2(source, fs / f"mechanism_{case}.csv")
    for case in ("R00", "RC10", "R26B7", "RC40L"):
        case_dir = bundle_dir / "cases" / "unified_course" / case
        shutil.copy2(case_dir / "ramp_profile.csv", fs / f"ramp_{case}.csv")

    # 4.5.2 severe hill and repairs.  Start at the first 120 m crossing; stop at
    # the first 224 m crossing, or retain the complete stopped/rollback history.
    fs = work / "452" / "figure_source"; copy_ref("452", fs)
    for case in HILL_CASES:
        cols = chronological_slice(all_frames[f"unified_course/{case}"], 120.0, 224.0)
        write_csv(fs / f"{case}_hill.csv", cols, HILL_COLUMNS)
        shutil.copy2(bundle_dir / "cases" / "unified_course" / case / "events.json",
                     fs / f"{case}_hill_events.json")

    # 4.5.3.  The recovered source deliberately carries 12 m of context on each side.
    fs = work / "453" / "figure_source"; copy_ref("453", fs)
    for case in CYCLIC_CASES:
        cols = chronological_slice(all_frames[f"unified_course/{case}"], 252.0, 348.0)
        write_csv(fs / f"{case}_cyclic.csv", cols)
        shutil.copy2(bundle_dir / "cases" / "unified_course" / case / "events.json",
                     fs / f"{case}_events.json")

    # 4.5.4.  Keep a one-metre context row on both sides; the exporter itself
    # applies the accepted 348-596 m display window and segment breaks.
    fs = work / "454" / "figure_source"; copy_ref("454", fs)
    for case in MODERATE_CASES:
        cols = chronological_slice(all_frames[f"unified_course/{case}"], 347.0, 597.0)
        write_csv(fs / f"{case}_moderate.csv", cols, MODERATE_COLUMNS)

    # 4.5.5 descent, with the exact upper-end state retained when present.
    fs = work / "455" / "figure_source"; copy_ref("455", fs)
    cols = chronological_slice(all_frames["unified_course/R00"], 603.0, 732.0, include_end=True)
    write_csv(fs / "R00_descent.csv", cols)


def run_script(script: Path, log: Path):
    proc = subprocess.run([sys.executable, str(script)], cwd=script.parent,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError(f"{script.name} failed with exit {proc.returncode}; see {log}")


def export(bundle_dir: Path, output_dir: Path, log_dir: Path | None = None) -> dict:
    bundle_dir = bundle_dir.resolve(); output_dir = output_dir.resolve()
    manifest = verify_bundle(bundle_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir = (log_dir or output_dir / "logs").resolve(); log_dir.mkdir(parents=True, exist_ok=True)
    all_frames = frames(bundle_dir)
    required = {f"unified_course/{c}" for c in set(LAUNCH_CASES + HILL_CASES + CYCLIC_CASES + MODERATE_CASES + ("R00",))}
    missing = sorted(required - set(all_frames))
    if missing:
        raise KeyError(f"Prepared course bundle omits selected manuscript cases: {missing}")

    with tempfile.TemporaryDirectory(prefix="cinder-course-export-") as td:
        work = Path(td)
        materialize_inputs(bundle_dir, work, all_frames)
        scripts = [
            work/"451/figure_source/build_figures.py",
            work/"452/figure_source/build_preserved_figures.py",
            work/"452/figure_source/build_repair_figure.py",
            work/"453/figure_source/build_cyclic_figure.py",
            work/"454/figure_source/build_moderate_figure.py",
            work/"455/figure_source/build_descent_figure.py",
        ]
        for i, script in enumerate(scripts, 1):
            run_script(script, log_dir / f"course_{i:02d}_{script.stem}.log")

        locations = {
            "common_course_profile.png": work/"451/figures/results/course/common_course_profile.png",
            "opening_free_shift_characteristics.png": work/"451/figures/results/course/opening_free_shift_characteristics.png",
            "shift_curve_mechanical_causes.png": work/"451/figures/results/course/shift_curve_mechanical_causes.png",
            "severe_hill_response.png": work/"452/figures/results/course/severe_hill_response.png",
            "d02_traction_power.png": work/"452/figures/results/course/d02_traction_power.png",
            "d02_hill_repairs.png": work/"452/figures/results/course/d02_hill_repairs.png",
            "cyclic_shift_and_support.png": work/"453/figures/results/course/cyclic_shift_and_support.png",
            "moderate_hill_operating_conditions.png": work/"454/figures/results/course/moderate_hill_operating_conditions.png",
            "descent_reverse_power.png": work/"455/figures/results/course/descent_reverse_power.png",
        }
        # Preserve available genuine vector companions.  Do not wrap the 4.5.1 PNGs in PDF.
        pdfs = {
            name.replace(".png", ".pdf"): src.with_suffix(".pdf")
            for name, src in locations.items() if src.with_suffix(".pdf").is_file()
        }
        for name, src in {**locations, **pdfs}.items():
            if not src.is_file():
                raise FileNotFoundError(f"Expected course export missing: {src}")
            shutil.copy2(src, output_dir / name)

    records = {}
    for p in sorted(output_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in {".png", ".pdf"}:
            records[p.name] = {"sha256": sha(p), "bytes": p.stat().st_size}
    missing_outputs = sorted(set(CURRENT_PNGS) - set(records))
    if missing_outputs:
        raise RuntimeError(f"Missing current manuscript course figures: {missing_outputs}")
    provenance = {
        "schema": 1,
        "accepted_numerical_source": "prep_20260929T205331850596Z prepared/course",
        "course_plot_inputs_sha256": sha(bundle_dir/"course_plot_inputs.npz"),
        "course_bundle_sha256": sha(bundle_dir/"course_bundle.json"),
        "source_suite": manifest.get("source_suite"),
        "row_order_and_event_sides_preserved": True,
        "smoothing_or_resampling": False,
        "export_sources": {str(p.relative_to(HERE)).replace('\\','/'): sha(p)
                           for p in sorted(REF.rglob('*')) if p.is_file()},
        "course_451_source_status": "presentation reconstruction from recovered v4 numerical exporter and current committed assets; later original plotting source unavailable",
        "figures": {
            "opening": {"cases": list(LAUNCH_CASES), "window": "launch through last row before first 120 m crossing", "complete_supported_and_free_shift_path": True},
            "shift_mechanics": {"cases": ["R00","P300","RC10","R26B7","RC40L"], "mechanism_maps": "prepared case mechanism_map/ramp_profile"},
            "severe_hill": {"cases": ["R00","D01","D02"], "road_window_m": [120,224], "D02_rollback_retained": True},
            "d02_traction_power": {"case": "D02", "x": "time_s", "output_power_expression": "-secondary_boundary_power_W/1000", "other_channels": ["primary_boundary_power_W/1000","primary_slip_loss_W/1000"], "post_zero_speed_rollback_retained": True},
            "d02_repairs": {"cases": ["D02","D02_M","D02_P","D02_M170"], "matched_state": "low_ratio_seat + stick_stick + primary_rpm<=3200; D02 additionally pre-capacity", "curves_not_interpolated": True},
            "cyclic": {"cases": list(CYCLIC_CASES), "plot_window_m": [264,336], "support_release_markers": "exact events.json", "free_mode_reaction": 0.0},
            "moderate": {"cases": list(MODERATE_CASES), "road_window_m": [348,596], "time_origin": "each case's 348 m crossing", "segment_breaks_retained": True, "late_window_definition": "recovered accepted moderate_evidence.json"},
            "descent": {"case": "R00", "road_window_m": [604,732], "channels": ["primary_boundary_power_W/1000","secondary_boundary_power_W/1000"], "segment_breaks_retained": True},
        },
        "outputs": records,
    }
    (output_dir / "course_export_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return provenance


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle-dir", type=Path, required=True,
                   help="Accepted prep_20260929T205331850596Z prepared/course directory")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--log-dir", type=Path)
    args = p.parse_args()
    result = export(args.bundle_dir, args.output_dir, args.log_dir)
    print(json.dumps({"outputs": result["outputs"]}, indent=2))


if __name__ == "__main__":
    main()
