from typing import List
from cvt_simulator.models.dataTypes import SystemBreakdown
from cvt_simulator.utils.system_state import SystemState
import pandas as pd
from cvt_simulator.models.model_initializer import get_models
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.utils.simulation_result import SimulationResult
from dataclasses import is_dataclass, fields, dataclass


@dataclass
class TimeStepData:
    """
    Represents all the data for a single time step in the simulation.
    Uses the unified SystemBreakdown for clean access to all component data.
    """

    time: float
    state: SystemState
    system: SystemBreakdown


class FormattedSimulationResult:
    data: List[TimeStepData]

    def __init__(self, result: SimulationResult, args: SimulationArgs):
        """
        Initialize using the base SimulationResult and then compute additional columns.
        """
        self.data = []
        self.gather_model_states(result, args)

    def gather_model_states(self, result: SimulationResult, args: SimulationArgs):
        system_model = get_models(args)

        for i, (time, state) in enumerate(zip(result.time, result.states)):
            system_breakdown = system_model.get_breakdown(state)

            time_step_data = TimeStepData(
                time=time, state=state, system=system_breakdown
            )
            self.data.append(time_step_data)

    @staticmethod
    def from_csv(filename="simulation_output.csv", args: SimulationArgs = None):
        """
        Reads the simulation states from a CSV file and returns a FormattedSimulationResult instance.
        Note: args parameter is required to compute car_state and cvt_state breakdowns.
        """
        base_result = SimulationResult.from_csv(filename)
        if args is None:
            raise ValueError("SimulationArgs is required to compute model breakdowns")
        return FormattedSimulationResult(base_result, args)

    def write_formatted_csv(self, filename="front_end_output.csv"):
        """
        Flattens the data and writes to a CSV file for front-end consumption.
        """
        # Get all unique keys from all time steps by flattening the entire TimeStepData
        all_keys = set()

        # Collect all unique keys from all time steps
        for time_step in self.data:
            flat_time_step = self._flatten_dataclass(time_step)
            all_keys.update(flat_time_step.keys())

        # Initialize all columns
        data = {}
        for key in all_keys:
            data[key] = []

        # Populate all the flattened data
        for time_step in self.data:
            flat_time_step = self._flatten_dataclass(time_step)

            # For each key, append the value or None if missing
            for key in all_keys:
                if key in flat_time_step:
                    data[key].append(flat_time_step[key])
                else:
                    data[key].append(None)

        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)

    def _flatten_dataclass(self, obj, prefix=""):
        """
        Recursively flatten a dataclass object into a flat dictionary.
        """
        flat_dict = {}

        if is_dataclass(obj):
            for field in fields(obj):
                field_name = field.name
                field_value = getattr(obj, field_name)

                # Create the key name with prefix
                key = f"{prefix}_{field_name}" if prefix else field_name

                # Recursively flatten if it's another dataclass
                if is_dataclass(field_value):
                    nested_dict = self._flatten_dataclass(field_value, key)
                    flat_dict.update(nested_dict)
                else:
                    flat_dict[key] = field_value
        else:
            # If it's not a dataclass, just return it with the prefix as key
            flat_dict[prefix] = obj

        return flat_dict
