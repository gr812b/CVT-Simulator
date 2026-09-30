"""Check the final figure interpretation against compact, signed frozen evidence.

Run with the release Python after canonical run.py --publication check.
This does not rerun a simulation or treat saved-state checks as a domain proof.
"""
from pathlib import Path
import hashlib,json
import numpy as np
STUDY=Path(__file__).resolve().parents[1]
P=STUDY/'publication_inputs'
a=json.loads((P/'belt_publication_audit.json').read_text())
z=np.load(P/'belt_publication.npz',allow_pickle=False)
assert hashlib.sha256((P/'belt_publication.npz').read_bytes()).hexdigest()==a['plot_inputs_sha256']
def terms(case):
 p=case+'_tight_full__terms__'
 return {k[len(p):]:z[k] for k in z.files if k.startswith(p)}
def values(d,i):
 return {k:float(d[k][i]) for k in ['time_s','loop.radial_shift_acceleration_N','loop.radial_geometry_curvature_N','loop.tangential_belt_acceleration_N','loop.tangential_shifting_radius_N','loop.normal_contact_N']}
d=terms('flat');i=np.argmax(abs(d['loop.radial_shift_acceleration_N']))
r={'early_radial_peak_and_signed_balance':values(d,i)}
i=np.flatnonzero(np.isclose(d['time_s'],1.5,atol=1e-12,rtol=0))[0]
r['reference_at_1_5s']=values(d,i)
r['reference_at_1_5s']['primary_normal_part_N']=float(d['coefficient.primary_G'][i]*d['contact.primary_normal_N'][i])
r['reference_at_1_5s']['secondary_normal_part_N']=float(d['coefficient.secondary_G'][i]*d['contact.secondary_normal_N'][i])
r['matched_rises']={}
for case in ('rise50','rise200','rise800'):
 d=terms(case);m=(d['time_s']>=1.45)&(d['time_s']<=2.55)
 assert all('CVTShiftConstraint.FREE' in s and 'EngagedContactMode.STICK_STICK:' in s for s in d['mode'][m])
 ids=np.flatnonzero(m);i=ids[np.argmax(abs(d['loop.radial_shift_acceleration_N'][m]))]
 v=values(d,i);v['all_displayed_states_free_stick_stick']=True
 v['radial_fraction_of_opposing_belt_speed_term']=abs(v['loop.radial_shift_acceleration_N']/v['loop.tangential_belt_acceleration_N'])
 r['matched_rises'][case]=v
# Main reference table and supporting later-travel case use the same definition.
r['regional_shares']={}
for region in ('free_shift','engagement','midshift_load'):
 nominal=a['regions'][region+'_nominal'];tight=a['regions'][region+'_tight']
 for entry in (nominal,tight):
  assert np.isclose(sum(entry['share_percent'].values()),100,atol=1e-10,rtol=0)
  assert np.isclose(sum(entry['absolute_integrals_Ns'].values()),entry['absolute_sum_integral_Ns'])
 change=max(abs(tight['share_percent'][k]-nominal['share_percent'][k]) for k in tight['share_percent'])
 r['regional_shares'][region]={'start_s':tight['start_s'],'end_s':tight['end_s'],
  'percent':tight['share_percent'],'maximum_refinement_change_percentage_points':change}
# Main signed-percentage panel is the FAST member of the matched-rate comparison.
d=terms('rise50');m=(d['time_s']>=1.48)&(d['time_s']<=1.62)
assert all('CVTShiftConstraint.FREE' in s and 'EngagedContactMode.STICK_STICK:' in s for s in d['mode'][m])
assert np.min(d['loop.radial_shift_acceleration_N'][m])>0
assert np.min(d['loop.normal_contact_N'][m])>0
assert np.max(d['loop.tangential_belt_acceleration_N'][m])<0
keys=list(a['regions']['midshift_load_tight']['share_percent'])
residual=float(np.max(abs(sum(d['loop.'+k+'_N'][m] for k in keys))))
assert residual<1e-8
r['matched_fast_signed_display']={'window_s':[1.48,1.62],
 'all_states_free_stick_stick':True,'radial_and_contact_positive':True,
 'belt_acceleration_negative':True,'maximum_signed_five_term_sum_N':residual}
forces=np.array([d['loop.'+k+'_N'][m] for k in keys])
den=np.sum(abs(forces),axis=0)
assert np.min(den)>.0529
percent=100*forces/den
assert np.max(abs(np.sum(percent,axis=0)))<1e-6
assert np.allclose(np.sum(abs(percent),axis=0),100,atol=1e-10,rtol=0)
radial=keys.index('radial_shift_acceleration');i=np.argmax(percent[radial])
assert 24.9<percent[radial,i]<25
r['matched_fast_signed_display'].update({
 'normalization':'100 F_i(t) / sum_k |F_k(t)|',
 'sum_absolute_force_range_N':[float(np.min(den)),float(np.max(den))],
 'maximum_signed_sum_percentage_points':float(np.max(abs(np.sum(percent,axis=0)))),
 'radial_percentage_peak':{'time_s':float(d['time_s'][m][i]),
                          'signed_percent':{k:float(percent[j,i]) for j,k in enumerate(keys)}},
 'signed_percent_ranges':{k:[float(np.min(percent[j])),float(np.max(percent[j]))]
                         for j,k in enumerate(keys)}})
