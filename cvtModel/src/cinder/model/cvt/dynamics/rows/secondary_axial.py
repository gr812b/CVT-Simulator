"""Secondary local axial balance."""

from __future__ import annotations

from math import cos, isfinite

from cinder.model.cvt.closure import AffineClosureScalar, ClosureEquation, ClosureGains
from cinder.model.system.evaluator import DynamicsSnapshot


def build_secondary_axial_equation(*, snapshot: DynamicsSnapshot) -> ClosureEquation:
    """Build ``F_elem,s - N_s cos(beta)/2 = 0``.

    ``N_s`` is the physical integrated normal load over both sheave faces.
    The mounted-element contribution is positive in the local closing
    direction and may include spring, helix, flyweight, and inertial terms.
    """

    cosine = cos(snapshot.sheave_half_angle)
    if not isfinite(cosine) or cosine <= 0.0:
        raise ValueError("sheave_half_angle must produce a positive finite cosine.")
    belt_opening = AffineClosureScalar(
        gains=ClosureGains(secondary_normal_resultant=0.5 * cosine)
    )
    return ClosureEquation(
        name="secondary_axial",
        residual=snapshot.secondary_pulley.closing_force - belt_opening,
    )
