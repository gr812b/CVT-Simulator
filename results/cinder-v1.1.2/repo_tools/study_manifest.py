# Common manifest validation for the CINDER v1.1.2 results tree.
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED = (
    "results_manifest_schema", "study_slug", "title", "maintenance_status",
    "paper_role", "classification", "cinder_release", "scientific_question",
    "reference_model", "entrypoints", "outputs",
)
VALID_CLASSIFICATIONS = {"verification", "benchmark", "mechanism", "system", "design"}


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_manifest(path: Path) -> list[str]:
    path = Path(path)
    errors: list[str] = []
    try:
        data = load_manifest(path)
    except Exception as exc:
        return [f"{path}: could not read JSON: {exc}"]

    for key in REQUIRED:
        if key not in data:
            errors.append(f"{path}: missing required key {key!r}")
    if data.get("results_manifest_schema") != 1:
        errors.append(f"{path}: results_manifest_schema must be 1")
    if data.get("maintenance_status") != "maintained":
        errors.append(f"{path}: maintained study should use maintenance_status='maintained'")
    if data.get("classification") not in VALID_CLASSIFICATIONS:
        errors.append(f"{path}: invalid classification {data.get('classification')!r}")

    release = data.get("cinder_release", {})
    expected = {
        "distribution": "cinder-cvt",
        "version": "1.1.2",
        "source_tag": "cinder-v1.1.2",
        "source_commit_sha": "7637a38b4fb9ec21dfb953c1c80a27ec5f389654",
    }
    for key, value in expected.items():
        if release.get(key) != value:
            errors.append(f"{path}: cinder_release.{key} must be {value!r}")

    study_root = path.parent
    if data.get("study_slug") != study_root.name:
        errors.append(f"{path}: study_slug must match directory name {study_root.name!r}")
    entry = data.get("entrypoints", {})
    run = entry.get("run")
    verify = entry.get("verify")
    if not run or not (study_root / run).is_file():
        errors.append(f"{path}: canonical run entry point is missing: {run!r}")
    if verify is not None and not (study_root / verify).is_file():
        errors.append(f"{path}: declared verify entry point is missing: {verify!r}")

    return errors
