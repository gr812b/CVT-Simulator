"""Reference-data loading and integrity checks for the Ballew benchmark."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

REFERENCE_MANIFEST = "manifest.json"


@dataclass(frozen=True, slots=True)
class ReferenceSeries:
    time_s: NDArray[np.float64]
    value: NDArray[np.float64]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    try:
        head = path.read_bytes()[:128]
    except OSError:
        return False
    return head.startswith(b"version https://git-lfs.github.com/spec/v1")


def load_reference_manifest(reference_dir: Path) -> dict[str, object]:
    manifest_path = reference_dir / REFERENCE_MANIFEST
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _validate_hashed_file(path: Path, expected: dict[str, object]) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    if is_lfs_pointer(path):
        raise RuntimeError(
            f"{path} is not materialized data in this checkout."
        )
    expected_size = expected.get("size_bytes")
    if expected_size is not None and path.stat().st_size != int(expected_size):
        raise RuntimeError(
            f"Reference size mismatch for {path.name}: "
            f"{path.stat().st_size} != {expected_size}"
        )
    expected_sha = expected.get("sha256")
    if expected_sha is not None:
        actual = sha256(path)
        if actual != expected_sha:
            raise RuntimeError(
                f"Reference SHA-256 mismatch for {path.name}: "
                f"{actual} != {expected_sha}"
            )


def validate_reference_data(*, study_root: Path) -> Path:
    """Validate and return this study's self-contained reference directory."""

    reference_dir = study_root / "reference"
    manifest = load_reference_manifest(reference_dir)
    prepared = manifest.get("prepared_reference_files", {})
    if not isinstance(prepared, dict) or not prepared:
        raise RuntimeError("Reference manifest has no prepared_reference_files.")

    for name, expected in prepared.items():
        if not isinstance(expected, dict):
            raise RuntimeError(f"Invalid manifest entry for {name}.")
        _validate_hashed_file(reference_dir / name, expected)
    return reference_dir


def reference_hash_document(reference_dir: Path) -> dict[str, object]:
    """Return the hashes of the exact benchmark-ready files used by a run."""

    manifest = load_reference_manifest(reference_dir)
    prepared = manifest["prepared_reference_files"]
    payload: dict[str, object] = {}
    for name, expected in prepared.items():
        path = reference_dir / name
        _validate_hashed_file(path, expected)
        payload[name] = {
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
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
    input_rpm: ReferenceSeries,
    output_rpm: ReferenceSeries,
) -> ReferenceSeries:
    """Build a ratio trace on the union of the two native Figure 41 grids."""

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
