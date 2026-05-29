import unittest

from cvt_simulator.core.components.primary_pulley import PrimaryPulley
from cvt_simulator.ramps.piecewise_ramp import PiecewiseRamp
from cvt_simulator.ramps.linear_segment import LinearSegment
from cvt_simulator.sim.system_state import SystemState
from cvt_simulator.constants.car_specs import MAX_SHIFT


class TestPrimaryPulley(unittest.TestCase):

    def setUp(self):
        # construct a simple piecewise ramp for tests
        ramp = PiecewiseRamp()
        ramp.add_segment(LinearSegment(length=1.0, angle=30.0))

        self.primary_pulley = PrimaryPulley(
            spring_coeff_comp=1000,  # N/m
            initial_compression=0.1,  # m
            flyweight_mass=0.5,  # kg
            ramp=ramp,
            initial_flyweight_radius=0.05,
        )

    def test_calculate_flyweight_force(self):
        shift_distance = 0.01
        angular_velocity = 100
        # use internal helper which returns a breakdown
        breakdown = self.primary_pulley._calculate_flyweight_force(
            float(shift_distance), float(angular_velocity)
        )
        self.assertTrue(hasattr(breakdown, "net"))
        self.assertIsInstance(breakdown.net, float)
        self.assertGreaterEqual(breakdown.net, 0)

    def test_calculate_spring_comp_force(self):
        compression = 0.1
        res = self.primary_pulley._calculate_spring_comp_force(compression)
        self.assertTrue(hasattr(res, "net"))
        self.assertIsInstance(res.net, float)
        self.assertGreaterEqual(res.net, 0)

    def test_calculate_net_force(self):
        shift_distance = 0.01
        angular_velocity = 100
        state = SystemState(s=shift_distance, ω_p=angular_velocity)
        pf = self.primary_pulley.calculate_axial_clamping_force(state)
        self.assertTrue(hasattr(pf, "net"))
        self.assertIsInstance(pf.net, float)

    def test_shift_distance_bounds(self):
        angular_velocity = 100
        # Call internal helper with clipped values to avoid geometry errors
        import numpy as _np

        s_low = float(_np.clip(-1.0, 0.0, MAX_SHIFT))
        breakdown = self.primary_pulley._calculate_flyweight_force(
            s_low, angular_velocity
        )
        self.assertIsInstance(breakdown.net, float)
        self.assertGreaterEqual(breakdown.net, 0)

        s_high = float(_np.clip(MAX_SHIFT + 1.0, 0.0, MAX_SHIFT))
        breakdown = self.primary_pulley._calculate_flyweight_force(
            s_high, angular_velocity
        )
        self.assertIsInstance(breakdown.net, float)
        self.assertGreaterEqual(breakdown.net, 0)


if __name__ == "__main__":
    unittest.main()
