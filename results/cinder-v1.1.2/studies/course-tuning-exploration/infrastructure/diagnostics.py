"""Post-integration mechanical inspection. Never called during integration."""
from __future__ import annotations
from math import sin, sqrt, pi
import numpy as np
from .common import finite


def value(x): return getattr(x,'value',str(x))


def mode_fields(mode) -> dict:
    m=mode.cvt
    contact=m.contact_regime
    return {'engagement':value(m.engagement),'shift_constraint':value(m.shift_constraint),
            'contact_mode':value(contact.mode) if contact is not None else 'disengaged',
            'regime':str(m)}


def inspect_row(system,course,time,state,mode,segment_id,location):
    from cinder.results import inspect_cvt_state
    from cinder.model.system import CVTState
    from cinder.model.cvt.closure import ClosureUnknowns
    from cinder.model.cvt.contact import ContactInterface
    from cinder.results.fields.belt import recover_belt_tension_boundaries
    y=np.asarray(state,dtype=float)
    cvt=CVTState.from_vector(y[:5]);factor=system.host.factor
    distance=float(y[5])*factor;speed=cvt.secondary_angular_speed*factor
    gamma,dgamma_dx=course.grade_and_gradient(distance)
    row={'time_s':float(time),'distance_m':distance,'speed_m_s':speed,'primary_rpm':cvt.primary_angular_speed*60/(2*pi),'secondary_rpm':cvt.secondary_angular_speed*60/(2*pi),'omega_p_rad_s':cvt.primary_angular_speed,'omega_s_rad_s':cvt.secondary_angular_speed,'belt_speed_m_s':cvt.belt_speed,'shift_mm':1000*cvt.shift_position,'shift_rate_mm_s':1000*cvt.shift_speed,'grade_deg':gamma*180/pi,'grade_rate_deg_s':dgamma_dx*speed*180/pi,'cyclic_encounter_frequency_hz':abs(speed)/course.wavelength if course.sector(distance).kind=='cyclic' else 0.,'sector':course.sector(distance).name,'segment_id':segment_id,'sample_location':location,**mode_fields(mode),'inspection_error':'','primary_slip_loss_W':0.,'secondary_slip_loss_W':0.}
    try:
        boundaries=system._shaft_boundaries(time=float(time),state=y)
        row.update(primary_boundary_torque_Nm=boundaries.primary.external_torque,secondary_boundary_torque_Nm=boundaries.secondary.external_torque,
                   primary_boundary_power_W=boundaries.primary.external_torque*cvt.primary_angular_speed,secondary_boundary_power_W=boundaries.secondary.external_torque*cvt.secondary_angular_speed)
        road=boundaries.secondary.metadata['road_load']
        row.update(grade_force_N=road.grade_force,rolling_force_N=road.rolling_force,aero_force_N=road.aerodynamic_force)
        ins=inspect_cvt_state(system=system.cvt,time=float(time),vector=y[:5],mode=mode.cvt,shaft_boundaries=boundaries,include_closure_audit=False)
        row['geometric_ratio_rp_over_rs']=ins.geometry.primary.effective/ins.geometry.secondary.effective
        row['shaft_speed_ratio_ws_over_wp']=cvt.secondary_angular_speed/cvt.primary_angular_speed if abs(cvt.primary_angular_speed)>1e-10 else None
        model=system.cvt.model; spec=model.geometry.spec
        row['active_shift_fraction']=(cvt.shift_position-spec.deadzone_shift)/(spec.max_shift-spec.deadzone_shift)
        z=ins.closure_unknowns
        if z is None:
            dz=ins.deadzone; d=dz.state_derivative
            z=ClosureUnknowns.from_components(primary_angular_acceleration=d.primary_angular_acceleration,secondary_angular_acceleration=d.secondary_angular_acceleration,belt_acceleration=d.belt_acceleration,shift_acceleration=d.shift_acceleration,primary_torque=0.,secondary_torque=-dz.snapshot.inertias.belt.mass*dz.snapshot.belt_secondary_lock_radius*d.belt_acceleration)
            row['lower_stop_reaction_N']=None if dz.lower_stop_reaction is None else dz.lower_stop_reaction.closing_direction_magnitude
        row.update(primary_alpha_rad_s2=z.primary_angular_acceleration,secondary_alpha_rad_s2=z.secondary_angular_acceleration,vehicle_acceleration_m_s2=factor*z.secondary_angular_acceleration,belt_acceleration_m_s2=z.belt_acceleration,shift_acceleration_m_s2=z.shift_acceleration)
        for side,act in [('primary',ins.primary_actuation),('secondary',ins.secondary_actuation)]:
            if act is None: continue
            row[f'{side}_actuator_closing_N']=act.resolve_total(z)
            for term in act.contributions:
                row[f'{side}.{term.key}_N']=term.relation.evaluate(z)
        if ins.contact is not None:
            c=ins.contact
            row.update(primary_belt_torque_Nm=z.primary_torque,secondary_belt_torque_Nm=z.secondary_torque,primary_to_belt_power_W=-z.primary_torque*cvt.primary_angular_speed,belt_to_secondary_power_W=z.secondary_torque*cvt.secondary_angular_speed,normal_primary_N=z.primary_normal_resultant,normal_secondary_N=z.secondary_normal_resultant,low_ratio_seat_reaction_N=c.low_ratio_seat_reaction,upper_stop_reaction_N=c.upper_stop_reaction)
            for side,interface in [('primary',ContactInterface.PRIMARY),('secondary',ContactInterface.SECONDARY)]:
                lam=getattr(c.traction_utilization,side+'_lambda')
                N=c.normal_at(interface);vrel=c.relative_motion.relative_speed_at(interface)
                sliding=interface in c.mode.slipping_interfaces
                row[f'{side}_lambda']=lam;row[f'{side}_vrel_m_s']=vrel
                row[f'{side}_sliding']=sliding
                row[f'{side}_static_utilization']=abs(lam)/float(model.contact.static_friction_coefficient) if hasattr(model,'contact') else None
                # The friction coefficient is also supplied once in analyse_run (see below).
                row[f'{side}_slip_loss_W']=-lam*N*vrel if sliding else 0.
            tensions=recover_belt_tension_boundaries(ins)
            if tensions is not None:
                row['min_tension_N']=min(tensions.primary_in,tensions.primary_out,tensions.secondary_in,tensions.secondary_out)
                for side in ('primary','secondary'):
                    row[f'tension_{side}_in_N']=getattr(tensions,side+'_in');row[f'tension_{side}_out_N']=getattr(tensions,side+'_out')
                    r=getattr(ins.geometry,side)
                    rdd=r.d_center_of_mass_ds*z.shift_acceleration+r.d2_center_of_mass_ds2*cvt.shift_speed**2
                    offset=c.snapshot.belt_linear_density*(cvt.belt_speed**2-r.center_of_mass*rdd)
                    row[f'{side}_min_dN_dtheta_N_per_rad']=(min(getattr(tensions,side+'_in'),getattr(tensions,side+'_out'))-offset)/sin(c.snapshot.sheave_half_angle)
            for k,v in c.mechanism_contact_margins: row['mechanism_margin.'+k]=float(v)
            # Positive values of BOTH channel powers indicate forward transmission.
            p=row['primary_to_belt_power_W']; s=row['belt_to_secondary_power_W']
            row['power_flow']='forward' if p>1. and s>1. else ('reverse' if p<-1. and s<-1. else 'mixed_or_small')
        else:
            row['power_flow']='disengaged'
        geometry=(model.geometry.evaluate_engaged(cvt.shift_position) if ins.contact is not None else model.geometry.evaluate_deadzone(cvt.shift_position))
        from cinder.model.cvt.actuation import FixedPivotFlyweightForce
        fw=next(l for l in model.primary_actuator.force_laws if type(l) is FixedPivotFlyweightForce)
        xp=geometry.primary_axial_coordinate; f=fw.spec.mechanism_map.evaluate(xp.value)
        row['flyweight_reflected_shift_mass_kg']=f.pivot_inertia*(f.angle_gradient*xp.d_value_ds)**2
        if ins.contact is not None:
            xs=geometry.secondary_axial_coordinate
            hk=model.secondary_helical_coupling.evaluate_from_local_coordinate(axial_position=xs.value,d_axial_position_ds=xs.d_value_ds,d2_axial_position_ds2=xs.d2_value_ds2)
            row['helix_reflected_shift_mass_kg']=model.inertias.secondary.movable_sheave_rotational_inertia*hk.dtheta_ds**2
            H=hk.dtheta_ds/xs.d_value_ds if abs(xs.d_value_ds)>1e-15 else None
            row['helix_dtheta_dx_rad_m']=H
            # Recover the signed helix torque from helix-force components, not total actuator force (which includes axial spring).
            hforce=sum(float(v) for k,v in row.items() if k.startswith('secondary.helix_') and k.endswith('_N') and finite(v))
            row['helix_signed_reaction_Nm']=hforce/H if H and abs(H)>1e-15 else None
    except Exception as exc:
        row['inspection_error']=f'{type(exc).__name__}: {exc}'
    return row


