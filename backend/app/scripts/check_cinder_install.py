"""Fail release checks when CINDER is not the exact index-installed dependency.

Run from backend/: python -m app.scripts.check_cinder_install
This checks installation metadata, not a cryptographic attestation of the index.
Local/editable/VCS/direct-wheel overrides must not pass a production check.
"""

from __future__ import annotations

import importlib
import re
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path


def required_version(requirements: Path) -> str:
    pins = re.findall(
        r"^cinder-cvt==([0-9A-Za-z.+!-]+)\s*$",
        requirements.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if len(pins) != 1:
        raise RuntimeError("Expected one exact cinder-cvt pin in requirements.txt.")
    return pins[0]


def verify_installation(requirements: Path | None = None) -> tuple[str, Path]:
    requirements = requirements or (Path(__file__).resolve().parents[2] / "requirements.txt")
    expected = required_version(requirements)
    try:
        installed = distribution("cinder-cvt")
    except PackageNotFoundError as exc:
        raise RuntimeError("The pinned CINDER distribution is not installed.") from exc
    if installed.version != expected:
        raise RuntimeError(
            f"Expected CINDER {expected}; " f"installed distribution is {installed.version}."
        )
    if installed.read_text("direct_url.json") is not None:
        raise RuntimeError(
            "CINDER was installed from a local path, VCS or direct URL. "
            "Use a fresh environment and install the published requirements."
        )
    module = importlib.import_module("cinder")
    actual_path = Path(module.__file__).resolve()
    installed_path = Path(installed.locate_file("cinder/__init__.py")).resolve()
    if actual_path != installed_path or module.__version__ != expected:
        raise RuntimeError(
            f"Imported CINDER does not match its pinned distribution: {actual_path}."
        )
    return expected, actual_path


def main() -> None:
    try:
        version, module_path = verify_installation()
    except (RuntimeError, OSError) as exc:
        raise SystemExit(f"CINDER installation check failed: {exc}") from exc
    print(f"Verified index-installed CINDER {version} from {module_path}")


if __name__ == "__main__":
    main()
