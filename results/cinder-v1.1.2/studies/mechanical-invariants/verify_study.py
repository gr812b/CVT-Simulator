"""Cheap preflight for the CINDER 1.1.2 mechanical-invariants study."""

from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

import cinder
from cinder.contracts import validate_simulation_case_document
from cinder.results.inspection import inspect_cvt_state
from cinder.model.cvt.geometry.belt_length import belt_length_residual
from cinder.execution.hybrid.cvt_contact import CVTContactEvaluation

HERE = Path(__file__).resolve().parent
RELEASE_ROOT = HERE.parents[1]
VERIFY = RELEASE_ROOT / "verify_environment.py"

subprocess.run([sys.executable, str(VERIFY)], check=True)
assert cinder.__version__ == "1.1.2"

spec = json.loads((HERE / "study.json").read_text(encoding="utf-8"))
base = (HERE / spec["base_document"]).resolve()
assert base.is_file(), base
document = json.loads(base.read_text(encoding="utf-8"))
report = validate_simulation_case_document(document)
assert report.is_valid, report.findings

for name in (
    "slipped_directions_are_consistent",
    "mechanism_contacts_are_admissible",
    "normal_at",
):
    assert hasattr(CVTContactEvaluation, name), name

assert callable(inspect_cvt_state)
assert callable(belt_length_residual)
print("PASS mechanical-invariants preflight")
