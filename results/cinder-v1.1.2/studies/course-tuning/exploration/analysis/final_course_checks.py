"""Check observed interior settling and repeated loads from saved trajectories.

This is post-processing, not an equilibrium solver. The road, force laws,
velocities, integrator, and stopping rules are never modified by these checks.
"""
from __future__ import annotations

import argparse
import html
from pathlib import Path
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.common import (load_json, read_csv, write_json, write_csv,
                                   finite, utc_now)
from infrastructure.course import Course
from analysis.feature_metrics import analyze_campaign, interval_summary

# Operational evidence thresholds, not physical or numerical solver parameters.
DEFAULT_CRITERIA = {
    'window_s': 5.0,
    'window_stride_s': 0.25,
    'maximum_sample_gap_s': 0.10,
    'interior_clearance_mm': 0.25,
    'minimum_forward_speed_m_s': 0.10,
    'grade_tolerance_deg': 1e-6,
    'max_abs_shift_rate_mm_s': 0.05,
    'max_abs_vehicle_acceleration_m_s2': 0.01,
    'max_abs_primary_rpm_rate_rpm_s': 2.0,
    'max_abs_secondary_rpm_rate_rpm_s': 2.0,
    'max_abs_belt_acceleration_m_s2': 0.01,
    'max_abs_shift_acceleration_m_s2': 0.0005,
    'shift_range_mm': 0.10,
    'vehicle_speed_range_m_s': 0.05,
    'primary_rpm_range': 10.0,
    'secondary_rpm_range': 10.0,
    'belt_speed_range_m_s': 0.05,
}
RATE_FIELDS = {
    'max_abs_shift_rate_mm_s': ('shift_rate_mm_s', 1.0),
    'max_abs_vehicle_acceleration_m_s2': ('vehicle_acceleration_m_s2', 1.0),
    'max_abs_primary_rpm_rate_rpm_s': ('primary_alpha_rad_s2', 60.0/(2*np.pi)),
    'max_abs_secondary_rpm_rate_rpm_s': ('secondary_alpha_rad_s2', 60.0/(2*np.pi)),
    'max_abs_belt_acceleration_m_s2': ('belt_acceleration_m_s2', 1.0),
    'max_abs_shift_acceleration_m_s2': ('shift_acceleration_m_s2', 1.0),
}
RANGE_FIELDS = {
    'shift_range_mm': 'shift_mm',
    'vehicle_speed_range_m_s': 'speed_m_s',
    'primary_rpm_range': 'primary_rpm',
    'secondary_rpm_range': 'secondary_rpm',
    'belt_speed_range_m_s': 'belt_speed_m_s',
}
MEAN_FIELDS = (
    'shift_mm', 'active_shift_fraction', 'speed_m_s', 'primary_rpm',
    'secondary_rpm', 'belt_speed_m_s', 'geometric_ratio_rp_over_rs',
    'shaft_speed_ratio_ws_over_wp', 'primary_actuator_closing_N',
    'secondary_actuator_closing_N', 'normal_primary_N', 'normal_secondary_N',
    'primary_lambda', 'secondary_lambda', 'primary_slip_loss_W',
    'secondary_slip_loss_W', 'primary_boundary_power_W',
)


def _ordered(rows: list[dict]) -> list[dict]:
    # Keep the successor at duplicate event/checkpoint timestamps. Event records
    # are separately checked, so this cannot conceal an event inside a window.
    return list({float(r['time_s']): r for r in sorted(
        rows, key=lambda r: (float(r['time_s']), int(r.get('segment_id', 0))))}.values())


def _array(rows, key, factor=1.):
    return np.asarray([factor*float(r[key]) if finite(r.get(key)) else np.nan
                       for r in rows], dtype=float)


