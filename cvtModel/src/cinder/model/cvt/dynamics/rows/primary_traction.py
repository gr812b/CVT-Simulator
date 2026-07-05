"""Primary integrated traction-resultant closure row."""

from __future__ import annotations

from cinder.model.cvt.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..equation_context import TrialEquationContext


def build_primary_traction_equation(
    *,
    context: TrialEquationContext,
) -> ClosureEquation:
    """Build ``tau_p / r_tau,p - lambda_p N_p = 0``.

    This is the effective-wrap integral of ``dQ_p = lambda_p dN_p`` followed
    by ``tau_p = r_tau,p integral(dQ_p)``. Keeping the product form preserves
    the regular clamped zero-traction state ``tau_p = lambda_p = 0`` with a
    finite preload normal resultant ``N_p``.
    """

    torque_radius = context.snapshot.geometry.primary.effective
    return ClosureEquation(
        name="primary_traction",
        residual=AffineClosureScalar(
            gains=ClosureGains(
                primary_torque=1.0 / torque_radius,
                primary_normal_resultant=-context.contact_terms.primary_lambda,
            )
        ),
    )
