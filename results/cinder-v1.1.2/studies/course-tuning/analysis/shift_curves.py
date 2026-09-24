"""Primary RPM versus secondary RPM from saved traces; never sorts by speed.

Individual plots use road-sector colours. Fleet plots use entrant colours only.
Finite-speed reset jumps are not drawn as continuous mechanical motion.
"""
from __future__ import annotations
import argparse
import html
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from infrastructure.common import load_json,read_csv,write_json,utc_now,finite,source_fingerprint
from infrastructure.course import Course


def chronological_edges(rows: list[dict], course: Course):
    """Return short curve edges and their exact road-sector name.

    A sampled edge crossing a road boundary is split by linear interpolation
    along that SAME time-adjacent edge. No connection crosses a solver segment
    boundary, a reset, or a missing speed. Repeated speeds remain in time order.
    """
    edges=[]; names=[]
    ordered=sorted(rows,key=lambda r:(float(r['time_s']),int(r.get('segment_id',0))))
    for left,right in zip(ordered,ordered[1:]):
        if left.get('segment_id')!=right.get('segment_id'): continue
        if float(right['time_s'])<=float(left['time_s']): continue
        if not all(finite(r.get(k)) for r in (left,right) for k in ('secondary_rpm','primary_rpm','distance_m')): continue
        a=np.array([float(left['secondary_rpm']),float(left['primary_rpm'])])
        b=np.array([float(right['secondary_rpm']),float(right['primary_rpm'])])
        xa=float(left['distance_m']);xb=float(right['distance_m'])
        cuts=[0.,1.]
        if abs(xb-xa)>1e-12:
            cuts.extend((s.start_m-xa)/(xb-xa) for s in course.sectors[1:] if min(xa,xb)<s.start_m<max(xa,xb))
        cuts=sorted(set(cuts))
        for lo,hi in zip(cuts,cuts[1:]):
            edges.append([a+(b-a)*lo,a+(b-a)*hi])
            names.append(course.sector(xa+(xb-xa)*.5*(lo+hi)).name)
    return np.asarray(edges,dtype=float).reshape(-1,2,2),names


