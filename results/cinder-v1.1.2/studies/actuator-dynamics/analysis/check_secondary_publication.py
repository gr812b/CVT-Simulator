"""Check the secondary publication quantities and event masks, without simulation.

The expected outgoing failure is checked as a limitation, not marked admissible.
Pass --raw-dir to verify all 68 frozen source files as well as compact inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

STUDY = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=STUDY/'publication_inputs')
    parser.add_argument('--raw-dir', type=Path)
    parser.add_argument('--backshift-dir', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    p = args.input_dir
    audit = json.loads((p/'secondary_publication_audit.json').read_text())
    archive = json.loads((p/'secondary_archive_audit.json').read_text())
    assert audit['release_commit'] == '7637a38b4fb9ec21dfb953c1c80a27ec5f389654'
    assert sha(p/'secondary_publication.npz') == audit['plot_inputs_sha256']
    assert sha(p/'secondary_archive_audit.json') == audit['archive_audit_sha256']
    z = np.load(p/'secondary_publication.npz', allow_pickle=False)
    results = {'this_check_runs_simulations': False, 'plot_inputs_sha256': audit['plot_inputs_sha256']}
    story=json.loads((p/'secondary_story_audit.json').read_text())
    assert story['release_commit']==audit['release_commit']
    assert sha(p/'secondary_story.npz')==story['plot_inputs_sha256']
    zs=np.load(p/'secondary_story.npz',allow_pickle=False)
    if args.backshift_dir:
        for name,digest in story['raw_sha256'].items():
            assert sha(args.backshift_dir/name)==digest,name
        results['backshift_raw_files_verified']=len(story['raw_sha256'])
    for torque in (120,240,480):
        for level in ('nominal','tight'):
            pre=f'm{torque}_{level}__'
            assert len(np.unique(zs[pre+'segment_index']))==1
            assert np.all(np.diff(zs[pre+'time_s'])>0)
            assert all('STICK_STICK' in m and 'CVTShiftConstraint.FREE' in m for m in zs[pre+'cvt_mode'])
            for side in ('primary','secondary'):
                assert np.min(zs[pre+side+'_min_local_normal_N_per_rad'])>0
                assert np.max(abs(zs[pre+'lambda_'+side]))<.65
            delta=zs[pre+'helix_full_reaction_force_N']-zs[pre+'helix_qs_reaction_force_N']
            parts=sum(zs[pre+'helix_dynamic_'+k+'_force_N'] for k in ('shaft_accel','shift_accel','curvature'))
            assert np.max(abs(delta-parts))<1e-8
    pre='launch_tight__';i=story['launch']['tight']['first_engaged_index']
    assert zs[pre+'sample_location'][i]=='segment_start'
    assert np.all(np.isnan(zs[pre+'helix_qs_reaction_force_N'][:i]))
    later=zs[pre+'time_s']>=.1
    bound=np.max(abs(100*zs[pre+'helix_dynamic_total_correction_N'][later]/zs[pre+'helix_qs_reaction_force_N'][later]))
    assert np.isclose(bound,story['launch']['tight']['max_later_fraction_percent'],rtol=1e-12)
    results['launch_later_force_bound_percent']=float(bound)
    results['backshift_refinement']={k:v for k,v in story['backshift'].items() if k.endswith('_refinement')}
    response_checks={}
    for torque in (120,240,480):
        for level in ('nominal','tight'):
            names=[f'm{torque}_{level}',f'm{torque}_{level}_qs',f'm0_{level}',f'm0_{level}_qs']
            for name in names:
                pre=name+'__'
                assert len(np.unique(zs[pre+'segment_index']))==1
                assert np.all(np.diff(zs[pre+'time_s'])>0)
                assert all('STICK_STICK' in m and 'CVTShiftConstraint.FREE' in m for m in zs[pre+'cvt_mode'])
                for side in ('primary','secondary'):
                    assert np.min(zs[pre+side+'_min_local_normal_N_per_rad'])>0
                    assert np.max(abs(zs[pre+'lambda_'+side]))<.65
            f,q,fc,qc=[zs[n+'__shift_m'] for n in names]
            expected=1000*((f-fc)-(q-qc))
            actual=zs[f'response_m{torque}_{level}__full_minus_qs_shift_mm']
            assert np.max(abs(expected-actual))<1e-12
            result=story['backshift_response'][f'm{torque}_{level}_comparison']
            assert np.isclose(np.max(abs(actual)),result['max_abs_shift_response_difference_mm'],rtol=1e-12)
            assert result['signed_shift_response_difference_at_peak_mm']<0
            response_checks[f'm{torque}_{level}']=result
        delta=zs[f'response_m{torque}_nominal__full_minus_qs_shift_mm']-zs[f'response_m{torque}_tight__full_minus_qs_shift_mm']
        assert np.max(abs(delta))<1e-4
    results['backshift_response_checks']=response_checks
    if args.raw_dir:
        for name, expected in audit['raw_sha256'].items():
            assert sha(args.raw_dir/name) == expected, name
        results['raw_files_verified'] = len(audit['raw_sha256'])

    events = {}
    for level in ('nominal', 'tight'):
        for variant in ('full', 'qs'):
            prefix = f'severe_{level}_{variant}'
            i = int(z[prefix+'__first_invalid_index'])
            assert i == int(z[prefix+'__exit_index'])
            t = z[prefix+'__time_s']
            assert t[i-1] == t[i]
            assert z[prefix+'__sample_location'][i-1] == 'segment_end'
            assert z[prefix+'__sample_location'][i] == 'segment_start'
            assert np.all(np.diff(t[:i]) >= 0)
            assert abs(z[prefix+'__lambda_primary'][i-1]+.65) < 1e-8
            for side in ('primary', 'secondary'):
                assert np.all(z[prefix+f'__{side}_min_local_normal_N_per_rad'][:i] > 0)
            outgoing = float(z[prefix+'__primary_min_local_normal_N_per_rad'][i])
            assert outgoing < -1e-6
            events[prefix] = {'incoming_time_s': float(t[i-1]),
                             'incoming_lambda_primary': float(z[prefix+'__lambda_primary'][i-1]),
                             'outgoing_primary_min_N_per_rad': outgoing}
            assert audit['checks'][f'stock_{level}_{variant}']['local_audit']['negative_local_load_count'] == 0
    results['masked_reversal_events'] = events
    results['qs_earlier_limit_ms'] = 1000*(events['severe_tight_full']['incoming_time_s']-events['severe_tight_qs']['incoming_time_s'])
    assert abs(results['qs_earlier_limit_ms']-audit['checks']['severe_response_tight']['qs_earlier_exit_ms']) < 1e-10

    pre = 'stock_tight_full__'
    shaft = z[pre+'e58_helix_physical_shaft_term_Nm']
    relative = z[pre+'e58_helix_physical_shift_term_Nm']+z[pre+'e58_helix_physical_curvature_term_Nm']
    error = z[pre+'e58_helix_actual_margin_Nm']-z[pre+'e58_helix_qs_margin_Nm']-shaft-relative
    engaged = np.array(['CVTEngagementState.ENGAGED' in mode for mode in z[pre+'mode']])
    assert np.array_equal(np.isfinite(error), engaged)
    assert np.max(np.abs(error[engaged])) < 1e-9
    ix = np.flatnonzero(np.isclose(z[pre+'time_s'], .0318, rtol=0, atol=1e-12))
    assert len(ix) == 1
    j = ix[0]
    assert shaft[j] > 0 and relative[j] < 0
    delta = z['stock_tight_shift_difference_mm']
    assert np.min(delta) > -.06 and np.max(delta) < .015
    results['stock_terms_at_1_8_ms_Nm'] = {'shaft': float(shaft[j]), 'relative_sheave': float(relative[j]),
                                         'net': float(shaft[j]+relative[j]),
                                         'quasi_static': float(z[pre+'e58_helix_qs_margin_Nm'][j])}
    results['stock_shift_difference_range_mm'] = [float(np.min(delta)), float(np.max(delta))]

    budget = z['severe_inertia_budget_kg']
    assert np.all(budget > 0)
    assert np.isclose(budget[0]/sum(budget), audit['checks']['inertia_budget']['fraction'])
    results['direct_shared_shift_inertia'] = audit['checks']['inertia_budget']
    nominal = archive['commercial']['nominal']
    ref = archive['reference_component']
    inertia = nominal['registered_inertia_kg_m2']
    H = nominal['peak_fraction_row']['helix_motion_ratio_rad_per_m']
    ratios = {'rotational_inertia_ratio': inertia/ref['movable_inertia_kg_m2'],
              'shaft_acceleration_force_coefficient_ratio': inertia*H/(ref['movable_inertia_kg_m2']*ref['local_motion_ratio_rad_per_m']),
              'local_reflected_inertia_ratio': inertia*H**2/ref['local_reflected_inertia_kg']}
    for key, value in ratios.items():
        assert np.isclose(value, nominal['scaling_vs_reference'][key], rtol=1e-12)
    results['nominal_hardware_ratios'] = ratios

    for variant in ('full', 'qs'):
        for role in ('stress', 'control'):
            prefix = f'commercial_tight_{variant}_{role}__'
            assert len(np.unique(z[prefix+'segment_index'])) == 1
            assert all('STICK_STICK' in mode and 'CVTShiftConstraint.FREE' in mode for mode in z[prefix+'mode'])
            for side in ('primary', 'secondary'):
                assert np.all(z[prefix+f'{side}_min_local_normal_N_per_rad'] > 0)
    results['commercial_response'] = audit['checks']['commercial_response_tight']
    results['scope'] = 'Sampled/native-event consistency and publication extraction; not continuous-time proof or admissible post-slip evidence.'
    if args.output:
        args.output.write_text(json.dumps(results, indent=2)+'\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