def evaluate_window(rows: list[dict], events: list[dict], limits: dict,
                    low_mm: float, high_mm: float, grade_deg: float) -> dict:
    """Require simultaneous near-stationarity, interior free shift and coverage.

    Derivatives come from the saved solved RHS, never finite differences. The
    host distance continues increasing and is intentionally not a steady state.
    """
    if not rows:
        return {'passed': False, 'failed_checks': ['no_samples']}
    t = _array(rows, 'time_s')
    duration = float(t[-1]-t[0])
    result: dict[str, Any] = {
        'start_time_s': float(t[0]), 'end_time_s': float(t[-1]),
        'start_distance_m': float(rows[0]['distance_m']),
        'end_distance_m': float(rows[-1]['distance_m']),
        'duration_s': duration, 'sample_count': len(rows),
    }
    failed = []
    if duration < limits['window_s']-1e-7:
        failed.append('insufficient_duration')
    if len(t) < 2 or np.max(np.diff(t)) > limits['maximum_sample_gap_s']+1e-9:
        failed.append('insufficient_sample_resolution')
    if any(r.get('inspection_error') for r in rows):
        failed.append('inspection_error')
    if any(r.get('engagement') != 'engaged' or r.get('shift_constraint') != 'free'
           for r in rows):
        failed.append('not_engaged_free_shift')
    contact_modes = sorted(set(str(r.get('contact_mode', '')) for r in rows))
    result['contact_modes'] = contact_modes
    if len(contact_modes) != 1 or contact_modes[0] in ('', 'None'):
        failed.append('contact_regime_changed_or_missing')
    transitions = [e for e in events if t[0] < float(e['time_s']) <= t[-1]
                   and any(str(n).startswith('cvt:') for n in e.get('event_names', []))]
    result['physical_event_count'] = len(transitions)
    if transitions:
        failed.append('physical_event_in_window')
    s = _array(rows, 'shift_mm')
    clearance = limits['interior_clearance_mm']
    if not np.isfinite(s).all() or np.min(s) <= low_mm+clearance or np.max(s) >= high_mm-clearance:
        failed.append('insufficient_distance_from_travel_stops')
    v = _array(rows, 'speed_m_s')
    if not np.isfinite(v).all() or np.min(v) <= limits['minimum_forward_speed_m_s']:
        failed.append('not_forward_travelling')
    grade = _array(rows, 'grade_deg')
    if not np.isfinite(grade).all() or np.max(np.abs(grade-grade_deg)) > limits['grade_tolerance_deg']:
        failed.append('not_constant_target_grade')
    for name, (key, factor) in RATE_FIELDS.items():
        values = _array(rows, key, factor)
        value = float(np.max(np.abs(values))) if np.isfinite(values).all() else None
        result[name] = value
        if value is None or value > limits[name]:
            failed.append(name)
    for name, key in RANGE_FIELDS.items():
        values = _array(rows, key)
        value = float(np.ptp(values)) if np.isfinite(values).all() else None
        result[name] = value
        if value is None or value > limits[name]:
            failed.append(name)
    for key in MEAN_FIELDS:
        values = _array(rows, key)
        result['mean_'+key] = (float(np.trapezoid(values, t)/duration)
                               if duration > 0 and np.isfinite(values).all() else None)
    result['passed'] = not failed
    result['failed_checks'] = failed
    return result


