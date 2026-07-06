"""Raw segment-preserving CVT integration traces."""

from __future__ import annotations

from dataclasses import dataclass

from numpy.typing import NDArray

from cinder.execution.hybrid.cvt_regime import CVTOperatingRegime
from cinder.execution.hybrid.hybrid import HybridIntegrationResult


@dataclass(frozen=True, slots=True)
class CVTIntegrationTrace:
    """The solver product, before signal materialization or report sampling.

    A trace deliberately contains only accepted hybrid segments, transitions,
    termination status, and raw six-state histories.  It is invariant to which
    report channels a caller later requests.
    """

    raw: HybridIntegrationResult[CVTOperatingRegime]

    def __post_init__(self) -> None:
        if not isinstance(self.raw, HybridIntegrationResult):
            raise TypeError("raw must be a HybridIntegrationResult instance.")

    @property
    def segments(self):
        return self.raw.segments

    @property
    def transitions(self):
        return self.raw.transitions

    @property
    def completed(self) -> bool:
        return self.raw.completed

    @property
    def termination_reason(self) -> str:
        return self.raw.termination_reason

    @property
    def final_time(self) -> float:
        return self.raw.final_time

    @property
    def final_state(self) -> NDArray:
        return self.raw.final_state

    def concatenated_time(self) -> NDArray:
        return self.raw.concatenated_time()

    def concatenated_state(self) -> NDArray:
        return self.raw.concatenated_state()
