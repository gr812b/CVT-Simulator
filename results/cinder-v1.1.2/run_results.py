#!/usr/bin/env python3
"""Run Results corrections/checks and always write a final health report.

correct (default): five fresh Ballew calculations + retained checks elsewhere.
check: no simulations; check explicitly identified existing evidence.
all: regenerate selected publication runs and core sweeps; may take hours or longer.

Historical discovery searches and exact course manuscript compositing are NOT
silently recreated. Missing retained evidence remains visible in the report.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import math
import zipfile
import os
from pathlib import Path
import shutil
import subprocess
import sys

RELEASE=Path(__file__).resolve().parent
REPO=RELEASE.parents[1]
if str(RELEASE) not in sys.path:sys.path.insert(0,str(RELEASE))
from results_health.common import digest,read_json,write_json
from results_health.engine import run_plan,report
from results_health.plan import build_plan,GROUPS
from results_health import PATCH_VERSION,MECHANICS_COMMIT

PATH_KEYS={'ballew_raw','mechanical_artifacts','energy_artifacts','solver_artifacts','solver_cache',
           'closure_artifacts','primary_inputs','primary_raw','secondary_inputs','belt_inputs',
           'belt_raw','course_suite','course_output_root'}


def source_inventory():
    """Record checked-out Results source/inputs; never traverse generated output or venvs."""
    files={}
    ignore={'artifacts','work','health_runs','.venv','__pycache__','.pytest_cache','.git','exploration','previous_attempts'}
    for parent,dirs,names in os.walk(RELEASE,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in ignore and not (Path(parent)/d).is_symlink())
        for name in sorted(names):
            p=Path(parent)/name
            if p.is_symlink() or p.name.startswith('.pr505'):continue
            if p.suffix in {'.py','.json','.csv','.npz'}:
                files[p.relative_to(RELEASE).as_posix()]=digest(p)
    identity=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
    return files,identity


def interpreter(requested):
    if requested:
        found=shutil.which(requested)
        return Path(found or requested).expanduser().resolve()
    return RELEASE/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')


def package_summary(root):
    """Small return package; raw datasets remain in place and are not duplicated."""
    dest=root/'health_summary.zip';tmp=root/'health_summary.zip.tmp'
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('health_report.html','health_report.json','health_report.md',
                     'run_context.json','source_manifest.json','execution_plan.json',
                     'manuscript_figure_inventory.json'):
            p=root/name
            if p.is_file():archive.write(p,name)
        for folder in ('logs','checks'):
            for p in sorted((root/folder).rglob('*')):
                if p.is_file():archive.write(p,p.relative_to(root).as_posix())
    os.replace(tmp,dest)
    return dest


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mode',choices=('correct','check','all'),default='correct')
    parser.add_argument('--output',type=Path,help='New output directory; defaults to health_runs/<UTC timestamp>')
    parser.add_argument('--resume',action='store_true',help='With --output: reuse matching successful generation only; recheck/reprocess evidence')
    parser.add_argument('--python',dest='python_path',help='Frozen interpreter override; still subject to verify_environment.py')
    parser.add_argument('--paths',type=Path,help='JSON paths to retained archives (example: results_paths.example.json)')
    parser.add_argument('--only',nargs='+',choices=GROUPS,help='Explicit subset; report records partial scope')
    parser.add_argument('--dry-run',action='store_true',help='Print the execution plan without integrating or writing outputs')
    parser.add_argument('--step-timeout-hours',type=float,default=0.,help='Optional per-step wall limit; 0 means no imposed limit')
    a=parser.parse_args(argv)
    if not math.isfinite(a.step_timeout_hours) or a.step_timeout_hours<0:parser.error('--step-timeout-hours cannot be negative')
    if a.resume and a.output is None:parser.error('--resume requires --output')
    paths=read_json(a.paths) if a.paths else {}
    if not isinstance(paths,dict) or set(paths)-PATH_KEYS:parser.error('Unknown keys in --paths JSON: '+repr(set(paths)-PATH_KEYS if isinstance(paths,dict) else paths))
    for key,value in paths.items():
        if value:
            p=Path(value).expanduser()
            if not p.is_absolute():p=(a.paths.resolve().parent/p) if a.paths else REPO/p
            paths[key]=str(p.resolve())
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root=(a.output or RELEASE/'health_runs'/stamp).expanduser().resolve()
    if root==RELEASE or root==REPO or root in RELEASE.parents:
        parser.error('--output must be a dedicated generated-output directory')
    # Protect committed source/evidence even if an output argument is mistyped.
    if root.is_relative_to(RELEASE) and not root.is_relative_to(RELEASE/'health_runs'):
        parser.error('Inside Results, place --output under health_runs/; other paths contain source or retained evidence')
    exe=interpreter(a.python_path)
    if a.dry_run:
        steps=build_plan(RELEASE,root,exe,a.mode,paths,a.only,save=False)
        print(__doc__);print('\nInterpreter:',exe,'\nOutput:',root)
        for i,s in enumerate(steps,1):print(f'{i:3d} {s.id} [{s.role}] after: {", ".join(s.dependencies) or "none"}')
        print(f'\n{len(steps)} steps. No execution and no health verdict.');return 0
    if root.exists() and any(root.iterdir()) and not a.resume:
        parser.error('Output is not empty; select a new directory or use --resume')
    root.mkdir(parents=True,exist_ok=True)
    context={'patch_version':PATCH_VERSION,'mode':a.mode,'scope':a.only or list(GROUPS),
             'partial_scope':bool(a.only and set(a.only)!=set(GROUPS)),
             'output':str(root),'interpreter':str(exe),'mechanics_commit':MECHANICS_COMMIT,
             'started_utc':stamp,'retained_paths':paths}
    lock=root/'RUNNING.lock'
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        os.write(fd,f'{os.getpid()}\n'.encode());os.close(fd)
    except FileExistsError:
        parser.error('RUNNING.lock exists. Check that no run is active before removing a stale lock.')
    try:
        inventory,identity=source_inventory();context['source_identity']=identity
        try:context['git_head']=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
        except (OSError,subprocess.CalledProcessError):context['git_head']=None
        if a.resume:
            previous=read_json(root/'run_context.json')
            for key in ('mode','scope','source_identity','interpreter','retained_paths'):
                if previous.get(key)!=context.get(key):
                    raise ValueError('Resume identity changed ('+key+'); preserve this run and choose a new output directory')
        write_json(root/'run_context.json',context)
        write_json(root/'source_manifest.json',inventory)
        # Snapshot text source/inputs for provenance. Large retained NPZs are identified by hash;
        # generated corrected evidence is retained separately under data/ and prepared/.
        snap=root/'source_snapshot'
        if not snap.exists():
            for name in inventory:
                src=RELEASE/name
                if src.suffix=='.npz':continue
                dst=snap/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
        steps=build_plan(RELEASE,root,exe,a.mode,paths,a.only,save=True)
        write_json(root/'execution_plan.json',[s.__dict__ for s in steps])
        print(f'Mode: {a.mode}; {len(steps)} steps; output: {root}',flush=True)
        if a.mode in ('all','correct'):
            print('This includes numerical integrations and may take a long time. Full mode may take hours or longer.',flush=True)
        print('Independent steps continue after failures. A final nonzero exit reports failed/missing work, not an early abort.',flush=True)
        result=run_plan(steps,root,REPO,context,resume=a.resume,timeout_s=a.step_timeout_hours*3600,
                        env={'PYTHONPATH':str(RELEASE)})
        _,after=source_inventory()
        if after!=identity:
            context['source_changed_during_execution']=True
            result['steps'].append({'id':'source-stability','group':'environment','role':'health','status':'FAIL','elapsed_s':0.,
                                    'detail':'Results source/inputs changed during this run; do not freeze this mixed execution'})
            result=report(root,result['steps'],context)
        # Hash the existing manuscript assets as an inventory, without conversion or optimization.
        assets=REPO/'docs/CVT_Module_Formulation/figures'
        if assets.is_dir():
            write_json(root/'manuscript_figure_inventory.json',{
                'scope':'Existing files only; format/visual cleanup deferred',
                'files':{p.relative_to(assets).as_posix():{'sha256':digest(p),'bytes':p.stat().st_size}
                         for p in sorted(assets.rglob('*')) if p.is_file() and p.suffix.lower() in ('.pdf','.svg','.png','.jpg','.jpeg')}})
        print('\nHealth report:',root/'health_report.html',flush=True)
        print('Machine-readable report:',root/'health_report.json',flush=True)
        print('Shareable summary:',package_summary(root),flush=True)
        return 0 if result['all_requested_steps_passed'] else 2
    except BaseException as exc:
        try:
            old=read_json(root/'health_report.json')['steps'] if (root/'health_report.json').is_file() else []
        except (OSError,ValueError,KeyError):
            old=[]
        old.append({'id':'orchestrator','group':'environment','role':'health','status':'FAIL','elapsed_s':0.,
                    'detail':f'{type(exc).__name__}: {exc}'})
        report(root,old,context)
        print('Health report written despite error:',root/'health_report.html',file=sys.stderr)
        print(str(exc),file=sys.stderr)
        try:package_summary(root)
        except OSError:pass
        return 130 if isinstance(exc,KeyboardInterrupt) else 2
    finally:lock.unlink(missing_ok=True)

if __name__=='__main__':raise SystemExit(main())
