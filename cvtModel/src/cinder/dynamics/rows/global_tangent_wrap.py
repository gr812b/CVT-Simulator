"""Row 5: global tangential wrap compatibility."""

from __future__ import annotations

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..snapshot import DynamicsSnapshot


def build_global_tangent_wrap_equation(
    *,
    snapshot: DynamicsSnapshot,
) -> ClosureEquation:
    """Build global compatibility of the two local tension jumps.

    Define positive torque variables by their forward-drive roles:

    ``tau_p``
        primary pulley -> belt;

    ``tau_s``
        belt -> secondary pulley.

    The secondary local wrap coordinate is opposite the global belt-travel
    direction, so the two local jump relations combine to

        tau_p / r_p - tau_s / r_s
          = rho_b A_b [
                phi_p (r_p v_b_dot + r_p' s_dot v_b)
              + phi_s (r_s v_b_dot + r_s' s_dot v_b)
            ].

    In the held-ratio, zero-acceleration limit this reduces to

        tau_p / r_p = tau_s / r_s,

    which permits finite forward torque transfer. The row has no lambda
    dependence and is therefore fixed across all lambda trials at one ODE
    state.
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

    # Residual form:
    #
    #   rhoA [phi_p a_p + phi_s a_s] - tau_p/r_p + tau_s/r_s = 0.
    #
    # The positive secondary coefficient is intentional: tau_s is defined as
    # belt -> secondary, not secondary -> belt.
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
                secondary_torque=1.0 / secondary.effective,
            ),
        ),
    )
