"""Physical rate/profile changes with explicit one-point preload matching.

Uses released ramp segments and the same full dynamic fixed-pivot mechanism.
No fitted RPM curve, force multiplier, CINDER monkey patch or solver retuning.
"""
from __future__ import annotations
from copy import deepcopy
from math import atan, degrees, isclose, isfinite, radians
from typing import Any
from infrastructure.tunes import resolve_tune as resolve_legacy, component

RATE_KEYS = {'primary_rate_scale','secondary_rate_scale','torsional_rate_scale'}
SHAPE_KEYS = RATE_KEYS | {'ramp_end_deg','ramp_prefix_m','ramp_blend_m','ramp_tail_kind'}
LEGACY_KEYS = {'tip_mass_scale','primary_preload_scale','secondary_preload_scale',
               'secondary_twist_deg','helix_angle_deg'}


def physical_differences(a: Any, b: Any, path: str = '') -> list[dict]:
    """Whole-list replacement if a profile changes its segment count."""
    if isinstance(a,dict) and isinstance(b,dict):
        if set(a)!=set(b): raise ValueError(f'Unexpected schema change: {path}')
        return [r for k in a for r in physical_differences(a[k],b[k],path+'/'+k)]
    if isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b): return [{'path':path,'baseline':a,'value':b}]
        return [r for k,(x,y) in enumerate(zip(a,b)) for r in physical_differences(x,y,path+'/'+str(k))]
    return [] if a==b else [{'path':path,'baseline':a,'value':b}]


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


def serialize(seg) -> dict:
    from cinder.model.cvt.profiles import LinearSegment, CircularSegment, C3TransitionSegment
    if isinstance(seg,LinearSegment): return {'kind':'linear_segment','length_m':seg.length,'angle_rad':radians(seg.angle_degrees)}
    if isinstance(seg,CircularSegment): return {'kind':'circular_segment','length_m':seg.length,
        'angle_start_rad':radians(seg.angle_start_degrees),'angle_end_rad':radians(seg.angle_end_degrees),'quadrant':seg.quadrant}
    if isinstance(seg,C3TransitionSegment): return {'kind':'c3_transition_segment','length_m':seg.length,
        'slope_start':seg.slope_start,'curvature_start_per_m':seg.curvature_start,'third_derivative_start_per_m2':seg.third_derivative_start,
        'slope_end':seg.slope_end,'curvature_end_per_m':seg.curvature_end,'third_derivative_end_per_m2':seg.third_derivative_end}
    raise TypeError(type(seg))


def make_ramp(baseline: dict, *, end_deg: float, prefix_m: float=.010,
              blend_m: float=.005, tail_kind: str='arc') -> dict:
    """Keep the original nose EXACTLY, then C3-join a different tail.

    The original circular segment is shortened without changing its radius;
    the new blend copies slope/curvature/third derivative from its neighbors.
    Tail endpoint angle is at the physical ramp end, not at maximum sheave shift.
    """
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
    # Let CINDER validate continuity before using this serialized ramp.
    PiecewiseRamp((_segment(parts[0]),_segment(parts[1]),prefix_arc,blend,tail))
    return {'kind':'piecewise_ramp','segments':[deepcopy(parts[0]),deepcopy(parts[1]),
                                             serialize(prefix_arc),serialize(blend),serialize(tail)]}


