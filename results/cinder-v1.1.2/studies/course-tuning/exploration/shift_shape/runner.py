"""One same-road exploratory campaign; final course-tuning selection is read-only."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from contextlib import contextmanager
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
import shutil
import sys
import traceback
from zipfile import ZipFile, ZIP_DEFLATED

from infrastructure.common import load_json,write_json,write_csv,sha_file,digest,utc_now,source_fingerprint
from infrastructure.model import check_environment
from infrastructure.course import Course
from .tuning import resolve_shape_tune

ROOT=Path(__file__).resolve().parents[1]  # exploration
FINAL=ROOT.parent
RELEASE=FINAL.parents[1]
ESSENTIAL=('summary.json','status.json','resolved_case.json','diagnostics.csv','events.json','segments.csv')
ERRORS={'setup_error','integration_error','wall_timeout','worker_error'}


def sources() -> dict:
    files={ROOT/p:sha for p,sha in source_fingerprint().items()}
    files.update({p:sha_file(p) for p in (ROOT/'shift_shape').rglob('*.py') if '__pycache__' not in p.parts})
    return {p.relative_to(ROOT).as_posix():v for p,v in sorted(files.items())}


def seal(folder: Path, fp: str):
    write_json(folder/'shape_integrity.json',{'fingerprint':fp,'files':{p.name:sha_file(p) for p in folder.iterdir()
        if p.is_file() and p.name!='shape_integrity.json'}})


def reusable(folder:Path, fp:str) -> bool:
    try:
        status=load_json(folder/'status.json');proof=load_json(folder/'shape_integrity.json')
        if not status.get('complete_output') or proof['fingerprint']!=fp:return False
        if not all((folder/n).is_file() for n in ESSENTIAL):return False
        return all((folder/n).is_file() and sha_file(folder/n)==s for n,s in proof['files'].items())
    except (OSError,ValueError,KeyError):return False


@contextmanager
def lock(folder:Path):
    p=folder/'RUNNING.lock'
    try:fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as exc:raise RuntimeError(f'Campaign locked: {p}. Remove only after confirming no run is active.') from exc
    try:
        with os.fdopen(fd,'w') as f:json.dump({'pid':os.getpid(),'started_utc':utc_now()},f)
        yield
    finally:p.unlink(missing_ok=True)


def run_job(job:dict):
    from experiments.fleet import execute_case
    from .preflight import inspect_definition
    out=Path(job['case_dir']);out.mkdir(parents=True,exist_ok=True)
    try:
        inspect_definition(job['document'],job['course'],job['execution'],out)
        result=execute_case(job)
    except Exception:
        text=traceback.format_exc()
        result={k:job['tune'][k] for k in ('id','label','family','intent')}
        result.update(status='worker_error',review_required=True,reason=text.splitlines()[-1],finish_time_s=None,max_distance_m=0.)
        write_json(out/'summary.json',result);write_json(out/'status.json',{'complete_output':False,'status':'worker_error','fingerprint':job['fingerprint']})
        (out/'error.txt').write_text(text)
    if all((out/n).is_file() for n in ESSENTIAL):seal(out,job['fingerprint'])
    return result


def make_pack(folder:Path):
    dest=folder.parent/(folder.name+'_return.zip')
    temp=dest.with_suffix('.zip.tmp')
    with ZipFile(temp,'w',ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(folder.rglob('*')):
            rel=p.relative_to(folder)
            if p.is_file() and not p.is_symlink() and not set(rel.parts)&{'previous_attempts','__pycache__'} and p.name!='RUNNING.lock':
                z.write(p,folder.name+'/'+rel.as_posix())
    os.replace(temp,dest);return dest


def arguments():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs',type=int,default=1)
    p.add_argument('--preset',choices=('tight','research','screen','smoke'),default='tight')
    p.add_argument('--cars',nargs='+',help='IDs/families; R00 is included automatically as the comparison reference')
    p.add_argument('--max-time',type=float)
    p.add_argument('--wall-timeout',type=float)
    p.add_argument('--resume',action='store_true');p.add_argument('--retry-errors',action='store_true')
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--list',action='store_true')
    p.add_argument('--verify',action='store_true',help='Run tests and validate every selected assembly; no trajectories')
    p.add_argument('--pack',action='store_true');p.add_argument('--no-plots',action='store_true')
    p.add_argument('--report-only',type=Path,help='Rebuild this campaign report from saved records')
    p.add_argument('--record-campaign',type=Path)
    return p.parse_args()


def main():
    a=arguments()
    from .report import build_shape_report
    if a.report_only:
        with lock(a.report_only):
            build_shape_report(a.report_only,plots=not a.no_plots)
        if a.pack:print(make_pack(a.report_only))
        return 0
    fleet_path=ROOT/'inputs/shift_shape_candidates.json';fleet=load_json(fleet_path)['competitors']
    if a.list:
        for t in fleet:print(f"{t['id']:7s} {t['family']:16s} {t['intent']}")
        return 0
    if a.jobs<1:raise ValueError('--jobs must be positive')
    if a.verify:
        import unittest
        tests=unittest.defaultTestLoader.discover(str(ROOT/'shift_shape/tests'),pattern='test_*.py')
        if not unittest.TextTestRunner(verbosity=2).run(tests).wasSuccessful():return 1
    env=check_environment();spec=load_json(ROOT/'exploration.json')
    settings=dict(spec['presets'][a.preset]);execution=dict(spec['execution'])
    if a.max_time is not None:settings['maximum_time_s']=a.max_time
    if a.wall_timeout is not None:execution['case_wall_timeout_s']=a.wall_timeout
    if any(not isinstance(v,(int,float)) or not 0<float(v)<float('inf') for v in settings.values()):raise ValueError('Invalid numerical settings')
    if not 0<float(execution['case_wall_timeout_s'])<float('inf'):raise ValueError('Invalid wall timeout')
    ids=[t['id'] for t in fleet]
    if len(ids)!=len(set(ids)) or any(not re.fullmatch(r'[A-Za-z0-9_-]+',i) for i in ids):raise ValueError('Invalid/duplicate IDs')
    chosen={i for token in (a.cars or []) for i in token.split(',')}
    unknown=chosen-set(ids)-{t['family'] for t in fleet}
    if unknown:raise ValueError(f'Unknown IDs/families: {unknown}')
    selected=[t for t in fleet if not chosen or t['id']=='R00' or t['id'] in chosen or t['family'] in chosen]
    course_path=FINAL/'inputs/course.json';course_config=load_json(course_path);course=Course(course_config)
    base_path=RELEASE/'defaults/baja/simulation_case.json';base=load_json(base_path)
    selected_lock=load_json(FINAL/'inputs/selection.lock.json')
    if digest(course_config)!=selected_lock['inputs']['inputs/course.json']:
        raise ValueError('The selected common road changed; this exploration is defined on the confirmed final road.')
    if digest(base)!=selected_lock['baseline_canonical_sha256']:
        raise ValueError('The shared Baja physical baseline changed; review before mixing this comparison with the selected study.')
    share=RELEASE/'defaults/reference_model'
    shared={str(p.relative_to(RELEASE)):sha_file(p) for p in sorted(share.glob('*')) if p.suffix in ('.py','.json')}
    source=sources()
    identity={'source':source,'baseline_sha256':sha_file(base_path),'shared_helpers':shared,
        'settings':settings,'execution':execution,'course':course_config,'competitors':fleet,
        'diagnostics':spec['diagnostics'],'environment':env,'shape_metric_revision':1}
    fp=digest(identity);folder=ROOT/'artifacts'/f'shift_shape_v1__{a.preset}__{fp[:12]}'
    folder.mkdir(parents=True,exist_ok=True);(folder/'cases').mkdir(exist_ok=True)
    campaign={**identity,'fingerprint':fp,'created_utc':utc_now(),'preset':a.preset,'artifact_status':'exploratory',
        'course_finish_m':course.finish_m,'course_sectors':course.table(),'baseline_source':str(base_path),
        'note':'Read-only use of the final common road; no candidates promoted to the final run.'}
    if (folder/'campaign.json').exists():campaign['created_utc']=load_json(folder/'campaign.json')['created_utc']
    print(f'Common road: {course.finish_m:g} m; selected entrants: {len(selected)}; {a.preset}',flush=True)
    print(f'Outputs: {folder}',flush=True)
    if not env['frozen_environment_match']:print('NOTE: surrounding dependency versions differ from the frozen Results environment; saved in campaign.json.',flush=True)
    if a.record_campaign:
        a.record_campaign.parent.mkdir(parents=True,exist_ok=True);a.record_campaign.write_text(str(folder)+'\n')
    with lock(folder):
        write_json(folder/'campaign.json',campaign)
        for rel in source:
            dest=folder/'provenance/exploration'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,dest)
        for path,rel in [(fleet_path,'inputs/shift_shape_candidates.json'),(course_path,'inputs/course.json'),(ROOT/'exploration.json','inputs/exploration.json'),(base_path,'shared/defaults/baja/simulation_case.json')]:
            dest=folder/'provenance'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
        for rel in shared:
            dest=folder/'provenance/shared'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(RELEASE/rel,dest)
        resolved=[];jobs=[]
        for t in fleet:
            doc,summary=resolve_shape_tune(base,t);resolved.append(summary)
            if t not in selected:continue
            out=folder/'cases'/t['id'];casefp=digest({'campaign':fp,'tune':t})
            if a.prepare_only:
                write_json(folder/'prepared'/f"{t['id']}.json",{'public_document':doc,'resolved_tune':summary});continue
            if a.verify:
                from .preflight import inspect_definition
                checks=inspect_definition(doc,course_config,execution,folder/'definition_checks'/t['id'])
                print(t['id'],checks['status'],flush=True);continue
            if out.exists() and any(out.iterdir()):
                status=load_json(out/'status.json').get('status') if (out/'status.json').exists() else 'incomplete'
                if a.resume and reusable(out,casefp) and not(a.retry_errors and status in ERRORS):
                    print(t['id'],'cached',status,flush=True);continue
                if not a.resume:raise RuntimeError(f'{out} exists. Use --resume; existing evidence is not overwritten.')
                dest=folder/'previous_attempts'/t['id']/utc_now().replace(':','-');dest.parent.mkdir(parents=True,exist_ok=True)
                if dest.exists():raise RuntimeError('Attempt archive collision; wait one second before retrying')
                shutil.move(str(out),str(dest))
            jobs.append({'case_dir':str(out),'tune':t,'resolved_tune':summary,'document':doc,
                'course':course_config,'settings':settings,'execution':execution,'diagnostics':spec['diagnostics'],
                'fingerprint':casefp,'launch_context':{'jobs':a.jobs}})
        write_csv(folder/'competitors_resolved.csv',resolved)
        write_json(folder/'invocation.json',{'utc':utc_now(),'selected_ids':[t['id'] for t in selected],'jobs':a.jobs,'prepare_only':a.prepare_only,'verify':a.verify,'resume':a.resume})
        (ROOT/'artifacts/latest_shift_shape.txt').write_text(str(folder)+'\n')
        if a.prepare_only or a.verify:return 0
        results=[]
        if a.jobs==1:
            for j in jobs:
                result=run_job(j);results.append(result);print(result['id'],result['status'],flush=True)
        else:
            with ProcessPoolExecutor(max_workers=a.jobs,mp_context=multiprocessing.get_context('spawn')) as pool:
                pending={pool.submit(run_job,j):j for j in jobs}
                for f in as_completed(pending):
                    try:result=f.result()
                    except Exception:
                        job=pending[f];out=Path(job['case_dir']);out.mkdir(parents=True,exist_ok=True)
                        text=traceback.format_exc()
                        result={**{k:job['tune'][k] for k in ('id','label','family','intent')},'status':'worker_error','review_required':True,'reason':text.splitlines()[-1]}
                        write_json(out/'summary.json',result);write_json(out/'status.json',{'complete_output':False,'status':'worker_error'})
                        (out/'error.txt').write_text(text)
                    results.append(result);print(result['id'],result['status'],flush=True)
        build_shape_report(folder,plots=not a.no_plots)
    if a.pack:print('Return ZIP:',make_pack(folder),flush=True)
    print('Open:',folder/'index.html',flush=True)
    selected_statuses=[load_json(folder/'cases'/t['id']/'status.json') if (folder/'cases'/t['id']/'status.json').exists() else {} for t in selected]
    return 1 if any(not s.get('complete_output') or s.get('status') in ERRORS for s in selected_statuses) else 0
