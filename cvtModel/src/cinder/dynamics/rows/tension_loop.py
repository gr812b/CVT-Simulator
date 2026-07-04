"""Regular normal-resultant form of the closed tension-loop compatibility row."""

from __future__ import annotations

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..equation_context import TrialEquationContext


def build_tension_loop_equation(
    *,
    context: TrialEquationContext,
) -> ClosureEquation:
    """Build the independent closed-loop tension compatibility residual.

    The one-speed reduced wrap model retains the radial and tangential
    shift-acceleration corrections

        C_j = q [v_b^2 - r_j r_j_ddot],
        A_j = q [r_j v_b_dot + r_j' s_dot v_b].

    For a fixed trial lambda pair, the integrated normal resultants reconstruct
    the four wrap endpoint tensions without divisions by ``lambda``. The two
    span relations have one independent combination after global belt momentum
    is imposed; in symmetric endpoint form it is

        T_u,p + T_l,p - T_u,s - T_l,s = 0.

    This row is affine in ``v_b_dot``, ``s_ddot``, ``N_p``, and ``N_s`` and
    remains finite at lambda = 0 through the regular functions cached in the
    trial context.
    """

    snapshot = context.snapshot
    geometry = snapshot.geometry
    state = snapshot.state
    contact = context.contact_terms
    q = snapshot.belt_linear_density

    primary_c = _radial_offset(
        linear_density=q,
        radius=geometry.primary.effective,
        d_radius_ds=geometry.primary.d_effective_ds,
        d2_radius_ds2=geometry.primary.d2_effective_ds2,
        belt_speed=state.belt_speed,
        shift_speed=state.shift_speed,
    )
    secondary_c = _radial_offset(
        linear_density=q,
        radius=geometry.secondary.effective,
        d_radius_ds=geometry.secondary.d_effective_ds,
        d2_radius_ds2=geometry.secondary.d2_effective_ds2,
        belt_speed=state.belt_speed,
        shift_speed=state.shift_speed,
    )

    primary_a = _tangential_offset(
        linear_density=q,
        radius=geometry.primary.effective,
        d_radius_ds=geometry.primary.d_effective_ds,
        belt_speed=state.belt_speed,
        shift_speed=state.shift_speed,
    )
    secondary_a = _tangential_offset(
        linear_density=q,
        radius=geometry.secondary.effective,
        d_radius_ds=geometry.secondary.d_effective_ds,
        belt_speed=state.belt_speed,
        shift_speed=state.shift_speed,
    )

    primary_wrap = geometry.primary_wrap_angle
    secondary_wrap = geometry.secondary_wrap_angle

    # Primary map, reconstructed from N_p:
    #
    # T_u,p = C_p + N_p/(phi_p Phi_-) - A_p phi_p Psi_-/Phi_-.
    primary_entry = (
        primary_c
        + AffineClosureScalar(
            gains=ClosureGains(
                primary_normal_resultant=(
                    1.0 / (primary_wrap * contact.primary_phi_minus)
                )
            )
        )
        - primary_a.scaled(
            primary_wrap * contact.primary_psi_minus / contact.primary_phi_minus
        )
    )

    # T_l,p = C_p + exp(-z_p)(T_u,p - C_p) + A_p phi_p Phi_-.
    primary_exit = (
        primary_c
        + (primary_entry - primary_c).scaled(contact.primary_exp_neg)
        + primary_a.scaled(primary_wrap * contact.primary_phi_minus)
    )

    # Secondary map, reconstructed from N_s:
    #
    # T_l,s = C_s + N_s/(phi_s Phi_+) - A_s phi_s Psi_+/Phi_+.
    secondary_entry = (
        secondary_c
        + AffineClosureScalar(
            gains=ClosureGains(
                secondary_normal_resultant=(
                    1.0 / (secondary_wrap * contact.secondary_phi_plus)
                )
            )
        )
        - secondary_a.scaled(
            secondary_wrap * contact.secondary_psi_plus / contact.secondary_phi_plus
        )
    )

    # T_u,s = C_s + exp(z_s)(T_l,s - C_s) + A_s phi_s Phi_+.
    secondary_exit = (
        secondary_c
        + (secondary_entry - secondary_c).scaled(contact.secondary_exp_pos)
        + secondary_a.scaled(secondary_wrap * contact.secondary_phi_plus)
    )

    return ClosureEquation(
        name="tension_loop",
        residual=(primary_entry + primary_exit - secondary_entry - secondary_exit),
    )


def _radial_offset(
    *,
    linear_density: float,
    radius: float,
    d_radius_ds: float,
    d2_radius_ds2: float,
    belt_speed: float,
    shift_speed: float,
) -> AffineClosureScalar:
    """Return ``C = q(v_b^2 - r r_ddot)`` as an affine scalar."""

    return AffineClosureScalar(
        bias=(
            linear_density * (belt_speed**2 - radius * d2_radius_ds2 * shift_speed**2)
        ),
        gains=ClosureGains(
            shift_acceleration=(-linear_density * radius * d_radius_ds),
        ),
    )


def _tangential_offset(
    *,
    linear_density: float,
    radius: float,
    d_radius_ds: float,
    belt_speed: float,
    shift_speed: float,
) -> AffineClosureScalar:
    """Return ``A = q(r v_b_dot + r' s_dot v_b)`` as an affine scalar."""

    return AffineClosureScalar(
        bias=(linear_density * d_radius_ds * shift_speed * belt_speed),
        gains=ClosureGains(
            belt_acceleration=(linear_density * radius),
        ),
    )
