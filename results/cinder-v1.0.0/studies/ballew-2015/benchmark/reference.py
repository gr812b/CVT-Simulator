"""Reference-data discovery and integrity checks for the Ballew benchmark."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


REFERENCE_FILES = {
    "figure_41_input_rpm.csv": {
        "sha256": "ad16629a0cefd308e7df0d4c79b00a08f295a7efff2cbf0f4173dca1929e0dd9",
        "size": 4325,
        "value_column": "input_rpm",
    },
    "figure_41_output_rpm.csv": {
        "sha256": "47dc6da83cae77ce0bef49277983120086ed577dcd1c84fdbc4ddb684b154d8a",
        "size": 2467,
        "value_column": "output_rpm",
    },
    "figure_45_primary_force.csv": {
        "sha256": "e61467317a884e0d75a32c52b0688fbaa4bde5fd327b3aaab9625ec16de282e8",
        "size": 7905,
        "value_column": "primary_axial_force_n",
    },
}

SOURCE_PDF_SHA256 = "cafead74895bbfaf092fe0354f0572064f44c6b4ff10c422877c5ae587f8df44"


@dataclass(frozen=True, slots=True)
class ReferenceSeries:
    time_s: NDArray[np.float64]
    value: NDArray[np.float64]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_lfs_pointer(path: Path) -> bool:
    try:
        head = path.read_bytes()[:128]
    except OSError:
        return False
    return head.startswith(b"version https://git-lfs.github.com/spec/v1")


def _validate_one(path: Path, expected: dict[str, object]) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    if _is_lfs_pointer(path):
        raise RuntimeError(
            f"{path} is a Git LFS pointer, not materialized data. Run `git lfs pull`."
        )
    actual = _sha256(path)
    if actual != expected["sha256"]:
        raise RuntimeError(
            f"Reference SHA-256 mismatch for {path.name}: {actual} != {expected['sha256']}"
        )


def materialize_reference_data(*, study_root: Path) -> Path:
    """Return the exact, migrated Ballew reference directory.

    This results study is intentionally self-contained after ``migrate_legacy.py``.
    Runtime fallback to ``cvtModel/launchTools`` is forbidden so the old location
    can be deleted after the migration is verified.
    """

    packaged = study_root / "reference"
    missing: list[str] = []
    for name, expected in REFERENCE_FILES.items():
        path = packaged / name
        if not path.exists():
            missing.append(name)
            continue
        _validate_one(path, expected)
    if missing:
        raise FileNotFoundError(
            "Ballew reference assets are not materialized in the results study: "
            + ", ".join(missing)
            + ". Run `python studies/ballew-2015/migrate_legacy.py` first."
        )
    return packaged


def reference_hash_document(reference_dir: Path) -> dict[str, object]:
    payload: dict[str, object] = {}
    for name, expected in REFERENCE_FILES.items():
        path = reference_dir / name
        _validate_one(path, expected)
        payload[name] = {
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
            "legacy_git_lfs_oid_sha256": expected["sha256"],
        }
    return payload


def load_series(path: Path, *, value_column: str) -> ReferenceSeries:
    times: list[float] = []
    values: list[float] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"time_s", value_column}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise RuntimeError(
                f"{path.name} must contain time_s and {value_column} columns."
            )
        for row in reader:
            times.append(float(row["time_s"]))
            values.append(float(row[value_column]))
    t = np.asarray(times, dtype=float)
    y = np.asarray(values, dtype=float)
    if t.ndim != 1 or t.size < 2 or y.shape != t.shape:
        raise RuntimeError(f"Invalid reference vector in {path}.")
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)):
        raise RuntimeError(f"Non-finite reference data in {path}.")
    if np.any(np.diff(t) <= 0.0):
        raise RuntimeError(f"Reference times must be strictly increasing in {path}.")
    t.setflags(write=False)
    y.setflags(write=False)
    return ReferenceSeries(time_s=t, value=y)


def build_reference_ratio(
    input_rpm: ReferenceSeries, output_rpm: ReferenceSeries
) -> ReferenceSeries:
    start = max(float(input_rpm.time_s[0]), float(output_rpm.time_s[0]))
    end = min(float(input_rpm.time_s[-1]), float(output_rpm.time_s[-1]))
    merged = np.unique(np.r_[input_rpm.time_s, output_rpm.time_s])
    times = merged[(merged >= start) & (merged <= end)]
    input_values = np.interp(times, input_rpm.time_s, input_rpm.value)
    output_values = np.interp(times, output_rpm.time_s, output_rpm.value)
    if np.any(np.abs(output_values) <= 1.0e-12):
        raise RuntimeError("Figure 41 output RPM passes through zero; ratio undefined.")
    ratio = input_values / output_values
    times.setflags(write=False)
    ratio.setflags(write=False)
    return ReferenceSeries(time_s=times, value=ratio)
