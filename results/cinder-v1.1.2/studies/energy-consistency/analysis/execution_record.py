"""Portable input/output identity for a completed energy-consistency run.

Generated evidence stays in ignored artifacts/. The record travels with those
artifacts, so plot-only regeneration need not trust a filename or a recap PDF.
"""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess

STUDY = Path(__file__).resolve().parents[1]
RELEASE = STUDY.parents[1]
REPOSITORY = RELEASE.parents[1]
PACKAGES = ("cinder-cvt", "numpy", "scipy", "matplotlib")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture_inputs() -> dict[str, bytes]:
    paths = [STUDY / "run.py", STUDY / "study.json", RELEASE / "requirements.txt",
             RELEASE / "verify_environment.py", Path(__file__).resolve()]
    paths += sorted((STUDY / "infrastructure").glob("*.py"))
    paths += sorted((RELEASE / "defaults").rglob("*.py"))
    paths += sorted((RELEASE / "defaults").rglob("*.json"))
    return {p.relative_to(REPOSITORY).as_posix(): p.read_bytes() for p in paths}


def write_execution_record(artifacts: Path, inputs: dict[str, bytes], *,
                           command: str, source_commit: str | None = None,
                           note: str = "") -> dict:
    if source_commit is None:
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True
        ).strip()
    snapshot_hashes = {}
    for name, content in inputs.items():
        target = artifacts / "execution_inputs" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        snapshot_hashes[name] = hashlib.sha256(content).hexdigest()
    outputs = {p.name: digest(p) for p in sorted(artifacts.iterdir())
               if p.is_file() and p.suffix in (".json", ".csv")
               and p.name != "execution_provenance.json"}
    identity = hashlib.sha256(json.dumps(
        {"inputs": snapshot_hashes, "outputs": outputs}, sort_keys=True
    ).encode()).hexdigest()
    record = {
        "schema_version": 1,
        "run_id": "energy-consistency-" + identity[:16],
        "repository": "gr812b/CVT-Simulator",
        "source_commit": source_commit,
        "source_identity_note": "Exact executed input bytes below supplement the parent commit; the working tree may contain uncommitted changes.",
        "mechanics_tag": "cinder-v1.1.2",
        "mechanics_commit": "7637a38b4fb9ec21dfb953c1c80a27ec5f389654",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {p: metadata.version(p) for p in PACKAGES},
        "installed_distributions": {d.metadata["Name"]: d.version for d in metadata.distributions()},
        "command": command,
        "note": note,
        "input_sha256": snapshot_hashes,
        "output_sha256": outputs,
    }
    (artifacts / "execution_provenance.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record


def verify_execution_record(artifacts: Path) -> dict:
    path = artifacts / "execution_provenance.json"
    if not path.is_file():
        raise ValueError("Missing execution_provenance.json; run canonical run.py to generate identified evidence.")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record["packages"] != {p: metadata.version(p) for p in PACKAGES}:
        raise ValueError("Plot environment differs from the recorded frozen environment.")
    if record["mechanics_commit"] != "7637a38b4fb9ec21dfb953c1c80a27ec5f389654":
        raise ValueError("Wrong mechanics source identity.")
    for name, expected in record["input_sha256"].items():
        if digest(artifacts / "execution_inputs" / name) != expected:
            raise ValueError(f"Changed execution input: {name}")
    for name, expected in record["output_sha256"].items():
        if digest(artifacts / name) != expected:
            raise ValueError(f"Changed execution output: {name}")
    # Refuse silent drift in the accounting code or frozen inputs used to
    # interpret the saved evidence. Plot styling is deliberately separate.
    for path in (STUDY / "run.py", STUDY / "study.json",
                 STUDY / "infrastructure" / "energy_accounting.py"):
        name = path.relative_to(REPOSITORY).as_posix()
        if digest(path) != record["input_sha256"][name]:
            raise ValueError(f"Current study input differs from executed snapshot: {name}")
    return record
