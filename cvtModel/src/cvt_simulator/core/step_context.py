from __future__ import annotations

from dataclasses import dataclass

from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY, CVTGeometryResult
from cvt_simulator.sim.system_state import SystemState


@dataclass(slots=True)
class StepContext:
    """Per-step shared context for dynamics/slip computations.

    This bundles state with geometry values that are expensive to compute and
    widely reused across modules in the same integration step.
    """

    state: SystemState
    geometry: CVTGeometryResult

    @classmethod
    def from_state(cls, state: SystemState) -> "StepContext":
        return cls(
            state=state,
            geometry=CVT_GEOMETRY.geometry_from_shift_distance(state.s, state.s_dot),
        )


def ensure_step_context(state: SystemState, ctx: StepContext | None = None) -> StepContext:
    """Return a valid StepContext for the given state.

    If ``ctx`` is provided it is reused; otherwise it is built from state.
    """

    if ctx is not None:
        return ctx
    return StepContext.from_state(state)
