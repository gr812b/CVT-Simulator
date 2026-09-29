"""Checks on retained evidence. No trajectories are integrated here."""
from __future__ import annotations
import csv
import gzip
import json
import math
from pathlib import Path
import shutil
from .common import MissingEvidence, digest, read_json, write_json, require_complete, verify_hashes, strict_bool
from .guards import course_endpoint_audit


def csv_rows(path):
    path=Path(path)
    if not path.is_file():raise MissingEvidence('Missing CSV: '+str(path))
    opener=gzip.open if path.suffix=='.gz' else open
    with opener(path,'rt',encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.DictReader(stream))
    if not rows:raise ValueError('Empty CSV: '+str(path))
    return rows


def check_primary(inputs, raw=None):
    import numpy as np
    inputs=Path(inputs);audit=read_json(inputs/'primary_publication_audit.json')
    if digest(inputs/'primary_publication.npz')!=audit['plot_inputs_sha256']:
        raise ValueError('Primary plot-input hash mismatch')
    verified=verify_hashes(Path(raw),audit['raw_sha256']) if raw and Path(raw).is_dir() else 0
    with np.load(inputs/'primary_publication.npz',allow_pickle=False) as z:
        failures=[]
        count=0
        for name,check in audit['checks'].items():
            if 'force_reconstruction_max_error_N' not in check:continue
            count+=1
            if not math.isfinite(check['force_reconstruction_max_error_N']) or check['force_reconstruction_max_error_N']>1e-8:
                failures.append(name+': force reconstruction')
            for key in ('minimum_primary_normal_N','minimum_secondary_normal_N','minimum_stick_stick_traction_margin'):
                if not math.isfinite(check[key]) or check[key]<-1e-8:failures.append(name+': '+key)
            t=z[name+'__time_s']
            if not np.isfinite(t).all() or np.any(np.diff(t)<0):failures.append(name+': time ordering')
            for key in ('shift_mm','shift_speed_mm_s','primary_rpm'):
                if not np.isfinite(z[name+'__'+key]).all():failures.append(name+': '+key)
        if count!=12:failures.append(f'Expected 12 primary raw trajectories, found {count}')
    if failures:raise ValueError('Primary evidence check: '+repr(failures))
    return {'checked_trajectories':count,'raw_files_verified':verified,
            'raw_available':bool(verified),'scope':'Retained primary values and force reconstruction; existing numerical-comparison definitions unchanged'}


def course_state(row):
    return [float(row[k])*scale for k,scale in (
        ('omega_p_rad_s',1),('omega_s_rad_s',1),('belt_speed_m_s',1),
        ('shift_mm',.001),('shift_rate_mm_s',.001))]


def event_sides(rows, events):
    """Match exact retained one-sided states; never interpolate across a reset."""
    import numpy as np
    from collections import defaultdict
    # Bucketing just accelerates lookup; the final time and state tests are explicit.
    by_time=defaultdict(list)
    for row in rows:by_time[round(float(row['time_s']),8)].append(row)
    failures=[];checked=0
    for event in events:
        now=float(event['time_s']);near=[]
        for offset in (-1e-8,0,1e-8):near.extend(by_time.get(round(now+offset,8),[]))
        near=[r for r in near if abs(float(r['time_s'])-now)<=1e-10]
        sides=[('pre_state','previous_mode','end')]
        if event.get('next_mode') not in (None,'None',''):
            sides.append(('post_state','next_mode','start'))
        for state_key,mode_key,location in sides:
            expected=np.asarray(event[state_key][:5],dtype=float)
            match=[r for r in near if r.get('sample_location') in ('start','end','post_transition_exact') and r.get('regime') and r['regime'] in str(event[mode_key])]
            accepted=any(np.allclose(course_state(r),expected,rtol=1e-10,atol=1e-10) for r in match)
            if not accepted:failures.append({'event':event.get('event_id'),'time_s':now,'missing_side':state_key})
            else:checked+=1
    return {'verified_event_sides':checked,'missing_event_sides':failures,
            'time_match_tolerance_s':1e-10,'state_match_rtol':1e-10,'state_match_atol_SI':1e-10}


