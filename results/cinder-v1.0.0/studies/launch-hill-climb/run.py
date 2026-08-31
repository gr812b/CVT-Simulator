"""Run the frozen CINDER 1.0.0 Baja launch + hill-climb example."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import cinder
from cinder.contracts import (
    decode_simulation_case_document,
    project_simulation_result,
    validate_simulation_case_document,
)

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
VERIFY = RELEASE_ROOT / "verify_environment.py"
STUDY_FILE = STUDY_ROOT / "study.json"
ARTIFACTS = STUDY_ROOT / "artifacts"

EXPECTED_CINDER_VERSION = "1.0.0"
RAD_PER_S_TO_RPM = 60.0 / (2.0 * math.pi)


def load_study() -> tuple[dict, dict]:
    spec = json.loads(STUDY_FILE.read_text(encoding="utf-8"))
    base_path = (STUDY_ROOT / spec["base_document"]).resolve()
    document = json.loads(base_path.read_text(encoding="utf-8"))
    return spec, document


def apply_overrides(document: dict, spec: dict) -> dict:
    """Apply only the study-level variables declared in study.json."""

    overrides = spec["overrides"]
    document["scenario"]["time_span_s"] = list(overrides["time_span_s"])

    segments = []
    for segment in overrides["road_grade_segments"]:
        segments.append(
            {
                "start_distance_m": float(segment["start_distance_m"]),
                "grade_angle_rad": math.radians(float(segment["grade_angle_deg"])),
            }
        )

    document["shaft_boundaries"]["secondary"]["road_profile"] = {
        "kind": "piecewise_constant_grade",
        "segments": segments,
    }
    return document


def column_map(payload: dict) -> dict[str, np.ndarray]:
    result = {}
    for column in payload["report_table"]["columns"]:
        result[column["key"]] = np.asarray(
            [np.nan if value is None else value for value in column["values"]],
            dtype=float,
        )
    return result


def require_column(columns: dict[str, np.ndarray], key: str) -> np.ndarray:
    if key not in columns:
        available = ", ".join(sorted(columns))
        raise KeyError(f"Missing report column {key!r}. Available: {available}")
    return columns[key]


def write_report_csv(payload: dict, path: Path) -> None:
    columns = payload["report_table"]["columns"]
    keys = [column["key"] for column in columns]
    values = [column["values"] for column in columns]
    row_count = payload["report_table"]["row_count"]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(keys)
        for row in range(row_count):
            writer.writerow([column[row] for column in values])


def save_time_plot(
    time: np.ndarray,
    series: list[tuple[np.ndarray, str]],
    *,
    ylabel: str,
    title: str,
    filename: str,
) -> None:
    fig, ax = plt.subplots()
    for values, label in series:
        ax.plot(time, values, label=label)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True)
    if len(series) > 1:
        ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / filename, dpi=180)
    plt.close(fig)


def main() -> int:
    subprocess.run([sys.executable, str(VERIFY)], check=True)

    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise SystemExit(
            f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__}."
        )

    spec, document = load_study()
    resolved = apply_overrides(document, spec)

    validation = validate_simulation_case_document(resolved)
    if not validation.is_valid:
        for finding in validation.findings:
            print(
                f"[{finding.severity}] "
                f"{finding.document_path or '/'}: {finding.message}"
            )
        raise SystemExit("Resolved study input failed CINDER validation.")

    decoded = decode_simulation_case_document(resolved)

    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)

    (ARTIFACTS / "resolved_simulation_case.json").write_text(
        json.dumps(resolved, indent=2) + "\n",
        encoding="utf-8",
    )

    result = decoded.system.run(
        time_span=decoded.time_span,
        initial_state=decoded.initial_state,
        initial_mode=decoded.initial_mode,
        settings=decoded.integrator_settings,
        reporting_settings=decoded.reporting_settings,
    )
    payload = project_simulation_result(result)

    (ARTIFACTS / "result.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report_csv(payload, ARTIFACTS / "report.csv")

    columns = column_map(payload)
    time = require_column(columns, "time_s")
    primary_rpm = (
        require_column(columns, "state.primary_angular_speed") * RAD_PER_S_TO_RPM
    )
    vehicle_speed_kmh = require_column(columns, "vehicle.speed") * 3.6
    distance = require_column(columns, "vehicle.distance")
    grade_deg = np.degrees(require_column(columns, "vehicle.grade_angle"))
    shift_mm = require_column(columns, "state.shift_position") * 1000.0
    primary_radius = require_column(columns, "geometry.primary_effective_radius")
    secondary_radius = require_column(columns, "geometry.secondary_effective_radius")
    ratio = secondary_radius / primary_radius
    primary_clamp = require_column(
        columns, "actuation.primary.total_clamp_force"
    )
    secondary_clamp = require_column(
        columns, "actuation.secondary.total_clamp_force"
    )

    save_time_plot(
        time,
        [(primary_rpm, "Primary")],
        ylabel="Primary speed (rpm)",
        title="Primary shaft speed",
        filename="primary_speed_rpm.png",
    )
    save_time_plot(
        time,
        [(vehicle_speed_kmh, "Vehicle")],
        ylabel="Vehicle speed (km/h)",
        title="Vehicle speed",
        filename="vehicle_speed_kmh.png",
    )
    save_time_plot(
        time,
        [(ratio, "CVT ratio")],
        ylabel="Reduction ratio",
        title="CVT effective-radius ratio",
        filename="cvt_ratio.png",
    )
    save_time_plot(
        time,
        [(shift_mm, "Shift")],
        ylabel="Shift position (mm)",
        title="Primary shift position",
        filename="shift_position_mm.png",
    )
    save_time_plot(
        time,
        [(primary_clamp, "Primary"), (secondary_clamp, "Secondary")],
        ylabel="Clamp force (N)",
        title="Pulley clamp forces",
        filename="clamp_forces_N.png",
    )

    fig, ax = plt.subplots()
    ax.plot(distance, grade_deg)
    ax.set_xlabel("Vehicle distance (m)")
    ax.set_ylabel("Road grade (deg)")
    ax.set_title("Road grade profile encountered")
    ax.grid(True)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "road_grade_deg.png", dpi=180)
    plt.close(fig)

    summary = {
        "study": spec,
        "cinder_version": cinder.__version__,
        "cinder_module_path": str(Path(cinder.__file__).resolve()),
        "termination_reason": payload["metrics"]["termination_reason"],
        "completed": result.completed,
        "transition_count": len(payload["transitions"]),
        "report_row_count": payload["report_table"]["row_count"],
        "warnings": payload["warnings"],
        "final_vehicle_distance_m": float(distance[-1]),
        "final_vehicle_speed_kmh": float(vehicle_speed_kmh[-1]),
    }
    (ARTIFACTS / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"CINDER {cinder.__version__}")
    print(f"Termination: {summary['termination_reason']}")
    print(f"Transitions: {summary['transition_count']}")
    print(f"Final distance: {summary['final_vehicle_distance_m']:.3f} m")
    print(f"Final speed: {summary['final_vehicle_speed_kmh']:.3f} km/h")
    print(f"Artifacts: {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