def resolve_shape_tune(base: dict, tune: dict) -> tuple[dict,dict]:
    knobs=tune['knobs']
    if set(knobs)-LEGACY_KEYS-SHAPE_KEYS: raise ValueError(f'Unknown knobs: {set(knobs)-LEGACY_KEYS-SHAPE_KEYS}')
    if 'ramp_end_deg' not in knobs and any(k in knobs for k in ('ramp_prefix_m','ramp_blend_m','ramp_tail_kind')):
        raise ValueError('Ramp modifiers need ramp_end_deg')
    for k in RATE_KEYS:
        if k in knobs and (not isfinite(float(knobs[k])) or not .4<=float(knobs[k])<=3.):
            raise ValueError(f'{k} must lie in [0.4,3.0]')
    # Avoid hidden double adjustments: this experiment does not combine rate and preload knobs.
    for rate,preload in [('primary_rate_scale','primary_preload_scale'),('secondary_rate_scale','secondary_preload_scale'),('torsional_rate_scale','secondary_twist_deg')]:
        if rate in knobs and preload in knobs:raise ValueError(f'{rate} uses matched preload, cannot also set {preload}')
    legacy={**tune,'knobs':{k:v for k,v in knobs.items() if k in LEGACY_KEYS}}
    doc,summary=resolve_legacy(base,legacy)
    sd=float(base['assembly']['geometry']['deadzone_shift_m'])
    matches=[]
    # In the selected geometry: x_p=s at engagement, x_s=0, theta_s=0.
    for side,key,anchor in [('primary','primary_rate_scale',sd),('secondary','secondary_rate_scale',0.)]:
        if key not in knobs: continue
        spring=component(doc,side,'axial_spring');scale=float(knobs[key]);k0=float(spring['stiffness_N_per_m'])
        c0=float(spring['initial_compression_m']);a=float(spring['compression_per_axial_position'])
        k=k0*scale; c=(c0+a*anchor)/scale-a*anchor
        if c<=0:raise ValueError('Matched installed compression must remain positive')
        spring.update(stiffness_N_per_m=k,initial_compression_m=c)
        matches.append({'component':side+'_axial_spring','anchor_local_axial_m':anchor,
            'reference_stiffness_N_per_m':k0,'stiffness_N_per_m':k,
            'reference_compression_m':c0,'compression_m':c,
            'reference_signed_force_N':-k0*(c0+a*anchor)*a,'matched_signed_force_N':-k*(c+a*anchor)*a,
            'policy':'Match signed spring force at the low-ratio engagement geometry; stiffness changes away from that point.'})
    if 'torsional_rate_scale' in knobs:
        spring=component(doc,'secondary','helical_torque_reaction');scale=float(knobs['torsional_rate_scale'])
        k0=float(spring['torsional_stiffness_Nm_per_rad']);theta0=float(spring['initial_twist_rad'])
        spring.update(torsional_stiffness_Nm_per_rad=k0*scale,initial_twist_rad=theta0/scale)
        matches.append({'component':'secondary_torsional_spring','anchor_theta_rad':0.,
            'reference_torque_Nm':k0*theta0,'matched_torque_Nm':spring['torsional_stiffness_Nm_per_rad']*spring['initial_twist_rad'],
            'policy':'Match initial torsional spring torque; do not change helix geometry.'})
    fw=component(doc,'primary','fixed_pivot_roller_flyweight');base_fw=component(base,'primary','fixed_pivot_roller_flyweight')
    if 'ramp_end_deg' in knobs:
        fw['geometry']['ramp_profile']=make_ramp(base_fw['geometry']['ramp_profile'],end_deg=float(knobs['ramp_end_deg']),
            prefix_m=float(knobs.get('ramp_prefix_m',.010)),blend_m=float(knobs.get('ramp_blend_m',.005)),tail_kind=knobs.get('ramp_tail_kind','arc'))
    for k in ('shaft_boundaries','host','scenario','execution'):
        if doc[k]!=base[k]:raise AssertionError(f'Changed common {k}')
    for k in ('geometry','contact','inertias'):
        if doc['assembly'][k]!=base['assembly'][k]:raise AssertionError(f'Changed CVT {k}')
    if doc['assembly']['pulleys']['secondary']['helical_coupling']!=base['assembly']['pulleys']['secondary']['helical_coupling']:
        if 'helix_angle_deg' not in knobs:raise AssertionError('Helix geometry changed unexpectedly')
    for k,v in base_fw['geometry'].items():
        if k!='ramp_profile' and fw['geometry'][k]!=v:raise AssertionError('Ramp change moved fixed-pivot hardware')
    if fw['mass_geometry']!=component(resolve_legacy(base,legacy)[0],'primary','fixed_pivot_roller_flyweight')['mass_geometry']:
        raise AssertionError('Ramp change altered body mass moments')
    p=component(doc,'primary','axial_spring');s=component(doc,'secondary','axial_spring');t=component(doc,'secondary','helical_torque_reaction')
    summary.update(primary_stiffness_N_per_m=p['stiffness_N_per_m'],secondary_stiffness_N_per_m=s['stiffness_N_per_m'],
        torsional_stiffness_Nm_per_rad=t['torsional_stiffness_Nm_per_rad'],
        primary_preload_mm=1000*p['initial_compression_m'],secondary_preload_mm=1000*s['initial_compression_m'],
        secondary_twist_deg=degrees(t['initial_twist_rad']),matches=matches,
        ramp_end_angle_deg=float(knobs.get('ramp_end_deg',20.)),ramp_unchanged_prefix_mm=1000*float(knobs.get('ramp_prefix_m',.010)) if 'ramp_end_deg' in knobs else None,
        ramp_tail_kind=knobs.get('ramp_tail_kind','arc') if 'ramp_end_deg' in knobs else 'baseline',
        changes=physical_differences(base,doc))
    return doc,summary
