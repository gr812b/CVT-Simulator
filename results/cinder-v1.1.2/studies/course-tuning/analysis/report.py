"""Offline HTML, tables and figures from saved results; never re-integrates."""
from __future__ import annotations
import argparse
import html
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from infrastructure.common import load_json,read_csv,write_csv,write_json,finite
from infrastructure.course import Course
from analysis.metrics import first_passage,passage_at


TUNE_COLOURS = {}

def configure_palette(manifest):
    import matplotlib.pyplot as plt
    order=manifest.get('colour_order',[t['id'] for t in manifest['competitors']])
    TUNE_COLOURS.clear()
    TUNE_COLOURS.update({car:plt.get_cmap('tab10')(i%10) for i,car in enumerate(order)})


def table(rows,columns):
    def fmt(v):
        if v is None: return '—'
        if isinstance(v,float): return f'{v:.5g}'
        return str(v)
    return '<table><thead><tr>'+''.join('<th>'+html.escape(c)+'</th>' for c in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(fmt(r.get(c)))+'</td>' for c in columns)+'</tr>' for r in rows)+'</tbody></table>'


def plot_lines(path,series,xkey,ykey,xlabel,ylabel,title,course=None,events=None,levels=()):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,5.5))
    has=False
    for label,rows in series:
        x=np.asarray([float(r[xkey]) if finite(r.get(xkey)) else np.nan for r in rows])
        y=np.asarray([float(r[ykey]) if finite(r.get(ykey)) else np.nan for r in rows])
        if np.isfinite(y).any():
            # Preserve chronological direction and leave reset/segment sides separate.
            xx=[]; yy=[]; previous=None
            for k,r in enumerate(rows):
                seg=r.get('segment_id')
                if previous is not None and seg is not None and seg!=previous:
                    xx.append(np.nan);yy.append(np.nan)
                xx.append(x[k]);yy.append(y[k]);previous=seg
            colour=TUNE_COLOURS.get(label)
            ax.plot(xx,yy,label=label,linewidth=1.2,**({'color':colour} if colour is not None else {}));has=True
    if course is not None:
        for s in course.sectors[1:]: ax.axvline(s.start_m,linewidth=.45,linestyle=':')
    if events:
        # Every event is retained in CSV; group spatially close labels so
        # launch chatter does not obscure later course transitions.
        lo,hi=ax.get_xlim(); gap=max(1e-8,0.024*(hi-lo));groups=[]
        for event in sorted(events,key=lambda e:float(e['distance_m'] if xkey=='distance_m' else e['time_s'])):
            x=float(event['distance_m'] if xkey=='distance_m' else event['time_s'])
            if not lo<=x<=hi: continue
            ax.axvline(x,linewidth=.35,linestyle=':')
            if groups and x-groups[-1][-1][0]<gap: groups[-1].append((x,event['event_id']))
            else: groups.append([(x,event['event_id'])])
        for n,group in enumerate(groups):
            label=group[0][1] if len(group)==1 else f"{group[0][1]}–{group[-1][1]}"
            ax.text(group[0][0],.98-(n%2)*.23,label,transform=ax.get_xaxis_transform(),rotation=90,va='top',fontsize=7)
    for y,label in levels: ax.axhline(y,linewidth=.8,linestyle='--',label=label)
    ax.set(xlabel=xlabel,ylabel=ylabel,title=title);ax.grid(True,alpha=.25)
    if has:ax.legend(fontsize=8,ncol=2,loc='best')
    fig.tight_layout();path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path,dpi=160);plt.close(fig)


