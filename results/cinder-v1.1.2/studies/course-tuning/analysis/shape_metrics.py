"""Measure opening-flat free-upshift shape without fitting a whole-course loop.

A primary RPM offset is removed only AFTER matching secondary RPM. Stop dwell,
clutch slip, reversals, road transitions and disconnected paths are excluded.
"""
from __future__ import annotations
from math import isfinite
import numpy as np
from infrastructure.common import finite

FRACTION_MIN=.15
FRACTION_MAX=.85
MIN_COMMON_RPM_SPAN=300.


def eligible(row:dict, launch_end_m:float=120.) -> bool:
    keys=('time_s','distance_m','primary_rpm','secondary_rpm','active_shift_fraction','shift_rate_mm_s')
    return (all(finite(row.get(k)) for k in keys)
        and not row.get('inspection_error') and 0.<=float(row['distance_m'])<launch_end_m
        and row.get('engagement')=='engaged' and row.get('shift_constraint')=='free'
        and row.get('contact_mode')=='stick_stick'
        and FRACTION_MIN<=float(row['active_shift_fraction'])<=FRACTION_MAX
        and float(row['shift_rate_mm_s'])>1e-5)


def launch_parts(rows:list[dict], launch_end_m:float=120.) -> list[list[dict]]:
    """Preserve chronology. Join administrative boundaries only at equal states.

    Duplicate-time state changes split a path. No values from an excluded mode
    are bridged by sorting on speed or discarding intermediate invalid rows.
    """
    parts=[];part=[]
    ordered=sorted(rows,key=lambda r:(float(r.get('time_s',0)),float(r.get('segment_id',0))))
    for r in ordered:
        if finite(r.get('distance_m')) and float(r['distance_m'])>=launch_end_m:
            break
        if not eligible(r,launch_end_m):
            if len(part)>=2:parts.append(part)
            part=[];continue
        if part:
            prev=part[-1]
            dt=float(r['time_s'])-float(prev['time_s'])
            if dt<=1e-12:
                equal=all(abs(float(r[k])-float(prev[k]))<=1e-7 for k in ('primary_rpm','secondary_rpm','active_shift_fraction'))
                if equal:continue
                if len(part)>=2:parts.append(part)
                part=[r];continue
            if (float(r['secondary_rpm'])<=float(prev['secondary_rpm'])+1e-8
                or float(r['active_shift_fraction'])<float(prev['active_shift_fraction'])-1e-7):
                if len(part)>=2:parts.append(part)
                part=[r];continue
        part.append(r)
    if len(part)>=2:parts.append(part)
    return parts


