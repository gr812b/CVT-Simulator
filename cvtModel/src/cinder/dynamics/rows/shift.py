"""Row 1: generalized global-shift dynamics."""

from __future__ import annotations

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..equation_context import TrialEquationContext


def build_shift_equation(
    *,
    context: TrialEquationContext,
) -> ClosureEquation:
    """Build the generalized shift equation for one trial lambda pair.

    The force-first form is:

        M_trans s_ddot + C_trans s_dot^2
          - x_p' F_p
          - x_s' F_s
          - [ tau_p/(2 lambda_p r_p tan(beta))
              - tau_s/(2 lambda_s r_s tan(beta)) ]
        = 0.

    ``F_p`` and ``F_s`` are the snapshot's existing affine actuator relations.
    This is deliberate: the secondary helix force already contains the true
    movable-sheave reaction/inertia contribution. Projecting that one relation
    through ``x_s'`` avoids manually adding the same reflected terms a second
    time.
    """

    snapshot = context.snapshot
    geometry = snapshot.geometry
    shift_inertia = snapshot.shift_translation_inertia
    contact = context.contact_terms

    primary_force_projection = snapshot.primary_actuation.relation.scaled(
        geometry.primary_axial_coordinate.d_value_ds
    )
    secondary_force_projection = snapshot.secondary_actuation.relation.scaled(
        geometry.secondary_axial_coordinate.d_value_ds
    )

    belt_contact_generalized_force = AffineClosureScalar(
        gains=ClosureGains(
            primary_torque=contact.primary_shift_torque_coefficient,
            secondary_torque=-contact.secondary_shift_torque_coefficient,
        )
    )

    inertial_relation = AffineClosureScalar(
        bias=(
            shift_inertia.coordinate_curvature_coefficient
            * snapshot.state.shift_speed**2
        ),
        gains=ClosureGains(
            shift_acceleration=shift_inertia.mass,
        ),
    )

    return ClosureEquation(
        name="shift",
        residual=(
            inertial_relation
            - primary_force_projection
            - secondary_force_projection
            - belt_contact_generalized_force
        ),
    )
