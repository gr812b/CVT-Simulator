"""One portable report for the selected common-course and supporting flat runs."""
from __future__ import annotations
import argparse
import html
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from infrastructure.common import load_json,read_csv,write_json,write_csv,digest,utc_now,finite
from infrastructure.course import Course
from infrastructure.selection import reusable_case,ERROR_STATUSES
from analysis.report import build_report,table,plot_lines,configure_palette
from analysis.final_course_checks import build_report as build_checks


def discussion_figures(folder:Path,plan:dict) -> list[dict]:
    """Named comparisons only; this changes no case or source measurement."""
    campaign=load_json(folder/'campaign.json');course=Course(campaign['course'])
    configure_palette(campaign)
    data={d.name:read_csv(d/'diagnostics.csv') for d in (folder/'cases').iterdir() if (d/'diagnostics.csv').is_file()}
    items=[]
    fields=[('speed_m_s','Vehicle speed [m/s]'),('primary_rpm','Primary speed [rpm]'),
            ('shift_mm','Shift coordinate [mm]'),('primary_static_utilization','Primary |lambda| / mu_static')]
    for group in plan['groups']:
        sectors=[s for s in course.sectors if s.name in group['sectors']]
        lo,hi=(sectors[0].start_m,sectors[-1].end_m) if sectors else (0.,course.finish_m)
        series=[(car,[r for r in data.get(car,[]) if lo<=float(r['distance_m'])<=hi]) for car in group['cars']]
        series=[(car,rows) for car,rows in series if rows]
        if not series:continue
        images=[]
        for key,label in fields:
            p=folder/'figures'/'comparisons'/group['id']/(key+'.png')
            plot_lines(p,series,'distance_m',key,'Distance along road [m]',label,group['title'])
            images.append(p.relative_to(folder).as_posix())
        items.append({**group,'images':images,'range_m':[lo,hi]})
    return items


def inventory_status(output:Path,manifest:dict) -> tuple[list[dict],dict]:
    rows=[]
    for key in manifest['expected_cases']:
        group,car=key.split('/');folder=output/group/'cases'/car
        status=load_json(folder/'status.json') if (folder/'status.json').is_file() else {}
        summary=load_json(folder/'summary.json') if (folder/'summary.json').is_file() else {}
        campaign=load_json(output/group/'campaign.json')
        tune=next(t for t in campaign['competitors'] if t['id']==car)
        fp=digest({'suite':manifest['fingerprint'],'case':key,'tune':tune})
        intact=reusable_case(folder,fp)
        rows.append({'experiment':group,'case':car,'case_key':key,
            'output_complete_and_hash_verified':intact,
            'status':status.get('status','not_run'),'review_required':summary.get('review_required',False),
            'finish_time_s':summary.get('finish_time_s'),
            'max_distance_m':summary.get('max_distance_m'),
            'reason':summary.get('reason',''),
            'inspection_errors':summary.get('inspection_errors'),
            'integration_wall_s':summary.get('integration_wall_s'),
            'setup_wall_s':summary.get('setup_wall_s'),
            'postprocess_wall_s':summary.get('postprocess_wall_s')})
    complete=all(r['output_complete_and_hash_verified'] for r in rows)
    errors=[r['case_key'] for r in rows if r['status'] in ERROR_STATUSES]
    review=[r['case_key'] for r in rows if r['review_required'] or r['status']=='model_domain_stop']
    ready=complete and not errors and not review
    return rows,{'dataset_status':('complete' if ready else 'complete_with_review_flags' if complete else 'incomplete'),
        'ready_for_review':ready,'all_expected_outputs_present':complete,
        'completed_output_count':sum(r['output_complete_and_hash_verified'] for r in rows),
        'expected_count':len(rows),'error_cases':errors,'review_cases':review,
        'is_smoke_test':manifest['smoke'],'frozen_environment_match':manifest['environment']['frozen_environment_match'],
        'ready_for_frozen_manuscript_review':ready and not manifest['smoke'] and manifest['environment']['frozen_environment_match'],
        'meaning':'Dataset completion counts documented observed non-finishers, not just course finishes. No expected trajectory or winner is enforced.',
        'generated_utc':utc_now()}


