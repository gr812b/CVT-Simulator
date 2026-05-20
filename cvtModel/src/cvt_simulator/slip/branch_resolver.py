"""Slip branch resolver.

Takes a selected branch and returns the torques for that branch.
The no-slip branch uses the torques already computed by the no-slip candidate.
The other branches are placeholders for now and will be filled in later.
"""
from dataclasses import dataclass

from cvt_simulator.slip.branch_selector import SlipBranch, BranchDeciderResult
from cvt_simulator.slip.no_slip_candidate import NoSlipResult
from cvt_simulator.core.system_state import SystemState
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.components.primary_pulley import PrimaryPulley
from cvt_simulator.components.secondary_pulley import SecondaryPulley
from cvt_simulator.constants.constants import (
    RUBBER_ALUMINUM_KINETIC_FRICTION,
    RUBBER_DENSITY,
)
from cvt_simulator.constants.car_specs import BELT_CROSS_SECTIONAL_AREA, SHEAVE_ANGLE
import math


@dataclass
class BranchTorqueResult:
    tau_p: float
    tau_s: float
    v_b_dot: float
    note: str


class BranchResolver:
    """Resolve branch choice into branch torques."""

    def resolve_branch(
        self,
        decision: BranchDeciderResult,
        state: SystemState,
        tau_engine: float,
        tau_load: float,
        I_p: float,
        I_s: float,
        m_b: float,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
    ) -> BranchTorqueResult:
        """Return the torques for the selected branch.

        Args:
            decision: Result from `BranchSelector.decide_branch()` containing
                the chosen branch, slip directions and the `no_slip` candidate.
            state: Current `SystemState`.
            tau_engine: Engine torque (unused for primary-slip algebra but
                included for symmetry).
            tau_load: External load at the secondary.
            I_p: Primary effective inertia.
            I_s: Secondary effective inertia.
            m_b: Effective belt mass.
            primary_pulley: PrimaryPulley instance (used to get axial force).
            secondary_pulley: SecondaryPulley instance (included for future use).
        """
        branch = decision.branch
        no_slip = decision.no_slip

        if branch is SlipBranch.NO_SLIP:
            return self._no_slip_branch(no_slip)
        if branch is SlipBranch.PRIMARY_SLIP:
            return self._primary_slip_branch(decision, state, tau_load, I_s, m_b, primary_pulley)
        if branch is SlipBranch.SECONDARY_SLIP:
            return self._secondary_slip_branch(decision, state, tau_engine, I_p, m_b, primary_pulley, secondary_pulley)
        return self._both_slip_branch(decision, state, tau_engine, tau_load, I_p, I_s, m_b, primary_pulley, secondary_pulley)

    def _no_slip_branch(self, no_slip: NoSlipResult) -> BranchTorqueResult:
        return BranchTorqueResult(
            tau_p=no_slip.tau_p_ns,
            tau_s=no_slip.tau_s_ns,
            v_b_dot=no_slip.v_b_dot_ns,
            note="No-slip branch accepted.",
        )

    def _primary_slip_branch(
        self,
        decision: BranchDeciderResult,
        state: SystemState,
        tau_load: float,
        I_s: float,
        m_b: float,
        primary_pulley: PrimaryPulley,
    ) -> BranchTorqueResult:
        """Resolve the primary-slip branch algebraically per the derivation.

        Uses kinetic traction at the primary and no-slip compatibility at the
        secondary to solve for `v_b_dot`, then recovers `tau_p` and `tau_s`.
        """
        s = state.s
        s_dot = state.s_dot
        v_b = state.v_b

        # Radii and rates from the no-slip breakdown (already computed)
        r_p = decision.no_slip.breakdown.r_p
        r_s = decision.no_slip.breakdown.r_s
        r_s_dot = decision.no_slip.breakdown.r_s_dot

        # Centroid quantities
        r_p_cm = tm.primary_centroid_radius(s)
        r_p_cm_dot = tm.primary_radius_rate_of_change(s) * s_dot

        # Wrap angle (phi_p)
        phi_p = tm.primary_wrap_angle(s)

        # Axial clamping force at primary (pulley-only, exclude belt contribution)
        F_p_ax = primary_pulley.calculate_axial_clamping_force(state).pulley_breakdown.net

        # Kinetic friction and geometry
        mu_k = RUBBER_ALUMINUM_KINETIC_FRICTION
        beta = SHEAVE_ANGLE / 2.0

        # Slip direction sign (with fallback when entering slip from rest)
        sigma_p = self._primary_slip_sign_from_decision(decision)

        # Constants
        rho_b = RUBBER_DENSITY
        A_b = BELT_CROSS_SECTIONAL_AREA

        # Numerator and denominator per AGENT_CONTEXT primary-slip equation
        numerator = (
            sigma_p * (2.0 * mu_k * F_p_ax * math.tan(beta) - rho_b * A_b * phi_p * r_p_cm_dot * v_b)
            - tau_load / r_s
            + I_s * r_s_dot * state.ω_s / (r_s ** 2)
        )

        denominator = m_b + sigma_p * rho_b * A_b * phi_p * r_p_cm + I_s / (r_s ** 2)

        v_b_dot = numerator / denominator

        # Recover torques
        tau_p = sigma_p * r_p * (
            2.0 * mu_k * F_p_ax * math.tan(beta)
            - rho_b * A_b * phi_p * (r_p_cm * v_b_dot + r_p_cm_dot * v_b)
        )

        tau_s = tau_load + I_s * (v_b_dot - r_s_dot * state.ω_s) / r_s

        return BranchTorqueResult(
            tau_p=tau_p,
            tau_s=tau_s,
            v_b_dot=v_b_dot,
            note="Primary-slip branch resolved.",
        )

    def _primary_slip_sign_from_decision(self, decision: BranchDeciderResult) -> float:
        if decision.primary_slip_direction != 0.0:
            return decision.primary_slip_direction

        tau_p_ns = decision.no_slip.tau_p_ns
        tau_p_lim = decision.admissibility.primary.tau_p_stick_limit

        if tau_p_ns > tau_p_lim:
            return 1.0
        if tau_p_ns < -tau_p_lim:
            return -1.0
        return 0.0

    def _secondary_slip_sign_from_decision(self, decision: BranchDeciderResult) -> float:
        if decision.secondary_slip_direction != 0.0:
            return decision.secondary_slip_direction

        tau_s_ns = decision.no_slip.tau_s_ns
        tau_s_upper = decision.admissibility.secondary.tau_stick_upper
        tau_s_lower = decision.admissibility.secondary.tau_stick_lower

        if tau_s_ns > tau_s_upper:
            return 1.0
        if tau_s_ns < tau_s_lower:
            return -1.0
        return 0.0

    def _secondary_slip_branch(
        self,
        decision: BranchDeciderResult,
        state: SystemState,
        tau_engine: float,
        I_p: float,
        m_b: float,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
    ) -> BranchTorqueResult:
        """Resolve the secondary-slip branch per the derivation.

        Uses no-slip compatibility at the primary and kinetic traction at the
        secondary. Solves algebraically for `v_b_dot`, then recovers torques.
        """
        s = state.s
        s_dot = state.s_dot
        v_b = state.v_b

        # Radii and rates from no-slip breakdown
        r_p = decision.no_slip.breakdown.r_p
        r_p_dot = decision.no_slip.breakdown.r_p_dot
        r_s = decision.no_slip.breakdown.r_s
        r_s_dot = decision.no_slip.breakdown.r_s_dot

        # Centroid quantities for secondary
        r_s_cm = tm.secondary_centroid_radius(s)
        r_s_cm_dot = tm.secondary_radius_rate_of_change(s) * s_dot

        # Wrap angle
        phi_s = tm.secondary_wrap_angle(s)

        # Helix / spring terms
        helix_rotation = secondary_pulley.initial_rotation + secondary_pulley.helix_ramp.theta(s)
        helix_rotation_rate = secondary_pulley.helix_ramp.dtheta_dx(s)
        spring_torsion_term = secondary_pulley.spring_coeff_tors * helix_rotation * helix_rotation_rate
        spring_comp_term = secondary_pulley.spring_coeff_comp * (secondary_pulley.initial_compression + s)

        mu_k = RUBBER_ALUMINUM_KINETIC_FRICTION
        beta = SHEAVE_ANGLE / 2.0
        rho_b = RUBBER_DENSITY
        A_b = BELT_CROSS_SECTIONAL_AREA

        # Determine slip sign; fall back to admissibility if zero
        sigma_s = self._secondary_slip_sign_from_decision(decision)

        # denominator for helix coupling
        den_s = 1.0 - sigma_s * r_s * mu_k * math.tan(beta) * helix_rotation_rate

        # bracketed traction numerator term (uses r_s_cm_dot * v_b here per derivation)
        traction_common = (
            mu_k * math.tan(beta) * spring_torsion_term
            + 2.0 * mu_k * math.tan(beta) * spring_comp_term
            - rho_b * A_b * phi_s * r_s_cm_dot * v_b
        )

        numerator = (
            tau_engine / r_p
            + I_p * r_p_dot * state.ω_p / (r_p ** 2)
            - sigma_s * (traction_common) / den_s
        )

        denominator = (
            m_b
            + I_p / (r_p ** 2)
            - sigma_s * rho_b * A_b * phi_s * r_s_cm / den_s
        )

        v_b_dot = numerator / denominator

        # Recover torques
        tau_p = tau_engine - I_p * (v_b_dot - r_p_dot * state.ω_p) / r_p

        tau_s = sigma_s * r_s * (
            mu_k * math.tan(beta) * spring_torsion_term
            + 2.0 * mu_k * math.tan(beta) * spring_comp_term
            - rho_b * A_b * phi_s * (r_s_cm * v_b_dot + r_s_cm_dot * v_b)
        ) / den_s

        return BranchTorqueResult(
            tau_p=tau_p,
            tau_s=tau_s,
            v_b_dot=v_b_dot,
            note="Secondary-slip branch resolved.",
        )

    def _both_slip_branch(
        self,
        decision: BranchDeciderResult,
        state: SystemState,
        tau_engine: float,
        tau_load: float,
        I_p: float,
        I_s: float,
        m_b: float,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
    ) -> BranchTorqueResult:
        """Resolve the both-slip branch per the derivation.

        Both contacts slip; traction is kinetic on both. Solve algebraically for
        `v_b_dot` then recover `tau_p` and `tau_s`.
        """
        s = state.s
        s_dot = state.s_dot
        v_b = state.v_b

        # Radii and rates
        r_p = decision.no_slip.breakdown.r_p
        r_s = decision.no_slip.breakdown.r_s
        r_s_dot = decision.no_slip.breakdown.r_s_dot

        # Centroid radii and rates
        r_p_cm = tm.primary_centroid_radius(s)
        r_p_cm_dot = tm.primary_radius_rate_of_change(s) * s_dot
        r_s_cm = tm.secondary_centroid_radius(s)
        r_s_cm_dot = tm.secondary_radius_rate_of_change(s) * s_dot

        # Wraps and axial forces
        phi_p = tm.primary_wrap_angle(s)
        phi_s = tm.secondary_wrap_angle(s)
        # Use pulley-only axial clamping (exclude belt contribution)
        F_p_ax = primary_pulley.calculate_axial_clamping_force(state).pulley_breakdown.net

        # Secondary helix/spring terms
        helix_rotation = secondary_pulley.initial_rotation + secondary_pulley.helix_ramp.theta(s)
        helix_rotation_rate = secondary_pulley.helix_ramp.dtheta_dx(s)
        spring_torsion_term = secondary_pulley.spring_coeff_tors * helix_rotation * helix_rotation_rate
        spring_comp_term = secondary_pulley.spring_coeff_comp * (secondary_pulley.initial_compression + s)

        mu_k = RUBBER_ALUMINUM_KINETIC_FRICTION
        beta = SHEAVE_ANGLE / 2.0
        rho_b = RUBBER_DENSITY
        A_b = BELT_CROSS_SECTIONAL_AREA

        # Determine slip signs (fall back to admissibility when zero)
        sigma_p = self._primary_slip_sign_from_decision(decision)
        sigma_s = self._secondary_slip_sign_from_decision(decision)

        # Secondary denominator (helix coupling)
        den_s = 1.0 - sigma_s * r_s * mu_k * math.tan(beta) * helix_rotation_rate
        if abs(den_s) < 1e-9:
            den_s = math.copysign(1e-9, den_s if den_s != 0.0 else 1.0)

        # Numerator per AGENT_CONTEXT (both-slip)
        primary_term = sigma_p * (2.0 * mu_k * F_p_ax * math.tan(beta) - rho_b * A_b * phi_p * r_p_cm_dot * v_b)
        secondary_term = sigma_s * (
            mu_k * math.tan(beta) * spring_torsion_term + 2.0 * mu_k * math.tan(beta) * spring_comp_term - rho_b * A_b * phi_s * r_s_cm_dot * v_b
        ) / den_s

        numerator = primary_term - secondary_term

        denominator = (
            m_b
            + sigma_p * rho_b * A_b * phi_p * r_p_cm
            - sigma_s * rho_b * A_b * phi_s * r_s_cm / den_s
        )

        v_b_dot = numerator / denominator

        # Recover torques
        tau_p = sigma_p * r_p * (
            2.0 * mu_k * F_p_ax * math.tan(beta) - rho_b * A_b * phi_p * (r_p_cm * v_b_dot + r_p_cm_dot * v_b)
        )

        tau_s = sigma_s * r_s * (
            mu_k * math.tan(beta) * spring_torsion_term + 2.0 * mu_k * math.tan(beta) * spring_comp_term - rho_b * A_b * phi_s * (r_s_cm * v_b_dot + r_s_cm_dot * v_b)
        ) / den_s

        return BranchTorqueResult(
            tau_p=tau_p,
            tau_s=tau_s,
            v_b_dot=v_b_dot,
            note="Both-slip branch resolved.",
        )


