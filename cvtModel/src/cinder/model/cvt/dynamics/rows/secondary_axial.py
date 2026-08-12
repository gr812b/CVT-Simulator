"""Secondary local axial balance."""

from __future__ import annotations

from math import isfinite, tan

from cinder.model.cvt.closure import AffineClosureScalar, ClosureEquation, ClosureGains
from cinder.model.system.evaluator import DynamicsSnapshot


def build_secondary_axial_equation(*, snapshot: DynamicsSnapshot) -> ClosureEquation:
    """Build ``F_elem,s - N_s/(2 tan(beta)) = 0``."""

    tangent = tan(snapshot.sheave_half_angle)
    if not isfinite(tangent) or tangent <= 0.0:
        raise ValueError("sheave_half_angle must produce a positive finite tangent.")
    wedge = AffineClosureScalar(
        gains=ClosureGains(secondary_normal_resultant=1.0 / (2.0 * tangent))
    )
    return ClosureEquation(
        name="secondary_axial",
        residual=snapshot.secondary_pulley.closing_force - wedge,
    )
