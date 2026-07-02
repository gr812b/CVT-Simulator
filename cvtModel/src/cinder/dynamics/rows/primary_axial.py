"""Primary movable-sheave axial dynamics in the global shift coordinate."""

from __future__ import annotations

from math import isfinite, tan

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..equation_context import TrialEquationContext


def build_primary_axial_equation(
    *,
    context: TrialEquationContext,
) -> ClosureEquation:
    """Build the physical primary axial force balance.

    The primary local closing coordinate is the global shift coordinate,

        x_p = s.

    With positive local force defined as pulley-closing and the belt wedge
    reaction opening the movable sheave, the balance is

        m_p s_ddot - F_p + N_p / (2 tan(beta)) = 0.

    ``F_p`` is the complete primary-actuator affine relation supplied by the
    snapshot. ``N_p`` is the integrated primary-wrap normal resultant; it is
    retained explicitly rather than being replaced by ``tau_p / (lambda_p r)``.
    """

    snapshot = context.snapshot
    tangent = tan(snapshot.sheave_half_angle)
    if not isfinite(tangent) or tangent <= 0.0:
        raise ValueError("sheave_half_angle must produce a positive finite tangent.")

    inertia = snapshot.axial_translation_inertias.primary

    inertial_relation = AffineClosureScalar(
        bias=inertia.local_known_inertial_force(
            shift_speed=snapshot.state.shift_speed
        ),
        gains=ClosureGains(
            shift_acceleration=inertia.local_shift_acceleration_gain,
            primary_normal_resultant=1.0 / (2.0 * tangent),
        ),
    )

    return ClosureEquation(
        name="primary_axial",
        residual=inertial_relation - snapshot.primary_actuation.relation,
    )
