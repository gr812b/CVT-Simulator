from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Dict, List

import pandas as pd

from cvt_simulator.constants.car_specs import MAX_SHIFT
from cvt_simulator.core.data_types import ContactDynamicsBreakdown, SlipBranch
from cvt_simulator.sim.system_state import SystemState
from cvt_simulator.sim.simulation_runner import SimulationRunner
from cvt_simulator.sim_utils.simulation_args import SimulationArgs
from cvt_simulator.sim_utils.simulation_result import SimulationResult
from cvt_simulator.utils.state_computations import (
    integrate_positions_trapezoidal,
    primary_pulley_angular_velocity_to_engine_angular_velocity,
    secondary_pulley_angular_velocity_to_car_velocity,
)


@dataclass
class AnalysisStepData:
    """All analysis data for one simulation time step."""

    time: float
    mode: str
    shift_mode: str
    slip_mode: str
    state: SystemState
    derived_state: "DerivedKinematicState"
    contact_breakdown: ContactDynamicsBreakdown


TimeStepData = AnalysisStepData


@dataclass
class DerivedKinematicState:
    """Kinematic signals derived from the solver state."""

    car_velocity: float
    car_position: float
    belt_position: float
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
    details: Dict[str, float | str | bool | int]


class SimulationAnalysisResult:
    """Analysis-oriented projection of a simulation run."""

    # Explicit response contract for backend auto model generation.
    data: List[AnalysisStepData]
    termination: SimulationTerminationContext

    def __init__(self, result: SimulationResult, args: SimulationArgs):
        contact_model = SimulationRunner.from_simulation_args(args).contact_model
        self.rows: List[AnalysisStepData] = []
        self.data = self.rows
        self.gather_model_states(result, contact_model)
        self.termination = self._build_termination_context(result)

    @staticmethod
    def _build_termination_context(
        result: SimulationResult,
    ) -> SimulationTerminationContext:
        context = result.termination_context or {}
        details_raw = context.get("details", {})
        details: Dict[str, float | str | bool | int] = {}
        if isinstance(details_raw, dict):
            details = {str(k): v for k, v in details_raw.items()}

        return SimulationTerminationContext(
            reason_code=str(context.get("reason_code", "unknown")),
            reason=str(
                context.get("reason", "Simulation completion reason unavailable.")
            ),
            mode=str(context.get("mode", "unknown")),
            final_time=float(
                context.get(
                    "final_time", result.time[-1] if len(result.time) > 0 else 0.0
                )
            ),
            reached_max_time=bool(context.get("reached_max_time", False)),
            event=str(context["event"]) if context.get("event") is not None else None,
            event_time=(
                float(context["event_time"])
                if context.get("event_time") is not None
                else None
            ),
            transition_count=int(context.get("transition_count", 0)),
            max_transitions=int(context.get("max_transitions", 0)),
            details=details,
        )

    def gather_model_states(self, result: SimulationResult, contact_model):
        car_velocities = [
            secondary_pulley_angular_velocity_to_car_velocity(state.ω_s)
            for state in result.states
        ]
        engine_angular_velocities = [
            primary_pulley_angular_velocity_to_engine_angular_velocity(state.ω_p)
            for state in result.states
        ]

        car_positions = integrate_positions_trapezoidal(result.time, car_velocities)
        belt_positions = integrate_positions_trapezoidal(
            result.time, [state.v_b for state in result.states]
        )
        engine_positions = integrate_positions_trapezoidal(
            result.time, engine_angular_velocities
        )

        for index, (time, state) in enumerate(zip(result.time, result.states)):
            display_state = SystemState(
                s=float(state.s),
                s_dot=float(state.s_dot),
                ω_p=float(state.ω_p),
                ω_s=float(state.ω_s),
                v_b=float(state.v_b),
            )

            if display_state.s <= 0.0:
                display_state.s = 0.0
                display_state.s_dot = max(0.0, display_state.s_dot)
            elif display_state.s > MAX_SHIFT:
                display_state.s = float(MAX_SHIFT)
                display_state.s_dot = min(0.0, display_state.s_dot)

            derived_state = DerivedKinematicState(
                car_velocity=car_velocities[index],
                car_position=float(car_positions[index]),
                belt_position=float(belt_positions[index]),
                engine_angular_velocity=engine_angular_velocities[index],
                engine_angular_position=float(engine_positions[index]),
            )

            mode = "unknown"
            shift_mode = "unknown"
            slip_mode = "unknown"
            if getattr(result, "modes", None) is not None and index < len(result.modes):
                mode = str(result.modes[index])
                if ":" in mode:
                    shift_mode, slip_mode = mode.split(":", 1)
                else:
                    shift_mode = mode

            contact_branch = self._slip_branch_from_mode(slip_mode)
            contact_breakdown = contact_model.get_breakdown(display_state, contact_branch)

            # Sanitize enum values to primitives to avoid retaining Enum internals.
            try:
                if hasattr(contact_breakdown, "contact") and getattr(contact_breakdown, "contact") is not None:
                    contact = contact_breakdown.contact
                    if hasattr(contact, "branch") and contact.branch is not None:
                        contact.branch = contact.branch.name
                    if hasattr(contact, "branch_result") and getattr(contact, "branch_result") is not None:
                        br = contact.branch_result
                        if hasattr(br, "branch") and br.branch is not None:
                            br.branch = br.branch.name
            except Exception:
                # Best-effort sanitization; failure is non-fatal.
                pass

            self.rows.append(
                AnalysisStepData(
                    time=float(time),
                    mode=mode,
                    shift_mode=shift_mode,
                    slip_mode=slip_mode,
                    state=display_state,
                    derived_state=derived_state,
                    contact_breakdown=contact_breakdown,
                )
            )

    @staticmethod
    def _slip_branch_from_mode(slip_mode: str) -> SlipBranch:
        try:
            return SlipBranch[slip_mode]
        except KeyError:
            return SlipBranch.NO_SLIP

    @staticmethod
    def from_csv(filename: str = "simulation_output.csv", args: SimulationArgs | None = None):
        """Read states from CSV and reconstruct the analysis view."""
        base_result = SimulationResult.from_csv(filename)
        if args is None:
            raise ValueError("SimulationArgs is required to compute model breakdowns")
        return SimulationAnalysisResult(base_result, args)

    def write_analysis_csv(self, filename: str = "front_end_output.csv"):
        """Flatten the analysis rows to CSV for downstream tooling."""
        all_keys = set()
        for row in self.rows:
            flat_row = self._flatten_dataclass(row)
            all_keys.update(flat_row.keys())

        data = {key: [] for key in all_keys}
        for row in self.rows:
            flat_row = self._flatten_dataclass(row)
            for key in all_keys:
                data[key].append(flat_row.get(key))

        pd.DataFrame(data).to_csv(filename, index=False)

    def write_formatted_csv(self, filename: str = "front_end_output.csv"):
        """Backward-compatible alias for the old formatter name."""
        self.write_analysis_csv(filename)

    def _flatten_dataclass(self, obj, prefix: str = ""):
        """Recursively flatten a dataclass object into a flat dictionary."""
        flat_dict = {}

        if is_dataclass(obj):
            for field in fields(obj):
                field_value = getattr(obj, field.name)
                key = f"{prefix}_{field.name}" if prefix else field.name
                if is_dataclass(field_value):
                    flat_dict.update(self._flatten_dataclass(field_value, key))
                else:
                    flat_dict[key] = field_value
        else:
            flat_dict[prefix] = obj

        return flat_dict


FormattedSimulationResult = SimulationAnalysisResult
