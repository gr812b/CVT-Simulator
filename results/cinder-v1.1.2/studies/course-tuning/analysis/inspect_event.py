"""Plot a local time window from saved diagnostics, without another integration."""
from __future__ import annotations
import argparse
import html
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from infrastructure.common import load_json,read_csv,write_csv,finite
from analysis.report import plot_lines,table


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run_dir',type=Path);p.add_argument('--car',required=True)
    choice=p.add_mutually_exclusive_group(required=True)
    choice.add_argument('--event',help='Exact event ID, such as E0017')
    choice.add_argument('--distance',type=float,help='Center on the first saved state nearest this distance')
    p.add_argument('--window',type=float,default=.3,help='Seconds on either side')
    a=p.parse_args();root=a.run_dir.resolve();case=root/'cases'/a.car
    if not case.is_dir() or case.parent.resolve()!=(root/'cases').resolve():raise ValueError('Unknown car')
    rows=read_csv(case/'diagnostics.csv');events=load_json(case/'events.json')
    if not rows:raise ValueError('This run has no completed sampled trajectory')
    if a.event:
        selected=next((e for e in events if e['event_id']==a.event),None)
        if selected is None:raise ValueError('Unknown event ID; see cases/<ID>/events.csv')
        t=float(selected['time_s']);label=a.event
    else:
        if a.distance<min(float(r['distance_m']) for r in rows) or a.distance>max(float(r['distance_m']) for r in rows):raise ValueError('Requested distance was not attained')
        selected=None;anchor=min(rows,key=lambda r:(abs(float(r['distance_m'])-a.distance),float(r['time_s'])))
        t=float(anchor['time_s']);label=f'x{a.distance:g}'
    if a.window<=0:raise ValueError('Window must be positive')
    near=[{**r,'relative_time_ms':1000*(float(r['time_s'])-t)} for r in rows if abs(float(r['time_s'])-t)<=a.window]
    out=root/'figures'/'cars'/a.car/label;out.mkdir(parents=True,exist_ok=True)
    nearby_events=[e for e in events if abs(float(e['time_s'])-t)<=a.window]
    markers=[{**e,'time_s':1000*(float(e['time_s'])-t)} for e in nearby_events]
    images=[]
    specs=[('motion',[('speed_m_s','Vehicle speed')],'Vehicle speed [m/s]'),
           ('rpm',[('primary_rpm','Primary'),('secondary_rpm','Secondary')],'Shaft speed [rpm]'),
           ('shift',[('shift_mm','Shift')],'Shift [mm]'),
           ('shift_rate',[('shift_rate_mm_s','Shift rate')],'Shift rate [mm/s]'),
           ('forces',[('primary_actuator_closing_N','Primary actuator'),('secondary_actuator_closing_N','Secondary actuator'),('secondary.helix_torsional_preload_N','Helix spring'),('secondary.helix_reacted_belt_torque_force_N','Helix torque feedback'),('secondary.helix_shift_acceleration_force_N','Helix shift acceleration'),('secondary.helix_shaft_acceleration_force_N','Helix shaft acceleration')],'Signed local closing force [N]'),
           ('support',[('upper_stop_reaction_N','Upper stop'),('low_ratio_seat_reaction_N','Low-ratio seat')],'Active support reaction [N]'),
           ('traction',[('primary_static_utilization','Primary'),('secondary_static_utilization','Secondary')],'|lambda| / mu_static'),
           ('slip',[('primary_slip_loss_W','Primary slip loss'),('secondary_slip_loss_W','Secondary slip loss')],'Kinetic-slip power [W]')]
    for name,fields,ylabel in specs:
        series=[(title,[{**r,'v':r.get(key)} for r in near]) for key,title in fields]
        q=out/f'{name}.png';plot_lines(q,series,'relative_time_ms','v','Time relative to selected point [ms]',ylabel,f'{a.car} / {label}: {name}',events=markers)
        images.append(q.relative_to(root).as_posix())
    nearby_events=[e for e in events if abs(float(e['time_s'])-t)<=a.window]
    write_csv(out/'samples.csv',near)
    report=root/f'{a.car}_{label}.html'
    body=f'<html><meta charset="utf-8"><body style="font:15px system-ui;margin:2rem"><h1>{html.escape(a.car)} / {html.escape(label)}</h1><p>Center t={t:.9g} s. Exact transition states are in events.json; the curves use saved diagnostic samples.</p>'+table(nearby_events,['event_id','time_s','distance_m','event_names','reason','delta_shift_rate_m_s','capture_loss_J'])+''.join(f'<img style="max-width:100%" src="{p}">' for p in images)+'</body></html>'
    report.write_text(body,encoding='utf-8');print(report)
if __name__=='__main__':main()
