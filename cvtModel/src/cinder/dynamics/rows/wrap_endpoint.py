"""Row 6: closed-loop wrap-endpoint compatibility."""

from __future__ import annotations

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..equation_context import TrialEquationContext


def build_wrap_endpoint_equation(
    *,
    context: TrialEquationContext,
) -> ClosureEquation:
    """Build the closed-loop wrap-endpoint compatibility residual.

    For fixed trial ``lambda_p, lambda_s`` this row is affine in the closure
    unknowns. Define

        a_p = r_p v_b_dot + r_p' s_dot v_b,
        a_s = r_s v_b_dot + r_s' s_dot v_b,
        r_j_ddot = r_j' s_ddot + r_j'' s_dot^2.

    With both local wrap coordinates directed from the common slack endpoint
    to the common tight endpoint, but with the secondary local coordinate
    opposite global belt travel,

        Tbar_p = rhoA v_b^2 - rhoA r_p r_p_ddot + rhoA a_p / lambda_p,
        Tbar_s = rhoA v_b^2 - rhoA r_s r_s_ddot - rhoA a_s / lambda_s.

    The common span-tension difference is taken from the primary wrap:

        D = tau_p/r_p - rhoA phi_p a_p.

    Equality of the two expressions for the common slack-span tension gives

        Tbar_p - Tbar_s
          - D [1/(1 - exp(lambda_p phi_p))
               - 1/(1 - exp(lambda_s phi_s))]
        = 0.

    ``TrialContactTerms.endpoint_span_coefficient`` evaluates the bracket with
    ``expm1``. Exact-zero lambda remains explicitly excluded by the trial
    context because the present analytical row contains ``1/lambda`` terms.
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
            # The sign differs from the primary because the secondary local
            # wrap coordinate is reversed relative to global belt travel.
            belt_acceleration=(
                -belt_linear_density
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

    primary_tension_jump = AffineClosureScalar(
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
            - primary_tension_jump.scaled(endpoint_span)
        ),
    )
