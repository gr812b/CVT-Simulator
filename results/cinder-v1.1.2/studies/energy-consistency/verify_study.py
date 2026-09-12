"""Static checks for the CINDER 1.1.2 mechanical-energy results study."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = ROOT.parents[1]
STUDY = ROOT / "study.json"


def main() -> int:
    required = [
        ROOT / "README.md",
        ROOT / "study.json",
        ROOT / "run.py",
        ROOT / "energy_accounting.py",
        RELEASE_ROOT / "verify_environment.py",
        RELEASE_ROOT / "defaults" / "baja_reference_simulation_case.json",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print("Energy study missing required files:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 1

    spec = json.loads(STUDY.read_text(encoding="utf-8"))
    release = spec["cinder_release"]
    if release["version"] != "1.1.2" or release["source_tag"] != "cinder-v1.1.2":
        print("Energy study release provenance is not frozen to CINDER 1.1.2.", file=sys.stderr)
        return 1

    steps = [float(value) for value in spec["audit_quadrature_steps_s"]]
    if len(steps) < 3 or any(step <= 0.0 for step in steps):
        print("Energy study requires at least three positive audit steps.", file=sys.stderr)
        return 1
    if any(b >= a for a, b in zip(steps, steps[1:])):
        print("Audit quadrature steps must be strictly decreasing.", file=sys.stderr)
        return 1

    forbidden = (
        "launchTools",
        "cvtModel/src",
        "helix_face_power_candidate",
        "missing_power_candidate",
        "circular_traction_first_reference",
    )
    for path in (ROOT / "run.py", ROOT / "energy_accounting.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                print(
                    f"{path.name} contains forbidden diagnostic/source dependency {token!r}.",
                    file=sys.stderr,
                )
                return 1

    print("Energy-consistency study verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
