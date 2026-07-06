"""One executable CVT case: assembly plus external shaft boundaries."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from cinder.model.boundaries.input import InputTorqueBoundary
from cinder.model.boundaries.output import OutputBoundary
from .assembly import CVTAssemblySpec
from .state import CVTDynamicState


@dataclass(frozen=True, slots=True)
class OperatingScenario:
    """Run-specific initial conditions and integration inputs."""

    time_span: tuple[float, float]
    initial_state: CVTDynamicState
    initial_mode: Any | None = None
    solver_settings: Any | None = None

    def __post_init__(self) -> None:
        if len(self.time_span) != 2:
            raise ValueError("time_span must contain exactly (start, end).")
        start, end = self.time_span
        if not start < end:
            raise ValueError("time_span must have end > start.")
        if not isinstance(self.initial_state, CVTDynamicState):
            raise TypeError("initial_state must be a CVTDynamicState.")

    def with_initial_state(self, initial_state: CVTDynamicState) -> "OperatingScenario":
        return replace(self, initial_state=initial_state)

    def with_time_span(self, time_span: tuple[float, float]) -> "OperatingScenario":
        return replace(self, time_span=time_span)


@dataclass(frozen=True, slots=True)
class CVTSimulationCase:
    """CVT assembly connected to an input and output mechanical boundary.

    A case is the only editable construction object.  Runtime models and hybrid
    systems are built from it and intentionally do not act as mutable case
    containers.
    """

    cvt: CVTAssemblySpec
    input_boundary: InputTorqueBoundary
    output_boundary: OutputBoundary
    scenario: OperatingScenario

    def __post_init__(self) -> None:
        if not isinstance(self.cvt, CVTAssemblySpec):
            raise TypeError("cvt must be a CVTAssemblySpec.")
        if not callable(getattr(self.input_boundary, "evaluate", None)):
            raise TypeError("input_boundary must provide evaluate(angular_speed).")
        if not callable(getattr(self.output_boundary, "evaluate", None)):
            raise TypeError("output_boundary must provide evaluate(state=...).")
        if not isinstance(self.scenario, OperatingScenario):
            raise TypeError("scenario must be an OperatingScenario.")

    def with_input_boundary(
        self, input_boundary: InputTorqueBoundary
    ) -> "CVTSimulationCase":
        return replace(self, input_boundary=input_boundary)

    def with_output_boundary(
        self, output_boundary: OutputBoundary
    ) -> "CVTSimulationCase":
        return replace(self, output_boundary=output_boundary)

    def with_scenario(self, scenario: OperatingScenario) -> "CVTSimulationCase":
        return replace(self, scenario=scenario)
