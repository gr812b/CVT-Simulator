"""Registered retained evidence and one selected, reproducible history replay.

The historical formal/dense sweeps are not silently rerun or renamed. Only the
different-signature median example lacked a saved trajectory and is integrated.
Archive member hashes, original configuration bytes, and replay inputs travel
with the ignored artifacts. Plot-only operations do not integrate CINDER.
"""
from __future__ import annotations

import csv
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import zipfile

import numpy as np

STUDY = Path(__file__).resolve().parents[1]
RELEASE = STUDY.parents[1]
REPO = RELEASE.parents[1]
REGISTER = STUDY / "provenance" / "retained_archives.json"
GROSS_KEYS = ("primary_omega_rad_s", "secondary_omega_rad_s", "belt_speed_m_s", "shift_m")
REFERENCE_KEY = "2c128c4eb06b60ec"
CANONICAL_KEY = "31d6f0938ba3b03a"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=True) + "\n")


def rows(path):
    with Path(path).open(newline="") as stream:
        out = list(csv.DictReader(stream))
    for row in out:
        for key, value in row.items():
            if value in ("True", "False"):
                row[key] = value == "True"
            elif value:
                try:
                    row[key] = float(value)
                except ValueError:
                    pass
    return out


def gross_rms(row):
    """Historical four-state, absolute-time sample RMS; NOT the formal norm."""
    return math.sqrt(sum(float(row[f"raw_time_{k}_rms_normalized"]) ** 2
                         for k in GROSS_KEYS) / len(GROSS_KEYS))


