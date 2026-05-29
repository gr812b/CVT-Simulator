"""Slip branch resolver.

Takes the contact-state decision and returns the torques for the selected
branch. The selector provides kinematics and admissibility; this module turns
that into the discrete branch and resolves the branch algebra.
"""

from cvt_simulator.core.components.primary_pulley import PrimaryPulley
from cvt_simulator.core.components.secondary_pulley import SecondaryPulley
from cvt_simulator.core.data_types import (
    SlipMetricsResult,
    BranchTorqueResult,
    SlipBranch,
)
from cvt_simulator.sim.system_state import SystemState
from cvt_simulator.core.slip.determiner.no_slip_candidate import (
    compute_no_slip_candidate,
)
from cvt_simulator.core.slip.slip_branch_algebra import (
    primary_slip_algebra,
    secondary_slip_algebra,
    both_slip_algebra,
)


class TorqueSolver:
    """Resolve branch choice into branch torques."""

    def resolve_branch(
        self,
        branch: SlipBranch,
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
        if branch is SlipBranch.NO_SLIP:
            return self._no_slip_branch(state, tau_engine, tau_load, I_p, I_s, m_b)
        if branch is SlipBranch.PRIMARY_SLIP:
            return self._primary_slip_branch(
                slip_metrics.primary_slip_direction,
                state,
                tau_load,
                I_s,
                m_b,
                primary_pulley,
            )
        if branch is SlipBranch.SECONDARY_SLIP:
            return self._secondary_slip_branch(
                slip_metrics.secondary_slip_direction,
                state,
                tau_engine,
                I_p,
                m_b,
                secondary_pulley,
            )

        return self._both_slip_branch(
            slip_metrics.primary_slip_direction,
            slip_metrics.secondary_slip_direction,
            state,
            m_b,
            primary_pulley,
            secondary_pulley,
        )

    def _no_slip_branch(
        self,
        state: SystemState,
        tau_engine: float,
        tau_load: float,
        I_p: float,
        I_s: float,
        m_b: float,
    ) -> BranchTorqueResult:
        no_slip = compute_no_slip_candidate(
            state=state,
            τ_eng=tau_engine,
            τ_load=tau_load,
            I_p=I_p,
            I_s=I_s,
            m_b=m_b,
        )
        return BranchTorqueResult(
            tau_p=no_slip.tau_p_ns,
            tau_s=no_slip.tau_s_ns,
        )

    def _primary_slip_branch(
        self,
        slip_dir: float,
        state: SystemState,
        tau_load: float,
        I_s: float,
        m_b: float,
        primary_pulley: PrimaryPulley,
    ) -> BranchTorqueResult:
        tau_p, tau_s = primary_slip_algebra(
            slip_dir, state, tau_load, I_s, m_b, primary_pulley
        )
        return BranchTorqueResult(
            tau_p=tau_p,
            tau_s=tau_s,
        )

    def _secondary_slip_branch(
        self,
        slip_dir: float,
        state: SystemState,
        tau_engine: float,
        I_p: float,
        m_b: float,
        secondary_pulley: SecondaryPulley,
    ) -> BranchTorqueResult:
        tau_p, tau_s = secondary_slip_algebra(
            slip_dir, state, tau_engine, I_p, m_b, secondary_pulley
        )
        return BranchTorqueResult(
            tau_p=tau_p,
            tau_s=tau_s,
        )

    def _both_slip_branch(
        self,
        slip_dir_p: float,
        slip_dir_s: float,
        state: SystemState,
        m_b: float,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
    ) -> BranchTorqueResult:
        tau_p, tau_s = both_slip_algebra(
            slip_dir_p, slip_dir_s, state, m_b, primary_pulley, secondary_pulley
        )
        return BranchTorqueResult(
            tau_p=tau_p,
            tau_s=tau_s,
        )
