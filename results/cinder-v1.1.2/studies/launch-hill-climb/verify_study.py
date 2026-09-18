#!/usr/bin/env python3
"""Repository-level verification for the launch/hill maintained study."""
from __future__ import annotations

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
RELEASE_ROOT = HERE.parents[1]
if str(RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(RELEASE_ROOT))

from repo_tools.study_manifest import validate_manifest


def main() -> int:
    errors = validate_manifest(HERE / "study.json")
    if not (HERE / "run.py").is_file():
        errors.append("canonical run.py is missing")
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    print("launch-hill-climb repository contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
