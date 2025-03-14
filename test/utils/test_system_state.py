import unittest

from utils.system_state import SystemState


class TestSystemState(unittest.TestCase):

    def test_initialization(self):
        state = SystemState(
            car_velocity=30.0,
            car_position=10.0,
            shift_velocity=5.0,
            shift_distance=2.0,
        )
        self.assertEqual(state.car_velocity, 30.0)
        self.assertEqual(state.car_position, 10.0)
        self.assertEqual(state.shift_velocity, 5.0)
        self.assertEqual(state.shift_distance, 2.0)

    def test_to_array(self):
        state = SystemState(
            car_velocity=30.0,
            car_position=10.0,
            shift_velocity=5.0,
            shift_distance=2.0,
        )
        expected_array = [30.0, 10.0, 5.0, 2.0]
        self.assertEqual(state.to_array(), expected_array)

    def test_from_array(self):
        array = [30.0, 10.0, 5.0, 2.0]
        state = SystemState.from_array(array)
        self.assertEqual(state.car_velocity, 30.0)
        self.assertEqual(state.car_position, 10.0)
        self.assertEqual(state.shift_velocity, 5.0)
        self.assertEqual(state.shift_distance, 2.0)


if __name__ == "__main__":
    unittest.main()
