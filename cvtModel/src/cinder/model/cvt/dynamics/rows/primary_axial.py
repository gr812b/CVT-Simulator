"""Primary local axial balance."""

from __future__ import annotations

from math import isfinite, tan

from cinder.model.cvt.closure import AffineClosureScalar, ClosureEquation, ClosureGains
from cinder.model.system.evaluator import DynamicsSnapshot


def build_primary_axial_equation(*, snapshot: DynamicsSnapshot) -> ClosureEquation:
    """Build ``F_elem,p - N_p/(2 tan(beta)) = 0``.

    Mounted element force is positive in the local primary-closing direction.
    It already includes actuator forces and D'Alembert inertial reactions.
    """

    tangent = tan(snapshot.sheave_half_angle)
    if not isfinite(tangent) or tangent <= 0.0:
        raise ValueError("sheave_half_angle must produce a positive finite tangent.")
    wedge = AffineClosureScalar(
        gains=ClosureGains(primary_normal_resultant=1.0 / (2.0 * tangent))
    )
    return ClosureEquation(
        name="primary_axial",
        residual=snapshot.primary_pulley.closing_force - wedge,
    )
