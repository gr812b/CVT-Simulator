from __future__ import annotations
from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from infrastructure.common import load_json,digest
from infrastructure.course import Course,smooth
from infrastructure.tunes import resolve_tune,component
from analysis.metrics import first_passage,passage_at,integral


class CourseTests(unittest.TestCase):
    def setUp(self): self.course=Course(load_json(ROOT/'inputs/course.json'))
    def test_finish_and_order(self):
        self.assertAlmostEqual(self.course.finish_m,732.0)
        for a,b in zip(self.course.sectors,self.course.sectors[1:]): self.assertEqual(a.end_m,b.start_m)
    def test_bounds(self):
        g=np.asarray([self.course.grade_and_gradient(float(x))[0] for x in np.linspace(0,self.course.finish_m,9001)])
        self.assertLessEqual(g.max(),math.radians(max(self.course.config['hill_angle_deg'],abs(self.course.config['cyclic_amplitude_deg'])))+1e-12)
        self.assertGreaterEqual(g.min(),math.radians(min(self.course.config['downhill_angle_deg'],-abs(self.course.config['cyclic_amplitude_deg'])))-1e-12)
    def test_continuity(self):
        for sec in self.course.sectors[:-1]:
            x=sec.end_m; a=self.course.grade_and_gradient(x-1e-6);b=self.course.grade_and_gradient(x+1e-6)
            self.assertLess(abs(a[0]-b[0]),1e-7)
            self.assertLess(abs(a[1]-b[1]),1e-6)
    def test_analytical_gradient(self):
        for x in np.linspace(.13,self.course.finish_m-.13,100):
            h=1e-5
            d=(self.course.grade_and_gradient(x+h)[0]-self.course.grade_and_gradient(x-h)[0])/(2*h)
            self.assertAlmostEqual(d,self.course.grade_and_gradient(float(x))[1],places=7)
    def test_height_uses_arc_length(self):
        rows=self.course.profile_rows(.05)
        hold=next(s for s in self.course.sectors if s.name=='hill_hold')
        a=min(rows,key=lambda r:abs(r['distance_m']-hold.start_m));b=min(rows,key=lambda r:abs(r['distance_m']-hold.end_m))
        self.assertAlmostEqual(b['elevation_m']-a['elevation_m'],(hold.end_m-hold.start_m)*math.sin(math.radians(hold.start_deg)),places=3)
    def test_outside_flat(self):
        self.assertEqual(self.course.grade_and_gradient(-1.),(0.,0.))
        self.assertEqual(self.course.grade_and_gradient(self.course.finish_m+1.),(0.,0.))
    def test_course_not_time_dependent(self):
        self.assertEqual(self.course.grade_and_gradient(125.),self.course.grade_and_gradient(125.))
        self.assertNotEqual(digest(self.course.config),digest({**self.course.config,'hill_angle_deg':self.course.config['hill_angle_deg']+1.}))


class TuneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=load_json(ROOT/'../../defaults/baja/simulation_case.json')
        cls.tunes=load_json(ROOT/'inputs/competitors.json')['competitors']
    def test_nonempty_unique(self):
        self.assertGreater(len(self.tunes),0);self.assertEqual(len({t['id'] for t in self.tunes}),len(self.tunes))
    def test_reference_is_unchanged(self):
        d,_=resolve_tune(self.base,{'id':'reference','label':'reference','family':'reference','intent':'test','knobs':{}});self.assertEqual(d,self.base)
    def test_invariants_all_cars(self):
        for t in self.tunes:
            d,_=resolve_tune(self.base,t)
            for k in ('shaft_boundaries','host','scenario','execution'): self.assertEqual(d[k],self.base[k])
            for k in ('geometry','contact','inertias'): self.assertEqual(d['assembly'][k],self.base['assembly'][k])
            a=component(self.base,'primary','fixed_pivot_roller_flyweight')['geometry']
            b=component(d,'primary','fixed_pivot_roller_flyweight')['geometry']
            for key in a:
                if key!='ramp_profile': self.assertEqual(b[key],a[key])
            if 'ramp_end_deg' not in t['knobs']: self.assertEqual(b['ramp_profile'],a['ramp_profile'])
    def test_tip_delta_moments(self):
        tune={'id':'test','label':'test','family':'test','intent':'test','knobs':{'tip_mass_scale':.9}};d,_=resolve_tune(self.base,tune)
        a=component(self.base,'primary','fixed_pivot_roller_flyweight');b=component(d,'primary','fixed_pivot_roller_flyweight')
        L=a['geometry']['arm_length_m'];dm=-.025
        for key,delta in [('mass_per_flyweight_kg',dm),('first_moment_u_kg_m',dm*L),('second_moment_u_kg_m2',dm*L*L)]:
            self.assertAlmostEqual(b['mass_geometry'][key]-a['mass_geometry'][key],delta,places=14)
    def test_mass_geometry_valid_all(self):
        from cinder.model.cvt.actuation import FlyweightMassGeometry
        for t in self.tunes:
            d,_=resolve_tune(self.base,t);m=component(d,'primary','fixed_pivot_roller_flyweight')['mass_geometry']
            FlyweightMassGeometry(number_of_flyweights=m['number_of_flyweights'],mass_per_flyweight=m['mass_per_flyweight_kg'],first_moment_u=m['first_moment_u_kg_m'],first_moment_v=m['first_moment_v_kg_m'],second_moment_u=m['second_moment_u_kg_m2'],second_moment_v=m['second_moment_v_kg_m2'],product_moment_uv=m['product_moment_uv_kg_m2'],second_moment_z=m['second_moment_z_kg_m2'])
    def test_primary_rate_match(self):
        t=next(x for x in self.tunes if x['id']=='P300')
        d,s=resolve_tune(self.base,t)
        a=component(self.base,'primary','axial_spring');b=component(d,'primary','axial_spring')
        sd=self.base['assembly']['geometry']['deadzone_shift_m']
        fa=a['stiffness_N_per_m']*(a['initial_compression_m']+a['compression_per_axial_position']*sd)
        fb=b['stiffness_N_per_m']*(b['initial_compression_m']+b['compression_per_axial_position']*sd)
        self.assertAlmostEqual(b['stiffness_N_per_m']/a['stiffness_N_per_m'],3.0)
        self.assertAlmostEqual(fa,fb,places=9)
        self.assertTrue(s['spring_matches'])
    def test_selected_ramps_build_and_preserve_mass(self):
        from cinder.model.cvt.actuation import FixedPivotFlyweightForce
        from cinder.model.system import MechanicalCVTPlant
        for cid in ('RC10','R26B7','RC40L'):
            t=next(x for x in self.tunes if x['id']==cid);d,_=resolve_tune(self.base,t)
            self.assertEqual(component(d,'primary','fixed_pivot_roller_flyweight')['mass_geometry'],component(self.base,'primary','fixed_pivot_roller_flyweight')['mass_geometry'])
            from cinder.contracts import decode_simulation_case_document
            decoded=decode_simulation_case_document(d)
            law=next(l for l in decoded.plant.primary_actuator.force_laws if type(l) is FixedPivotFlyweightForce)
            self.assertTrue(law.spec.mechanism_map.validation_report.is_valid)
    def test_helix_angle_convention(self):
        t={'id':'test','label':'test','family':'test','intent':'test','knobs':{'helix_angle_deg':18.}};d,s=resolve_tune(self.base,t)
        angle=d['assembly']['pulleys']['secondary']['helical_coupling']['profile']['circumferential_profile']['segments'][0]['angle_rad']
        self.assertAlmostEqual(math.degrees(angle),72.);self.assertAlmostEqual(s['helix_angle_from_circumferential_deg'],18.)
    def test_reject_new_mechanism_knob(self):
        with self.assertRaises(ValueError):resolve_tune(self.base,{'id':'bad','knobs':{'static_friction_coefficient':.1}})
    def test_reject_changed_mass_partition(self):
        d=deepcopy(self.base);component(d,'primary','fixed_pivot_roller_flyweight')['mass_geometry']['first_moment_u_kg_m']*=1.01
        with self.assertRaises(ValueError):resolve_tune(d,{'id':'bad','knobs':{}})


class MetricTests(unittest.TestCase):
    def test_no_extrapolation(self):
        x,t=first_passage([{'distance_m':0.,'time_s':0.},{'distance_m':5.,'time_s':2.}])
        self.assertEqual(passage_at(x,t,2.5),1.)
        self.assertIsNone(passage_at(x,t,6.))
    def test_rollback_first_passage(self):
        x,t=first_passage([{'distance_m':0.,'time_s':0.},{'distance_m':1.,'time_s':1.},{'distance_m':.5,'time_s':2.},{'distance_m':1.1,'time_s':3.}])
        self.assertEqual(passage_at(x,t,1.),1.)
        self.assertAlmostEqual(passage_at(x,t,1.05),2.+.55/.6)
    def test_launch_dwell(self):
        x,t=first_passage([{'distance_m':0.,'time_s':0.},{'distance_m':0.,'time_s':1.},{'distance_m':1.,'time_s':2.}])
        self.assertEqual(passage_at(x,t,0.),0.);self.assertEqual(passage_at(x,t,.5),1.5)
    def test_segmentwise_integration(self):
        rows=[{'segment_id':0,'time_s':0.,'p':1.},{'segment_id':0,'time_s':1.,'p':1.},{'segment_id':1,'time_s':1.,'p':100.},{'segment_id':1,'time_s':2.,'p':100.}]
        self.assertEqual(integral(rows,'p'),101.)
    def test_missing_power_not_interpolated(self):
        rows=[{'segment_id':0,'time_s':0.,'p':1.},{'segment_id':0,'time_s':1.,'p':None},{'segment_id':0,'time_s':2.,'p':100.}]
        self.assertEqual(integral(rows,'p'),0.)

if __name__=='__main__': unittest.main()
