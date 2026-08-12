"""Host state carrying accumulated secondary shaft angle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from cinder.core import StateBlock
from cinder.execution.hybrid.hybrid import HybridEvent, HybridTransition
from cinder.model.system import CVTShaftBoundaryValues, CVTState


@dataclass(frozen=True, slots=True)
class SecondaryShaftAngleHost:
    """One-state host storing accumulated secondary shaft angle."""

    block_name: str = "host"

    @property
    def state_block(self) -> StateBlock:
        return StateBlock(self.block_name, 1)

    def initial_state(
        self, *, secondary_shaft_angle: float = 0.0
    ) -> NDArray[np.float64]:
        return np.asarray([secondary_shaft_angle], dtype=float)

    def context(
        self, *, time: float, cvt_state: CVTState, host_state: NDArray[np.float64]
    ) -> Mapping[str, Any]:
        del time, cvt_state
        return {"secondary_shaft_angle": float(host_state[0])}

    def rhs(
        self,
        *,
        time: float,
        cvt_state: CVTState,
        host_state: NDArray[np.float64],
        shaft_boundaries: CVTShaftBoundaryValues,
    ) -> NDArray[np.float64]:
        del time, host_state, shaft_boundaries
        return np.asarray([cvt_state.secondary_angular_speed], dtype=float)

    def events(
        self,
        *,
        time: float,
        cvt_state: CVTState,
        host_state: NDArray[np.float64],
        shaft_boundaries: CVTShaftBoundaryValues,
    ) -> Sequence[HybridEvent]:
        del time, cvt_state, host_state, shaft_boundaries
        return ()

    def transition(
        self,
        *,
        time: float,
        cvt_state: CVTState,
        host_state: NDArray[np.float64],
        shaft_boundaries: CVTShaftBoundaryValues,
        fired_event_names: tuple[str, ...],
    ) -> HybridTransition[Any] | None:
        del time, cvt_state, host_state, shaft_boundaries, fired_event_names
        return None
