"""Composition of local axial-force laws into one mounted pulley actuator."""

from __future__ import annotations

from cinder.model.cvt.closure import AffineClosureScalar

from .types import AxialForceLaw, PulleyActuationResult, PulleyActuationState


class PulleyActuator:
    """Sum local force laws without knowing which pulley owns them.

    ``evaluate_relation`` is the RHS-facing method.  It returns only the
    affine closure relation required by the mechanics.  Rich named reporting is
    intentionally not built here; it will be added later by a result observer
    that re-evaluates the same laws at sampled trajectory points.
    """

    def __init__(self, *force_laws: AxialForceLaw) -> None:
        if not force_laws:
            raise ValueError("PulleyActuator requires at least one force law.")
        self._force_laws = tuple(force_laws)

    @property
    def force_laws(self) -> tuple[AxialForceLaw, ...]:
        return self._force_laws

    def evaluate_relation(self, state: PulleyActuationState) -> AffineClosureScalar:
        relation = AffineClosureScalar.zero()
        for force_law in self._force_laws:
            relation = relation + force_law.evaluate(state)
        return relation

    def evaluate(self, state: PulleyActuationState) -> PulleyActuationResult:
        """Compatibility wrapper returning the current compact result object."""
        return PulleyActuationResult(relation=self.evaluate_relation(state))