def detail_figures(run_dir,car,rows,course):
    out=run_dir/'figures'/'cars'/car
    event_file=run_dir/'cases'/car/'events.json'
    events=load_json(event_file) if event_file.is_file() else []
    plot_lines(out/'motion.png',[(f'{car} vehicle',rows)],'distance_m','speed_m_s','Distance along road [m]','Vehicle speed [m/s]',f'{car}: complete accepted progress',course,events)
    plot_lines(out/'rpm.png',[(f'{car} primary',rows)],'distance_m','primary_rpm','Distance along road [m]','Primary speed [rpm]',f'{car}: engine operating trajectory',course)
    plot_lines(out/'shift.png',[(f'{car} shift',rows)],'distance_m','shift_mm','Distance along road [m]','Shift coordinate [mm]',f'{car}: shifting and stops',course,events)
    series=[]
    for key,label in [('primary_actuator_closing_N','Primary net actuator'),('secondary_actuator_closing_N','Secondary net actuator'),('secondary.helix_torsional_preload_N','Helix torsional spring'),('secondary.helix_reacted_belt_torque_force_N','Helix reacted belt torque'),('secondary.helix_shaft_acceleration_force_N','Helix shaft-acceleration term'),('secondary.helix_shift_acceleration_force_N','Helix shift-acceleration term'),('secondary.axial_spring_N','Secondary axial spring')]:
        series.append((label,[{**r,'value':r.get(key)} for r in rows]))
    plot_lines(out/'actuation.png',series,'distance_m','value','Distance along road [m]','Signed local closing force [N]',f'{car}: actuator contributions',course)
    series=[(side,[{**r,'value':r.get(side+'_static_utilization')} for r in rows]) for side in ('primary','secondary')]
    plot_lines(out/'traction.png',series,'distance_m','value','Distance along road [m]','|lambda| / mu_static (kinetic intervals included)',f'{car}: represented traction utilization',course,levels=[(1.,'Static capacity')])
    series=[('Primary → belt',[{**r,'value':r.get('primary_to_belt_power_W')} for r in rows]),('Belt → secondary',[{**r,'value':r.get('belt_to_secondary_power_W')} for r in rows]),('Engine boundary',[{**r,'value':r.get('primary_boundary_power_W')} for r in rows])]
    plot_lines(out/'powers.png',series,'distance_m','value','Distance along road [m]','Signed power [W]',f'{car}: forward/reverse transfer; no throttle schedule',course,levels=[(0.,'Zero power')])
    series=[('Geometric r_p/r_s',[{**r,'value':r.get('geometric_ratio_rp_over_rs')} for r in rows]),('Shaft omega_s/omega_p',[{**r,'value':r.get('shaft_speed_ratio_ws_over_wp')} for r in rows])]
    plot_lines(out/'ratios.png',series,'distance_m','value','Distance along road [m]','Ratio [dimensionless]',f'{car}: geometry versus shaft speeds during slip',course)
    series=[(side,[{**r,'value':r.get(side+'_min_dN_dtheta_N_per_rad')} for r in rows]) for side in ('primary','secondary')]
    plot_lines(out/'local_normal.png',series,'distance_m','value','Distance along road [m]','Minimum local wrap normal [N/rad]',f'{car}: full-wrap contact margin',course,levels=[(0.,'Local contact limit')])
    series=[(label,[{**r,'value':r.get(key)} for r in rows]) for key,label in [('low_ratio_seat_reaction_N','Low-ratio seat'),('upper_stop_reaction_N','Upper stop'),('lower_stop_reaction_N','Deadzone lower stop')]]
    plot_lines(out/'support_reaction.png',series,'distance_m','value','Distance along road [m]','Active support reaction [N]',f'{car}: structural constraints',course,events,levels=[(0.,'Zero reaction')])
    import matplotlib.pyplot as plt
    for key,title in [('contact_mode','Contact regimes'),('shift_constraint','Shift support regimes')]:
        names=list(dict.fromkeys(str(r.get(key)) for r in rows))
        fig,ax=plt.subplots(figsize=(10,3.8))
        ax.step([r['distance_m'] for r in rows],[names.index(str(r.get(key))) for r in rows],where='post')
        ax.set_yticks(range(len(names)),names);ax.set(xlabel='Distance along road [m]',title=f'{car}: {title}')
        ax.grid(True,alpha=.25);fig.tight_layout();fig.savefig(out/f'{key}.png',dpi=150);plt.close(fig)
    links=''.join(f'<a href="figures/cars/{car}/{p.name}"><img src="figures/cars/{car}/{p.name}"></a>' for p in sorted(out.glob('*.png')))
    return links


