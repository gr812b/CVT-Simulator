"""Primary shaft angular-momentum balance."""

from __future__ import annotations

from cinder.model.cvt.closure import AffineClosureScalar, ClosureEquation, ClosureGains
from cinder.model.system.evaluator import DynamicsSnapshot


def build_primary_rotation_equation(*, snapshot: DynamicsSnapshot) -> ClosureEquation:
    """Build ``T_ext,p + T_elem,p - tau_p = 0``.

    ``T_elem,p`` contains the shaft inertial reaction and any mounted pulley
    element torque, all signed in the positive primary rotation direction.
    """

    return ClosureEquation(
        name="primary_rotation",
        residual=AffineClosureScalar(
            bias=snapshot.primary_external_torque,
            gains=ClosureGains(primary_torque=-1.0),
        )
        + snapshot.primary_pulley.shaft_torque,
    )
