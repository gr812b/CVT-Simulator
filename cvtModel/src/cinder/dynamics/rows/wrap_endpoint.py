"""Row 6: closed-loop wrap-endpoint compatibility."""

from __future__ import annotations

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..equation_context import TrialEquationContext


def build_wrap_endpoint_equation(
    *,
    context: TrialEquationContext,
) -> ClosureEquation:
    """Build the closed-loop wrap-endpoint compatibility residual.

    For fixed trial ``lambda_p, lambda_s`` this is affine in the closure
    unknowns. In derivation notation, define:

        a_i = r_i v_b_dot + r_i' s_dot v_b.

    The imposed relation is:

        [rhoA v_b^2 - rhoA r_p(r_p' s_ddot + r_p'' s_dot^2)
         + rhoA a_p/lambda_p]
        -
        [rhoA v_b^2 - rhoA r_s(r_s' s_ddot + r_s'' s_dot^2)
         + rhoA a_s/lambda_s]
        -
        [tau_p/r_p - rhoA phi_p a_p]
        [1/(1-exp(lambda_p phi_p))
         + exp(lambda_s phi_s)/(1-exp(lambda_s phi_s))]
        = 0.

    ``TrialContactTerms.endpoint_span_coefficient`` evaluates the final bracket
    with ``expm1`` so it remains well-conditioned away from the explicitly
    excluded exact-zero lambda limit.
    """

    snapshot = context.snapshot
    geometry = snapshot.geometry
    state = snapshot.state
    contact = context.contact_terms

    primary = geometry.primary
    secondary = geometry.secondary
    belt_linear_density = snapshot.belt_linear_density
    endpoint_span = contact.endpoint_span_coefficient

    primary_block = AffineClosureScalar(
        bias=(
            belt_linear_density * state.belt_speed**2
            - belt_linear_density
            * primary.effective
            * primary.d2_effective_ds2
            * state.shift_speed**2
        ),
        gains=ClosureGains(
            belt_acceleration=(
                belt_linear_density
                * primary.effective
                * contact.primary_inverse_lambda
            ),
            shift_acceleration=(
                -belt_linear_density
                * primary.effective
                * primary.d_effective_ds
            ),
        ),
    )

    secondary_block = AffineClosureScalar(
        bias=(
            belt_linear_density * state.belt_speed**2
            - belt_linear_density
            * secondary.effective
            * secondary.d2_effective_ds2
            * state.shift_speed**2
        ),
        gains=ClosureGains(
            belt_acceleration=(
                belt_linear_density
                * secondary.effective
                * contact.secondary_inverse_lambda
            ),
            shift_acceleration=(
                -belt_linear_density
                * secondary.effective
                * secondary.d_effective_ds
            ),
        ),
    )

    primary_tension_endpoint = AffineClosureScalar(
        bias=(
            -belt_linear_density
            * geometry.primary_wrap_angle
            * primary.d_effective_ds
            * state.shift_speed
            * state.belt_speed
        ),
        gains=ClosureGains(
            belt_acceleration=(
                -belt_linear_density
                * geometry.primary_wrap_angle
                * primary.effective
            ),
            primary_torque=1.0 / primary.effective,
        ),
    )

    return ClosureEquation(
        name="wrap_endpoint",
        residual=(
            primary_block
            - secondary_block
            - primary_tension_endpoint.scaled(endpoint_span)
        ),
    )
