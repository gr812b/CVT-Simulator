"""Prepare/run independent flat-limit, secondary-hill and cyclic-load screens.

Default is preparation only. --execute uses the normal study runner on full
trajectories. This is deliberately not called by run.py and does not select a
final course. Every variant has an identical course for all of its competitors.
"""
from __future__ import annotations
import argparse
import os
import time
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from infrastructure.common import load_json,write_json,write_csv,digest,source_fingerprint,utc_now
from infrastructure.course import Course


def variants(spec:dict,base:dict):
    output=[]
    flat=deepcopy(base);flat.update(id='feature_flat800',flat_probe_length_m=float(spec['flat_probe_length_m']),hill_angle_deg=0.,cyclic_amplitude_deg=0.,downhill_angle_deg=0.,description='Flat-only finite-time high-ratio reachability probe.')
    flat['id']=f"feature_flat{flat['flat_probe_length_m']:g}"
    output.append({'id':'flat_limit','group':'flat','role':'Extended flat: distinguish slow arrival from persistent finite-time under-shifting','cars':spec['flat_cars'],'course':flat})
    h=spec['secondary_hill']
    for angle in h['angles_deg']:
        name=f'mild_hill_{float(angle):g}'
        course=deepcopy(base);course['id']=name
        course['secondary_hill']={k:v for k,v in h.items() if k!='angles_deg'}
        course['secondary_hill'].update(enabled=True,angle_deg=float(angle))
        output.append({'id':name,'group':'mild_hill','role':'Matched added-distance level control' if angle==0 else 'Moderate second hill after the cyclic sector, before descent','cars':spec['feature_cars'],'course':course})
    for trial in spec['cyclic_variants']:
        course=deepcopy(base);wave=float(trial['wavelength_m']);count=round(spec['cyclic_length_m']/wave)
        if count<2 or abs(count*wave-spec['cyclic_length_m'])>1e-8:raise ValueError('Cyclic length must contain an integer >=2 periods')
        course.update(id=trial['id'],cyclic_amplitude_deg=trial['amplitude_deg'],cyclic_wavelength_m=wave,
            cyclic_count=count,cyclic_mean_grade_deg=trial['mean_grade_deg'],
            cyclic_envelope_length_m=spec['cyclic_envelope_length_m'])
        # Keep the legacy validation field compatible; physical envelope is fixed.
        course['cyclic_envelope_periods']=min(1.,count/2.)
        output.append({'id':trial['id'],'group':'cyclic','role':trial['role'],'cars':spec['feature_cars'],'course':course})
    for item in output:Course(item['course'])
    return output


def upsert_trial(plan_file: Path, identity: dict, item: dict) -> None:
    """Merge one trial atomically; separate group launchers cannot erase a sibling.

    Lock only the short metadata transaction, not any simulation. A stale lock
    fails visibly rather than permitting two writers to corrupt the plan.
    """
    lock=plan_file.with_suffix('.lock');deadline=time.monotonic()+15.
    while True:
        try:
            fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
            os.write(fd,str(os.getpid()).encode());os.close(fd)
            break
        except FileExistsError:
            if time.monotonic()>deadline:
                raise RuntimeError(f'Plan lock remains held: {lock}. Check for another writer before removing a stale lock.')
            time.sleep(.05)
    try:
        state=load_json(plan_file) if plan_file.exists() else {'created_utc':utc_now(),'identity':identity,'trials':[]}
        if state['identity']!=identity:raise ValueError('Existing feature plan identity differs')
        current={t['id']:t for t in state['trials']}
        current[item['id']]={**current.get(item['id'],{}),**item}
        state['trials']=list(current.values());write_json(plan_file,state)
    finally:
        lock.unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--plan',type=Path,default=ROOT/'inputs/feature_exploration.json')
    p.add_argument('--groups',nargs='+',choices=['flat','mild_hill','cyclic'],default=['flat','mild_hill','cyclic'])
    p.add_argument('--variants',nargs='+',help='Restrict to named variants printed by preparation')
    p.add_argument('--cars',nargs='+',help='Override group-specific entrant IDs')
    p.add_argument('--preset',choices=['screen','research','tight'])
    p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--no-plots',action='store_true',help='Defer normal per-campaign graphics, retain all data')
    a=p.parse_args();spec=load_json(a.plan);base=load_json(ROOT/spec['baseline_course'])
    all_trials=variants(spec,base)
    unknown=set(a.variants or [])-{t['id'] for t in all_trials}
    if unknown:raise ValueError(f'Unknown variants: {sorted(unknown)}')
    trials=[t for t in all_trials if t['group'] in a.groups and (not a.variants or t['id'] in a.variants)]
    if not trials:raise ValueError('Selection has no feature trials')
    if a.jobs<1:raise ValueError('--jobs must be positive')
    if a.cars:
        for t in trials:t['cars']=a.cars
    preset=a.preset or spec['preset']
    # Selection doesn't change the plan identity, allowing group-by-group execution.
    identity={'plan':spec,'base_course':base,'source':source_fingerprint(),'preset':preset,'cars_override':a.cars,
        'competitors':load_json(ROOT/spec['competitors'])}
    folder=ROOT/'artifacts/feature_explorations'/digest(identity)[:12];folder.mkdir(parents=True,exist_ok=True)
    plan_file=folder/'plan.json'
    plan=load_json(plan_file) if plan_file.exists() else {'created_utc':utc_now(),'identity':identity,'trials':[]}
    prior={t['id']:t for t in plan['trials']}
    for trial in trials:
        config=folder/'courses'/(trial['id']+'.json');write_json(config,trial['course'])
        record=folder/'campaign_paths'/(trial['id']+'.txt')
        cmd=[sys.executable,str(ROOT/'run.py'),'--course',str(config),'--competitors',str(ROOT/spec['competitors']),
            '--preset',preset,'--cars',*trial['cars'],'--jobs',str(a.jobs),'--max-time',str(spec['maximum_time_s']),
            '--record-campaign',str(record)]
        if a.resume:cmd.append('--resume')
        if a.no_plots:cmd.append('--no-plots')
        item={**prior.get(trial['id'],{}),**trial,'course_file':str(config),'command':cmd,'record_file':str(record)}
        prior[trial['id']]=item
        upsert_trial(plan_file,identity,item)
        print(f"{trial['id']}: {len(trial['cars'])} entrants, {Course(trial['course']).finish_m:g} m — {trial['role']}",flush=True)
        if a.execute:
            result=subprocess.run(cmd,cwd=ROOT.parents[2])
            item['return_code']=result.returncode;item['last_run_utc']=utc_now()
            if record.exists():item['campaign_dir']=record.read_text(encoding='utf-8').strip()
            upsert_trial(plan_file,identity,item)
            if result.returncode:print(f"WARNING: {trial['id']} returned {result.returncode}; retained for review, proceeding.",flush=True)
            from analysis.compare_features import build_comparison
            build_comparison(plan_file)
    write_csv(folder/'planned_cases.csv',[{'variant':t['id'],'group':t['group'],'cars':t['cars'],'role':t['role'],'length_m':Course(t['course']).finish_m} for t in trials])
    print(f"\nSelected work: {sum(len(t['cars']) for t in trials)} complete-trajectory cases in {len(trials)} campaigns.")
    print(f"Plan: {plan_file}")
    if not a.execute:print('Preparation only. Add --execute --resume to run; inputs/course.json and inputs/competitors.json are unchanged.')
    else:print(f"Comparison: {folder/'index.html'}")
    return 0
if __name__=='__main__':raise SystemExit(main())
