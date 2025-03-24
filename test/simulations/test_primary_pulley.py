import unittest

from simulations.primary_pulley import PrimaryPulley
from constants.car_specs import MAX_SHIFT


class TestPrimaryPulley(unittest.TestCase):

    def setUp(self):
        self.primary_pulley = PrimaryPulley(
            spring_coeff_comp=1000,  # N/m
            initial_compression=0.1,  # m
            flyweight_mass=0.5,  # kg
            initial_flyweight_radius=0.05,  # m
            ramp_type=1
        )

    def test_calculate_flyweight_force(self):
        shift_distance = 0.1
        angular_velocity = 100
        force = self.primary_pulley.calculate_flyweight_force(
            shift_distance, angular_velocity
        )
        self.assertIsInstance(force, float)
        self.assertGreaterEqual(force, 0)

    def test_calculate_spring_comp_force(self):
        compression = 0.1
        force = self.primary_pulley.calculate_spring_comp_force(compression)
        self.assertIsInstance(force, float)
        self.assertGreaterEqual(force, 0)

    def test_calculate_net_force(self):
        shift_distance = 0.1
        angular_velocity = 100
        net_force = self.primary_pulley.calculate_net_force(
            shift_distance, angular_velocity
        )
        self.assertIsInstance(net_force, float)

    def test_shift_distance_bounds(self):
        angular_velocity = 100
        force = self.primary_pulley.calculate_flyweight_force(-1, angular_velocity)
        self.assertIsInstance(force, float)
        self.assertGreaterEqual(force, 0)

        force = self.primary_pulley.calculate_flyweight_force(
            MAX_SHIFT + 1, angular_velocity
        )
        self.assertIsInstance(force, float)
        self.assertGreaterEqual(force, 0)


if __name__ == "__main__":
    unittest.main()
