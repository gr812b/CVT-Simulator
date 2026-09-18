
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
import sys
STUDY_ROOT=Path(__file__).resolve().parents[1]
if str(STUDY_ROOT) not in sys.path: sys.path.insert(0,str(STUDY_ROOT))
from experiments.run_controlled_transients import select_targets

def main():
    rows=[
      {'case_id':'near_1pct','actuator':'secondary','status':'completed','response_class':'clean_continuous','peak_dynamic_number':0.0105},
      {'case_id':'near_2p6pct','actuator':'secondary','status':'completed','response_class':'clean_continuous','peak_dynamic_number':0.0260},
      {'case_id':'reset_20pct','actuator':'secondary','status':'completed','response_class':'impact_reset','peak_dynamic_number':0.20},]
    sel=select_targets(rows,'secondary',[0.01,0.05],maximum_relative_error=0.25)
    assert sel[0]['selection_status']=='selected' and sel[0]['case_id']=='near_1pct'
    assert sel[1]['selection_status']=='unreached_outside_target_tolerance'
    assert abs(sel[1]['nearest_achieved_dynamic_number']-0.026)<1e-12
    print('PASS controlled target selection')
    return 0
if __name__=='__main__': raise SystemExit(main())
