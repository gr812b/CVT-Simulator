"""Composition of local axial-force laws into one pulley-mounted actuator."""

from __future__ import annotations

from cinder.model.cvt.closure import AffineClosureScalar

from .types import AxialForceLaw, PulleyActuationContext


class PulleyActuator:
    """Sum local force laws without knowing which shaft hosts them.

    This is intentionally the only runtime actuator operation.  It produces an
    affine closure relation and allocates no reporting objects, labels, or
    per-law dictionaries inside the ODE hot path.
    """

    def __init__(self, *force_laws: AxialForceLaw) -> None:
        if not force_laws:
            raise ValueError("PulleyActuator requires at least one force law.")
        self._force_laws = tuple(force_laws)

    @property
    def force_laws(self) -> tuple[AxialForceLaw, ...]:
        return self._force_laws

    def evaluate_relation(self, context: PulleyActuationContext) -> AffineClosureScalar:
        relation = AffineClosureScalar.zero()
        for force_law in self._force_laws:
            relation = relation + force_law.evaluate(context)
        return relation
