"""One competitor = one process-isolated CINDER trajectory."""
from __future__ import annotations
import json
from pathlib import Path
from time import perf_counter
import traceback
import numpy as np
from infrastructure.common import write_json,write_csv,json_safe,utc_now
from infrastructure.course import Course
from infrastructure.model import build_system,WatchedSystem
from infrastructure.diagnostics import inspect_row,mechanism_map,mode_fields
from analysis.metrics import summarize,nominate_windows


def nested_values(obj,key):
    if isinstance(obj,dict):
        if key in obj: yield obj[key]
        for value in obj.values(): yield from nested_values(value,key)
    elif isinstance(obj,(tuple,list)):
        for value in obj: yield from nested_values(value,key)


def sample_segment(seg,step):
    start=float(seg.start_time);end=float(seg.end_time)
    if end<=start: return np.array([start]),np.asarray(seg.state[:,-1:],dtype=float)
    times=np.unique(np.r_[start,np.arange(start+step,end,step),start+(end-start)/2.,end])
    return times,np.asarray(seg.dense_state_at(times),dtype=float)


def execute_case(job:dict) -> dict:
    from cinder.execution.hybrid import HybridIntegratorSettings,integrate_hybrid
    out=Path(job['case_dir']);out.mkdir(parents=True,exist_ok=True)
    course=Course(job['course']);tune=job['tune'];settings=job['settings'];execution=job['execution']
    write_json(out/'status.json',{'status':'running','started_utc':utc_now(),'id':tune['id']})
    write_json(out/'resolved_case.json',{'tune':tune,'resolved_tune':job['resolved_tune'],'course':job['course'],'numerical_settings':settings,'execution':execution,'public_document':job['document'],'fingerprint':job['fingerprint']})
    started=perf_counter(); chunks=[];events=[];maps=[];watched=None;system=None
    outcome={'status':'setup_error','reason':'','integration_wall_s':0.,'setup_wall_s':0.,'postprocess_wall_s':0.,'rhs_calls':0,'native_solver_points':0,'checkpoint_count':0,'last_completed_time_s':0.,'requested_maximum_time_s':settings['maximum_time_s'],'started_utc':utc_now(),'parallel_workers':job.get('launch_context',{}).get('jobs',1),'blas_threads':job.get('launch_context',{}).get('blas_threads',{})}
    error_text=''
    try:
        system,y,mode,identity=build_system(job['document'],course,execution)
        write_json(out/'model_identity.json',identity)
        maps=mechanism_map(system,int(job['diagnostics']['mechanism_map_points']))
        write_csv(out/'mechanism_map.csv',maps)
        outcome['setup_wall_s']=perf_counter()-started
        solver=HybridIntegratorSettings(method='LSODA',relative_tolerance=settings['relative_tolerance'],absolute_tolerance=settings['absolute_tolerance'],max_step=settings['max_step_s'],maximum_transitions=int(execution['maximum_transitions_per_checkpoint']),event_time_tolerance=execution['event_time_tolerance_s'],retain_dense_output=True)
        watched=WatchedSystem(system,float(execution['case_wall_timeout_s']))
        t=0.;progress=[(0.,0.)];ntrans=0;native_points=0;integration_start=perf_counter()
        outcome['status']='time_limit';outcome['reason']='maximum simulated duration reached without finishing'
        while t<float(settings['maximum_time_s'])-1e-10:
            end=min(float(settings['maximum_time_s']),t+float(execution['checkpoint_interval_s']))
            result=integrate_hybrid(system=watched,time_span=(t,end),initial_state=y,initial_mode=mode,settings=solver)
            chunks.append(result)
            ntrans+=len(result.transitions)
            native_points+=sum(len(s.time) for s in result.segments)
            t=float(result.final_time);y=np.array(result.final_state,dtype=float,copy=True)
            # Preserve the regime and solver continuation cache across administrative checkpoints.
            mode=result.segments[-1].mode
            if result.transitions and abs(result.transitions[-1].time-t)<1e-12 and not result.transitions[-1].transition.terminates:
                mode=result.transitions[-1].transition.next_mode
            x=float(y[5])*system.host.factor
            progress.append((t,x))
            payload={};index=len(chunks)-1
            for k,seg in enumerate(result.segments):
                payload[f's{k:04d}_native_t']=seg.time;payload[f's{k:04d}_native_y']=seg.state
                payload[f's{k:04d}_mode']=np.asarray([str(seg.mode)])
            payload['checkpoint_final_state']=y
            np.savez_compressed(out/f'checkpoint_{index:04d}.npz',**payload)
            write_json(out/'checkpoint.json',{'last_completed_time_s':t,'distance_m':x,'state':y,'mode':str(mode),'checkpoint_count':len(chunks),'physical_transitions_so_far':ntrans,'rhs_calls':watched.rhs_calls,'accepted':True})
            outcome.update(last_completed_time_s=t,checkpoint_count=len(chunks),native_solver_points=native_points)
            if not result.completed:
                reason=result.termination_reason
                if reason=='course_finish': outcome.update(status='finished',reason=reason)
                elif reason=='rollback_observed': outcome.update(status='rollback',reason='Backwards speed crossed the declared study stop; no claim of irreversible physical failure.')
                else: outcome.update(status='model_domain_stop',reason=reason)
                break
            window=float(execution['no_progress_window_s'])
            if window>0 and t>=max(float(execution['progress_monitor_after_s']),window):
                earlier=[(tt,xx) for tt,xx in progress if tt<=t-window]
                if earlier:
                    tb,xb=earlier[-1]
                    max_recent=max(xx for tt,xx in progress if tt>=tb)
                    if max_recent-xb<float(execution['no_progress_distance_m']):
                        outcome.update(status='progress_limited',reason=f'Less than {execution["no_progress_distance_m"]:g} m forward progress over {t-tb:g} s; study censoring rule, not proof of a stalled equilibrium.')
                        break
            if ntrans>int(execution['maximum_total_transitions']):
                outcome.update(status='integration_error',reason='Study total-transition budget exceeded; possible chatter or under-resolution.');break
        outcome['integration_wall_s']=perf_counter()-integration_start
        outcome['rhs_calls']=watched.rhs_calls
    except Exception as exc:
        error_text=traceback.format_exc()
        if watched is None: status='setup_error'
        elif isinstance(exc,TimeoutError): status='wall_timeout'
        else: status='integration_error'
        outcome.update(status=status,reason=f'{type(exc).__name__}: {exc}')
        if watched:
            outcome['rhs_calls']=watched.rhs_calls
            write_json(out/'last_trial_probe_NOT_ACCEPTED.json',watched.last_probe)
        if 'integration_start' in locals(): outcome['integration_wall_s']=perf_counter()-integration_start
        (out/'error.txt').write_text(error_text,encoding='utf-8')
    # Inspect only AFTER all integration calls; report-time solves cannot change the subsequent trajectory.
    post_start=perf_counter();rows=[];segment_rows=[];seg_id=0
    if system is not None:
        mu=float(job['document']['assembly']['contact']['static_friction_coefficient'])
        for result in chunks:
            for seg in result.segments:
                times,states=sample_segment(seg,float(settings['diagnostic_step_s']))
                np.savez_compressed(out/f'segment_{seg_id:04d}.npz',time_s=times,state=states,mode=np.asarray([str(seg.mode)]))
                segment_rows.append({'segment_id':seg_id,'start_s':seg.start_time,'end_s':seg.end_time,'start_distance_m':float(seg.state[5,0])*system.host.factor,'end_distance_m':float(seg.state[5,-1])*system.host.factor,'native_point_count':len(seg.time),**mode_fields(seg.mode),'event_names':list(seg.fired_event_names)})
                for n,time in enumerate(times):
                    location='start' if n==0 else ('end' if n==len(times)-1 else 'interior')
                    r=inspect_row(system,course,float(time),states[:,n],seg.mode,seg_id,location)
                    for side in ('primary','secondary'):
                        if r.get(f'{side}_lambda') is not None:
                            r[f'{side}_static_utilization']=abs(r[f'{side}_lambda'])/mu
                    rows.append(r)
                seg_id+=1
            for record in result.transitions:
                seg=next(s for s in result.segments if abs(s.end_time-record.time)<1e-12 and s.fired_event_names==record.fired_event_names)
                pre=np.asarray(seg.state[:,-1]);post=np.asarray(record.post_transition_state)
                loss=sum(float(v) for v in nested_values(record.transition.metadata,'impact_dissipated_energy_J'))
                events.append({'event_id':f'E{len(events)+1:04d}','time_s':record.time,'distance_m':float(pre[5])*system.host.factor,'event_names':list(record.fired_event_names),'previous_mode':str(record.previous_mode),'next_mode':str(record.transition.next_mode),'reason':record.transition.reason,'has_explicit_successor_state':record.transition.has_successor_state,'nonzero_velocity_jump':bool(np.max(np.abs(post[:5]-pre[:5]))>1e-10),'capture_loss_J':loss,'pre_state':pre.tolist(),'post_state':post.tolist(),'delta_omega_p_rad_s':float(post[0]-pre[0]),'delta_omega_s_rad_s':float(post[1]-pre[1]),'delta_belt_speed_m_s':float(post[2]-pre[2]),'delta_shift_rate_m_s':float(post[4]-pre[4]),'metadata':json_safe(record.transition.metadata)})
    outcome['postprocess_wall_s']=perf_counter()-post_start
    outcome['total_wall_s']=perf_counter()-started
    outcome['finished_utc']=utc_now()
    summary,sectors=summarize(rows,events,course,outcome,tune,review_tolerance=float(job['diagnostics']['physical_margin_review_tolerance']))
    write_csv(out/'diagnostics.csv',rows)
    write_csv(out/'segments.csv',segment_rows)
    write_json(out/'events.json',events)
    write_csv(out/'events.csv',events)
    write_csv(out/'sector_metrics.csv',sectors)
    write_csv(out/'interesting_windows.csv',nominate_windows(rows,events,course))
    # Near-event context uses nearest stored same-trajectory samples; exact reset states are in events.json.
    contexts=[]
    for e in events:
        near=[r for r in rows if abs(r['time_s']-e['time_s'])<=float(job['diagnostics']['event_window_s'])]
        contexts.extend({'event_id':e['event_id'],'event_time_s':e['time_s'],'time_from_event_s':r['time_s']-e['time_s'],**r} for r in near)
    write_csv(out/'event_windows.csv',contexts)
    write_json(out/'summary.json',summary)
    write_json(out/'status.json',{'status':summary['status'],'complete_output':True,'fingerprint':job['fingerprint'],'finished_utc':utc_now()})
    return summary
