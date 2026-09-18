#!/usr/bin/env python3
"""Validate all maintained CINDER v1.1.2 study manifests and local verifiers."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
STUDIES = HERE / "studies"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from repo_tools.study_manifest import validate_manifest


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifests-only", action="store_true")
    p.add_argument("--study", action="append", default=[])
    return p.parse_args()


def main() -> int:
    args = parse_args()
    requested = set(args.study)
    failures: list[str] = []
    roots = sorted(p for p in STUDIES.iterdir() if p.is_dir() and (p / "study.json").is_file())
    if requested:
        roots = [p for p in roots if p.name in requested]
        missing = requested - {p.name for p in roots}
        failures.extend(f"unknown study: {name}" for name in sorted(missing))

    for root in roots:
        errors = validate_manifest(root / "study.json")
        if errors:
            failures.extend(errors)
            continue
        print(f"[manifest ok] {root.name}")
        if args.manifests_only:
            continue
        verifier = root / "verify_study.py"
        if verifier.is_file():
            print(f"[verify] {root.name}")
            completed = subprocess.run([sys.executable, str(verifier)], cwd=HERE.parents[1])
            if completed.returncode != 0:
                failures.append(f"{root.name}: verify_study.py returned {completed.returncode}")

    if failures:
        print("\nFAILURES:")
        for item in failures:
            print(" -", item)
        return 1
    print("\nAll requested maintained studies passed repository checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