def check_hill(car: str, rows: list[dict], events: list[dict], course: Course,
               summary: dict, document: dict, limits: dict) -> tuple[dict, list[dict]]:
    sector = next((s for s in course.sectors if s.name == 'secondary_hill_hold'), None)
    result = {'id': car, 'status': summary.get('status'),
              'case_review_required': bool(summary.get('review_required')),
              'settled_at_hold_exit': False, 'passing_window_seen': False}
    if sector is None:
        return {**result, 'settling_status': 'no_secondary_hill'}, []
    rows = _ordered(rows)
    # Conservative: no interpolation through a ramp, reset or unsampled gap.
    hold = [r for r in rows if sector.start_m <= float(r['distance_m']) < sector.end_m]
    result.update(hold_start_m=sector.start_m, hold_end_m=sector.end_m,
                  hold_length_m=sector.end_m-sector.start_m,
                  hold_grade_deg=sector.start_deg)
    if not hold:
        return {**result, 'settling_status': 'hill_not_reached'}, []
    geometry = document['assembly']['geometry']
    low_mm = 1000*float(geometry['deadzone_shift_m'])
    high_mm = 1000*float(geometry['max_shift_m'])
    times = _array(hold, 'time_s')
    hold_completed = any(float(r['distance_m']) >= sector.end_m for r in rows)
    result.update(hold_completed=hold_completed, observed_hold_duration_s=float(times[-1]-times[0]))
    endpoint_indices = []
    next_time = times[0]+limits['window_s']
    for k, t in enumerate(times):
        if t >= next_time:
            endpoint_indices.append(k)
            next_time = t+limits['window_stride_s']
    if not endpoint_indices or endpoint_indices[-1] != len(times)-1:
        endpoint_indices.append(len(times)-1)
    windows = []
    for k in endpoint_indices:
        # Include the sample just before the intended start so the window covers
        # at least window_s. Extra coverage is <= maximum_sample_gap_s.
        j = max(0, int(np.searchsorted(times, times[k]-limits['window_s'], side='right'))-1)
        item = evaluate_window(hold[j:k+1], events, limits, low_mm, high_mm, sector.start_deg)
        windows.append({'id': car, **item})
    tail = windows[-1]
    passing = [w for w in windows if w['passed']]
    result.update(passing_window_seen=bool(passing),
                  first_passing_window_start_m=passing[0]['start_distance_m'] if passing else None,
                  first_passing_window_end_m=passing[0]['end_distance_m'] if passing else None,
                  first_passing_window_end_time_s=passing[0]['end_time_s'] if passing else None,
                  tail_window_passed=tail['passed'],
                  tail_window_failed_checks=tail['failed_checks'])
    result.update({'tail_'+key: value for key, value in tail.items() if key != 'id'})
    # Once a sustained passing tail begins, check every sampled sliding window
    # through exit, not only an isolated favourable five-second interval.
    last_failure = max((i for i,w in enumerate(windows) if not w['passed']), default=-1)
    sustained = windows[last_failure+1:]
    result['sustained_tail_verified_from_m'] = sustained[0]['start_distance_m'] if sustained else None
    result['sustained_tail_verified_duration_s'] = (tail['end_time_s']-sustained[0]['start_time_s']) if sustained else 0.
    at_exit = bool(hold_completed and tail['passed'])
    result['settled_at_hold_exit'] = at_exit
    if summary.get('review_required'):
        result['settling_status'] = 'case_requires_review'
    elif not hold_completed:
        result['settling_status'] = 'hill_incomplete'
    elif at_exit:
        result['settling_status'] = 'observed_steady_interior'
    elif tail.get('duration_s',0) < limits['window_s']-1e-7:
        result['settling_status'] = 'hold_too_short_to_test'
    elif passing:
        result['settling_status'] = 'passing_window_seen_but_not_at_exit'
    else:
        result['settling_status'] = 'still_evolving_or_not_interior'
    return result, windows


def _table(rows, columns):
    def f(v):
        if v is None: return '\u2014'
        if isinstance(v, float): return f'{v:.5g}'
        if isinstance(v, list): return ', '.join(map(str,v))
        return str(v)
    return '<table><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in columns)+'</tr>'+''.join(
        '<tr>'+''.join('<td>'+html.escape(f(row.get(k)))+'</td>' for k in columns)+'</tr>' for row in rows)+'</table>'


