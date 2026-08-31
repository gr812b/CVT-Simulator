"""Prepare benchmark-ready Ballew reference CSVs from raw WebPlotDigitizer exports.

The files in ``digitization/`` are immutable provenance copies of the user's
manual digitization. This script performs only the small deterministic cleanup
needed by CINDER's benchmark readers:

* add explicit column headers;
* keep the Figure 41 input/output traces on their own native time grids;
* collapse exact duplicate Figure 45 time coordinates by arithmetic mean;
* prepend a t=0 Figure 45 sample using a zero-order hold of the first visible
  force point because the published curve begins near 0.1 s.

No smoothing, resampling, curve fitting, or controller reconstruction is done.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from math import isfinite
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "digitization"

RAW_INPUT_RPM = RAW / "input_rpm.csv"
RAW_OUTPUT_RPM = RAW / "output_rpm.csv"
RAW_AXIAL_FORCE = RAW / "axial_force.csv"

INPUT_RPM = ROOT / "figure_41_input_rpm.csv"
OUTPUT_RPM = ROOT / "figure_41_output_rpm.csv"
PRIMARY_FORCE = ROOT / "figure_45_primary_force.csv"


def main() -> None:
    input_rpm = _read_headerless_xy(RAW_INPUT_RPM)
    output_rpm = _read_headerless_xy(RAW_OUTPUT_RPM)
    axial_force = _read_headerless_xy(RAW_AXIAL_FORCE)

    _require_strictly_increasing(input_rpm, RAW_INPUT_RPM.name)
    _require_strictly_increasing(output_rpm, RAW_OUTPUT_RPM.name)
    _require_nondecreasing(axial_force, RAW_AXIAL_FORCE.name)

    force_clean = _mean_duplicate_times(axial_force)
    _require_strictly_increasing(force_clean, "cleaned axial force")

    # Reconstruction A6: Figure 45 visibly starts near 0.1 s, but the prescribed
    # input must exist at simulation t=0. Hold the first visible force backward
    # over this short unsupported interval rather than inventing a slope.
    if force_clean[0][0] > 0.0:
        force_clean = [(0.0, force_clean[0][1]), *force_clean]

    _write_xy(INPUT_RPM, "input_rpm", input_rpm)
    _write_xy(OUTPUT_RPM, "output_rpm", output_rpm)
    _write_xy(PRIMARY_FORCE, "primary_axial_force_n", force_clean)

    print(f"wrote {INPUT_RPM.name}: {len(input_rpm)} points")
    print(f"wrote {OUTPUT_RPM.name}: {len(output_rpm)} points")
    print(f"wrote {PRIMARY_FORCE.name}: {len(force_clean)} points")


def _read_headerless_xy(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream)
        for line_number, row in enumerate(reader, start=1):
            if not row:
                continue
            if len(row) != 2:
                raise ValueError(f"{path.name}:{line_number}: expected two columns.")
            x = float(row[0].strip())
            y = float(row[1].strip())
            if not isfinite(x) or not isfinite(y):
                raise ValueError(f"{path.name}:{line_number}: values must be finite.")
            rows.append((x, y))
    if len(rows) < 2:
        raise ValueError(f"{path.name} must contain at least two points.")
    return rows


def _require_strictly_increasing(
    rows: list[tuple[float, float]], name: str
) -> None:
    if any(right[0] <= left[0] for left, right in zip(rows, rows[1:])):
        raise ValueError(f"{name} time coordinates must be strictly increasing.")


def _require_nondecreasing(
    rows: list[tuple[float, float]], name: str
) -> None:
    if any(right[0] < left[0] for left, right in zip(rows, rows[1:])):
        raise ValueError(f"{name} time coordinates must be nondecreasing.")


def _mean_duplicate_times(
    rows: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    grouped: dict[float, list[float]] = defaultdict(list)
    order: list[float] = []
    for time_s, value in rows:
        if time_s not in grouped:
            order.append(time_s)
        grouped[time_s].append(value)
    return [
        (time_s, sum(grouped[time_s]) / len(grouped[time_s]))
        for time_s in order
    ]


def _write_xy(
    path: Path,
    value_name: str,
    rows: list[tuple[float, float]],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("time_s", value_name))
        writer.writerows(rows)


if __name__ == "__main__":
    main()
