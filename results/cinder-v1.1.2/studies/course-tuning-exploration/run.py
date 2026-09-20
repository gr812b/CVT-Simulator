"""Run a full-throttle competitor fleet on one common distance-based course."""
from __future__ import annotations
import os
# LSODA is isolated by PROCESS, not thread. Avoid BLAS oversubscription.
for _k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ.setdefault(_k,'1')
import argparse
import re
from concurrent.futures import ProcessPoolExecutor,as_completed
import multiprocessing
from pathlib import Path
import sys
import traceback

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path: sys.path.insert(0,str(HERE))
from infrastructure.common import load_json,write_json,write_csv,source_fingerprint,sha_file,digest,environment,utc_now
from infrastructure.tunes import resolve_tune
from infrastructure.course import Course


def arguments():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--course',type=Path,default=HERE/'inputs/course.json')
    p.add_argument('--competitors',type=Path,default=HERE/'inputs/competitors.json')
    p.add_argument('--preset',choices=('smoke','screen','research','tight'),default='screen')
    p.add_argument('--cars',nargs='+',help='IDs or family names (comma-separated also accepted); default all 32')
    p.add_argument('--jobs',type=int,default=1,help='Separate processes, not threads; use e.g. 4 on your machine')
    p.add_argument('--max-time',type=float,help='Override maximum simulated seconds for every selected car')
    p.add_argument('--wall-timeout',type=float,help='Per-car integration wall timeout [s]')
    p.add_argument('--diagnostic-step',type=float,help='Saved mechanical inspection spacing [s], not solver step')
    p.add_argument('--checkpoint-seconds',type=float,help='Administrative integration chunk size; keep fixed within a comparison')
    p.add_argument('--no-progress-stop',action='store_true',help='Disable the slow-progress censoring rule (rollback event still applies)')
    p.add_argument('--list',action='store_true',help='List competitor intentions and exit without importing CINDER')
    p.add_argument('--prepare-only',action='store_true',help='Resolve configurations and campaign hashes, without simulation')
    p.add_argument('--resume',action='store_true',help='Skip complete case outputs with the same exact fingerprint')
    p.add_argument('--rerun',action='store_true',help='Replace selected case outputs in the same fingerprinted campaign')
    p.add_argument('--retry-errors',action='store_true',help='With --resume, rerun setup/integration/timeout errors')
    p.add_argument('--no-plots',action='store_true',help='Write tables and HTML but postpone plot generation')
    p.add_argument('--focus',nargs='+',help='IDs to emphasize in overview and detailed plots')
    return p.parse_args()


