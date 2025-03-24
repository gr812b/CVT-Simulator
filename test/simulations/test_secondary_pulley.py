import unittest
import numpy as np

from simulations.secondary_pulley import SecondaryPulley
from utils.theoretical_models import TheoreticalModels as tm

from constants.car_specs import BELT_HEIGHT


class TestSecondaryPulley(unittest.TestCase):

    def setUp(self):
        self.pulley = SecondaryPulley(
            spring_coeff_tors=10.0,
            spring_coeff_comp=100.0,
            initial_rotation=0.1,
            initial_compression=0.1,
            helix_radius=0.05,
            ramp_type=1,
        )

    def test_calculate_helix_force(self):
        torque = 10.0
        spring_torque = 10.0
        shift_distance = 0.025
        expected_force = -(torque + spring_torque) / (
            2
            * np.tan(np.arctan(-0.5774))
            * (tm.outer_sec_radius(shift_distance) - BELT_HEIGHT / 2)
        )
        result = self.pulley.calculate_helix_force(
            torque, spring_torque, shift_distance
        )
        self.assertAlmostEqual(result, expected_force, places=5)

    def test_calculate_spring_comp_force(self):
        compression = 0.02
        expected_force = tm.hookes_law_comp(
            self.pulley.spring_coeff_comp, self.pulley.initial_compression + compression
        )
        result = self.pulley.calculate_spring_comp_force(compression)
        self.assertAlmostEqual(result, expected_force, places=5)

    def test_calculate_spring_tors_torque(self):
        shift_distance = 0.025
        rotation = (
            self.pulley.initial_rotation
            + self.pulley.ramp.height(shift_distance) / self.pulley.helix_radius
        )
        expected_torque = tm.hookes_law_tors(self.pulley.spring_coeff_tors, rotation)
        result = self.pulley.calculate_spring_tors_torque(shift_distance)
        self.assertAlmostEqual(result, expected_torque, places=5)

    def test_calculate_net_force(self):
        torque = 50.0
        shift_distance = 0.025
        spring_comp_force = self.pulley.calculate_spring_comp_force(shift_distance)
        spring_tors_torque = self.pulley.calculate_spring_tors_torque(shift_distance)
        helix_force = self.pulley.calculate_helix_force(
            torque, spring_tors_torque, shift_distance
        )
        expected_net_force = helix_force + spring_comp_force
        result = self.pulley.calculate_net_force(torque, shift_distance)
        self.assertAlmostEqual(result, expected_net_force, places=5)


if __name__ == "__main__":
    unittest.main()
