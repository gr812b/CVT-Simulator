"""Read-only audit of recovered secondary evidence; does not import CINDER.

Run with the three data archives extracted as described in SOURCE_INVENTORY.md:
    python audit_secondary.py --root /path/to/secondary_spine
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def maxabs(a):
    return float(np.nanmax(np.abs(a)))


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def ordered(frame):
    # Matches archived scalar comparisons. Event diagnostics retain both sides.
    return frame.drop_duplicates('time_s', keep='last').sort_values('time_s')


def interp(frame, key, grid):
    frame = ordered(frame).dropna(subset=[key])
    return np.interp(grid, frame.time_s, frame[key])


def short_mode(value):
    import re
    hit = re.search(r'EngagedContactMode\.([A-Z_]+)', str(value))
    return hit.group(1) if hit else 'DEADZONE'


def main(root):
    out = {'scope': 'reanalysis of archived outputs; no new simulations',
           'scientific_release': 'cinder-cvt==1.1.2',
           'mechanics_commit': '7637a38b4fb9ec21dfb953c1c80a27ec5f389654'}
    used = []
    commercial = root / 'commercial_archive5/artifacts/trajectory-demo'
    selection = json.loads((commercial / 'selected_case.json').read_text())
    screen = pd.read_csv(commercial / 'screen.csv')
    eligible = screen[(screen.response_class == 'clean_continuous') &
                      (screen.minimum_qs_torque_fraction_of_onset >= .25)]
    out['commercial_selection'] = {
        'selected': selection,
        'screen_rows': len(screen),
        'response_classes': screen.response_class.value_counts().to_dict(),
        'eligible_count': len(eligible),
        'eligible_in_target_band': int(eligible.peak_pi_total.between(.1,.2).sum()),
        'highest_eligible_case': eligible.loc[eligible.peak_pi_total.idxmax(), 'case_id'],
    }
    summary = pd.read_csv(commercial / 'validation_summary.csv').set_index('estimate_level')
    # Frozen reference inputs, also recorded in the maintained commercial
    # PARAMETER_PROVENANCE.csv. Compare like local axial coordinates here.
    reference_I = 0.0025139
    reference_H = 1.0 / (0.04445 * np.tan(np.deg2rad(20.0)))
    out['reference_component'] = {
        'movable_inertia_kg_m2': reference_I,
        'helix_radius_m': 0.04445,
        'helix_angle_deg': 20.0,
        'local_motion_ratio_rad_per_m': float(reference_H),
        'local_reflected_inertia_kg': float(reference_I * reference_H**2),
    }
    out['commercial'] = {}
    for level in ('low', 'nominal', 'high'):
        path = commercial / level / 'trajectory_samples.csv'
        used.append(path)
        df = pd.read_csv(path)
        trace_path = commercial / level / 'full_dynamic_component_trace.csv'
        used.append(trace_path)
        terms = pd.read_csv(trace_path)
        spec = summary.loc[level]
        inertia = float(spec.movable_member_inertia_kg_m2)
        H = terms.helix_motion_ratio_rad_per_m
        moment = inertia * (terms.secondary_alpha_rad_s2 +
                            H * terms.secondary_axial_acceleration_m_s2 +
                            terms.helix_motion_ratio_gradient_rad_per_m2 *
                            terms.secondary_axial_speed_m_s**2)
        groups = {k: v for k,v in df.groupby('run_role')}
        grid = np.arange(.05, min(g.time_s.max() for g in groups.values()) + .00025, .0005)
        # Preserve the archive's guard against roundoff extending beyond support.
        grid = grid[grid <= min(g.time_s.max() for g in groups.values())]
        metrics = {}
        for name, key in [('shift_mm','shift_mm'),('primary_rpm','primary_rpm'),
                          ('secondary_clamp_N','secondary_actuator_closing_force_N')]:
            full = interp(groups['full_stress'],key,grid)-interp(groups['full_control'],key,grid)
            qs = interp(groups['qs_stress'],key,grid)-interp(groups['qs_control'],key,grid)
            delta = full-qs
            idx = int(np.argmax(np.abs(delta)))
            metrics[name] = {'max_abs_full_minus_qs_response': maxabs(delta),
                             'time_s':float(grid[idx]),'full_response_at_max':float(full[idx]),
                             'qs_response_at_max':float(qs[idx]),
                             'archive_metric_difference':maxabs(delta)-float(spec['max_abs_paired_delta_'+name])}
        full = groups['full_stress']
        Hs = full.helix_dtheta_ds_rad_per_m
        # Generic baseline diagnostics hard-code the Baja inertia. Reconstruct
        # from the executed model's registered inertia for the transplant.
        inferred_I = full.mass_helix_reflected_active_kg / Hs**2
        matching = full.merge(terms,on='time_s',suffixes=('_generic','_dedicated'))
        spring = 3532.0 * (.11 - matching.secondary_axial_x_m)
        delivered_residual = (matching.secondary_actuator_closing_force_N -
                              spring - matching.helix_full_force_N)
        peak = terms.loc[terms.pi_s_total.idxmax()].to_dict()
        out['commercial'][level] = {
            'registered_inertia_kg_m2':inertia,
            'generic_diagnostic_inertia_range': [float(inferred_I.min()),float(inferred_I.max())],
            'local_reflected_inertia_kg':float(spec.reflected_axial_inertia_kg),
            'scaling_vs_reference': {
                'rotational_inertia_ratio': inertia / reference_I,
                'shaft_acceleration_force_coefficient_ratio': float(inertia * H.iloc[0] / (reference_I * reference_H)),
                'local_reflected_inertia_ratio': float(inertia * H.iloc[0]**2 / (reference_I * reference_H**2)),
            },
            'term_reconstruction_max_error_Nm':maxabs(moment-terms.dynamic_torque_total_Nm),
            'delivered_force_from_correct_inertia_max_error_N':maxabs(delivered_residual),
            'force_identity_max_error_N':maxabs(-H*moment-terms.helix_dynamic_force_correction_N),
            'peak_fraction':float(terms.pi_s_total.max()),
            'peak_abs_dynamic_force_N':maxabs(terms.helix_dynamic_force_correction_N),
            'minimum_denominator_fraction':float(terms.tau_helix_qs_Nm.abs().min()/abs(terms.tau_helix_qs_Nm.iloc[0])),
            'peak_fraction_row':peak,
            'response_metrics':metrics,
            'roles': {k:{'segments':int(v.segment_index.nunique()),
                        'modes':sorted(set(map(short_mode,v.cvt_mode))),
                        'min_primary_normal_N':float(v.normal_primary_N.min()),
                        'min_secondary_normal_N':float(v.normal_secondary_N.min())}
                      for k,v in groups.items()}
        }
    paired_path = root / 'helix_archive5/artifacts/paired-helix-performance/paired_trace.csv'
    used.append(paired_path)
    paired = pd.read_csv(paired_path)
    out['paired'] = {}
    saved_event_rows = []
    for case, data in paired.groupby('e58_case_id',sort=False):
        group = {k:v for k,v in data.groupby('e58_model')}
        records = {}
        for model,g in group.items():
            segs=[]
            for idx,v in g.groupby('segment_index',sort=False):
                segs.append({'index':int(idx),'start':float(v.time_s.min()),'end':float(v.time_s.max()),
                             'mode':short_mode(v.cvt_mode.iloc[0]),
                             'event':None if pd.isna(v.segment_event_names.iloc[0]) else str(v.segment_event_names.iloc[0])})
            nonstick=[s for s in segs if s['mode']!='STICK_STICK' and s['end']>.03]
            duration=sum(s['end']-max(.03,s['start']) for s in nonstick)
            records[model]={'segments':segs,'first_post_onset_nonstick_s':min(s['start'] for s in nonstick),
                            'post_onset_nonstick_duration_s':duration,
                            'radius_ratio_reconstruction_error':maxabs(g.ratio_secondary_over_primary-g.secondary_effective_radius_m/g.primary_effective_radius_m),
                            'end_s':float(g.time_s.max())}
            if 'reversal' in case:
                for _,r in g[(g.sample_location!='interior')&(g.time_s>.03)].iterrows():
                    keys=['time_s','segment_index','sample_location','shift_mm','shift_speed_m_s',
                          'shift_acceleration_closure_m_s2','e58_helix_qs_margin_Nm','e58_helix_actual_margin_Nm',
                          'e58_helix_physical_shaft_term_Nm','e58_helix_physical_shift_term_Nm',
                          'e58_helix_physical_curvature_term_Nm','normal_secondary_N',
                          'mass_helix_reflected_active_kg','mass_total_direct_active_kg','lambda_primary','lambda_secondary']
                    event={k:r[k] for k in keys};event.update({'case':case,'model':model})
                    saved_event_rows.append(event)
        grid=np.arange(0,min(g.time_s.max() for g in group.values())+.00005,.0001)
        grid=grid[grid>=.03]
        f=group['full'].copy();q=group['quasi_static_helix'].copy()
        for g in (f,q):g['actual_speed_ratio']=g.secondary_omega_rad_s/g.primary_omega_rad_s
        metrics={key:maxabs(interp(f,key,grid)-interp(q,key,grid))
                 for key in ['shift_mm','ratio_secondary_over_primary','actual_speed_ratio','primary_rpm','secondary_rpm']}
        tdiff=1000*(records['quasi_static_helix']['first_post_onset_nonstick_s']-records['full']['first_post_onset_nonstick_s'])
        initial_fields=['primary_omega_rad_s','secondary_omega_rad_s','belt_speed_m_s','shift_m','shift_speed_m_s']
        records['initial_state_max_absolute_difference']=maxabs(f.iloc[0][initial_fields].astype(float)-q.iloc[0][initial_fields].astype(float))
        records['common_clock_differences']=metrics
        records['qs_minus_full_first_nonstick_ms']=tdiff
        out['paired'][case]=records
    out['severe_native_event_sides']=saved_event_rows
    incoming = min((r for r in saved_event_rows
                    if r['model'] == 'full' and r['sample_location'] == 'segment_end'),
                   key=lambda r: r['time_s'])
    helix = incoming['mass_helix_reflected_active_kg']
    total = incoming['mass_total_direct_active_kg']
    out['severe_shift_inertia_budget'] = {
        'time_s': incoming['time_s'],
        'sample_location': incoming['sample_location'],
        'helix_reflected_kg': helix,
        'other_direct_terms_kg': total - helix,
        'total_direct_coefficient_kg': total,
        'helix_fraction': helix / total,
        'meaning': 'Direct shared-shift inertia coefficient: axial translation plus flyweight and helix reflection; not total physical CVT mass or a scalar inertia after eliminating the coupled shaft/contact equations.',
    }
    baseline_path=root/'actuator_archive2/artifacts/baseline-ablation/trajectory_diagnostics.csv'
    used.append(baseline_path)
    baseline=pd.read_csv(baseline_path)
    baseline=baseline[(baseline.variant=='full')&(baseline.time_s>=.1)]
    out['baseline_t_ge_0_1_s']={'peak_abs_helix_force_correction_N':maxabs(baseline.helix_dynamic_total_correction_N),
                              'peak_abs_helix_force_fraction':maxabs(baseline.helix_dynamic_correction_pct_of_qs_force)/100}
    out['source_hashes']={str(p.relative_to(root)):sha(p) for p in used}
    out['remaining_limits']=[
        'No new numerical-refinement integrations or fresh local wrap-contact audit.',
        'Paired field ratio_secondary_over_primary is r_s/r_p, not omega_s/omega_p.',
        'Generic commercial trajectory helix diagnostic columns use Baja inertia; dedicated component trace and actual actuator total agree with registered commercial inertia.',
        'Severe helix reaction reverses sign across a native traction event. An interpolated zero and its interpolated force do not represent a resolved intervening state.',
        'Stock first non-stick event is low-ratio seating followed by deadzone/reengagement, not an isolated static-traction failure.',
        'Native segment endpoints are retained; separate serialized event ledger is absent from the recovered E5.8 archive.'
    ]
    (root/'SECONDARY_EVIDENCE_AUDIT.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    pd.DataFrame(saved_event_rows).to_csv(root/'severe_native_event_sides.csv',index=False)
    print('Wrote SECONDARY_EVIDENCE_AUDIT.json and severe_native_event_sides.csv')
    print('Commercial fractions:',{k:v['peak_fraction'] for k,v in out['commercial'].items()})
    print('Commercial force-identity errors:',{k:v['delivered_force_from_correct_inertia_max_error_N'] for k,v in out['commercial'].items()})
    print('Paired shifts:',{k:v['common_clock_differences']['shift_mm'] for k,v in out['paired'].items()})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    main(p.parse_args().root)
