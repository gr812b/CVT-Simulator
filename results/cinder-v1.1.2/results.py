#!/usr/bin/env python3
"""Single public entry point for the frozen CINDER 1.1.2 Results workspace."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

RELEASE = Path(__file__).resolve().parent
REPO = RELEASE.parents[1]
WORKFLOWS = RELEASE / "results_health" / "workflows"


def frozen_python() -> Path:
    return RELEASE / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def require_frozen_python() -> Path:
    exe = frozen_python()
    if not exe.is_file():
        raise SystemExit(
            f"Frozen Results interpreter not found: {exe}\n"
            f"Run: py -3.12 {Path(__file__).as_posix()} bootstrap"
        )
    return exe


def run_script(script: Path, args: list[str], *, frozen: bool = True) -> int:
    exe = require_frozen_python() if frozen else Path(sys.executable)
    return subprocess.call([str(exe), str(script), *args], cwd=REPO)


def verify_studies(args: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="results.py studies",
        description="Validate maintained study manifests and optional study-local verifiers.",
    )
    parser.add_argument("--manifests-only", action="store_true")
    parser.add_argument("--study", action="append", default=[])
    ns = parser.parse_args(args)

    if str(RELEASE) not in sys.path:
        sys.path.insert(0, str(RELEASE))
    from repo_tools.study_manifest import validate_manifest

    requested = set(ns.study)
    roots = sorted(
        p for p in (RELEASE / "studies").iterdir()
        if p.is_dir() and (p / "study.json").is_file()
    )
    failures: list[str] = []
    if requested:
        roots = [p for p in roots if p.name in requested]
        missing = requested - {p.name for p in roots}
        failures.extend(f"unknown study: {name}" for name in sorted(missing))

    exe = require_frozen_python()
    for study in roots:
        errors = validate_manifest(study / "study.json")
        if errors:
            failures.extend(errors)
            continue
        print(f"[manifest ok] {study.name}")
        if ns.manifests_only:
            continue
        verifier = study / "verify_study.py"
        if verifier.is_file():
            print(f"[verify] {study.name}")
            proc = subprocess.run([str(exe), str(verifier)], cwd=REPO)
            if proc.returncode:
                failures.append(f"{study.name}: verify_study.py returned {proc.returncode}")

    if failures:
        print("\nFAILURES:")
        for item in failures:
            print(" -", item)
        return 1
    print("\nAll requested maintained studies passed repository checks.")
    return 0


HELP = """CINDER 1.1.2 Results

Commands:
  bootstrap   create/recreate the pinned Python 3.12 Results environment
  verify      verify the pinned environment and installed CINDER source
  run         numerical Results corrections/checks
  prepare     prepare/check accepted numerical evidence without integrations
  figures     reproduce the current manuscript Results figures
  studies     validate maintained study manifests/verifiers
  test        run fast Results health/regression tests

Examples:
  python results/cinder-v1.1.2/results.py run --help
  python results/cinder-v1.1.2/results.py prepare --help
  python results/cinder-v1.1.2/results.py figures --help
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(HELP)
        return 0

    command, rest = argv[0], argv[1:]
    if command == "bootstrap":
        return run_script(RELEASE / "bootstrap.py", rest, frozen=False)
    if command == "verify":
        if rest:
            raise SystemExit("results.py verify takes no additional arguments")
        return run_script(RELEASE / "verify_environment.py", [], frozen=True)
    if command == "run":
        return run_script(WORKFLOWS / "run.py", rest, frozen=True)
    if command == "prepare":
        return run_script(WORKFLOWS / "prepare.py", rest, frozen=True)
    if command == "figures":
        return run_script(WORKFLOWS / "figures.py", rest, frozen=True)
    if command == "studies":
        return verify_studies(rest)
    if command == "test":
        exe = require_frozen_python()
        return subprocess.call(
            [
                str(exe), "-m", "unittest", "discover",
                "-s", str(RELEASE / "results_health" / "tests"), "-v", *rest,
            ],
            cwd=REPO,
        )
    raise SystemExit(f"Unknown command {command!r}.\n\n{HELP}")


if __name__ == "__main__":
    raise SystemExit(main())
