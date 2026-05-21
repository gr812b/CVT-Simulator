"""Slip branch resolver.

Takes the contact-state decision and returns the torques for the selected
branch. The selector provides kinematics and admissibility; this module turns
that into the discrete branch and resolves the branch algebra.
"""

import math

from cvt_simulator.components.primary_pulley import PrimaryPulley
from cvt_simulator.components.secondary_pulley import SecondaryPulley
from cvt_simulator.constants.car_specs import BELT_CROSS_SECTIONAL_AREA, SHEAVE_ANGLE
from cvt_simulator.constants.constants import RUBBER_ALUMINUM_KINETIC_FRICTION, RUBBER_DENSITY
from cvt_simulator.core.data_types import SlipMetricsResult, BranchTorqueResult, SlipBranch
from cvt_simulator.core.system_state import SystemState
from cvt_simulator.slip.no_slip_candidate import NoSlipResult
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm
from cvt_simulator.slip.branch_algebra import (
    primary_slip_algebra,
    secondary_slip_algebra,
    both_slip_algebra,
)


class BranchResolver:
    """Resolve branch choice into branch torques."""

    def resolve_branch(
        self,
        slip_metrics: SlipMetricsResult,
        state: SystemState,
        tau_engine: float,
        tau_load: float,
        I_p: float,
        I_s: float,
        m_b: float,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
    ) -> BranchTorqueResult:
        """Return the torques for the selected branch."""
        branch = self._select_branch(slip_metrics)
        no_slip = slip_metrics.no_slip

        if branch is SlipBranch.NO_SLIP:
            return self._no_slip_branch(no_slip)
        if branch is SlipBranch.PRIMARY_SLIP:
            return self._primary_slip_branch(branch, slip_metrics, state, tau_load, I_s, m_b, primary_pulley)
        if branch is SlipBranch.SECONDARY_SLIP:
            return self._secondary_slip_branch(branch, slip_metrics, state, tau_engine, I_p, m_b, primary_pulley, secondary_pulley)
        return self._both_slip_branch(branch, slip_metrics, state, tau_engine, tau_load, I_p, I_s, m_b, primary_pulley, secondary_pulley)

    def _select_branch(self, decision: SlipMetricsResult) -> SlipBranch:
        # Stickability removed from the selector contract. Decide purely from admissibility.
        if decision.primary_admissible and decision.secondary_admissible:
            return SlipBranch.NO_SLIP

        if (not decision.primary_admissible) and decision.secondary_admissible:
            return SlipBranch.PRIMARY_SLIP

        if decision.primary_admissible and (not decision.secondary_admissible):
            return SlipBranch.SECONDARY_SLIP

        return SlipBranch.BOTH_SLIP

    def _no_slip_branch(self, no_slip: NoSlipResult) -> BranchTorqueResult:
        return BranchTorqueResult(
            branch=SlipBranch.NO_SLIP,
            tau_p=no_slip.tau_p_ns,
            tau_s=no_slip.tau_s_ns,
        )

    def _primary_slip_branch(
        self,
        branch: SlipBranch,
        decision: SlipMetricsResult,
        state: SystemState,
        tau_load: float,
        I_s: float,
        m_b: float,
        primary_pulley: PrimaryPulley,
    ) -> BranchTorqueResult:
        tau_p, tau_s = primary_slip_algebra(decision, state, tau_load, I_s, m_b, primary_pulley)
        return BranchTorqueResult(
            branch=branch,
            tau_p=tau_p,
            tau_s=tau_s,
        )

    def _secondary_slip_branch(
        self,
        branch: SlipBranch,
        decision: SlipMetricsResult,
        state: SystemState,
        tau_engine: float,
        I_p: float,
        m_b: float,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
    ) -> BranchTorqueResult:
        tau_p, tau_s = secondary_slip_algebra(
            decision, state, tau_engine, I_p, m_b, primary_pulley, secondary_pulley
        )
        return BranchTorqueResult(
            branch=branch,
            tau_p=tau_p,
            tau_s=tau_s,
        )

    def _both_slip_branch(
        self,
        branch: SlipBranch,
        decision: SlipMetricsResult,
        state: SystemState,
        tau_engine: float,
        tau_load: float,
        I_p: float,
        I_s: float,
        m_b: float,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
    ) -> BranchTorqueResult:
        tau_p, tau_s = both_slip_algebra(
            decision, state, tau_engine, tau_load, I_p, I_s, m_b, primary_pulley, secondary_pulley
        )
        return BranchTorqueResult(
            branch=branch,
            tau_p=tau_p,
            tau_s=tau_s,
        )