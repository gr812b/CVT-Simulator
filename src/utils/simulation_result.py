from utils.system_state import SystemState
import pandas as pd
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
        """Parses the solution from solve_ivp into a list of DrivetrainState instances."""
        states = [SystemState.from_array(state) for state in solution.y.T]
        return states

    @staticmethod
    def from_csv(filename="simulation_output.csv"):
        """Reads the solution states from a CSV file and returns a SimulationResult instance."""
        df = pd.read_csv(filename)
        time = df["time"].values
        states = [
            SystemState(
                car_velocity=row["car_velocity"],
                car_position=row["car_position"],
                shift_velocity=row["shift_velocity"],
                shift_distance=row["shift_distance"],
            )
            for _, row in df.iterrows()
        ]
        return SimulationResult(time=time, states=states)

    def write_csv(self, filename="simulation_output.csv"):
        """Writes the parsed solution states to a CSV file."""
        data = {
            "time": self.time,
            "car_velocity": [state.car_velocity for state in self.states],
            "car_position": [state.car_position for state in self.states],
            "shift_velocity": [state.shift_velocity for state in self.states],
            "shift_distance": [state.shift_distance for state in self.states],
        }
        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)

    def plot(self, field="car_velocity"):
        """Plots a selected field over time."""
        # Mapping field names to their respective data
        field_data = {
            "car_velocity": [state.car_velocity for state in self.states],
            "car_position": [state.car_position for state in self.states],
            "shift_velocity": [state.shift_velocity for state in self.states],
            "shift_distance": [state.shift_distance for state in self.states],
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
