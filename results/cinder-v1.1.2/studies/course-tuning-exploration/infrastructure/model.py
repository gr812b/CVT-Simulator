"""Adapters around the installed CINDER 1.1.2 model and shared Results loader."""
from __future__ import annotations
import importlib.metadata
import json
from pathlib import Path
import sys
from time import perf_counter
import numpy as np
from .common import RELEASE_ROOT, environment
from .course import Course


def check_environment() -> dict:
    import cinder
    version=importlib.metadata.version('cinder-cvt')
    if version!='1.1.2' or cinder.__version__!='1.1.2':
        raise RuntimeError(f'Use the results/cinder-v1.1.2 environment; found cinder-cvt {version}')
    module_path=Path(cinder.__file__).resolve()
    if 'cvtModel' in module_path.parts and 'src' in module_path.parts:
        raise RuntimeError('CINDER is being imported from a live source tree. Use its installed wheel.')
    dist=importlib.metadata.distribution('cinder-cvt')
    direct=dist.read_text('direct_url.json')
    if direct and json.loads(direct).get('dir_info',{}).get('editable'):
        raise RuntimeError('Editable CINDER installs are not supported for this study.')
    out=environment(); out['cinder_import_path']=str(module_path)
    out['frozen_environment_match']=(sys.version_info[:2]==(3,12) and out['numpy']=='2.5.2' and out['scipy']=='1.18.1' and out['matplotlib']=='3.11.1')
    return out


class CourseHost:
    """The usual shaft-angle host plus finish/rollback observation events.

    No additional mechanical states, torque requests, or velocity resets.
    Event callbacks receive the full [5 CVT states, shaft angle] vector.
    """
    block_name='host'
    def __init__(self,course:Course,distance_per_radian:float,rollback_speed:float):
        from cinder.core import StateBlock
        self.state_block=StateBlock('host',1)
        self.course=course; self.factor=float(distance_per_radian);self.rollback_speed=float(rollback_speed)
    def initial_state(self,*,secondary_shaft_angle:float=0.):
        return np.asarray([secondary_shaft_angle],dtype=float)
    def context(self,*,time,cvt_state,host_state):
        return {'secondary_shaft_angle':float(host_state[0])}
    def rhs(self,*,time,cvt_state,host_state,shaft_boundaries):
        return np.asarray([cvt_state.secondary_angular_speed],dtype=float)
    def events(self,*,time,cvt_state,host_state,shaft_boundaries):
        from cinder.execution.hybrid import HybridEvent
        return (
            HybridEvent('course_finish',lambda t,y:float(y[5])*self.factor-self.course.finish_m,direction=1.),
            HybridEvent('rollback_observed',lambda t,y:float(y[1])*self.factor-self.rollback_speed,direction=-1.),
        )
    def transition(self,*,time,cvt_state,host_state,shaft_boundaries,fired_event_names):
        from cinder.execution.hybrid import HybridTransition
        if not {'course_finish','rollback_observed'}.intersection(fired_event_names): return None
        reason='course_finish' if 'course_finish' in fired_event_names else 'rollback_observed'
        return HybridTransition(next_mode=None,reason=reason,metadata={'study_stop':reason,'distance_m':float(host_state[0])*self.factor})


def build_system(document:dict,course:Course,execution:dict):
    # Only the release Results directory is added, never cvtModel/src.
    if str(RELEASE_ROOT) not in sys.path: sys.path.insert(0,str(RELEASE_ROOT))
    from defaults.reference_model import decode_reference_case
    from cinder.execution.hybrid.composed import ComposedCVTHybridSystem
    from cinder.model.boundaries.shaft import LockedFinalDriveShaftBoundary,FullThrottleEngineBoundary
    from cinder.model.cvt.actuation import FixedPivotFlyweightForce,HelicalTorqueReactionForce
    decoded=decode_reference_case(document)
    primary=decoded.system.primary_boundary; secondary=decoded.system.secondary_boundary
    if not isinstance(primary,FullThrottleEngineBoundary): raise RuntimeError('Reference primary is not the packaged full-throttle boundary')
    if not isinstance(secondary,LockedFinalDriveShaftBoundary): raise RuntimeError('Reference secondary is not the packaged locked final-drive boundary')
    laws=decoded.plant.primary_actuator.force_laws
    if sum(type(l) is FixedPivotFlyweightForce for l in laws)!=1:
        raise RuntimeError('Expected the unreduced dynamic fixed-pivot flyweight law')
    helix=[l for l in decoded.plant.secondary_actuator.force_laws if isinstance(l,HelicalTorqueReactionForce)]
    if len(helix)!=1 or getattr(helix[0],'contact_topology',None)!='bilateral_zero_clearance_slot':
        raise RuntimeError('Shared Results decoder did not install the bilateral slotted helix')
    if type(helix[0]).evaluate is not HelicalTorqueReactionForce.evaluate:
        raise RuntimeError('Secondary force law is not the full released dynamic helix')
    road=secondary.road_load
    factor=road.final_drive.wheel_radius/road.final_drive.reduction_ratio
    host=CourseHost(course,factor,execution['rollback_stop_speed_m_s'])
    secondary=LockedFinalDriveShaftBoundary(road_load=road,road_profile=course,direct_secondary_shaft_inertia=secondary.direct_secondary_shaft_inertia)
    system=ComposedCVTHybridSystem.from_plant(plant=decoded.plant,primary_boundary=primary,secondary_boundary=secondary,host=host)
    cvt=decoded.system.layout.view(decoded.initial_state,'cvt')
    from cinder.model.system import CVTState
    initial=system.initial_state(cvt_state=CVTState.from_vector(cvt),host_state=host.initial_state())
    if initial.size!=6: raise RuntimeError('Study host expects exactly six composed states')
    mode=system.classify_initial_mode_at_time(time=0.,state=initial)
    identity={'primary_boundary':type(primary).__name__,'secondary_boundary':type(secondary).__name__,'road_profile':type(course).__name__,'host':type(host).__name__,'primary_actuator_laws':[type(l).__name__ for l in laws],'secondary_actuator_laws':[type(l).__name__ for l in decoded.plant.secondary_actuator.force_laws],'primary_boundary_inertia_kg_m2':primary.equivalent_rotational_inertia,'secondary_boundary_inertia_kg_m2':secondary.reflected_rotational_inertia,'full_throttle_all_course':True,'distance_per_secondary_radian_m':factor}
    return system,initial,mode,identity


class WatchedSystem:
    """Delegate every mechanical call; retain only a labelled trial-state diagnostic."""
    def __init__(self,system,wall_timeout_s:float):
        self.system=system;self.deadline=perf_counter()+wall_timeout_s
        self.rhs_calls=0;self.last_probe=None;self.stage_error=None
    def events(self,*a,**kw): return self.system.events(*a,**kw)
    def transition(self,*a,**kw): return self.system.transition(*a,**kw)
    def rhs(self,time,state,mode):
        self.rhs_calls+=1
        self.last_probe={'time_s':float(time),'state':np.asarray(state).tolist(),'mode':str(mode),'accepted':False,'note':'ODE trial evaluation only; not a completed solver step or trajectory endpoint.'}
        if perf_counter()>self.deadline: raise TimeoutError('Study case wall-clock integration limit reached')
        try: return self.system.rhs(time,state,mode)
        except Exception as exc:
            self.stage_error=f'{type(exc).__name__}: {exc}'
            raise
