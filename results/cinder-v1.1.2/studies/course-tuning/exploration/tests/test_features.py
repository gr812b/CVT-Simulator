from __future__ import annotations
from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from infrastructure.common import load_json
from infrastructure.course import Course
from infrastructure.tunes import resolve_tune
from scans.scan_features import variants
from analysis.feature_metrics import interval_summary,analyze_car,_cycle_rows
from analysis.shift_curves import chronological_edges


class FeatureCourseTests(unittest.TestCase):
    def setUp(self):
        self.base=load_json(ROOT/'inputs/course.json')
        self.spec=load_json(ROOT/'inputs/feature_exploration.json')
        self.variants=variants(self.spec,self.base)
    def test_plan_merges_sibling_groups(self):
        from tempfile import TemporaryDirectory
        from scans.scan_features import upsert_trial
        with TemporaryDirectory() as folder:
            p=Path(folder)/'plan.json';identity={'test':True}
            upsert_trial(p,identity,{'id':'a','group':'flat'})
            upsert_trial(p,identity,{'id':'b','group':'cyclic'})
            upsert_trial(p,identity,{'id':'a','campaign_dir':'saved'})
            trials={t['id']:t for t in load_json(p)['trials']}
            self.assertEqual(set(trials),{'a','b'})
            self.assertEqual(trials['a']['group'],'flat')
            self.assertFalse(p.with_suffix('.lock').exists())
    def test_plan_size_and_matched_lengths(self):
        self.assertEqual(len(self.variants),12)
        self.assertEqual(sum(len(t['cars']) for t in self.variants),52)
        self.assertEqual({Course(t['course']).finish_m for t in self.variants if t['group']=='cyclic'},{420.})
        self.assertEqual({Course(t['course']).finish_m for t in self.variants if t['group']=='mild_hill'},{501.})
    def test_flat_probe(self):
        c=Course(self.variants[0]['course'])
        self.assertEqual(c.finish_m,800.)
        self.assertEqual(len(c.sectors),1)
        for x in np.linspace(-10,810,93):self.assertEqual(c.grade_and_gradient(float(x)),(0.,0.))
    def test_original_course_untouched_by_generator(self):
        b=deepcopy(self.base);variants(self.spec,self.base);self.assertEqual(b,self.base)
    def test_second_hill_precedes_descent(self):
        c=Course(next(t['course'] for t in self.variants if t['id']=='mild_hill_18'))
        names=[s.name for s in c.sectors]
        self.assertLess(names.index('cyclic'),names.index('secondary_hill_entry'))
        self.assertLess(names.index('secondary_hill_exit'),names.index('descent_entry'))
        s=next(s for s in c.sectors if s.name=='secondary_hill_hold')
        self.assertAlmostEqual(c.grade_and_gradient(.5*(s.start_m+s.end_m))[0],math.radians(18.))
    def test_variants_preserve_approach(self):
        old=Course(self.base)
        for t in self.variants[1:]:
            c=Course(t['course'])
            for x in np.linspace(0,264,117):self.assertEqual(c.grade_and_gradient(float(x)),old.grade_and_gradient(float(x)))
    def test_variant_continuity_and_gradient(self):
        for t in self.variants:
            c=Course(t['course'])
            for sector in c.sectors[:-1]:
                a=c.grade_and_gradient(sector.end_m-1e-6);b=c.grade_and_gradient(sector.end_m+1e-6)
                self.assertLess(abs(a[0]-b[0]),1e-6)
                self.assertLess(abs(a[1]-b[1]),1e-5)
            for x in np.linspace(.131,c.finish_m-.131,160):
                h=1e-5;d=(c.grade_and_gradient(x+h)[0]-c.grade_and_gradient(x-h)[0])/(2*h)
                self.assertAlmostEqual(d,c.grade_and_gradient(float(x))[1],places=6)
    def test_zero_amplitude_bias_control(self):
        c=Course(next(t['course'] for t in self.variants if t['id']=='cyc_a0_w6_b8'))
        self.assertAlmostEqual(c.grade_and_gradient(282.)[0],math.radians(8.))
        self.assertEqual(c.grade_and_gradient(264.),(0.,0.))
    def test_invalid_bias(self):
        b={**self.base,'cyclic_mean_grade_deg':80.}
        with self.assertRaises(ValueError):Course(b)
    def test_fleet_extends_without_altering_original(self):
        old=load_json(ROOT/'inputs/competitors.json')['competitors']
        new=load_json(ROOT/'inputs/competitors_features.json')['competitors']
        self.assertEqual(new[:len(old)],old);self.assertEqual(len(new),38)
        base=load_json(ROOT/'../../../defaults/baja/simulation_case.json')
        for t in new:
            doc,_=resolve_tune(base,t)
            self.assertEqual(doc['shaft_boundaries'],base['shaft_boundaries'])
            self.assertEqual(doc['assembly']['inertias'],base['assembly']['inertias'])
            self.assertEqual(doc['assembly']['contact'],base['assembly']['contact'])