def curve_at(parts:list[list[dict]], grid:np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    """No extrapolation; overlapping distinct paths are ambiguous and masked."""
    y=np.full(grid.shape,np.nan);coverage=np.zeros(grid.shape,dtype=int);ambiguous=np.zeros(grid.shape,dtype=bool)
    for p in parts:
        x=np.asarray([r['secondary_rpm'] for r in p],float)
        v=np.asarray([r['primary_rpm'] for r in p],float)
        mask=(grid>=x[0])&(grid<=x[-1])
        vals=np.interp(grid[mask],x,v)
        occupied=coverage[mask]>0
        prior=y[mask]
        collision=ambiguous[mask] | (occupied & (np.abs(prior-vals)>1e-5))
        ambiguous[mask]=collision
        y[mask]=np.where(collision,np.nan,vals)
        coverage[mask]+=1
    return y,coverage


def crossing(parts:list[list[dict]],fraction:float):
    found=[]
    for p in parts:
        for a,b in zip(p,p[1:]):
            fa=float(a['active_shift_fraction']);fb=float(b['active_shift_fraction'])
            if fa<=fraction<=fb and fb>fa:
                w=(fraction-fa)/(fb-fa)
                found.append({k:float(a[k])+w*(float(b[k])-float(a[k])) for k in ('time_s','secondary_rpm','primary_rpm')})
                break
    return min(found,key=lambda r:r['time_s']) if found else None


def describe(parts:list[list[dict]]) -> dict:
    rows=[r for p in parts for r in p]
    result={'eligible_sample_count':len(rows),'eligible_path_count':len(parts)}
    if not rows:return {**result,'shape_status':'no_eligible_free_stick_upshift'}
    result.update(secondary_rpm_min=min(r['secondary_rpm'] for r in rows),secondary_rpm_max=max(r['secondary_rpm'] for r in rows),
        active_fraction_min=min(r['active_shift_fraction'] for r in rows),active_fraction_max=max(r['active_shift_fraction'] for r in rows))
    nodes={p:crossing(parts,p) for p in (.2,.5,.8)}
    for p,node in nodes.items():
        for k in ('primary_rpm','secondary_rpm','time_s'):
            result[f'{k}_at_f{int(100*p):02d}']=node[k] if node else None
    # Do not span a missing physical branch with a secant.
    for a,b,name in [(.2,.5,'early'),(.5,.8,'late'),(.2,.8,'overall')]:
        covering=[(i,p) for i,p in enumerate(parts) if p[0]['active_shift_fraction']<=a and p[-1]['active_shift_fraction']>=b]
        result[name+'_slope_rpm_per_1000_secondary_rpm']=None
        if covering:
            # Both secant endpoints must belong to the SAME physical path.
            # An earlier partial excursion can also cross a; never mix it with
            # the later complete upshift's b crossing.
            path_id,path=min(covering,key=lambda item:item[1][0]['time_s'])
            pa,pb=crossing([path],a),crossing([path],b)
            if pa and pb and pb['secondary_rpm']>pa['secondary_rpm']+1e-8:
                result[name+'_slope_rpm_per_1000_secondary_rpm']=1000*(pb['primary_rpm']-pa['primary_rpm'])/(pb['secondary_rpm']-pa['secondary_rpm'])
                result[name+'_slope_path_id']=path_id
                result[name+'_slope_start_time_s']=pa['time_s']
                result[name+'_slope_end_time_s']=pb['time_s']
    result['shape_status']='complete_f20_f80' if result['overall_slope_rpm_per_1000_secondary_rpm'] is not None else 'partial_or_disconnected_upshift'
    return result


def longest_true(mask:np.ndarray) -> np.ndarray:
    idx=np.flatnonzero(mask)
    if not len(idx):return idx
    groups=np.split(idx,np.where(np.diff(idx)>1)[0]+1)
    return max(groups,key=len)


def compare_to_reference(parts,reference) -> tuple[dict,list[dict]]:
    if not parts or not reference:return {'comparison_status':'no_overlap'},[]
    lo=max(min(p[0]['secondary_rpm'] for p in parts),min(p[0]['secondary_rpm'] for p in reference))
    hi=min(max(p[-1]['secondary_rpm'] for p in parts),max(p[-1]['secondary_rpm'] for p in reference))
    if hi<=lo:return {'comparison_status':'no_overlap'},[]
    grid=np.linspace(lo,hi,401);pred,_=curve_at(parts,grid);ref,_=curve_at(reference,grid)
    keep=longest_true(np.isfinite(pred)&np.isfinite(ref))
    if len(keep)<3:return {'comparison_status':'insufficient_connected_overlap'},[]
    grid=grid[keep];pred=pred[keep];ref=ref[keep];delta=pred-ref
    offset=float(np.mean(delta));centered=delta-offset;span=float(grid[-1]-grid[0])
    slope=1000*float(np.polyfit(grid-grid.mean(),delta,1)[0])
    stats={'comparison_status':'usable_overlap' if span>=MIN_COMMON_RPM_SPAN else 'narrow_overlap_do_not_rank',
        'common_secondary_rpm_lo':float(grid[0]),'common_secondary_rpm_hi':float(grid[-1]),'common_secondary_rpm_span':span,
        'mean_primary_offset_rpm':offset,'offset_removed_shape_rms_rpm':float(np.sqrt(np.mean(centered**2))),
        'offset_removed_shape_peak_to_peak_rpm':float(np.ptp(centered)),
        'delta_fitted_slope_rpm_per_1000_secondary_rpm':slope}
    points=[{'secondary_rpm':float(x),'primary_rpm':float(y),'reference_primary_rpm':float(z),
        'primary_difference_rpm':float(d),'offset_removed_difference_rpm':float(c)} for x,y,z,d,c in zip(grid,pred,ref,delta,centered)]
    return stats,points


def secants(parts,width:float=200.) -> list[dict]:
    rows=[]
    for idx,p in enumerate(parts):
        x=np.asarray([r['secondary_rpm'] for r in p],float);y=np.asarray([r['primary_rpm'] for r in p],float)
        if x[-1]-x[0]<width:continue
        for n in np.linspace(x[0]+width/2,x[-1]-width/2,30):
            slope=(np.interp(n+width/2,x,y)-np.interp(n-width/2,x,y))/width*1000
            rows.append({'path_id':idx,'secondary_rpm':float(n),'secant_width_secondary_rpm':width,'slope_rpm_per_1000_secondary_rpm':float(slope)})
    return rows
