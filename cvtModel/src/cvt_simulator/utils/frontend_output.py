from typing import List
from cvt_simulator.models.dataTypes import CarForceBreakdown, CvtSystemForceBreakdown
from cvt_simulator.utils.system_state import SystemState
import pandas as pd
from cvt_simulator.models.model_initializer import get_models
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.utils.simulation_result import SimulationResult
from dataclasses import is_dataclass, fields


# TODO: figure out how to structure the returned object over the API as one guy, that makes sense for the
# front end and is easy, with type gen
class FormattedSimulationResult:
    times: List[float]
    states: List[SystemState]
    car_states: List[CarForceBreakdown]
    cvt_states: List[CvtSystemForceBreakdown]

    def __init__(self, result: SimulationResult, args: SimulationArgs):
        """
        Initialize using the base SimulationResult and then compute additional columns.
        """
        self.times = result.time
        self.states = result.states
        self.car_states = []
        self.cvt_states = []
        self.gather_model_states(args)

    def gather_model_states(self, args):
        car_model, cvt_model = get_models(args)

        for i, t in enumerate(self.times):
            # dt = t - self.time[i - 1] if i > 0 else 0
            state = self.states[i]

            car_state = car_model.get_breakdown(state)
            cvt_state = cvt_model.get_breakdown(state)

            self.car_states.append(car_state)
            self.cvt_states.append(cvt_state)

    @staticmethod
    def from_csv(filename="simulation_output.csv"):
        """
        Reads the simulation states from a CSV file and returns an FormattedSimulationResult instance.
        """
        base_result = SimulationResult.from_csv(filename)
        return FormattedSimulationResult(base_result)

    def write_formatted_csv(self, filename="front_end_output.csv"):
        """
        Flattens the data and writes to a CSV file for front-end consumption.
        """
        # Get all unique keys from all states by flattening everything
        all_keys = set()

        # Add basic simulation data by flattening each state
        for state in self.states:
            flat_state = self._flatten_dataclass(state, "state")
            all_keys.update(flat_state.keys())

        # Add time as a basic field
        all_keys.add("time")

        # Collect all unique keys from car and CVT states
        for car_state in self.car_states:
            flat_car = self._flatten_dataclass(car_state, "car")
            all_keys.update(flat_car.keys())

        for cvt_state in self.cvt_states:
            flat_cvt = self._flatten_dataclass(cvt_state, "cvt")
            all_keys.update(flat_cvt.keys())

        # Initialize all columns
        data = {}
        for key in all_keys:
            data[key] = []

        # Populate all the flattened data
        for i, (time_val, state, car_state, cvt_state) in enumerate(
            zip(self.times, self.states, self.car_states, self.cvt_states)
        ):
            flat_state = self._flatten_dataclass(state, "state")
            flat_car = self._flatten_dataclass(car_state, "car")
            flat_cvt = self._flatten_dataclass(cvt_state, "cvt")

            # Merge all flattened data
            flat_combined = {**flat_state, **flat_car, **flat_cvt, "time": time_val}

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
        for i, (time, state, car_state, cvt_state) in enumerate(
            zip(self.times, self.states, self.car_states, self.cvt_states)
        ):
            entry = {
                "time": time,
                "state": state,
                "car_state": car_state,
                "cvt_state": cvt_state,
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
