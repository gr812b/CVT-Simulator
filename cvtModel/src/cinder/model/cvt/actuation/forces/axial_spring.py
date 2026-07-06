"""Generic linear compression-spring force in a pulley-local coordinate."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from cinder.model.cvt.closure import AffineClosureScalar

from ..types import ActuationContribution, PulleyActuationContext


@dataclass(frozen=True, slots=True)
class AxialSpringForceSpec:
    """A compression spring defined through its local compression geometry.

    With local coordinate x, define spring compression as:

        delta(x) = initial_compression + compression_per_axial_position * x.

    The signed local axial force follows from stored energy:

        U = 1/2 k delta(x)^2,
        F_x = -dU/dx
            = -k delta(x) compression_per_axial_position.

    Positive returned force closes the pulley.  Therefore:

    * primary return spring: usually ``compression_per_axial_position = +1``;
      increasing primary closure compresses the spring, producing opening force;
    * secondary clamping spring: usually ``compression_per_axial_position = -1``;
      increasing local secondary closure relieves compression, producing closing
      force while the spring remains compressed.

    The coordinate adapter is responsible for supplying the correct local x to
    each pulley.  This law never needs to know whether it belongs to a primary
    or a secondary.
    """

    stiffness: float
    initial_compression: float
    compression_per_axial_position: float

    def __post_init__(self) -> None:
        if not isfinite(self.stiffness) or self.stiffness < 0.0:
            raise ValueError("stiffness must be finite and non-negative.")

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
    """Known signed local axial force of one compression spring."""

    def __init__(self, spec: AxialSpringForceSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> AxialSpringForceSpec:
        return self._spec

    def evaluate(self, state: PulleyActuationContext) -> AffineClosureScalar:
        compression = (
            self._spec.initial_compression
            + self._spec.compression_per_axial_position * state.axial_position
        )

        axial_force = (
            -self._spec.stiffness
            * compression
            * self._spec.compression_per_axial_position
        )

        return AffineClosureScalar(bias=axial_force)

    def inspect(
        self, context: PulleyActuationContext
    ) -> tuple[ActuationContribution, ...]:
        return (
            ActuationContribution(
                key="axial_spring",
                label="Axial spring",
                relation=self.evaluate(context),
            ),
        )
