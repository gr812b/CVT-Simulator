"""Broad solver-stability sweep for the migrated Ballew closed-loop case.

This is the cleaned results-tree counterpart to the legacy numerical-stability
stress harness.  The exact old harness and its archived outputs are preserved by
``migrate_legacy.py``.  This runner keeps the same published/plant/controller
inputs and the same preset grids, but uses the CINDER result object directly for
accepted-step statistics instead of monkey-patching SciPy.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import cinder

from migrate_legacy import ensure_reference_assets
from benchmark.simulation import build_closed_loop_setup, run_setup, sample_dense

STUDY_ROOT = Path(__file__).resolve().parent
RELEASE_ROOT = STUDY_ROOT.parents[1]
VERIFY = RELEASE_ROOT / "verify_environment.py"
OUTPUT_ROOT = STUDY_ROOT / "artifacts" / "rerun-v1.0.0" / "numerical-stability"
EXPECTED_CINDER_VERSION = "1.0.0"
DURATION_S = 5.0
BALLEW_FIXED_STEP_S = 1.0e-5

PRESETS = {
    "smoke": {
        "max_step_ms": [0.10, 1.0, 100.0],
        "rtol": [1e-9, 1e-7, 1e-4],
    },
    "quick": {
        "max_step_ms": [0.03, 0.10, 0.30, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0],
        "rtol": [1e-10, 1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3],
    },
    "full": {
        "max_step_ms": [0.01, 0.03, 0.10, 0.30, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0],
        "rtol": [1e-11, 3e-11, 1e-10, 3e-10, 1e-9, 3e-9, 1e-8, 3e-8, 1e-7, 1e-6, 1e-5, 1e-4],
    },
    "extreme": {
        "max_step_ms": [0.01, 0.03, 0.10, 0.30, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 5000.0],
        "rtol": [1e-11, 1e-10, 1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 3e-3, 1e-2],
    },
}

REFERENCE = {
    "method": "LSODA",
    "max_step_s": 1.0e-4,
    "rtol": 1.0e-10,
    "atol": 1.0e-12,
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--preset", choices=tuple(PRESETS), default="quick")
    p.add_argument("--report-step", type=float, default=5.0e-4)
    p.add_argument("--maximum-transitions", type=int, default=5000)
    p.add_argument("--output-dir", type=Path, default=None)
    return p.parse_args()


def _accepted_step_stats(result) -> dict[str, float | int | None]:
    chunks=[]
    accepted=0
    for seg in result.trace.raw.segments:
        t=np.asarray(seg.time,dtype=float)
        if t.size >= 2:
            dt=np.diff(t)
            dt=dt[np.isfinite(dt) & (dt>0.0)]
            accepted += int(dt.size)
            if dt.size:
                chunks.append(dt)
    if not chunks:
        return {"accepted_steps":accepted,"actual_dt_min_ms":None,"actual_dt_median_ms":None,"actual_dt_p95_ms":None,"actual_dt_max_ms":None}
    dt=np.concatenate(chunks)
    return {
        "accepted_steps":accepted,
        "actual_dt_min_ms":float(np.min(dt)*1e3),
        "actual_dt_median_ms":float(np.median(dt)*1e3),
        "actual_dt_p95_ms":float(np.quantile(dt,0.95)*1e3),
        "actual_dt_max_ms":float(np.max(dt)*1e3),
    }


def _rms(x: np.ndarray) -> float:
    a=np.asarray(x,dtype=float)
    a=a[np.isfinite(a)]
    return float(np.sqrt(np.mean(a*a))) if a.size else math.nan


def _relative_rms(delta: np.ndarray, reference: np.ndarray, floor: float) -> float:
    d=np.asarray(delta,dtype=float); r=np.asarray(reference,dtype=float)
    m=np.isfinite(d)&np.isfinite(r)
    if not np.any(m): return math.nan
    denom=max(_rms(r[m]),float(floor))
    return _rms(d[m])/denom


def _compare(cur, ref) -> dict[str,float]:
    dp=cur.primary_rpm-ref.primary_rpm
    ds=cur.secondary_rpm-ref.secondary_rpm
    dr=cur.speed_ratio-ref.speed_ratio
    dx=(cur.shift_m-ref.shift_m)*1e6
    rels=np.array([
        _relative_rms(dp,ref.primary_rpm,1.0),
        _relative_rms(ds,ref.secondary_rpm,1.0),
        _relative_rms(dr,ref.speed_ratio,1e-3),
        _relative_rms(cur.shift_m-ref.shift_m,ref.shift_m,1e-5),
    ])
    return {
        "primary_rpm_rms_delta":_rms(dp),
        "primary_rpm_max_delta":float(np.nanmax(np.abs(dp))),
        "secondary_rpm_rms_delta":_rms(ds),
        "ratio_rms_delta":_rms(dr),
        "ratio_max_delta":float(np.nanmax(np.abs(dr))),
        "shift_rms_delta_um":_rms(dx),
        "shift_max_delta_um":float(np.nanmax(np.abs(dx))),
        "composite_relative_error_ppm":float(np.nanmax(rels)*1e6),
    }


def _run_case(*, rtol:float, max_step_s:float, report_step:float, maximum_transitions:int):
    setup=build_closed_loop_setup()
    t0=time.perf_counter()
    result=run_setup(
        setup,
        relative_tolerance=rtol,
        absolute_tolerance=rtol*1e-2,
        max_step_s=max_step_s,
        maximum_transitions=maximum_transitions,
        report_step_s=report_step,
        method="LSODA",
    )
    wall=time.perf_counter()-t0
    times=np.arange(0.0,DURATION_S+0.5*report_step,report_step,dtype=float)
    times[-1]=DURATION_S
    sample=sample_dense(setup,result,times) if result.completed else None
    return result,sample,wall


def main() -> int:
    args=parse_args()
    subprocess.run([sys.executable,str(VERIFY)],check=True)
    if cinder.__version__ != EXPECTED_CINDER_VERSION:
        raise SystemExit(f"Expected CINDER {EXPECTED_CINDER_VERSION}, found {cinder.__version__}.")
    ensure_reference_assets()  # also ensures the complete legacy archive has been migrated
    out=(args.output_dir or (OUTPUT_ROOT/args.preset)).resolve()
    out.mkdir(parents=True,exist_ok=True)

    ref_setup=build_closed_loop_setup()
    ref_result=run_setup(
        ref_setup,
        relative_tolerance=REFERENCE["rtol"],
        absolute_tolerance=REFERENCE["atol"],
        max_step_s=REFERENCE["max_step_s"],
        maximum_transitions=args.maximum_transitions,
        report_step_s=args.report_step,
        method=REFERENCE["method"],
    )
    if not ref_result.completed:
        raise RuntimeError(f"Tight CINDER reference did not complete: {ref_result.termination_reason}")
    times=np.arange(0.0,DURATION_S+0.5*args.report_step,args.report_step,dtype=float)
    times[-1]=DURATION_S
    ref=sample_dense(ref_setup,ref_result,times)

    rows=[]
    preset=PRESETS[args.preset]
    total=len(preset["rtol"])*len(preset["max_step_ms"])
    n=0
    for rtol in preset["rtol"]:
        for max_step_ms in preset["max_step_ms"]:
            n+=1
            print(f"[{n}/{total}] rtol={rtol:g}, max_step={max_step_ms:g} ms")
            try:
                result,sample,wall=_run_case(
                    rtol=float(rtol),
                    max_step_s=float(max_step_ms)*1e-3,
                    report_step=args.report_step,
                    maximum_transitions=args.maximum_transitions,
                )
                row={
                    "rtol":rtol,
                    "atol":rtol*1e-2,
                    "max_step_ms":max_step_ms,
                    "completed":bool(result.completed),
                    "termination_reason":str(result.termination_reason),
                    "wall_time_s":wall,
                    "real_time_factor":DURATION_S/wall if wall>0 else math.nan,
                    "segment_count":len(result.trace.raw.segments),
                    "raw_transition_count":len(result.transitions),
                    **_accepted_step_stats(result),
                }
                if sample is not None:
                    row.update(_compare(sample,ref))
            except Exception as exc:
                row={
                    "rtol":rtol,"atol":rtol*1e-2,"max_step_ms":max_step_ms,
                    "completed":False,"termination_reason":f"{type(exc).__name__}: {exc}",
                }
            rows.append(row)

    fields=[]
    for row in rows:
        for k in row:
            if k not in fields: fields.append(k)
    with (out/'stress_sweep.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    payload={
        "cinder_version":cinder.__version__,
        "preset":args.preset,
        "reference":REFERENCE,
        "ballew_reported_fixed_step_s":BALLEW_FIXED_STEP_S,
        "ballew_implied_fixed_step_count_over_5s":DURATION_S/BALLEW_FIXED_STEP_S,
        "metric_note":"composite_relative_error_ppm is max relative RMS across primary RPM, secondary RPM, speed ratio, and shift coordinate against the tight CINDER-only reference; it is not a Ballew fit metric.",
        "cases":rows,
    }
    (out/'stress_sweep.json').write_text(json.dumps(payload,indent=2)+"\n",encoding='utf-8')
    print(f"Artifacts: {out}")
    return 0 if all(bool(r.get('completed')) for r in rows) else 1

if __name__=='__main__':
    raise SystemExit(main())
