"""Reproduce the note's checks. No source repository files are changed.

  python verify_reference.py
  python verify_reference.py --repo /path/to/CVT-Simulator

The optional comparison requires the v1.1.5 cvtModel source. The current git
head may be newer if cvtModel is unchanged from that tag. Results are written
beside this script unless --output specifies another JSON path.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from math import cos, sin
from pathlib import Path
import subprocess
import sys

import numpy as np
import scipy

from fixed_pivot_reference import (
    FixedPivotReference, Geometry, InertiaSample, MassMoments, ReferenceRamp,
    StraightRamp, energy, force_torque, straight_ramp_oracle,
)

PIN = "8261226b8cd1e8b65c883d3a382c3f109ccbb10c"


class Checks:
    def __init__(self):
        self.maxima = {}
        self.comparisons = {}

    def close(self, name, actual, expected, *, atol=1e-9, rtol=1e-10):
        a,b = np.asarray(actual,dtype=float),np.asarray(expected,dtype=float)
        err = float(np.max(np.abs(a-b)))
        self.maxima[name] = max(err,self.maxima.get(name,0.))
        self.comparisons[name] = self.comparisons.get(name,0)+1
        np.testing.assert_allclose(a,b,atol=atol,rtol=rtol,err_msg=name)


def independent_checks(ref, checks):
    straight = FixedPivotReference(StraightRamp(length=.015),Geometry(x_max=.007))
    for x in np.linspace(0,.007,41):
        c = straight.contact(float(x))
        q = straight_ramp_oracle(x,straight.geometry,straight.ramp.k)
        for name,actual,expected in zip(("q","q_prime","q_second"),
                                       (c.q,c.q_prime,c.q_second),q):
            checks.close("straight_closed_form_"+name,actual,expected,atol=1e-8)

    # A finite point cloud with nonzero v, z and product moment uv. Each point
    # has an equal reflected partner in z, giving the required symmetry.
    points = np.array([[.004,.002,.001],[.016,-.003,.002],[.026,.001,.0015]])
    points = np.concatenate([points,points*np.array([1.,1.,-1.])])
    masses = np.array([.01,.035,.065,.01,.035,.065])
    u,v,z = points.T
    moment = MassMoments(3,float(masses.sum()),float(masses@u),float(masses@v),
                         float(masses@(u*u)),float(masses@(v*v)),
                         float(masses@(u*v)),float(masses@(z*z)))
    e = np.array([1.,0.,0.])
    weights = moment.n*masses
    for x in np.linspace(0,ref.geometry.x_max,19):
        c = ref.contact(float(x))
        q,q1,q2 = c.q,c.q_prime,c.q_second
        rho = np.column_stack([u*cos(q)-v*sin(q),
                               ref.geometry.rP+u*sin(q)+v*cos(q),z])
        rq = np.column_stack([-u*sin(q)-v*cos(q),u*cos(q)-v*sin(q),np.zeros_like(u)])
        rqq = np.column_stack([-u*cos(q)+v*sin(q),-u*sin(q)-v*cos(q),np.zeros_like(u)])
        r1,r2 = rq*q1,rqq*q1*q1+rq*q2
        samp = moment.inertias(ref.geometry.rP,q,q1,q2)
        checks.close("mass_integral_M",samp.M,weights@np.sum(r1*r1,axis=1))
        checks.close("mass_integral_M_prime",samp.M_prime,2*weights@np.sum(r1*r2,axis=1))
        er = np.cross(e,rho)
        checks.close("mass_integral_J",samp.J,weights@np.sum(er*er,axis=1))
        checks.close("mass_integral_J_prime",samp.J_prime,2*weights@np.sum(er*np.cross(e,r1),axis=1))
        checks.close("mixed_coefficient_B",weights@np.sum(r1*er,axis=1),0.)
        assert samp.J_prime**2 <= 4*samp.M*samp.J + 1e-12
        for xd,xdd,w,alpha in [(0.,0.,300.,0.),(.08,1.2,260.,12.),(-.05,-.7,420.,-10.)]:
            velocity = r1*xd+w*er
            acceleration = (r1*xdd+r2*xd*xd+2*w*xd*np.cross(e,r1)
                            +alpha*er+w*w*np.cross(e,er))
            F,tau = force_torque(samp,omega=w,x_dot=xd,x_ddot=xdd,alpha=alpha)
            checks.close("Newton_force_N",F,-weights@np.sum(acceleration*r1,axis=1),atol=1e-8)
            checks.close("Newton_torque_Nm",tau,-weights@(np.cross(rho,acceleration)@e))
            checks.close("power_balance_W",F*xd+tau*w,-weights@np.sum(velocity*acceleration,axis=1),atol=1e-8)

        # This recovery belongs specifically to the fixed-pivot branch.
        samp = ref.evaluate(float(x))
        F,_ = force_torque(samp,omega=300.,x_dot=.04,x_ddot=2.,alpha=10.)
        normal = ref.normal_per_roller(float(x),F)
        ell = c.a*c.normal_r-c.b*c.normal_x
        qdd = c.q_prime*2.+c.q_second*.04**2
        Jq = samp.J_prime/c.q_prime
        checks.close("roller_moment_balance_Nm",.5*Jq*300.**2+ref.mass.n*normal*ell,
                     ref.mass.I*qdd,atol=1e-8)
        checks.close("normal_motion_ratio_identity",c.q_prime*ell,c.normal_x)

    # Differentiate the computed exact inertia values, not the derivative code.
    joins = [ref.closure_from_contact(xi) for xi in ref.ramp.joins]
    h = 2e-6
    for x in np.linspace(.0001,ref.geometry.x_max-.0001,47):
        if any(abs(x-j)<20*h for j in joins):
            continue
        lo2,lo1,hi1,hi2 = [ref.evaluate(float(x+i*h)) for i in [-2,-1,1,2]]
        sample = ref.evaluate(float(x))
        checks.close("finite_difference_M_prime",sample.M_prime,
                     (lo2.M-8*lo1.M+8*hi1.M-hi2.M)/(12*h),atol=3e-5,rtol=2e-6)
        checks.close("finite_difference_J_prime",sample.J_prime,
                     (lo2.J-8*lo1.J+8*hi1.J-hi2.J)/(12*h),atol=1e-9)
    return joins


def cinder_checks(repo, ref, checks):
    if subprocess.run(["git","diff","--quiet",PIN,"--","cvtModel"],cwd=repo).returncode:
        raise RuntimeError("cvtModel differs from pinned CINDER v1.1.5; use that source for this comparison.")
    sys.path.insert(0,str(repo/"cvtModel/src"))
    from cinder.contracts import decode_assembly_document
    from cinder.model.cvt.actuation import PulleyActuator,PulleyActuationContext,PulleyClosureChannels
    from cinder.model.cvt.actuation.types import PulleyElementContribution,PulleyKineticMode
    from cinder.model.cvt.closure import AffineClosureScalar,ClosureGains,ClosureUnknowns
    from cinder.model.cvt.contact import ContactTractionUtilization
    from cinder.model.cvt.dynamics.deadzone.free import DeadzoneDynamicsEvaluator
    from cinder.model.cvt.dynamics.equation_context import TrialEquationContext
    from cinder.model.cvt.dynamics.equations import build_trial_closure_system
    from cinder.model.cvt.dynamics.state_fixed_equations import build_state_fixed_equations
    from cinder.model.cvt.dynamics.shift_constraints import EngagedShiftConstraint
    from cinder.model.system import MechanicalCVTPlant
    from cinder.model.system.ports import CVTShaftBoundaryValues,ShaftBoundaryValue
    from cinder.model.system.state import CVTState
    from cinder.execution.hybrid.cvt_impact import CVTVelocityTopology,kinetic_energy_for_topology,project_cvt_velocity_topology

    assembly = decode_assembly_document(json.loads((repo/"cvtModel/examples/baja_baseline_assembly.json").read_text()))
    original = assembly.pulleys.primary.actuator.force_laws[0]
    existing_map = original.spec.mechanism_map

    def converted(x):
        old = existing_map.evaluate(x)
        return InertiaSample(old.pivot_inertia*old.angle_gradient**2,
                             2*old.pivot_inertia*old.angle_gradient*old.angle_curvature,
                             old.shaft_inertia,old.shaft_inertia_gradient)

    class FixedPivotReducedElement:
        """Use four maps; the contact policy below is fixed-pivot-specific."""
        def evaluate(self,c):
            p = converted(c.axial_position)
            return AffineClosureScalar.constant(.5*p.J_prime*c.shaft_speed**2-.5*p.M_prime*c.axial_speed**2)+c.axial_acceleration.scaled(-p.M)

        def evaluate_element(self,c):
            p = converted(c.axial_position)
            return PulleyElementContribution(self.evaluate(c),AffineClosureScalar(
                bias=-p.J_prime*c.axial_speed*c.shaft_speed,
                gains=ClosureGains.from_by_unknown({c.closure_channels.shaft_angular_acceleration:-p.J})))

        def kinetic_modes(self,c):
            p = converted(c.axial_position)
            return (PulleyKineticMode(p.J,shaft_speed_coefficient=1.),
                    PulleyKineticMode(p.M,axial_speed_coefficient=1.))

        def compressive_contact_margin(self,*,context,unknowns):
            p = converted(context.axial_position)
            terms = (.5*p.J_prime*context.shaft_speed**2,
                     -p.M*context.axial_acceleration.evaluate(unknowns),
                     -.5*p.M_prime*context.axial_speed**2)
            raw = self.evaluate(context).evaluate(unknowns)
            tolerance = 4096*np.finfo(float).eps*max(1.,sum(abs(v) for v in terms))
            return 0. if abs(raw)<=tolerance else raw

    new = FixedPivotReducedElement()
    # Exact geometry comparison, including both sides of the two C3 joins.
    x_max = min(ref.geometry.x_max,existing_map.axial_position_max)
    xs = list(np.linspace(0,x_max,65))
    for xi in ref.ramp.joins:
        x = ref.closure_from_contact(xi)
        xs.extend([x-1e-8,x,x+1e-8])
    for x in xs:
        old = existing_map.evaluate_exact(float(x))
        new_contact = ref.contact(float(x))
        for name,a,b in zip(("q","q_prime","q_second"),
                            (new_contact.q,new_contact.q_prime,new_contact.q_second),
                            (old.angle,old.angle_gradient,old.angle_curvature)):
            checks.close("exact_CINDER_"+name,a,b,atol=2e-6,rtol=2e-7)
        old_values = (old.pivot_inertia*old.angle_gradient**2,
                      2*old.pivot_inertia*old.angle_gradient*old.angle_curvature,
                      old.shaft_inertia,old.shaft_inertia_gradient)
        for name,a,b in zip(("M","M_prime","J","J_prime"),ref.evaluate(float(x)).values(),old_values):
            checks.close("exact_CINDER_"+name,a,b,atol=2e-7,rtol=2e-7)

    for x in np.linspace(0,x_max,65):
        for primary in [True,False]:
            for xd,w in [(0.,0.),(.08,300.),(-.06,425.)]:
                c = PulleyActuationContext(time=.4,axial_position=float(x),axial_speed=xd,shaft_speed=w,
                    axial_acceleration=AffineClosureScalar(bias=.007,gains=ClosureGains(shift_acceleration=.8 if primary else -.65)),
                    closure_channels=PulleyClosureChannels.primary() if primary else PulleyClosureChannels.secondary())
                a,b = original.evaluate_element(c),new.evaluate_element(c)
                checks.close("affine_force_coefficients",(a.closing_force.bias,*a.closing_force.gains.as_tuple()),
                             (b.closing_force.bias,*b.closing_force.gains.as_tuple()),atol=1e-10)
                checks.close("affine_torque_coefficients",(a.shaft_torque.bias,*a.shaft_torque.gains.as_tuple()),
                             (b.shaft_torque.bias,*b.shaft_torque.gains.as_tuple()),atol=1e-12)
                def metric(element):
                    return sum(mode.inertia*np.outer([mode.shaft_speed_coefficient,mode.axial_speed_coefficient],
                                [mode.shaft_speed_coefficient,mode.axial_speed_coefficient]) for mode in element.kinetic_modes(c))
                checks.close("kinetic_metric",metric(original),metric(new),atol=1e-14)
                u = ClosureUnknowns(shift_acceleration=2.,primary_angular_acceleration=10.,secondary_angular_acceleration=-4.)
                checks.close("fixed_pivot_contact_margin_N",original.compressive_contact_margin(context=c,unknowns=u),
                             new.compressive_contact_margin(context=c,unknowns=u),atol=1e-10)

    # Deliberately test both physical signs and cancellation at zero reaction.
    c = PulleyActuationContext(time=0.,axial_position=.01,axial_speed=.05,shaft_speed=300.,
        axial_acceleration=AffineClosureScalar(gains=ClosureGains(shift_acceleration=1.)),
        closure_channels=PulleyClosureChannels.primary())
    p = converted(.01)
    azero = (.5*p.J_prime*300**2-.5*p.M_prime*.05**2)/p.M
    margins=[]
    for a in [azero-1,azero,azero+1]:
        u = ClosureUnknowns(shift_acceleration=a)
        left = original.compressive_contact_margin(context=c,unknowns=u)
        right = new.compressive_contact_margin(context=c,unknowns=u)
        checks.close("contact_zero_crossing_N",left,right,atol=1e-10)
        margins.append(right)
    assert margins[0]>0 and margins[1]==0 and margins[2]<0

    new_assembly = replace(assembly,pulleys=replace(assembly.pulleys,primary=replace(
        assembly.pulleys.primary,actuator=PulleyActuator(new,*assembly.pulleys.primary.actuator.force_laws[1:]))))
    plants = [MechanicalCVTPlant.from_assembly(a) for a in [assembly,new_assembly]]
    lim = assembly.geometry.spec
    boundaries = CVTShaftBoundaryValues(primary=ShaftBoundaryValue(external_torque=12.))
    for fraction in (0.,.3,.7,1.):
        x = lim.deadzone_shift+fraction*(lim.max_shift-lim.deadzone_shift)
        for constraint in EngagedShiftConstraint:
            state = CVTState(245.,90.,7.,x,.025 if constraint is EngagedShiftConstraint.FREE else 0.)
            solutions=[]
            for plant in plants:
                snap=plant.snapshot(state=state,shaft_boundaries=boundaries,geometry_side="engaged")
                system=build_trial_closure_system(fixed_equations=build_state_fixed_equations(snapshot=snap,shift_constraint=constraint),
                    trial_context=TrialEquationContext(snapshot=snap,traction_utilization=ContactTractionUtilization(.20,-.15)))
                solutions.append(system.solve().unknowns.as_tuple())
            checks.close("engaged_closure_unknowns",*solutions,atol=1e-9)
    for f in (.2,.8):
        state=CVTState(245.,0.,0.,f*lim.deadzone_shift,.025)
        solutions=[DeadzoneDynamicsEvaluator(p).evaluate_free(state=state,shaft_boundaries=boundaries).state_derivative for p in plants]
        checks.close("deadzone_accelerations",[solutions[0].primary_angular_acceleration,solutions[0].shift_acceleration],
                     [solutions[1].primary_angular_acceleration,solutions[1].shift_acceleration],atol=1e-10)
    for topology in CVTVelocityTopology:
        state=CVTState(245.,90.,7.,lim.deadzone_shift,.025)
        energies=[kinetic_energy_for_topology(model=p,state=state,topology=topology) for p in plants]
        checks.close("topology_kinetic_energy_J",*energies,atol=1e-10)
    state=CVTState(245.,90.,7.,lim.max_shift,.025)
    impacts=[project_cvt_velocity_topology(model=p,vector=state.as_vector(),shift_position=lim.max_shift,
                from_topology=CVTVelocityTopology.ENGAGED,to_topology=CVTVelocityTopology.ENGAGED,stop_shift_velocity=True) for p in plants]
    checks.close("upper_stop_successor_state",impacts[0].successor_state,impacts[1].successor_state,atol=1e-10)
    return {"model_commit":PIN,"source_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip(),
            "exact_positions":len(xs),"affine_contexts":390,"engaged_solve_pairs":12,"deadzone_pairs":2,
            "geometry_audit_valid":existing_map.validation_report.is_valid}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--repo",type=Path)
    parser.add_argument("--output",type=Path,default=Path(__file__).with_name("check_results.json"))
    args=parser.parse_args()
    checks=Checks()
    ref=FixedPivotReference()
    joins=independent_checks(ref,checks)
    cinder_info=cinder_checks(args.repo.resolve(),ref,checks) if args.repo else None
    # Keep approximation error separate from the interface equivalence check.
    compiled=ref.compile(257)
    interpolation_max=np.zeros(4)
    xs=sorted(set(np.linspace(0,ref.geometry.x_max,1025)) | set(joins))
    ranges=[]
    for x in xs:
        exact=np.array(ref.evaluate(float(x)).values())
        approx=np.array(compiled.evaluate(float(x)).values())
        interpolation_max=np.maximum(interpolation_max,abs(exact-approx))
        ranges.append(exact)
    ranges=np.array(ranges)
    # Limits allow the existing 257-node spline approximation; they are not
    # rounded claims of identity with the exact contact curve.
    assert np.all(interpolation_max<np.array([1e-4,.8,1e-8,2e-5])),interpolation_max
    result={"status":"passed","python":sys.version.split()[0],"numpy":np.__version__,"scipy":scipy.__version__,
            "cinder":cinder_info,"max_absolute_errors":checks.maxima,"comparison_counts":checks.comparisons,
            "map_order":["M_kg","M_prime_kg_per_m","J_kg_m2","J_prime_kg_m"],
            "sampled_map_minima":ranges.min(axis=0).tolist(),"sampled_map_maxima":ranges.max(axis=0).tolist(),
            "interpolation_positions":len(xs),"compiled_257_max_absolute_errors":interpolation_max.tolist(),
            "join_closures_m":joins,
            "example_at_10mm":{"contact":ref.contact(.01).__dict__,"maps":ref.evaluate(.01).__dict__,
                "force_torque_at_omega300_xdot0p05_xddot2_alpha10":force_torque(ref.evaluate(.01),omega=300.,x_dot=.05,x_ddot=2.,alpha=10.)}}
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
