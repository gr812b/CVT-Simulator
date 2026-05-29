"""Public contact torque orchestration for the slip pipeline.

This module wraps the no-slip candidate, torque admissibility evaluation,
branch selection, and branch resolution into one call that returns the
selected contact torques and belt acceleration.
"""

from cvt_simulator.core.components.primary_pulley import PrimaryPulley
from cvt_simulator.core.components.secondary_pulley import SecondaryPulley
from cvt_simulator.core.data_types import ContactTorqueResult, SlipBranch, SlipMetricsResult
from cvt_simulator.sim.system_state import SystemState

from cvt_simulator.core.slip.torque_solver import TorqueSolver
from cvt_simulator.core.slip.determiner.slip_metrics import SlipMetrics
from cvt_simulator.core.slip.determiner.no_slip_candidate import compute_no_slip_candidate
from cvt_simulator.core.slip.determiner.torque_admissibility import TorqueAdmissibility


class ContactTorqueSolver:
    """Resolve contact torques by selecting and solving the active slip branch."""

    def __init__(
        self,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
        I_p: float,
        I_s: float,
        m_b: float,
    ) -> None:
        self.I_p = I_p
        self.I_s = I_s
        self.m_b = m_b

        self.primary_pulley = primary_pulley
        self.secondary_pulley = secondary_pulley
        self.torque_admissibility = TorqueAdmissibility(primary_pulley, secondary_pulley)
        self.slip_metric_solver = SlipMetrics(
            torque_admissibility_solver = self.torque_admissibility,
            I_p=I_p,
            I_s=I_s,
            m_b=m_b,
        )
        self.branch_resolver = TorqueSolver()

    def solve(
        self,
        state: SystemState,
        contact_branch: SlipBranch,
        tau_engine: float,
        tau_load: float,
    ) -> ContactTorqueResult:
        """Return the branch-selected contact torques and belt acceleration."""
        slip_metrics = self.slip_metric_solver.get_slip_metrics(state, tau_engine, tau_load)

        branch_result = self.branch_resolver.resolve_branch(
            branch=contact_branch,
            slip_metrics=slip_metrics,
            state=state,
            tau_engine=tau_engine,
            tau_load=tau_load,
            I_p=self.I_p,
            I_s=self.I_s,
            m_b=self.m_b,
            primary_pulley=self.primary_pulley,
            secondary_pulley=self.secondary_pulley,
        )

        return ContactTorqueResult(
            tau_p=branch_result.tau_p,
            tau_s=branch_result.tau_s,
            branch=contact_branch,
            slip_metrics=slip_metrics,
            branch_result=branch_result,
        )
    
    # TODO: Temp drilling to avoid extra compute
    def get_slip_metrics(self, state: SystemState, tau_engine: float, tau_load: float) -> SlipMetricsResult:
        """Return the slip metrics for the current state and torques."""
        return self.slip_metric_solver.get_slip_metrics(state, tau_engine, tau_load)
