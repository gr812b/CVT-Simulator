"""Physical parameter edits for the selected course-tuning configurations.

The final study supports the original mass/preload/helix changes plus the
selected primary spring-rate and ramp-profile changes promoted from exploration.
All variants retain the same full dynamic actuator mechanisms and shared shaft
boundaries. No force scaling, quasi-static ablation, fitted RPM curve, or model
patch is applied.
"""
from __future__ import annotations
from copy import deepcopy
from math import atan, degrees, isclose, isfinite, radians
from typing import Any

LEGACY_KEYS={
    'tip_mass_scale','primary_preload_scale','secondary_preload_scale',
    'secondary_twist_deg','helix_angle_deg'
}
RATE_KEYS={'primary_rate_scale','secondary_rate_scale','torsional_rate_scale'}
RAMP_KEYS={'ramp_end_deg','ramp_prefix_m','ramp_blend_m','ramp_tail_kind'}
ALLOWED_KNOBS=LEGACY_KEYS|RATE_KEYS|RAMP_KEYS


def component(doc:dict,side:str,kind:str) -> dict:
    found=[c for c in doc['assembly']['pulleys'][side]['components'] if c['kind']==kind]
    if len(found)!=1: raise ValueError(f'Expected exactly one {side}/{kind}; got {len(found)}')
    return found[0]


def differences(a: Any,b: Any,prefix:str='') -> list[dict]:
    """Return explicit physical changes; whole-list replacement if profile topology changes."""
    if isinstance(a,dict) and isinstance(b,dict):
        if set(a)!=set(b): raise ValueError(f'Unexpected schema change at {prefix}')
        return [r for k in a for r in differences(a[k],b[k],prefix+'/'+k)]
    if isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b): return [{'path':prefix,'baseline':a,'value':b}]
        return [r for i,(x,y) in enumerate(zip(a,b)) for r in differences(x,y,prefix+'/'+str(i))]
    return [] if a==b else [{'path':prefix,'baseline':a,'value':b}]


def _segment(d: dict):
    from cinder.model.cvt.profiles import LinearSegment, CircularSegment, C3TransitionSegment
    if d['kind']=='linear_segment':
        return LinearSegment(length=float(d['length_m']),angle_degrees=degrees(d['angle_rad']))
    if d['kind']=='circular_segment':
        return CircularSegment(length=float(d['length_m']),angle_start_degrees=degrees(d['angle_start_rad']),
                               angle_end_degrees=degrees(d['angle_end_rad']),quadrant=int(d['quadrant']))
    if d['kind']=='c3_transition_segment':
        return C3TransitionSegment(length=float(d['length_m']),slope_start=float(d['slope_start']),
            curvature_start=float(d['curvature_start_per_m']),third_derivative_start=float(d['third_derivative_start_per_m2']),
            slope_end=float(d['slope_end']),curvature_end=float(d['curvature_end_per_m']),
            third_derivative_end=float(d['third_derivative_end_per_m2']))
    raise ValueError(f'Unsupported reference segment {d["kind"]}')


def _serialize_segment(seg) -> dict:
    from cinder.model.cvt.profiles import LinearSegment, CircularSegment, C3TransitionSegment
    if isinstance(seg,LinearSegment):
        return {'kind':'linear_segment','length_m':seg.length,'angle_rad':radians(seg.angle_degrees)}
    if isinstance(seg,CircularSegment):
        return {'kind':'circular_segment','length_m':seg.length,
            'angle_start_rad':radians(seg.angle_start_degrees),'angle_end_rad':radians(seg.angle_end_degrees),'quadrant':seg.quadrant}
    if isinstance(seg,C3TransitionSegment):
        return {'kind':'c3_transition_segment','length_m':seg.length,
            'slope_start':seg.slope_start,'curvature_start_per_m':seg.curvature_start,'third_derivative_start_per_m2':seg.third_derivative_start,
            'slope_end':seg.slope_end,'curvature_end_per_m':seg.curvature_end,'third_derivative_end_per_m2':seg.third_derivative_end}
    raise TypeError(type(seg))


