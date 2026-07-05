"""One executable CVT system case: assembly plus external shaft boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cinder.model.boundaries.input import InputTorqueBoundary
from cinder.model.boundaries.output import OutputBoundary
from .assembly import CVTAssemblySpec
from .state import CVTDynamicState


@dataclass(frozen=True, slots=True)
class OperatingScenario:
    """Run-specific initial conditions and execution inputs.

    Road/load mapping is intentionally owned by the selected output boundary,
    because it changes the secondary-shaft torque/inertia mapping.  Scenario
    inputs therefore cover initial conditions, timing, commands, and optional
    execution settings rather than CVT or vehicle hardware.
    """

    time_span: tuple[float, float]
    initial_state: CVTDynamicState
    initial_mode: Any | None = None
    solver_settings: Any | None = None


@dataclass(frozen=True, slots=True)
class CVTSimulationCase:
    """CVT assembly connected to a source and an output-side mechanical boundary."""

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