def selected_row(dense):
    eligible = [r for r in dense if r["run_status"] == "completed"
                and not r["transition_signature_match"]]
    eligible.sort(key=lambda r: (gross_rms(r), r["relative_tolerance"], r["max_step"]))
    if len(eligible) != 609:
        raise ValueError("Registered dense population no longer contains 609 different-signature runs.")
    return eligible[len(eligible) // 2]


def capture_inputs():
    paths = [STUDY / "run.py", STUDY / "study.json", REGISTER,
             Path(__file__), RELEASE / "requirements.txt", RELEASE / "verify_environment.py"]
    paths += sorted((RELEASE / "defaults").rglob("*.py"))
    paths += sorted((RELEASE / "defaults").rglob("*.json"))
    return {p.relative_to(REPO).as_posix(): p.read_bytes() for p in paths}


def import_archive(source, kind, artifacts):
    spec = read_json(REGISTER)[kind]
    if digest(source) != spec["sha256"]:
        raise ValueError(f"Wrong {kind} archive; exact registered bytes required.")
    members = {}
    with zipfile.ZipFile(source) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            if kind == "formal":
                if Path(name).suffix not in (".csv", ".json", ".md"):
                    continue
                relative = Path(name).relative_to("artifacts")
                target = artifacts / relative
            else:
                relative = Path(name).relative_to("dense-overnight")
                if relative.parts[0] == "plots":
                    continue
                target = artifacts / "retained_dense" / relative
            if ".." in relative.parts or relative.is_absolute():
                raise ValueError("Unsafe archive member.")
            content = archive.read(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != content:
                raise ValueError(f"Refusing to overwrite different retained evidence: {target}")
            target.write_bytes(content)
            members[name] = hashlib.sha256(content).hexdigest()
    return {**spec, "member_sha256": members}


def prepare_retained(formal, formal_zip, dense_zip):
    artifacts = formal.ARTIFACTS
    artifacts.mkdir(parents=True, exist_ok=True)
    sources = {"formal": import_archive(formal_zip, "formal", artifacts),
               "dense": import_archive(dense_zip, "dense", artifacts)}
    write_json(artifacts / "retained_sources.json", sources)
    # The old byte hash is exactly the current case with CRLF newlines. This is
    # stronger than merely comparing JSON objects or trusting the stale locator.
    source = (STUDY / formal.load_json(formal.SPEC_FILE)["base_document"]).resolve()
    old_hash = read_json(artifacts / "summary.json")["reference"]["base_document_sha256"]
    if hashlib.sha256(source.read_bytes().replace(b"\n", b"\r\n")).hexdigest() != old_hash:
        raise ValueError("Historical case identity cannot be resolved by the recorded newline conversion.")
    snapshot = capture_inputs()
    selected = selected_row(rows(artifacts / "retained_dense" / "dense_sweep.csv"))
    spec = formal.load_json(formal.SPEC_FILE)
    cfg = formal.config(spec, rtol=selected["relative_tolerance"],
                        atol=selected["absolute_tolerance"], max_step=selected["max_step"],
                        comparison_step=selected["comparison_step_s"])
    replay = formal.run_cached(spec, cfg)
    destination = artifacts / "selected_history"
    destination.mkdir(exist_ok=True)
    for path in replay.iterdir():
        if path.is_file():
            shutil.copy2(path, destination / path.name)
    reference = artifacts / "retained_dense" / "cache" / REFERENCE_KEY
    scales = read_json(artifacts / "state_normalization_scales.json")
    actual = formal.compare_cache(destination, reference, scales, spec["review_guards"])
    if actual["transition_signature_match"] or actual["transition_count"] != selected["transition_count"]:
        raise ValueError("Selected replay did not recover the intended different history.")
    write_json(artifacts / "selection.json", {
        "rule": "Median four-state absolute-time RMS among 609 completed different-signature dense rows; selected before trajectory replay.",
        "archived_row": selected, "replay_metrics": actual, "replay_config": cfg,
        "reference_cache": f"retained_dense/cache/{REFERENCE_KEY}",
        "canonical_cache": f"retained_dense/cache/{CANONICAL_KEY}",
        "selected_cache": "selected_history",
        "historical_case_hash_resolved_as": "current simulation_case.json bytes with LF converted to CRLF",
    })
    for name, content in snapshot.items():
        target = artifacts / "execution_inputs" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    record_evidence(artifacts, formal_origin="retained artifacts(3).zip, revision 4")


def record_evidence(artifacts, *, formal_origin):
    if not (artifacts / "selection.json").is_file():
        raise ValueError("Selected-history evidence missing. Import registered archives with --import-retained first.")
    outputs = {}
    for path in sorted(artifacts.rglob("*")):
        relative = path.relative_to(artifacts)
        if not path.is_file() or relative.parts[0] in ("publication", "execution_inputs", "formal_execution_inputs", "formal_recomputed", "quick"):
            continue
        if path.suffix not in (".json", ".csv", ".npz") or path.name == "execution_provenance.json":
            continue
        outputs[relative.as_posix()] = digest(path)
    inputs = {p.relative_to(artifacts / "execution_inputs").as_posix(): digest(p)
              for p in sorted((artifacts / "execution_inputs").rglob("*")) if p.is_file()}
    formal_inputs = {p.relative_to(artifacts / "formal_execution_inputs").as_posix(): digest(p)
                     for p in sorted((artifacts / "formal_execution_inputs").rglob("*")) if p.is_file()}
    identity_inputs = {"inputs": inputs, "outputs": outputs}
    if formal_inputs:
        identity_inputs["formal_inputs"] = formal_inputs
    identity = hashlib.sha256(json.dumps(identity_inputs, sort_keys=True).encode()).hexdigest()
    record = {
        "schema_version": 1, "run_id": "solver-convergence-" + identity[:16],
        "formal_origin": formal_origin,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "mechanics_version": "1.1.2", "mechanics_commit": "7637a38b4fb9ec21dfb953c1c80a27ec5f389654",
        "replay_python": platform.python_version(), "replay_platform": platform.platform(),
        "replay_packages": {p: metadata.version(p) for p in ("cinder-cvt", "numpy", "scipy", "matplotlib")},
        "historical_environment_note": "Archives identify CINDER 1.1.2 and LSODA; original complete package lock and machine are not supplied. Current replay versions do not retroactively describe the archived sweep.",
        "input_sha256": inputs, "output_sha256": outputs,
        "formal_input_sha256": formal_inputs,
    }
    write_json(artifacts / "execution_provenance.json", record)
    return record


def record_formal_execution(artifacts, snapshot, reference_path, canonical_path, *, run_mode):
    """Keep a newly computed sweep separate; do not silently promote it."""
    for name, content in snapshot.items():
        target = artifacts / "execution_inputs" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    for name, source in (("reference", reference_path), ("canonical", canonical_path)):
        shutil.copytree(source, artifacts / name, dirs_exist_ok=True)
    inputs = {name: hashlib.sha256(content).hexdigest() for name, content in snapshot.items()}
    outputs = {p.relative_to(artifacts).as_posix(): digest(p)
               for p in sorted(artifacts.rglob("*")) if p.is_file()
               and p.suffix in (".csv", ".json", ".npz")
               and "execution_inputs" not in p.relative_to(artifacts).parts
               and p.name != "execution_provenance.json"}
    identity = hashlib.sha256(json.dumps({"inputs": inputs, "outputs": outputs}, sort_keys=True).encode()).hexdigest()
    write_json(artifacts / "execution_provenance.json", {
        "schema_version": 1, "run_id": f"solver-convergence-{run_mode}-" + identity[:16],
        "status": "New formal execution; not silently substituted for reviewed retained evidence.",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "mechanics_version": "1.1.2", "mechanics_commit": "7637a38b4fb9ec21dfb953c1c80a27ec5f389654",
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": {p: metadata.version(p) for p in ("cinder-cvt", "numpy", "scipy", "matplotlib")},
        "input_sha256": inputs, "output_sha256": outputs,
    })


def verify_record(artifacts):
    record = read_json(artifacts / "execution_provenance.json")
    for group, root in (("input_sha256", artifacts / "execution_inputs"), ("output_sha256", artifacts)):
        for name, expected in record[group].items():
            if digest(root / name) != expected:
                raise ValueError(f"Changed evidence: {name}")
    for name, expected in record.get("formal_input_sha256", {}).items():
        if digest(artifacts / "formal_execution_inputs" / name) != expected:
            raise ValueError(f"Changed formal execution input: {name}")
    if record["mechanics_commit"] != "7637a38b4fb9ec21dfb953c1c80a27ec5f389654":
        raise ValueError("Wrong mechanics source identity.")
    return record
