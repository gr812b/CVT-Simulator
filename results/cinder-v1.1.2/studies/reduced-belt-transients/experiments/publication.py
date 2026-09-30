"""Selected belt publication runs; frozen CINDER, separate output, exact events.

The joint omission replaces C=q(v²-r r' sddot-r r'' sdot²) by
C=q(v²-r r' sddot), and A=q(r vdot+r' sdot v) by A=q r vdot in
both wrap maps. Other continuous equations, contact laws and resets are retained.
This is a study-local equation reduction, not a new release or exact massless law.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import replace
import csv
import gzip
import hashlib
import io
import json
from math import sin
from pathlib import Path
import sys
import time
import numpy as np
from results_health.common import simulation_fingerprint

STUDY = Path(__file__).resolve().parents[1]
RELEASE = STUDY.parents[1]
SETTINGS = {
    'nominal': (1e-6, 1e-9, .01),
    'tight': (1e-7, 1e-10, .005),
}
CASES = {
    'flat': 'inertia_flat_reference',
    'loading': 'inertia_fast_backshift_reference',
    'unloading': 'inertia_fast_unload_reference',
    'rise50': 'controlled_18deg_050ms',
    'rise200': 'controlled_18deg_200ms',
    'rise800': 'controlled_18deg_800ms',
    'envelope': 'envelope_05',
    'contact': 'contact_primary_45',
    'contact_combined': 'contact_combined_p40_s20',
    'overrun_mild': 'overrun_mild',
    'overrun_strong': 'overrun_strong',
}

def run_schedule(output):
    """Independent processes are required because the omission hook is process-local."""
    from concurrent.futures import ThreadPoolExecutor
    import os
    import subprocess
    plan=json.loads((STUDY/'publication_inputs/run_plan.json').read_text())
    output.mkdir(parents=True,exist_ok=True)
    def run(job):
        name='{case}_{level}_{variant}'.format(**job)
        summary=output/name/'summary.json'
        if summary.exists():
            s=json.loads(summary.read_text())
            if s.get('simulation_fingerprint') != simulation_fingerprint(STUDY):
                raise ValueError('Generator/input changed; use a new raw directory: '+name)
            if not s.get('completed'):
                raise ValueError('Incomplete run cannot be reused: '+name)
            if (s.get('case'),s.get('level'),s.get('variant')) != (job['case'],job['level'],job['variant']):
                raise ValueError('Cached run identity mismatch: '+name)
            for f,d in s['source_sha256'].items():
                if sha(RELEASE/f)!=d:
                    raise ValueError('Generator/input changed; use a new raw output directory: '+f)
            for f,d in s['output_sha256'].items():
                if sha(summary.parent/f)!=d:raise ValueError('Changed output '+name+'/'+f)
            return name+' REUSED'
        env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
        cmd=[sys.executable,str(STUDY/'run.py'),'--publication','run','--publication-case',job['case'],
             '--publication-variant',job['variant'],'--publication-level',job['level'],
             '--publication-dir',str(output)]
        with (output/(name+'.log')).open('w') as log:
            p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env)
        return name+(' DONE' if p.returncode==0 else ' FAILED (see log)')
    with ThreadPoolExecutor(max_workers=4) as pool:
        messages = list(pool.map(run, plan))
        for message in messages:
            print(message, flush=True)
        if any(' FAILED ' in message for message in messages):
            raise RuntimeError('Publication runs failed; see the named logs.')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def write_json(p, value):
    p.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')

def write_rows(p, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    s=io.StringIO(newline=''); w=csv.DictWriter(s,fieldnames=fields)
    w.writeheader(); w.writerows(rows)
    p.write_bytes(gzip.compress(s.getvalue().encode(),mtime=0))

@contextmanager
def omit_two_terms(enabled=True):
    """Patch only this process; restore even after a failed continuation."""
    from cinder.model.cvt.dynamics.rows import tension_loop as m
    radial, tangential = m._radial_offset, m._tangential_offset
    def r(**kw):
        return radial(**{**kw, 'd2_radius_ds2': 0.})
    def a(**kw):
        return tangential(**{**kw, 'd_radius_ds': 0.})
    if enabled:
        m._radial_offset, m._tangential_offset = r, a
    try:
        yield
    finally:
        m._radial_offset, m._tangential_offset = radial, tangential

def wrap_audit(inspection, omitted):
    """Analytical endpoint extrema using the SAME offsets as the solved row.

    Within each circular wrap, T-C is an affine function of exp(-lambda theta/
    sin(beta)), or a linear function at zero lambda. Thus its extrema are at
    the endpoints. No angular sampling or total-normal proxy is used.
    """
    from cinder.model.cvt.dynamics.equation_context import TrialEquationContext
    c=inspection.contact; u=inspection.closure_unknowns
    sn=c.snapshot; g=sn.geometry; st=sn.state; q=sn.belt_linear_density
    ct=TrialEquationContext(snapshot=sn, traction_utilization=c.traction_utilization).contact_terms
    result={}; sums=[]
    for side in ('primary','secondary'):
        r=getattr(g,side); phi=getattr(g,side+'_wrap_angle')
        C=q*(st.belt_speed**2-r.center_of_mass*(r.d_center_of_mass_ds*u.shift_acceleration
            +(0. if omitted else r.d2_center_of_mass_ds2*st.shift_speed**2)))
        A=q*(r.center_of_mass*u.belt_acceleration
            +(0. if omitted else r.d_center_of_mass_ds*st.shift_speed*st.belt_speed))
        P=getattr(ct,side+'_phi_minus'); Q=getattr(ct,side+'_psi_minus'); E=getattr(ct,side+'_exp_neg')
        sb=sin(sn.sheave_half_angle); N=getattr(u,side+'_normal_resultant')
        entry=C+N*sb/(phi*P)-A*phi*Q/P
        leave=C+E*(entry-C)+A*phi*P
        result[side+'.min_tension_N']=min(entry,leave)
        result[side+'.min_local_normal_N_per_rad']=min(entry-C,leave-C)/sb
        result[side+'.entry_tension_N']=entry; result[side+'.exit_tension_N']=leave
        sums.append(entry+leave)
    result['wrap.endpoint_sum_residual_N']=sums[0]-sums[1]
    return result

def configure(system, protocol):
    from infrastructure.protocol_support import (SmoothGradeProgram, SmoothOverrunProgram,
        make_time_programmed_boundary, make_overrun_boundaries)
    if 'controlled_overrun' in protocol:
        cfg={k:v for k,v in protocol['controlled_overrun'].items() if k!='kind'}
        system.primary_boundary,system.secondary_boundary=make_overrun_boundaries(
            base_primary=system.primary_boundary,base_secondary=system.secondary_boundary,
            program=SmoothOverrunProgram(**cfg))
        return cfg
    if 'controlled_load' in protocol:
        cfg={k:v for k,v in protocol['controlled_load'].items() if k!='kind'}
        system.secondary_boundary=make_time_programmed_boundary(base_boundary=system.secondary_boundary,
            program=SmoothGradeProgram(**cfg))
        return cfg
    return {}

def grids(end, cfg):
    # Values are sampled with solver-native dense output WITHIN each segment.
    dense=np.unique(np.r_[np.arange(0,end+.0001,.001),np.arange(0,.15,.00005)])
    diagnostics=np.unique(np.r_[np.arange(0,end+.0001,.005),np.arange(0,.15,.00025)])
    if cfg:
        a=cfg['start_time_s']; b=min(end,a+cfg['rise_time_s']+ .6)
        dense=np.unique(np.r_[dense,np.arange(max(0,a-.05),b,.00025),a,a+cfg['rise_time_s']])
        diagnostics=np.unique(np.r_[diagnostics,np.arange(max(0,a-.03),b,.001),a,a+cfg['rise_time_s']])
    return dense[dense<=end],diagnostics[diagnostics<=end]

def run_one(case, variant, level, output):
    import cinder, scipy, matplotlib
    from cinder.results import CVTResultBuilder, inspect_cvt_state
    from cinder.model.cvt.contact.relative_motion import ContactInterface
    from defaults.reference_model import decode_reference_case
    from infrastructure.belt_terms import inspect_final_belt_terms
    from infrastructure.trajectory_audit import _boundary_context
    assert cinder.__version__=='1.1.2'
    cp=Path(cinder.__file__).resolve()
    assert 'site-packages' in cp.parts, 'Live source must not enter frozen runs'
    source=STUDY/'publication_inputs/cases'/CASES[case]
    document=json.loads((source/'simulation_case.json').read_text())
    protocol=json.loads((source/'protocol.json').read_text())
    rtol,atol,step=SETTINGS[level]
    document['execution']['integrator'].update(relative_tolerance=rtol,absolute_tolerance=atol,max_step=step)
    if variant=='density03':
        document['assembly']['inertias']['belt_density_kg_per_m3']*=.03
    elif variant not in ('full','omission'):
        raise ValueError(variant)
    decoded=decode_reference_case(document); system=decoded.system
    cfg=configure(system,protocol)
    out=output/f'{case}_{level}_{variant}'
    out.mkdir(parents=True,exist_ok=True)
    if (out/'summary.json').exists():
        raise FileExistsError(f'Preserving completed run: {out}')
    write_json(out/'simulation_case.json',document);write_json(out/'protocol.json',protocol)
    start=time.monotonic();print('START',out.name,flush=True)
    try:
        with omit_two_terms(variant=='omission'):
            trace=system.integrate_trace(time_span=decoded.time_span,initial_state=decoded.initial_state,
                initial_mode=decoded.initial_mode,settings=decoded.integrator_settings)
            print('INTEGRATED',out.name,len(trace.segments),trace.completed,flush=True)
            builder=CVTResultBuilder(system=system)
            dense_grid,diag_grid=grids(trace.final_time,cfg)
            states=[]; rows=[]; segments=[]; arrays={}; errors=[]
            for si,seg in enumerate(trace.segments):
                mode=builder._cvt_mode(seg.mode)
                segments.append({'segment_index':si,'start_s':seg.start_time,'end_s':seg.end_time,
                    'mode':str(mode),'events':list(seg.fired_event_names)})
                arrays[f's{si}_time']=seg.time;arrays[f's{si}_state']=seg.state
                for grid, target, inspect in [(dense_grid,states,False),(diag_grid,rows,True)]:
                    t=np.unique(np.r_[seg.start_time,grid[(grid>seg.start_time)&(grid<seg.end_time)],seg.end_time])
                    # Native accepted steps additionally support peak/event audits.
                    if inspect:t=np.unique(np.r_[t,seg.time])
                    y=seg.dense_state_at(t)
                    cv=builder._cvt_state_matrix(y)
                    for j,now in enumerate(t):
                        loc='start' if j==0 else 'end' if j==len(t)-1 else 'interior'
                        row={'time_s':float(now),'segment_index':si,'sample_location':loc,'mode':str(mode)}
                        for k,key in enumerate(('primary_omega','secondary_omega','belt_speed','shift','shift_speed')):
                            row[key]=float(cv[k,j])
                        if inspect:
                            b,bc=_boundary_context(builder,time=float(now),full_state=y[:,j])
                            try:
                                ins=inspect_cvt_state(system=builder._cvt_system,time=float(now),vector=cv[:,j],
                                    mode=mode,shaft_boundaries=b,include_closure_audit=True)
                                terms=inspect_final_belt_terms(ins)
                                if terms is None:continue
                                row.update(terms);row.update(bc);row.update(wrap_audit(ins,variant=='omission'))
                                if variant=='omission':
                                    # Retain omitted full-law values for transparency; audited balance is reduced.
                                    row['loop.omitted_full_law_sum_N']=sum(row[k] for k in (
                                        'loop.radial_geometry_curvature_N','loop.tangential_shifting_radius_N'))
                                    row['loop.residual_N']-=row['loop.omitted_full_law_sum_N']
                                row['closure.max_abs_residual']=max(abs(r.value) for r in ins.closure_audit.equation_residuals)
                                row['boundary.primary_power_W']=ins.primary_external_torque*ins.state.primary_angular_speed
                                row['boundary.secondary_power_W']=ins.secondary_external_torque*ins.state.secondary_angular_speed
                                for side in ('primary','secondary'):
                                    interface=ContactInterface(side)
                                    sticking=mode.contact_regime.mode.sticking_interfaces
                                    row[side+'.sticking']=interface in sticking
                                    row[side+'.relative_speed']=getattr(ins.contact.relative_motion,side+'_relative_speed')
                                    row[side+'.relative_acceleration']=getattr(ins.contact.relative_motion,side+'_relative_acceleration')
                            except Exception as exc:
                                errors.append({'time_s':float(now),'segment':si,'location':loc,'error':repr(exc)})
                                continue
                        target.append(row)
            events=[]
            for i,e in enumerate(trace.transitions):
                pre=trace.segments[i].state[:,-1]
                events.append({'time_s':e.time,'previous_mode':str(e.previous_mode),
                    'next_mode':str(e.transition.next_mode),'events':list(e.fired_event_names),
                    'reason':e.transition.reason,'pre_state':pre.tolist(),
                    'post_state':e.post_transition_state.tolist()})
            np.savez_compressed(out/'native.npz',**arrays)
            write_rows(out/'states.csv.gz',states);write_rows(out/'terms.csv.gz',rows)
            write_json(out/'events.json',events);write_json(out/'segments.json',segments)
            write_json(out/'inspection_errors.json',errors)
            metrics={'engaged_samples':len(rows),'inspection_errors':len(errors)}
            for key in ('closure.max_abs_residual','loop.residual_N','transport.residual_N','wrap.endpoint_sum_residual_N'):
                metrics[key]=max((abs(r[key]) for r in rows),default=None)
            for side in ('primary','secondary'):
                for k in ('min_tension_N','min_local_normal_N_per_rad'):
                    metrics[side+'.'+k]=min((r[side+'.'+k] for r in rows),default=None)
                stick=[r for r in rows if r[side+'.sticking']]
                metrics[side+'.max_sticking_speed_mps']=max((abs(r[side+'.relative_speed']) for r in stick),default=None)
                metrics[side+'.max_sticking_acceleration_mps2']=max((abs(r[side+'.relative_acceleration']) for r in stick),default=None)
            sources=[Path(__file__),*STUDY.glob('infrastructure/*.py'),*RELEASE.glob('defaults/**/*.py'),
                *RELEASE.glob('defaults/**/*.json'),*source.glob('*.json')]
            summary={'simulation_fingerprint':simulation_fingerprint(STUDY),'case':case,'variant':variant,'level':level,'completed':trace.completed,
                'termination_reason':trace.termination_reason,'final_time_s':trace.final_time,
                'segments':len(segments),'transitions':len(events),'audit':metrics,
                'settings':{'rtol':rtol,'atol':atol,'max_step_s':step},'boundary_programme':cfg,
                'runtime':{'cinder':cinder.__version__,'cinder_path':str(cp),'numpy':np.__version__,
                    'scipy':scipy.__version__,'matplotlib':matplotlib.__version__,'python':sys.version},
                'release_commit':'7637a38b4fb9ec21dfb953c1c80a27ec5f389654',
                'source_sha256':{str(p.relative_to(RELEASE)):sha(p) for p in sorted(set(sources))},
                'output_sha256':{p.name:sha(p) for p in out.iterdir() if p.is_file()},
                'elapsed_s':time.monotonic()-start}
            write_json(out/'summary.json',summary)
            print('DONE',out.name,summary['elapsed_s'],metrics,flush=True)
    except Exception as exc:
        write_json(out/'failure.json',{'error':repr(exc),'elapsed_s':time.monotonic()-start})
        raise
