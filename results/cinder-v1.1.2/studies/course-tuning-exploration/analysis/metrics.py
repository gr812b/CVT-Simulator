"""Defined comparison metrics; reaching less road never earns a shorter finish time."""
from __future__ import annotations
from collections import defaultdict
from math import isfinite
import numpy as np
from infrastructure.common import finite


def first_passage(rows:list[dict]) -> tuple[np.ndarray,np.ndarray]:
    """Monotone record-distance envelope in chronological order, never sorted by x.

    Interpolation is allowed only between successively attained new distances.
    A rollback ends a run by default; arbitrary backwards/repeated coordinates
    cannot silently become an extra forward race segment.
    """
    x=[];t=[];best=-float('inf');previous=None
    ordered=sorted(rows,key=lambda r:(float(r['time_s']),int(r.get('segment_id',0))))
    for row in ordered:
        xx=float(row['distance_m']);tt=float(row['time_s'])
        if previous is None:
            x.append(xx);t.append(tt);best=xx
        elif xx>best+1e-10:
            xa,ta=previous
            # Reattaining the previous record after a pause/rollback creates
            # a right-hand time discontinuity at that record distance.
            if xx>xa and best>=xa:
                crossing=ta+(tt-ta)*(best-xa)/(xx-xa)
                if crossing>t[-1]+1e-10:
                    x.append(best);t.append(crossing)
            x.append(xx);t.append(tt);best=xx
        previous=(xx,tt)
    return np.asarray(x),np.asarray(t)


def passage_at(x:np.ndarray,t:np.ndarray,station:float) -> float | None:
    if len(x)==0 or station<x[0]-1e-8 or station>x[-1]+1e-7: return None
    exact=np.flatnonzero(np.abs(x-station)<=1e-10)
    return float(t[exact[0]]) if len(exact) else float(np.interp(station,x,t))


def integral(rows:list[dict],key:str) -> float:
    total=0.
    # Never integrate across a velocity reset, missing mechanical evaluation,
    # or an interval belonging to another continuous solver segment.
    for left,right in zip(rows,rows[1:]):
        if left.get('segment_id')!=right.get('segment_id'): continue
        if not finite(left.get(key)) or not finite(right.get(key)): continue
        dt=float(right['time_s'])-float(left['time_s'])
        if dt>0: total+=.5*dt*(float(left[key])+float(right[key]))
    return total


def boolean_duration(rows:list[dict],key:str,target=True) -> float:
    total=0.
    for a,b in zip(rows,rows[1:]):
        if a.get('segment_id')==b.get('segment_id') and a.get(key)==target:
            total+=max(0.,float(b['time_s'])-float(a['time_s']))
    return total


def minimum(rows,key):
    v=[float(r[key]) for r in rows if finite(r.get(key))]
    return min(v) if v else None


def maximum(rows,key):
    v=[float(r[key]) for r in rows if finite(r.get(key))]
    return max(v) if v else None


