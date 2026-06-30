"""Row 2: primary rotational dynamics."""

from __future__ import annotations

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..snapshot import DynamicsSnapshot


def build_primary_rotation_equation(
    *,
    snapshot: DynamicsSnapshot,
) -> ClosureEquation:
    """Build ``I_p alpha_p + tau_p - tau_eng = 0``.

    This is fully fixed for one state snapshot because engine torque is
    evaluated from the current primary speed before lambda trials begin.
    """

    return ClosureEquation(
        name="primary_rotation",
        residual=AffineClosureScalar(
            bias=-snapshot.engine_torque,
            gains=ClosureGains(
                primary_angular_acceleration=(
                    snapshot.primary_rotational_inertia
                ),
                primary_torque=1.0,
            ),
        ),
    )
