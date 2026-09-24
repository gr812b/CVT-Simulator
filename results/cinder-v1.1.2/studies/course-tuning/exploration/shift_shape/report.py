"""Familiar course gallery plus launch-only offset/slope/shape comparisons."""
from __future__ import annotations
from pathlib import Path
import html
import numpy as np
from infrastructure.common import load_json,read_csv,write_csv,write_json,finite,utc_now
from analysis.report import build_report,table
from .metrics import launch_parts,describe,compare_to_reference,secants

CAR_PALETTE={}


def lines(path,series,xkey,ykey,xlabel,ylabel,title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,6))
    for label,rows in series:
        if rows and 'path_id' in rows[0]:
            separated=[];previous=None
            for r in rows:
                if previous is not None and r['path_id']!=previous:separated.append({xkey:np.nan,ykey:np.nan})
                separated.append(r);previous=r['path_id']
            rows=separated
        x=np.asarray([r.get(xkey,np.nan) for r in rows],float);y=np.asarray([r.get(ykey,np.nan) for r in rows],float)
        if len(x) and np.isfinite(y).any():ax.plot(x,y,label=label,lw=1.5,**({'color':CAR_PALETTE[label]} if label in CAR_PALETTE else {}))
    ax.set(xlabel=xlabel,ylabel=ylabel,title=title);ax.grid(True,alpha=.25)
    if ax.lines:ax.legend(fontsize=8,ncol=2)
    fig.tight_layout();path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path,dpi=160);plt.close(fig)


def _flatten(parts):
    result=[]
    for p in parts:
        result+=p+[{'secondary_rpm':np.nan,'primary_rpm':np.nan}]
    return result


