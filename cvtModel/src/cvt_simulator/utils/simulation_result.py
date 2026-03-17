from cvt_simulator.utils.system_state import SystemState
from cvt_simulator.utils.state_computations import (
    secondary_pulley_angular_velocity_to_car_velocity,
)
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


class SimulationResult:
    def __init__(self, solution=None, time=None, states=None):
        """Initialize with solution from solve_ivp and parse it into states, or directly with time and states."""
        if solution is not None:
            self.time = solution.t
            self.states = self.parse_solution(solution)
        else:
            self.time = time
            self.states = states

    @staticmethod
    def parse_solution(solution):
        """Parses the solution from solve_ivp into a list of SystemState instances."""
        states = [SystemState.from_array(state) for state in solution.y.T]
        return states

    @staticmethod
    def from_csv(filename="simulation_output.csv"):
        """Reads the solution states from a CSV file and returns a SimulationResult instance."""
        df = pd.read_csv(filename)
        time = df["time"].values
        states = [
            SystemState(
                shift_distance=row["shift_distance"],
                shift_velocity=row["shift_velocity"],
                primary_pulley_angular_velocity=row[
                    "primary_pulley_angular_velocity"
                ],
                secondary_pulley_angular_velocity=row[
                    "secondary_pulley_angular_velocity"
                ],
            )
            for _, row in df.iterrows()
        ]
        return SimulationResult(time=time, states=states)

    def write_csv(self, filename="simulation_output.csv"):
        """Writes the parsed solution states to a CSV file.
        
        Includes 4 DOF from state plus derived quantities.
        Positions (car_position, engine_angular_position) are computed via kinematic integration.
        """
        # Compute positions via trapezoidal integration of velocities
        car_positions = self._compute_positions(
            self.time,
            [
                secondary_pulley_angular_velocity_to_car_velocity(
                    s.secondary_pulley_angular_velocity
                )
                for s in self.states
            ],
        )
        engine_positions = self._compute_positions(
            self.time,
            [s.primary_pulley_angular_velocity for s in self.states],
        )
        
        data = {
            "time": self.time,
            "shift_distance": [state.shift_distance for state in self.states],
            "shift_velocity": [state.shift_velocity for state in self.states],
            "primary_pulley_angular_velocity": [state.primary_pulley_angular_velocity for state in self.states],
            "secondary_pulley_angular_velocity": [state.secondary_pulley_angular_velocity for state in self.states],
            "car_velocity": [
                secondary_pulley_angular_velocity_to_car_velocity(
                    s.secondary_pulley_angular_velocity
                )
                for s in self.states
            ],
            "engine_angular_velocity": [
                s.primary_pulley_angular_velocity for s in self.states
            ],
            "car_position": car_positions,
            "engine_angular_position": engine_positions,
        }
        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)

    def plot(self, field="secondary_pulley_angular_velocity"):
        """Plots a selected field over time.
        
        Available fields: shift_distance, shift_velocity, primary_pulley_angular_velocity,
                        secondary_pulley_angular_velocity, car_velocity, engine_angular_velocity
        """
        # Mapping field names to their respective data
        field_data = {
            "shift_distance": [state.shift_distance for state in self.states],
            "shift_velocity": [state.shift_velocity for state in self.states],
            "primary_pulley_angular_velocity": [state.primary_pulley_angular_velocity for state in self.states],
            "secondary_pulley_angular_velocity": [state.secondary_pulley_angular_velocity for state in self.states],
            "car_velocity": [
                secondary_pulley_angular_velocity_to_car_velocity(
                    s.secondary_pulley_angular_velocity
                )
                for s in self.states
            ],
            "engine_angular_velocity": [
                s.primary_pulley_angular_velocity for s in self.states
            ],
        }

        if field not in field_data:
            raise ValueError(
                f"Invalid field '{field}'. Choose from {list(field_data.keys())}"
            )

        # Plotting
        plt.plot(self.time, field_data[field])
        plt.xlabel("Time (s)")
        plt.ylabel(field.replace("_", " ").capitalize())
        plt.title(f"{field.replace('_', ' ').capitalize()} Over Time")
        plt.grid()
        plt.show()

    @staticmethod
    def _compute_positions(time, velocities):
        """Compute positions via kinematic integration of velocities using trapezoidal rule."""
        positions = np.zeros(len(time))
        for i in range(1, len(time)):
            dt = time[i] - time[i-1]
            positions[i] = positions[i-1] + (velocities[i-1] + velocities[i]) / 2.0 * dt
        return positions