def build_final_report(output:Path,plots:bool=True) -> dict:
    output=Path(output).resolve();manifest=load_json(output/'suite.json')
    comparisons=[]
    for g in manifest['experiments']:
        folder=output/g['id']
        build_report(folder,focus=g['cars'],plots=plots)
        if g['id']=='unified_course':
            build_checks(folder,criteria=manifest['settling_criteria'],plots=plots)
            from analysis.shape_report import build_shape_report
            build_shape_report(folder,plots=plots)
            if plots:comparisons=discussion_figures(folder,manifest['comparison_groups'])
        page=folder/'index.html';body=page.read_text(encoding='utf-8')
        if '<!-- final-suite-nav -->' not in body:
            body=body.replace('<body>','<body><!-- final-suite-nav --><p><a href="../index.html"><b>All selected results</b></a></p>',1)
            page.write_text(body,encoding='utf-8')
    rows,status=inventory_status(output,manifest)
    dest=output/'tables';dest.mkdir(exist_ok=True)
    write_csv(dest/'case_inventory.csv',rows)
    # Keep the schema / values emitted by each existing analysis, simply add an experiment identifier.
    sources={'outcomes.csv':'leaderboard.csv','sector_comparison.csv':'sector_comparison.csv',
             'feature_metrics.csv':'feature_metrics.csv','cyclic_cycle_metrics.csv':'cyclic_cycle_metrics.csv',
             'settling_summary.csv':'final_checks/settling_summary.csv','competitors_resolved.csv':'competitors_resolved.csv',
             'shift_shape_metrics.csv':'shift_shape_metrics.csv'}
    for name,relative in sources.items():
        combined=[]
        for g in manifest['experiments']:
            file=output/g['id']/relative
            if file.exists():combined += [{'experiment':g['id'],**r} for r in read_csv(file)]
        write_csv(dest/name,combined)
    events=[]
    for row in rows:
        p=output/row['experiment']/'cases'/row['case']/'events.json'
        if p.is_file():events += [{'experiment':row['experiment'],'case':row['case'],**e} for e in load_json(p)]
    write_csv(dest/'events.csv',events)
    write_json(output/'completion.json',status)
    warning=''
    if manifest['smoke']:warning+='<p class="warning">SMOKE TEST ONLY: three simulated seconds, two entrants. Not the final study.</p>'
    if not status['frozen_environment_match']:warning+='<p class="warning">Dependency environment differs from the frozen Results environment. This archive records a diagnostic run, not the frozen manuscript run.</p>'
    if not status['ready_for_review']:warning+='<p class="warning">Missing, incomplete, or flagged outputs remain. See the inventory; do not silently omit those cases.</p>'
    nav=''
    for g in manifest['experiments']:
        nav+=f'<h2>{html.escape(g["title"])}</h2><p><a href="{g["id"]}/index.html">Course, vehicle and mechanical plots</a> · <a href="{g["id"]}/shift_curves.html">All shift curves</a>'
        if g['id']=='unified_course':nav+=' · <a href="unified_course/final_checks/index.html">Interior settling, cycle-by-cycle and failure chronology</a> · <a href="unified_course/shift_shape.html">Selected shift-curve shape comparisons</a>'
        nav+='</p>'
    comparison_html=''
    for group in comparisons:
        links=''.join(f'<a href="unified_course/{p}"><img loading="lazy" src="unified_course/{p}"></a>' for p in group['images'])
        comparison_html+=f'<details><summary>{html.escape(group["title"])} — {", ".join(group["cars"])}</summary>{links}</details>'
    carlinks=[]
    for row in rows:
        folder=f'{row["experiment"]}/cases/{row["case"]}'
        links=[]
        for name in ('diagnostics.csv','events.csv','resolved_case.json','summary.json','execution.log'):
            if (output/folder/name).exists():links.append(f'<a href="{folder}/{name}">{name}</a>')
        carlinks.append(f'<p><b>{row["case_key"]}</b>: '+ ' · '.join(links)+'</p>')
    text=f'''<!doctype html><html><head><meta charset="utf-8"><title>CINDER — selected course study</title>
<style>body{{font:15px system-ui,sans-serif;max-width:1450px;margin:2rem}}p{{line-height:1.55}}table{{border-collapse:collapse;display:block;overflow:auto}}th,td{{padding:.45rem;border:1px solid #bbb;text-align:left}}img{{max-width:100%;margin:1rem 0}}summary{{font-weight:bold;cursor:pointer;padding:1rem}}.warning{{border:2px solid #b45a00;padding:1rem}}code{{overflow-wrap:anywhere}}</style></head><body>
<h1>CINDER: coupled vehicle operation and tuning</h1>
<p>Selected final case set, not an optimization or experimental validation. The selected configurations share one 732 m road, full throttle, initial conditions, dynamic flyweights and a bilateral dynamic helix. The separate 800 m flat compares R00 and U55. No exploratory campaigns are included.</p>
{warning}<p><b>Dataset: {status['dataset_status']} — {status['completed_output_count']} / {status['expected_count']} outputs.</b> A documented rollback or slow-progress stop counts as an observed output, not as a numerical error.</p>
<p>Selection: {manifest['selection_revision']} · fingerprint <code>{manifest['fingerprint']}</code>.</p>
{nav}<h2>Recorded outcomes and completeness</h2>{table(rows,['experiment','case','status','output_complete_and_hash_verified','review_required','finish_time_s','max_distance_m'])}
<h2>Event-focused comparisons</h2>{comparison_html if plots else '<p>Image generation deferred. Rebuild this report without --no-plots.</p>'}
<h2>Consolidated tables</h2><p>{' · '.join(f'<a href="tables/{p.name}">{p.name}</a>' for p in sorted(dest.glob('*.csv')))}</p>
<h2>Individual records</h2>{''.join(carlinks)}
<h2>Interpretation and reproducibility</h2>
<p>The full-throttle engine map retains its extrapolated overspeed-resisting tail. Cyclic terrain is longitudinal road grade, not suspension or wheel-lift dynamics. Slip work is sampled diagnostic energy, not a complete physical loss model. Hill settling is a finite-window observation, not a proof of stability.</p>
<p>Source and exact inputs: <a href="suite.json">suite manifest</a> · <a href="completion.json">completion/review status</a> · <a href="provenance/study/README.md">run instructions</a> · <a href="tables/events.csv">combined event record</a>.</p>
</body></html>'''
    (output/'index.html').write_text(text,encoding='utf-8')
    artifacts=sorted(p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file() and 'previous_attempts' not in p.relative_to(output).parts and p.name!='RUNNING.lock')
    write_json(output/'artifact_index.json',{'generated_utc':utc_now(),'files':artifacts})
    return status


def pack_results(output:Path) -> Path:
    """Archive the entire current dataset, not the exploratory workspace or old attempts."""
    output=Path(output).resolve()
    if not (output/'suite.json').is_file():raise ValueError('Expected a final-results folder containing suite.json')
    archive=output.with_name(output.name+'_return.zip');tmp=archive.with_suffix('.zip.tmp')
    try:
        with ZipFile(tmp,'w',compression=ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(output.rglob('*')):
                if not p.is_file():continue
                rel=p.relative_to(output)
                if any(x in rel.parts for x in ('previous_attempts','__pycache__','.pytest_cache')) or p.name=='RUNNING.lock':continue
                z.write(p,Path(output.name)/rel)
        tmp.replace(archive)
    finally:
        tmp.unlink(missing_ok=True)
    return archive


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path,help='Final suite folder containing suite.json')
    p.add_argument('--no-plots',action='store_true');p.add_argument('--pack',action='store_true')
    a=p.parse_args();s=build_final_report(a.output,plots=not a.no_plots)
    print(a.output/'index.html')
    if a.pack:print(pack_results(a.output))
    return 0 if s['ready_for_review'] else 2

if __name__=='__main__':raise SystemExit(main())