def _plot_lines(out: Path, datasets, key, ylabel, title, low_mm=None, high_mm=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for car, rows, windows, course in datasets:
        entry = next(s.start_m for s in course.sectors if s.name=='secondary_hill_entry')
        hold = next(s for s in course.sectors if s.name=='secondary_hill_hold')
        exit_sector = next(s for s in course.sectors if s.name=='secondary_hill_exit')
        selected = [r for r in rows if entry <= float(r['distance_m']) <= exit_sector.end_m]
        if not selected: continue
        t0=float(selected[0]['time_s'])
        # Retain segment breaks. No fictitious line across a velocity reset.
        tx=[]; yy=[]; previous=None
        for r in selected:
            if previous is not None and r.get('segment_id') != previous:
                tx.append(np.nan); yy.append(np.nan)
            tx.append(float(r['time_s'])-t0)
            yy.append(float(r[key]) if finite(r.get(key)) else np.nan)
            previous=r.get('segment_id')
        line,=ax.plot(tx,yy,label=car,linewidth=1.25)
        # Explicit event/feature markers inherit their tune's line colour.
        for boundary,marker in [(hold.start_m,'o'),(hold.end_m,'s')]:
            r=min(selected,key=lambda q:abs(float(q['distance_m'])-boundary))
            if finite(r.get(key)):
                ax.plot(float(r['time_s'])-t0,float(r[key]),marker=marker,
                        color=line.get_color(),markersize=4)
    if key=='shift_mm' and low_mm is not None:
        ax.axhline(low_mm,linestyle=':',linewidth=.9,label='Low-ratio seat')
        ax.axhline(high_mm,linestyle='--',linewidth=.9,label='Upper stop')
    ax.set(xlabel='Time since each vehicle entered the moderate hill [s]',ylabel=ylabel,title=title)
    ax.grid(True,alpha=.25); ax.legend(fontsize=8,ncol=3)
    fig.tight_layout();fig.savefig(out,dpi=150);plt.close(fig)



def _failure_figures(destination, car, rows, events, course):
    """Keep stall/rollback chronology visible; distance is not one-to-one there."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    hill=next((s for s in course.sectors if s.name=='hill_entry'),None)
    rows=_ordered(rows)
    reached=next((r for r in rows if hill and float(r['distance_m'])>=hill.start_m),None)
    if reached is None:return []
    start=float(reached['time_s'])
    rows=[r for r in rows if float(r['time_s'])>=start]
    out=destination/car;out.mkdir(exist_ok=True)
    views=[
        ('failure_vehicle_speed','Vehicle speed [m/s]', [('speed_m_s','Vehicle')]),
        ('failure_engine_speed','Primary speed [rpm]', [('primary_rpm','Primary shaft')]),
        ('failure_power','Power [W]', [('primary_boundary_power_W','Engine boundary'),
                                     ('primary_slip_loss_W','Primary kinetic-slip dissipation'),
                                     ('secondary_slip_loss_W','Secondary kinetic-slip dissipation')]),
    ]
    paths=[]
    for name,ylabel,fields in views:
        fig,ax=plt.subplots(figsize=(10,5.0))
        for key,label in fields:
            tx=[];yy=[];previous=None
            for row in rows:
                if previous is not None and row.get('segment_id')!=previous:
                    tx.append(np.nan);yy.append(np.nan)
                tx.append(float(row['time_s']))
                yy.append(float(row[key]) if finite(row.get(key)) else np.nan)
                previous=row.get('segment_id')
            ax.plot(tx,yy,label=label,linewidth=1.25)
        groups=[]
        gap=.025*max(1.,float(rows[-1]['time_s'])-start)
        for event in sorted(events,key=lambda e:float(e['time_s'])):
            t=float(event['time_s'])
            if not start<=t<=float(rows[-1]['time_s']):continue
            ax.axvline(t,linestyle=':',linewidth=.65)
            if groups and t-float(groups[-1][-1]['time_s'])<gap:
                groups[-1].append(event)
            else:
                groups.append([event])
        for group in groups:
            labels=[str(e.get('event_id','')) for e in group]
            label=labels[0] if len(labels)==1 else labels[0]+'–'+labels[-1]
            position=float(np.mean([float(e['time_s']) for e in group]))
            ax.text(position,.97,label,transform=ax.get_xaxis_transform(),
                    rotation=90,va='top',ha='right',fontsize=8)
        ax.axhline(0.,linestyle='--',linewidth=.7)
        ax.set(xlabel='Elapsed simulation time [s]',ylabel=ylabel,
               title=car+': main-hill chronology (event IDs match the exact event record)')
        ax.grid(True,alpha=.25);ax.legend(fontsize=8);fig.tight_layout()
        target=out/(name+'.png');fig.savefig(target,dpi=150);plt.close(fig)
        paths.append(target.relative_to(destination).as_posix())
    return paths


def build_report(run_dir: Path, criteria: dict | None=None, plots: bool=True) -> Path:
    run_dir=Path(run_dir).resolve()
    manifest=load_json(run_dir/'campaign.json');course=Course(manifest['course'])
    unknown=set(criteria or {})-set(DEFAULT_CRITERIA)
    if unknown:
        raise ValueError('Unknown settling criteria: '+', '.join(sorted(unknown)))
    criteria={**DEFAULT_CRITERIA,**(criteria or {})}
    if any(not finite(v) or float(v)<=0 for v in criteria.values()):
        raise ValueError('Settling criteria must be finite and positive')
    destination=run_dir/'final_checks';destination.mkdir(exist_ok=True)
    analyze_campaign(run_dir)
    all_summaries=[];all_windows=[];datasets=[];overview=[];failure_data=[]
    for path in sorted((run_dir/'cases').iterdir()):
        if not (path/'diagnostics.csv').is_file() or not (path/'summary.json').is_file():continue
        rows=read_csv(path/'diagnostics.csv');summary=load_json(path/'summary.json')
        document=load_json(path/'resolved_case.json')['public_document']
        events=load_json(path/'events.json') if (path/'events.json').exists() else []
        result,windows=check_hill(path.name,rows,events,course,summary,document,criteria)
        all_summaries.append(result);all_windows.extend(windows)
        if summary.get('status') in ('progress_limited','rollback'):
            failure_data.append((path.name,rows,events))
        if result['settling_status'] not in ('hill_not_reached','no_secondary_hill'):
            datasets.append((path.name,_ordered(rows),windows,course))
        row={'id':path.name,**{k:summary.get(k) for k in
             ('status','review_required','finish_time_s','max_distance_m',
              'primary_slip_work_J','secondary_slip_work_J','physical_transition_count')}}
        hill=[s for s in course.sectors if s.name in ('hill_entry','hill_hold','hill_exit')]
        if hill:row.update({'hill_'+k:v for k,v in interval_summary(rows,hill[0].start_m,hill[-1].end_m).items()})
        row['moderate_hill_status']=result['settling_status'];overview.append(row)
    write_csv(destination/'settling_summary.csv',all_summaries)
    write_csv(destination/'settling_windows.csv',all_windows)
    write_csv(destination/'course_outcomes.csv',overview)
    write_json(destination/'definitions.json',{
        'generated_utc':utc_now(),'criteria':criteria,
        'meaning':'Observed near-stationary interior travelling operation on a constant grade over the declared window; not proof of asymptotic stability.',
        'derivatives':'Saved solved CVT RHS; primary/secondary angular acceleration converted to rpm/s. Vehicle acceleration follows the fixed final drive.',
        'time_windows':'Five-second trailing windows checked every 0.25 seconds and at the last hold sample; include the preceding saved sample to cover the full duration. Gaps >0.1 s fail the coverage check.',
        'travel_conditions':'Engaged free shift, >0.25 mm from both travel stops and >0.1 m/s forward speed; one unchanged contact mode and no physical CVT events in each window.',
        'range_checks':'All five speed/shift variables must satisfy their range bounds, as well as the RHS derivative bounds. The distance/shaft-angle host is allowed to keep growing.',
        'case_review':'Case-wide mechanical/inspection review flags are reported separately and override the headline steady classification.',
        'alignment':'Plot times are relative to each car\'s own hill-entry time only for local comparison. No trajectories are restarted and no entry states are made equal.',
        'cycle_analysis':'../cyclic_cycle_metrics.csv separates full-amplitude cycles from tapered entry/exit cycles; per-cycle differences are not claimed to prove a periodic attractor.',
    })
    order={item['id']:index for index,item in enumerate(manifest['competitors'])}
    datasets.sort(key=lambda entry:order.get(entry[0],len(order)))
    images=[]
    if plots and datasets:
        # Geometry is common to all study entrants.
        d=load_json(run_dir/'cases'/datasets[0][0]/'resolved_case.json')['public_document']['assembly']['geometry']
        for key,ylabel in [('shift_mm','Shift [mm]'),('shift_rate_mm_s','Shift rate [mm/s]'),
                           ('speed_m_s','Vehicle speed [m/s]'),('vehicle_acceleration_m_s2','Vehicle acceleration [m/s²]'),
                           ('primary_rpm','Primary speed [rpm]')]:
            name='moderate_hill_'+key+'.png'
            _plot_lines(destination/name,datasets,key,ylabel,'Moderate hill: transient approach and interior settling',
                        1000*d['deadzone_shift_m'],1000*d['max_shift_m'])
            images.append(name)
        for car,rows,windows,c in datasets:
            sub=destination/car;sub.mkdir(exist_ok=True)
            for key,ylabel in [('shift_mm','Shift [mm]'),('speed_m_s','Vehicle speed [m/s]')]:
                _plot_lines(sub/(key+'.png'),[(car,rows,windows,c)],key,ylabel,
                            car+': constant-grade response (circles: hold entry, squares: hold exit)',
                            1000*d['deadzone_shift_m'],1000*d['max_shift_m'])
    failure_images=[]
    if plots:
        for car,rows,events in failure_data:
            failure_images.extend(_failure_figures(destination,car,rows,events,course))
    cycle_file=run_dir/'cyclic_cycle_metrics.csv'
    cycle_rows=read_csv(cycle_file) if cycle_file.exists() else []
    feature_rows=read_csv(run_dir/'feature_metrics.csv')
    text='''<!doctype html><html><head><meta charset="utf-8"><title>Unified-course final checks</title>
<style>body{font:15px system-ui,sans-serif;max-width:1400px;margin:2rem}table{border-collapse:collapse;display:block;overflow:auto}th,td{border:1px solid #bbb;padding:.45rem;text-align:left}img{max-width:100%;margin:1rem 0}p{line-height:1.5}code{background:#eee}</style></head><body>
<h1>Unified-course final checks</h1><p><a href="../index.html">Full course and mechanical report</a> · <a href="../shift_curves.html">Phase-coloured shift curves</a></p>
<p>One unchanged full-throttle vehicle history per tune. Near-stationarity is checked from multiple state variables and their solved derivatives, not inferred from a flat-looking shift curve. The five-second test is an operational criterion, not proof of an exact equilibrium or its stability.</p>'''
    text+='<p>Campaign: <code>'+html.escape(run_dir.name)+'</code></p>'
    text+='<h2>Whole-course outcomes</h2>'+_table(overview,['id','status','review_required','finish_time_s','max_distance_m','hill_sliding_duration_s','moderate_hill_status'])
    text+='<h2>Does the moderate hill end in steady interior operation?</h2>'+_table(all_summaries,[
        'id','settling_status','tail_contact_modes','tail_mean_shift_mm','tail_mean_speed_m_s','tail_mean_primary_rpm',
        'sustained_tail_verified_duration_s','first_passing_window_end_m','tail_window_failed_checks'])
    text+='<p>Means are over the last tested window, even when it fails: they must not be quoted as equilibria for failed rows. Full checks: <a href="settling_summary.csv">summary</a> · <a href="settling_windows.csv">every tested window</a> · <a href="definitions.json">definitions and thresholds</a>. Circles and squares on the hill plots locate hold entry and exit for each car.</p>'
    text+=''.join(f'<a href="{n}"><img loading="lazy" src="{n}"></a>' for n in images)
    text+='<h2>Individual moderate-hill views</h2>'
    for car,_,_,_ in datasets:
        text+=f'<details><summary>{html.escape(car)}</summary>'
        if plots:
            for name in ['shift_mm','speed_m_s']:
                text+=f'<a href="{car}/{name}.png"><img loading="lazy" src="{car}/{name}.png"></a>'
        text+='</details>'
    if failure_images:
        text+='<h2>Main-hill non-completion in time</h2><p>Forward rotation and backward vehicle motion remain distinguishable. Event IDs link the changes to the saved event records. These plots are chronological; road positions can be revisited during rollback.</p>'
        text+=''.join(f'<a href="{name}"><img loading="lazy" src="{name}"></a>' for name in failure_images)
    text+='<h2>Opening flat and cycle coverage</h2>'+_table(feature_rows,['id','opening_flat_reached_upper_stop','opening_flat_max_shift_mm','cyclic_resolved_full_amplitude_cycles','cyclic_max_backshift_drawdown_mm','cyclic_upper_stop_fraction'])
    envelope=float(course.config.get('cyclic_envelope_length_m',course.envelope_periods*course.wavelength))
    interior_periods=sum(k*course.wavelength>=envelope-1e-8 and
                         (k+1)*course.wavelength<=course.count*course.wavelength-envelope+1e-8
                         for k in range(course.count))
    text+=f'<h2>Cycle-by-cycle response</h2><p>The course has {course.count} periods, of which {interior_periods} are fully outside the amplitude tapers. The table preserves entry and exit cycles rather than mixing them into a nominal periodic amplitude.</p>'+_table(cycle_rows,[
        'id','cycle_index','full_amplitude_cycle','completed','cycle_time_s','shift_min_mm','shift_max_mm','max_backshift_drawdown_mm','upper_stop_fraction'])
    text+='</body></html>'
    (destination/'index.html').write_text(text,encoding='utf-8')
    # Add a navigation link to the existing report, never rewrite its content.
    main=run_dir/'index.html'
    if main.exists():
        body=main.read_text(encoding='utf-8');marker='<!-- final-course-checks -->'
        if marker not in body:
            body=body.replace('<body>','<body>'+marker+'<p><a href="final_checks/index.html"><b>Unified-course settling and cycle checks</b></a></p>',1)
            main.write_text(body,encoding='utf-8')
    return destination/'index.html'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('campaign',type=Path)
    p.add_argument('--criteria',type=Path,help='JSON overrides of the documented operational criteria')
    p.add_argument('--no-plots',action='store_true')
    a=p.parse_args()
    print(build_report(a.campaign,load_json(a.criteria) if a.criteria else None,not a.no_plots))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