def row(t,x,s,segment=0,constraint='free'):
    return {'time_s':t,'distance_m':x,'shift_mm':s,'shift_rate_mm_s':0.,'segment_id':segment,
        'shift_constraint':constraint,'primary_rpm':3000.+s,'secondary_rpm':1000.+x,'active_shift_fraction':(s-2.4892)/16.5608,
        'speed_m_s':1.,'primary_sliding':False,'secondary_sliding':False,'inspection_error':''}


class FeatureMetricTests(unittest.TestCase):
    def setUp(self):self.base=load_json(ROOT/'inputs/course.json')
    def test_clipped_support_duration(self):
        r=[row(0,0,19,0,'upper_stop'),row(10,10,19,0,'upper_stop')]
        s=interval_summary(r,2,7)
        self.assertAlmostEqual(s['duration_s'],5.);self.assertAlmostEqual(s['upper_stop_duration_s'],5.)
    def test_reset_not_opening_travel(self):
        r=[row(0,0,18,0),row(1,1,18,0),row(1,1,5,1),row(2,2,5,1)]
        self.assertEqual(interval_summary(r,0,2)['opening_travel_mm'],0.)
    def test_secular_upshift_is_not_cyclic_modulation(self):
        c=Course(self.base);r=[row(float(x),float(x),10+.01*x) for x in np.linspace(264,300,601)]
        cycles=_cycle_rows('T',r,c)
        for cy in cycles:
            self.assertLess(cy['detrended_first_harmonic_peak_to_peak_mm'],1e-10)
            self.assertEqual(cy['opening_travel_mm'],0.)
    def test_known_cyclic_modulation(self):
        c=Course(self.base);r=[row(float(x),float(x),10+.01*x+.5*np.sin(2*np.pi*(x-264)/6.)) for x in np.linspace(264,300,601)]
        for cy in _cycle_rows('T',r,c):self.assertAlmostEqual(cy['detrended_first_harmonic_peak_to_peak_mm'],1.,places=8)
    def test_incomplete_hill_is_not_partial_success(self):
        c=deepcopy(self.base);c['secondary_hill']={'angle_deg':18.,'entry_m':8.,'hold_m':45.,'exit_m':8.,'recovery_m':20.}
        course=Course(c);start=next(s.start_m for s in course.sectors if s.name=='secondary_hill_entry')
        r=[row(0,0,2.49),row(1,start,18.),row(2,start+2,15.)]
        m,_=analyze_car('T',r,course,{'status':'time_limit'})
        self.assertFalse(m['partial_backshift_candidate'])
    def test_unvisited_cyclic_is_missing(self):
        m,_=analyze_car('T',[row(0,0,0.),row(1,5,2.5)],Course(self.base),{'status':'time_limit'})
        self.assertFalse(m['cyclic_visited']);self.assertIsNone(m['cyclic_opening_travel_mm'])


class ShiftCurveTests(unittest.TestCase):
    def setUp(self):self.course=Course(load_json(ROOT/'inputs/course.json'))
    def test_does_not_sort_by_speed(self):
        r=[row(0,1,10),row(1,2,11),row(2,3,12)]
        r[0]['secondary_rpm']=100;r[1]['secondary_rpm']=200;r[2]['secondary_rpm']=150
        edges,_=chronological_edges(r,self.course)
        self.assertEqual(edges[:,0,0].tolist(),[100,200]);self.assertEqual(edges[:,1,0].tolist(),[200,150])
    def test_does_not_connect_reset(self):
        r=[row(0,1,10,0),row(1,2,11,0),row(1,2,11,1),row(2,3,12,1)]
        edges,_=chronological_edges(r,self.course);self.assertEqual(len(edges),2)
    def test_splits_road_sector_crossing(self):
        edges,names=chronological_edges([row(0,119,10),row(1,121,12)],self.course)
        self.assertEqual(names,['launch_flat','hill_entry']);self.assertEqual(len(edges),2)
        np.testing.assert_allclose(edges[0,1],edges[1,0])
    def test_missing_speed_breaks_curve(self):
        r=[row(0,1,10),row(1,2,11),row(2,3,12)];r[1]['primary_rpm']=None
        self.assertEqual(len(chronological_edges(r,self.course)[0]),0)

if __name__=='__main__':unittest.main()
