"""Secondary movable-sheave axial dynamics mapped through ``x_s(s)``."""

from __future__ import annotations

from math import isfinite, tan

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..equation_context import TrialEquationContext


def build_secondary_axial_equation(
    *,
    context: TrialEquationContext,
) -> ClosureEquation:
    """Build the physical secondary axial force balance in the global coordinate.

    The physical local secondary closing coordinate is supplied by geometry:

        x_s = x_s(s),
        x_s_ddot = x_s'(s) s_ddot + x_s''(s) s_dot^2.

    Positive local force closes the secondary. The belt wedge reaction opens
    the movable sheave, so the local balance is

        m_s x_s_ddot - F_s + N_s / (2 tan(beta)) = 0.

    ``F_s`` is the snapshot's full affine secondary-actuation relation. It
    already carries the helix coupling to secondary angular acceleration,
    secondary torque, and global shift acceleration; this row must therefore
    use it directly rather than project it once more through ``x_s'``.
    """

    snapshot = context.snapshot
    tangent = tan(snapshot.sheave_half_angle)
    if not isfinite(tangent) or tangent <= 0.0:
        raise ValueError("sheave_half_angle must produce a positive finite tangent.")

    inertia = snapshot.axial_translation_inertias.secondary

    inertial_relation = AffineClosureScalar(
        bias=inertia.local_known_inertial_force(
            shift_speed=snapshot.state.shift_speed
        ),
        gains=ClosureGains(
            shift_acceleration=inertia.local_shift_acceleration_gain,
            secondary_normal_resultant=1.0 / (2.0 * tangent),
        ),
    )

    return ClosureEquation(
        name="secondary_axial",
        residual=inertial_relation - snapshot.secondary_actuation.relation,
    )
