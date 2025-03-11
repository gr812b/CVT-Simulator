import unittest

from simulations.engine_simulation import EngineSimulator


class TestEngineSimulator(unittest.TestCase):

    def test_init(self):
        def mock_torque_curve(angular_velocity):
            return 10.0

        inertia = 5.0
        simulator = EngineSimulator(torque_curve=mock_torque_curve, inertia=inertia)

        self.assertEqual(simulator.torque_curve, mock_torque_curve)
        self.assertEqual(simulator.inertia, inertia)

    def test_get_torque(self):
        def mock_torque_curve(angular_velocity):
            return angular_velocity * 2.0

        simulator = EngineSimulator(torque_curve=mock_torque_curve, inertia=5.0)
        self.assertEqual(simulator.get_torque(5.0), 10.0)

    def test_get_power(self):
        def mock_torque_curve(angular_velocity):
            return angular_velocity * 2.0

        simulator = EngineSimulator(torque_curve=mock_torque_curve, inertia=5.0)
        self.assertEqual(simulator.get_power(5.0), 50.0)

    def test_calculate_angular_acceleration(self):
        def mock_torque_curve(angular_velocity):
            return angular_velocity * 2.0

        simulator = EngineSimulator(torque_curve=mock_torque_curve, inertia=5.0)
        angular_velocity = 5.0
        load_torque = 5.0
        expected_acceleration = (10.0 - load_torque) / 5.0
        self.assertEqual(
            simulator.calculate_angular_acceleration(angular_velocity, load_torque),
            expected_acceleration,
        )


if __name__ == "__main__":
    unittest.main()
