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


if __name__=='__main__':unittest.main()
