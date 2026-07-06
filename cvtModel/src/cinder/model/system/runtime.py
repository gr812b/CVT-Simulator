"""Lean state-advance values returned by the CVT runtime evaluator."""

from __future__ import annotations

from dataclasses import dataclass

from cinder.model.system.state import CVTDynamicStateDerivative


@dataclass(frozen=True, slots=True)
class RuntimeEvaluation:
    """The small public result required to advance the ODE state.

    Detailed snapshots, closure matrices, labelled force contributions, and
    plot-ready signals deliberately do not belong here.  They are reconstructed
    through CINDER's results inspect/report layer after integration.
    """

    state_derivative: CVTDynamicStateDerivative

    def derivative_vector(self):
        """Return the aligned six-entry derivative vector."""

        return self.state_derivative.as_vector()
