from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..types import PulleyActuationResult, PulleyActuationState


@dataclass(frozen=True, slots=True)
class AxialSpringForceSpec:
    """
    Linear axial spring expressed through its signed compression geometry.

    Define spring compression as:

        delta(x) = initial_compression
                   + compression_per_axial_position * x.

    The local spring force follows directly from stored energy:

        U = 1/2 * k * delta(x)^2
        F_x = -dU/dx
            = -k * delta(x) * compression_per_axial_position.

    Local x is positive toward pulley closure.

    Typical configurations:
      - Primary return spring:
            compression_per_axial_position = +1
        More primary closure compresses the spring, so it returns an opening
        force (negative).

      - Secondary clamping spring:
            compression_per_axial_position = -1
        More secondary closure relieves compression, so the spring returns a
        closing force (positive), provided it remains compressed.

    ``compression_per_axial_position`` is dimensionless. It is normally +1 or
    -1, but is left general to support spring-linkage ratios.
    """

    stiffness: float
    initial_compression: float
    compression_per_axial_position: float

    def __post_init__(self) -> None:
        if not isfinite(self.stiffness) or self.stiffness <= 0.0:
            raise ValueError("stiffness must be finite and positive.")

        if not isfinite(self.initial_compression):
            raise ValueError("initial_compression must be finite.")

        if (
            not isfinite(self.compression_per_axial_position)
            or self.compression_per_axial_position == 0.0
        ):
            raise ValueError(
                "compression_per_axial_position must be finite and nonzero."
            )


class AxialSpringForce:
    """A linear axial spring returning a signed local axial force."""

    def __init__(self, spec: AxialSpringForceSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> AxialSpringForceSpec:
        return self._spec

    def force_relation(
        self,
        state: PulleyActuationState,
    ) -> PulleyActuationResult:
        compression = (
            self._spec.initial_compression
            + self._spec.compression_per_axial_position
            * state.axial_position
        )

        axial_force = (
            -self._spec.stiffness
            * compression
            * self._spec.compression_per_axial_position
        )

        return PulleyActuationResult(
            bias_force=axial_force,
            torque_gain=0.0,
        )