def build_shape_report(folder:Path,plots:bool=True):
    folder=Path(folder).resolve();campaign=load_json(folder/'campaign.json')
    if 'shape_metric_revision' not in campaign:raise ValueError('This is not a shift-shape campaign; use the original report builder for other runs.')
    import matplotlib.pyplot as plt
    CAR_PALETTE.clear();CAR_PALETTE.update({t['id']:plt.get_cmap('turbo')(i/max(1,len(campaign['competitors'])-1)) for i,t in enumerate(campaign['competitors'])})
    data={p.name:read_csv(p/'diagnostics.csv') for p in (folder/'cases').iterdir() if (p/'diagnostics.csv').is_file()}
    order=[t['id'] for t in campaign['competitors'] if t['id'] in data]
    # Retain the familiar per-car galleries and phase-coloured complete-road curves.
    build_report(folder,focus=order,plots=plots)
    launch_end=float(campaign['course']['lengths_m']['launch_flat'])
    parts={i:launch_parts(data[i],launch_end) for i in order}
    stats=[];comparisons={};slopes={};summary_lookup={}
    for i in order:
        s=load_json(folder/'cases'/i/'summary.json');summary_lookup[i]=s
        diff,points=compare_to_reference(parts[i],parts.get('R00',[]));comparisons[i]=points
        slopes[i]=secants(parts[i]);row={'id':i,'run_status':s['status'],'review_required':s.get('review_required'),**describe(parts[i]),**diff}
        events=load_json(folder/'cases'/i/'events.json')
        for label,eventname in [('engagement','engagement_reached'),('upper_stop','upper_stop_reached')]:
            ev=next((e for e in events if any(eventname in n for n in e.get('event_names',[])) and float(e['distance_m'])<launch_end),None)
            row[label+'_time_s']=ev['time_s'] if ev else None
            row[label+'_distance_m']=ev['distance_m'] if ev else None
        stats.append(row)
    write_csv(folder/'shift_shape_metrics.csv',stats)
    write_csv(folder/'shift_shape_aligned_curves.csv',[{'id':i,**r} for i,rows in comparisons.items() for r in rows])
    write_csv(folder/'shift_shape_local_secants.csv',[{'id':i,**r} for i,rows in slopes.items() for r in rows])
    definitions={'generated_utc':utc_now(),'x_axis':'secondary_rpm','y_axis':'primary_rpm','region':f'First {launch_end:g} m only',
        'eligibility':'Engaged, free shift, stick–stick, positive shift rate, 0.15 <= active shift fraction <= 0.85; increasing secondary RPM.',
        'secant_nodes':[.2,.5,.8],'local_secant_width_secondary_rpm':200.,
        'comparison':'Longest contiguous shared secondary-RPM support on a 401-point grid; no extrapolation or bridging excluded modes. Pair-specific support is recorded.',
        'offset':'Mean candidate minus reference primary RPM on the common grid.',
        'shape':'RMS/peak-to-peak residual after subtracting that single constant RPM offset.',
        'interpretation':'Finite-transient shape descriptors, not a steady shift law, local Jacobian, damping measure or hardware suitability score.',
        'cautions':['Do not infer slope from a support-held diagonal or clutch-slip loop.','Low-overlap/partial cases remain explicit.','Spring matching applies at ONE geometry; road/state histories may subsequently differ.','A smaller shape score is not necessarily a better tune.']}
    write_json(folder/'shift_shape_metric_definitions.json',definitions)
    profiles={i:read_csv(folder/'cases'/i/'ramp_profile.csv') for i in order if (folder/'cases'/i/'ramp_profile.csv').exists()}
    maps={i:read_csv(folder/'cases'/i/'shape_mechanism_map.csv') for i in order if (folder/'cases'/i/'shape_mechanism_map.csv').exists()}
    groups=[('all',order)]+[(fam,[t['id'] for t in campaign['competitors'] if t['id'] in order and (t['family']==fam or t['id']=='R00')])
        for fam in dict.fromkeys(t['family'] for t in campaign['competitors'] if t['family']!='reference')]
    images=[]
    if plots:
        for name,ids in groups:
            if not ids:continue
            specs=[('launch_curve',[(i,_flatten(parts[i])) for i in ids],'secondary_rpm','primary_rpm','Secondary speed [rpm]','Primary speed [rpm]','Opening-flat free-shift curve'),
                ('offset_removed',[(i,comparisons[i]) for i in ids if i!='R00'],'secondary_rpm','offset_removed_difference_rpm','Secondary speed [rpm]','Primary difference after removing constant offset [rpm]','Shape difference from R00 (pairwise overlap)'),
                ('slope',[(i,slopes[i]) for i in ids],'secondary_rpm','slope_rpm_per_1000_secondary_rpm','Secondary speed [rpm]','200-rpm secant slope [primary rpm / 1000 secondary rpm]','Slope within the eligible free-upshift path')]
            for stem,series,x,y,xl,yl,title in specs:
                path=folder/'figures/shift_shape'/f'{name}_{stem}.png';lines(path,series,x,y,xl,yl,name.replace('_',' ')+' — '+title)
                images.append((name,stem,path.relative_to(folder).as_posix()))
        map_specs=[('primary_rate','primary_spring_opening_N','Primary spring opposition [N]'),('secondary_rate','secondary_spring_closing_N','Secondary spring closing force [N]'),('torsional_rate','torsional_spring_torque_Nm','Torsional spring torque [N m]'),('ramp_shape','centrifugal_force_3000rpm_N','Centrifugal closing contribution at 3000 rpm [N]'),('ramp_shape','flyweight_reflected_shift_mass_kg','Flyweight reflected shift mass [kg]'),('ramp_shape','roller_contact_coordinate_mm','Roller contact coordinate on the ramp [mm]')]
        for family,y,yl in map_specs:
            ids=next(ids for fam,ids in groups if fam==family)
            p=folder/'figures/shift_shape'/f'map_{y}.png';lines(p,[(i,maps[i]) for i in ids if i in maps],
                'active_shift_fraction',y,'Active shift fraction',yl,'Mechanism map — '+family.replace('_',' '))
            images.append(('mechanisms',y,p.relative_to(folder).as_posix()))
        ramp_ids=next(ids for fam,ids in groups if fam=='ramp_shape')
        for y,yl in [('radial_offset_mm','Ramp radial offset [mm]'),('tangent_angle_deg','Ramp tangent angle [deg]')]:
            p=folder/'figures/shift_shape'/f'ramp_{y}.png';lines(p,[(i,profiles[i]) for i in ramp_ids if i in profiles],
                'ramp_coordinate_mm',y,'Physical ramp profile coordinate [mm]',yl,'Unchanged nose, smooth transition, reshaped tail')
            images.append(('mechanisms',y,p.relative_to(folder).as_posix()))
        for i in order:
            # A two-car clean launch curve complements the existing phase-coloured full-course plot.
            p=folder/'figures/cars'/i/'shift_shape_launch.png'
            lines(p,[(j,_flatten(parts[j])) for j in dict.fromkeys(['R00',i]) if j in parts],
                'secondary_rpm','primary_rpm','Secondary speed [rpm]','Primary speed [rpm]',i+' — free upshift versus R00')
    def img(p):return f'<a href="{p}"><img loading="lazy" src="{p}"></a>'
    body=f'''<!doctype html><html><head><meta charset="utf-8"><title>Shift-curve shape exploration</title><style>body{{font:15px system-ui;max-width:1450px;margin:2rem}}img{{max-width:100%}}table{{border-collapse:collapse;display:block;overflow:auto}}th,td{{border:1px solid #bbb;padding:.5rem}}summary{{padding:1rem;font-weight:bold;cursor:pointer}}p{{line-height:1.5}}</style></head><body>
<h1>Spring-rate and ramp-shape exploration</h1><p><a href="index.html">Full course, events and per-car mechanics</a> · <a href="shift_curves.html">Phase-coloured complete-course shift curves</a></p>
<p>Primary RPM is vertical, secondary RPM horizontal. The shape analysis uses only the opening-flat, freely upshifting, sticking interval (15–85% active travel). Stop-held ratios, clutch slip, hill backshift and downhill overspeed are not fitted into one slope.</p>
<p>Rate candidates preserve the spring's force or torque at the engagement geometry by an explicit preload adjustment. Ramp candidates keep the initial physical nose and use the released C3 segment constructors. No engine map, vehicle boundary, belt property or dynamic mechanism is replaced. These are engineering hypotheses, not certified available springs or manufacturable ramps.</p>
<h2>Outcome and shape descriptors</h2>{table(stats,['id','run_status','review_required','shape_status','mean_primary_offset_rpm','offset_removed_shape_rms_rpm','delta_fitted_slope_rpm_per_1000_secondary_rpm','overall_slope_rpm_per_1000_secondary_rpm','common_secondary_rpm_span'])}
<p>Shape RMS removes a single constant vertical offset on each car's recorded overlap with R00. Support can differ between pairs; a large score is not a performance score. Partial and narrow-overlap cases are not silently extrapolated.</p>
<p><a href="shift_shape_metrics.csv">All metrics, early/late slopes and launch events</a> · <a href="shift_shape_metric_definitions.json">Exact definitions</a> · <a href="shift_shape_aligned_curves.csv">Aligned data</a> · <a href="competitors_resolved.csv">Rates, adjusted preloads and exact changes</a></p>'''
    for name in dict.fromkeys(g for g,_,_ in images):
        body+=f'<details {"open" if name=="all" else ""}><summary>{html.escape(name.replace("_"," "))}</summary>'+''.join(img(p) for group,_,p in images if group==name)+'</details>'
    body+='<h2>Each car</h2>'
    for i in order:
        body+=f'<details><summary>{html.escape(i)}</summary>'
        if plots:body+=img(f'figures/cars/{i}/shift_shape_launch.png')+img(f'figures/cars/{i}/shift_curve.png')
        for filename,label in [('definition_checks.json','Geometry checks'),('shape_mechanism_map.csv','Exact sampled mechanism map'),('ramp_profile.csv','Ramp profile'),('events.csv','Events'),('diagnostics.csv','All signals')]:
            if (folder/'cases'/i/filename).exists():body+=f'<p><a href="cases/{i}/{filename}">{label}</a></p>'
        body+='</details>'
    body+='</body></html>'
    (folder/'shift_shape.html').write_text(body,encoding='utf-8')
    main=folder/'index.html'
    if main.exists():
        text=main.read_text(encoding='utf-8');text=text.replace('<h1>Common-course tuning exploration</h1>','<h1>Spring-rate and ramp-shape course exploration</h1><p><strong><a href="shift_shape.html">Start here: launch-curve slope, shape, and mechanism comparisons</a></strong></p>')
        main.write_text(text,encoding='utf-8')
    all_summaries=[load_json(p/'summary.json') for p in (folder/'cases').iterdir() if (p/'summary.json').exists()]
    invocation=load_json(folder/'invocation.json') if (folder/'invocation.json').exists() else {}
    requested=invocation.get('selected_ids',[t['id'] for t in campaign['competitors']])
    write_json(folder/'shift_shape_completion.json',{'utc':utc_now(),'present_ids':order,'requested_this_invocation':requested,
        'missing_requested_ids':[i for i in requested if i not in data],
        'other_not_run_ids':[t['id'] for t in campaign['competitors'] if t['id'] not in data and t['id'] not in requested],
        'error_or_review':[s['id'] for s in all_summaries if s.get('review_required') or s.get('status') in ('setup_error','integration_error','worker_error','wall_timeout')]})
    return stats
