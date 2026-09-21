#!/usr/bin/env python3
"""Reproduce the selected Section 4.5 cases and all reports in one final-results folder."""
from __future__ import annotations
import os
for _key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ.setdefault(_key,'1')
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from infrastructure.common import (load_json,write_json,write_csv,digest,sha_file,
    source_fingerprint,utc_now,RELEASE_ROOT)
from infrastructure.course import Course
from infrastructure.tunes import resolve_tune
from infrastructure.selection import (validate_selection,shared_hashes,snapshot_sources,
    seal_case,reusable_case,archive_attempt,output_lock,ERROR_STATUSES)


def arguments(argv=None):
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--jobs',type=int,default=4,help='Independent processes; never parallel LSODA threads')
    p.add_argument('--resume',action='store_true',help='Reuse hash-verified completed cases; restart interrupted cases from their original initial state')
    p.add_argument('--retry-errors',action='store_true',help='With --resume, retry completed setup/integration/timeout errors')
    p.add_argument('--only',nargs='+',metavar='EXPERIMENT/CAR',help='Run a subset such as unified_course/D02; the final report remains incomplete until all selected cases exist')
    p.add_argument('--prepare-only',action='store_true',help='Verify and write exact inputs without integrating')
    p.add_argument('--smoke',action='store_true',help='Separate three-second R00/D02 plumbing check, never the final-results folder')
    p.add_argument('--no-plots',action='store_true',help='Defer image rendering; CSV/JSON reports are still produced')
    p.add_argument('--pack',action='store_true',help='Also write a portable return ZIP beside the results folder')
    p.add_argument('--allow-environment-mismatch',action='store_true',help='Diagnostic use only; preserve a conspicuous non-frozen-environment warning')
    return p.parse_args(argv)


def run_one(job:dict) -> dict:
    """Every case's stdout and traceback stay beside its saved trajectory."""
    from contextlib import redirect_stdout,redirect_stderr
    from experiments.fleet import execute_case
    from infrastructure.shape_preflight import inspect_definition
    out=Path(job['case_dir']);out.mkdir(parents=True,exist_ok=True)
    with (out/'execution.log').open('a',encoding='utf-8') as log:
        with redirect_stdout(log),redirect_stderr(log):
            inspect_definition(job['document'],job['course'],job['execution'],out)
            summary=execute_case(job)
    seal_case(out,job['fingerprint'])
    return summary


def record_worker_error(job:dict) -> None:
    out=Path(job['case_dir']);out.mkdir(parents=True,exist_ok=True)
    message=traceback.format_exc();(out/'worker_error.txt').write_text(message,encoding='utf-8')
    checkpoint=load_json(out/'checkpoint.json') if (out/'checkpoint.json').exists() else {}
    write_json(out/'summary.json',{'id':job['tune']['id'],'status':'worker_error',
        'reason':message.splitlines()[-1],'review_required':True,'finish_time_s':None,
        'max_distance_m':checkpoint.get('distance_m',0),
        'last_completed_time_s':checkpoint.get('last_completed_time_s',0)})
    write_json(out/'status.json',{'status':'worker_error','complete_output':False,'fingerprint':job['fingerprint']})