def _plot(path: Path, series: list[tuple[str,list[dict]]], course: Course, individual=False, title='', palette=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    fig,ax=plt.subplots(figsize=(10.5,7.0 if individual else 7.8))
    sector_names=[s.name for s in course.sectors]
    sector_colours={name:plt.get_cmap('tab20')(i%20) for i,name in enumerate(sector_names)}
    handles=[]; reached=set(); any_data=False
    for index,(car,rows) in enumerate(series):
        edges,names=chronological_edges(rows,course)
        if not len(edges): continue
        any_data=True
        if individual:
            colours=[sector_colours[n] for n in names];reached.update(names)
        else:
            colour=(palette or {}).get(car,plt.get_cmap('tab20')(index%20))
            colours=colour;handles.append(Line2D([0],[0],color=colour,lw=1.3,label=car))
        ax.add_collection(LineCollection(edges,colors=colours,linewidths=1.45 if individual else 1.05,alpha=.9))
        ax.update_datalim(edges.reshape(-1,2))
        if individual:
            valid=[r for r in sorted(rows,key=lambda r:float(r['time_s'])) if finite(r.get('primary_rpm')) and finite(r.get('secondary_rpm'))]
            if valid:
                for r,mark,label in [(valid[0],'o','Start'),(valid[-1],'X','Last accepted sample')]:
                    ax.scatter([r['secondary_rpm']],[r['primary_rpm']],marker=mark,s=38,color='black',zorder=5,label=label)
            # Few time-direction arrows within continuous pieces, not across resets.
            for n in np.linspace(0,len(edges)-1,min(7,len(edges)),dtype=int):
                a,b=edges[n]
                if np.linalg.norm(b-a)>2.:
                    ax.annotate('',xy=b,xytext=a,arrowprops={'arrowstyle':'->','lw':1.,'color':sector_colours[names[n]]})
    if individual:
        handles=[Line2D([0],[0],color=sector_colours[n],lw=2,label=n.replace('_',' ')) for n in sector_names if n in reached]
        handles.extend([Line2D([0],[0],color='black',marker='o',ls='',label='Start'),Line2D([0],[0],color='black',marker='X',ls='',label='Last accepted sample')])
    ax.autoscale_view();ax.margins(.04)
    ax.set(xlabel='Secondary speed [rpm]',ylabel='Primary speed [rpm]',title=title)
    ax.grid(True,alpha=.25)
    if handles:ax.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,-.13),fontsize=8,ncol=3 if individual else min(8,max(2,len(handles)//5)))
    if not any_data:ax.text(.5,.5,'No continuous accepted speed samples',ha='center',transform=ax.transAxes)
    fig.tight_layout();path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path,dpi=150);plt.close(fig)


def build_shift_curves(run_dir: Path, focus=None, data=None):
    """Add all-car curves and an offline gallery to an old or new campaign."""
    run_dir=Path(run_dir).resolve();manifest=load_json(run_dir/'campaign.json');course=Course(manifest['course'])
    if data is None:
        data={p.name:read_csv(p/'diagnostics.csv') for p in sorted((run_dir/'cases').iterdir()) if (p/'diagnostics.csv').is_file()}
    ids=[t['id'] for t in manifest['competitors'] if data.get(t['id'])]
    if focus is None:focus=[i for i in ('R00','W85','P300','RC10','R26B7','RC40L','H28','U55','D01','D02','D02_M','D02_P') if i in ids]
    focus=[i for i in focus if i in ids]
    import matplotlib.pyplot as plt
    # Fleet colours are independent of sector colours and stable across focus/family views.
    order=manifest.get('colour_order',[t['id'] for t in manifest['competitors']])
    colours={car:plt.get_cmap('tab10')(i%10) for i,car in enumerate(order)}
    out=run_dir/'figures';out.mkdir(exist_ok=True)
    if ids:_plot(out/'shift_curve_all.png',[(i,data[i]) for i in ids],course,title='All entrants: primary versus secondary speed',palette=colours)
    if focus:_plot(out/'shift_curve_focus.png',[(i,data[i]) for i in focus],course,title='Selected entrants: primary versus secondary speed',palette=colours)
    for family in dict.fromkeys(t['family'] for t in manifest['competitors']):
        group=[t['id'] for t in manifest['competitors'] if t['family'] in ('reference',family) and t['id'] in ids]
        if family!='reference' and len(group)>1:
            _plot(out/f'shift_curve_{family}.png',[(i,data[i]) for i in group],course,title=f'{family.replace("_"," ")}: primary versus secondary speed',palette=colours)
    for i in ids:
        _plot(out/'cars'/i/'shift_curve.png',[(i,data[i])],course,True,f'{i}: speed trajectory by road sector')
    def image(path):
        return f'<a href="{path}"><img loading="lazy" src="{path}"></a>'
    gallery=''.join(f'<details><summary>{html.escape(i)}</summary>{image(f"figures/cars/{i}/shift_curve.png")}</details>' for i in ids)
    body=f'''<!doctype html><html><head><meta charset="utf-8"><title>CVT shift curves</title><style>body{{font:15px system-ui;margin:2rem;max-width:1200px}}img{{max-width:100%}}summary{{padding:1rem;cursor:pointer;font-weight:bold}}</style></head><body>
<h1>Primary RPM versus secondary RPM</h1><p><a href="index.html">Main report</a> · {html.escape(run_dir.name)}</p>
<p>The horizontal axis is secondary speed; the vertical axis is primary speed. Traces follow chronological order, so repeated speeds and loops are retained. Individual-car colours denote road sectors; fleet colours denote cars only. No continuous line is drawn across a finite-speed reset or a missing segment. These are sampled transient trajectories, not fitted or steady-state shift laws.</p>
{image('figures/shift_curve_focus.png') if focus else ''}{image('figures/shift_curve_all.png') if ids else ''}
<h2>Every simulated entrant</h2>{gallery}</body></html>'''
    (run_dir/'shift_curves.html').write_text(body,encoding='utf-8')
    write_json(run_dir/'shift_curve_generation.json',{'generated_utc':utc_now(),'campaign_fingerprint':manifest['fingerprint'],'source':source_fingerprint(),'cars':ids,'focus':focus,'x':'secondary_rpm','y':'primary_rpm','new_integration':False})
    return run_dir/'shift_curves.html'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run_dir',type=Path);p.add_argument('--focus',nargs='+')
    a=p.parse_args();print(build_shift_curves(a.run_dir,a.focus))
if __name__=='__main__':main()
