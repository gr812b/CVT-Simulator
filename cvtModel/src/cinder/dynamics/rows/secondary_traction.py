"""Secondary integrated traction-resultant closure row."""

from __future__ import annotations

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..equation_context import TrialEquationContext


def build_secondary_traction_equation(
    *,
    context: TrialEquationContext,
) -> ClosureEquation:
    """Build ``tau_s / r_tau,s - lambda_s N_s = 0``.

    The forward-drive sign convention is already contained in the definitions
    of ``tau_s`` and ``lambda_s``, so the integrated traction product has the
    same algebraic sign form as the primary relation.
    """

    torque_radius = context.snapshot.geometry.secondary.effective
    return ClosureEquation(
        name="secondary_traction",
        residual=AffineClosureScalar(
            gains=ClosureGains(
                secondary_torque=1.0 / torque_radius,
                secondary_normal_resultant=-context.contact_terms.secondary_lambda,
            )
        ),
    )
