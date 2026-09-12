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

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
REPO_ROOT = STUDY_ROOT.parents[3]
ARTIFACTS = STUDY_ROOT / "artifacts"
WORK = STUDY_ROOT / "work"
UPSTREAM_ROOT = WORK / "upstream"
MANIFEST_FILE = STUDY_ROOT / "upstream_manifest.json"
STUDY_FILE = STUDY_ROOT / "study.json"
VERIFY_ENVIRONMENT = RELEASE_ROOT / "verify_environment.py"
EXPECTED_VERSION = "1.1.2"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        capture_output=True,
    )


def verify_release_tag() -> str:
    manifest = load_json(MANIFEST_FILE)
    tag = manifest["release_tag"]
    expected = manifest["release_commit_sha"]
    actual = _git("rev-parse", f"{tag}^{{commit}}").stdout.decode().strip()
    if actual != expected:
        raise RuntimeError(f"{tag} resolves to {actual}, expected {expected}.")
    return actual


def materialize_tagged_upstream(*, clean: bool = True) -> Path:
    manifest = load_json(MANIFEST_FILE)
    tag = manifest["release_tag"]
    verify_release_tag()

    if clean and UPSTREAM_ROOT.exists():
        shutil.rmtree(UPSTREAM_ROOT)
    UPSTREAM_ROOT.mkdir(parents=True, exist_ok=True)

    for item in manifest["files"]:
        data = _git("show", f"{tag}:{item['path']}").stdout
        actual = git_blob_sha(data)
        if actual != item["git_blob_sha"]:
            raise RuntimeError(
                f"Blob mismatch for {item['path']}: {actual} != {item['git_blob_sha']}"
            )
        target = UPSTREAM_ROOT / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    return UPSTREAM_ROOT / "cvtModel" / "launchTools"


def load_tagged_modules():
    launch_tools = materialize_tagged_upstream(clean=False)
    if str(launch_tools) not in sys.path:
        sys.path.insert(0, str(launch_tools))
    import run_dynamic_actuator_ablation as ab
    import run_route_grade_response as route
    return launch_tools, ab, route


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


def run_tagged_tool(script_name: str, args: list[str], output_dir: Path) -> dict[str, Any]:
    launch_tools = materialize_tagged_upstream(clean=False)
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(launch_tools / script_name),
        "--output-dir",
        str(output_dir),
        *args,
    ]
    env = dict(os.environ)
    env["MPLBACKEND"] = "Agg"
    print("$ " + " ".join(command))
    subprocess.run(command, cwd=str(launch_tools), check=True, env=env)
    return {"script": script_name, "command": command, "output_dir": str(output_dir)}


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


def copy_provenance() -> None:
    out = ARTIFACTS / "provenance"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STUDY_FILE, out / "study.json")
    shutil.copy2(MANIFEST_FILE, out / "upstream_manifest.json")