def check_course(suite, output):
    """Write a fresh review alongside, never rewrite or reseal the original suite."""
    suite=Path(suite);output=Path(output)
    manifest=read_json(suite/'suite.json')
    from infrastructure.selection import reusable_case, validate_selection
    if manifest.get('selection') != validate_selection():
        raise ValueError('Retained suite does not match the locked publication case selection')
    expected=manifest.get('expected_cases',[])
    if len(expected)!=15 or len(set(expected))!=15 or manifest.get('smoke'):
        raise ValueError('The selected manuscript course suite requires 15 cases, not a smoke run')
    if not manifest.get('environment',{}).get('frozen_environment_match'):
        raise ValueError('Course suite was not generated in its frozen environment')
    tolerance=float(manifest['diagnostics']['physical_margin_review_tolerance'])
    result={'suite':str(suite.resolve()),'suite_sha256':digest(suite/'suite.json'),'cases':{},'passed':True}
    for name in expected:
        case=suite/name.split('/')[0]/'cases'/name.split('/')[1]
        try:
            resolved=read_json(case/'resolved_case.json')
            if not reusable_case(case, resolved['fingerprint']):
                raise ValueError('Retained case integrity/fingerprint check failed')
            rows=csv_rows(case/'diagnostics.csv');events=read_json(case/'events.json')
            original=read_json(case/'summary.json')
            a=course_endpoint_audit(rows,tolerance);e=event_sides(rows,events)
            status=original.get('status')
            if status == 'time_limit':
                require_complete(True,original['last_completed_time_s'],
                                 resolved['numerical_settings']['maximum_time_s'],label=name)
            passed=a['failed_rows']==0 and not e['missing_event_sides'] and status in ('finished','rollback','progress_limited','time_limit')
            value={'passed':passed,'original_status':status,'original_review_required':original.get('review_required'),
                   'endpoint_audit':a,**e,'input_sha256':{f:digest(case/f) for f in ('diagnostics.csv','events.json','summary.json','resolved_case.json')}}
        except Exception as exc:
            value={'passed':False,'error':f'{type(exc).__name__}: {exc}'}
        result['cases'][name]=value
        result['passed'] &= value['passed']
    write_json(output,result)
    if not result['passed']:
        raise ValueError('Course health failed; all cases were still checked. See '+str(output))
    return result


def solver_completion(root, output):
    """C06: separately inspect actual cached termination, including old caches."""
    root=Path(root);records=[];failures=[]
    for meta_file in sorted(root.rglob('metadata.json')):
        cfg_file=meta_file.with_name('config.json')
        if not cfg_file.is_file():continue
        meta=read_json(meta_file);cfg=read_json(cfg_file)
        if 'time_span_s' not in cfg:continue
        status=meta.get('run_status','completed')
        if status=='integration_failed':
            records.append({'path':str(meta_file),'status':'documented_integration_failure'})
            continue
        try:require_complete(meta.get('completed'),meta.get('final_time_s'),cfg['time_span_s'][-1],label=str(meta_file))
        except Exception as exc:failures.append(str(exc))
        records.append({'path':str(meta_file),'status':status,'completed':meta.get('completed'),'final_time_s':meta.get('final_time_s')})
    result={'checked_execution_records':len(records),'failures':failures,'records':records}
    write_json(output,result)
    if not records:raise MissingEvidence('No original config.json + metadata.json cache pairs found under '+str(root))
    if failures:raise ValueError('Incomplete solver caches: '+repr(failures[:8]))
    return result


def import_compact(source, target, names):
    target=Path(target);target.mkdir(parents=True,exist_ok=True)
    for name in names:
        p=Path(source)/name
        if not p.is_file():raise MissingEvidence('Missing retained input: '+str(p))
        shutil.copy2(p,target/name)
