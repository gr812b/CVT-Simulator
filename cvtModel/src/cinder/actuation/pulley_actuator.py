"""Composition of independent force laws into one pulley actuator."""

from __future__ import annotations

from cinder.closure import AffineClosureScalar

from .types import AxialForceLaw, PulleyActuationResult, PulleyActuationState


class PulleyActuator:
    """Sum local force laws without knowing which pulley owns them."""

    def __init__(self, *force_laws: AxialForceLaw) -> None:
        if not force_laws:
            raise ValueError("PulleyActuator requires at least one force law.")

        self._force_laws = tuple(force_laws)

    @property
    def force_laws(self) -> tuple[AxialForceLaw, ...]:
        return self._force_laws

    def evaluate(self, state: PulleyActuationState) -> PulleyActuationResult:
        relation = AffineClosureScalar.zero()

        for force_law in self._force_laws:
            relation = relation + force_law.evaluate(state)

        return PulleyActuationResult(relation=relation)
