"""Cheap preflight for the CINDER 1.1.2 solver-convergence study."""

from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

import cinder
from cinder.contracts import validate_simulation_case_document
from cinder.execution.hybrid import integrate_hybrid

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
assert callable(integrate_hybrid)

import numpy as np

x = np.linspace(0.0, 1.0, 101)
reference = np.sin(x)
candidate = reference + 1e-5
normalized_rms = float(np.sqrt(np.mean((candidate - reference) ** 2)))
assert 0.0 < normalized_rms < 1e-4

print("PASS solver-convergence preflight")
