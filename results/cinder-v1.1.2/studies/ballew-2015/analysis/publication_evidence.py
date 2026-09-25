"""Audit raw executions and retain compact, exact publication inputs."""
from __future__ import annotations

# --- results study-local import bootstrap ---
from pathlib import Path as _ResultsPath
import sys as _results_sys

_results_file = _ResultsPath(__file__).resolve()
_results_study_root = next(
    (parent for parent in _results_file.parents if (parent / "study.json").is_file()),
    None,
)
if _results_study_root is None:
    raise RuntimeError(f"Could not locate study root for {_results_file}")
_results_release_root = _results_study_root.parents[1]
for _results_path in (str(_results_study_root), str(_results_release_root)):
    while _results_path in _results_sys.path:
        _results_sys.path.remove(_results_path)
_results_sys.path.insert(0, str(_results_release_root))
_results_sys.path.insert(0, str(_results_study_root))

# --- end results study-local import bootstrap ---

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def verify_execution(d):
    p=json.loads((d/'execution_provenance.json').read_text())
    assert p['cinder_version']=='1.1.2'
    assert p['cinder_tag_commit']=='7637a38b4fb9ec21dfb953c1c80a27ec5f389654'
    for name,h in p['input_sha256'].items():
        assert sha(d/'execution_inputs'/name)==h,(d,name)
    for name,h in p['output_sha256'].items():
        assert sha(d/name)==h,(d,name)
    return p


def metrics_check(d):
    metrics=json.loads((d/'metrics.json').read_text())
    assert metrics['completed'] and metrics['final_time_s']==5
    out={}
    for name,m in metrics['metrics'].items():
        data=np.genfromtxt(d/f'{name}_comparison.csv',delimiter=',',names=True)
        a,b=(data[n] for n in data.dtype.names[1:3])
        rmse=np.sqrt(np.mean((b-a)**2))
        percent=100*rmse/np.mean(np.abs(a))
        assert np.isclose(rmse,m['root_mean_square_error'],rtol=1e-12,atol=1e-12)
        assert np.isclose(percent,m['rmse_percent_of_reference_mean'],rtol=1e-12)
        out[name]={'rmse':float(rmse),'percent':float(percent),'samples':len(a)}
    return out


def trace_check(d):
    manifest=json.loads((d/'trace_manifest.json').read_text())
    r=np.load(d/'segmented_report.npz');n=np.load(d/'native_trace.npz')
    assert sum(manifest['mode_duration_s'].values())==5 or np.isclose(sum(manifest['mode_duration_s'].values()),5,atol=1e-12)
    for data in (r,n):
        for seg in manifest['segments']:
            ix=np.flatnonzero(data['segment_id']==seg['id'])
            assert data['time_s'][ix[0]]==seg['start_s']
            assert data['time_s'][ix[-1]]==seg['end_s']
            assert np.all(np.diff(data['time_s'][ix])>=0)
    for k,i in [('state.primary_angular_speed',0),('state.secondary_angular_speed',1)]:
        assert np.array_equal(n['full_state'][i,[0,-1]],r[k][[0,-1]])
    losses={}
    for side in ('primary','secondary'):
        power=np.abs(r[f'contact.{side}_transmitted_torque']/r[f'geometry.{side}_effective_radius']*r[f'contact.{side}_relative_speed'])
        ids=r['segment_id'];value=0.;coarse=0.
        for i in np.unique(ids):
            ix=np.flatnonzero(ids==i);jx=np.unique(np.r_[ix[::2],ix[-1]])
            value+=np.trapezoid(power[ix],r['time_s'][ix])
            coarse+=np.trapezoid(power[jx],r['time_s'][jx])
        recorded=r[f'observer.{side}_slip_dissipation']
        assert np.isclose(value,recorded[-1],rtol=1e-12)
        assert np.min(np.diff(recorded))>=-1e-9
        losses[side]={'reported_J':float(value),'decimated_quadrature_difference_J':float(coarse-value)}
    ratio=r['geometry.effective_ratio_secondary_over_primary']
    return {'events':len(manifest['events']), 'all_segment_sides_retained':True,
            'radius_ratio_min':float(min(ratio)), 'radius_ratio_max':float(max(ratio)),
            'slip_loss':losses,'mode_duration_s':manifest['mode_duration_s'],
            'transition_reasons':manifest['transition_reasons']}


def dense_modes(manifest,t):
    modes=np.empty(t.size,dtype='U100')
    for s in manifest['segments']:
        mask=(t>=s['start_s'])&(t<=s['end_s']);modes[mask]=s['mode']
    return modes


