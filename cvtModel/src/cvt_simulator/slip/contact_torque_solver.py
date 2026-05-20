"""Public contact torque orchestration for the slip pipeline.

This module wraps the no-slip candidate, branch selection, and branch
resolution into one call that returns the selected contact torques and belt
acceleration.
"""
from dataclasses import dataclass

from cvt_simulator.components.primary_pulley import PrimaryPulley
from cvt_simulator.components.secondary_pulley import SecondaryPulley
from cvt_simulator.core.system_state import SystemState
from cvt_simulator.slip.branch_resolver import BranchResolver, BranchTorqueResult
from cvt_simulator.slip.branch_selector import BranchDeciderResult, BranchSelector, SlipBranch
from cvt_simulator.slip.no_slip_candidate import NoSlipResult, compute_no_slip_candidate


@dataclass
class ContactTorqueResult:
    tau_p: float
    tau_s: float
    v_b_dot: float
    branch: SlipBranch
    no_slip: NoSlipResult
    decision: BranchDeciderResult
    branch_result: BranchTorqueResult
    note: str


class ContactTorqueSolver:
    """Resolve contact torques by selecting and solving the active slip branch."""

    def __init__(
        self,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
    ) -> None:
        self.primary_pulley = primary_pulley
        self.secondary_pulley = secondary_pulley
        self.branch_selector = BranchSelector(primary_pulley, secondary_pulley)
        self.branch_resolver = BranchResolver()

    def solve(
        self,
        state: SystemState,
        tau_engine: float,
        tau_load: float,
        I_p: float,
        I_s: float,
        m_b: float,
    ) -> ContactTorqueResult:
        """Return the branch-selected contact torques and belt acceleration."""
        no_slip = compute_no_slip_candidate(
            state=state,
            τ_eng=tau_engine,
            τ_load=tau_load,
            I_p=I_p,
            I_s=I_s,
            m_b=m_b,
        )

        decision = self.branch_selector.decide_branch(
            state=state,
            no_slip=no_slip,
        )

        branch_result = self.branch_resolver.resolve_branch(
            decision=decision,
            state=state,
            tau_engine=tau_engine,
            tau_load=tau_load,
            I_p=I_p,
            I_s=I_s,
            m_b=m_b,
            primary_pulley=self.primary_pulley,
            secondary_pulley=self.secondary_pulley,
        )

        return ContactTorqueResult(
            tau_p=branch_result.tau_p,
            tau_s=branch_result.tau_s,
            v_b_dot=branch_result.v_b_dot,
            branch=decision.branch,
            no_slip=no_slip,
            decision=decision,
            branch_result=branch_result,
            note=branch_result.note,
        )
