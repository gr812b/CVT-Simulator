"""Cheap preflight for the CINDER 1.1.2 closure-conditioning study."""

from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

import cinder
from cinder.contracts import validate_simulation_case_document
from cinder.model.cvt.dynamics.result import TrialClosureResult
from cinder.model.cvt.dynamics.engaged_contact import (
    EngagedContactClosure,
    EngagedContactSolveResult,
)

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

required_closure = {
    "matrix", "right_hand_side", "unknowns", "equation_residuals",
    "condition_number", "matrix_rank", "scaled_condition_number",
}
assert required_closure <= set(TrialClosureResult.__dataclass_fields__)

required_root = {
    "jacobian", "jacobian_determinant", "jacobian_condition_number",
    "function_evaluations",
}
assert required_root <= set(EngagedContactSolveResult.__dataclass_fields__)
assert callable(EngagedContactClosure.evaluate_trial)

import numpy as np
from conditioning_math import finite_difference_jacobian

lp = np.linspace(-1.0, 1.0, 41)
ls = np.linspace(-1.0, 1.0, 41)
LP, LS = np.meshgrid(lp, ls)
J = np.array([[2.0, 0.5], [-0.25, 1.5]])
rp = J[0, 0] * LP + J[0, 1] * LS + 0.2
rs = J[1, 0] * LP + J[1, 1] * LS - 0.1
smin, smax, kappa, det = finite_difference_jacobian(lp, ls, rp, rs)
exact_s = np.linalg.svd(J, compute_uv=False)
interior = np.s_[2:-2, 2:-2]
assert np.max(np.abs(smax[interior] - exact_s[0])) < 1e-10
assert np.max(np.abs(smin[interior] - exact_s[-1])) < 1e-10
assert np.max(np.abs(kappa[interior] - np.linalg.cond(J))) < 1e-10
assert np.max(np.abs(det[interior] - np.linalg.det(J))) < 1e-10

print("PASS closure-conditioning preflight")
