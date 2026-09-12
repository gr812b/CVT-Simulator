"""Cheap preflight for the upgraded CINDER 1.1.2 closure-conditioning study."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

import cinder
from cinder.contracts import validate_simulation_case_document
from cinder.model.cvt.dynamics.result import TrialClosureResult
from cinder.model.cvt.dynamics.engaged_contact import EngagedContactClosure, EngagedContactSolveResult, LambdaSearchBounds

HERE = Path(__file__).resolve().parent
RELEASE_ROOT = HERE.parents[1]
VERIFY = RELEASE_ROOT / "verify_environment.py"
CASE_LIBRARY = RELEASE_ROOT / "defaults" / "verification_operating_cases.json"

subprocess.run([sys.executable, str(VERIFY)], check=True)
assert cinder.__version__ == "1.1.2"
spec = json.loads((HERE / "study.json").read_text(encoding="utf-8"))
base = (HERE / spec["base_document"]).resolve(); assert base.is_file(), base
assert CASE_LIBRARY.is_file(), CASE_LIBRARY
library = json.loads(CASE_LIBRARY.read_text(encoding="utf-8"))
assert int(library["schema_version"]) >= 2
assert library["stick_cases"] and library["free_shift_cases"]
document = json.loads(base.read_text(encoding="utf-8"))
report = validate_simulation_case_document(document); assert report.is_valid, report.findings

required_closure = {"matrix","right_hand_side","unknowns","equation_residuals","condition_number","matrix_rank","scaled_condition_number"}
assert required_closure <= set(TrialClosureResult.__dataclass_fields__)
required_root = {"jacobian","jacobian_determinant","jacobian_condition_number","function_evaluations"}
assert required_root <= set(EngagedContactSolveResult.__dataclass_fields__)
assert callable(EngagedContactClosure.evaluate_trial)
_ = LambdaSearchBounds(primary_lower=-2.6, primary_upper=2.6, secondary_lower=-2.6, secondary_upper=2.6)

import numpy as np
from conditioning_math import finite_difference_jacobian
lp=np.linspace(-1.0,1.0,41); ls=np.linspace(-1.0,1.0,41); LP,LS=np.meshgrid(lp,ls)
J=np.array([[2.0,0.5],[-0.25,1.5]])
rp=J[0,0]*LP+J[0,1]*LS+0.2; rs=J[1,0]*LP+J[1,1]*LS-0.1
smin,smax,kappa,det=finite_difference_jacobian(lp,ls,rp,rs); exact=np.linalg.svd(J,compute_uv=False); interior=np.s_[2:-2,2:-2]
assert np.max(np.abs(smax[interior]-exact[0])) < 1e-10
assert np.max(np.abs(smin[interior]-exact[-1])) < 1e-10
assert np.max(np.abs(kappa[interior]-np.linalg.cond(J))) < 1e-10
assert np.max(np.abs(det[interior]-np.linalg.det(J))) < 1e-10

# Plot-label smoke test.  Matplotlib mathtext support changes independently of
# CINDER; draw the exact symbolic labels used by run.py so verify_study catches
# presentation/parser failures before a long conditioning sweep is started.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, axes = plt.subplots(2, 4, figsize=(8, 4))
labels = [
    r"Primary stick residual $R_p$",
    r"Secondary stick residual $R_s$",
    r"Residual norm $\|R\|_2$",
    r"Equilibrated 8×8 $\kappa(A)$",
    r"$\sigma_{\min}(J_R)$",
    r"$\kappa(J_R)$",
    r"Signed $\det(J_R)$",
    r"max$(|N_p|,|N_s|)$",
]
for ax, label in zip(axes.ravel(), labels):
    ax.set_title(label)
fig.canvas.draw()
plt.close(fig)

print("PASS upgraded closure-conditioning preflight")

# Optional ridge-anatomy diagnostic must remain import/syntax clean.  It is not
# executed here because it intentionally depends on map artifacts from run.py.
_diag = HERE / "singular_vector_diagnostics.py"
assert _diag.is_file(), _diag
compile(_diag.read_text(encoding="utf-8"), str(_diag), "exec")
