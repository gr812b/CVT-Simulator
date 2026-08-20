"""Primary local axial balance."""

from __future__ import annotations

from math import cos, isfinite

from cinder.model.cvt.closure import AffineClosureScalar, ClosureEquation, ClosureGains
from cinder.model.system.evaluator import DynamicsSnapshot


def build_primary_axial_equation(*, snapshot: DynamicsSnapshot) -> ClosureEquation:
    """Build ``F_elem,p - N_p cos(beta)/2 = 0``.

    ``N_p`` is the physical integrated normal load over both sheave faces.
    Symmetric face-load sharing places one half on the movable face, whose
    axial projection is ``N_p cos(beta)/2``. Mounted element force is positive
    in the local primary-closing direction and already includes actuator
    forces plus D'Alembert inertial reactions.
    """

    cosine = cos(snapshot.sheave_half_angle)
    if not isfinite(cosine) or cosine <= 0.0:
        raise ValueError("sheave_half_angle must produce a positive finite cosine.")
    belt_opening = AffineClosureScalar(
        gains=ClosureGains(primary_normal_resultant=0.5 * cosine)
    )
    return ClosureEquation(
        name="primary_axial",
        residual=snapshot.primary_pulley.closing_force - belt_opening,
    )
