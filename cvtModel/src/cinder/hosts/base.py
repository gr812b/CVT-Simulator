"""Host-side contracts for simulations that contain a CVT plant."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

import numpy as np
from numpy.typing import NDArray

from cinder.core import StateBlock
from cinder.execution.hybrid.hybrid import HybridEvent, HybridTransition
from cinder.model.system import CVTShaftBoundaryValues, CVTState


class CVTHost(Protocol):
    """Additional states and dynamics wrapped around a five-state CVT plant."""

    @property
    def state_block(self) -> StateBlock:
        """Return the host's single contiguous state block."""

    def context(
        self,
        *,
        time: float,
        cvt_state: CVTState,
        host_state: NDArray[np.float64],
    ) -> Mapping[str, Any]:
        """Return values exposed to shaft boundaries."""

    def rhs(
        self,
        *,
        time: float,
        cvt_state: CVTState,
        host_state: NDArray[np.float64],
        shaft_boundaries: CVTShaftBoundaryValues,
    ) -> NDArray[np.float64]:
        """Return the derivative for the host state block."""

    def events(
        self,
        *,
        time: float,
        cvt_state: CVTState,
        host_state: NDArray[np.float64],
        shaft_boundaries: CVTShaftBoundaryValues,
    ) -> Sequence[HybridEvent]:
        """Return optional host events."""

    def transition(
        self,
        *,
        time: float,
        cvt_state: CVTState,
        host_state: NDArray[np.float64],
        shaft_boundaries: CVTShaftBoundaryValues,
        fired_event_names: tuple[str, ...],
    ) -> HybridTransition[Any] | None:
        """Return an optional host transition."""


@dataclass(frozen=True, slots=True)
class NoHost:
    """Zero-dynamics host with one inert dummy state.

    The generic state-layout machinery requires contiguous blocks of positive
    size. This host is useful for shaft-only bench cases where no additional
    state is needed.
    """

    @property
    def state_block(self) -> StateBlock:
        return StateBlock("host", 1)

    def initial_state(self) -> NDArray[np.float64]:
        return np.zeros(1, dtype=float)

    def context(self, *, time: float, cvt_state: CVTState, host_state: NDArray[np.float64]) -> Mapping[str, Any]:
        del time, cvt_state, host_state
        return {}

    def rhs(self, *, time: float, cvt_state: CVTState, host_state: NDArray[np.float64], shaft_boundaries: CVTShaftBoundaryValues) -> NDArray[np.float64]:
        del time, cvt_state, host_state, shaft_boundaries
        return np.zeros(1, dtype=float)

    def events(self, *, time: float, cvt_state: CVTState, host_state: NDArray[np.float64], shaft_boundaries: CVTShaftBoundaryValues) -> Sequence[HybridEvent]:
        del time, cvt_state, host_state, shaft_boundaries
        return ()

    def transition(self, *, time: float, cvt_state: CVTState, host_state: NDArray[np.float64], shaft_boundaries: CVTShaftBoundaryValues, fired_event_names: tuple[str, ...]) -> HybridTransition[Any] | None:
        del time, cvt_state, host_state, shaft_boundaries, fired_event_names
        return None
