import unittest
import numpy as np
import pandas as pd
from unittest.mock import patch

from scipy.integrate import solve_ivp
from utils.simulation_result import SimulationResult
from utils.system_state import SystemState


class TestSimulationResult(unittest.TestCase):

    def setUp(self):
        # Define a simple ODE system for testing
        def simple_ode(t, y):
            return [y[1], -0.1 * y[1] - y[0]]

        # Solve the ODE system
        y0 = [1.0, 0.0]
        t_span = (0, 10)
        t_eval = np.linspace(*t_span, 100)
        self.solution = solve_ivp(simple_ode, t_span, y0, t_eval=t_eval)

        # Mock SystemState.from_array to return a simple object
        self.original_from_array = SystemState.from_array
        SystemState.from_array = lambda arr: SystemState(
            car_velocity=arr[0],
            car_position=arr[1],
            shift_velocity=arr[0],
            shift_distance=arr[1],
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
        self.assertIn("car_position", df.columns)

    @patch.object(SimulationResult, "plot")
    def test_plot(self, mock_plot):
        result = SimulationResult(self.solution)
        result.plot("car_velocity")
        mock_plot.assert_called_once_with("car_velocity")


if __name__ == "__main__":
    unittest.main()
