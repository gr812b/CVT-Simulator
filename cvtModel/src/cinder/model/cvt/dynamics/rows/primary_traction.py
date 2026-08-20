"""Primary integrated traction-resultant closure row."""

from __future__ import annotations

from cinder.model.cvt.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..equation_context import TrialEquationContext


def build_primary_traction_equation(
    *,
    context: TrialEquationContext,
) -> ClosureEquation:
    """Build ``tau_p / r_eff,p + lambda_p N_p = 0``.

    ``lambda_p`` is the physical signed traction utilization defined by
    ``dF_t,p = lambda_p dN_p``, where ``dF_t,p`` is the force exerted by the
    pulley on the belt in the positive belt-travel direction. The equal and
    opposite belt-on-pulley torque used by the shaft balance is therefore

        tau_p = -r_eff,p lambda_p N_p.
    """

    torque_radius = context.snapshot.geometry.primary.effective
    return ClosureEquation(
        name="primary_traction",
        residual=AffineClosureScalar(
            gains=ClosureGains(
                primary_torque=1.0 / torque_radius,
                primary_normal_resultant=context.contact_terms.primary_lambda,
            )
        ),
    )
