"""Regression checks for local helix derivatives used by validity envelopes."""
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

from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
import sys

STUDY_ROOT = Path(__file__).resolve().parents[1]
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from experiments.run_validity_envelopes import _local_helix_derivatives
from cinder.model.cvt.profiles import HelixShiftKinematics


def main() -> int:
    names = {f.name for f in fields(HelixShiftKinematics)}
    required = {
        "dtheta_dopening",
        "d2theta_dopening2",
        "dtheta_ds",
        "d2theta_ds2",
    }
    assert required <= names
    assert "dtheta_daxial" not in names
    assert "d2theta_daxial2" not in names

    coupling = SimpleNamespace(opening_per_axial_position=-2.0)
    kin = SimpleNamespace(dtheta_dopening=-3.0, d2theta_dopening2=4.0)
    H, Hp = _local_helix_derivatives(coupling, kin)
    assert H == 6.0
    assert Hp == 16.0

    print("PASS validity-envelope local helix derivative regression")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
