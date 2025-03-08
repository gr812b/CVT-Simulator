import unittest

from simulations.car_simulation import CarSimulator


class TestCarSimulator(unittest.TestCase):

    def setUp(self):
        self.simulator = CarSimulator(car_mass=1000)  # 1000 kg

    def test_calculate_acceleration(self):
        force = 2000  # 2000 N
        expected_acceleration = 2.0  # m/s^2
        self.assertEqual(
            self.simulator.calculate_acceleration(force), expected_acceleration
        )


if __name__ == "__main__":
    unittest.main()