def make_ramp(baseline: dict, *, end_deg: float, prefix_m: float=.010,
              blend_m: float=.005, tail_kind: str='arc') -> dict:
    """Keep the selected Baja ramp nose, then C3-join a different physical tail."""
    from cinder.model.cvt.profiles import LinearSegment, CircularSegment, C3TransitionSegment, PiecewiseRamp
    parts=baseline['segments']
    if [p['kind'] for p in parts]!=['linear_segment','c3_transition_segment','circular_segment']:
        raise ValueError('Expected the selected linear/blend/circular Baja ramp')
    nose_len=float(parts[0]['length_m'])+float(parts[1]['length_m'])
    total=sum(float(p['length_m']) for p in parts)
    if not (nose_len+1e-5<prefix_m<total-blend_m-1e-3 and .001<=blend_m<=.010):
        raise ValueError('Invalid unchanged-prefix/blend extent')
    if not isfinite(end_deg) or not 5.<=end_deg<=50.: raise ValueError('Ramp endpoint angle outside 5–50 degrees')
    if tail_kind not in ('arc','straight'): raise ValueError('tail_kind must be arc or straight')
    original_arc=_segment(parts[2]); prefix_arc_length=prefix_m-nose_len
    end_prefix_deg=degrees(atan(original_arc.evaluate_local(prefix_arc_length).first_derivative))
    prefix_arc=CircularSegment(length=prefix_arc_length,
        angle_start_degrees=degrees(parts[2]['angle_start_rad']),angle_end_degrees=end_prefix_deg,quadrant=2)
    tail_len=total-prefix_m-blend_m
    start_tail_deg=degrees(atan(original_arc.evaluate_local(prefix_m+blend_m-nose_len).first_derivative))
    if tail_kind=='straight' or abs(end_deg-start_tail_deg)<1e-8:
        tail=LinearSegment(length=tail_len,angle_degrees=end_deg)
    else:
        tail=CircularSegment(length=tail_len,angle_start_degrees=start_tail_deg,
                             angle_end_degrees=end_deg,quadrant=2 if end_deg<start_tail_deg else 4)
    blend=C3TransitionSegment.between_segments(left=prefix_arc,right=tail,length=blend_m)
    PiecewiseRamp((_segment(parts[0]),_segment(parts[1]),prefix_arc,blend,tail))
    return {'kind':'piecewise_ramp','segments':[deepcopy(parts[0]),deepcopy(parts[1]),
                                             _serialize_segment(prefix_arc),_serialize_segment(blend),_serialize_segment(tail)]}


