"""Re-run historically helix-limited states under the slotted results reference model.

These probes are descriptive capability evidence only. They are not required for
mechanical-invariants PASS. Their purpose is to confirm whether removing the
selected-flank helix inequality exposes a clean belt/contact continuation, or
whether a different retained belt/traction/topology limit appears next.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
RELEASE_ROOT=HERE.parents[1]
if str(RELEASE_ROOT) not in sys.path:
    sys.path.insert(0,str(RELEASE_ROOT))

from support.reference_model import decode_results_simulation_case_document, reference_model_status

spec=importlib.util.spec_from_file_location('mechanical_invariants_core_for_probes', HERE/'run.py')
if spec is None or spec.loader is None:
    raise RuntimeError('Could not load run.py')
core=importlib.util.module_from_spec(spec); sys.modules[spec.name]=core; spec.loader.exec_module(core)


def _validate_and_decode_results(document: dict):
    report=core.validate_simulation_case_document(document)
    if not report.is_valid:
        raise RuntimeError(f'Invariant-study input failed validation: {report.findings}')
    return decode_results_simulation_case_document(document)


core.validate_and_decode=_validate_and_decode_results
CASE_LIBRARY=(HERE/'../../defaults/verification_operating_cases.json').resolve()
OUT=HERE/'artifacts'/'capability_probe_states.csv'


def finite_min(values):
    vals=[]
    for value in values:
        try: x=float(value)
        except (TypeError,ValueError): continue
        if math.isfinite(x): vals.append(x)
    return min(vals) if vals else float('nan')


def write_rows(rows):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if not rows: OUT.write_text('',encoding='utf-8'); return
    fields=[]; seen=set()
    for row in rows:
        for key in row:
            if key not in seen: seen.add(key); fields.append(key)
    with OUT.open('w',newline='',encoding='utf-8') as h:
        wr=csv.DictWriter(h,fieldnames=fields); wr.writeheader(); wr.writerows(rows)


def main()->int:
    library=json.loads(CASE_LIBRARY.read_text(encoding='utf-8'))
    raw_spec=json.loads((HERE/'study.json').read_text(encoding='utf-8'))
    hydrated=core.hydrate_case_recipes(raw_spec,library)
    guards=hydrated['review_guards']
    decoded,_,_=core.load_frozen_reference(hydrated)
    topology=reference_model_status(decoded.plant).secondary_helix_topology
    requests={r.case_id:r for r in core.contact_requests(library)}
    cfg=library['targeted_contact_state_integrator']
    settings=core.integration_settings(cfg)
    rows=[]
    for seed in library.get('capability_probe_states',[]):
        target=str(seed['target']); request=requests[target]
        system=core.make_bench_system(decoded,
            primary_torque=float(seed['primary_torque_Nm']),secondary_torque=float(seed['secondary_torque_Nm']),
            primary_inertia=float(seed['primary_inertia_kg_m2']),secondary_inertia=float(seed['secondary_inertia_kg_m2']))
        cvt=core.CVTState(float(seed['primary_speed_rad_s']),float(seed['secondary_speed_rad_s']),float(seed['belt_speed_m_s']),float(seed['shift_position_m']),float(seed['shift_speed_m_s']))
        state=core.full_state(system,cvt)
        row={'probe_id':seed['id'],'target':target,'historical_termination':seed.get('historical_termination',''),'results_helix_topology':topology}
        try:
            mode=system.classify_initial_mode(state)
            row['classifier_mode']=mode.cvt.contact_regime.mode.value if mode.cvt.contact_regime else ''
            row['classifier_matches_target']=core.mode_and_directions_match(mode,request)
            initial,_,_=core.audit_sample_safe(system,core.AuditSample(seed['id'],0.0,state,mode,'initial_exact'))
            initial_fail=core.hard_row_failures(initial,guards)
            row['initial_failures']='|'.join(initial_fail)
            if not row['classifier_matches_target'] or initial_fail:
                row['status']='INITIAL_REJECT'; rows.append(row); continue
            trace=system.integrate_trace(time_span=(0.0,float(cfg['duration_s'])),initial_state=state,initial_mode=mode,settings=settings)
            row['trace_completed']=trace.completed; row['trace_termination_reason']=trace.termination_reason
            row['requested_branch_dwell_s']=float(trace.segments[0].end_time-trace.segments[0].start_time)
            samples=[]; failures=[]
            for sample in core.build_trace_samples(seed['id'],trace,float(cfg['audit_time_step_s'])):
                rr,_,_=core.audit_sample_safe(system,sample); samples.append(rr); failures.extend(core.hard_row_failures(rr,guards))
            successors=core.post_transition_rows(seed['id'],system,trace)
            successor_fail=[]
            for rr in successors:
                if rr.get('successor_exists'): successor_fail.extend(core.hard_row_failures(rr,guards))
            row['sample_failures']='|'.join(sorted(set(failures)))
            row['successor_failures']='|'.join(sorted(set(successor_fail)))
            row['transitions']=len(trace.transitions)
            row['min_belt_tension_N']=finite_min(r.get('belt_min_tension_N') for r in samples)
            row['min_primary_local_normal_N_per_rad']=finite_min(r.get('primary_min_dnormal_dtheta_N_per_rad') for r in samples)
            row['min_secondary_local_normal_N_per_rad']=finite_min(r.get('secondary_min_dnormal_dtheta_N_per_rad') for r in samples)
            row['min_primary_normal_N']=finite_min(r.get('normal_primary_N') for r in samples)
            row['min_secondary_normal_N']=finite_min(r.get('normal_secondary_N') for r in samples)
            row['first_transition_event']='|'.join(trace.transitions[0].fired_event_names) if trace.transitions else ''
            row['first_transition_reason']=trace.transitions[0].transition.reason if trace.transitions else ''
            row['status']='PASS' if trace.completed and not failures and not successor_fail else 'REVIEW'
        except Exception as exc:
            row['status']='ERROR'; row['error']=f'{type(exc).__name__}: {exc}'
        rows.append(row)
    write_rows(rows)
    print(f'Wrote {OUT}')
    for row in rows: print(row['probe_id'],row['status'])
    return 0 if all(r['status']=='PASS' for r in rows) else 2


if __name__=='__main__':
    raise SystemExit(main())
