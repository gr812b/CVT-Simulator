"""Row 5: global tangential wrap compatibility."""

from __future__ import annotations

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..snapshot import DynamicsSnapshot


def build_global_tangent_wrap_equation(
    *,
    snapshot: DynamicsSnapshot,
) -> ClosureEquation:
    """Build the sum of the two pulley tension-jump equations.

    The derivation form is:

        tau_p/r_p + tau_s/r_s
          = rho_b A_b [
                phi_p (r_p v_b_dot + r_p' s_dot v_b)
              + phi_s (r_s v_b_dot + r_s' s_dot v_b)
            ].

    It has no lambda dependence and is therefore fixed across all lambda
    trials at one ODE state.
    """

    geometry = snapshot.geometry
    state = snapshot.state
    primary = geometry.primary
    secondary = geometry.secondary
    belt_linear_density = snapshot.belt_linear_density

    known_radius_rate_term = (
        belt_linear_density
        * state.shift_speed
        * state.belt_speed
        * (
            geometry.primary_wrap_angle * primary.d_effective_ds
            + geometry.secondary_wrap_angle * secondary.d_effective_ds
        )
    )

    return ClosureEquation(
        name="global_tangent_wrap",
        residual=AffineClosureScalar(
            bias=known_radius_rate_term,
            gains=ClosureGains(
                belt_acceleration=(
                    belt_linear_density
                    * (
                        geometry.primary_wrap_angle * primary.effective
                        + geometry.secondary_wrap_angle * secondary.effective
                    )
                ),
                primary_torque=-1.0 / primary.effective,
                secondary_torque=-1.0 / secondary.effective,
            ),
        ),
    )
