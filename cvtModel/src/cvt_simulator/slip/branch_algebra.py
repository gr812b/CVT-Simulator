"""Branch-specific algebra moved out of BranchResolver.

Each function computes the branch kinematics and returns
tau_p, tau_s, v_b_dot for the branch.
"""
import math

from cvt_simulator.components.primary_pulley import PrimaryPulley
from cvt_simulator.components.secondary_pulley import SecondaryPulley
from cvt_simulator.constants.car_specs import BELT_CROSS_SECTIONAL_AREA, SHEAVE_ANGLE
from cvt_simulator.constants.constants import RUBBER_ALUMINUM_KINETIC_FRICTION, RUBBER_DENSITY
from cvt_simulator.core.data_types import SlipMetricsResult
from cvt_simulator.sim_utils.system_state import SystemState
from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY


def primary_slip_algebra(
    decision: SlipMetricsResult,
    state: SystemState,
    tau_load: float,
    I_s: float,
    m_b: float,
    primary_pulley: PrimaryPulley,
) -> tuple[float, float]:
    s = state.s
    s_dot = state.s_dot
    v_b = state.v_b

    r_p = decision.no_slip.breakdown.r_p
    r_s = decision.no_slip.breakdown.r_s
    r_s_dot = decision.no_slip.breakdown.r_s_dot

    r_p_cm = CVT_GEOMETRY.primary_centroid_radius(s)
    r_p_cm_dot = CVT_GEOMETRY.primary_outer_radius_time_derivative(s, s_dot)
    phi_p = CVT_GEOMETRY.primary_wrap_angle(s)

    F_p_ax = primary_pulley.calculate_axial_clamping_force(state).pulley_breakdown.net

    mu_k = RUBBER_ALUMINUM_KINETIC_FRICTION
    beta = SHEAVE_ANGLE / 2.0
    rho_b = RUBBER_DENSITY
    A_b = BELT_CROSS_SECTIONAL_AREA

    sigma_p = decision.primary_slip_direction

    numerator = (
        sigma_p * (2.0 * mu_k * F_p_ax * math.tan(beta) - rho_b * A_b * phi_p * r_p_cm_dot * v_b)
        - tau_load / r_s
        + I_s * r_s_dot * state.ω_s / (r_s ** 2)
    )
    denominator = m_b + sigma_p * rho_b * A_b * phi_p * r_p_cm + I_s / (r_s ** 2)
    v_b_dot = numerator / denominator

    tau_p = sigma_p * r_p * (
        2.0 * mu_k * F_p_ax * math.tan(beta)
        - rho_b * A_b * phi_p * (r_p_cm * v_b_dot + r_p_cm_dot * v_b)
    )
    tau_s = tau_load + I_s * (v_b_dot - r_s_dot * state.ω_s) / r_s

    return tau_p, tau_s


def secondary_slip_algebra(
    decision: SlipMetricsResult,
    state: SystemState,
    tau_engine: float,
    I_p: float,
    m_b: float,
    secondary_pulley: SecondaryPulley,
) -> tuple[float, float]:
    s = state.s
    s_dot = state.s_dot
    v_b = state.v_b

    r_p = decision.no_slip.breakdown.r_p
    r_p_dot = decision.no_slip.breakdown.r_p_dot
    r_s = decision.no_slip.breakdown.r_s
    r_s_dot = decision.no_slip.breakdown.r_s_dot

    r_s_cm = CVT_GEOMETRY.secondary_centroid_radius(s)
    r_s_cm_dot = CVT_GEOMETRY.secondary_outer_radius_time_derivative(s, s_dot)
    phi_s = CVT_GEOMETRY.secondary_wrap_angle(s)

    helix_rotation = secondary_pulley.initial_rotation + secondary_pulley.helix_ramp.theta(s)
    helix_rotation_rate = secondary_pulley.helix_ramp.dtheta_dx(s)
    spring_torsion_term = secondary_pulley.spring_coeff_tors * helix_rotation * helix_rotation_rate
    spring_comp_term = secondary_pulley.spring_coeff_comp * (secondary_pulley.initial_compression + s)

    mu_k = RUBBER_ALUMINUM_KINETIC_FRICTION
    beta = SHEAVE_ANGLE / 2.0
    rho_b = RUBBER_DENSITY
    A_b = BELT_CROSS_SECTIONAL_AREA

    sigma_s = decision.secondary_slip_direction
    den_s = 1.0 - sigma_s * r_s * mu_k * math.tan(beta) * helix_rotation_rate

    traction_common = (
        mu_k * math.tan(beta) * spring_torsion_term
        + 2.0 * mu_k * math.tan(beta) * spring_comp_term
        - rho_b * A_b * phi_s * r_s_cm_dot * v_b
    )

    numerator = (
        tau_engine / r_p
        + I_p * r_p_dot * state.ω_p / (r_p ** 2)
        - sigma_s * traction_common / den_s
    )
    denominator = m_b + I_p / (r_p ** 2) - sigma_s * rho_b * A_b * phi_s * r_s_cm / den_s
    v_b_dot = numerator / denominator

    tau_p = tau_engine - I_p * (v_b_dot - r_p_dot * state.ω_p) / r_p
    tau_s = sigma_s * r_s * (
        mu_k * math.tan(beta) * spring_torsion_term
        + 2.0 * mu_k * math.tan(beta) * spring_comp_term
        - rho_b * A_b * phi_s * (r_s_cm * v_b_dot + r_s_cm_dot * v_b)
    ) / den_s

    return tau_p, tau_s


