"""Static and reference-integrity checks for the Ballew results study."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "reference"
MANIFEST = REFERENCE / "manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    digest = hashlib.sha1()
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    try:
        return path.read_bytes()[:128].startswith(
            b"version https://git-lfs.github.com/spec/v1"
        )
    except OSError:
        return False


def _required_files() -> list[Path]:
    return [
        ROOT / "README.md",
        ROOT / "study.json",
        ROOT / "run.py",
        ROOT / "run_controller_reconstruction.py",
        ROOT / "run_convergence.py",
        ROOT / "run_stability_sweep.py",
        ROOT / "benchmark" / "actuation.py",
        ROOT / "benchmark" / "belt.py",
        ROOT / "benchmark" / "case.py",
        ROOT / "benchmark" / "constants.py",
        ROOT / "benchmark" / "controller.py",
        ROOT / "benchmark" / "metrics.py",
        ROOT / "benchmark" / "reference.py",
        ROOT / "benchmark" / "simulation.py",
        ROOT / "provenance" / "RECONSTRUCTION.md",
        ROOT / "provenance" / "CINDER_FIXES.md",
        ROOT / "provenance" / "NUMERICAL_STABILITY.md",
        REFERENCE / "README.md",
        REFERENCE / "prepare_reference_data.py",
        REFERENCE / "digitization" / "README.md",
        REFERENCE / "digitization" / "input_rpm.csv",
        REFERENCE / "digitization" / "output_rpm.csv",
        REFERENCE / "digitization" / "axial_force.csv",
        REFERENCE / "digitization" / "rpms_ballew.json",
        REFERENCE / "digitization" / "axial_force_ballew.json",
        REFERENCE / "figure_41_input_rpm.csv",
        REFERENCE / "figure_41_output_rpm.csv",
        REFERENCE / "figure_45_primary_force.csv",
        REFERENCE / "source" / "Ballew_2015_thesis.pdf",
        REFERENCE / "source" / "README.md",
        MANIFEST,
    ]


def _verify_manifest() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    groups = (
        (REFERENCE, manifest["prepared_reference_files"]),
        (REFERENCE / "digitization", manifest["raw_digitization_files"]),
    )
    for directory, entries in groups:
        for name, expected in entries.items():
            path = directory / name
            if is_lfs_pointer(path):
                raise RuntimeError(f"{path.relative_to(ROOT)} is not materialized data.")
            expected_size = expected.get("size_bytes")
            if expected_size is not None and path.stat().st_size != int(expected_size):
                raise RuntimeError(
                    f"size mismatch for {path.relative_to(ROOT)}: "
                    f"{path.stat().st_size} != {expected_size}"
                )
            expected_sha = expected.get("sha256")
            if expected_sha is not None:
                actual = sha256(path)
                if actual != expected_sha:
                    raise RuntimeError(
                        f"SHA-256 mismatch for {path.relative_to(ROOT)}: "
                        f"{actual} != {expected_sha}"
                    )
            expected_blob = expected.get("git_blob_sha1")
            if expected_blob is not None:
                actual_blob = git_blob_sha1(path)
                if actual_blob != expected_blob:
                    raise RuntimeError(
                        f"Git-blob mismatch for {path.relative_to(ROOT)}: "
                        f"{actual_blob} != {expected_blob}"
                    )

    source = manifest["source_thesis"]
    thesis = REFERENCE / "source" / "Ballew_2015_thesis.pdf"
    if thesis.stat().st_size != int(source["size_bytes"]):
        raise RuntimeError("Ballew thesis size mismatch.")
    actual_thesis_sha = sha256(thesis)
    if actual_thesis_sha != source["sha256"]:
        raise RuntimeError(
            f"Ballew thesis SHA-256 mismatch: {actual_thesis_sha}"
        )


def _verify_no_old_runtime_dependencies() -> None:
    forbidden = (
        "sys.path.insert",
        "cvtModel/src",
        "launchTools/literature/ballew_2015",
        "migrate_legacy",
        "historical_v1_0_0",
        "historical-v1.0.0",
    )
    candidates = [
        ROOT / "run.py",
        ROOT / "run_controller_reconstruction.py",
        ROOT / "run_convergence.py",
        ROOT / "run_stability_sweep.py",
        *sorted((ROOT / "benchmark").glob("*.py")),
    ]
    failures: list[str] = []
    for path in candidates:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in text:
                failures.append(
                    f"{path.relative_to(ROOT)} contains forbidden runtime dependency {needle!r}"
                )
    if failures:
        raise RuntimeError("\n".join(failures))


def main() -> int:
    missing = [
        str(path.relative_to(ROOT))
        for path in _required_files()
        if not path.exists()
    ]
    if missing:
        print(
            "Missing required Ballew study files: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1

    try:
        _verify_manifest()
        _verify_no_old_runtime_dependencies()
        subprocess.run(
            [
                sys.executable,
                str(REFERENCE / "prepare_reference_data.py"),
                "--check",
            ],
            check=True,
        )
    except Exception as exc:
        print(f"Ballew study verification failed: {exc}", file=sys.stderr)
        return 1

    print("Ballew study verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
