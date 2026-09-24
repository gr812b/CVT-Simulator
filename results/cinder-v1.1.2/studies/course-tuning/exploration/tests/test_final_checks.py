"""Regression tests for the final course and observed-settling classifier."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from analysis.final_course_checks import evaluate_window, check_hill, DEFAULT_CRITERIA
from infrastructure.course import Course
from infrastructure.common import load_json
from infrastructure.tunes import resolve_tune


def sample_rows(duration=6.,step=.01):
    return [{'time_s':float(t),'distance_m':356.+7.*float(t),'segment_id':0,
        'shift_mm':10.,'active_shift_fraction':.45,'shift_rate_mm_s':0.,
        'primary_rpm':3200.,'secondary_rpm':1800.,'belt_speed_m_s':19.,
        'speed_m_s':7.,'vehicle_acceleration_m_s2':0.,'primary_alpha_rad_s2':0.,
        'secondary_alpha_rad_s2':0.,'belt_acceleration_m_s2':0.,
        'shift_acceleration_m_s2':0.,'grade_deg':18.,'engagement':'engaged',
        'shift_constraint':'free','contact_mode':'stick_stick','inspection_error':''}
        for t in np.arange(0,duration+.5*step,step)]


class WindowTests(unittest.TestCase):
    def evaluate(self,rows,events=None):
        return evaluate_window(rows,events or [],DEFAULT_CRITERIA,2.4892,19.05,18.)
    def test_stationary_travelling_interior_passes(self):
        result=self.evaluate(sample_rows());self.assertTrue(result['passed']);self.assertAlmostEqual(result['mean_shift_mm'],10.)
    def test_constant_shift_accelerating_vehicle_is_not_steady(self):
        rows=sample_rows()
        for r in rows:r['vehicle_acceleration_m_s2']=.1
        self.assertIn('max_abs_vehicle_acceleration_m_s2',self.evaluate(rows)['failed_checks'])
    def test_slowly_moving_shift_is_not_steady(self):
        rows=sample_rows()
        for r in rows:r['shift_rate_mm_s']=.06
        self.assertFalse(self.evaluate(rows)['passed'])
    def test_constant_derivative_but_large_range_fails(self):
        rows=sample_rows()
        for r in rows:r['shift_mm']+=.1*r['time_s']
        self.assertIn('shift_range_mm',self.evaluate(rows)['failed_checks'])
    def test_upper_stop_not_mislabelled_as_interior(self):
        rows=sample_rows()
        for r in rows:r['shift_constraint']='upper_stop';r['shift_mm']=19.05
        self.assertFalse(self.evaluate(rows)['passed'])
    def test_low_seat_not_mislabelled_as_interior(self):
        rows=sample_rows()
        for r in rows:r['shift_mm']=2.4892
        self.assertFalse(self.evaluate(rows)['passed'])
    def test_missing_rhs_does_not_pass(self):
        rows=sample_rows();rows[10].pop('primary_alpha_rad_s2')
        self.assertFalse(self.evaluate(rows)['passed'])
    def test_one_spike_not_hidden_by_averaging(self):
        rows=sample_rows();rows[100]['secondary_alpha_rad_s2']=1.
        self.assertFalse(self.evaluate(rows)['passed'])
    def test_missing_sample_interval_fails(self):
        rows=sample_rows();del rows[200:250]
        self.assertIn('insufficient_sample_resolution',self.evaluate(rows)['failed_checks'])
    def test_short_window_fails(self):
        self.assertIn('insufficient_duration',self.evaluate(sample_rows(3.))['failed_checks'])
    def test_contact_change_fails(self):
        rows=sample_rows();rows[100]['contact_mode']='both_slip'
        self.assertFalse(self.evaluate(rows)['passed'])
    def test_hidden_physical_event_fails(self):
        self.assertFalse(self.evaluate(sample_rows(),[{'time_s':2.,'event_names':['cvt:stick_release']}])['passed'])
    def test_administrative_checkpoint_is_not_physical_event(self):
        self.assertTrue(self.evaluate(sample_rows(),[{'time_s':2.,'event_names':['host:checkpoint']}])['passed'])
    def test_grade_ramp_fails(self):
        rows=sample_rows();rows[40]['grade_deg']=17.99
        self.assertFalse(self.evaluate(rows)['passed'])
    def test_reverse_travel_fails(self):
        rows=sample_rows()
        for r in rows:r['speed_m_s']=-2.
        self.assertFalse(self.evaluate(rows)['passed'])
    def test_inspection_error_fails(self):
        rows=sample_rows();rows[100]['inspection_error']='failed'
        self.assertFalse(self.evaluate(rows)['passed'])


class FinalInputTests(unittest.TestCase):
    def setUp(self):
        self.old=load_json(ROOT/'inputs/course.json')
        self.new=load_json(ROOT/'inputs/course_unified_candidate.json')
    def test_approach_main_hill_and_recovery_unchanged(self):
        a,b=Course(self.old),Course(self.new)
        for x in np.linspace(0,264,1057):
            self.assertEqual(a.grade_and_gradient(float(x)),b.grade_and_gradient(float(x)))
    def test_six_cycles_four_fully_untapered(self):
        c=Course(self.new);s=next(s for s in c.sectors if s.name=='cyclic')
        self.assertEqual(c.count,6);self.assertEqual(s.end_m-s.start_m,72.)
        env=self.new['cyclic_envelope_length_m']
        self.assertEqual(sum(k*12>=env and (k+1)*12<=72-env for k in range(6)),4)
    def test_grade_and_slopes_match_at_boundaries(self):
        c=Course(self.new)
        for s in c.sectors[1:]:
            a=c.grade_and_gradient(s.start_m-1e-7);b=c.grade_and_gradient(s.start_m+1e-7)
            np.testing.assert_allclose(a,b,atol=1e-6)
    def test_driver_unchanged(self):
        self.assertEqual(self.new['driver'],self.old['driver'])
    def test_ten_independent_candidates(self):
        fleet=load_json(ROOT/'inputs/competitors_final_check.json')['competitors']
        self.assertEqual(len(fleet),10);self.assertEqual(len(set(t['id'] for t in fleet)),10)
        by={t['id']:t['knobs'] for t in fleet}
        self.assertEqual(by['D02'],{'tip_mass_scale':.65,'primary_preload_scale':1.15})
        self.assertEqual(by['D02_M'],{'primary_preload_scale':1.15})
        self.assertEqual(by['D02_P'],{'tip_mass_scale':.65})
    def test_original_car_inputs_are_retained(self):
        old={t['id']:t for t in load_json(ROOT/'inputs/competitors_features.json')['competitors']}
        for t in load_json(ROOT/'inputs/competitors_final_check.json')['competitors']:
            if t['id'] in old:self.assertEqual(t,old[t['id']])
    def test_boundary_identity_and_mechanism_geometry(self):
        base_path=ROOT.parents[2]/'defaults/baja/simulation_case.json'
        if not base_path.exists():self.skipTest('Installed shared Results baseline not present')
        base=load_json(base_path)
        for tune in load_json(ROOT/'inputs/competitors_final_check.json')['competitors']:
            doc,_=resolve_tune(base,tune)
            for k in ('shaft_boundaries','host','scenario','execution'):
                self.assertEqual(doc[k],base[k])


if __name__=='__main__':unittest.main()
