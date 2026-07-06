"""Composition of local axial-force laws into one pulley-mounted actuator."""

from __future__ import annotations

from cinder.model.cvt.closure import AffineClosureScalar

from .types import (
    ActuationContribution,
    ActuatorInspection,
    AxialForceLaw,
    InspectableAxialForceLaw,
    PulleyActuationContext,
)


class PulleyActuator:
    """Sum local force laws without knowing which shaft hosts them.

    :meth:`evaluate_relation` is the only RHS-facing operation.  Rich named
    force breakdowns live in :meth:`inspect`, which reporting calls after the
    integrator has produced a trace.
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

    def inspect(self, context: PulleyActuationContext) -> ActuatorInspection:
        """Return named terms without changing the RHS calculation path."""

        contributions: list[ActuationContribution] = []
        for index, force_law in enumerate(self._force_laws):
            if isinstance(force_law, InspectableAxialForceLaw):
                contributions.extend(force_law.inspect(context))
                continue
            relation = force_law.evaluate(context)
            contributions.append(
                ActuationContribution(
                    key=f"force_law_{index}",
                    label=type(force_law).__name__,
                    relation=relation,
                )
            )
        total = AffineClosureScalar.zero()
        for contribution in contributions:
            total = total + contribution.relation
        return ActuatorInspection(
            total_relation=total, contributions=tuple(contributions)
        )
