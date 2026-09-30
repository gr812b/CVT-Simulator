"""Verify and compact the reference launch and selected backshift evidence.

No integration or simulator import. Native rows and event sides are retained.
Launch comes from the hashed primary-production archive, using FULL dynamics.
Backshift comes from run_secondary_backshift.py's frozen-release refinements.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import numpy as np
import sys
_release_root = Path(__file__).resolve().parents[3]
if str(_release_root) not in sys.path:
    sys.path.insert(0, str(_release_root))
from results_health.primary_source import primary_source

from audit_secondary_windows import csv_arrays, wrap_loading, PRIMARY, PREFIX

STUDY=Path(__file__).resolve().parents[1]
COMMIT='7637a38b4fb9ec21dfb953c1c80a27ec5f389654'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--primary-archive',type=Path)
    source.add_argument('--primary-dir',type=Path,
                        help='Fresh primary-publication raw directory; verifies full baseline provenance.')
    p.add_argument('--backshift-dir',type=Path,default=STUDY/'artifacts/secondary-backshift')
    p.add_argument('--output-dir',type=Path,default=STUDY/'publication_inputs')
    args=p.parse_args();out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    source, source_identity = primary_source(args.primary_archive, args.primary_dir, STUDY, PRIMARY, PREFIX)
    audit={'release_commit':COMMIT,'primary_source':source_identity,
           'primary_archive_sha256':source_identity.get('archive_sha256'),
           'launch':{},'backshift':{},'raw_sha256':{}}
    fields=['time_s','segment_index','sample_location','cvt_mode','shift_m','shift_speed_m_s',
        'helix_qs_reaction_force_N','helix_full_reaction_force_N','helix_dynamic_total_correction_N',
        'helix_dynamic_shaft_accel_force_N','helix_dynamic_shift_accel_force_N','helix_dynamic_curvature_force_N',
        'mass_helix_reflected_active_kg','mass_total_direct_active_kg','lambda_primary','lambda_secondary',
        'primary_min_local_normal_N_per_rad','secondary_min_local_normal_N_per_rad']
    arrays={};data={}
    with source as z:
        assembly=json.loads(z.read(PREFIX+'defaults/baja/simulation_case.json'))['assembly']
        old=json.loads(z.read(PRIMARY+'publication_inputs/primary_publication_audit.json'))
        for level in ('nominal','tight'):
            name=f'baseline_{level}_full';prefix=PRIMARY+'artifacts/primary-publication/'+name+'/'
            raw=z.read(prefix+'trajectory.csv.gz')
            digest=hashlib.sha256(raw).hexdigest()
            assert digest==old['raw_sha256'][name+'/trajectory.csv.gz']
            d=csv_arrays(raw);d.update(wrap_loading(d,assembly))
            for field in fields: arrays['launch_'+level+'__'+field]=d[field]
            e=np.isfinite(d['helix_qs_reaction_force_N']);i=int(np.flatnonzero(e)[0]);later=e&(d['time_s']>=.1)
            parts=sum(d['helix_dynamic_'+k+'_force_N'] for k in ('shaft_accel','shift_accel','curvature'))
            assert np.max(abs(parts[e]-d['helix_dynamic_total_correction_N'][e]))<1e-8
            for side in ('primary','secondary'):assert np.min(d[side+'_min_local_normal_N_per_rad'][e])>0
            audit['launch'][level]={'raw_sha256':digest,'first_engaged_index':i,
                'first_engaged':{k:d[k][i].item() for k in fields},
                'max_later_force_N':float(np.max(abs(parts[later]))),
                'max_later_fraction_percent':float(np.max(abs(100*parts[later]/d['helix_qs_reaction_force_N'][later]))),
                'helix_inertia_share_percent_range':[float(op(100*d['mass_helix_reflected_active_kg'][e]/d['mass_total_direct_active_kg'][e])) for op in (np.min,np.max)]}
    for torque in (120,240,480):
        for level in ('nominal','tight'):
            name=f'm{torque}_{level}';folder=args.backshift_dir/name
            meta=json.loads((folder/'summary.json').read_text())
            assert meta['release_commit']==COMMIT and meta['cinder_version']=='1.1.2'
            assert meta['completed'] and meta['segment_count']==1
            for filename,digest in meta['output_sha256'].items():
                assert sha(folder/filename)==digest
                audit['raw_sha256'][name+'/'+filename]=digest
            audit['raw_sha256'][name+'/summary.json']=sha(folder/'summary.json')
            d=csv_arrays((folder/'trajectory.csv.gz').read_bytes());data[name]=d
            local=csv_arrays((folder/'local_wrap_audit.csv.gz').read_bytes());d.update({k:local[k] for k in fields if k.endswith('_N_per_rad')})
            assert np.array_equal(d['time_s'],local['time_s'])
            assert all('STICK_STICK' in m and 'CVTShiftConstraint.FREE' in m for m in d['cvt_mode'])
            for side in ('primary','secondary'):
                assert np.min(d[side+'_min_local_normal_N_per_rad'])>0
                assert np.max(abs(d['lambda_'+side]))<.65
            parts=sum(d['helix_dynamic_'+k+'_force_N'] for k in ('shaft_accel','shift_accel','curvature'))
            assert np.max(abs(parts-d['helix_dynamic_total_correction_N']))<1e-8
            assert np.max(abs(d['helix_full_reaction_force_N']-d['helix_qs_reaction_force_N']-parts))<1e-8
            for field in fields:arrays[name+'__'+field]=d[field]
            geom=assembly['geometry'];travel=100*(d['shift_m']-geom['deadzone_shift_m'])/(geom['max_shift_m']-geom['deadzone_shift_m'])
            arrays[name+'__active_travel_percent']=travel
            active=d['time_s']>=.05;i=int(np.argmax(np.where(active,abs(parts),-np.inf)))
            audit['backshift'][name]={'settings':meta['settings'],'peak':{k:d[k][i].item() for k in fields},
                'peak_travel_percent':float(travel[i]),'peak_percent_of_qs':float(100*parts[i]/d['helix_qs_reaction_force_N'][i]),
                'max_fraction_percent':float(np.max(abs(100*parts[active]/d['helix_qs_reaction_force_N'][active]))),
                'min_correction_after_ramp_N':float(np.min(parts[d['time_s']>=.06])),
                'audit':meta['audit']}
        n,t=(data[f'm{torque}_{v}'] for v in ('nominal','tight'))
        assert np.array_equal(n['time_s'],t['time_s'])
        audit['backshift'][f'm{torque}_refinement']={
            'max_force_trace_change_N':float(np.max(abs(n['helix_dynamic_total_correction_N']-t['helix_dynamic_total_correction_N']))),
            'max_shift_trace_change_mm':float(1000*np.max(abs(n['shift_m']-t['shift_m'])))}
    # Independent motion comparisons. Full stress traces above are reused;
    # each reduction and no-added-load control has its own solved trajectory.
    # Do not treat the sampler's candidate full-force diagnostics on a QS
    # trajectory as forces actually present in that reduced model.
    motion_fields=['time_s','segment_index','sample_location','cvt_mode',
        'shift_m','shift_speed_m_s','lambda_primary','lambda_secondary',
        'primary_min_local_normal_N_per_rad','secondary_min_local_normal_N_per_rad']
    audit['backshift_response']={}
    for torque in (0,120,240,480):
        for level in ('nominal','tight'):
            for variant in ('full','qs'):
                name=f'm{torque}_{level}'+('_qs' if variant=='qs' else '')
                if name in data: continue
                folder=args.backshift_dir/name
                meta=json.loads((folder/'summary.json').read_text())
                assert meta['release_commit']==COMMIT and meta['cinder_version']=='1.1.2'
                assert meta['completed'] and meta['segment_count']==1
                assert meta['variant']==variant
                for filename,digest in meta['output_sha256'].items():
                    assert sha(folder/filename)==digest
                    audit['raw_sha256'][name+'/'+filename]=digest
                audit['raw_sha256'][name+'/summary.json']=sha(folder/'summary.json')
                d=csv_arrays((folder/'trajectory.csv.gz').read_bytes())
                local=csv_arrays((folder/'local_wrap_audit.csv.gz').read_bytes())
                assert np.array_equal(d['time_s'],local['time_s'])
                d.update({k:local[k] for k in motion_fields if k.endswith('_N_per_rad')})
                assert all('STICK_STICK' in m and 'CVTShiftConstraint.FREE' in m for m in d['cvt_mode'])
                for side in ('primary','secondary'):
                    assert np.min(d[side+'_min_local_normal_N_per_rad'])>0
                    assert np.max(abs(d['lambda_'+side]))<.65
                if variant=='qs':
                    assert set(d['variant'])=={'quasi_static_helix'}
                    assert np.max(abs(d['mass_helix_reflected_active_kg']))==0
                for field in motion_fields: arrays[name+'__'+field]=d[field]
                data[name]=d
                audit['backshift_response'][name]={'settings':meta['settings'],'audit':meta['audit'],
                    'initial_reaction_guard_Nm':meta['initial_reaction_guard_Nm']}
    for torque in (120,240,480):
        deltas={}
        for level in ('nominal','tight'):
            f,q,fc,qc=(data[n] for n in (f'm{torque}_{level}',f'm{torque}_{level}_qs',f'm0_{level}',f'm0_{level}_qs'))
            assert all(np.array_equal(f['time_s'],d['time_s']) for d in (q,fc,qc))
            assert all(d['shift_m'][0]==f['shift_m'][0] for d in (q,fc,qc))
            fr=1000*(f['shift_m']-fc['shift_m']);qr=1000*(q['shift_m']-qc['shift_m'])
            delta=fr-qr;deltas[level]=delta
            pre=f'response_m{torque}_{level}__'
            for field,value in [('time_s',f['time_s']),('full_shift_mm',fr),('qs_shift_mm',qr),('full_minus_qs_shift_mm',delta)]:arrays[pre+field]=value
            active=f['time_s']>=.05;i=int(np.argmax(np.where(active,abs(delta),-np.inf)))
            audit['backshift_response'][f'm{torque}_{level}_comparison']={
                'max_abs_shift_response_difference_mm':float(abs(delta[i])),
                'signed_shift_response_difference_at_peak_mm':float(delta[i]),
                'time_at_peak_s':float(f['time_s'][i]),'full_response_at_peak_mm':float(fr[i]),
                'qs_response_at_peak_mm':float(qr[i]),
                'max_preload_response_residual_mm':float(max(np.max(abs(fr[~active])),np.max(abs(qr[~active]))))}
        audit['backshift_response'][f'm{torque}_refinement']={
            'max_change_in_response_difference_mm':float(np.max(abs(deltas['nominal']-deltas['tight'])))}
    np.savez_compressed(out/'secondary_story.npz',**arrays)
    audit['plot_inputs_sha256']=sha(out/'secondary_story.npz')
    audit['scope']='Full-trajectory forces and independent full/QS backshift loaded-minus-own-control responses. No secondary-QS launch trajectory claim. OTS comparison is in secondary_publication.npz.'
    (out/'secondary_story_audit.json').write_text(json.dumps(audit,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in audit['backshift'].items() if k.endswith('refinement')},indent=2))


if __name__=='__main__':main()
