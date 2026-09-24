"""Collect feature trials and compare their local responses, not race rankings.

Every linked campaign still compares entrants on an identical course. Different
feature variants have different roads and must not share a finish-time ranking.
"""
from __future__ import annotations
import argparse
import html
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from infrastructure.common import load_json,read_csv,write_csv,write_json,finite
from infrastructure.course import Course
from infrastructure.paths import saved_campaign_path
from analysis.feature_metrics import analyze_campaign
from analysis.report import table,plot_lines


def build_comparison(plan_file:Path):
    plan_file=Path(plan_file).resolve();folder=plan_file.parent;plan=load_json(plan_file)
    rows=[];cycles=[];links=[];data={}
    for trial in plan['trials']:
        if not trial.get('campaign_dir'):continue
        run=saved_campaign_path(trial['campaign_dir'], plan_file)
        if not (run/'campaign.json').is_file():continue
        manifest=load_json(run/'campaign.json')
        # Refuse a stale/mismatched path file rather than mix two roads.
        if manifest['course']!=trial['course']:raise ValueError(f"Stored campaign differs from plan: {trial['id']}")
        rr,cc=analyze_campaign(run)
        selected=set(trial['cars'])
        rows.extend({'variant':trial['id'],'group':trial['group'],**r} for r in rr if r['id'] in selected)
        cycles.extend({'variant':trial['id'],'group':trial['group'],**c} for c in cc if c['id'] in selected)
        rel=Path(os.path.relpath(run/'index.html',folder)).as_posix()
        links.append(f'<li><a href="{html.escape(rel)}">{html.escape(trial["id"])}</a>: {html.escape(trial["role"])}</li>')
        for car in trial['cars']:
            p=run/'cases'/car/'diagnostics.csv'
            if p.exists():data[(trial['id'],car)]=read_csv(p)
    write_csv(folder/'feature_comparison.csv',rows);write_csv(folder/'cycle_comparison.csv',cycles)
    images=[]
    # Same car, different feature variants: directly compare disturbance response.
    for group,sector_names in [('mild_hill',('secondary_hill_entry','secondary_hill_hold','secondary_hill_exit')),('cyclic',('cyclic',))]:
        trials=[t for t in plan['trials'] if t['group']==group and t.get('campaign_dir')]
        cars=list(dict.fromkeys(c for t in trials for c in t['cars']))
        for car in cars:
            series=[]
            for trial in trials:
                course=Course(trial['course']);sectors=[s for s in course.sectors if s.name in sector_names]
                if not sectors:continue
                lo,hi=sectors[0].start_m,sectors[-1].end_m
                r=[{**r,'feature_distance_m':float(r['distance_m'])-lo} for r in data.get((trial['id'],car),[]) if lo<=float(r['distance_m'])<=hi]
                if r:series.append((trial['id'],r))
            if not series:continue
            for key,label in [('shift_mm','Shift [mm]'),('shift_rate_mm_s','Shift rate [mm/s]'),('primary_rpm','Primary speed [rpm]'),('speed_m_s','Vehicle speed [m/s]')]:
                out=folder/'figures'/f'{group}_{car}_{key}.png'
                plot_lines(out,series,'feature_distance_m',key,'Distance into feature [m]',label,f'{car}: {group.replace("_"," ")} variants')
                images.append(out.relative_to(folder).as_posix())
    cols={
      'flat':['variant','id','status','opening_flat_reached_upper_stop','flat_first_upper_distance_m','opening_flat_max_shift_mm','flat_tail_duration_s','flat_tail_shift_slope_mm_s','flat_tail_speed_min_m_s','review_required'],
      'mild_hill':['variant','id','status','secondary_hill_visited','secondary_hill_completed','secondary_hill_max_backshift_drawdown_mm','secondary_hill_min_active_fraction','secondary_hill_low_ratio_seat_fraction','partial_backshift_candidate','review_required'],
      'cyclic':['variant','id','status','cyclic_visited','cyclic_completed','cyclic_max_backshift_drawdown_mm','cyclic_opening_travel_mm','cyclic_net_shift_mm','cyclic_median_detrended_modulation_mm','cyclic_upper_stop_fraction','cyclic_max_encounter_hz','review_required']}
    parts=''.join(f'<h2>{g.replace("_"," ")}</h2>'+table([r for r in rows if r['group']==g],c) for g,c in cols.items())
    body=f'''<!doctype html><html><head><meta charset="utf-8"><title>Course-feature discovery</title><style>body{{font:14px system-ui;margin:2rem;max-width:1400px}}table{{display:block;overflow-x:auto;border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:.4rem}}img{{max-width:100%}}</style></head><body>
<h1>Course-feature discovery</h1><p>These are separate road variants, not one final combined race. No finishing-time ranking compares unlike roads. Each linked campaign contains full launch-to-finish trajectories, unchanged full throttle, identical boundaries across cars, and the same dynamic actuator models.</p>
<p><b>Interpretation:</b> a large shift range can be continuing upshift, not cyclic backshift. Compare opening travel and maximum drawdown with detrended per-cycle modulation and travel-stop occupancy. A small end-of-flat slope is finite-time evidence, not proof of an unreachable ratio. Missing sectors and numerical/domain failures are not successful examples.</p><ul>{''.join(links)}</ul>{parts}
<h2>Same-car local comparisons</h2>{''.join(f'<a href="{p}"><img loading="lazy" src="{p}"></a>' for p in images)}
<p><a href="feature_comparison.csv">Feature metrics</a> · <a href="cycle_comparison.csv">Per-cycle metrics</a> · <a href="plan.json">Input definitions and execution record</a></p></body></html>'''
    (folder/'index.html').write_text(body,encoding='utf-8')
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('plan_file',type=Path)
    a=p.parse_args();build_comparison(a.plan_file);print(a.plan_file.parent/'index.html')
if __name__=='__main__':main()
