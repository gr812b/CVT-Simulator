import unittest

from utils.system_state import SystemState


class TestSystemState(unittest.TestCase):

    def test_initialization(self):
        state = SystemState(
            engine_angular_velocity=100.0,
            engine_angular_position=50.0,
            car_velocity=30.0,
            car_position=10.0,
            shift_velocity=5.0,
            shift_distance=2.0
        )
        self.assertEqual(state.engine_angular_velocity, 100.0)
        self.assertEqual(state.engine_angular_position, 50.0)
        self.assertEqual(state.car_velocity, 30.0)
        self.assertEqual(state.car_position, 10.0)
        self.assertEqual(state.shift_velocity, 5.0)
        self.assertEqual(state.shift_distance, 2.0)

    def test_to_array(self):
        state = SystemState(
            engine_angular_velocity=100.0,
            engine_angular_position=50.0,
            car_velocity=30.0,
            car_position=10.0,
            shift_velocity=5.0,
            shift_distance=2.0
        )
        expected_array = [100.0, 50.0, 30.0, 10.0, 5.0, 2.0]
        self.assertEqual(state.to_array(), expected_array)

    def test_from_array(self):
        array = [100.0, 50.0, 30.0, 10.0, 5.0, 2.0]
        state = SystemState.from_array(array)
        self.assertEqual(state.engine_angular_velocity, 100.0)
        self.assertEqual(state.engine_angular_position, 50.0)
        self.assertEqual(state.car_velocity, 30.0)
        self.assertEqual(state.car_position, 10.0)
        self.assertEqual(state.shift_velocity, 5.0)
        self.assertEqual(state.shift_distance, 2.0)


if __name__ == '__main__':
    unittest.main()
