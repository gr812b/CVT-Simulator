"""Import registered retained evidence; never silently rerun or overwrite it."""
from __future__ import annotations

import csv
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
import zipfile

STUDY = Path(__file__).resolve().parents[1]
RELEASE = STUDY.parents[1]
REPO = RELEASE.parents[1]
REGISTER = STUDY / "provenance/retained_archives.json"
MECHANICS = "7637a38b4fb9ec21dfb953c1c80a27ec5f389654"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def rows(path):
    with Path(path).open(newline="") as stream:
        result = list(csv.DictReader(stream))
    for row in result:
        for key, value in row.items():
            if value in ("True", "False"):
                row[key] = value == "True"
            elif value:
                try:
                    row[key] = float(value)
                except ValueError:
                    pass
    return result


def write_rows(path, values):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)


def import_archive(source, kind, destination):
    spec = read_json(REGISTER)[kind]
    if digest(source) != spec["sha256"]:
        raise ValueError(f"Wrong {kind} archive; registered exact bytes required.")
    members = {}
    with zipfile.ZipFile(source) as archive:
        for name in archive.namelist():
            if not name.startswith(spec["prefix"]) or name.endswith("/"):
                continue
            relative = Path(name[len(spec["prefix"]):])
            if ".." in relative.parts or relative.is_absolute():
                raise ValueError("Unsafe archive member.")
            if relative.suffix not in (".csv", ".json", ".npz"):
                continue
            # The selected inverse grid is useful; the unrelated 3D volume is not.
            if kind == "two_contact" and (relative.name == "zero_surface_volume.npz"
                                          or len(relative.parts) != 1):
                continue
            target = destination / kind / relative
            content = archive.read(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != content:
                raise ValueError(f"Refusing to replace different evidence: {target}")
            target.write_bytes(content)
            members[name] = hashlib.sha256(content).hexdigest()
    if not members:
        raise ValueError(f"No selected members in {kind} archive.")
    return {**spec, "member_sha256": members}


def input_paths():
    paths = [STUDY / "run.py", STUDY / "study.json", REGISTER,
             RELEASE / "requirements.txt", RELEASE / "verify_environment.py"]
    paths += list((STUDY / "analysis").glob("*.py"))
    paths += list((STUDY / "infrastructure").glob("*.py"))
    paths += list((RELEASE / "defaults").rglob("*.py"))
    paths += list((RELEASE / "defaults").rglob("*.json"))
    return sorted(set(paths))


def prepare(cc, artifacts, archives):
    from .frozen_audit import run_frozen_audit
    artifacts.mkdir(parents=True, exist_ok=True)
    sources = {kind: import_archive(path, kind, artifacts) for kind, path in archives.items()}
    write_json(artifacts / "retained_sources.json", sources)
    old = read_json(artifacts / "full/summary.json")
    case = RELEASE / "defaults/baja/simulation_case.json"
    if hashlib.sha256(case.read_bytes().replace(b"\n", b"\r\n")).hexdigest() != old["base_document_sha256"]:
        raise ValueError("Historical case bytes do not match the documented CRLF conversion.")
    current = read_json(STUDY / "study.json")
    for key in ("cinder_release", "reference_runs", "lambda_domains", "map_selection", "multistart"):
        if current[key] != old["study"][key]:
            raise ValueError(f"Retained protocol differs in {key}.")
    inputs = {p.relative_to(REPO).as_posix(): p.read_bytes() for p in input_paths()}
    run_frozen_audit(cc, artifacts)
    for name, content in inputs.items():
        target = artifacts / "execution_inputs" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        if (REPO / name).read_bytes() != content:
            raise ValueError(f"Input changed during execution: {name}")
    outputs = {p.relative_to(artifacts).as_posix(): digest(p)
               for p in sorted(artifacts.rglob("*")) if p.is_file()
               and p.suffix in (".csv", ".json", ".npz")
               and p.relative_to(artifacts).parts[0] not in ("execution_inputs", "publication")
               and p.name != "execution_provenance.json"}
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in inputs.items()}
    identity = hashlib.sha256(json.dumps({"inputs": hashes, "outputs": outputs}, sort_keys=True).encode()).hexdigest()
    write_json(artifacts / "execution_provenance.json", {
        "run_id": "closure-conditioning-" + identity[:16],
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "mechanics_version": "1.1.2", "mechanics_commit": MECHANICS,
        "execution": "Retained full maps/censuses; fresh selected frozen-state checks. No transient or broad search rerun.",
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": {p: metadata.version(p) for p in ("cinder-cvt", "numpy", "scipy", "matplotlib")},
        "historical_environment_limit": "Retained archives identify CINDER 1.1.2 but do not preserve a complete original package/machine lock.",
        "input_sha256": hashes, "output_sha256": outputs,
    })


def verify_record(artifacts):
    record = read_json(artifacts / "execution_provenance.json")
    if record["mechanics_commit"] != MECHANICS:
        raise ValueError("Wrong mechanics release.")
    for group, root in (("input_sha256", artifacts / "execution_inputs"), ("output_sha256", artifacts)):
        for name, expected in record[group].items():
            if digest(root / name) != expected:
                raise ValueError(f"Changed evidence: {name}")
    return record
