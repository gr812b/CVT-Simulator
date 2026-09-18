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

from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
STUDY_ROOT = HERE.parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
if str(RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(RELEASE_ROOT))
if str(STUDY_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDY_ROOT))

from infrastructure.study_support import ARTIFACTS, load_json, verify_environment


def main() -> int:
    verify_environment()
    cfg = load_json(STUDY_ROOT / "study.json")["experiments"]["coupling_energy"]
    s = cfg["solver"]
    command = [
        sys.executable,
        str(STUDY_ROOT / "infrastructure" / "coupling_energy_core.py"),
        "--duration-s", str(cfg["duration_s"]),
        "--report-step-s", str(cfg["report_step_s"]),
        "--rtol", str(s["relative_tolerance"]),
        "--atol", str(s["absolute_tolerance"]),
        "--max-step-s", str(s["max_step_s"]),
        "--output-dir", str(ARTIFACTS / "coupling-energy"),
        "--no-show",
    ]
    subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
