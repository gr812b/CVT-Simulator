from typing import List, Dict
from cvt_simulator.constants.car_specs import MAX_SHIFT
from cvt_simulator.models.dataTypes import DrivetrainBreakdown
from cvt_simulator.utils.system_state import SystemState
import pandas as pd
from cvt_simulator.models.model_initializer import get_models
from cvt_simulator.utils.simulation_args import SimulationArgs
from cvt_simulator.utils.simulation_result import SimulationResult
from cvt_simulator.utils.state_computations import (
    integrate_positions_trapezoidal,
    primary_pulley_angular_velocity_to_engine_angular_velocity,
    secondary_pulley_angular_velocity_to_car_velocity,
)
from dataclasses import is_dataclass, fields, dataclass


@dataclass
class TimeStepData:
    """
    Represents all the data for a single time step in the simulation.
    Uses the unified DrivetrainBreakdown for clean access to all component data.
    """

    time: float
    state: SystemState
    derived_state: "DerivedKinematicState"
    drivetrain: DrivetrainBreakdown


@dataclass
class DerivedKinematicState:
    """Derived kinematic signals that are not part of the 4 DOF solver state."""

    car_velocity: float
    car_position: float
    engine_angular_velocity: float
    engine_angular_position: float


@dataclass
class SimulationTerminationContext:
    """Explains why simulation execution ended and includes final-state context."""

    reason_code: str
    reason: str
    mode: str
    final_time: float
    reached_max_time: bool
    event: str | None
    event_time: float | None
    transition_count: int
    max_transitions: int
    details: Dict[str, float | str | bool]


class FormattedSimulationResult:
    data: List[TimeStepData]
    termination: SimulationTerminationContext

    def __init__(self, result: SimulationResult, args: SimulationArgs):
        """
        Initialize using the base SimulationResult and then compute additional columns.
        """
        self.data = []
        self.gather_model_states(result, args)
        self.termination = self._build_termination_context(result)

    @staticmethod
    def _build_termination_context(result: SimulationResult) -> SimulationTerminationContext:
        context = result.termination_context or {}
        details_raw = context.get("details", {})
        details: Dict[str, float | str | bool] = {}
        if isinstance(details_raw, dict):
            details = {str(k): v for k, v in details_raw.items()}

        return SimulationTerminationContext(
            reason_code=str(context.get("reason_code", "unknown")),
            reason=str(context.get("reason", "Simulation completion reason unavailable.")),
            mode=str(context.get("mode", "unknown")),
            final_time=float(context.get("final_time", result.time[-1] if len(result.time) > 0 else 0.0)),
            reached_max_time=bool(context.get("reached_max_time", False)),
            event=str(context["event"]) if context.get("event") is not None else None,
            event_time=float(context["event_time"]) if context.get("event_time") is not None else None,
            transition_count=int(context.get("transition_count", 0)),
            max_transitions=int(context.get("max_transitions", 0)),
            details=details,
        )

    def gather_model_states(self, result: SimulationResult, args: SimulationArgs):
        system_model = get_models(args)

        car_velocities = [
            secondary_pulley_angular_velocity_to_car_velocity(
                state.secondary_pulley_angular_velocity
            )
            for state in result.states
        ]
        engine_angular_velocities = [
            primary_pulley_angular_velocity_to_engine_angular_velocity(
                state.primary_pulley_angular_velocity
            )
            for state in result.states
        ]
        primary_pulley_angular_velocities = [
            state.primary_pulley_angular_velocity for state in result.states
        ]
        secondary_pulley_angular_velocities = [
            state.secondary_pulley_angular_velocity for state in result.states
        ]
        car_positions = integrate_positions_trapezoidal(result.time, car_velocities)
        engine_positions = integrate_positions_trapezoidal(
            result.time, engine_angular_velocities
        )
        primary_pulley_angular_positions = integrate_positions_trapezoidal(
            result.time, primary_pulley_angular_velocities
        )
        secondary_pulley_angular_positions = integrate_positions_trapezoidal(
            result.time, secondary_pulley_angular_velocities
        )

        for i, (time, state) in enumerate(zip(result.time, result.states)):
            shift_velocity = state.shift_velocity
            shift_distance = state.shift_distance
            if shift_distance <= 0:
                state.shift_distance = 0
                state.shift_velocity = max(0, shift_velocity)

            elif shift_distance > MAX_SHIFT:
                state.shift_distance = MAX_SHIFT
                state.shift_velocity = min(0, shift_velocity)

            drivetrain_breakdown = system_model.get_breakdown(state)

            # The 4-DOF solver tracks angular velocities only; integrate them over time
            # so frontend consumers can animate pulley angular position directly.
            drivetrain_breakdown.cvt_dynamics.primaryPulleyState.angular_position = float(
                primary_pulley_angular_positions[i]
            )
            drivetrain_breakdown.cvt_dynamics.secondaryPulleyState.angular_position = float(
                secondary_pulley_angular_positions[i]
            )

            derived_state = DerivedKinematicState(
                car_velocity=car_velocities[i],
                car_position=float(car_positions[i]),
                engine_angular_velocity=engine_angular_velocities[i],
                engine_angular_position=float(engine_positions[i]),
            )

            time_step_data = TimeStepData(
                time=time,
                state=state,
                derived_state=derived_state,
                drivetrain=drivetrain_breakdown,
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
