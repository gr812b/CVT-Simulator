"""One process per Results step: study-local modules never collide across studies."""
from __future__ import annotations
import argparse
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import traceback

RELEASE=Path(__file__).resolve().parents[1]
if str(RELEASE) not in sys.path:sys.path.insert(0,str(RELEASE))
from results_health.common import (MissingEvidence,read_json,write_json,require_complete,
                                   digest,verify_current_ballew_execution)
from results_health import MECHANICS_COMMIT


def module(study, filename='run.py'):
    root=RELEASE/'studies'/study
    # Match direct script execution as well as package-relative imports. Some
    # existing study scripts import a sibling by its filename.
    sys.path[:0]=[str((root/filename).parent),str(root),str(RELEASE)]
    name=filename.removesuffix('.py').replace('/','.')
    return importlib.import_module(name)


def invoke(study, filename, args, overrides=None):
    m=module(study,filename)
    for key,value in (overrides or {}).items():
        if key not in {'ARTIFACTS','CACHE'}:raise ValueError('Unsupported output override: '+key)
        setattr(m,key,Path(value))
    sys.argv=[str(RELEASE/'studies'/study/filename),*map(str,args)]
    result=m.main()
    if isinstance(result,int) and result!=0:raise RuntimeError(f'{study}/{filename}: returned {result}')
    return result


