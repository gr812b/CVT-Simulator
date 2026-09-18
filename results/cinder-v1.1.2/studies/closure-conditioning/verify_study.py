"""Cheap preflight for the upgraded CINDER 1.1.2 closure-conditioning study."""
from __future__ import annotations

# --- results study-local import bootstrap ---
from pathlib import Path as _ResultsPath
import sys as _results_sys

_results_file = _ResultsPath(__file__).resolve()
_results_study_root = next(
    (parent for parent in _results_file.parents if (parent / "study.json").is_file()),
    None,
)
if _results_study_root is None:
    raise RuntimeError(f"Could not locate study root for {_results_file}")
_results_release_root = _results_study_root.parents[1]
for _results_path in (str(_results_study_root), str(_results_release_root)):
    while _results_path in _results_sys.path:
        _results_sys.path.remove(_results_path)
_results_sys.path.insert(0, str(_results_release_root))
_results_sys.path.insert(0, str(_results_study_root))
# --- end results study-local import bootstrap ---


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
for _path in (str(HERE), str(RELEASE_ROOT)):
    while _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, str(RELEASE_ROOT))
sys.path.insert(0, str(HERE))

from infrastructure.conditioning_math import finite_difference_jacobian

VERIFY = RELEASE_ROOT / "verify_environment.py"
CASE_LIBRARY = RELEASE_ROOT / "defaults" / "verification" / "operating_cases.json"


def main() -> int:
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
    lp=np.linspace(-1.0,1.0,41); ls=np.linspace(-1.0,1.0,41); LP,LS=np.meshgrid(lp,ls)
    J=np.array([[2.0,0.5],[-0.25,1.5]])
    rp=J[0,0]*LP+J[0,1]*LS+0.2; rs=J[1,0]*LP+J[1,1]*LS-0.1
    smin,smax,kappa,det=finite_difference_jacobian(lp,ls,rp,rs); exact=np.linalg.svd(J,compute_uv=False); interior=np.s_[2:-2,2:-2]
    assert np.max(np.abs(smax[interior]-exact[0])) < 1e-10
    assert np.max(np.abs(smin[interior]-exact[-1])) < 1e-10
    assert np.max(np.abs(kappa[interior]-np.linalg.cond(J))) < 1e-10
    assert np.max(np.abs(det[interior]-np.linalg.det(J))) < 1e-10

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
    fig.canvas.draw(); plt.close(fig)

    diagnostic = HERE / "analysis" / "singular_vector_diagnostics.py"
    assert diagnostic.is_file(), diagnostic
    compile(diagnostic.read_text(encoding="utf-8"), str(diagnostic), "exec")

    print("PASS upgraded closure-conditioning preflight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