rates={};instantaneous={}
for case,folder,rise in [('rise800','controlled_18deg_800ms',.8),
                       ('rise200','controlled_18deg_200ms',.2),
                       ('rise50','controlled_18deg_050ms',.05)]:
 protocol=json.loads((P/'cases'/folder/'protocol.json').read_text())['controlled_load']
 assert protocol['kind']=='smooth_time_programmed_grade'
 assert protocol['start_time_s']==1.5 and protocol['target_grade_deg']==18.0
 assert np.isclose(protocol['rise_time_s'],rise)
 entry=a['terms'][case+'_tight_full']['load_rise']
 assert np.isclose(entry['start'],1.5) and np.isclose(entry['end'],1.5+rise)
 assert np.isclose(sum(entry['integrated_share'].values()),1)
 rates[case]={'share_percent':100*entry['integrated_share']['radial_shift_acceleration'],
              'peak_N':abs(entry['peak']['radial_shift_acceleration']['loop.radial_shift_acceleration_N'])}
 d=terms(case);den=sum(abs(d['loop.'+k+'_N']) for k in keys)
 ids=np.flatnonzero((d['time_s']>=1.5)&(d['time_s']<=1.5+rise)&(den>0))
 i=ids[np.argmax(abs(d['loop.radial_shift_acceleration_N'][ids])/den[ids])]
 instantaneous[case]={'maximum_sampled_share_percent':100*abs(float(d['loop.radial_shift_acceleration_N'][i]))/float(den[i]),
  'time_s':float(d['time_s'][i]),'radial_N':float(d['loop.radial_shift_acceleration_N'][i]),
  'sum_absolute_N':float(den[i])}
r['matched_rate_summary']=rates
r['instantaneous_rate_shares']=instantaneous
r['fast_to_slow_radial_peak_ratio']=rates['rise50']['peak_N']/rates['rise800']['peak_N']
assert 13.5<r['fast_to_slow_radial_peak_ratio']<13.7
d=terms('envelope');m=(d['time_s']>=2.4675)&(d['time_s']<=2.6075)
assert all('CVTShiftConstraint.FREE' in s and 'EngagedContactMode.STICK_STICK:' in s for s in d['mode'][m])
assert min(d['shift_speed'][m])<0<max(d['shift_speed'][m])
keys=list(a['regions']['midshift_load_tight']['share_percent'])
residual=float(np.max(abs(sum(d['loop.'+k+'_N'][m] for k in keys))))
assert residual<1e-8
r['midshift_display']={'window_s':[2.4675,2.6075],'all_states_free_stick_stick':True,
 'shift_changes_direction':True,'maximum_signed_five_term_sum_N':residual}
d=terms('contact_combined');m=(d['time_s']>=1.6)&(d['time_s']<=2.08)
r['combined_tune_support_window_peak_moving_radius_N']=float(max(abs(d['loop.tangential_shifting_radius_N'][m])))
r['omission']={};r['density']={}
for name,c in a['comparisons'].items():
 e=c['events'];case=name.split('_')[0]
 if name.endswith('_omission'):
  assert e['same_ordered_events_and_modes']
  if '_tight_' in name:
   ref=max(a['refinement'][name]['whole']['shift_mm'],a['refinement'][name.replace('_omission','_full')]['whole']['shift_mm'])
   assert c['whole']['shift_mm']<ref
   r['omission'][name]={'max_shift_um':1000*c['whole']['shift_mm'],'refinement_um':1000*ref,'max_event_time_us':1000*e['max_abs_event_time_difference_ms'],'same_event_mode_order_both_settings':a['comparisons'][name.replace('_tight_','_nominal_')]['events']['same_ordered_events_and_modes']}
 else:
  assert e['variant_count']==e['full_count']+2 and e['same_order_after_0_1s']
  r['density'][name]={'max_shift_mm':c['whole']['shift_mm'],'later_shift_mm':c['after_0_1s']['shift_mm'],'primary_rpm':c['whole']['primary_omega_rpm'],'full_events':e['full_count'],'lighter_events':e['variant_count'],'later_order_agrees':True}
# Check that plotted early positions contain both limits, not unique-time collapse.
for variant in ('full','density03'):
 p='flat_tight_'+variant+'__early_states__';t=z[p+'time_s'];seg=z[p+'segment_index']
 assert np.any((np.diff(t)==0)&(np.diff(seg)!=0))
r['early_positions_retain_segment_limits']=True
r['raw_files_in_verified_archive']=len(a['raw_sha256'])
r['compact_inputs_sha256']=a['plot_inputs_sha256']
(STUDY/'provenance/reader_checks.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({'matched_rise_masks':'free stick-stick','omission_pairs_at_two_settings':14,'density_pairs_at_two_settings':6,'early_positions':'segment limits retained','record':'provenance/reader_checks.json'},indent=2))
