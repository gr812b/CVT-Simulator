"""Audit-first RC28 replacement search on the locked final course.

Every definition is decoded through the shared Results reference loader before
any trajectory is launched. Geometry rejections are retained as evidence and
are never integrated. The original RC28 geometry is an explicit expected-
rejection control and is never run even if a future environment unexpectedly
accepts it.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import html
import multiprocessing
import os
from pathlib import Path
import re
import shutil
import traceback

from infrastructure.common import load_json, write_json, write_csv, read_csv, sha_file, digest, utc_now
from infrastructure.model import check_environment
from infrastructure.course import Course
from shift_shape.tuning import resolve_shape_tune
from shift_shape.preflight import inspect_definition
from shift_shape.runner import run_job, reusable, lock, make_pack, ERRORS
from shift_shape.report import build_shape_report

ROOT=Path(__file__).resolve().parents[1]      # exploration/
FINAL=ROOT.parent                            # course-tuning/
RELEASE=FINAL.parents[1]                     # results/cinder-v1.1.2/
CANDIDATES=ROOT/'inputs/rc28_replacement_candidates.json'


def _source_files() -> list[Path]:
    files=[Path(__file__).resolve(), ROOT/'scans/scan_rc28_replacements.py', CANDIDATES]
    files += sorted((ROOT/'shift_shape').glob('*.py'))
    files += [FINAL/'inputs/course.json', FINAL/'inputs/selection.lock.json']
    return [p for p in files if p.is_file()]


def _preflight_one(payload:dict):
    base=payload['base'];tune=payload['tune'];course_config=payload['course'];execution=payload['execution'];out=Path(payload['out'])
    row={'id':tune['id'],'label':tune['label'],'family':tune['family'],
         'expected_preflight_rejection':bool(tune.get('expected_preflight_rejection',False)),
         'ramp_end_deg':tune.get('knobs',{}).get('ramp_end_deg'),
         'ramp_prefix_mm':None if tune.get('knobs',{}).get('ramp_prefix_m') is None else 1000*float(tune['knobs']['ramp_prefix_m']),
         'ramp_blend_mm':None if tune.get('knobs',{}).get('ramp_blend_m') is None else 1000*float(tune['knobs']['ramp_blend_m']),
         'ramp_tail_kind':tune.get('knobs',{}).get('ramp_tail_kind')}
    summary=None
    try:
        doc,summary=resolve_shape_tune(base,tune)
        checks=inspect_definition(doc,course_config,execution,out)
        audit=checks['released_geometry_audit']
        row.update(preflight_status='accepted_definition',preflight_reason='',
            minimum_angle_gradient_per_m=audit.get('minimum_angle_gradient_per_m'),
            maximum_absolute_angle_curvature_per_m2=audit.get('maximum_absolute_angle_curvature_per_m2'),
            minimum_absolute_offset_regular_factor=audit.get('minimum_absolute_offset_regular_factor'),
            minimum_ramp_endpoint_margin_m=audit.get('minimum_ramp_endpoint_margin_m'),
            maximum_mathematical_candidates=audit.get('maximum_mathematical_candidates'))
        if tune.get('expected_preflight_rejection'):
            row['preflight_status']='unexpectedly_accepted_rejection_control'
    except Exception as exc:
        row.update(preflight_status='rejected_definition',preflight_reason=f'{type(exc).__name__}: {exc}')
        if summary is None:
            try: _,summary=resolve_shape_tune(base,tune)
            except Exception: pass
    return row,summary


def _screen(base:dict, fleet:list[dict], course_config:dict, execution:dict, folder:Path, jobs:int):
    payloads=[{'base':base,'tune':t,'course':course_config,'execution':execution,'out':str(folder/'definition_checks'/t['id'])} for t in fleet]
    results=[]
    if jobs==1:
        results=[_preflight_one(p) for p in payloads]
    else:
        with ProcessPoolExecutor(max_workers=jobs,mp_context=multiprocessing.get_context('spawn')) as pool:
            futures={pool.submit(_preflight_one,p):p['tune']['id'] for p in payloads}
            by={}
            for f in as_completed(futures):
                by[futures[f]]=f.result()
                print('preflight',futures[f],by[futures[f]][0]['preflight_status'],flush=True)
            results=[by[t['id']] for t in fleet]
    rows=[r for r,_ in results]
    resolved=[s for _,s in results if s is not None]
    accepted=[]
    for tune,row in zip(fleet,rows):
        if row['preflight_status']=='accepted_definition' and not tune.get('expected_preflight_rejection'):
            doc,summary=resolve_shape_tune(base,tune);accepted.append((tune,doc,summary))
    write_csv(folder/'definition_screen.csv',rows)
    write_csv(folder/'competitors_resolved.csv',resolved)
    return rows,accepted


def _build_replacement_summary(folder:Path, screen_rows:list[dict]):
    shape={r['id']:r for r in read_csv(folder/'shift_shape_metrics.csv')} if (folder/'shift_shape_metrics.csv').is_file() else {}
    outcomes={}
    for p in (folder/'cases').iterdir() if (folder/'cases').is_dir() else []:
        if (p/'summary.json').is_file(): outcomes[p.name]=load_json(p/'summary.json')
    rows=[]
    for s in screen_rows:
        q=shape.get(s['id'],{});o=outcomes.get(s['id'],{})
        rows.append({**s,
            'run_status':o.get('status'),
            'finish_time_s':o.get('finish_time_s'),
            'max_distance_m':o.get('max_distance_m'),
            'overall_slope_rpm_per_1000_secondary_rpm':q.get('overall_slope_rpm_per_1000_secondary_rpm'),
            'offset_removed_shape_rms_rpm':q.get('offset_removed_shape_rms_rpm'),
            'mean_primary_offset_rpm':q.get('mean_primary_offset_rpm'),
            'common_secondary_rpm_span':q.get('common_secondary_rpm_span')})
    write_csv(folder/'replacement_summary.csv',rows)
    measured=[r for r in rows if r.get('preflight_status')=='accepted_definition' and r.get('run_status') not in (None,*ERRORS)
            and isinstance(r.get('overall_slope_rpm_per_1000_secondary_rpm'),(int,float))]
    measured.sort(key=lambda r:r['overall_slope_rpm_per_1000_secondary_rpm'])
    falling=[r for r in measured if float(r['overall_slope_rpm_per_1000_secondary_rpm'])<0]
    write_csv(folder/'accepted_measured_candidates.csv',measured)
    write_csv(folder/'falling_curve_candidates.csv',falling)

    def cell(v):
        if v is None:return ''
        if isinstance(v,float):return f'{v:.5g}'
        return html.escape(str(v))
    cols=['id','preflight_status','ramp_end_deg','ramp_prefix_mm','ramp_blend_mm','run_status',
          'overall_slope_rpm_per_1000_secondary_rpm','finish_time_s','max_distance_m','preflight_reason']
    def table(data):
        return '<table><thead><tr>'+''.join(f'<th>{html.escape(c)}</th>' for c in cols)+'</tr></thead><tbody>'+''.join(
            '<tr>'+''.join(f'<td>{cell(r.get(c))}</td>' for c in cols)+'</tr>' for r in data)+'</tbody></table>'
    body='''<!doctype html><html><head><meta charset="utf-8"><title>RC28 replacement search</title>
<style>body{font:15px system-ui;max-width:1500px;margin:2rem}table{border-collapse:collapse;display:block;overflow:auto}th,td{border:1px solid #bbb;padding:.45rem;vertical-align:top}p{line-height:1.5}.good{background:#e7f6e7}</style></head><body>
<h1>RC28 replacement search</h1>
<p><strong>Audit first:</strong> every definition is decoded through the frozen Results reference path before integration. Rejected definitions are recorded and never run. <code>RC28X</code> is the exact final-v2 RC28 geometry and is an expected-rejection control only.</p>
<p><a href="shift_shape.html">Shift-curve and mechanism comparison</a> · <a href="index.html">Full course gallery</a> · <a href="definition_screen.csv">Definition screen CSV</a> · <a href="falling_curve_candidates.csv">Accepted candidates sorted by measured opening-flat slope</a></p>
<h2>All definitions</h2>'''+table(rows)
    if falling:
        body+='<h2>Measured falling-curve candidates</h2><p>Sorted from most negative upward by opening-flat free-upshift secant. This is a trajectory descriptor, not a performance score or automatic promotion rule.</p>'+table(falling)
    body+='''<h2>Selection boundary</h2><p>No candidate is automatically promoted into <code>course-tuning/run.py</code>. We will select a replacement only after reviewing geometry acceptance, the measured shift curve, whole-course behavior, and the mechanism maps from this frozen-environment run.</p></body></html>'''
    (folder/'replacement_screen.html').write_text(body,encoding='utf-8')
    main=folder/'index.html'
    if main.is_file():
        text=main.read_text(encoding='utf-8')
        text=text.replace('<h1>Spring-rate and ramp-shape course exploration</h1>',
                          '<h1>RC28 replacement course exploration</h1><p><strong><a href="replacement_screen.html">Start here: construction-audit screen and falling-curve candidates</a></strong></p>')
        main.write_text(text,encoding='utf-8')
    return rows,falling


def arguments():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs',type=int,default=1)
    p.add_argument('--preset',choices=('tight','research','screen','smoke'),default='tight')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--retry-errors',action='store_true')
    p.add_argument('--preflight-only',action='store_true',help='Run the exact construction audit only; do not integrate accepted candidates.')
    p.add_argument('--pack',action='store_true')
    p.add_argument('--no-plots',action='store_true')
    p.add_argument('--report-only',type=Path)
    return p.parse_args()


def main():
    a=arguments()
    if a.jobs<1:raise ValueError('--jobs must be positive')
    if a.report_only:
        folder=a.report_only.resolve();screen=read_csv(folder/'definition_screen.csv')
        with lock(folder):
            build_shape_report(folder,plots=not a.no_plots);_build_replacement_summary(folder,screen)
        if a.pack:print('Return ZIP:',make_pack(folder),flush=True)
        return 0

    env=check_environment();spec=load_json(ROOT/'exploration.json');settings=dict(spec['presets'][a.preset]);execution=dict(spec['execution'])
    fleet_doc=load_json(CANDIDATES);fleet=fleet_doc['competitors']
    ids=[t['id'] for t in fleet]
    if len(ids)!=len(set(ids)) or any(not re.fullmatch(r'[A-Za-z0-9_-]+',i) for i in ids):raise ValueError('Invalid/duplicate candidate IDs')
    course_path=FINAL/'inputs/course.json';course_config=load_json(course_path);course=Course(course_config)
    base_path=RELEASE/'defaults/baja/simulation_case.json';base=load_json(base_path)
    selected_lock=load_json(FINAL/'inputs/selection.lock.json')
    if digest(course_config)!=selected_lock['inputs']['inputs/course.json']:raise ValueError('Final course changed; replacement search is locked to the selected road.')
    if digest(base)!=selected_lock['baseline_canonical_sha256']:raise ValueError('Shared Baja baseline changed; review before running replacement search.')
    shared_dir=RELEASE/'defaults/reference_model';shared={str(p.relative_to(RELEASE)):sha_file(p) for p in sorted(shared_dir.glob('*')) if p.suffix in ('.py','.json')}
    source={p.relative_to(ROOT).as_posix() if ROOT in p.parents else str(p):sha_file(p) for p in _source_files()}
    identity={'study':'rc28_replacement_v1','source':source,'environment':env,'settings':settings,'execution':execution,
              'course':course_config,'candidate_definition':fleet_doc,'baseline_sha256':sha_file(base_path),'shared_helpers':shared,
              'diagnostics':spec['diagnostics'],'shape_metric_revision':1}
    fp=digest(identity);folder=ROOT/'artifacts'/f'rc28_replacement_v1__{a.preset}__{fp[:12]}'
    folder.mkdir(parents=True,exist_ok=True);(folder/'cases').mkdir(exist_ok=True)
    campaign={**identity,'fingerprint':fp,'created_utc':utc_now(),'preset':a.preset,'artifact_status':'exploratory',
              'competitors':fleet,'course_finish_m':course.finish_m,'course_sectors':course.table(),'baseline_source':str(base_path),
              'note':'Focused RC28 replacement search. Definitions rejected by the released construction audit are never integrated.'}
    if (folder/'campaign.json').exists():campaign['created_utc']=load_json(folder/'campaign.json')['created_utc']
    print(f'RC28 replacement screen: {len(fleet)-2} candidates + R00 + rejection control; {a.preset}',flush=True)
    print('Outputs:',folder,flush=True)
    if not env['frozen_environment_match']:print('NOTE: surrounding dependency versions differ from the frozen Results environment; saved in campaign.json.',flush=True)

    with lock(folder):
        write_json(folder/'campaign.json',campaign)
        # Snapshot only this focused search plus the shared exploration/final inputs it consumes.
        for p in _source_files():
            rel=p.relative_to(ROOT) if ROOT in p.parents else Path('external')/p.name
            dest=folder/'provenance/exploration'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        for path,rel in [(course_path,'inputs/course.json'),(base_path,'shared/defaults/baja/simulation_case.json'),(ROOT/'exploration.json','inputs/exploration.json')]:
            dest=folder/'provenance'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
        for rel in shared:
            dest=folder/'provenance/shared'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(RELEASE/rel,dest)

        screen,accepted=_screen(base,fleet,course_config,execution,folder,a.jobs)
        expected=next(r for r in screen if r['id']=='RC28X')
        if expected['preflight_status']!='rejected_definition':
            print('WARNING: RC28X did not reproduce the expected rejection in this environment; it remains excluded from integration.',flush=True)
        print(f'Construction audit accepted {len(accepted)-1 if any(t[0]["id"]=="R00" for t in accepted) else len(accepted)} replacement candidates.',flush=True)
        if a.preflight_only:
            _build_replacement_summary(folder,screen)
            if a.pack:print('Return ZIP:',make_pack(folder),flush=True)
            print('Open:',folder/'replacement_screen.html',flush=True)
            return 0

        accepted_ids=[t[0]['id'] for t in accepted]
        if 'R00' not in accepted_ids:raise RuntimeError('Reference definition failed construction audit; stop before candidate comparison.')
        replacement_count=sum(i!='R00' for i in accepted_ids)
        if replacement_count==0:raise RuntimeError('No replacement geometry passed the frozen construction audit. Return definition_screen.csv for the next search.')
        jobs=[]
        for tune,doc,summary in accepted:
            out=folder/'cases'/tune['id'];casefp=digest({'campaign':fp,'tune':tune})
            if out.exists() and any(out.iterdir()):
                status=load_json(out/'status.json').get('status') if (out/'status.json').is_file() else 'incomplete'
                if a.resume and reusable(out,casefp) and not(a.retry_errors and status in ERRORS):
                    print(tune['id'],'cached',status,flush=True);continue
                if not a.resume:raise RuntimeError(f'{out} exists. Use --resume; existing evidence is not overwritten.')
                dest=folder/'previous_attempts'/tune['id']/utc_now().replace(':','-');dest.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(out),str(dest))
            jobs.append({'case_dir':str(out),'tune':tune,'resolved_tune':summary,'document':doc,'course':course_config,
                         'settings':settings,'execution':execution,'diagnostics':spec['diagnostics'],'fingerprint':casefp,
                         'launch_context':{'jobs':a.jobs}})
        write_json(folder/'invocation.json',{'utc':utc_now(),'accepted_ids':accepted_ids,'jobs':a.jobs,'resume':a.resume,'preset':a.preset})
        write_json(folder/'accepted_candidates.json',{'ids':accepted_ids,'replacement_ids':[i for i in accepted_ids if i!='R00']})
        if a.jobs==1:
            for job in jobs:
                result=run_job(job);print(result['id'],result['status'],flush=True)
        else:
            with ProcessPoolExecutor(max_workers=a.jobs,mp_context=multiprocessing.get_context('spawn')) as pool:
                pending={pool.submit(run_job,j):j for j in jobs}
                for future in as_completed(pending):
                    try:result=future.result()
                    except Exception:
                        job=pending[future];out=Path(job['case_dir']);out.mkdir(parents=True,exist_ok=True);text=traceback.format_exc()
                        result={**{k:job['tune'][k] for k in ('id','label','family','intent')},'status':'worker_error','review_required':True,'reason':text.splitlines()[-1]}
                        write_json(out/'summary.json',result);write_json(out/'status.json',{'complete_output':False,'status':'worker_error'});(out/'error.txt').write_text(text)
                    print(result['id'],result['status'],flush=True)
        build_shape_report(folder,plots=not a.no_plots)
        _,falling=_build_replacement_summary(folder,screen)
        print(f'Measured falling-curve candidates: {len(falling)}',flush=True)
    if a.pack:print('Return ZIP:',make_pack(folder),flush=True)
    print('Open:',folder/'replacement_screen.html',flush=True)
    errors=[]
    for cid in accepted_ids:
        p=folder/'cases'/cid/'status.json'
        if not p.is_file() or load_json(p).get('status') in ERRORS:errors.append(cid)
    return 1 if errors else 0
