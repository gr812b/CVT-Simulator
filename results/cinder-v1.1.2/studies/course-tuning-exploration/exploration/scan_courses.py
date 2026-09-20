"""Optional discovery-only course screen. Each course is common to all its entrants."""
from __future__ import annotations
import argparse
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from infrastructure.common import load_json,write_json,write_csv,digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--grades',nargs='+',type=float,default=[35.,38.,40.])
    p.add_argument('--wavelengths',nargs='+',type=float,default=[4.,6.])
    p.add_argument('--cars',nargs='+',default=['R00','W90','B01','D02','D03'])
    p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--preset',choices=['screen','research','tight'],default='screen')
    p.add_argument('--execute',action='store_true',help='Without this flag, write profiles and print commands only')
    a=p.parse_args();base=load_json(HERE/'inputs/course.json')
    spec={'grades':a.grades,'wavelengths':a.wavelengths,'cars':a.cars,'preset':a.preset,'base':base}
    root=HERE/'artifacts'/'course_screens'/digest(spec)[:12];root.mkdir(parents=True,exist_ok=True)
    write_json(root/'screen_spec.json',spec);all_rows=[]
    length=float(base['cyclic_wavelength_m'])*int(base['cyclic_count'])
    for grade in a.grades:
        for wave in a.wavelengths:
            if not 0<grade<89 or wave<=0:raise ValueError('Invalid grade or wavelength')
            cycles=round(length/wave)
            if cycles<2 or abs(cycles*wave-length)>1e-8:
                raise ValueError(f'{wave:g} m does not divide the {length:g} m cyclic sector into at least two whole periods')
            course=deepcopy(base);course.update(hill_angle_deg=grade,cyclic_wavelength_m=wave,cyclic_count=cycles,id=f'explore_g{grade:g}_w{wave:g}_{digest(base)[:6]}')
            path=root/f"{course['id']}.json";write_json(path,course)
            cmd=[sys.executable,str(HERE/'run.py'),'--course',str(path),'--preset',a.preset,'--cars',*a.cars,'--jobs',str(a.jobs),'--resume','--no-plots']
            print(subprocess.list2cmdline(cmd),flush=True)
            if not a.execute:continue
            subprocess.run(cmd,check=True)
            run_dir=Path((HERE/'artifacts/latest_run.txt').read_text().strip())
            recorded=load_json(run_dir/'campaign.json')
            if recorded['course']!=course:raise RuntimeError('Another process changed latest_run; inspect printed campaign path')
            for q in sorted((run_dir/'cases').glob('*/summary.json')):
                summary=load_json(q)
                all_rows.append({'course':course['id'],'hill_deg':grade,'wavelength_m':wave,'run_dir':str(run_dir),**summary})
            write_csv(root/'course_screen_summary.csv',all_rows)
    print(f'Course screen: {root}',flush=True)
if __name__=='__main__':main()
