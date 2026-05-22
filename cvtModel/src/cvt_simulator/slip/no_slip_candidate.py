"""No-slip candidate dynamics (slip folder).

Compute the no-slip candidate belt acceleration and corresponding
primary/secondary torques per the derivation:

    v̇_b,ns = (τ_eng/r_p - τ_load/r_s + I_p * ṙ_p * ω_p / r_p**2 + I_s * ṙ_s * ω_s / r_s**2)
              / ( m_b + I_p / r_p**2 + I_s / r_s**2 )

    τ_p,ns = τ_eng - I_p * ( v̇_b,ns - ṙ_p * ω_p ) / r_p
    τ_s,ns = τ_load + I_s * ( v̇_b,ns - ṙ_s * ω_s ) / r_s
"""
from cvt_simulator.sim_utils.system_state import SystemState
from cvt_simulator.core.data_types import NoSlipResult, NoSlipBreakdown
from cvt_simulator.geometry.theoretical_models import TheoreticalModels as tm


def compute_no_slip_candidate(
    state: SystemState,
    τ_eng: float,
    τ_load: float,
    I_p: float,
    I_s: float,
    m_b: float,
) -> NoSlipResult:
    """Compute no-slip candidate belt acceleration and pulley torques.

    Args:
        state: Current SystemState (must contain s, s_dot, ω_p, ω_s)
        τ_eng: Engine drive torque [N·m]
        τ_load: External load torque at secondary [N·m]
        I_p: Primary effective rotational inertia [kg·m²]
        I_s: Secondary effective rotational inertia [kg·m²]
        m_b: Belt mass (effective) [kg]

    Returns:
        NoSlipResult dataclass with v_b_dot_ns, τ_p_ns, τ_s_ns and breakdown
    """
    s = state.s
    s_dot = state.s_dot
    ω_p = state.ω_p
    ω_s = state.ω_s

    # Effective radii
    r_p = tm.primary_effective_radius(s)
    r_s = tm.secondary_effective_radius(s)

    # Time derivatives of radii: dr/dt = (dr/ds) * s_dot
    r_p_dot = tm.primary_radius_rate_of_change(s) * s_dot
    r_s_dot = tm.secondary_radius_rate_of_change(s) * s_dot

    # Numerator terms
    tau_engine_over_r_p = τ_eng / r_p
    tau_load_over_r_s = τ_load / r_s
    primary_inertia_term = (I_p * r_p_dot * ω_p) / (r_p**2)
    secondary_inertia_term = (I_s * r_s_dot * ω_s) / (r_s**2)

    numerator = tau_engine_over_r_p - tau_load_over_r_s + primary_inertia_term + secondary_inertia_term

    # Denominator
    denominator = m_b + (I_p / (r_p ** 2)) + (I_s / (r_s ** 2))

    v_b_dot_ns = numerator / denominator

    # Compute pulley torques under no-slip candidate
    tau_p_ns = τ_eng - I_p * (v_b_dot_ns - r_p_dot * ω_p) / r_p
    tau_s_ns = τ_load + I_s * (v_b_dot_ns - r_s_dot * ω_s) / r_s

    breakdown = NoSlipBreakdown(
        r_p=r_p,
        r_s=r_s,
        r_p_dot=r_p_dot,
        r_s_dot=r_s_dot,
        tau_engine_over_r_p=tau_engine_over_r_p,
        tau_load_over_r_s=tau_load_over_r_s,
        primary_inertia_term=primary_inertia_term,
        secondary_inertia_term=secondary_inertia_term,
        numerator=numerator,
        denominator=denominator,
    )

    return NoSlipResult(v_b_dot_ns=v_b_dot_ns, tau_p_ns=tau_p_ns, tau_s_ns=tau_s_ns, breakdown=breakdown)