def build_report(run_dir:Path,focus:list[str]|None=None,plots=True,reference='R00'):
    run_dir=Path(run_dir).resolve();manifest=load_json(run_dir/'campaign.json');course=Course(manifest['course'])
    configure_palette(manifest)
    summaries=[];data={};sector_rows=[]
    for d in sorted((run_dir/'cases').glob('*')):
        if not (d/'summary.json').exists(): continue
        summary=load_json(d/'summary.json');summaries.append(summary)
        data[d.name]=read_csv(d/'diagnostics.csv') if (d/'diagnostics.csv').exists() else []
        if (d/'sector_metrics.csv').exists(): sector_rows+=read_csv(d/'sector_metrics.csv')
    summaries.sort(key=lambda r:(0 if r.get('status')=='finished' and not r.get('review_required') else 1, float(r['finish_time_s']) if finite(r.get('finish_time_s')) else float('inf'),-float(r.get('max_distance_m') or 0)))
    write_csv(run_dir/'leaderboard.csv',summaries)
    sec_lookup={(r['id'],r['sector']):r for r in sector_rows}
    for r in sector_rows:
        ref=sec_lookup.get((reference,r['sector']),{})
        a,b=r.get('sector_time_s'),ref.get('sector_time_s')
        r['sector_delta_vs_reference_s']=float(a)-float(b) if finite(a) and finite(b) else None
        r['reference']=reference
    write_csv(run_dir/'sector_comparison.csv',sector_rows)
    gap_rows=[];grid=np.arange(0.,course.finish_m+1e-9,float(manifest['diagnostics']['distance_grid_step_m']))
    ref_x,ref_t=first_passage(data.get(reference,[]))
    for car,rows in data.items():
        x,t=first_passage(rows)
        for station in grid:
            own=passage_at(x,t,float(station));base=passage_at(ref_x,ref_t,float(station))
            gap_rows.append({'id':car,'distance_m':float(station),'first_passage_s':own,'reference_first_passage_s':base,'time_gap_s':own-base if own is not None and base is not None else None})
    write_csv(run_dir/'time_gaps.csv',gap_rows)
    write_csv(run_dir/'course_profile.csv',course.profile_rows())
    from analysis.feature_metrics import analyze_campaign
    analyze_campaign(run_dir)
    images=[]
    if focus is None:
        focus=[t['id'] for t in manifest['competitors']]
    focus=[c for c in focus if data.get(c)]
    if plots:
        out=run_dir/'figures';out.mkdir(exist_ok=True)
        for key,ylabel in [('grade_deg','Grade [deg]'),('elevation_m','Height relative to start [m]')]:
            p=out/f'course_{key}.png';plot_lines(p,[('Common road',course.profile_rows())],'distance_m',key,'Distance along road [m]',ylabel,'Shared distance-based course',course);images.append(p.relative_to(run_dir).as_posix())
        sets=[('focus',focus)]+[(family,[r['id'] for r in manifest['competitors'] if r['family'] in (family,'reference') and data.get(r['id'])]) for family in dict.fromkeys(t['family'] for t in manifest['competitors'] if t['family']!='reference')]
        for name,ids in sets:
            if not ids: continue
            for key,label in [('speed_m_s','Vehicle speed [m/s]'),('primary_rpm','Primary speed [rpm]'),('shift_mm','Shift [mm]')]:
                p=out/f'{name}_{key}.png';plot_lines(p,[(c,data[c]) for c in ids],'distance_m',key,'Distance along road [m]',label,f'{name}: {label}',course)
                if name=='focus': images.append(p.relative_to(run_dir).as_posix())
            p=out/f'{name}_time_gap.png';plot_lines(p,[(c,[r for r in gap_rows if r['id']==c]) for c in ids],'distance_m','time_gap_s','Distance along road [m]',f'Time gap to {reference} [s]; negative = ahead',f'{name}: no extrapolation beyond attained distance',course)
            if name=='focus': images.append(p.relative_to(run_dir).as_posix())
        for car in focus: detail_figures(run_dir,car,data[car],course)
        from analysis.shift_curves import build_shift_curves
        build_shift_curves(run_dir,focus,data)
        images.append('figures/shift_curve_focus.png')
    columns=['id','family','status','review_required','finish_time_s','max_distance_m','hill_min_speed_m_s','primary_slip_work_J','secondary_slip_work_J','physical_transition_count','integration_wall_s']
    reasons=[{'id':r['id'],'status':r['status'],'reason':r.get('reason','')} for r in summaries if r.get('status')!='finished' or r.get('review_required')]
    detail=''
    for car in focus:
        d=run_dir/'figures'/'cars'/car
        links=''.join(f'<a href="{p.relative_to(run_dir).as_posix()}"><img loading="lazy" src="{p.relative_to(run_dir).as_posix()}"></a>' for p in sorted(d.glob('*.png')))
        detail+=f'<details><summary>{html.escape(car)} — mechanics and regimes</summary>{links}<p><a href="cases/{car}/events.csv">Exact event records</a> · <a href="cases/{car}/interesting_windows.csv">Suggested inspection windows</a> · <a href="cases/{car}/diagnostics.csv">All signals</a></p></details>'
    body=f'''<!doctype html><html><head><meta charset="utf-8"><title>Common-course CVT operation and tuning</title><style>body{{font:15px system-ui,sans-serif;margin:2rem;max-width:1400px}}table{{border-collapse:collapse;display:block;overflow-x:auto}}th,td{{border:1px solid #bbb;padding:.45rem;text-align:left}}img{{max-width:100%;margin:1rem 0}}summary{{font-weight:bold;cursor:pointer;padding:1rem}}code{{background:#eee}}p{{line-height:1.5}}</style></head><body>
<h1>Common-course CVT operation and tuning</h1><p><b>Selected-case numerical study; not experimental validation or an optimized tune.</b> Full throttle is unchanged. Every entrant uses the same road and boundary parameters, with dynamic fixed-pivot flyweights and a dynamic bilateral slotted helix.</p>
<p>Campaign: <code>{html.escape(run_dir.name)}</code>. Reference for gaps: <b>{html.escape(reference)}</b>. Course: {html.escape(course.summary_text())}.</p>
<p>Partial runs are censored. Numerical/model termination is not called failure to climb. Review flags require inspection before ranking mechanically credible results. Runtime is integration-only where labelled; setup and post-processing are separate. Mechanical energies below are approximate sampled diagnostics, not efficiency or repeated formal verification.</p>
<h2>Observed progress</h2>{table(summaries,columns)}<h2>Incomplete / review cases</h2>{table(reasons,['id','status','reason'])}
<h2>Course and selected competitors</h2>{''.join(f'<a href="{p}"><img src="{p}"></a>' for p in images)}
<h2>Sector times</h2>{table(sector_rows,['id','sector','completed','sector_time_s','sector_delta_vs_reference_s','sampled_min_speed_m_s'])}
<h2>Competitor intentions</h2>{table(manifest['competitors'],['id','label','family','intent','knobs'])}
<h2>Shift curves for every entrant</h2><p><a href="shift_curves.html">Open all-car and phase-coloured individual shift curves</a></p><p><a href="feature_metrics.csv">Feature-specific shift metrics</a> · <a href="cyclic_cycle_metrics.csv">Per-cycle modulation</a></p><h2>Detailed views</h2>{detail}<p><a href="campaign.json">Configuration and hashes</a> · <a href="time_gaps.csv">Distance time gaps</a> · <a href="leaderboard.csv">Complete metrics</a></p></body></html>'''
    (run_dir/'index.html').write_text(body,encoding='utf-8')
    return summaries


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run_dir',type=Path);p.add_argument('--focus',nargs='+');p.add_argument('--reference',default='R00');p.add_argument('--no-plots',action='store_true')
    a=p.parse_args();build_report(a.run_dir,a.focus,not a.no_plots,a.reference)
    print(a.run_dir/'index.html')
if __name__=='__main__': main()
