"""Final-equation term decomposition for CINDER's reduced-belt study.

The study intentionally starts from the two *final equations actually solved*:

    m_b v_b_dot + tau_p / r_eff,p + tau_s / r_eff,s = 0

and the independent closed tension-loop compatibility after exact common-mode
terms have already been eliminated.  No precursor terms that cancel
identically in the derivation are reported as scientific study channels.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sin
from typing import Any

_EPS = 1.0e-15


@dataclass(frozen=True, slots=True)
class FinalBeltInputs:
    belt_mass: float
    linear_density: float
    belt_speed: float
    belt_acceleration: float
    shift_speed: float
    shift_acceleration: float

    primary_effective_radius: float
    secondary_effective_radius: float
    primary_radius_cm: float
    secondary_radius_cm: float
    primary_d_radius_ds: float
    secondary_d_radius_ds: float
    primary_d2_radius_ds2: float
    secondary_d2_radius_ds2: float
    primary_wrap_angle: float
    secondary_wrap_angle: float

    primary_torque: float
    secondary_torque: float
    primary_normal: float
    secondary_normal: float
    primary_lambda: float
    secondary_lambda: float

    sin_beta: float
    primary_phi_minus: float
    secondary_phi_minus: float
    primary_psi_minus: float
    secondary_psi_minus: float
    primary_exp_neg: float
    secondary_exp_neg: float


def _f(name: str, value: float) -> float:
    value = float(value)
    if not isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}.")
    return value


def _shares(values: dict[str, float]) -> tuple[float, dict[str, float]]:
    scale = sum(abs(value) for value in values.values())
    if scale <= _EPS:
        return 0.0, {key: 0.0 for key in values}
    return scale, {key: abs(value) / scale for key, value in values.items()}


def contact_coefficients(*, wrap_angle: float, sin_beta: float, phi_minus: float,
                         psi_minus: float, exp_neg: float) -> tuple[float, float]:
    """Return (H, G) in the collapsed endpoint-sum relation.

    For one wrap,

        T_in + T_out = 2 C + H A + G N,

    where C=q(v_b^2-r r_ddot) and A=q(r v_b_dot+r' s_dot v_b).
    """
    phi = _f("wrap_angle", wrap_angle)
    sb = _f("sin_beta", sin_beta)
    Phi = _f("phi_minus", phi_minus)
    Psi = _f("psi_minus", psi_minus)
    E = _f("exp_neg", exp_neg)
    if phi <= 0.0 or sb <= 0.0 or abs(Phi) <= _EPS:
        raise ValueError("wrap angle and sin(beta) must be positive and Phi_- nonzero.")
    H = phi * (Phi - (1.0 + E) * Psi / Phi)
    G = (1.0 + E) * sb / (phi * Phi)
    return H, G


def decompose_final_equations(inputs: FinalBeltInputs) -> dict[str, float]:
    """Return the surviving additive terms of CINDER's two final belt equations."""
    mb = _f("belt_mass", inputs.belt_mass)
    q = _f("linear_density", inputs.linear_density)
    vb = _f("belt_speed", inputs.belt_speed)
    vbdot = _f("belt_acceleration", inputs.belt_acceleration)
    sdot = _f("shift_speed", inputs.shift_speed)
    sddot = _f("shift_acceleration", inputs.shift_acceleration)
    rep = _f("primary_effective_radius", inputs.primary_effective_radius)
    res = _f("secondary_effective_radius", inputs.secondary_effective_radius)
    rp = _f("primary_radius_cm", inputs.primary_radius_cm)
    rs = _f("secondary_radius_cm", inputs.secondary_radius_cm)
    rpp = _f("primary_d_radius_ds", inputs.primary_d_radius_ds)
    rsp = _f("secondary_d_radius_ds", inputs.secondary_d_radius_ds)
    rpp2 = _f("primary_d2_radius_ds2", inputs.primary_d2_radius_ds2)
    rsp2 = _f("secondary_d2_radius_ds2", inputs.secondary_d2_radius_ds2)
    taup = _f("primary_torque", inputs.primary_torque)
    taus = _f("secondary_torque", inputs.secondary_torque)
    Np = _f("primary_normal", inputs.primary_normal)
    Ns = _f("secondary_normal", inputs.secondary_normal)

    if mb <= 0.0 or q <= 0.0 or rep <= 0.0 or res <= 0.0 or rp <= 0.0 or rs <= 0.0:
        raise ValueError("belt mass, line density, and radii must be positive.")

    Hp, Gp = contact_coefficients(
        wrap_angle=inputs.primary_wrap_angle,
        sin_beta=inputs.sin_beta,
        phi_minus=inputs.primary_phi_minus,
        psi_minus=inputs.primary_psi_minus,
        exp_neg=inputs.primary_exp_neg,
    )
    Hs, Gs = contact_coefficients(
        wrap_angle=inputs.secondary_wrap_angle,
        sin_beta=inputs.sin_beta,
        phi_minus=inputs.secondary_phi_minus,
        psi_minus=inputs.secondary_psi_minus,
        exp_neg=inputs.secondary_exp_neg,
    )

    transport = {
        "belt_inertia_N": mb * vbdot,
        "primary_reaction_N": taup / rep,
        "secondary_reaction_N": taus / res,
    }
    transport_scale, transport_shares = _shares(transport)
    transport_residual = sum(transport.values())

    loop = {
        "radial_shift_acceleration_N": -2.0 * q * (rp * rpp - rs * rsp) * sddot,
        "radial_geometry_curvature_N": -2.0 * q * (rp * rpp2 - rs * rsp2) * sdot**2,
        "tangential_belt_acceleration_N": q * (Hp * rp - Hs * rs) * vbdot,
        "tangential_shifting_radius_N": q * (Hp * rpp - Hs * rsp) * sdot * vb,
        "normal_contact_N": Gp * Np - Gs * Ns,
    }
    loop_scale, loop_shares = _shares(loop)
    loop_residual = sum(loop.values())

    radial = loop["radial_shift_acceleration_N"] + loop["radial_geometry_curvature_N"]
    tangential = loop["tangential_belt_acceleration_N"] + loop["tangential_shifting_radius_N"]

    row: dict[str, float] = {
        "state.belt_speed_m_per_s": vb,
        "state.belt_acceleration_m_per_s2": vbdot,
        "state.shift_speed_m_per_s": sdot,
        "state.shift_acceleration_m_per_s2": sddot,
        "geometry.primary_effective_radius_m": rep,
        "geometry.secondary_effective_radius_m": res,
        "geometry.primary_radius_cm_m": rp,
        "geometry.secondary_radius_cm_m": rs,
        "geometry.primary_d_radius_ds": rpp,
        "geometry.secondary_d_radius_ds": rsp,
        "geometry.primary_d2_radius_ds2_per_m": rpp2,
        "geometry.secondary_d2_radius_ds2_per_m": rsp2,
        "contact.primary_lambda": _f("primary_lambda", inputs.primary_lambda),
        "contact.secondary_lambda": _f("secondary_lambda", inputs.secondary_lambda),
        "contact.primary_normal_N": Np,
        "contact.secondary_normal_N": Ns,
        "coefficient.primary_H": Hp,
        "coefficient.secondary_H": Hs,
        "coefficient.primary_G": Gp,
        "coefficient.secondary_G": Gs,
        "transport.belt_inertia_N": transport["belt_inertia_N"],
        "transport.primary_reaction_N": transport["primary_reaction_N"],
        "transport.secondary_reaction_N": transport["secondary_reaction_N"],
        "transport.activity_scale_N": transport_scale,
        "transport.residual_N": transport_residual,
        "loop.radial_shift_acceleration_N": loop["radial_shift_acceleration_N"],
        "loop.radial_geometry_curvature_N": loop["radial_geometry_curvature_N"],
        "loop.tangential_belt_acceleration_N": loop["tangential_belt_acceleration_N"],
        "loop.tangential_shifting_radius_N": loop["tangential_shifting_radius_N"],
        "loop.normal_contact_N": loop["normal_contact_N"],
        "loop.radial_total_N": radial,
        "loop.tangential_total_N": tangential,
        "loop.activity_scale_N": loop_scale,
        "loop.residual_N": loop_residual,
    }
    for key, value in transport_shares.items():
        row[f"transport.share.{key.removesuffix('_N')}"] = value
    for key, value in loop_shares.items():
        row[f"loop.share.{key.removesuffix('_N')}"] = value
    return row


def inspect_final_belt_terms(inspection: Any) -> dict[str, float | str] | None:
    """Reconstruct final-equation terms from one accepted engaged CINDER state."""
    if inspection.contact is None or inspection.closure_unknowns is None:
        return None

    from cinder.model.cvt.dynamics.equation_context import TrialEquationContext

    contact = inspection.contact
    unknowns = inspection.closure_unknowns
    snapshot = contact.snapshot
    geometry = snapshot.geometry
    state = snapshot.state
    regular = TrialEquationContext(
        snapshot=snapshot,
        traction_utilization=contact.traction_utilization,
    ).contact_terms

    values = decompose_final_equations(
        FinalBeltInputs(
            belt_mass=snapshot.belt_transport_mass,
            linear_density=snapshot.belt_linear_density,
            belt_speed=state.belt_speed,
            belt_acceleration=unknowns.belt_acceleration,
            shift_speed=state.shift_speed,
            shift_acceleration=unknowns.shift_acceleration,
            primary_effective_radius=geometry.primary.effective,
            secondary_effective_radius=geometry.secondary.effective,
            primary_radius_cm=geometry.primary.center_of_mass,
            secondary_radius_cm=geometry.secondary.center_of_mass,
            primary_d_radius_ds=geometry.primary.d_center_of_mass_ds,
            secondary_d_radius_ds=geometry.secondary.d_center_of_mass_ds,
            primary_d2_radius_ds2=geometry.primary.d2_center_of_mass_ds2,
            secondary_d2_radius_ds2=geometry.secondary.d2_center_of_mass_ds2,
            primary_wrap_angle=geometry.primary_wrap_angle,
            secondary_wrap_angle=geometry.secondary_wrap_angle,
            primary_torque=unknowns.primary_torque,
            secondary_torque=unknowns.secondary_torque,
            primary_normal=unknowns.primary_normal_resultant,
            secondary_normal=unknowns.secondary_normal_resultant,
            primary_lambda=contact.traction_utilization.primary_lambda,
            secondary_lambda=contact.traction_utilization.secondary_lambda,
            sin_beta=sin(snapshot.sheave_half_angle),
            primary_phi_minus=regular.primary_phi_minus,
            secondary_phi_minus=regular.secondary_phi_minus,
            primary_psi_minus=regular.primary_psi_minus,
            secondary_psi_minus=regular.secondary_psi_minus,
            primary_exp_neg=regular.primary_exp_neg,
            secondary_exp_neg=regular.secondary_exp_neg,
        )
    )
    values.update(
        {
            "time_s": float(inspection.time),
            "mode": str(inspection.mode),
            "state.shift_position_m": float(state.shift_position),
            "state.primary_angular_speed_rad_per_s": float(state.primary_angular_speed),
            "state.secondary_angular_speed_rad_per_s": float(state.secondary_angular_speed),
        }
    )
    return values


def inventory() -> tuple[dict[str, str], ...]:
    return (
        {"equation": "whole_belt_transport", "channel": "transport.belt_inertia_N", "term": "m_b v_b_dot", "role": "surviving belt transport inertia"},
        {"equation": "whole_belt_transport", "channel": "transport.primary_reaction_N", "term": "tau_p / r_eff,p", "role": "primary contact reaction"},
        {"equation": "whole_belt_transport", "channel": "transport.secondary_reaction_N", "term": "tau_s / r_eff,s", "role": "secondary contact reaction"},
        {"equation": "tension_loop", "channel": "loop.radial_shift_acceleration_N", "term": "-2 q (r_p r'_p-r_s r'_s) s_ddot", "role": "radial shift-acceleration transient"},
        {"equation": "tension_loop", "channel": "loop.radial_geometry_curvature_N", "term": "-2 q (r_p r''_p-r_s r''_s) s_dot^2", "role": "radial geometry-curvature transient"},
        {"equation": "tension_loop", "channel": "loop.tangential_belt_acceleration_N", "term": "q (H_p r_p-H_s r_s) v_b_dot", "role": "tangential belt-acceleration transient"},
        {"equation": "tension_loop", "channel": "loop.tangential_shifting_radius_N", "term": "q (H_p r'_p-H_s r'_s) s_dot v_b", "role": "tangential shifting-radius transient"},
        {"equation": "tension_loop", "channel": "loop.normal_contact_N", "term": "G_p N_p-G_s N_s", "role": "contact/load reference contribution"},
    )
