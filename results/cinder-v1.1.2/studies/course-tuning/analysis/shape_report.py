"""Selected opening-flat shift-curve shape and mechanism comparisons."""
from __future__ import annotations
from pathlib import Path
import html
import numpy as np
from infrastructure.common import load_json,read_csv,write_csv,write_json,utc_now
from analysis.report import table,configure_palette,TUNE_COLOURS
from analysis.shape_metrics import launch_parts,describe,compare_to_reference,secants


def _lines(path,series,xkey,ykey,xlabel,ylabel,title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,6))
    for label,rows in series:
        separated=[];previous=None
        for r in rows:
            if previous is not None and r.get('path_id') is not None and r.get('path_id')!=previous:
                separated.append({xkey:np.nan,ykey:np.nan})
            separated.append(r);previous=r.get('path_id',previous)
        x=np.asarray([r.get(xkey,np.nan) for r in separated],float)
        y=np.asarray([r.get(ykey,np.nan) for r in separated],float)
        if len(x) and np.isfinite(y).any():
            colour=TUNE_COLOURS.get(label)
            ax.plot(x,y,label=label,lw=1.5,**({'color':colour} if colour is not None else {}))
    ax.set(xlabel=xlabel,ylabel=ylabel,title=title);ax.grid(True,alpha=.25)
    if ax.lines:ax.legend(fontsize=8,ncol=2)
    fig.tight_layout();path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path,dpi=160);plt.close(fig)


def _flatten(parts):
    out=[]
    for p in parts:
        out.extend([{**r,'path_id':len(out)} for r in p]);out.append({'secondary_rpm':np.nan,'primary_rpm':np.nan})
    return out


