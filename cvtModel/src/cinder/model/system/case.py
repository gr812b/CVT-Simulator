"""Small run-spec objects for composed CVT simulations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .assembly import CVTAssemblySpec
from .state import CVTState


@dataclass(frozen=True, slots=True)
class OperatingScenario:
    """Initial conditions and solver-level inputs for one run."""

    time_span: tuple[float, float]
    initial_cvt_state: CVTState
    initial_mode: Any | None = None
    solver_settings: Any | None = None

    def __post_init__(self) -> None:
        if len(self.time_span) != 2:
            raise ValueError("time_span must contain exactly (start, end).")
        start, end = self.time_span
        if not start < end:
            raise ValueError("time_span must have end > start.")
        if not isinstance(self.initial_cvt_state, CVTState):
            raise TypeError("initial_cvt_state must be a CVTState.")

    def with_initial_cvt_state(
        self, initial_cvt_state: CVTState
    ) -> "OperatingScenario":
        return replace(self, initial_cvt_state=initial_cvt_state)

    def with_time_span(self, time_span: tuple[float, float]) -> "OperatingScenario":
        return replace(self, time_span=time_span)


@dataclass(frozen=True, slots=True)
class CVTAssemblyCase:
    """Mechanical assembly plus a nominal initial scenario.

    Shaft boundaries and host states are intentionally not part of this object.
    They are supplied by a host system when the plant is composed for a run.
    """

    cvt: CVTAssemblySpec
    scenario: OperatingScenario

    def __post_init__(self) -> None:
        if not isinstance(self.cvt, CVTAssemblySpec):
            raise TypeError("cvt must be a CVTAssemblySpec.")
        if not isinstance(self.scenario, OperatingScenario):
            raise TypeError("scenario must be an OperatingScenario.")