def refinement(base,cases):
    nominal=base/cases[0]['artifact_path'];a=np.load(nominal/'comparison_grid.npz')
    ma=json.loads((nominal/'trace_manifest.json').read_text())
    mode_a=dense_modes(ma,a['time_s']);rows=[]
    scales=np.array([30/np.pi,30/np.pi,1,1000,1])
    names=('primary_rpm','secondary_rpm','belt_speed_m_per_s','shift_mm','shift_speed_m_per_s')
    skip='kinetic_slip_direction_updated_at_zero_crossing'
    ea=[e for e in ma['events'] if e['reason']!=skip]
    for case in cases:
        d=base/case['artifact_path'];b=np.load(d/'comparison_grid.npz')
        mb=json.loads((d/'trace_manifest.json').read_text());assert np.array_equal(a['time_s'],b['time_s'])
        assert np.array_equal(b['full_state'][:5],b['cvt_state'])
        diff=(b['cvt_state']-a['cvt_state'])*scales[:,None]
        vals={name:{'rms':float(np.sqrt(np.mean(v*v))),'maximum_absolute':float(np.max(np.abs(v)))} for name,v in zip(names,diff)}
        # Primary force follows the exact reconstructed controller state, not
        # interpolation of a coarse output curve. Integral state is last.
        force_a=2400+5*(a['cvt_state'][0]*30/np.pi-2500)+75*a['full_state'][-1]
        force_b=2400+5*(b['cvt_state'][0]*30/np.pi-2500)+75*b['full_state'][-1]
        delta=force_b-force_a
        vals['primary_force_N']={'rms':float(np.sqrt(np.mean(delta**2))),
                                 'maximum_absolute':float(np.max(np.abs(delta)))}
        eb=[e for e in mb['events'] if e['reason']!=skip]
        sequence_equal=[(e['reason'],e['previous_mode'],e['next_mode']) for e in ea]==[(e['reason'],e['previous_mode'],e['next_mode']) for e in eb]
        event_dt=max(abs(x['time_s']-y['time_s']) for x,y in zip(ea,eb)) if sequence_equal else None
        mode_b=dense_modes(mb,b['time_s']);same_mode=mode_a==mode_b
        peak=int(np.argmax(np.abs(diff[4])))
        rows.append({**case, 'common_grid_samples':a['time_s'].size,
          'shift_speed_peak_difference':{'time_s':float(a['time_s'][peak]),
            'nominal_mode':str(mode_a[peak]),'comparison_mode':str(mode_b[peak]),
            'maximum_when_same_mode_m_per_s':float(np.max(np.abs(diff[4,same_mode])))},
          'difference_from_nominal':vals,
          'common_grid_mode_mismatch_count':int(np.count_nonzero(mode_a!=dense_modes(mb,b['time_s']))),
          'sequence_excluding_direction_updates_equal':sequence_equal,
          'event_count_excluding_direction_updates':len(eb),
          'maximum_matched_event_time_difference_s':event_dt,
          'mode_duration_s':mb['mode_duration_s'], 'transition_reasons':mb['transition_reasons']})
    return rows


def freeze(base,out,cases,audit):
    out.mkdir(parents=True,exist_ok=True)
    dirs=['closed-loop','force-replay']+[c['artifact_path'] for c in cases[1:]]
    derivations={}
    for name in dirs:
        src=base/name;dst=out/name;dst.mkdir(parents=True,exist_ok=True)
        for f in ['metrics.json','trace_manifest.json','execution_provenance.json']+[p.name for p in src.glob('*_comparison.csv')]:
            shutil.copy2(src/f,dst/f)
        r=np.load(src/'segmented_report.npz')
        keys=['time_s','segment_id','state.primary_angular_speed','state.secondary_angular_speed',
              'geometry.effective_ratio_secondary_over_primary','actuation.primary.total_clamp_force',
              'observer.primary_slip_dissipation','observer.secondary_slip_dissipation']
        np.savez_compressed(dst/'segmented_report.npz',**{k:r[k] for k in keys})
        n=np.load(src/'native_trace.npz')
        np.savez_compressed(dst/'native_trace.npz',time_s=n['time_s'],segment_id=n['segment_id'],
            **{'state.primary_angular_speed':n['full_state'][0],
               'state.secondary_angular_speed':n['full_state'][1]})
        # Needed for transparent same-clock refinement reanalysis; full state
        # includes the controller integral. No dense interpolation across events.
        if name!='force-replay':shutil.copy2(src/'comparison_grid.npz',dst/'comparison_grid.npz')
        derivations[name]={'source_execution_manifest_sha256':sha(src/'execution_provenance.json'),
            'report_selection':keys,'native_state_indices':{'primary':0,'secondary':1},
            'arrays_copied_without_resampling':True}
    shutil.copy2(base/'convergence/convergence.json',out/'convergence.json')
    (out/'evidence_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    files={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='publication_inputs.json'}
    record={'cinder_version':'1.1.2','cinder_tag_commit':'7637a38b4fb9ec21dfb953c1c80a27ec5f389654',
            'derivations':derivations,'files':files,
            'note':'Compact plot and refinement inputs selected from hash-verified full executions. Full output hashes and executed source snapshots are retained in the delivery evidence archive.'}
    (out/'publication_inputs.json').write_text(json.dumps(record,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts',type=Path,default=ROOT/'artifacts')
    p.add_argument('--freeze-to',type=Path)
    args=p.parse_args();base=args.artifacts
    cases=json.loads((base/'convergence/convergence.json').read_text())['cases']
    assert len(cases)==4 and all(c['completed'] for c in cases)
    details={}
    for name in ['closed-loop','force-replay']+[c['artifact_path'] for c in cases[1:]]:
        verify_execution(base/name)
        details[name]={'metrics':metrics_check(base/name),'trace':trace_check(base/name)}
    result={'raw_execution_hashes_verified':True,'all_five_runs_completed':True,
            'runs':details,'refinement':refinement(base,cases)}
    (base/'evidence_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    if args.freeze_to:freeze(base,args.freeze_to,cases,result)
    print(json.dumps({'runs':len(details),'refinement':[{'case':r['label'],
       'sequence_equal':r['sequence_excluding_direction_updates_equal'],
       'event_time_difference_s':r['maximum_matched_event_time_difference_s'],
       'differences':r['difference_from_nominal']} for r in result['refinement']]},indent=2))

if __name__=='__main__':main()
