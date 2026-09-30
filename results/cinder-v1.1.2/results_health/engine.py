"""Small dependency-aware subprocess runner. An independent failure never aborts the plan."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Any
from .common import digest, read_json, write_json

GOOD = {'PASS', 'REUSED'}

@dataclass
class Step:
    id: str
    group: str
    command: list[str]
    dependencies: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    role: str = 'generation'
    note: str = ''


def output_hashes(paths):
    files={}
    for item in paths:
        p=Path(item)
        if not p.exists():raise FileNotFoundError('Expected output was not written: '+str(p))
        candidates=[p] if p.is_file() else sorted(x for x in p.rglob('*') if x.is_file() and '__pycache__' not in x.parts)
        if not candidates:raise ValueError('Expected output directory is empty: '+str(p))
        for file in candidates:files[str(file.resolve())]=digest(file)
    return files


def signature(step, identity):
    return hashlib.sha256(json.dumps({'step':asdict(step),'source_identity':identity},sort_keys=True).encode()).hexdigest()


def stop_process(p):
    if p.poll() is not None:return
    if os.name == 'nt':
        subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    else:
        try:os.killpg(p.pid,signal.SIGTERM)
        except ProcessLookupError:return
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:pass


def run_child(command, log, cwd, env, timeout_s):
    options={'cwd':str(cwd),'env':env,'stdout':log,'stderr':subprocess.STDOUT}
    if os.name=='nt':options['creationflags']=subprocess.CREATE_NEW_PROCESS_GROUP
    else:options['start_new_session']=True
    p=subprocess.Popen(command,**options)
    try:
        return p.wait(timeout=None if timeout_s<=0 else timeout_s)
    except (KeyboardInterrupt,subprocess.TimeoutExpired):
        stop_process(p)
        raise


def report(root, rows, context):
    counts={s:sum(r['status']==s for r in rows) for s in sorted({r['status'] for r in rows})}
    health=[r for r in rows if r.get('role')=='health']
    all_health=bool(health) and all(r['status'] in GOOD for r in health)
    report_data={**context,'updated_utc':datetime.now(timezone.utc).isoformat(),
        'counts':counts,'all_requested_steps_passed':bool(rows) and all(r['status'] in GOOD for r in rows),
        'all_requested_health_checks_passed':all_health,
        'ready_to_freeze':False,
        'freeze_notes':[
            'This is a numerical execution/health record, not automatic approval of manuscript conclusions.',
            'The exact nine course manuscript composites still need their publication extraction registered (F03).',
            'Distribute any externally retained evidence used here (F05); a local path is not a public archive.',
            'Review corrected benchmark values and compare conclusions before promoting figures into the manuscript.',
            'Archived discovery searches are not silently replaced by new selected-publication or core runs.'
        ],'steps':rows}
    write_json(root/'health_report.json',report_data)
    lines=['# CINDER Results health report','',
           'This report concerns the requested numerical tasks. It does not automatically freeze or approve the paper.',
           '',f"Mode: **{context.get('mode','custom')}**. Requested health checks passed: **{all_health}**.",'',
           '| Step | Status | Seconds | Detail |','|---|---|---:|---|']
    for row in rows:
        detail=row.get('detail','').replace('|','/').replace('\n',' ')
        lines.append(f"| {row['id']} | {row['status']} | {row.get('elapsed_s',0):.2f} | {detail} |")
    lines += ['', '## Before freezing', *['- '+n for n in report_data['freeze_notes']]]
    (root/'health_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    esc=lambda x:html.escape(str(x))
    body=['<!doctype html><meta charset="utf-8"><title>CINDER Results health</title>',
          '<style>body{font:15px system-ui;max-width:1200px;margin:2rem auto;padding:0 1rem}td,th{border:1px solid #aaa;padding:.6rem;text-align:left}table{border-collapse:collapse;width:100%}code{overflow-wrap:anywhere}p,li{line-height:1.5}</style>',
          '<h1>CINDER Results health report</h1>',f'<p>Mode: <b>{esc(context.get("mode"))}</b>. All requested health checks passed: <b>{all_health}</b>.</p>',
          '<p>A failed step does not stop independent work. BLOCKED means a prerequisite failed; MISSING means required evidence was absent. Neither is a pass.</p>',
          '<table><tr><th>Step</th><th>Status</th><th>Seconds</th><th>Detail / log</th></tr>']
    for r in rows:
        log=r.get('log')
        loglink=f'<br><a href="{esc(log)}">Open log</a>' if log else ''
        body.append(f'<tr><td>{esc(r["id"])}</td><td><b>{esc(r["status"])}</b></td><td>{r.get("elapsed_s",0):.2f}</td><td>{esc(r.get("detail",""))}{loglink}</td></tr>')
    body+=['</table><h2>Before freezing</h2><ul>',*['<li>'+esc(n)+'</li>' for n in report_data['freeze_notes']],'</ul><p><a href="health_report.json">Machine-readable report</a> · <a href="health_report.md">Markdown report</a></p>']
    (root/'health_report.html').write_text('\n'.join(body),encoding='utf-8')
    return report_data


def run_plan(steps, root, cwd, context, *, resume=False, timeout_s=0., env=None):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    (root/'logs').mkdir(exist_ok=True)
    ids=[s.id for s in steps]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate step IDs')
    seen=set()
    for s in steps:
        if set(s.dependencies)-seen:raise ValueError('Plan is not in dependency order: '+s.id)
        seen.add(s.id)
    env={**os.environ,**(env or {}),'PYTHONUNBUFFERED':'1','PYTHONIOENCODING':'utf-8',
         'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONOPTIMIZE':''}
    prior={}
    if resume and (root/'health_report.json').is_file():
        prior={r['id']:r for r in read_json(root/'health_report.json')['steps']}
    rows=[];by_id={};interrupted=False
    try:
        for index, step in enumerate(steps,1):
            row={'id':step.id,'group':step.group,'role':step.role,'command':step.command,
                 'note':step.note,'status':'NOT_RUN','elapsed_s':0.,'detail':'',
                 'signature':signature(step,{'source':context.get('source_identity'),
                     'dependencies':{d:by_id[d].get('output_sha256',{}) for d in step.dependencies}}), 'output_sha256':{}}
            rows.append(row);by_id[step.id]=row
            failed=[i for i in step.dependencies if by_id[i]['status'] not in GOOD]
            missing=[i for i in step.requires if not Path(i).exists()]
            if failed:
                row.update(status='BLOCKED',detail='Prerequisites did not pass: '+', '.join(failed))
            elif missing:
                row.update(status='MISSING',detail='Required paths missing: '+'; '.join(missing))
            else:
                old=prior.get(step.id,{})
                if old.get('status') in GOOD and old.get('signature')==row['signature']:
                    try:
                        current=output_hashes(step.products)
                        if current != old.get('output_sha256'):
                            raise ValueError('Recorded outputs changed')
                        # Checks must be repeated; generation may be reused only with verified outputs.
                        if step.role == 'generation' and step.products:
                            row.update(status='REUSED',detail='Matching source/plan and output hashes',output_sha256=current)
                    except (OSError,ValueError):pass
                if row['status']!='REUSED':
                    # Never rerun into partial outputs: preserve them as previous attempts.
                    for product in step.products:
                        target=Path(product)
                        if target.exists() and target.is_relative_to(root):
                            olddir=root/'previous_attempts'/f'{step.id}-{time.time_ns()}'
                            olddir.mkdir(parents=True,exist_ok=True)
                            target.rename(olddir/target.name)
                    log_name=f'logs/{index:03d}_{step.id}_{time.time_ns()}.log'
                    row.update(status='RUNNING',log=log_name)
                    print(f'[{index}/{len(steps)}] {step.id}',flush=True)
                    report(root,rows,context)
                    start=time.monotonic()
                    try:
                        with (root/log_name).open('w',encoding='utf-8') as log:
                            log.write(json.dumps(step.command)+'\n');log.flush()
                            code=run_child(step.command,log,cwd,env,timeout_s)
                        row['exit_code']=code
                        if code==0:
                            row.update(status='PASS',output_sha256=output_hashes(step.products),detail='Completed; required outputs present')
                        else:
                            row.update(status='MISSING' if code==3 else 'FAIL',detail=f'Exit {code}; see log')
                    except subprocess.TimeoutExpired:
                        row.update(status='TIMEOUT',detail=f'Exceeded per-step timeout {timeout_s:g} s; process tree stopped')
                    except KeyboardInterrupt:
                        row.update(status='INTERRUPTED',detail='Interrupted by user; child process tree stopped')
                        interrupted=True
                    except Exception as exc:
                        row.update(status='FAIL',detail=f'{type(exc).__name__}: {exc}')
                    finally:row['elapsed_s']=time.monotonic()-start
            print(f'  {row["status"]}: {row["detail"]}',flush=True)
            report(root,rows,context)
            if interrupted:break
    finally:
        for step in steps[len(rows):]:
            rows.append({'id':step.id,'group':step.group,'role':step.role,'status':'NOT_RUN',
                         'detail':'Not reached after interruption','elapsed_s':0.})
        result=report(root,rows,context)
    return result
