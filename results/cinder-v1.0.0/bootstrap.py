"""Create the isolated environment for CINDER 1.0.0 result studies."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

EXPECTED_PYTHON = (3, 12)
PYPI_INDEX = "https://pypi.org/simple"

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
VERIFY = ROOT / "verify_environment.py"


def _venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _clean_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "PYTHONPATH",
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "PIP_FIND_LINKS",
        "PIP_CONFIG_FILE",
        "PIP_REQUIRE_VIRTUALENV",
    ):
        env.pop(key, None)
    return env


def main() -> int:
    if sys.version_info[:2] != EXPECTED_PYTHON:
        expected = ".".join(map(str, EXPECTED_PYTHON))
        actual = f"{sys.version_info.major}.{sys.version_info.minor}"
        raise SystemExit(
            f"CINDER 1.0.0 results require Python {expected}; "
            f"bootstrap is running under Python {actual}."
        )

    if VENV.exists():
        print(f"Removing existing environment: {VENV}")
        shutil.rmtree(VENV)

    print(f"Creating clean environment: {VENV}")
    subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)

    python = _venv_python()
    env = _clean_environment()

    print(f"Installing frozen dependencies from {PYPI_INDEX}")
    subprocess.run(
        [
            str(python), "-m", "pip", "--isolated", "install",
            "--no-cache-dir", "--index-url", PYPI_INDEX,
            "--requirement", str(REQUIREMENTS),
        ],
        check=True,
        cwd=ROOT,
        env=env,
    )

    print("Verifying environment")
    subprocess.run(
        [str(python), str(VERIFY)],
        check=True,
        cwd=ROOT,
        env=env,
    )

    activate = (
        VENV / "Scripts/Activate.ps1"
        if os.name == "nt"
        else VENV / "bin/activate"
    )
    print(f"\nEnvironment ready. Activate with: {activate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
