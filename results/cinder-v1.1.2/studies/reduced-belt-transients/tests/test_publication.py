"""Regression checks for the two scientifically consequential publication operations."""
import unittest
import numpy as np
from analysis.publication import sample_segments, STATE_KEYS
from experiments.publication import omit_two_terms

class PublicationChecks(unittest.TestCase):
    def test_event_limits_are_not_interpolated_across(self):
        d={'time_s':np.array([0.,1.,1.,2.]),'segment_index':np.array([0,0,1,1])}
        for k in STATE_KEYS:d[k]=np.array([0.,1.,10.,12.])
        right,_=sample_segments(d,np.array([.5,1.,1.5]))
        left,_=sample_segments(d,np.array([.5,1.,1.5]),side='left')
        np.testing.assert_allclose(right[:,0],[.5,10.,11.])
        np.testing.assert_allclose(left[:,0],[.5,1.,11.])

    def test_joint_omission_changes_bias_only_and_restores(self):
        from cinder.model.cvt.dynamics.rows import tension_loop as m
        r=dict(linear_density=.3,radius=.08,d_radius_ds=2.,d2_radius_ds2=-7.,belt_speed=14.,shift_speed=.02)
        a={k:v for k,v in r.items() if k!='d2_radius_ds2'}
        original_r=m._radial_offset;original_a=m._tangential_offset
        full_r=original_r(**r);full_a=original_a(**a)
        with omit_two_terms():
            small_r=m._radial_offset(**r);small_a=m._tangential_offset(**a)
            self.assertAlmostEqual(full_r.bias-small_r.bias,-.3*.08*(-7.)*.02**2)
            self.assertAlmostEqual(full_a.bias-small_a.bias,.3*2.*.02*14.)
            self.assertEqual(full_r.gains,small_r.gains)
            self.assertEqual(full_a.gains,small_a.gains)
        self.assertIs(m._radial_offset,original_r);self.assertIs(m._tangential_offset,original_a)

if __name__=='__main__':unittest.main()
