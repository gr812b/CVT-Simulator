"""Feature-specific summaries from saved data. Values nominate cases, not causes.

In particular, overall shift range includes secular upshift. Opening travel,
maximum drawdown and per-cycle detrended modulation distinguish it from cyclic
backshift. These metrics never certify an asymptotic equilibrium or validation.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import math
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from infrastructure.common import load_json,read_csv,write_csv,write_json,finite,utc_now
from infrastructure.course import Course
from analysis.metrics import first_passage,passage_at


def window_rows(rows,lo,hi):
    return [r for r in rows if lo<=float(r['distance_m'])<=hi and finite(r.get('shift_mm'))]


def interval_summary(rows,lo,hi):
    """Clip time-adjacent continuous edges to a distance window before summing.

    Support/contact modes are constant within a hybrid segment. Bounds of the
    spatial window are linearly located on its saved samples. No integration
    spans a reset or missing segment. Thus durations are sampled, not exact-event
    roots; the raw exact event records remain the source for final event timing.
    """
    duration=0.;upper=0.;lower=0.;opening=0.;closing=0.;back_time=0.;slip_time=0.
    for a,b in zip(rows,rows[1:]):
        if a.get('segment_id')!=b.get('segment_id'):continue
        dt=float(b['time_s'])-float(a['time_s'])
        if dt<=0:continue
        xa=float(a['distance_m']);xb=float(b['distance_m'])
        if abs(xb-xa)<1e-12:
            if not lo<=xa<=hi:continue
            left,right=0.,1.
        else:
            u,v=sorted(((lo-xa)/(xb-xa),(hi-xa)/(xb-xa)))
            left,right=max(0.,u),min(1.,v)
            if right<=left:continue
        span=right-left;weight=dt*span;duration+=weight
        if a.get('shift_constraint')=='upper_stop':upper+=weight
        if a.get('shift_constraint')=='low_ratio_seat':lower+=weight
        if a.get('primary_sliding') or a.get('secondary_sliding'):slip_time+=weight
        if finite(a.get('shift_mm')) and finite(b.get('shift_mm')):
            delta=(float(b['shift_mm'])-float(a['shift_mm']))*span
            opening+=max(0.,-delta);closing+=max(0.,delta)
        if finite(a.get('shift_rate_mm_s')) and finite(b.get('shift_rate_mm_s')):
            if .5*(float(a['shift_rate_mm_s'])+float(b['shift_rate_mm_s']))<-.1:back_time+=weight
    return {'duration_s':duration,'upper_stop_duration_s':upper,'low_ratio_seat_duration_s':lower,
        'upper_stop_fraction':upper/duration if duration else None,'low_ratio_seat_fraction':lower/duration if duration else None,
        'opening_travel_mm':opening,'closing_travel_mm':closing,'backshift_duration_s':back_time,'sliding_duration_s':slip_time}


def _range(rows,key):
    vals=[float(r[key]) for r in rows if finite(r.get(key))]
    return (min(vals),max(vals)) if vals else (None,None)


def _drawdown(rows):
    values=[float(r['shift_mm']) for r in rows if finite(r.get('shift_mm'))]
    if not values:return None
    best=values[0];drop=0.
    for v in values:best=max(best,v);drop=max(drop,best-v)
    return drop


def _cycle_rows(car,rows,course):
    sector=next((s for s in course.sectors if s.name=='cyclic'),None)
    if sector is None:return []
    out=[];x,t=first_passage(rows)
    for cycle in range(course.count):
        lo=sector.start_m+cycle*course.wavelength;hi=lo+course.wavelength
        r=window_rows(rows,lo,hi);start=passage_at(x,t,lo);end=passage_at(x,t,hi)
        vals=[rr for rr in r if not rr.get('inspection_error')]
        minimum,maximum=_range(vals,'shift_mm')
        # Use one value per attained distance; no repeat-weighting of checkpoints.
        dist,y=[],[];last=-float('inf')
        for rr in vals:
            xx=float(rr['distance_m'])
            if xx>last+1e-10:dist.append(xx);y.append(float(rr['shift_mm']));last=xx
        amplitude=None
        if len(dist)>=6 and (dist[-1]-dist[0])>=.85*course.wavelength:
            phase=2*np.pi*(np.asarray(dist)-lo)/course.wavelength
            M=np.column_stack([np.ones(len(phase)),phase,np.cos(phase),np.sin(phase)])
            coeff=np.linalg.lstsq(M,np.asarray(y),rcond=None)[0]
            amplitude=2.*float(np.hypot(coeff[2],coeff[3]))
        env=float(course.config.get('cyclic_envelope_length_m',course.envelope_periods*course.wavelength))
        interior=lo>=sector.start_m+env-1e-8 and hi<=sector.end_m-env+1e-8
        out.append({'id':car,'cycle_index':cycle+1,'start_m':lo,'end_m':hi,'completed':end is not None,
            'full_amplitude_cycle':interior,'cycle_time_s':end-start if start is not None and end is not None else None,
            'shift_min_mm':minimum,'shift_max_mm':maximum,'shift_peak_to_peak_mm':maximum-minimum if minimum is not None else None,
            'max_backshift_drawdown_mm':_drawdown(vals),'detrended_first_harmonic_peak_to_peak_mm':amplitude,
            **interval_summary(rows,lo,hi)})
    return out


def analyze_car(car,rows,course,summary):
    rows=sorted(rows,key=lambda r:(float(r['time_s']),int(r.get('segment_id',0))))
    x,t=first_passage(rows)
    out={'id':car,'status':summary.get('status'),'review_required':summary.get('review_required'),
        'max_distance_m':summary.get('max_distance_m'),'finish_time_s':summary.get('finish_time_s')}
    flat=next(s for s in course.sectors if s.name=='launch_flat')
    rf=window_rows(rows,flat.start_m,flat.end_m)
    out['opening_flat_completed']=passage_at(x,t,flat.end_m) is not None
    out['opening_flat_reached_upper_stop']=any(r.get('shift_constraint')=='upper_stop' for r in rf)
    out['opening_flat_max_shift_mm']=_range(rf,'shift_mm')[1]
    out['opening_flat_max_active_fraction']=_range(rf,'active_shift_fraction')[1]
    early=window_rows(rows,0.,min(120.,flat.end_m))
    out['reached_upper_by_120m']=any(r.get('shift_constraint')=='upper_stop' for r in early)
    high=next((r for r in rf if r.get('shift_constraint')=='upper_stop'),None)
    out['flat_first_upper_distance_m']=float(high['distance_m']) if high else None
    if rf:
        last=max(float(r['time_s']) for r in rf)
        tail=[r for r in rf if float(r['time_s'])>=last-10.]
        tail=list({float(r['time_s']):r for r in tail}.values())
        span=last-min(float(r['time_s']) for r in tail)
        out['flat_tail_duration_s']=span
        out['flat_tail_shift_min_mm'],out['flat_tail_shift_max_mm']=_range(tail,'shift_mm')
        out['flat_tail_speed_min_m_s'],out['flat_tail_speed_max_m_s']=_range(tail,'speed_m_s')
        out['flat_tail_shift_slope_mm_s']=float(np.polyfit([float(r['time_s'])-last for r in tail],[float(r['shift_mm']) for r in tail],1)[0]) if len(tail)>2 and span>1 else None
    for label,names in [('main_hill',('hill_entry','hill_hold','hill_exit')),('secondary_hill',('secondary_hill_entry','secondary_hill_hold','secondary_hill_exit')),('cyclic',('cyclic',))]:
        sectors=[s for s in course.sectors if s.name in names]
        if not sectors:continue
        lo=sectors[0].start_m;hi=sectors[-1].end_m
        r=window_rows(rows,lo,hi);vals=[rr for rr in r if not rr.get('inspection_error')]
        entry=passage_at(x,t,lo);exit=passage_at(x,t,hi)
        out[label+'_visited']=entry is not None;out[label+'_completed']=exit is not None
        for k,v in interval_summary(rows,lo,hi).items():out[label+'_'+k]=v if entry is not None else None
        for key,name in [('shift_mm','shift_mm'),('active_shift_fraction','active_fraction'),('speed_m_s','speed_m_s'),('cyclic_encounter_frequency_hz','encounter_hz'),('upper_stop_reaction_N','upper_stop_reaction_N')]:
            a,b=_range(vals,key);out[label+'_min_'+name]=a;out[label+'_max_'+name]=b
        out[label+'_net_shift_mm']=float(vals[-1]['shift_mm'])-float(vals[0]['shift_mm']) if vals else None
        drop=_drawdown(vals);out[label+'_max_backshift_drawdown_mm']=drop
        if label=='secondary_hill':
            frac=out.get(label+'_min_active_fraction')
            seated=any(r.get('shift_constraint')=='low_ratio_seat' for r in vals)
            # Nomination threshold only, not a new contact or solver tolerance.
            out['partial_backshift_candidate']=bool(not summary.get('review_required') and exit is not None and drop is not None and drop>=.25 and not seated and frac is not None and frac>.003)
    cycles=_cycle_rows(car,rows,course)
    complete=[c for c in cycles if c['completed'] and c['full_amplitude_cycle']]
    amplitudes=[c['detrended_first_harmonic_peak_to_peak_mm'] for c in complete if c['detrended_first_harmonic_peak_to_peak_mm'] is not None]
    out['cyclic_median_detrended_modulation_mm']=float(np.median(amplitudes)) if amplitudes else None
    out['cyclic_resolved_full_amplitude_cycles']=len(complete)
    return out,cycles


def analyze_campaign(run_dir: Path):
    run_dir=Path(run_dir).resolve();manifest=load_json(run_dir/'campaign.json');course=Course(manifest['course'])
    rows=[];cycles=[]
    for p in sorted((run_dir/'cases').iterdir()):
        if not (p/'summary.json').exists() or not (p/'diagnostics.csv').exists():continue
        result,c=analyze_car(p.name,read_csv(p/'diagnostics.csv'),course,load_json(p/'summary.json'))
        rows.append(result);cycles.extend(c)
    write_csv(run_dir/'feature_metrics.csv',rows);write_csv(run_dir/'cyclic_cycle_metrics.csv',cycles)
    write_json(run_dir/'feature_metric_definitions.json',{
        'generated_utc':utc_now(),'partial_backshift_candidate':'Completed added hill; sampled drawdown >= 0.25 mm; no sampled low-ratio-seat mode; minimum active fraction > 0.003. A screening label, not a model setting.',
        'opening_travel_mm':'Sum of negative shift increments on continuous sampled edges clipped to the sector; excludes reset jumps.',
        'max_backshift_drawdown_mm':'Largest fall from an earlier sampled shift maximum in the window. Distinguishes backshift from ordinary continuing upshift.',
        'detrended_first_harmonic_peak_to_peak_mm':'Each resolved cycle: least squares offset + linear spatial trend + cos/sin of spatial phase; 2*hypot(cos coefficient,sin coefficient). Empirical modulation, not a transfer function or causal isolation.',
        'flat_tail':'Last at most 10 seconds of the observed opening flat. Small slope is finite-time evidence only, never proof a vehicle can NEVER attain high ratio.',
        'durations':'Segment-preserving sampled time quadrature, linearly clipped at spatial boundaries. Consult events.json for exact event times.',
        'scope':'Unvisited sectors are missing. Incomplete/review cases are not silently counted as successful feature demonstrations.'})
    return rows,cycles


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run_dir',type=Path)
    a=p.parse_args();analyze_campaign(a.run_dir);print(a.run_dir/'feature_metrics.csv')
if __name__=='__main__':main()
