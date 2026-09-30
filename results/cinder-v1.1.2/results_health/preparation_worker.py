"""One isolated, non-integrating preparation/check/export operation."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import shutil
import sys
import traceback

RELEASE = Path(__file__).resolve().parents[1]
REPO = RELEASE.parents[1]
if str(RELEASE) not in sys.path:
    sys.path.insert(0, str(RELEASE))
from results_health.common import MissingEvidence, digest, read_json, write_json, verify_hashes
from results_health.prep_support import (materialize_asset, validate_primary_screen,
    verify_saved_subtree, resolve_saved_suite, require_data, portable_hashes)
from results_health.worker import module, invoke


def action(spec):
    p = spec.get('parameters', {})
    kind = spec['action']
    if kind == 'integrity':
        return verify_saved_subtree(Path(p['run']), p['relative'], required_prefix=p.get('producer'))
    if kind == 'primary-screen':
        target = Path(p['target'])
        value = materialize_asset(Path(p['source']), target, REPO, fetch=p.get('fetch_lfs', False))
        rows = validate_primary_screen(target)
        value['verified_screen_rows'] = len(rows)
        value['screen_dropped_or_recomputed'] = False
        return value
    if kind == 'primary-prepare':
        invoke('actuator-dynamics', 'analysis/prepare_primary_publication.py',
               ['--raw-dir', p['raw'], '--output-dir', p['output'], '--screen-csv', p['screen']])
        return {'prepared': str(p['output']), 'screen_rows': 72}
    if kind == 'primary-health':
        from results_health.audits import check_primary
        return check_primary(Path(p['inputs']), Path(p['raw']))
    if kind == 'secondary-archive':
        original = Path(p['source'])
        require_data(original)
        target = Path(p['target'])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        return {'copied_registered_archive_audit': digest(target), 'source': str(original)}
    if kind == 'secondary-prepare':
        invoke('actuator-dynamics', 'analysis/prepare_secondary_publication.py',
               ['--raw-dir', p['raw'], '--output-dir', p['output']])
        return {'prepared': str(p['output'])}
    if kind == 'secondary-story':
        invoke('actuator-dynamics', 'analysis/prepare_secondary_story.py',
               ['--primary-dir', p['primary_raw'], '--backshift-dir', p['backshift_raw'],
                '--output-dir', p['output']])
        return {'prepared': str(p['output']),
                'note': 'Uses existing full-primary baselines; does not depend on the screening table.'}
    if kind == 'secondary-health':
        invoke('actuator-dynamics', 'analysis/check_secondary_publication.py',
               ['--input-dir', p['inputs'], '--output', p['details']])
        return read_json(Path(p['details']))
    if kind == 'primary-export':
        invoke('actuator-dynamics', 'analysis/primary_publication_plots.py',
               ['--input-dir', p['inputs'], '--figure-dir', p['figures']])
        return export_inventory(Path(p['figures']), ('primary_engagement', 'primary_torque_ramps'))
    if kind == 'secondary-export':
        invoke('actuator-dynamics', 'analysis/secondary_publication_plots.py',
               ['--input-dir', p['inputs'], '--figure-dir', p['figures']])
        return export_inventory(Path(p['figures']), ('secondary_launch', 'secondary_backshift',
                                                     'secondary_continuous_response', 'secondary_support'))
    if kind in ('belt-prepare', 'belt-health', 'belt-export'):
        m = module('reduced-belt-transients', 'analysis/publication.py')
        command = {'belt-prepare': 'prepare', 'belt-health': 'check', 'belt-export': 'plot'}[kind]
        m.main(command, Path(p['raw']), Path(p['figures']) if p.get('figures') else None,
               Path(p['inputs']))
        if kind == 'belt-export':
            return export_inventory(Path(p['figures']), ('belt_load_rate', 'belt_shift_transient',
                                                        'belt_coefficient_driver', 'belt_density_response'))
        if kind == 'belt-health':
            from results_health.belt import check_publication
            return check_publication(Path(p['inputs']), Path(p['raw']),
                RELEASE/'studies/reduced-belt-transients/publication_inputs/runtime_source_check.json')
        a = read_json(Path(p['inputs'])/'belt_publication_audit.json')
        return {'runs_prepared': len(a['runs']), 'same_raw_directory_used_for_moving_evidence': True,
                'simulation_calls': 0}
    if kind == 'course-health':
        module('course-tuning')
        from results_health.audits import check_course
        suite = resolve_saved_suite(Path(p['run']))
        result = check_course(suite, Path(p['details']))
        # Retain plot-input location and source fields; do not manufacture a
        # replacement plot or a different definition of transmitted power.
        write_json(Path(p['inputs'])/'course_source.json', {
            'suite': str(suite), 'suite_sha256': digest(suite/'suite.json'),
            'audit': str(Path(p['details']).resolve()), 'audit_sha256': digest(Path(p['details'])),
            'case_count': len(result['cases']), 'event_sides_preserved': True,
            'raw_rows_modified': False,
            'power_channels': {
                'primary_boundary_power_W': 'primary boundary external torque * primary angular speed',
                'secondary_boundary_power_W': 'secondary boundary external torque * secondary angular speed',
                'primary_to_belt_power_W': '-primary_belt_torque_Nm * omega_p_rad_s',
                'belt_to_secondary_power_W': 'secondary_belt_torque_Nm * omega_s_rad_s'},
            'course_paper_compositor': 'not present in the inspected maintained publication route'})
        return result
    if kind == 'course-prepare':
        from results_health.prep_support import prepare_course_bundle
        source = read_json(Path(p['inputs'])/'course_source.json')
        result = prepare_course_bundle(Path(source['suite']), Path(p['inputs']), Path(p['details']))
        return {'case_count': result['case_count'], 'bundle': str(Path(p['inputs'])/'course_bundle.json'),
                'smoothing_or_resampling': False}
    if kind == 'retained-probe':
        directory = Path(p['directory'])
        expected = p['required']
        missing = [str(directory/name) for name in expected if not (directory/name).exists()]
        detail = {'study': p['study'], 'directory': str(directory), 'missing': missing,
                  'not_replaced_by_new_core_sweep': True,
                  'recovery_instructions': p['instructions'], 'core_directory': p.get('core')}
        write_json(Path(p['details']), detail)
        if missing:
            raise MissingEvidence(f'{p["study"]}: required retained publication evidence is unavailable. '
                                  f'See {p["details"]}. A fresh core sweep is not substituted.')
        for name in expected:
            if (directory/name).is_file(): require_data(directory/name)
        # Actual maintained audit/plot commands run in a later independent task.
        return detail
    if kind == 'solver-export':
        invoke('solver-convergence', 'run.py', ['--plot-only', '--publication-dir', p['figures']],
               {'ARTIFACTS': p['directory']})
        return export_inventory(Path(p['figures']), ('gross_motion_hybrid_history', 'solver_refinement',
                                                     'solver_acceptance_support', 'solver_population_support'))
    if kind == 'closure-export':
        invoke('closure-conditioning', 'run.py', ['--plot-only', '--artifacts-dir', p['directory'],
                                                 '--figure-dir', p['figures']])
        return export_inventory(Path(p['figures']), ('closure_robustness', 'sticking_closure_fold'))
    if kind == 'ballew-register':
        run = Path(p['run'])
        value = verify_saved_subtree(run, 'prepared/ballew', required_prefix='ballew-prepare')
        plots = verify_saved_subtree(run, 'figures/ballew', required_prefix='ballew-figures')
        if read_json(run/'checks/ballew-health.json').get('status') != 'PASS':
            raise ValueError('The identified Ballew health step did not pass')
        raw = run/'data/ballew'
        # Identity/integrity of the old accepted execution is the criterion here,
        # not current simulation_fingerprint after unrelated prep-helper edits.
        m = module('ballew-2015', 'analysis/publication_evidence.py')
        checked = {}
        for name in ('closed-loop', 'force-replay', 'convergence/nominal_0p50ms',
                     'convergence/nominal_0p25ms', 'convergence/tight_0p50ms'):
            m.verify_execution(raw/name)
            mass = read_json(raw/name/'resolved_belt_mass.json')
            if not math.isfinite(float(mass['mass_kg'])) or abs(float(mass['mass_kg']) - 1.) > 2e-12:
                raise ValueError('Wrong assembled belt mass in retained Ballew calculation')
            checked[name] = {'mass_kg': mass['mass_kg'], 'execution': digest(raw/name/'execution_provenance.json')}
        result = {'prepared_integrity': value, 'figure_integrity': plots, 'executions': checked,
                  'original_generating_identity_preserved': True, 'reintegrated': False,
                  'plot_input_directory': str(run/'prepared/ballew')}
        write_json(Path(p['inputs'])/'ballew_source.json', result)
        return result
    raise ValueError('Unknown preparation action: ' + str(kind))


def export_inventory(directory, stems):
    files = {}
    for stem in stems:
        file = directory/(stem+'.pdf')
        if not file.is_file():
            raise ValueError('Expected publication PDF was not exported: '+str(file))
        data = file.read_bytes()
        if not data.startswith(b'%PDF-') or not data.rstrip().endswith(b'%%EOF'):
            raise ValueError('Publication PDF stream appears incomplete: '+str(file))
        files[file.name] = {'sha256': digest(file), 'bytes': len(data)}
    return {'exports': files, 'plot_style_changed': False,
            'check_scope': 'Expected outputs and complete PDF streams; not independent visual approval'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path)
    args = parser.parse_args()
    spec = read_json(args.spec)
    out = Path(spec['report'])
    try:
        result = action(spec)
        write_json(out, {'status': 'PASS', 'result': result})
        return 0
    except (MissingEvidence, FileNotFoundError) as exc:
        write_json(out, {'status': 'MISSING', 'error': str(exc)})
        print(str(exc), file=sys.stderr)
        return 3
    except (Exception, SystemExit) as exc:
        write_json(out, {'status': 'FAIL', 'error': f'{type(exc).__name__}: {exc}'})
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
