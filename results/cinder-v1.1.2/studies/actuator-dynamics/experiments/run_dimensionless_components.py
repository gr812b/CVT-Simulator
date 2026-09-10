from __future__ import annotations
import csv, math
from pathlib import Path
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
STUDY_ROOT=HERE.parent
if str(STUDY_ROOT) not in sys.path: sys.path.insert(0,str(STUDY_ROOT))
from study_support import ARTIFACTS, write_rows


def f(x):
    try:
        y=float(x)
        return y if math.isfinite(y) else None
    except (TypeError,ValueError): return None


def ratio(num,den):
    n=f(num); d=f(den)
    if n is None or d is None or abs(d)<1e-9: return float("nan")
    return abs(n)/abs(d)


def main():
    src=ARTIFACTS/'baseline-ablation'/'direct_clamp_on_full_trajectory.csv'
    if not src.is_file():
        raise RuntimeError('Run baseline ablation before dimensionless component analysis.')
    with src.open(newline='',encoding='utf-8') as h: rows=list(csv.DictReader(h))
    out=[]
    for r in rows:
        qpf=r.get('fly_qs_centrifugal_force_N')
        qsh=r.get('helix_qs_reaction_force_N')
        o=dict(r)
        o.update({
          'Pi_p_accel':ratio(r.get('fly_dynamic_axial_inertia_force_N'),qpf),
          'Pi_p_curvature':ratio(r.get('fly_dynamic_curvature_force_N'),qpf),
          'Pi_p_total':ratio(r.get('fly_dynamic_total_correction_N'),qpf),
          'Pi_s_omega':ratio(r.get('helix_dynamic_shaft_accel_force_N'),qsh),
          'Pi_s_axial':ratio(r.get('helix_dynamic_shift_accel_force_N'),qsh),
          'Pi_s_curvature':ratio(r.get('helix_dynamic_curvature_force_N'),qsh),
          'Pi_s_total':ratio(r.get('helix_dynamic_total_correction_N'),qsh),
          'ratio_valid_primary': abs(f(qpf) or 0.0)>=1.0,
          'ratio_valid_secondary': abs(f(qsh) or 0.0)>=1.0,
        })
        out.append(o)
    dst=ARTIFACTS/'dimensionless-components'
    dst.mkdir(parents=True,exist_ok=True)
    write_rows(dst/'component_dynamic_numbers.csv',out)

    t=np.asarray([float(r['time_s']) for r in out])
    fig,ax=plt.subplots(figsize=(9,5.5))
    for key,label in [('Pi_p_accel',r'$\Pi_{p,a}$'),('Pi_p_curvature',r'$\Pi_{p,c}$')]:
        y=np.asarray([float(r[key]) if r['ratio_valid_primary'] and math.isfinite(float(r[key])) and float(r[key])>0 else np.nan for r in out])
        ax.plot(t,y,label=label)
    ax.set_yscale('log'); ax.set_xlabel('Time [s]'); ax.set_ylabel('Fraction of QS flyweight force [-]')
    ax.set_title('Primary flyweight dynamic-correction components'); ax.grid(True,alpha=.25); ax.legend(); fig.tight_layout()
    fig.savefig(dst/'primary_component_dynamic_numbers.png',dpi=180); plt.close(fig)

    fig,ax=plt.subplots(figsize=(9,5.5))
    for key,label in [('Pi_s_omega',r'$\Pi_{s,\omega}$'),('Pi_s_axial',r'$\Pi_{s,x}$'),('Pi_s_curvature',r'$\Pi_{s,c}$')]:
        y=np.asarray([float(r[key]) if r['ratio_valid_secondary'] and math.isfinite(float(r[key])) and float(r[key])>0 else np.nan for r in out])
        ax.plot(t,y,label=label)
    ax.set_yscale('log'); ax.set_xlabel('Time [s]'); ax.set_ylabel('Fraction of QS helix force [-]')
    ax.set_title('Secondary helix dynamic-correction components'); ax.grid(True,alpha=.25); ax.legend(); fig.tight_layout()
    fig.savefig(dst/'secondary_component_dynamic_numbers.png',dpi=180); plt.close(fig)

    for start,name in [(0.0,'all'),(0.1,'post_capture')]:
        subset=[r for r in out if float(r['time_s'])>=start]
        summary={'window':name,'start_s':start}
        for key,valid in [('Pi_p_accel','ratio_valid_primary'),('Pi_p_curvature','ratio_valid_primary'),('Pi_p_total','ratio_valid_primary'),('Pi_s_omega','ratio_valid_secondary'),('Pi_s_axial','ratio_valid_secondary'),('Pi_s_curvature','ratio_valid_secondary'),('Pi_s_total','ratio_valid_secondary')]:
            vals=[float(r[key]) for r in subset if r[valid] and math.isfinite(float(r[key]))]
            summary[key+'_max']=max(vals) if vals else None
            summary[key+'_p99']=float(np.percentile(vals,99)) if vals else None
        (dst/f'summary_{name}.json').write_text(__import__('json').dumps(summary,indent=2)+'\n')
    print(f'Wrote component dynamic numbers to {dst}')
    return 0

if __name__=='__main__': raise SystemExit(main())
