from typing import List
from cvt_simulator.models.dataTypes import CarForceBreakdown, CvtSystemForceBreakdown
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
    """

    time: float
    state: SystemState
    car_state: CarForceBreakdown
    cvt_state: CvtSystemForceBreakdown


# TODO: figure out how to structure the returned object over the API as one guy, that makes sense for the
# front end and is easy, with type gen
class FormattedSimulationResult:
    data: List[TimeStepData]

    def __init__(self, result: SimulationResult, args: SimulationArgs):
        """
        Initialize using the base SimulationResult and then compute additional columns.
        """
        self.data = []
        self.gather_model_states(result, args)

    def gather_model_states(self, result: SimulationResult, args: SimulationArgs):
        car_model, cvt_model = get_models(args)

        for i, (time, state) in enumerate(zip(result.time, result.states)):
            car_state = car_model.get_breakdown(state)
            cvt_state = cvt_model.get_breakdown(state)

            time_step_data = TimeStepData(
                time=time, state=state, car_state=car_state, cvt_state=cvt_state
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
        # Get all unique keys from all time steps by flattening everything
        all_keys = set()

        # Add time as a basic field
        all_keys.add("time")

        # Collect all unique keys from all time steps
        for time_step in self.data:
            flat_state = self._flatten_dataclass(time_step.state, "state")
            flat_car = self._flatten_dataclass(time_step.car_state, "car")
            flat_cvt = self._flatten_dataclass(time_step.cvt_state, "cvt")

            all_keys.update(flat_state.keys())
            all_keys.update(flat_car.keys())
            all_keys.update(flat_cvt.keys())

        # Initialize all columns
        data = {}
        for key in all_keys:
            data[key] = []

        # Populate all the flattened data
        for time_step in self.data:
            flat_state = self._flatten_dataclass(time_step.state, "state")
            flat_car = self._flatten_dataclass(time_step.car_state, "car")
            flat_cvt = self._flatten_dataclass(time_step.cvt_state, "cvt")

            # Merge all flattened data
            flat_combined = {
                **flat_state,
                **flat_car,
                **flat_cvt,
                "time": time_step.time,
            }

            # For each key, append the value or None if missing
            for key in all_keys:
                if key in flat_combined:
                    data[key].append(flat_combined[key])
                else:
                    data[key].append(None)

        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)

    def to_dict(self):
        """
        Converts the entire result into a list of dictionaries for each time step. No flattening
        """
        result_list = []
        for time_step in self.data:
            entry = {
                "time": time_step.time,
                "state": time_step.state,
                "car_state": time_step.car_state,
                "cvt_state": time_step.cvt_state,
            }
            result_list.append(entry)
        return result_list

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
