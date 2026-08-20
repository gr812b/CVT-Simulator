"""Secondary shaft angular-momentum balance."""

from __future__ import annotations

from cinder.model.cvt.closure import AffineClosureScalar, ClosureEquation, ClosureGains
from cinder.model.system.evaluator import DynamicsSnapshot


def build_secondary_rotation_equation(*, snapshot: DynamicsSnapshot) -> ClosureEquation:
    """Build ``T_ext,s + T_elem,s + tau_s = 0``.

    ``tau_s`` is the signed belt-on-secondary torque. In ordinary forward
    power transfer ``lambda_s < 0`` and therefore ``tau_s > 0``. ``T_elem,s`` includes shaft
    inertial reaction and any mounted secondary element torque.
    """

    return ClosureEquation(
        name="secondary_rotation",
        residual=AffineClosureScalar(
            bias=snapshot.secondary_external_torque,
            gains=ClosureGains(secondary_torque=1.0),
        )
        + snapshot.secondary_pulley.shaft_torque,
    )