def action(spec):
    kind=spec['action'];p=spec.get('parameters',{});out=Path(spec['report'])
    if kind=='environment':
        subprocess.run([sys.executable,str(RELEASE/'verify_environment.py')],check=True)
        import cinder
        return {'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
                'cinder_path':str(Path(cinder.__file__).resolve()),
                'packages':{n:importlib.metadata.version(n) for n in ('cinder-cvt','numpy','scipy','matplotlib')},
                'simulator_source_commit':MECHANICS_COMMIT}
    if kind=='module':
        result=invoke(p['study'],p.get('file','run.py'),p.get('arguments',[]),p.get('overrides'))
        return {'module':p['study']+'/'+p.get('file','run.py'),'returned_successfully':True,
                'note':p.get('note','The generating module succeeded; separate health steps still apply.')}
    if kind=='ballew-one':
        m=module('ballew-2015')
        from infrastructure.benchmark.reference import validate_reference_data
        target=Path(p['directory']);target.mkdir(parents=True,exist_ok=True)
        args=argparse.Namespace(rtol=p.get('rtol'),atol=p.get('atol'),
                               max_step=p.get('max_step'),maximum_transitions=p.get('maximum_transitions'))
        data=m._run_protocol(protocol=p['protocol'],spec=read_json(m.STUDY_FILE),
             reference_dir=validate_reference_data(study_root=m.STUDY_ROOT),
             make_plots=False,args=args,output_dir=target)
        require_complete(data['completed'],data['final_time_s'],5.,label=p['protocol'])
        mass=read_json(target/'resolved_belt_mass.json')
        if abs(mass['mass_kg']-1.)>2e-12:raise ValueError('Resolved Ballew belt mass is not 1 kg')
        verify_current_ballew_execution(m.STUDY_ROOT,target)
        return {'completed':True,'resolved_belt':mass,'slip_accounting':read_json(target/'slip_accounting.json')}
    if kind=='ballew-collect':
        root=Path(p['directory']);rows=[]
        for label,folder in [('nominal_1p00ms','closed-loop'),('nominal_0p50ms','convergence/nominal_0p50ms'),
                             ('nominal_0p25ms','convergence/nominal_0p25ms'),('tight_0p50ms','convergence/tight_0p50ms')]:
            d=read_json(root/folder/'metrics.json');require_complete(d['completed'],d['final_time_s'],5.,label=label)
            s=d['solver']
            expected={'nominal_1p00ms':(1e-7,1e-9,.001),'nominal_0p50ms':(1e-7,1e-9,.0005),
                      'nominal_0p25ms':(1e-7,1e-9,.00025),'tight_0p50ms':(3e-8,3e-10,.0005)}[label]
            if (s['relative_tolerance'],s['absolute_tolerance'],s['max_step_s']) != expected:
                raise ValueError('Refinement labels do not match executed settings: '+label)
            row={'label':label,'rtol':s['relative_tolerance'],'atol':s['absolute_tolerance'],
                 'max_step_s':s['max_step_s'],'completed':True,'termination_reason':d['termination_reason'],
                 'transition_count':d['transition_count'],'segment_count':d['segment_count'],'artifact_path':folder}
            row.update({key+'_rmse':value['root_mean_square_error'] for key,value in d['metrics'].items()})
            rows.append(row)
        value={'cinder_version':'1.1.2','cases':rows};write_json(root/'convergence/convergence.json',value)
        return value
    if kind=='ballew-health':
        root=Path(p['directory']);a=read_json(root/'evidence_audit.json')
        if not a.get('all_five_runs_completed'):raise ValueError('Benchmark publication audit did not pass all five runs')
        paths=['closed-loop','force-replay','convergence/nominal_0p50ms','convergence/nominal_0p25ms','convergence/tight_0p50ms']
        checks={}
        for name in paths:
            verify_current_ballew_execution(RELEASE/'studies/ballew-2015',root/name)
            mass=read_json(root/name/'resolved_belt_mass.json')
            if abs(mass['mass_kg']-1.)>2e-12:raise ValueError('Wrong mass: '+name)
            checks[name]={'mass':mass,'slip':read_json(root/name/'slip_accounting.json')}
        return {'five_corrected_runs_verified':True,'runs':checks,
                'conclusions_unchanged':'not automatically asserted; compare corrected values with the manuscript'}
    if kind=='mechanical-health':
        m=module('mechanical-invariants')
        directory=Path(p['directory'])
        if not directory.is_dir():raise MissingEvidence('Mechanical audit directory absent: '+str(directory))
        destination=Path(p['destination']);destination.mkdir(parents=True,exist_ok=True)
        evidence=m.reader_evidence(directory,destination,m.core)
        return {'checked':True,'run_id':evidence['run_id'],'metrics':evidence['metrics'],
                'counts':evidence['counts_for_reproduction_only']}
    if kind=='primary-health':
        from results_health.audits import check_primary
        return check_primary(Path(p['directory']),p.get('raw'))
    if kind=='belt-check':
        from results_health.audits import import_compact
        from results_health.belt import BUNDLE_FILES,bind_existing_bundle,check_publication
        src=Path(p['directory']);dst=Path(p['destination'])
        import_compact(src,dst,BUNDLE_FILES)
        if (src/'publication_manifest.json').is_file():
            import shutil;shutil.copy2(src/'publication_manifest.json',dst/'publication_manifest.json')
        else:bind_existing_bundle(dst)
        raw=Path(p.get('raw') or RELEASE/'studies/reduced-belt-transients/artifacts/publication')
        return check_publication(dst,raw,RELEASE/'studies/reduced-belt-transients/publication_inputs/runtime_source_check.json')
    if kind=='copy-inputs':
        from results_health.audits import import_compact
        import_compact(Path(p['source']),Path(p['destination']),p['names'])
        return {'copied':p['names'],'source':p['source'],'source_hashes':{name:digest(Path(p['source'])/name) for name in p['names']}}
    if kind=='course-health':
        module('course-tuning')  # Resolve its existing integrity/selection helpers.
        from results_health.audits import check_course
        directory=p.get('directory')
        if not directory:
            pointer=Path(p['pointer'])
            if not pointer.is_file():raise MissingEvidence('Provide course_suite in --paths; no selected-suite pointer at '+str(pointer))
            directory=pointer.read_text(encoding='utf-8-sig').strip()
        # Original re-analysis writes its detailed result even if it raises.
        result=check_course(Path(directory),out.with_name(out.stem+'_case_details.json'))
        return result
    if kind=='solver-completion':
        from results_health.audits import solver_completion
        return solver_completion(Path(p['directory']),out.with_name(out.stem+'_cache_details.json'))
    if kind=='artifact-note':
        return {'note':p['note'],'status':'recorded_not_a_scientific_pass'}
    raise ValueError('Unknown action: '+kind)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('spec',type=Path)
    args=parser.parse_args();spec=read_json(args.spec);out=Path(spec['report'])
    try:
        result=action(spec)
        write_json(out,{'status':'PASS','result':result})
        return 0
    except MissingEvidence as exc:
        write_json(out,{'status':'MISSING','error':str(exc)});print(str(exc),file=sys.stderr);return 3
    except SystemExit as exc:
        code=exc.code if isinstance(exc.code,int) else (0 if exc.code is None else 1)
        if code==0:
            write_json(out,{'status':'PASS','result':{'exit_code':0}});return 0
        write_json(out,{'status':'FAIL','error':str(exc)});raise
    except Exception as exc:
        write_json(out,{'status':'FAIL','error':f'{type(exc).__name__}: {exc}'})
        traceback.print_exc();return 1

if __name__=='__main__':raise SystemExit(main())
