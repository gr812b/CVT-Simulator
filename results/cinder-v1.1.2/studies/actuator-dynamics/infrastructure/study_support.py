from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

STUDY_ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = STUDY_ROOT.parents[1]
ARTIFACTS = STUDY_ROOT / "artifacts"
STUDY_FILE = STUDY_ROOT / "study.json"
VERIFY_ENVIRONMENT = RELEASE_ROOT / "verify_environment.py"
EXPECTED_VERSION = "1.1.2"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))












def verify_environment() -> None:
    subprocess.run([sys.executable, str(VERIFY_ENVIRONMENT)], check=True)
    import cinder
    if cinder.__version__ != EXPECTED_VERSION:
        raise RuntimeError(
            f"Expected cinder-cvt=={EXPECTED_VERSION}, found {cinder.__version__} "
            f"from {Path(cinder.__file__).resolve()}."
        )


def reset_artifacts() -> None:
    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)




def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def finite_float(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def max_abs(rows: list[dict[str, Any]], key: str, *, predicate=None) -> float | None:
    vals = []
    for row in rows:
        if predicate is not None and not predicate(row):
            continue
        x = finite_float(row.get(key))
        if x is not None:
            vals.append(abs(x))
    return max(vals) if vals else None


def percentile_abs(rows: list[dict[str, Any]], key: str, percentile: float, *, predicate=None):
    import numpy as np
    vals = []
    for row in rows:
        if predicate is not None and not predicate(row):
            continue
        x = finite_float(row.get(key))
        if x is not None:
            vals.append(abs(x))
    return float(np.percentile(vals, percentile)) if vals else None










def load_study_modules():
    """Return study-local inspection/ablation code and shared Baja defaults."""
    from . import ablation_core as ab
    from defaults.baja import reference as route
    return ab, route


def copy_provenance() -> None:
    out = ARTIFACTS / "provenance"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STUDY_FILE, out / "study.json")
    policy = RELEASE_ROOT / "defaults" / "reference_model" / "policy.json"
    if policy.is_file():
        shutil.copy2(policy, out / "reference_model_policy.json")