def build_shape_report(folder:Path,plots:bool=True) -> list[dict]:
    folder=Path(folder).resolve();campaign=load_json(folder/'campaign.json');configure_palette(campaign)
    data={p.name:read_csv(p/'diagnostics.csv') for p in (folder/'cases').iterdir() if (p/'diagnostics.csv').is_file()}
    order=[t['id'] for t in campaign['competitors'] if t['id'] in data]
    launch_end=float(campaign['course']['lengths_m']['launch_flat'])
    parts={i:launch_parts(data[i],launch_end) for i in order}
    stats=[];comparisons={};slopes={}
    for i in order:
        s=load_json(folder/'cases'/i/'summary.json')
        diff,points=compare_to_reference(parts[i],parts.get('R00',[]));comparisons[i]=points
        slopes[i]=secants(parts[i]);row={'id':i,'run_status':s['status'],'review_required':s.get('review_required'),**describe(parts[i]),**diff}
        events=load_json(folder/'cases'/i/'events.json')
        for label,eventname in [('engagement','engagement_reached'),('upper_stop','upper_stop_reached')]:
            ev=next((e for e in events if any(eventname in n for n in e.get('event_names',[])) and float(e['distance_m'])<launch_end),None)
            row[label+'_time_s']=ev['time_s'] if ev else None;row[label+'_distance_m']=ev['distance_m'] if ev else None
        stats.append(row)
    write_csv(folder/'shift_shape_metrics.csv',stats)
    write_csv(folder/'shift_shape_aligned_curves.csv',[{'id':i,**r} for i,rows in comparisons.items() for r in rows])
    write_csv(folder/'shift_shape_local_secants.csv',[{'id':i,**r} for i,rows in slopes.items() for r in rows])
    write_json(folder/'shift_shape_metric_definitions.json',{
        'generated_utc':utc_now(),'x_axis':'secondary_rpm','y_axis':'primary_rpm','region':f'First {launch_end:g} m only',
        'eligibility':'Engaged, free shift, stick-stick, positive shift rate, 0.15 <= active shift fraction <= 0.85; increasing secondary RPM.',
        'secant_nodes':[.2,.5,.8],'local_secant_width_secondary_rpm':200.,
        'comparison':'Longest contiguous shared secondary-RPM support on a 401-point grid; no extrapolation or bridging excluded modes.',
        'offset':'Mean candidate minus reference primary RPM on the common grid.',
        'shape':'RMS/peak-to-peak residual after subtracting that single constant RPM offset.',
        'interpretation':'Finite-transient shape descriptors, not a steady shift law, local Jacobian, damping measure or hardware suitability score.',
        'cautions':['Do not infer slope from a support-held diagonal or clutch-slip loop.','Spring matching applies at one declared geometry.','A visually distinctive curve is not automatically a better course tune.']})
    profiles={i:read_csv(folder/'cases'/i/'ramp_profile.csv') for i in order if (folder/'cases'/i/'ramp_profile.csv').exists()}
    maps={i:read_csv(folder/'cases'/i/'shape_mechanism_map.csv') for i in order if (folder/'cases'/i/'shape_mechanism_map.csv').exists()}
    selected=[i for i in ('R00','W85','P300','RC10','R26B7','RC40L') if i in order]
    groups=[('selected',selected),('mass',[i for i in ('R00','W85') if i in order]),
            ('primary_rate',[i for i in ('R00','P300') if i in order]),
            ('ramp_shape',[i for i in ('R00','RC10','R26B7','RC40L') if i in order])]
    images=[]
    if plots:
        for name,ids in groups:
            if len(ids)<2:continue
            for stem,series,x,y,xl,yl,title in [
                ('launch_curve',[(i,_flatten(parts[i])) for i in ids],'secondary_rpm','primary_rpm','Secondary speed [rpm]','Primary speed [rpm]','Opening-flat free-shift trajectory'),
                ('offset_removed',[(i,comparisons[i]) for i in ids if i!='R00'],'secondary_rpm','offset_removed_difference_rpm','Secondary speed [rpm]','Primary difference after constant offset removal [rpm]','Shape difference from R00'),
                ('slope',[(i,slopes[i]) for i in ids],'secondary_rpm','slope_rpm_per_1000_secondary_rpm','Secondary speed [rpm]','200-rpm secant slope [primary rpm / 1000 secondary rpm]','Local slope along eligible upshift')]:
                p=folder/'figures/shift_shape'/f'{name}_{stem}.png';_lines(p,series,x,y,xl,yl,f'{name.replace("_"," ")} — {title}');images.append((name,p.relative_to(folder).as_posix()))
        for ids,y,yl,stem in [
            (['R00','P300'],'primary_spring_opening_N','Primary spring opposition [N]','primary_spring'),
            (['R00','RC10','R26B7','RC40L'],'centrifugal_force_3000rpm_N','Centrifugal closing contribution at 3000 rpm [N]','ramp_force'),
            (['R00','RC10','R26B7','RC40L'],'flyweight_reflected_shift_mass_kg','Flyweight reflected shift mass [kg]','ramp_inertia'),
            (['R00','RC10','R26B7','RC40L'],'roller_contact_coordinate_mm','Roller contact coordinate on ramp [mm]','ramp_contact')]:
            ids=[i for i in ids if i in maps]
            if len(ids)<2:continue
            p=folder/'figures/shift_shape'/f'{stem}.png';_lines(p,[(i,maps[i]) for i in ids],'active_shift_fraction',y,'Active shift fraction',yl,yl);images.append(('mechanisms',p.relative_to(folder).as_posix()))
        ramp_ids=[i for i in ('R00','RC10','R26B7','RC40L') if i in profiles]
        for y,yl,stem in [('radial_offset_mm','Ramp radial offset [mm]','ramp_radial'),('tangent_angle_deg','Ramp tangent angle [deg]','ramp_tangent')]:
            p=folder/'figures/shift_shape'/f'{stem}.png';_lines(p,[(i,profiles[i]) for i in ramp_ids],'ramp_coordinate_mm',y,'Physical ramp profile coordinate [mm]',yl,'Selected physical ramp profiles');images.append(('mechanisms',p.relative_to(folder).as_posix()))
        for i in order:
            p=folder/'figures/cars'/i/'shift_shape_launch.png';_lines(p,[(j,_flatten(parts[j])) for j in dict.fromkeys(['R00',i]) if j in parts],'secondary_rpm','primary_rpm','Secondary speed [rpm]','Primary speed [rpm]',i+' — eligible opening upshift versus R00')
    def img(p):return f'<a href="{p}"><img loading="lazy" src="{p}"></a>'
    body=f'''<!doctype html><html><head><meta charset="utf-8"><title>Selected shift-curve shape comparisons</title><style>body{{font:15px system-ui;max-width:1450px;margin:2rem}}img{{max-width:100%}}table{{border-collapse:collapse;display:block;overflow:auto}}th,td{{border:1px solid #bbb;padding:.5rem}}summary{{padding:1rem;font-weight:bold;cursor:pointer}}p{{line-height:1.5}}</style></head><body>
<h1>Selected shift-curve shape comparisons</h1><p><a href="index.html">Full-course report</a> · <a href="shift_curves.html">Phase-coloured complete-course shift curves</a></p>
<p>Primary RPM is vertical and secondary RPM horizontal. Shape metrics use only the opening-flat, freely upshifting, stick-stick interval from 15–85% active travel. Stop-held ratios, clutch slip, hill backshift and downhill behavior are excluded from these slope descriptors.</p>
<p>P300 changes primary spring stiffness while matching spring force at the low-ratio engagement geometry. RC10, R26B7 and RC40L change the physical ramp profile while retaining the dynamic flyweight mechanism. No RPM curve is prescribed.</p>
<h2>Descriptors</h2>{table(stats,['id','run_status','review_required','shape_status','primary_rpm_at_f20','primary_rpm_at_f80','overall_slope_rpm_per_1000_secondary_rpm','mean_primary_offset_rpm','offset_removed_shape_rms_rpm'])}
<p><a href="shift_shape_metrics.csv">All metrics</a> · <a href="shift_shape_metric_definitions.json">Definitions</a> · <a href="shift_shape_aligned_curves.csv">Aligned curves</a> · <a href="competitors_resolved.csv">Resolved hardware values</a></p>'''
    for name in ('selected','mass','primary_rate','ramp_shape','mechanisms'):
        subset=[p for group,p in images if group==name]
        if subset: body+=f'<details {"open" if name=="selected" else ""}><summary>{html.escape(name.replace("_"," "))}</summary>'+''.join(img(p) for p in subset)+'</details>'
    body+='<h2>Per-car launch comparison</h2>'
    for i in order:
        body+=f'<details><summary>{html.escape(i)}</summary>'
        if plots:body+=img(f'figures/cars/{i}/shift_shape_launch.png')+img(f'figures/cars/{i}/shift_curve.png')
        for filename,label in [('definition_checks.json','Geometry checks'),('shape_mechanism_map.csv','Mechanism map'),('ramp_profile.csv','Ramp profile'),('diagnostics.csv','All signals')]:
            if (folder/'cases'/i/filename).exists():body+=f'<p><a href="cases/{i}/{filename}">{label}</a></p>'
        body+='</details>'
    body+='</body></html>'
    (folder/'shift_shape.html').write_text(body,encoding='utf-8')
    write_json(folder/'shift_shape_completion.json',{'generated_utc':utc_now(),'present_ids':order,'missing_ids':[t['id'] for t in campaign['competitors'] if t['id'] not in data]})
    return stats
