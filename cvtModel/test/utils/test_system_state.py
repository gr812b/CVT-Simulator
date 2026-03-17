import unittest

from cvt_simulator.utils.system_state import SystemState


class TestSystemState(unittest.TestCase):

    def test_initialization(self):
        state = SystemState(
            shift_distance=2.0,
            shift_velocity=5.0,
            primary_pulley_angular_velocity=100.0,
            secondary_pulley_angular_velocity=30.0,
        )
        self.assertEqual(state.shift_distance, 2.0)
        self.assertEqual(state.shift_velocity, 5.0)
        self.assertEqual(state.primary_pulley_angular_velocity, 100.0)
        self.assertEqual(state.secondary_pulley_angular_velocity, 30.0)

    def test_to_array(self):
        state = SystemState(
            shift_distance=2.0,
            shift_velocity=5.0,
            primary_pulley_angular_velocity=100.0,
            secondary_pulley_angular_velocity=30.0,
        )
        expected_array = [2.0, 5.0, 100.0, 30.0]
        self.assertEqual(state.to_array(), expected_array)

    def test_from_array(self):
        array = [2.0, 5.0, 100.0, 30.0]
        state = SystemState.from_array(array)
        self.assertEqual(state.shift_distance, 2.0)
        self.assertEqual(state.shift_velocity, 5.0)
        self.assertEqual(state.primary_pulley_angular_velocity, 100.0)
        self.assertEqual(state.secondary_pulley_angular_velocity, 30.0)


if __name__ == "__main__":
    unittest.main()
