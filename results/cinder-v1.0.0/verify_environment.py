"""Verify the frozen PyPI environment for CINDER 1.0.0 results."""

from __future__ import annotations

from importlib import metadata
import json
from pathlib import Path
import sys

EXPECTED_PYTHON = (3, 12)
EXPECTED = {
    "cinder-cvt": "1.0.0",
    "numpy": "2.5.2",
    "scipy": "1.18.1",
}

ROOT = Path(__file__).resolve().parent
VENV = (ROOT / ".venv").resolve()


def fail(message: str) -> None:
    raise SystemExit(f"Environment verification failed: {message}")


def main() -> int:
    if sys.version_info[:2] != EXPECTED_PYTHON:
        fail(
            f"expected Python 3.12, found "
            f"{sys.version_info.major}.{sys.version_info.minor}"
        )

    if Path(sys.prefix).resolve() != VENV:
        fail(f"active interpreter is not {VENV}")

    installed = {}
    for package, expected in EXPECTED.items():
        try:
            actual = metadata.version(package)
        except metadata.PackageNotFoundError:
            fail(f"{package} is not installed")
        if actual != expected:
            fail(f"{package} is {actual}, expected {expected}")
        installed[package] = actual

    import cinder

    module_path = Path(cinder.__file__).resolve()
    if VENV not in module_path.parents:
        fail(f"cinder imported from outside the result venv: {module_path}")

    direct_url = metadata.distribution("cinder-cvt").read_text("direct_url.json")
    if direct_url:
        try:
            detail = json.loads(direct_url)
        except json.JSONDecodeError:
            detail = direct_url
        fail(f"cinder-cvt has local/direct install provenance: {detail}")

    repo_root = ROOT.parents[1]
    local_source = (repo_root / "cvtModel" / "src").resolve()
    for entry in sys.path:
        try:
            path = Path(entry or ".").resolve()
        except OSError:
            continue
        if path == local_source or local_source in path.parents:
            fail(f"local CINDER source is on sys.path: {path}")

    print("Environment verification passed.")
    print(f"Python:      {sys.version_info.major}.{sys.version_info.minor}")
    print(f"cinder-cvt: {installed['cinder-cvt']}")
    print(f"NumPy:       {installed['numpy']}")
    print(f"SciPy:       {installed['scipy']}")
    print(f"cinder path: {module_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
