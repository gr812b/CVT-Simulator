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
from analysis.feature_metrics import interval_summary,analyze_car,_cycle_rows
from analysis.shift_curves import chronological_edges


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
        c=Course(self.base);r=[row(float(x),float(x),10+.01*x) for x in np.linspace(264,336,1201)]
        cycles=_cycle_rows('T',r,c)
        for cy in cycles:
            self.assertLess(cy['detrended_first_harmonic_peak_to_peak_mm'],1e-10)
            self.assertEqual(cy['opening_travel_mm'],0.)
    def test_known_cyclic_modulation(self):
        c=Course(self.base);r=[row(float(x),float(x),10+.01*x+.5*np.sin(2*np.pi*(x-264)/12.)) for x in np.linspace(264,336,1201)]
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
