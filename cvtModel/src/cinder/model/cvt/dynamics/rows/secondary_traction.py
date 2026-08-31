"""Secondary integrated traction-resultant closure row."""

from __future__ import annotations

from cinder.model.cvt.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..equation_context import TrialEquationContext


def build_secondary_traction_equation(
    *,
    context: TrialEquationContext,
) -> ClosureEquation:
    """Build ``tau_s / r_eff,s + lambda_s N_s = 0``.

    One signed definition is used on both pulleys:
    ``dF_t,j = lambda_j dN_j`` is pulley-on-belt traction along positive belt
    travel, and ``tau_j`` is the equal-and-opposite belt-on-pulley shaft torque.
    """

    torque_radius = context.snapshot.geometry.secondary.effective
    return ClosureEquation(
        name="secondary_traction",
        residual=AffineClosureScalar(
            gains=ClosureGains(
                secondary_torque=1.0 / torque_radius,
                secondary_normal_resultant=context.contact_terms.secondary_lambda,
            )
        ),
    )
