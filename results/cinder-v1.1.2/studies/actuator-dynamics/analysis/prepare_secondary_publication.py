"""Extract checked figure inputs from frozen secondary replays.

Continuous state comparisons use a common clock. Force plots preserve native
segments and both event sides. Commercial components use the actual model's
inertia, never the legacy sampler's reference-inertia diagnostic columns.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

STUDY = Path(__file__).resolve().parents[1]


def rows(path):
    with gzip.open(path, 'rt', newline='') as f:
        return list(csv.DictReader(f))


def col(data, key):
    return np.array([float(r.get(key) or 'nan') for r in data])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def interp_state(data, field, grid):
    # These are continuous positions/speeds, never discontinuous forces.
    t = col(data, 'time_s')
    if np.any(np.diff(t) < -1e-14):
        raise ValueError('Rows are not chronological')
    return np.interp(grid, t, col(data, field))


def contact_exit(data):
    return next(i for i, r in enumerate(data) if float(r['time_s']) > .03
                and 'STICK_STICK' not in r['cvt_mode'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-dir', type=Path, default=STUDY/'artifacts/secondary-publication-final')
    p.add_argument('--output-dir', type=Path, default=STUDY/'publication_inputs')
    args = p.parse_args(); out = args.output_dir; out.mkdir(parents=True, exist_ok=True)
    arrays, checks, data, provenance = {}, {}, {}, {}
    fields = ['time_s', 'segment_index', 'shift_mm', 'primary_rpm', 'secondary_rpm',
              'shift_speed_m_s', 'shift_acceleration_closure_m_s2', 'normal_primary_N',
              'normal_secondary_N', 'secondary_actuator_closing_force_N',
              'lambda_primary', 'lambda_secondary']
    paired_fields = ['e58_helix_qs_margin_Nm', 'e58_helix_actual_margin_Nm',
        'e58_helix_physical_shaft_term_Nm', 'e58_helix_physical_shift_term_Nm',
        'e58_helix_physical_curvature_term_Nm', 'mass_helix_reflected_active_kg',
        'mass_total_direct_active_kg']
    for kind in ('commercial', 'severe', 'stock'):
        for level in ('nominal', 'tight'):
            for variant in ('full', 'qs'):
                folder = args.raw_dir/f'{kind}_nominal_{level}_{variant}'
                if kind != 'commercial':
                    folder = folder.with_name(folder.name+'_stick')
                meta = json.loads((folder/'summary.json').read_text())
                provenance[folder.name] = meta
                for role in (('stress', 'control') if kind == 'commercial' else ('',)):
                    path = folder/role/'trajectory.csv.gz'
                    d = rows(path)
                    name = '_'.join(x for x in (kind, level, variant, role) if x)
                    data[name] = d
                    for field in fields + (paired_fields if kind != 'commercial' else []):
                        arrays[name+'__'+field] = col(d, field)
                    arrays[name+'__sample_location'] = np.array([r['sample_location'] for r in d])
                    arrays[name+'__mode'] = np.array([r['cvt_mode'] for r in d])
                    rmeta = meta['results'][role] if role else meta['results']
                    assert rmeta['completed'], name+' did not complete'
                    if kind != 'severe':
                        assert rmeta['local_audit']['negative_local_load_count'] == 0, name+' local contact failed'
                    local = rows(folder/role/'local_wrap_audit.csv.gz')
                    assert len(local)==len(d)
                    for key in ('primary_min_local_normal_N_per_rad','secondary_min_local_normal_N_per_rad'):
                        arrays[name+'__'+key] = col(local,key)
                    bad = np.flatnonzero((col(local,'primary_min_local_normal_N_per_rad') < -1e-6) | (col(local,'secondary_min_local_normal_N_per_rad') < -1e-6))
                    arrays[name+'__first_invalid_index'] = np.array(bad[0] if len(bad) else len(d))
                    checks[name] = rmeta
                    if kind == 'commercial':
                        assert len(set(r['segment_index'] for r in d)) == 1
                        assert all('STICK_STICK' in r['cvt_mode'] and 'CVTShiftConstraint.FREE' in r['cvt_mode'] for r in d)
                        components = rows(folder/role/'components.csv.gz')
                        assert np.array_equal(col(d, 'time_s'), col(components, 'time_s'))
                        for key in components[0]:
                            arrays[name+'__'+key] = col(components, key)
                        H = col(components, 'helix_motion_ratio_rad_per_m')
                        torque = col(components, 'dynamic_torque_total_Nm')
                        correction = col(components, 'helix_dynamic_force_correction_N')
                        identity = correction+H*torque
                        delivered = col(d, 'secondary_actuator_closing_force_N')-(3532*(.11-col(d,'secondary_axial_x_m'))+col(components,'helix_full_force_N'))
                        assert np.nanmax(abs(identity)) < 1e-9
                        assert np.nanmax(abs(delivered)) < 1e-8
                        active = col(d,'time_s') >= .05
                        checks[name]['components'] = {
                            'max_force_identity_error_N': float(np.max(abs(identity))),
                            'max_delivered_force_error_N': float(np.max(abs(delivered))),
                            'peak_force_N': float(np.max(abs(correction[active]))),
                            'peak_fraction': float(np.max(col(components,'pi_s_total')[active])),
                            'minimum_qs_torque_Nm': float(np.min(col(components,'tau_helix_qs_Nm')[active])),
                        }
                    else:
                        initial=rmeta['local_audit']['initial_engaged_state']
                        for side in ('primary','secondary'):
                            assert initial[side+'_sticking']
                            assert abs(initial[side+'_relative_speed_m_s']) < .001
                            assert abs(initial[side+'_lambda']) < .65
                            assert initial[side+'_min_local_normal_N_per_rad'] > 0
                        i = contact_exit(d)
                        checks[name]['first_post_onset_exit_s'] = float(d[i]['time_s'])
                        arrays[name+'__exit_index'] = np.array(i)
                        if kind == 'severe':
                            assert len(bad) and bad[0] == i, 'Severe claim mask must stop at the first invalid outgoing state'
                            assert d[i]['sample_location'] == 'segment_start'
                            assert float(d[i-1]['time_s']) == float(d[i]['time_s'])
                            assert abs(abs(float(d[i-1]['lambda_primary']))-.65) < 1e-8
                            assert float(local[i-1]['primary_min_local_normal_N_per_rad']) > 0
                            checks[name]['event_sides'] = [{k: r[k] for k in fields+paired_fields+['sample_location','cvt_mode']} for r in d[i-1:i+1]]
                            f = col(d,'e58_helix_actual_margin_Nm')
                            total = col(d,'e58_helix_qs_margin_Nm')
                            if variant == 'full':
                                total += sum(col(d,key) for key in paired_fields[2:5])
                            assert np.max(abs(f-total)) < 1e-9
    grid = np.arange(.05,.425+1e-10,.0005)
    arrays['commercial_response_time_s'] = grid-.05
    for level in ('nominal','tight'):
        metrics={}
        for field in ('shift_mm','primary_rpm','secondary_actuator_closing_force_N'):
            response=[]
            for variant in ('full','qs'):
                vals=[interp_state(data[f'commercial_{level}_{variant}_{role}'],field,grid) for role in ('stress','control')]
                value=vals[0]-vals[1];response.append(value)
                arrays[f'commercial_response_{level}_{variant}__'+field]=value
            delta=response[0]-response[1];i=int(np.argmax(abs(delta)))
            arrays[f'commercial_response_{level}_delta__'+field]=delta
            metrics[field]={'max_abs_difference':float(abs(delta[i])), 'time_s':float(grid[i]),
                'full_at_max':float(response[0][i]), 'qs_at_max':float(response[1][i])}
        checks['commercial_response_'+level]=metrics
        for kind,end in [('severe',.43),('stock',.382)]:
            g=np.arange(.03,end+1e-10,.0001)
            f=data[f'{kind}_{level}_full'];q=data[f'{kind}_{level}_qs']
            delta=interp_state(f,'shift_mm',g)-interp_state(q,'shift_mm',g)
            arrays[f'{kind}_{level}_response_time_s']=g-.03
            arrays[f'{kind}_{level}_shift_difference_mm']=delta
            checks[f'{kind}_response_{level}']={
                'max_abs_shift_difference_mm':float(abs(delta).max()),
                'qs_earlier_exit_ms':1000*(checks[f'{kind}_{level}_full']['first_post_onset_exit_s']-checks[f'{kind}_{level}_qs']['first_post_onset_exit_s'])}
            if kind == 'severe':
                limit = min(checks[f'{kind}_{level}_{v}']['local_audit']['first_negative_local_state']['time_s'] for v in ('full','qs'))
                checks[f'{kind}_response_{level}']['common_admissible_end_s'] = limit
                checks[f'{kind}_response_{level}']['max_abs_shift_difference_before_local_failure_mm'] = float(abs(delta[g<limit]).max())
                checks[f'{kind}_response_{level}']['scope'] = 'Post-exit difference is a formal continuation through locally inadmissible wrap states; not a valid performance prediction.'
    checks['refinement']={}
    for field in ('shift_mm','primary_rpm'):
        checks['refinement']['commercial_'+field]=float(np.max(abs(arrays[f'commercial_response_tight_delta__{field}']-arrays[f'commercial_response_nominal_delta__{field}'])))
    for kind in ('severe','stock'):
        checks['refinement'][kind+'_shift_difference_change_mm']=float(np.max(abs(arrays[kind+'_tight_shift_difference_mm']-arrays[kind+'_nominal_shift_difference_mm'])))
        checks['refinement'][kind+'_timing_difference_change_ms']=abs(checks[kind+'_response_tight']['qs_earlier_exit_ms']-checks[kind+'_response_nominal']['qs_earlier_exit_ms'])
    d=data['severe_tight_full'];i=contact_exit(d)
    # Budget belongs to the admissible incoming event side, not the failed outgoing state.
    h=float(d[i-1]['mass_helix_reflected_active_kg']);total=float(d[i-1]['mass_total_direct_active_kg'])
    checks['inertia_budget']={'helix_kg':h,'other_direct_kg':total-h,'total_kg':total,'fraction':h/total}
    arrays['severe_inertia_budget_kg']=np.array([h,total-h])
    archive=json.loads((out/'secondary_archive_audit.json').read_text())
    checks['archive_comparison'] = {}
    for kind,key in [('severe','E58_reversal_270_s30_engine_m28_r050'),('stock','E58_stock_300_s30_output_m120_r002')]:
        old=archive['paired'][key]
        new=checks[kind+'_response_nominal']
        checks['archive_comparison'][kind]={'shift_metric_difference_mm':new['max_abs_shift_difference_mm']-old['common_clock_differences']['shift_mm'],
            'timing_metric_difference_ms':new['qs_earlier_exit_ms']+old['qs_minus_full_first_nonstick_ms']}
    np.savez_compressed(out/'secondary_publication.npz',**arrays)
    manifest={'release_commit':'7637a38b4fb9ec21dfb953c1c80a27ec5f389654',
        'publication_trace_level':'tight','plot_inputs_sha256':sha(out/'secondary_publication.npz'),
        'archive_audit_sha256':sha(out/'secondary_archive_audit.json'),
        'raw_sha256':{str(p.relative_to(args.raw_dir)):sha(p) for p in sorted(args.raw_dir.rglob('*')) if p.suffix in ('.gz','.json')},
        'run_provenance':provenance,'checks':checks}
    (out/'secondary_publication_audit.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:checks[k] for k in ('commercial_response_tight','severe_response_tight','stock_response_tight','refinement','inertia_budget','archive_comparison')},indent=2))


if __name__=='__main__':main()
