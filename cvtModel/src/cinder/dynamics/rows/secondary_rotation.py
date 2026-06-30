"""Row 4: total-secondary rotational dynamics."""

from __future__ import annotations

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..snapshot import DynamicsSnapshot


def build_secondary_rotation_equation(
    *,
    snapshot: DynamicsSnapshot,
) -> ClosureEquation:
    """Build the total-secondary angular-momentum equation.

    In derivation notation with ``tau_load`` as a positive opposing magnitude,

        tau_s - tau_load
          = (I_s,F + I_M) alpha_s - I_M H' s_dot^2 - I_M H s_ddot.

    ``RoadLoadResult.secondary_external_torque`` instead uses a signed external
    torque convention, so the code form is:

        tau_s + tau_external
          = (I_s,F + I_M) alpha_s - I_M H' s_dot^2 - I_M H s_ddot.

    The returned zero-equals residual is therefore:

        (I_s,F + I_M) alpha_s
        - I_M H s_ddot
        - tau_s
        - tau_external
        - I_M H' s_dot^2 = 0.
    """

    movable_inertia = snapshot.movable_secondary_rotational_inertia
    helix = snapshot.secondary_helix
    shift_speed = snapshot.state.shift_speed

    return ClosureEquation(
        name="secondary_rotation",
        residual=AffineClosureScalar(
            bias=(
                -snapshot.secondary_external_torque
                - movable_inertia * helix.d2theta_ds2 * shift_speed**2
            ),
            gains=ClosureGains(
                secondary_angular_acceleration=(
                    snapshot.secondary_absolute_rotational_inertia
                ),
                shift_acceleration=(
                    -movable_inertia * helix.dtheta_ds
                ),
                secondary_torque=-1.0,
            ),
        ),
    )
