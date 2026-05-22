import unittest
import numpy as np
import pandas as pd
from unittest.mock import patch

from scipy.integrate import solve_ivp
from cvt_simulator.sim_utils.simulation_result import SimulationResult
from cvt_simulator.sim_utils.system_state import SystemState


class TestSimulationResult(unittest.TestCase):

    def setUp(self):
        # Define a simple ODE system for testing (4 DOF)
        def simple_ode(t, y):
            return [y[1], -0.1 * y[1] - y[0], 0.0, 0.0]

        # Solve the ODE system
        y0 = [1.0, 0.0, 0.0, 0.0]
        t_span = (0, 10)
        t_eval = np.linspace(*t_span, 100)
        self.solution = solve_ivp(simple_ode, t_span, y0, t_eval=t_eval)

        # Mock SystemState.from_array to return a simple object
        self.original_from_array = SystemState.from_array
        SystemState.from_array = lambda arr: SystemState(
            s=arr[0],
            s_dot=arr[1],
            ω_p=arr[2],
            ω_s=arr[3],
        )

    def tearDown(self):
        # Restore the original SystemState.from_array method
        SystemState.from_array = self.original_from_array

    def test_parse_solution(self):
        result = SimulationResult(self.solution)
        self.assertEqual(len(result.states), len(self.solution.t))
        self.assertIsInstance(result.states[0], SystemState)

    def test_write_csv(self):
        result = SimulationResult(self.solution)
        result.write_csv("test_output.csv")
        df = pd.read_csv("test_output.csv")
        self.assertEqual(len(df), len(self.solution.t))
        self.assertIn("time", df.columns)
        self.assertIn("shift_distance", df.columns)
        self.assertIn("car_position", df.columns)

    @patch.object(SimulationResult, "plot")
    def test_plot(self, mock_plot):
        result = SimulationResult(self.solution)
        result.plot("secondary_pulley_angular_velocity")
        mock_plot.assert_called_once_with("secondary_pulley_angular_velocity")


if __name__ == "__main__":
    unittest.main()