def resolve_tune(base:dict,tune:dict,baseline_tip_mass_kg:float=.250) -> tuple[dict,dict]:
    """Resolve one selected hardware configuration into a public CINDER document.

    Spring-rate variants explicitly match spring force/torque at one declared
    low-ratio engagement geometry. Ramp variants change only the contacted ramp
    profile; CINDER rebuilds the dynamic flyweight mechanism map from that geometry.
    """
    doc=deepcopy(base);knobs=dict(tune.get('knobs',{}))
    if set(knobs)-ALLOWED_KNOBS: raise ValueError(f'Unsupported knobs: {set(knobs)-ALLOWED_KNOBS}')
    if any(not isfinite(float(v)) for k,v in knobs.items() if k!='ramp_tail_kind'):
        raise ValueError('Non-finite tune value')
    if 'ramp_end_deg' not in knobs and any(k in knobs for k in ('ramp_prefix_m','ramp_blend_m','ramp_tail_kind')):
        raise ValueError('Ramp modifiers need ramp_end_deg')
    for k in ('tip_mass_scale','primary_preload_scale','secondary_preload_scale'):
        if float(knobs.get(k,1.))<=0: raise ValueError(f'{k} must be positive')
    for k in RATE_KEYS:
        if k in knobs and not .4<=float(knobs[k])<=3.:
            raise ValueError(f'{k} must lie in [0.4,3.0]')
    for rate,preload in [('primary_rate_scale','primary_preload_scale'),('secondary_rate_scale','secondary_preload_scale'),('torsional_rate_scale','secondary_twist_deg')]:
        if rate in knobs and preload in knobs: raise ValueError(f'{rate} uses matched preload, cannot also set {preload}')

    fw=component(doc,'primary','fixed_pivot_roller_flyweight');mg=fw['mass_geometry']
    base_fw=component(base,'primary','fixed_pivot_roller_flyweight')
    L=float(fw['geometry']['arm_length_m']);scale=float(knobs.get('tip_mass_scale',1.))
    body=float(mg['mass_per_flyweight_kg'])-baseline_tip_mass_kg
    if body<=0: raise ValueError('Baseline tip mass incompatible with total flyweight mass')
    if not isclose(float(mg['first_moment_u_kg_m']),body*L/2+baseline_tip_mass_kg*L,rel_tol=1e-9):
        raise ValueError('Baseline mass partition changed: review tip model before applying these tunes')
    if not isclose(float(mg['second_moment_u_kg_m2']),body*L*L/3+baseline_tip_mass_kg*L*L,rel_tol=1e-9):
        raise ValueError('Baseline second moment does not match the declared reference tip model')
    if scale!=1.:
        dm=baseline_tip_mass_kg*(scale-1.)
        mg['mass_per_flyweight_kg']+=dm
        mg['first_moment_u_kg_m']+=dm*L
        mg['second_moment_u_kg_m2']+=dm*L*L

    for side,key in [('primary','primary_preload_scale'),('secondary','secondary_preload_scale')]:
        if key in knobs: component(doc,side,'axial_spring')['initial_compression_m']*=float(knobs[key])
    helix=component(doc,'secondary','helical_torque_reaction')
    if 'secondary_twist_deg' in knobs:
        if not 0<float(knobs['secondary_twist_deg'])<720: raise ValueError('Unreasonable torsional preload')
        helix['initial_twist_rad']=radians(float(knobs['secondary_twist_deg']))
    profile=doc['assembly']['pulleys']['secondary']['helical_coupling']['profile']
    segments=profile['circumferential_profile']['segments']
    if len(segments)!=1 or segments[0]['kind']!='linear_segment': raise ValueError('Reference constant-angle helix changed')
    if 'helix_angle_deg' in knobs:
        a=float(knobs['helix_angle_deg'])
        if not 10<=a<=45: raise ValueError('Helix angle outside declared bounds')
        segments[0]['angle_rad']=radians(90.-a)

    matches=[]
    sd=float(base['assembly']['geometry']['deadzone_shift_m'])
    for side,key,anchor in [('primary','primary_rate_scale',sd),('secondary','secondary_rate_scale',0.)]:
        if key not in knobs: continue
        spring=component(doc,side,'axial_spring');rate=float(knobs[key]);k0=float(spring['stiffness_N_per_m'])
        c0=float(spring['initial_compression_m']);a=float(spring['compression_per_axial_position'])
        k=k0*rate;c=(c0+a*anchor)/rate-a*anchor
        if c<=0: raise ValueError('Matched installed compression must remain positive')
        spring.update(stiffness_N_per_m=k,initial_compression_m=c)
        matches.append({'component':side+'_axial_spring','anchor_local_axial_m':anchor,
            'reference_stiffness_N_per_m':k0,'stiffness_N_per_m':k,
            'reference_compression_m':c0,'compression_m':c,
            'reference_signed_force_N':-k0*(c0+a*anchor)*a,'matched_signed_force_N':-k*(c+a*anchor)*a,
            'policy':'Match signed spring force at the low-ratio engagement geometry; stiffness changes away from that point.'})
    if 'torsional_rate_scale' in knobs:
        rate=float(knobs['torsional_rate_scale']);k0=float(helix['torsional_stiffness_Nm_per_rad']);theta0=float(helix['initial_twist_rad'])
        helix.update(torsional_stiffness_Nm_per_rad=k0*rate,initial_twist_rad=theta0/rate)
        matches.append({'component':'secondary_torsional_spring','anchor_theta_rad':0.,
            'reference_torque_Nm':k0*theta0,'matched_torque_Nm':helix['torsional_stiffness_Nm_per_rad']*helix['initial_twist_rad'],
            'policy':'Match initial torsional spring torque; do not change helix geometry.'})

    if 'ramp_end_deg' in knobs:
        fw['geometry']['ramp_profile']=make_ramp(base_fw['geometry']['ramp_profile'],end_deg=float(knobs['ramp_end_deg']),
            prefix_m=float(knobs.get('ramp_prefix_m',.010)),blend_m=float(knobs.get('ramp_blend_m',.005)),tail_kind=str(knobs.get('ramp_tail_kind','arc')))

    for invariant in ('shaft_boundaries','host','scenario','execution'):
        if doc[invariant]!=base[invariant]: raise AssertionError(f'Tune modified shared {invariant}')
    for invariant in ('geometry','contact','inertias'):
        if doc['assembly'][invariant]!=base['assembly'][invariant]: raise AssertionError(f'Tune changed reference {invariant}')
    for k,v in base_fw['geometry'].items():
        if k!='ramp_profile' and fw['geometry'][k]!=v: raise AssertionError('Ramp change moved fixed-pivot hardware')

    p=component(doc,'primary','axial_spring');s=component(doc,'secondary','axial_spring')
    summary={
        'id':tune['id'],'label':tune['label'],'family':tune['family'],'intent':tune['intent'],
        'tip_mass_per_flyweight_kg':baseline_tip_mass_kg*scale,
        'body_mass_per_flyweight_kg':body,'total_mass_per_flyweight_kg':mg['mass_per_flyweight_kg'],
        'primary_stiffness_N_per_m':p['stiffness_N_per_m'],'primary_preload_mm':1000*p['initial_compression_m'],
        'secondary_stiffness_N_per_m':s['stiffness_N_per_m'],'secondary_preload_mm':1000*s['initial_compression_m'],
        'torsional_stiffness_Nm_per_rad':helix['torsional_stiffness_Nm_per_rad'],
        'secondary_twist_deg':degrees(helix['initial_twist_rad']),
        'helix_angle_from_circumferential_deg':90.-degrees(segments[0]['angle_rad']),
        'ramp_end_angle_deg':float(knobs.get('ramp_end_deg',20.)),
        'ramp_unchanged_prefix_mm':1000*float(knobs.get('ramp_prefix_m',.010)) if 'ramp_end_deg' in knobs else None,
        'ramp_blend_mm':1000*float(knobs.get('ramp_blend_m',.005)) if 'ramp_end_deg' in knobs else None,
        'ramp_tail_kind':str(knobs.get('ramp_tail_kind','arc')) if 'ramp_end_deg' in knobs else 'baseline',
        'spring_matches':matches,
        'mass_partition':'Concentrated tip delta; body and constant shaft-inertia entries unchanged',
        'changes':differences(base,doc),
    }
    return doc,summary
