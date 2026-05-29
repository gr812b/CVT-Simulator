import unittest

from cvt_simulator.core.components.secondary_pulley import SecondaryPulley
from cvt_simulator.ramps.piecewise_ramp import PiecewiseRamp
from cvt_simulator.ramps.linear_segment import LinearSegment
from cvt_simulator.geometry.theoretical_models import TheoreticalModels as tm
from cvt_simulator.sim.system_state import SystemState


class TestSecondaryPulley(unittest.TestCase):

    def setUp(self):
        angle_ramp = PiecewiseRamp()
        angle_ramp.add_segment(LinearSegment(length=1.0, angle=-30.0))
        helix_radius = 0.05
        from cvt_simulator.ramps.theta_ramp import ThetaRamp

        theta_ramp = ThetaRamp(angle_ramp, helix_radius)

        self.pulley = SecondaryPulley(
            spring_coeff_tors=10.0,
            spring_coeff_comp=100.0,
            initial_rotation=0.1,
            initial_compression=0.1,
            helix_ramp=theta_ramp,
            helix_radius=helix_radius,
        )

    def test_calculate_helix_force(self):
        torque = 10.0
        shift_distance = 0.015
        # Call internal helix helper and check structure
        helix = self.pulley._calculate_helix_force(torque, float(shift_distance))
        self.assertTrue(hasattr(helix, "net"))
        self.assertIsInstance(helix.net, float)

    def test_calculate_spring_comp_force(self):
        compression = 0.01
        res = self.pulley._calculate_spring_comp_force(compression)
        expected_force = tm.hookes_law_comp(
            self.pulley.spring_coeff_comp, self.pulley.initial_compression + compression
        )
        # allow small numerical differences from conversions
        self.assertAlmostEqual(res.net, expected_force, places=5)

    def test_calculate_spring_tors_torque(self):
        shift_distance = 0.015
        # Use internal torsion helper
        tors = self.pulley._calculate_spring_tors_torque(shift_distance)
        rotation = tors.rotation
        expected_torque = tm.hookes_law_tors(self.pulley.spring_coeff_tors, rotation)
        self.assertAlmostEqual(tors.net, expected_torque, places=7)

    def test_calculate_net_force(self):
        torque = 50.0
        shift_distance = 0.015
        state = SystemState(s=shift_distance)
        pf = self.pulley.calculate_axial_clamping_force(state, torque)
        # net should equal pulley_breakdown.net + belt_wrap.axial_belt_force
        self.assertAlmostEqual(
            pf.net, pf.pulley_breakdown.net + pf.belt_wrap.axial_belt_force, places=7
        )


if __name__ == "__main__":
    unittest.main()
