"""Physical parameter edits only. No force scaling, ablations, or model patches."""
from __future__ import annotations
from copy import deepcopy
from math import radians, degrees, isfinite, isclose
from typing import Any

ALLOWED_KNOBS={'tip_mass_scale','primary_preload_scale','secondary_preload_scale','secondary_twist_deg','helix_angle_deg'}


def component(doc:dict,side:str,kind:str) -> dict:
    found=[c for c in doc['assembly']['pulleys'][side]['components'] if c['kind']==kind]
    if len(found)!=1: raise ValueError(f'Expected exactly one {side}/{kind}; got {len(found)}')
    return found[0]


def differences(a: Any,b: Any,prefix:str='') -> list[dict]:
    if isinstance(a,dict) and isinstance(b,dict):
        if set(a)!=set(b): raise ValueError(f'Unexpected schema change at {prefix}')
        return sum((differences(a[k],b[k],prefix+'/'+k) for k in a),[])
    if isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b): raise ValueError(f'Unexpected list change at {prefix}')
        return sum((differences(x,y,prefix+'/'+str(i)) for i,(x,y) in enumerate(zip(a,b))),[])
    return [] if a==b else [{'path':prefix,'baseline':a,'value':b}]


def resolve_tune(base:dict,tune:dict,baseline_tip_mass_kg:float=.250) -> tuple[dict,dict]:
    """Update all affected tip mass moments at u=L, v=z=0; preserve arm moments."""
    doc=deepcopy(base); knobs=tune['knobs']
    if set(knobs)-ALLOWED_KNOBS: raise ValueError(f'Unsupported knobs: {set(knobs)-ALLOWED_KNOBS}')
    if any(not isfinite(float(v)) for v in knobs.values()): raise ValueError('Non-finite tune value')
    for k in ('tip_mass_scale','primary_preload_scale','secondary_preload_scale'):
        if float(knobs.get(k,1.))<=0: raise ValueError(f'{k} must be positive')
    fw=component(doc,'primary','fixed_pivot_roller_flyweight'); mg=fw['mass_geometry']
    base_fw=component(base,'primary','fixed_pivot_roller_flyweight')
    L=float(fw['geometry']['arm_length_m']); scale=float(knobs.get('tip_mass_scale',1.))
    # Reference uses a 13.646 g uniform body plus 250 g concentrated tip.
    # Verify the declared reference before removing tip mass from its moments.
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
        if not 10<=a<=45: raise ValueError('Helix angle outside declared exploratory bounds')
        # The serialized ramp angle is measured from the axial, not circumferential, axis.
        segments[0]['angle_rad']=radians(90.-a)
    for invariant in ('shaft_boundaries','host','scenario','execution'):
        if doc[invariant]!=base[invariant]: raise AssertionError(f'Tune modified shared {invariant}')
    for invariant in ('geometry','contact','inertias'):
        if doc['assembly'][invariant]!=base['assembly'][invariant]: raise AssertionError(f'Tune changed reference {invariant}')
    if fw['geometry']!=base_fw['geometry']: raise AssertionError('Primary mechanism geometry was changed')
    summary={
        'id':tune['id'],'label':tune['label'],'family':tune['family'],'intent':tune['intent'],
        'tip_mass_per_flyweight_kg':baseline_tip_mass_kg*scale,
        'body_mass_per_flyweight_kg':body,'total_mass_per_flyweight_kg':mg['mass_per_flyweight_kg'],
        'primary_preload_mm':1000*component(doc,'primary','axial_spring')['initial_compression_m'],
        'secondary_preload_mm':1000*component(doc,'secondary','axial_spring')['initial_compression_m'],
        'secondary_twist_deg':degrees(helix['initial_twist_rad']),
        'helix_angle_from_circumferential_deg':90.-degrees(segments[0]['angle_rad']),
        'mass_partition':'Concentrated tip delta; body and constant shaft-inertia entries unchanged',
        'changes':differences(base,doc),
    }
    return doc,summary
