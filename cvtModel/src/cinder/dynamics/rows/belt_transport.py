"""Row 3: belt transport dynamics."""

from __future__ import annotations

from cinder.closure import AffineClosureScalar, ClosureEquation, ClosureGains

from ..snapshot import DynamicsSnapshot


def build_belt_transport_equation(
    *,
    snapshot: DynamicsSnapshot,
) -> ClosureEquation:
    """Build ``m_b v_b_dot - tau_p/r_p + tau_s/r_s = 0``."""

    primary_radius = snapshot.geometry.primary.effective
    secondary_radius = snapshot.geometry.secondary.effective

    return ClosureEquation(
        name="belt_transport",
        residual=AffineClosureScalar(
            gains=ClosureGains(
                belt_acceleration=snapshot.belt_transport_mass,
                primary_torque=-1.0 / primary_radius,
                secondary_torque=1.0 / secondary_radius,
            ),
        ),
    )
