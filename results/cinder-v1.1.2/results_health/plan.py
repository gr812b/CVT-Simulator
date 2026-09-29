"""Explicit manuscript study plan; no implicit launch of historical exploration campaigns."""
from pathlib import Path
from .common import read_json,write_json
from .engine import Step

GROUPS=('ballew','mechanical','energy','solver','closure','primary','secondary','belt','course')


def build_plan(release, output, interpreter, mode, paths=None, only=None, save=True):
    release=Path(release).resolve();output=Path(output).resolve();paths=paths or {}
    studies=release/'studies';selected=set(only or GROUPS)
    unknown=selected-set(GROUPS)
    if unknown:raise ValueError('Unknown studies: '+repr(sorted(unknown)))
    all_mode=mode=='all';steps=[]
    def location(key,default):
        return str(Path(paths[key]).expanduser().resolve()) if paths.get(key) else str(default)
    def task(id,group,action,parameters=None,*,deps=None,requires=(),products=(),role='generation',note=''):
        report=output/'checks'/f'{id}.json';specpath=output/'task_specs'/f'{id}.json'
        payload={'action':action,'parameters':parameters or {},'report':str(report)}
        if save:write_json(specpath,payload)
        step=Step(id,group,[str(interpreter),str(release/'results_health/worker.py'),str(specpath)],
                  list(deps if deps is not None else ['environment']),list(map(str,requires)),
                  [*map(str,products),str(report)],role,note)
        steps.append(step);return id
    def mod(id,group,study,file='run.py',args=(),overrides=None,**kwargs):
        return task(id,group,'module',{'study':study,'file':file,'arguments':list(map(str,args)),
                                      'overrides':overrides or {},'note':kwargs.get('note','')},**kwargs)
    task('environment','environment','environment',deps=[],role='preflight')
    # Tests are independent of scientific tasks: a failed code test is visible but
    # does not prevent gathering useful diagnostics from the other studies.
    testspec=output/'checks/code_tests.json'
    steps.append(Step('code-tests','environment',[str(interpreter),'-m','unittest','discover','-s',str(release/'results_health/tests'),'-v'],
                      ['environment'],[],[],role='health',note='Unit/regression tests; not a substitute for numerical study checks.'))

    if 'ballew' in selected:
        study=studies/'ballew-2015';raw=output/'data/ballew';prep=output/'prepared/ballew'
        if mode in ('correct','all'):
            inputs=mod('ballew-inputs','ballew','ballew-2015','verify_study.py',role='preflight')
            jobs=[]
            for id,protocol,folder,rtol,atol,cap in (
                ('replay','force_replay','force-replay',None,None,None),
                ('nominal','closed_loop','closed-loop',None,None,None),
                ('half-step','closed_loop','convergence/nominal_0p50ms',1e-7,1e-9,.0005),
                ('quarter-step','closed_loop','convergence/nominal_0p25ms',1e-7,1e-9,.00025),
                ('tight','closed_loop','convergence/tight_0p50ms',3e-8,3e-10,.0005)):
                directory=raw/folder
                jobs.append(task('ballew-'+id,'ballew','ballew-one',{
                    'protocol':protocol,'directory':str(directory),'rtol':rtol,'atol':atol,'max_step':cap,
                    'maximum_transitions':2000 if rtol else None},deps=[inputs],products=[directory]))
            collect=task('ballew-collect','ballew','ballew-collect',{'directory':str(raw)},deps=jobs,
                         products=[raw/'convergence/convergence.json'],role='analysis')
            prepare=mod('ballew-prepare','ballew','ballew-2015','analysis/publication_evidence.py',
                        ['--artifacts',raw,'--freeze-to',prep],deps=[collect],products=[prep,raw/'evidence_audit.json'],role='analysis')
            check=task('ballew-health','ballew','ballew-health',{'directory':str(raw)},deps=[prepare],role='health')
            mod('ballew-figures','ballew','ballew-2015','analysis/publication_plots.py',
                ['--input-dir',prep,'--output-dir',output/'figures/ballew'],deps=[check],products=[output/'figures/ballew'],role='export')
        else:
            raw=location('ballew_raw',study/'artifacts')
            task('ballew-health','ballew','ballew-health',{'directory':raw},requires=[raw],role='health',
                 note='Requires corrected raw evidence; old 0.973 kg results are not accepted as corrected runs.')

    if 'mechanical' in selected:
        directory=Path(location('mechanical_artifacts',studies/'mechanical-invariants/artifacts'))
        deps=['environment']
        if all_mode:
            directory=output/'data/mechanical'
            deps=[mod('mechanical-generate','mechanical','mechanical-invariants',args=['--artifacts-dir',directory,'--figure-dir',output/'figures/mechanical'],products=[directory,output/'figures/mechanical'])]
        task('mechanical-health','mechanical','mechanical-health',{'directory':str(directory),'destination':str(output/'prepared/mechanical')},
             deps=deps,requires=[directory],products=[output/'prepared/mechanical'],role='health')

    if 'energy' in selected:
        directory=Path(location('energy_artifacts',studies/'energy-consistency/artifacts'));deps=['environment']
        if all_mode:
            directory=output/'data/energy'
            deps=[mod('energy-generate','energy','energy-consistency',args=['--no-plots'],overrides={'ARTIFACTS':str(directory)},products=[directory])]
        mod('energy-health','energy','energy-consistency',args=['--plot-only','--publication-dir',output/'figures/energy'],
            overrides={'ARTIFACTS':str(directory)},deps=deps,requires=[directory],products=[output/'figures/energy'],role='health')

    if 'solver' in selected:
        retained=Path(location('solver_artifacts',studies/'solver-convergence/artifacts'))
        cache=Path(location('solver_cache',studies/'solver-convergence/work/cache'));deps=['environment']
        if all_mode:
            core=output/'data/solver';cache=core/'cache'
            deps=[mod('solver-core','solver','solver-convergence',overrides={'ARTIFACTS':str(core),'CACHE':str(cache)},products=[core],
                      note='New formal core sweep; does not replace the archived dense-population search.')]
        task('solver-completion','solver','solver-completion',{'directory':str(cache)},deps=deps,requires=[cache],role='health')
        mod('solver-retained-publication','solver','solver-convergence',args=['--plot-only','--publication-dir',output/'figures/solver'],
            overrides={'ARTIFACTS':str(retained)},requires=[retained],products=[output/'figures/solver'],role='health',
            note='Independently checks retained publication evidence, including its selected dense-search example.')

    if 'closure' in selected:
        retained=Path(location('closure_artifacts',studies/'closure-conditioning/artifacts/reviewed'))
        if all_mode:
            mod('closure-core','closure','closure-conditioning',args=['--core-output-dir',output/'data/closure-core'],products=[output/'data/closure-core'],
                note='New core maps/census; selected historical folded-branch evidence is checked separately.')
        mod('closure-retained-publication','closure','closure-conditioning',args=['--plot-only','--artifacts-dir',retained,'--figure-dir',output/'figures/closure'],
            requires=[retained],products=[output/'figures/closure'],role='health')

    actuator=studies/'actuator-dynamics';original=actuator/'publication_inputs';prepared=output/'prepared/actuator'
    primary_jobs=[];primary_prepare=None
    # In all mode a requested secondary regeneration needs its full primary launch.
    if 'primary' in selected or ('secondary' in selected and all_mode):
        if all_mode:
            raw=output/'data/primary'
            for kind in ('baseline','transient'):
                for level in ('nominal','tight'):
                    for variant in ('full','qs'):
                        name=f'{kind}_{level}_{variant}'
                        primary_jobs.append(mod('primary-'+name,'primary','actuator-dynamics','experiments/run_primary_publication.py',
                            ['--kind',kind,'--level',level,'--variant',variant,'--output-dir',raw],products=[raw/name]))
            primary_prepare=mod('primary-prepare','primary','actuator-dynamics','analysis/prepare_primary_publication.py',
                ['--raw-dir',raw,'--output-dir',prepared],deps=primary_jobs,
                products=[prepared/'primary_publication.npz',prepared/'primary_publication_audit.json'],role='analysis')
            directory=prepared;deps=[primary_prepare]
        else:
            directory=Path(location('primary_inputs',original));raw=Path(location('primary_raw',actuator/'artifacts/primary-publication'));deps=['environment']
        task('primary-health','primary','primary-health',{'directory':str(directory),'raw':str(raw)},
             deps=deps,requires=[directory],role='health')

    if 'secondary' in selected:
        deps=['environment'];directory=Path(location('secondary_inputs',original))
        if all_mode:
            raw=output/'data/secondary';back=output/'data/backshift';jobs=[]
            archive=task('secondary-archived-reference','secondary','copy-inputs',{'source':str(original),'destination':str(prepared),
                'names':['secondary_archive_audit.json']},requires=[original/'secondary_archive_audit.json'],
                products=[prepared/'secondary_archive_audit.json'],role='analysis')
            for kind in ('commercial','severe','stock'):
                for level in ('nominal','tight'):
                    for variant in ('full','qs'):
                        name=f'{kind}_nominal_{level}_{variant}'+('_stick' if kind!='commercial' else '')
                        args=['--kind',kind,'--level',level,'--variant',variant,'--output-dir',raw]
                        if kind!='commercial':args.append('--sticking-start')
                        jobs.append(mod('secondary-'+name,'secondary','actuator-dynamics','experiments/run_secondary_publication.py',args,products=[raw/name]))
            prepare=mod('secondary-prepare','secondary','actuator-dynamics','analysis/prepare_secondary_publication.py',
                ['--raw-dir',raw,'--output-dir',prepared],deps=[archive,*jobs],
                products=[prepared/'secondary_publication.npz',prepared/'secondary_publication_audit.json'],role='analysis')
            jobs=[]
            for torque in (0,-120,-240,-480):
                for level in ('nominal','tight'):
                    for variant in ('full','qs'):
                        name=f'm{abs(torque)}_{level}'+('_qs' if variant=='qs' else '')
                        jobs.append(mod('backshift-'+name,'secondary','actuator-dynamics','experiments/run_secondary_backshift.py',
                            ['--torque',torque,'--level',level,'--variant',variant,'--output-dir',back],products=[back/name]))
            story=mod('secondary-story','secondary','actuator-dynamics','analysis/prepare_secondary_story.py',
                ['--primary-dir',output/'data/primary','--backshift-dir',back,'--output-dir',prepared],
                deps=[*jobs,primary_prepare],products=[prepared/'secondary_story.npz',prepared/'secondary_story_audit.json'],role='analysis')
            directory=prepared;deps=[prepare,story]
        mod('secondary-health','secondary','actuator-dynamics','analysis/check_secondary_publication.py',
            ['--input-dir',directory,'--output',output/'prepared/secondary_health_details.json'],deps=deps,
            requires=[directory],products=[output/'prepared/secondary_health_details.json'],role='health',
            note='Checks known outgoing inadmissibility as an explicitly masked limitation, not as a valid post-slip trajectory.')

    if 'belt' in selected:
        study=studies/'reduced-belt-transients';inputs=Path(location('belt_inputs',study/'publication_inputs'))
        raw=Path(location('belt_raw',study/'artifacts/publication'));deps=['environment']
        if all_mode:
            raw=output/'data/belt';inputs=output/'prepared/belt-generated';jobs=[]
            for job in read_json(study/'publication_inputs/run_plan.json'):
                name='{case}_{level}_{variant}'.format(**job)
                jobs.append(mod('belt-'+name,'belt','reduced-belt-transients',
                    args=['--publication','run','--publication-case',job['case'],'--publication-variant',job['variant'],
                          '--publication-level',job['level'],'--publication-dir',raw],products=[raw/name]))
            deps=[mod('belt-prepare','belt','reduced-belt-transients',args=['--publication','prepare','--publication-dir',raw,'--publication-inputs',inputs],
                      deps=jobs,products=[inputs],role='analysis')]
        task('belt-health','belt','belt-check',{'directory':str(inputs),'destination':str(output/'prepared/belt-checked'),'raw':str(raw)},
             deps=deps,requires=[inputs],products=[output/'prepared/belt-checked'],role='health')

    if 'course' in selected:
        root=Path(location('course_output_root',studies/'course-tuning/artifacts'));deps=['environment']
        directory=paths.get('course_suite')
        if all_mode:
            root=output/'data/course';directory=None
            deps=[mod('course-generate','course','course-tuning',args=['--jobs','1','--no-plots','--output-root',root],products=[root],
                note='15 existing selected cases. A rollback or documented progress stop is not a numerical failure.')]
        task('course-health','course','course-health',{'directory':directory,'pointer':str(root/'latest_final.txt')},deps=deps,role='health',
             note='Checks every case and applicable event side; exact manuscript composite generation remains F03.')
    return steps
