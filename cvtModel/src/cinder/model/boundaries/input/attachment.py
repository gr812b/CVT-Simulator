"""Input-shaft boundary values for CINDER simulations."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol


@dataclass(frozen=True, slots=True)
class InputBoundaryEvaluation:
    """Known upstream contribution to one input-shaft RHS evaluation.

    ``equivalent_rotational_inertia`` is referred directly to the primary
    shaft and is added to CINDER's CVT-owned primary hardware inertia.
    ``source_torque`` is the signed torque applied to the primary shaft by the
    input boundary. Positive torque drives positive primary rotation.
    """

    source_torque: float = 0.0
    equivalent_rotational_inertia: float = 0.0

    def __post_init__(self) -> None:
        if not isfinite(self.source_torque):
            raise ValueError("source_torque must be finite.")
        if (
            not isfinite(self.equivalent_rotational_inertia)
            or self.equivalent_rotational_inertia < 0.0
        ):
            raise ValueError(
                "equivalent_rotational_inertia must be finite and non-negative."
            )

    @property
    def torque(self) -> float:
        """Backward-compatible alias for callers that need the scalar torque."""

        return self.source_torque


class InputBoundary(Protocol):
    """A state-evaluated boundary condition attached to CINDER's primary."""

    def evaluate(self, angular_speed: float) -> InputBoundaryEvaluation:
        """Return the known input-shaft boundary for ``angular_speed``."""
