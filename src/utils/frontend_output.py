import pandas as pd
import matplotlib.pyplot as plt
from utils.simulation_result import SimulationResult
from constants.car_specs import (
    GEARBOX_RATIO,
    WHEEL_RADIUS,
    MAX_SHIFT,
)
from utils.theoretical_models import TheoreticalModels as tm
from utils.conversions import rad_s_to_rpm, meter_s_to_km_h


class FormattedSimulationResult(SimulationResult):
    def __init__(self, solution=None, time=None, states=None):
        """
        Initialize using the base SimulationResult and then compute additional columns.
        """
        super().__init__(solution=solution, time=time, states=states)
        self.compute_updated_metrics()

    def compute_updated_metrics(self):
        """
        Recompute the simulation outputs to add:
        - Engine angular position
        - Secondary angular position
        - Engine angular velocity (RPM)
        """
        self.engine_angular_positions = []
        self.secondary_angular_positions = []
        self.engine_angular_velocities = []
        self.car_velocities = []
        self.shift_distance_percents = []

        current_engine_angle = 0.0
        current_secondary_angle = 0.0

        for i, t in enumerate(self.time):
            dt = t - self.time[i - 1] if i > 0 else 0
            state = self.states[i]

            cvt_ratio = tm.current_cvt_ratio(state.shift_distance)
            wheel_to_engine_ratio = (cvt_ratio * GEARBOX_RATIO) / WHEEL_RADIUS
            engine_velocity = state.car_velocity * wheel_to_engine_ratio

            engine_rpm = rad_s_to_rpm(engine_velocity)
            current_engine_angle += engine_velocity * dt
            current_secondary_angle += engine_velocity / cvt_ratio * dt
            car_km_per_hour = meter_s_to_km_h(state.car_velocity)
            shift_distance_percent = state.shift_distance / MAX_SHIFT

            # Append the calculated values.
            self.engine_angular_positions.append(current_engine_angle)
            self.secondary_angular_positions.append(current_secondary_angle)
            self.engine_angular_velocities.append(engine_rpm)
            self.car_velocities.append(car_km_per_hour)
            self.shift_distance_percents.append(shift_distance_percent)

    @staticmethod
    def from_csv(filename="simulation_output.csv"):
        """
        Reads the simulation states from a CSV file and returns an FormattedSimulationResult instance.
        """
        base_result = SimulationResult.from_csv(filename)
        return FormattedSimulationResult(
            time=base_result.time, states=base_result.states
        )

    def write_formatted_csv(self, filename="front_end_output.csv"):
        """
        Writes the original simulation data along with the additional computed columns to a CSV file.
        """
        data = {
            "time": self.time,
            "car_velocity": self.car_velocities,
            "car_position": [state.car_position for state in self.states],
            "shift_distance": self.shift_distance_percents,
            "engine_angular_position": self.engine_angular_positions,
            "secondary_angular_position": self.secondary_angular_positions,
            "engine_angular_velocity": self.engine_angular_velocities,
        }
        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)

    def plot_updates(self):
        """
        Optionally, plot the new computed columns for quick visualization.
        """
        fig, axs = plt.subplots(2, 3, figsize=(12, 8), sharex=True)

        axs[0, 0].plot(self.time, self.engine_angular_positions)
        axs[0, 0].set_ylabel("Engine Angular Position (rad)")
        axs[0, 0].set_title("Engine Angular Position Over Time")
        axs[0, 0].grid(True)

        axs[0, 1].plot(self.time, self.secondary_angular_positions)
        axs[0, 1].set_ylabel("Secondary Angular Position (rad)")
        axs[0, 1].set_title("Secondary Angular Position Over Time")
        axs[0, 1].grid(True)

        axs[1, 0].plot(self.time, self.engine_angular_velocities)
        axs[1, 0].set_xlabel("Time (s)")
        axs[1, 0].set_ylabel("Engine Angular Velocity (rpm)")
        axs[1, 0].set_title("Engine Angular Velocity Over Time")
        axs[1, 0].grid(True)

        axs[1, 1].plot(self.time, self.car_velocities)
        axs[1, 1].set_xlabel("Time (s)")
        axs[1, 1].set_ylabel("Car Velocity (km/h)")
        axs[1, 1].set_title("Car Velocity Over Time")
        axs[1, 1].grid(True)

        axs[1, 2].plot(self.time, self.shift_distance_percents)
        axs[1, 2].set_xlabel("Time (s)")
        axs[1, 2].set_ylabel("Shift Distance (%)")
        axs[1, 2].set_title("Shift Distance Over Time")
        axs[1, 2].grid(True)

        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    result = FormattedSimulationResult.from_csv("simulation_output.csv")
    result.write_formatted_csv()
    result.plot_updates()
