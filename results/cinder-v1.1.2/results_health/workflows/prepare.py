#!/usr/bin/env python3
"""Reprepare completed Results, audit them and smoke-test the existing exporters.

No CVT integrations. Old numerical runs and manuscript assets are never edited.
One failed/missing task blocks only its dependents; an end-of-run report is saved.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

RELEASE = Path(__file__).resolve().parents[2]
REPO = RELEASE.parents[1]
sys.path.insert(0, str(RELEASE))
from results_health.common import digest, read_json, write_json
from results_health.engine import Step, run_plan, report
from results_health.workflows.run import source_inventory, interpreter, package_summary

GROUPS = ('primary', 'secondary', 'belt', 'course', 'retained', 'ballew')


def build_prep_plan(root, source_run, ballew_run, exe, paths, *, only=None, fetch_lfs=False,
                    exports=True, save=True):
    root, source_run = Path(root), Path(source_run)
    selected = set(only or GROUPS)
    if 'secondary' in selected:
        # Its launch source needs raw full-primary evidence, NOT the old screen.
        selected.add('primary_raw')
    worker = RELEASE/'results_health/preparation_worker.py'
    old_worker = RELEASE/'results_health/worker.py'
    steps = []
    def task(id, group, action, parameters=None, *, deps=None, requires=(), products=(), role='analysis', legacy=False):
        check = root/'checks'/(id+'.json')
        spec = root/'task_specs'/(id+'.json')
        if save:
            write_json(spec, {'action': action, 'parameters': parameters or {}, 'report': str(check)})
        steps.append(Step(id, group, [str(exe), str(old_worker if legacy else worker), str(spec)],
                          list(['environment'] if deps is None else deps), list(map(str, requires)),
                          [*map(str, products), str(check)], role))
        return id
    task('environment', 'environment', 'environment', deps=[], role='preflight', legacy=True)
    steps.append(Step('prep-code-tests', 'environment', [str(exe), '-m', 'unittest', 'discover', '-s',
        str(RELEASE/'results_health/tests'), '-v'], ['environment'], role='health'))
    def integrity(id, group, relative, producer):
        return task(id, group, 'integrity', {'run': str(source_run), 'relative': relative, 'producer': producer},
                    requires=[source_run/'health_report.json'], role='health')
    actuator = root/'prepared/actuator'
    primary_verified = None
    if selected & {'primary', 'primary_raw'}:
        primary_verified = integrity('primary-raw-integrity', 'primary', 'data/primary', 'primary-')
    if 'primary' in selected:
        screen = root/'inputs/primary_screen.csv'
        screen_id = task('primary-screen-data', 'primary', 'primary-screen', {
            'source': str(paths.get('primary_screen', RELEASE/'studies/actuator-dynamics/publication_inputs/primary_screen.csv')),
            'target': str(screen), 'fetch_lfs': fetch_lfs}, products=[screen])
        prepare = task('primary-prepare', 'primary', 'primary-prepare', {
            'raw': str(source_run/'data/primary'), 'output': str(actuator), 'screen': str(screen)},
            deps=[primary_verified, screen_id], products=[actuator/'primary_publication.npz', actuator/'primary_publication_audit.json'])
        health = task('primary-health', 'primary', 'primary-health', {
            'inputs': str(actuator), 'raw': str(source_run/'data/primary')}, deps=[prepare], role='health')
        if exports:
            task('primary-export-smoke', 'primary', 'primary-export', {'inputs': str(actuator), 'figures': str(root/'figures/primary')},
                 deps=[health], products=[root/'figures/primary'], role='export')
    if 'secondary' in selected:
        raw_check = integrity('secondary-raw-integrity', 'secondary', 'data/secondary', 'secondary-')
        back_check = integrity('backshift-raw-integrity', 'secondary', 'data/backshift', 'backshift-')
        archive_check = integrity('secondary-retained-audit-integrity', 'secondary', 'prepared/actuator', 'secondary-')
        archived = task('secondary-archive-copy', 'secondary', 'secondary-archive', {
            'source': str(source_run/'prepared/actuator/secondary_archive_audit.json'),
            'target': str(actuator/'secondary_archive_audit.json')}, deps=[archive_check],
            products=[actuator/'secondary_archive_audit.json'])
        prep = task('secondary-prepare', 'secondary', 'secondary-prepare', {
            'raw': str(source_run/'data/secondary'), 'output': str(actuator)}, deps=[raw_check, archived],
            products=[actuator/'secondary_publication.npz', actuator/'secondary_publication_audit.json'])
        story = task('secondary-story', 'secondary', 'secondary-story', {
            'primary_raw': str(source_run/'data/primary'), 'backshift_raw': str(source_run/'data/backshift'),
            'output': str(actuator)}, deps=[primary_verified, back_check],
            products=[actuator/'secondary_story.npz', actuator/'secondary_story_audit.json'])
        details = root/'checks/secondary_publication_details.json'
        health = task('secondary-health', 'secondary', 'secondary-health', {
            'inputs': str(actuator), 'details': str(details)}, deps=[prep, story], products=[details], role='health')
        if exports:
            task('secondary-export-smoke', 'secondary', 'secondary-export', {
                'inputs': str(actuator), 'figures': str(root/'figures/secondary')}, deps=[health],
                products=[root/'figures/secondary'], role='export')
    if 'belt' in selected:
        integrity_id = integrity('belt-raw-integrity', 'belt', 'data/belt', 'belt-')
        inputs = root/'prepared/belt'
        prep = task('belt-prepare', 'belt', 'belt-prepare', {'raw': str(source_run/'data/belt'), 'inputs': str(inputs)},
                    deps=[integrity_id], products=[inputs])
        health = task('belt-health', 'belt', 'belt-health', {'raw': str(source_run/'data/belt'), 'inputs': str(inputs)},
                      deps=[prep], role='health')
        if exports:
            task('belt-export-smoke', 'belt', 'belt-export', {'raw': str(source_run/'data/belt'), 'inputs': str(inputs),
                'figures': str(root/'figures/belt')}, deps=[health], products=[root/'figures/belt'], role='export')
    if 'course' in selected:
        integrity_id = integrity('course-raw-integrity', 'course', 'data/course', 'course-generate')
        details = root/'checks/course_case_details.json'
        check = task('course-health', 'course', 'course-health', {'run': str(source_run), 'details': str(details),
             'inputs': str(root/'prepared/course')}, deps=[integrity_id],
             products=[details, root/'prepared/course/course_source.json'], role='health')
        target = root/'prepared/course'
        task('course-prepare', 'course', 'course-prepare', {'inputs': str(target), 'details': str(details)},
             deps=[check], products=[target/'course_plot_inputs.npz', target/'course_bundle.json',
                                    target/'suite.json', target/'course_health_audit.json', target/'cases'])
    if 'retained' in selected:
        for name, required, instructions in (
            ('solver', ['execution_provenance.json'],
             'Supply the reviewed evidence/artifacts directory via --paths solver_artifacts. '
             'Or recover artifacts(3).zip + dense-overnight.zip using the maintained --import-retained route; '
             'that explicitly replays the one missing selected trajectory and is not launched by this prep run.'),
            ('closure', ['execution_provenance.json', 'contour_audit'],
             'Supply the reviewed directory INCLUDING contour_audit via --paths closure_artifacts. '
             'See provenance/CONTOUR_REVISION_2026_09_25.md. The full_recomputed core is not the targeted fold evidence.')):
            default = RELEASE/('studies/solver-convergence/artifacts' if name == 'solver' else 'studies/closure-conditioning/artifacts/reviewed')
            directory = Path(paths.get(name+'_artifacts', default))
            probe = task(name+'-retained-inputs', 'retained', 'retained-probe', {
                'study': name, 'directory': str(directory), 'required': required,
                'details': str(root/'checks'/f'{name}_retained_requirements.json'),
                'instructions': instructions, 'core': str(source_run/'data'/('solver' if name == 'solver' else 'closure-core'))},
                products=[root/'checks'/f'{name}_retained_requirements.json'], role='health')
            if exports:
                task(name+'-retained-export', 'retained', name+'-export', {'directory': str(directory),
                    'figures': str(root/'figures'/name)}, deps=[probe], products=[root/'figures'/name], role='export')
    if 'ballew' in selected:
        if ballew_run is not None:
            task('ballew-register-accepted-run', 'ballew', 'ballew-register', {'run': str(ballew_run),
                 'inputs': str(root/'prepared/ballew')}, requires=[Path(ballew_run)/'health_report.json'],
                 products=[root/'prepared/ballew/ballew_source.json'], role='health')
        else:
            task('ballew-run-needed', 'ballew', 'retained-probe', {'study': 'ballew',
                'directory': str(root/'not_supplied/ballew'), 'required': ['health_report.json'],
                'details': str(root/'checks/ballew_run_needed.json'),
                'instructions': 'Provide the already-passed localized run using --ballew-run; do not reintegrate it.'},
                products=[root/'checks/ballew_run_needed.json'], role='health')
    return steps


def readiness(root, source_run, ballew_run, result, paths):
    state = {row['id']: row['status'] for row in result['steps']}
    good = {'PASS', 'REUSED'}
    def passed(name): return state.get(name) in good
    families = {
        'primary': {'ready': passed('primary-health'), 'inputs': str(root/'prepared/actuator'),
                    'exporter': 'studies/actuator-dynamics/analysis/primary_publication_plots.py'},
        'secondary': {'ready': passed('secondary-health'), 'inputs': str(root/'prepared/actuator'),
                      'exporter': 'studies/actuator-dynamics/analysis/secondary_publication_plots.py'},
        'belt': {'ready': passed('belt-health'), 'inputs': str(root/'prepared/belt'),
                 'exporter': 'studies/reduced-belt-transients/analysis/publication_plots.py'},
        'course': {'ready': passed('course-prepare'), 'inputs': str(root/'prepared/course/course_bundle.json'),
                   'exporter': None,
                   'remaining': 'Recover/register the nine exact paper composites; do not substitute restricted generic shift-shape plots.'},
        'solver': {'ready': passed('solver-retained-export'),
                   'inputs': str(paths.get('solver_artifacts', RELEASE/'studies/solver-convergence/artifacts')),
                   'exporter': 'studies/solver-convergence/run.py --plot-only'},
        'closure': {'ready': passed('closure-retained-export'),
                    'inputs': str(paths.get('closure_artifacts', RELEASE/'studies/closure-conditioning/artifacts/reviewed')),
                    'exporter': 'studies/closure-conditioning/run.py --plot-only'},
        'ballew': {'ready': passed('ballew-register-accepted-run'),
                   'inputs': str(Path(ballew_run)/'prepared/ballew') if ballew_run else None,
                   'exporter': 'studies/ballew-2015/analysis/publication_plots.py'},
    }
    value = {'schema': 1, 'original_all_run': str(source_run), 'new_preparation': str(root),
             'families': families, 'numeric_inputs_ready_for_requested_checks': result['all_requested_steps_passed'],
             'every_paper_figure_registered': False, 'figure_appearance_changed': False,
             'compression_performed': False, 'simulations_reexecuted': 0,
             'note': 'Prepared inputs retain their original simulation identities; new preparation/exports have separate hashes.'}
    write_json(root/'checks/figure_rerun_inputs.json', value)
    # Explicit evidence locations for the later figure-only workflow. Historical
    # Ballew identity is verified by ballew-register, not current-generator reuse.
    # Solver/closure keep missing paths instead of substituting new core outputs.
    config = {'primary_inputs': str(root/'prepared/actuator'), 'primary_raw': str(source_run/'data/primary'),
              'secondary_inputs': str(root/'prepared/actuator'), 'belt_inputs': str(root/'prepared/belt'),
              'belt_raw': str(source_run/'data/belt'),
              'solver_cache': str(source_run/'data/solver/cache'),
              'mechanical_artifacts': str(source_run/'data/mechanical'),
              'energy_artifacts': str(source_run/'data/energy')}
    for key in ('solver_artifacts', 'closure_artifacts'):
        if key in paths: config[key] = str(paths[key])
    if ballew_run: config['ballew_raw'] = str(Path(ballew_run)/'data/ballew')
    course = root/'prepared/course/course_source.json'
    if course.is_file(): config['course_suite'] = read_json(course)['suite']
    write_json(root/'figure_input_locations.json', {'locations': config,
        'not_a_generic_run_results_paths_file': True,
        'note': 'Historical accepted executions keep their own identity. Use these locations in the figure-only workflow, not as a request for current-generator cache reuse.'})
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--from-run', type=Path, required=True, help='Existing complete --mode all output directory; read only')
    parser.add_argument('--ballew-run', type=Path, help='Already-passed Ballew hotfix run; read only')
    parser.add_argument('--output', type=Path, help='New dedicated output under health_runs/ or outside the repository')
    parser.add_argument('--paths', type=Path, help='Optional JSON: primary_screen, solver_artifacts, closure_artifacts')
    parser.add_argument('--fetch-lfs', action='store_true', help='Allow a targeted git lfs fetch for the missing primary CSV; no checkout or working-tree changes')
    parser.add_argument('--only', nargs='+', choices=GROUPS)
    parser.add_argument('--skip-export-smoke', action='store_true', help='Prepare/check only; do not exercise plot exporters')
    parser.add_argument('--python', dest='python_path')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--step-timeout-hours', type=float, default=0.)
    args = parser.parse_args(argv)
    import math
    if not math.isfinite(args.step_timeout_hours) or args.step_timeout_hours < 0:
        parser.error('Invalid timeout')
    if args.resume and args.output is None: parser.error('--resume requires --output')
    source_run = args.from_run.expanduser().resolve()
    ballew_run = args.ballew_run.expanduser().resolve() if args.ballew_run else None
    paths = read_json(args.paths) if args.paths else {}
    if not isinstance(paths, dict) or set(paths)-{'primary_screen', 'solver_artifacts', 'closure_artifacts'}:
        parser.error('Unknown --paths keys')
    for key, raw in list(paths.items()):
        path = Path(raw).expanduser()
        paths[key] = path.resolve() if path.is_absolute() else (args.paths.resolve().parent/path).resolve()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root = (args.output or RELEASE/'health_runs'/('prep_'+stamp)).resolve()
    inputs = [source_run, *([ballew_run] if ballew_run else []), *paths.values()]
    if root in (REPO, RELEASE) or root in RELEASE.parents or any(root == p or p.is_relative_to(root) or root.is_relative_to(p) for p in inputs):
        parser.error('Output must be separate from every input run/evidence directory')
    if root.is_relative_to(REPO) and not root.is_relative_to(RELEASE/'health_runs'):
        parser.error('Inside the repository, use a new health_runs/ directory')
    exe = interpreter(args.python_path)
    if args.dry_run:
        steps = build_prep_plan(root, source_run, ballew_run, exe, paths, only=args.only,
                               fetch_lfs=args.fetch_lfs, exports=not args.skip_export_smoke, save=False)
        print(f'{len(steps)} preparation/check/export steps; ZERO integrations. Output: {root}')
        for step in steps: print(step.id, step.role, 'after', ', '.join(step.dependencies))
        return 0
    if root.exists() and any(root.iterdir()) and not args.resume:
        parser.error('Output already contains files; choose a new directory or use --resume')
    root.mkdir(parents=True, exist_ok=True)
    context = {'mode': 'localized-prep', 'source_all_run': str(source_run),
               'source_ballew_run': str(ballew_run) if ballew_run else None,
               'output': str(root), 'scope': args.only or list(GROUPS), 'partial_scope': True,
               'retained_paths': {k: str(v) for k,v in paths.items()}, 'interpreter': str(exe),
               'mechanics_commit': '7637a38b4fb9ec21dfb953c1c80a27ec5f389654',
               'simulations_reexecuted': 0, 'plot_restyling': False,
               'export_smoke_enabled': not args.skip_export_smoke}
    lock = root/'RUNNING.lock'
    try:
        fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        with os.fdopen(fd, 'w') as stream: stream.write(str(os.getpid()))
    except FileExistsError: parser.error('RUNNING.lock exists; check the prior process before removing a stale lock')
    try:
        before, identity = source_inventory()
        context['source_identity'] = identity
        try: context['git_head'] = subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
        except (OSError,subprocess.CalledProcessError): context['git_head'] = None
        original = read_json(source_run/'health_report.json')
        if original.get('mode') != 'all': raise ValueError('--from-run must identify the completed all-run, not a Ballew-only run')
        context['original_all_report_sha256'] = digest(source_run/'health_report.json')
        if ballew_run: context['original_ballew_report_sha256'] = digest(ballew_run/'health_report.json')
        if args.resume:
            previous = read_json(root/'run_context.json')
            for key in ('mode','source_identity','scope','source_all_run','source_ballew_run','retained_paths','interpreter',
                        'original_all_report_sha256','original_ballew_report_sha256','export_smoke_enabled'):
                if previous.get(key) != context.get(key): raise ValueError('Resume identity changed: '+key+'; select a new output')
        write_json(root/'run_context.json', context)
        write_json(root/'source_manifest.json', before)
        snap = root/'source_snapshot'
        if not snap.exists():
            import shutil
            for name in before:
                source = RELEASE/name
                if source.suffix == '.npz': continue
                target = snap/name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source,target)
        steps = build_prep_plan(root, source_run, ballew_run, exe, paths, only=args.only,
                               fetch_lfs=args.fetch_lfs, exports=not args.skip_export_smoke)
        write_json(root/'execution_plan.json',[step.__dict__ for step in steps])
        print(f'{len(steps)} localized prep/check/export steps. No CVT integrations.\nOutput: {root}',flush=True)
        result = run_plan(steps,root,REPO,context,resume=args.resume,
                          timeout_s=args.step_timeout_hours*3600,env={'PYTHONPATH':str(RELEASE)})
        _, after = source_inventory()
        if after != identity:
            result['steps'].append({'id':'source-stability','group':'environment','role':'health','status':'FAIL','elapsed_s':0.,
                                    'detail':'Source/committed inputs changed during preparation; do not freeze this mixed pass'})
            result = report(root,result['steps'],context)
        readiness(root,source_run,ballew_run,result,paths)
        print('\nHealth report:',root/'health_report.html',flush=True)
        print('Figure-input readiness:',root/'checks/figure_rerun_inputs.json',flush=True)
        summary_zip = package_summary(root)
        with zipfile.ZipFile(summary_zip, 'a', zipfile.ZIP_DEFLATED) as archive:
            if (root/'figure_input_locations.json').is_file():
                archive.write(root/'figure_input_locations.json', 'figure_input_locations.json')
        print('Shareable summary:',summary_zip,flush=True)
        return 0 if result['all_requested_steps_passed'] else 2
    except BaseException as exc:
        old = read_json(root/'health_report.json').get('steps',[]) if (root/'health_report.json').is_file() else []
        old.append({'id':'prep-orchestrator','group':'environment','role':'health','status':'FAIL','elapsed_s':0.,
                    'detail':f'{type(exc).__name__}: {exc}'})
        report(root,old,context)
        print('Prep stopped:',exc,'\nReport:',root/'health_report.html',file=sys.stderr)
        try: package_summary(root)
        except OSError: pass
        return 130 if isinstance(exc,KeyboardInterrupt) else 2
    finally:
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    raise SystemExit(main())
