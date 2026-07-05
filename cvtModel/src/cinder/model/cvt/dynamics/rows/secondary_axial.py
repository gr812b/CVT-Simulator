"""Secondary movable-sheave axial dynamics mapped through ``x_s(s)``."""

from __future__ import annotations

from math import isfinite, tan

from cinder.model.cvt.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from cinder.model.system.evaluator import DynamicsSnapshot


def build_secondary_axial_equation(
    *,
    snapshot: DynamicsSnapshot,
) -> ClosureEquation:
    """Build the lambda-independent physical secondary axial balance.

    The local coordinate supplied by geometry satisfies

        x_s_ddot = x_s'(s) s_ddot + x_s''(s) s_dot^2.

    With positive local force closing the secondary, the balance is

        m_s x_s_ddot - F_s + N_s / (2 tan(beta)) = 0.

    ``F_s`` already contains its helix coupling to secondary acceleration,
    secondary torque, and global shift acceleration. The row contains no trial
    lambda, so it is built once per frozen state together with the other four
    lambda-independent mechanics rows.
    """

    tangent = tan(snapshot.sheave_half_angle)
    if not isfinite(tangent) or tangent <= 0.0:
        raise ValueError("sheave_half_angle must produce a positive finite tangent.")

    inertia = snapshot.axial_translation_inertias.secondary
    inertial_relation = AffineClosureScalar(
        bias=inertia.local_known_inertial_force(shift_speed=snapshot.state.shift_speed),
        gains=ClosureGains(
            shift_acceleration=inertia.local_shift_acceleration_gain,
            secondary_normal_resultant=1.0 / (2.0 * tangent),
        ),
    )

    return ClosureEquation(
        name="secondary_axial",
        residual=inertial_relation - snapshot.secondary_actuation.relation,
    )