def mechanism_map(system,points:int) -> list[dict]:
    from cinder.model.cvt.actuation import FixedPivotFlyweightForce
    model=system.cvt.model;spec=model.geometry.spec
    fw=next(l for l in model.primary_actuator.force_laws if type(l) is FixedPivotFlyweightForce)
    rows=[]
    for s in np.linspace(spec.deadzone_shift,spec.max_shift,points):
        g=model.geometry.evaluate_engaged(float(s));xp=g.primary_axial_coordinate;xs=g.secondary_axial_coordinate
        f=fw.spec.mechanism_map.evaluate(xp.value)
        hk=model.secondary_helical_coupling.evaluate_from_local_coordinate(axial_position=xs.value,d_axial_position_ds=xs.d_value_ds,d2_axial_position_ds2=xs.d2_value_ds2)
        rows.append({'shift_mm':float(s)*1000,'active_shift_fraction':float((s-spec.deadzone_shift)/(spec.max_shift-spec.deadzone_shift)),
                     'flyweight_shaft_inertia_kg_m2':f.shaft_inertia,'flyweight_dJ_dx_kg_m':f.shaft_inertia_gradient,'flyweight_reflected_shift_mass_kg':f.pivot_inertia*(f.angle_gradient*xp.d_value_ds)**2,
                     'helix_dtheta_dx_rad_m':hk.dtheta_ds/xs.d_value_ds,'helix_reflected_shift_mass_kg':model.inertias.secondary.movable_sheave_rotational_inertia*hk.dtheta_ds**2})
    return rows
