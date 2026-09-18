"""Prepare benchmark-ready Ballew reference CSVs from raw digitization exports.

The files in ``digitization/`` are immutable provenance copies of the manual
WebPlotDigitizer exports. This script performs only the deterministic cleanup
required by the benchmark:

* add explicit column headers;
* keep the Figure 41 input/output traces on their native time grids;
* collapse exact duplicate Figure 45 time coordinates by arithmetic mean;
* prepend a t=0 Figure 45 sample using a zero-order hold of the first visible
  force point because the published curve begins near 0.1 s.

No smoothing, resampling, curve fitting, or controller reconstruction is done.
Use ``--check`` to verify that the committed benchmark-ready CSVs are exactly
reproducible from the raw digitization files without modifying them.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from io import StringIO
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed prepared CSVs instead of rewriting them",
    )
    return parser.parse_args()


def prepare() -> dict[Path, tuple[str, list[tuple[float, float]]]]:
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

    return {
        INPUT_RPM: ("input_rpm", input_rpm),
        OUTPUT_RPM: ("output_rpm", output_rpm),
        PRIMARY_FORCE: ("primary_axial_force_n", force_clean),
    }


def main() -> int:
    args = parse_args()
    prepared = prepare()

    if args.check:
        mismatches: list[str] = []
        for path, (value_name, rows) in prepared.items():
            expected = _render_xy(value_name, rows)
            if not path.exists():
                mismatches.append(f"missing {path.name}")
                continue
            actual = path.read_text(encoding="utf-8")
            # csv.writer uses platform newline by default, so normalize only line
            # endings for this textual reproducibility check.
            if actual.replace("\r\n", "\n") != expected.replace("\r\n", "\n"):
                mismatches.append(f"{path.name} differs from regenerated data")
        if mismatches:
            raise SystemExit("Reference preparation check failed: " + "; ".join(mismatches))
        print("Reference preparation check passed.")
        return 0

    for path, (value_name, rows) in prepared.items():
        _write_xy(path, value_name, rows)
        print(f"wrote {path.name}: {len(rows)} points")
    return 0


def _read_headerless_xy(path: Path) -> list[tuple[float, float]]:
    if _is_lfs_pointer(path):
        raise RuntimeError(
            f"{path} is not materialized reference data in this checkout."
        )
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


def _is_lfs_pointer(path: Path) -> bool:
    try:
        return path.read_bytes()[:128].startswith(
            b"version https://git-lfs.github.com/spec/v1"
        )
    except OSError:
        return False


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


def _render_xy(value_name: str, rows: list[tuple[float, float]]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(("time_s", value_name))
    writer.writerows(rows)
    return stream.getvalue()


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
    raise SystemExit(main())