def summarize(rows:list[dict],events:list[dict],course,outcome:dict,tune:dict,review_tolerance:float=1e-5) -> tuple[dict,list[dict]]:
    summary={**{k:tune[k] for k in ('id','label','family','intent')},**outcome}
    if not rows:
        summary.update(finish_time_s=None,max_distance_m=0.,diagnostic_samples=0,inspection_errors=0,review_required=True)
        return summary,[]
    xx,tt=first_passage(rows)
    sectors=[]
    for s in course.sectors:
        start=passage_at(xx,tt,s.start_m);end=passage_at(xx,tt,s.end_m)
        local=[r for r in rows if s.start_m-1e-9<=float(r['distance_m'])<=s.end_m+1e-9]
        sectors.append({'id':tune['id'],'sector':s.name,'start_m':s.start_m,'end_m':s.end_m,'entry_time_s':start,'exit_time_s':end,'sector_time_s':end-start if start is not None and end is not None else None,'completed':end is not None,'sampled_min_speed_m_s':minimum(local,'speed_m_s'),'sampled_max_primary_rpm':maximum(local,'primary_rpm'),'sampled_min_primary_rpm':minimum(local,'primary_rpm'),'sampled_max_static_utilization':max((float(r[k]) for r in local for k in ('primary_static_utilization','secondary_static_utilization') if finite(r.get(k))),default=None)})
    interiors=[r for r in rows if r.get('sample_location')=='interior']
    errors=[r for r in rows if r.get('inspection_error')]
    interior_errors=[r for r in errors if r.get('sample_location')=='interior']
    margin_keys=('normal_primary_N','normal_secondary_N','min_tension_N','primary_min_dN_dtheta_N_per_rad','secondary_min_dN_dtheta_N_per_rad')
    bad=[r for r in interiors if any(finite(r.get(k)) and float(r[k])<-review_tolerance for k in margin_keys) or any(k.startswith('mechanism_margin.') and finite(v) and float(v)<-review_tolerance for k,v in r.items())]
    physical_events=[e for e in events if any(n.startswith('cvt:') for n in e['event_names'])]
    finish=passage_at(xx,tt,course.finish_m) if outcome.get('status')=='finished' else None
    hill_start=next(s.start_m for s in course.sectors if s.name=='hill_entry')
    hill_end=next(s.end_m for s in course.sectors if s.name=='hill_exit')
    hill=[r for r in rows if hill_start<=float(r['distance_m'])<=hill_end]
    back=next((r for r in hill if float(r['shift_rate_mm_s'])<-.1 and r.get('shift_constraint')=='free'),None)
    engage=next((r for r in rows if r.get('engagement')=='engaged'),None)
    high=next((r for r in rows if r.get('shift_constraint')=='upper_stop'),None)
    for row in rows:
        p=row.get('primary_boundary_power_W');row['engine_absorbed_power_W']=max(0.,-float(p)) if finite(p) else None
    summary.update(
        finish_time_s=finish,max_distance_m=float(xx[-1]),final_distance_m=float(rows[-1]['distance_m']),
        diagnostic_samples=len(rows),inspection_errors=len(errors),interior_inspection_errors=len(interior_errors),
        sampled_admissibility_review_count=len(bad),review_required=bool(interior_errors or bad),
        first_review_time_s=float((bad or interior_errors)[0]['time_s']) if bad or interior_errors else None,
        max_speed_m_s=maximum(rows,'speed_m_s'),max_primary_rpm=maximum(rows,'primary_rpm'),
        hill_min_speed_m_s=minimum(hill,'speed_m_s'),hill_min_primary_rpm=minimum(hill,'primary_rpm'),
        first_hill_backshift_time_s=back['time_s'] if back else None,first_hill_backshift_distance_m=back['distance_m'] if back else None,
        engagement_time_s=engage['time_s'] if engage else None,engagement_distance_m=engage['distance_m'] if engage else None,
        engagement_primary_rpm=engage['primary_rpm'] if engage else None,
        first_upper_stop_time_s=high['time_s'] if high else None,
        primary_slip_work_J=integral(rows,'primary_slip_loss_W'),secondary_slip_work_J=integral(rows,'secondary_slip_loss_W'),
        primary_shaft_work_J=integral(rows,'primary_boundary_power_W'),secondary_shaft_work_J=integral(rows,'secondary_boundary_power_W'),
        engine_absorbed_work_J=integral(rows,'engine_absorbed_power_W'),
        primary_slip_duration_s=boolean_duration(rows,'primary_sliding'),secondary_slip_duration_s=boolean_duration(rows,'secondary_sliding'),
        reverse_transmission_duration_s=boolean_duration(rows,'power_flow','reverse'),
        capture_loss_J=sum(float(e.get('capture_loss_J') or 0.) for e in events),physical_transition_count=len(physical_events),
        min_normal_primary_N=minimum(interiors,'normal_primary_N'),min_normal_secondary_N=minimum(interiors,'normal_secondary_N'),
        min_local_primary_normal_N_per_rad=minimum(interiors,'primary_min_dN_dtheta_N_per_rad'),min_local_secondary_normal_N_per_rad=minimum(interiors,'secondary_min_dN_dtheta_N_per_rad'),
        max_realized_cyclic_frequency_hz=maximum(rows,'cyclic_encounter_frequency_hz'),
        review_margin_tolerance=review_tolerance,metric_note='Sampled mechanical extrema and segmentwise trapezoidal work diagnostics; not a repeated formal energy/convergence audit. Missing sectors are censored, not zero.')
    return summary,sectors


def nominate_windows(rows:list[dict],events:list[dict],course) -> list[dict]:
    out=[]
    # Nomination is for human inspection, not automated causal interpretation.
    for s in course.sectors:
        local=[r for r in rows if s.start_m<=float(r['distance_m'])<s.end_m]
        if not local: continue
        for key,kind,fn in [('speed_m_s','sector_min_speed',min),('shift_acceleration_m_s2','peak_shift_acceleration',max),('primary_slip_loss_W','peak_primary_slip_loss',max),('secondary_slip_loss_W','peak_secondary_slip_loss',max)]:
            vals=[r for r in local if finite(r.get(key))]
            if not vals: continue
            pick=fn(vals,key=lambda r:abs(float(r[key])) if key=='shift_acceleration_m_s2' else float(r[key]))
            out.append({'kind':kind,'sector':s.name,'time_s':pick['time_s'],'distance_m':pick['distance_m'],'channel':key,'value':pick[key],'event_id':None})
    for e in events:
        out.append({'kind':'hybrid_transition','sector':course.sector(float(e['distance_m'])).name,'time_s':e['time_s'],'distance_m':e['distance_m'],'channel':'|'.join(e['event_names']),'value':None,'event_id':e['event_id']})
    return out