def main(argv=None) -> int:
    a=arguments(argv)
    if a.jobs<1:raise ValueError('--jobs must be positive')
    if a.retry_errors and not a.resume:raise ValueError('--retry-errors requires --resume')
    lock=validate_selection();spec=load_json(ROOT/'study.json')
    from infrastructure.model import check_environment
    env=check_environment()
    if not env['frozen_environment_match'] and not a.allow_environment_mismatch:
        raise RuntimeError('Activate the existing CINDER 1.1.2 Results environment (Python 3.12, NumPy 2.5.2, SciPy 1.18.1, Matplotlib 3.11.1). Diagnostic runs can explicitly use --allow-environment-mismatch; that does not replace the frozen final run.')
    if not env['frozen_environment_match']:print('WARNING: non-frozen dependency environment; prominently recorded in the report.',flush=True)
    baseline=RELEASE_ROOT/'defaults/baja/simulation_case.json';base=load_json(baseline)
    fleet=load_json(ROOT/spec['inputs']['competitors'])['competitors'];by_id={t['id']:t for t in fleet}
    groups=spec['experiments'];settings=dict(spec['numerical_settings'])
    if a.smoke:
        groups=[{**groups[0],'cars':['R00','D02']}]
        settings['maximum_time_s']=3.0
    expected=[g['id']+'/'+car for g in groups for car in g['cars']]
    chosen=set(a.only or expected)
    if chosen-set(expected):raise ValueError('Unknown selected case(s): '+', '.join(sorted(chosen-set(expected))))
    identity={'selection':lock,'source':source_fingerprint(),
        'baseline_canonical_sha256':digest(base),'baseline_file_sha256':sha_file(baseline),
        'shared_helpers':shared_hashes(),'environment':env,'settings':settings,
        'execution':spec['execution'],'diagnostics':spec['diagnostics'],
        'experiments':groups,'smoke':a.smoke}
    fp=digest(identity)
    output=ROOT/'artifacts'/f"{'smoke' if a.smoke else 'final_v3'}__{fp[:12]}"
    output.mkdir(parents=True,exist_ok=True)
    manifest={**identity,'fingerprint':fp,'selection_revision':spec['selection_revision'],
        'created_utc':utc_now(),'expected_cases':expected,'expected_case_count':len(expected),
        'artifact_kind':'smoke_only' if a.smoke else 'selected_final_case_set',
        'comparison_groups':load_json(ROOT/'inputs/presentation.json'),
        'settling_criteria':load_json(ROOT/'inputs/settling_criteria.json'),
        'notes':['No exploratory outputs are imported or re-used.',
                 'Supporting flat runs are regenerated at the same final tight settings.',
                 'A full dataset may contain observed non-finishers; completion does not mean every vehicle finished.']}
    if (output/'suite.json').exists():manifest['created_utc']=load_json(output/'suite.json')['created_utc']
    with output_lock(output):
        write_json(output/'suite.json',manifest)
        snapshot_sources(output/'provenance')
        invocation={'started_utc':utc_now(),'selected_cases':sorted(chosen),'jobs':a.jobs,
            'resume':a.resume,'retry_errors':a.retry_errors,'prepare_only':a.prepare_only,
            'blas_threads':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')}}
        history=output/'invocations.json';write_json(history,(load_json(history) if history.exists() else [])+[invocation])
        jobs=[]
        for g in groups:
            course_config=load_json(ROOT/g['course']);course=Course(course_config)
            folder=output/g['id'];folder.mkdir(exist_ok=True);(folder/'cases').mkdir(exist_ok=True)
            campaign={**identity,'fingerprint':digest({'suite':fp,'group':g}),
                'preset':'smoke' if a.smoke else 'tight','course':course_config,
                'competitors':[by_id[c] for c in g['cars']], 'colour_order':list(by_id), 'course_sectors':course.table(),
                'course_finish_m':course.finish_m,'created_utc':manifest['created_utc'],
                'artifact_status':manifest['artifact_kind'],'experiment_id':g['id'],
                'experiment_title':g['title'],'baseline_source':str(baseline)}
            write_json(folder/'campaign.json',campaign)
            write_csv(folder/'course_profile.csv',course.profile_rows())
            resolved=[]
            for car in g['cars']:
                tune=by_id[car];doc,values=resolve_tune(base,tune);resolved.append(values)
                key=g['id']+'/'+car
                casefp=digest({'suite':fp,'case':key,'tune':tune})
                out=folder/'cases'/car
                if key not in chosen:continue
                job={'case_dir':str(out),'case_key':key,'tune':tune,'resolved_tune':values,
                    'document':doc,'course':course_config,'settings':settings,
                    'execution':spec['execution'],'diagnostics':spec['diagnostics'],
                    'fingerprint':casefp,'launch_context':invocation}
                if a.prepare_only:
                    write_json(output/'prepared'/g['id']/(car+'.json'),job)
                    continue
                if out.exists():
                    if not a.resume:raise RuntimeError(f'{key} already has outputs. Use --resume to continue without mixing or overwriting runs.')
                    prior=load_json(out/'status.json') if (out/'status.json').exists() else {}
                    if reusable_case(out,casefp) and not (a.retry_errors and prior.get('status') in ERROR_STATUSES):
                        print(f'{key}: retained {prior.get("status")}',flush=True);continue
                    archive_attempt(out,output)
                jobs.append(job)
            write_csv(folder/'competitors_resolved.csv',resolved)
        pointer=ROOT/'artifacts'/('latest_smoke.txt' if a.smoke else 'latest_final.txt')
        pointer.write_text(str(output)+'\n',encoding='utf-8')
        # Portable entry point even when some cases are still running.
        if not (output/'index.html').exists():
            (output/'index.html').write_text('<!doctype html><html><meta charset="utf-8"><h1>Selected course study</h1><p>Prepared/running. Rebuild completes after simulation.</p><a href="suite.json">Exact manifest</a></html>',encoding='utf-8')
        print(f'Output: {output}\nSelected {len(chosen)} of {len(expected)} cases; {len(jobs)} to integrate.',flush=True)
        if a.prepare_only:return 0
        if a.jobs==1:
            for n,job in enumerate(jobs,1):
                print(f'[{n}/{len(jobs)}] {job["case_key"]}',flush=True)
                try:
                    s=run_one(job);print(f'{job["case_key"]}: {s["status"]}; {s.get("max_distance_m",0):.2f} m',flush=True)
                except Exception:
                    record_worker_error(job);print(f'{job["case_key"]}: worker error; see case folder',flush=True)
        else:
            with ProcessPoolExecutor(max_workers=a.jobs,mp_context=multiprocessing.get_context('spawn')) as pool:
                pending={pool.submit(run_one,j):j for j in jobs}
                for f in as_completed(pending):
                    job=pending[f]
                    try:
                        s=f.result();print(f'{job["case_key"]}: {s["status"]}; {s.get("max_distance_m",0):.2f} m',flush=True)
                    except Exception:
                        record_worker_error(job);print(f'{job["case_key"]}: worker error; see case folder',flush=True)
        from analysis.report_final import build_final_report,pack_results
        status=build_final_report(output,plots=not a.no_plots)
        print(f'Report: {output/"index.html"}',flush=True)
        if a.pack:print(f'Return ZIP: {pack_results(output)}',flush=True)
    print('Dataset:',status['dataset_status'],flush=True)
    return 0 if status['ready_for_review'] else 2

if __name__=='__main__':
    multiprocessing.freeze_support()
    try:raise SystemExit(main())
    except KeyboardInterrupt:raise SystemExit('Interrupted. Use --resume; completed cases are retained, unfinished cases restart from t=0.')
    except (ValueError,RuntimeError,FileNotFoundError) as exc:raise SystemExit(str(exc))
