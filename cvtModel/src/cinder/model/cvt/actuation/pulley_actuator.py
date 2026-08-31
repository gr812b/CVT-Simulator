"""Composition of local axial-force laws into one pulley-mounted actuator."""

from __future__ import annotations

from cinder.model.cvt.closure import AffineClosureScalar, ClosureUnknowns

from .types import (
    ActuationContribution,
    ActuatorInspection,
    AxialForceLaw,
    InspectableAxialForceLaw,
    KineticPulleyElement,
    PulleyActuationContext,
    PulleyElementContribution,
    PulleyKineticMode,
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
        return self.evaluate_element(context).closing_force

    def evaluate_element(
        self, context: PulleyActuationContext
    ) -> PulleyElementContribution:
        contribution = PulleyElementContribution.zero()
        for force_law in self._force_laws:
            if hasattr(force_law, "evaluate_element"):
                contribution = contribution + force_law.evaluate_element(context)
            else:
                contribution = (
                    contribution
                    + PulleyElementContribution.from_closing_force(
                        force_law.evaluate(context)
                    )
                )
        return contribution

    def kinetic_modes(
        self, context: PulleyActuationContext
    ) -> tuple[PulleyKineticMode, ...]:
        """Collect kinetic modes from every mounted element that provides them."""

        modes: list[PulleyKineticMode] = []
        for force_law in self._force_laws:
            if isinstance(force_law, KineticPulleyElement):
                modes.extend(force_law.kinetic_modes(context))
        return tuple(modes)

    def compressive_contact_margins(
        self,
        context: PulleyActuationContext,
        unknowns: ClosureUnknowns,
    ) -> tuple[tuple[str, float], ...]:
        """Return unilateral-contact margins exposed by mounted elements."""

        margins: list[tuple[str, float]] = []
        for index, force_law in enumerate(self._force_laws):
            margin = getattr(force_law, "compressive_contact_margin", None)
            if margin is None:
                continue
            value = float(margin(context=context, unknowns=unknowns))
            margins.append((f"{index}:{type(force_law).__name__}", value))
        return tuple(margins)

    def has_compressive_contacts(
        self,
        context: PulleyActuationContext,
        unknowns: ClosureUnknowns,
        *,
        tolerance: float = 0.0,
    ) -> bool:
        if tolerance < 0.0:
            raise ValueError("tolerance must be non-negative.")
        return all(
            margin >= -tolerance
            for _key, margin in self.compressive_contact_margins(context, unknowns)
        )

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
