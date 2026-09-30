"""Checks of the two transformations used in the retained-output review."""
import unittest
import numpy as np

from analysis.archive_review import STATES, historical_metric, local_loading


class ArchiveReviewTests(unittest.TestCase):
    def test_fraction_and_percent_are_distinct(self):
        ref = {'time_s': np.array([0., 1.])}
        var = {'time_s': np.array([0., 1.])}
        for k in STATES:
            ref['state.' + k] = np.array([0., 2.])
            var['state.' + k] = np.array([.02, 2.02])
        result = historical_metric(ref, var)
        for metric in result['states'].values():
            self.assertAlmostEqual(metric['fraction'], .01)
            self.assertAlmostEqual(metric['percent'], 1.)

    def test_endpoint_loading_integrates_to_saved_resultant(self):
        # Constant-radius steady transport: exact wrap ODE has exponential
        # loading for nonzero signed traction and uniform loading at zero.
        sb = np.sin(.2)
        assembly = {'geometry': {'sheave_half_angle_rad': .2,
                     'belt': {'height_m': .01, 'outer_width_m': .02, 'inner_width_m': .02}},
                    'inertias': {'belt_density_kg_per_m3': 1000.}}
        for lam in (0., .3, -.3):
            wrap = np.pi
            z = lam * wrap / sb
            G = 2*sb/wrap if lam == 0 else lam/np.tanh(z/2)
            H = 0 if lam == 0 else (2*sb-G*wrap)/lam
            d = {'state.belt_speed_m_per_s': np.array([2.]),
                 'state.belt_acceleration_m_per_s2': np.array([0.]),
                 'state.shift_speed_m_per_s': np.array([0.]),
                 'state.shift_acceleration_m_per_s2': np.array([0.])}
            for side in ('primary', 'secondary'):
                values = {'contact.'+side+'_lambda':lam, 'contact.'+side+'_normal_N':100.,
                          'coefficient.'+side+'_H':H, 'coefficient.'+side+'_G':G,
                          'geometry.'+side+'_radius_cm_m':.05,
                          'geometry.'+side+'_d_radius_ds':0.,
                          'geometry.'+side+'_d2_radius_ds2_per_m':0.}
                d.update({k:np.array([v]) for k,v in values.items()})
            result = local_loading(d, assembly)
            nmin = result['primary_min_local_N_per_rad'][0]
            angles = np.linspace(0, wrap, 10001)
            n = nmin*np.exp(abs(lam)/sb*angles)
            self.assertAlmostEqual(np.trapezoid(n, angles),100.,places=5)
            self.assertAlmostEqual(result['primary_min_tension_N'][0]-sb*nmin,.8)
            self.assertAlmostEqual(result['endpoint_sum_difference_N'][0],0.)


if __name__ == '__main__':
    unittest.main()
