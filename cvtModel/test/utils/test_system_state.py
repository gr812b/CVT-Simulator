import unittest

from cvt_simulator.core.system_state import SystemState
from cvt_simulator.constants.car_specs import MAX_SHIFT


class TestSystemState(unittest.TestCase):

    def test_initialization(self):
        state = SystemState(
            s=2.0,
            s_dot=5.0,
            ω_p=100.0,
            ω_s=30.0,
            v_b=12.0,
        )
        self.assertEqual(state.s, 2.0)
        self.assertEqual(state.s_dot, 5.0)
        self.assertEqual(state.ω_p, 100.0)
        self.assertEqual(state.ω_s, 30.0)
        self.assertEqual(state.v_b, 12.0)

    def test_to_array(self):
        state = SystemState(
            s=2.0,
            s_dot=5.0,
            ω_p=100.0,
            ω_s=30.0,
            v_b=12.0,
        )
        expected_array = [2.0, 5.0, 100.0, 30.0, 12.0]
        self.assertEqual(state.to_array(), expected_array)

    def test_from_array(self):
        array = [MAX_SHIFT, 5.0, 100.0, 30.0, 12.0]
        state = SystemState.from_array(array)
        # Shift distance is clamped when fetching it
        self.assertEqual(state.s, MAX_SHIFT)
        self.assertEqual(state.s_dot, 5.0)
        self.assertEqual(state.ω_p, 100.0)
        self.assertEqual(state.ω_s, 30.0)
        self.assertEqual(state.v_b, 12.0)

    def test_from_array_with_legacy_state_vector(self):
        array = [MAX_SHIFT, 5.0, 100.0, 30.0]
        state = SystemState.from_array(array)

        self.assertEqual(state.s, MAX_SHIFT)
        self.assertEqual(state.s_dot, 5.0)
        self.assertEqual(state.ω_p, 100.0)
        self.assertEqual(state.ω_s, 30.0)
        self.assertEqual(state.v_b, 0.0)


if __name__ == "__main__":
    unittest.main()
