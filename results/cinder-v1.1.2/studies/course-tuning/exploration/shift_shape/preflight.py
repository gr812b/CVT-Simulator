"""Released geometry checks and independently saved mechanism/spring maps."""
from __future__ import annotations
from math import atan, degrees, isfinite
from pathlib import Path
import numpy as np
from infrastructure.common import write_csv,write_json
from infrastructure.model import build_system
from infrastructure.course import Course
from infrastructure.tunes import component
from .tuning import _segment


def inspect_definition(document: dict, course: dict, execution: dict, out: Path) -> dict:
    from cinder.model.cvt.actuation import FixedPivotFlyweightForce
    from cinder.model.cvt.profiles import PiecewiseRamp
    system,y,mode,identity=build_system(document,Course(course),execution)
    model=system.cvt.model
    law=next(l for l in model.primary_actuator.force_laws if type(l) is FixedPivotFlyweightForce)
    mapper=law.spec.mechanism_map
    audit=mapper.validation_report.as_dict()
    if not audit['is_valid']:raise ValueError('Released fixed-pivot construction audit failed')
    fw=component(document,'primary','fixed_pivot_roller_flyweight')
    profile=PiecewiseRamp(tuple(_segment(d) for d in fw['geometry']['ramp_profile']['segments']))
    samples=[]
    for xi in np.linspace(profile.x_min,profile.x_max,401):
        p=profile.evaluate(float(xi))
        samples.append({'ramp_coordinate_mm':1000*float(xi),'radial_offset_mm':1000*p.value,
                        'tangent_angle_deg':degrees(atan(p.first_derivative)),
                        'curvature_per_m':p.second_derivative,'third_derivative_per_m2':p.third_derivative})
    write_csv(out/'ramp_profile.csv',samples)
    ps=component(document,'primary','axial_spring');ss=component(document,'secondary','axial_spring')
    tors=component(document,'secondary','helical_torque_reaction');g=model.geometry.spec
    rows=[]
    for s in np.linspace(g.deadzone_shift,g.max_shift,101):
        geom=model.geometry.evaluate_engaged(float(s));xp=geom.primary_axial_coordinate;xs=geom.secondary_axial_coordinate
        f=mapper.evaluate(xp.value);c=mapper.contact_at(xp.value)
        h=model.secondary_helical_coupling.evaluate_from_local_coordinate(axial_position=xs.value,
            d_axial_position_ds=xs.d_value_ds,d2_axial_position_ds2=xs.d2_value_ds2)
        pc=ps['initial_compression_m']+ps['compression_per_axial_position']*xp.value
        sc=ss['initial_compression_m']+ss['compression_per_axial_position']*xs.value
        if pc<=0 or sc<=0:raise ValueError('A compression spring becomes uncompressed within the travel interval')
        rows.append({'active_shift_fraction':(float(s)-g.deadzone_shift)/(g.max_shift-g.deadzone_shift),
            'shift_mm':1000*float(s),'primary_axial_mm':1000*xp.value,'secondary_axial_mm':1000*xs.value,
            'roller_contact_coordinate_mm':1000*c.contact_coordinate,
            'flyweight_angle_deg':degrees(f.angle),'dq_dx_per_m':f.angle_gradient,'d2q_dx2_per_m2':f.angle_curvature,
            'flyweight_dJ_dx_kg_m':f.shaft_inertia_gradient,'centrifugal_force_3000rpm_N':.5*(3000*2*np.pi/60)**2*f.shaft_inertia_gradient,
            'flyweight_reflected_shift_mass_kg':f.pivot_inertia*(f.angle_gradient*xp.d_value_ds)**2,
            'primary_spring_opening_N':ps['stiffness_N_per_m']*pc*ps['compression_per_axial_position'],
            'secondary_spring_closing_N':-ss['stiffness_N_per_m']*sc*ss['compression_per_axial_position'],
            'torsional_spring_torque_Nm':tors['torsional_stiffness_Nm_per_rad']*(tors['initial_twist_rad']-h.theta),
            'helix_dtheta_dx_rad_m':h.dtheta_ds/xs.d_value_ds,
            'primary_compression_mm':pc*1000,'secondary_compression_mm':sc*1000})
    write_csv(out/'shape_mechanism_map.csv',rows)
    report={'status':'accepted_definition','model_identity':identity,'released_geometry_audit':audit,
        'initial_mode':str(mode),'initial_state':y.tolist(),
        'visited_ramp_coordinate_min_mm':min(q['roller_contact_coordinate_mm'] for q in rows),
        'visited_ramp_coordinate_max_mm':max(q['roller_contact_coordinate_mm'] for q in rows),
        'note':'Construction/geometry checks are not a hardware manufacturability or spring-availability certification.'}
    write_json(out/'definition_checks.json',report)
    return report
