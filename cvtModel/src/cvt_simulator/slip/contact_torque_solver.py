"""Public contact torque orchestration for the slip pipeline.

This module wraps the no-slip candidate, torque admissibility evaluation,
branch selection, and branch resolution into one call that returns the
selected contact torques and belt acceleration.
"""

from cvt_simulator.components.primary_pulley import PrimaryPulley
from cvt_simulator.components.secondary_pulley import SecondaryPulley
from cvt_simulator.core.data_types import ContactTorqueResult
from cvt_simulator.core.system_state import SystemState

from cvt_simulator.slip.branch_resolver import BranchResolver
from cvt_simulator.slip.slip_metrics import SlipMetrics
from cvt_simulator.slip.no_slip_candidate import NoSlipResult, compute_no_slip_candidate
from cvt_simulator.slip.torque_admissibility import TorqueAdmissibility


class ContactTorqueSolver:
    """Resolve contact torques by selecting and solving the active slip branch."""

    def __init__(
        self,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
    ) -> None:
        self.primary_pulley = primary_pulley
        self.secondary_pulley = secondary_pulley
        self.torque_admissibility = TorqueAdmissibility(primary_pulley, secondary_pulley)
        self.branch_selector = SlipMetrics()
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

        admissibility = self.torque_admissibility.get_breakdown(state, no_slip)

        # Contains no slip and admissibility objects
        slip_metrics = self.branch_selector.decide_branch(
            state=state,
            no_slip=no_slip,
            admissibility=admissibility,
        )

        branch_result = self.branch_resolver.resolve_branch(
            slip_metrics=slip_metrics,
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
            branch=branch_result.branch,
            slip_metrics=slip_metrics,
            branch_result=branch_result,
        )