def both_slip_algebra(
    decision: SlipMetricsResult,
    state: SystemState,
    m_b: float,
    primary_pulley: PrimaryPulley,
    secondary_pulley: SecondaryPulley,
) -> tuple[float, float]:
    s = state.s
    s_dot = state.s_dot
    v_b = state.v_b

    r_p = decision.no_slip.breakdown.r_p
    r_s = decision.no_slip.breakdown.r_s

    r_p_cm = CVT_GEOMETRY.primary_centroid_radius(s)
    r_p_cm_dot = CVT_GEOMETRY.primary_outer_radius_time_derivative(s, s_dot)
    r_s_cm = CVT_GEOMETRY.secondary_centroid_radius(s)
    r_s_cm_dot = CVT_GEOMETRY.secondary_outer_radius_time_derivative(s, s_dot)

    phi_p = CVT_GEOMETRY.primary_wrap_angle(s)
    phi_s = CVT_GEOMETRY.secondary_wrap_angle(s)
    F_p_ax = primary_pulley.calculate_axial_clamping_force(state).pulley_breakdown.net

    helix_rotation = secondary_pulley.initial_rotation + secondary_pulley.helix_ramp.theta(s)
    helix_rotation_rate = secondary_pulley.helix_ramp.dtheta_dx(s)
    spring_torsion_term = secondary_pulley.spring_coeff_tors * helix_rotation * helix_rotation_rate
    spring_comp_term = secondary_pulley.spring_coeff_comp * (secondary_pulley.initial_compression + s)

    mu_k = RUBBER_ALUMINUM_KINETIC_FRICTION
    beta = SHEAVE_ANGLE / 2.0
    rho_b = RUBBER_DENSITY
    A_b = BELT_CROSS_SECTIONAL_AREA

    sigma_p = decision.primary_slip_direction
    sigma_s = decision.secondary_slip_direction

    den_s = 1.0 - sigma_s * r_s * mu_k * math.tan(beta) * helix_rotation_rate
    if abs(den_s) < 1e-9:
        den_s = math.copysign(1e-9, den_s if den_s != 0.0 else 1.0)

    primary_term = sigma_p * (2.0 * mu_k * F_p_ax * math.tan(beta) - rho_b * A_b * phi_p * r_p_cm_dot * v_b)
    secondary_term = sigma_s * (
        mu_k * math.tan(beta) * spring_torsion_term
        + 2.0 * mu_k * math.tan(beta) * spring_comp_term
        - rho_b * A_b * phi_s * r_s_cm_dot * v_b
    ) / den_s

    numerator = primary_term - secondary_term
    denominator = m_b + sigma_p * rho_b * A_b * phi_p * r_p_cm - sigma_s * rho_b * A_b * phi_s * r_s_cm / den_s
    v_b_dot = numerator / denominator

    tau_p = sigma_p * r_p * (
        2.0 * mu_k * F_p_ax * math.tan(beta)
        - rho_b * A_b * phi_p * (r_p_cm * v_b_dot + r_p_cm_dot * v_b)
    )
    tau_s = sigma_s * r_s * (
        mu_k * math.tan(beta) * spring_torsion_term
        + 2.0 * mu_k * math.tan(beta) * spring_comp_term
        - rho_b * A_b * phi_s * (r_s_cm * v_b_dot + r_s_cm_dot * v_b)
    ) / den_s

    return tau_p, tau_s