def main():
    a=arguments();spec=load_json(HERE/'study.json');fleet=load_json(a.competitors)['competitors']
    ids=[t['id'] for t in fleet]
    if not fleet or len(set(ids))!=len(ids): raise ValueError('The competitor file needs unique nonempty IDs')
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',i) for i in ids): raise ValueError('Use simple alphanumeric competitor IDs')
    if a.list:
        for t in fleet: print(f"{t['id']:5s} {t['label']:40s} {t['family']}\n      {t['intent']}")
        return 0
    if a.jobs<1: raise ValueError('--jobs must be >=1')
    chosen=set(s for token in (a.cars or []) for s in token.split(','))
    all_ids={t['id'] for t in fleet};families={t['family'] for t in fleet}
    if chosen-all_ids-families: raise ValueError(f'Unknown competitor/family: {chosen-all_ids-families}')
    selected=[t for t in fleet if not chosen or t['id'] in chosen or t['family'] in chosen]
    course_config=load_json(a.course);course=Course(course_config)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',str(course_config['id'])): raise ValueError('Use a simple alphanumeric course ID')
    settings=dict(spec['presets'][a.preset]);execution=dict(spec['execution'])
    if a.max_time is not None: settings['maximum_time_s']=a.max_time
    if a.wall_timeout is not None: execution['case_wall_timeout_s']=a.wall_timeout
    if a.diagnostic_step is not None: settings['diagnostic_step_s']=a.diagnostic_step
    if a.checkpoint_seconds is not None: execution['checkpoint_interval_s']=a.checkpoint_seconds
    if a.no_progress_stop: execution['no_progress_window_s']=0.
    for k in ('maximum_time_s','diagnostic_step_s','max_step_s'):
        if settings[k]<=0: raise ValueError(f'{k} must be positive')
    if execution['checkpoint_interval_s']<=0 or execution['case_wall_timeout_s']<=0: raise ValueError('Invalid time budget')
    base_path=(HERE/spec['base_document']).resolve()
    if not base_path.is_file(): raise FileNotFoundError(f'Extract this study into results/cinder-v1.1.2. Missing shared baseline: {base_path}')
    base=load_json(base_path)
    from infrastructure.model import check_environment
    env=check_environment()
    if not env['frozen_environment_match']:
        print('NOTE: dependency/Python versions differ from the frozen Results environment; recorded in campaign.json.',flush=True)
    shared=base_path.parents[1]/'reference_model'
    shared_sources={p.name:sha_file(p) for p in sorted(shared.glob('*.py'))}
    if (shared/'policy.json').exists(): shared_sources['policy.json']=sha_file(shared/'policy.json')
    identity={'source':source_fingerprint(),'baseline_sha256':sha_file(base_path),'shared_helpers':shared_sources,'settings':settings,'execution':execution,'course':course_config,'competitors':fleet,'diagnostics':spec['diagnostics'],'environment':env}
    fp=digest(identity)
    run_dir=HERE/'artifacts'/f"{course_config['id']}__{a.preset}__{fp[:12]}"
    run_dir.mkdir(parents=True,exist_ok=True);(run_dir/'cases').mkdir(exist_ok=True)
    campaign={**identity,'fingerprint':fp,'created_utc':utc_now(),'preset':a.preset,'competitors':fleet,'course_sectors':course.table(),'course_finish_m':course.finish_m,'artifact_status':'exploratory','baseline_source':str(base_path)}
    if (run_dir/'campaign.json').exists(): campaign['created_utc']=load_json(run_dir/'campaign.json')['created_utc']
    invocation={'started_utc':utc_now(),'selected_ids':[t['id'] for t in selected],'jobs':a.jobs,'prepare_only':a.prepare_only,'resume':a.resume,'rerun':a.rerun,'blas_threads':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')}}
    inv_path=run_dir/'invocations.json'
    invocations=load_json(inv_path) if inv_path.exists() else []
    write_json(inv_path,[*invocations,invocation])
    write_json(run_dir/'campaign.json',campaign);write_csv(run_dir/'course_profile.csv',course.profile_rows())
    resolved=[];jobs=[]
    for t in fleet:
        doc,summary=resolve_tune(base,t);resolved.append(summary)
        if t not in selected: continue
        out=run_dir/'cases'/t['id'];casefp=digest({'campaign':fp,'tune':t})
        job={'case_dir':str(out),'tune':t,'resolved_tune':summary,'document':doc,'course':course_config,'settings':settings,'execution':execution,'diagnostics':spec['diagnostics'],'fingerprint':casefp,'launch_context':invocation}
        if out.exists() and (out/'status.json').exists() and not a.prepare_only:
            prior=load_json(out/'status.json')
            good=(prior.get('complete_output') and prior.get('fingerprint')==casefp)
            error=prior.get('status') in ('integration_error','setup_error','wall_timeout','worker_error')
            if good and a.resume and not a.rerun and not (a.retry_errors and error):
                print(f"{t['id']}: cached {prior['status']}");continue
            if not a.rerun and not a.resume: raise RuntimeError(f'{out} already exists. Use --resume or --rerun.')
            # Only this explicitly selected case directory is regenerated.
            import shutil
            shutil.rmtree(out)
        if a.prepare_only:
            write_json(run_dir/'prepared'/f"{t['id']}.json",{'public_document':doc,'resolved_tune':summary,'course':course_config})
        else:jobs.append(job)
    write_csv(run_dir/'competitors_resolved.csv',resolved)
    (HERE/'artifacts/latest_run.txt').write_text(str(run_dir)+'\n',encoding='utf-8')
    print(f'Course: {course_config["hill_angle_deg"]:g} deg hill, {course.wavelength:g} m cyclic wavelength, {course.finish_m:g} m total.\nOutputs: {run_dir}',flush=True)
    if a.prepare_only: return 0
    from experiments.fleet import execute_case
    def announce(s):
        print(f"{s['id']}: {s['status']}; max distance {s.get('max_distance_m',0):.1f} m; last accepted t={s.get('last_completed_time_s',0):.2f} s; {s.get('reason','')}",flush=True)
    def worker_error(job):
        text=traceback.format_exc(); print(text,flush=True)
        out=Path(job['case_dir']); checkpoint={}
        if (out/'checkpoint.json').is_file(): checkpoint=load_json(out/'checkpoint.json')
        record={**{k:job['tune'][k] for k in ('id','label','family','intent')},
                'status':'worker_error','reason':text.splitlines()[-1],
                'review_required':True,'finish_time_s':None,
                'last_completed_time_s':checkpoint.get('last_completed_time_s',0.),
                'max_distance_m':checkpoint.get('distance_m',0.),
                'note':'Incomplete post-processing/worker output. Inspect worker_error.json and retained checkpoints.'}
        write_json(out/'worker_error.json',{'error':text,'complete_output':False})
        write_json(out/'summary.json',record)
        write_json(out/'status.json',{'status':'worker_error','complete_output':False,'fingerprint':job['fingerprint']})
    worker_failures=0
    if a.jobs==1:
        for n,job in enumerate(jobs,1):
            print(f"[{n}/{len(jobs)}] {job['tune']['id']}",flush=True)
            try:announce(execute_case(job))
            except Exception:
                worker_failures+=1;worker_error(job)
    else:
        with ProcessPoolExecutor(max_workers=a.jobs,mp_context=multiprocessing.get_context('spawn')) as pool:
            pending={pool.submit(execute_case,j):j for j in jobs}
            for f in as_completed(pending):
                try:announce(f.result())
                except Exception:
                    worker_failures+=1;worker_error(pending[f])
    from analysis.report import build_report
    build_report(run_dir,a.focus,not a.no_plots)
    print(f'Report: {run_dir / "index.html"}',flush=True)
    return 1 if worker_failures else 0

if __name__=='__main__':
    multiprocessing.freeze_support()
    try:raise SystemExit(main())
    except KeyboardInterrupt:raise SystemExit('Interrupted. Completed case outputs/checkpoints are retained.')
