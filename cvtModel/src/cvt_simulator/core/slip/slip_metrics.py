"""Slip branch selection helper.

Chooses between the four torque-transfer branches:
- no slip
- primary slip
- secondary slip
- both slip

This module uses the no-slip candidate together with the torque admissibility
limits. It only decides which branch is active and records the relative contact
speeds that determine slip direction.
"""
from __future__ import annotations

from cvt_simulator.geometry.cvt_geometry import CVT_GEOMETRY
from cvt_simulator.constants.tuning import BELT_STICK_SPEED_THRESHOLD
from cvt_simulator.core.data_types import SlipMetricsResult, TorqueAdmissibilityResult
from cvt_simulator.sim_utils.system_state import SystemState
from cvt_simulator.core.slip.no_slip_candidate import NoSlipResult
from cvt_simulator.geometry.theoretical_models import TheoreticalModels as tm


class SlipMetrics:
    """Select the active torque-transfer branch.

    This is the new branch-selection implementation. The legacy
    `BranchDecider` remains available in `branch_decider.py`.
    """
    def __init__(self) -> None:
        self.cvt = CVT_GEOMETRY

    def decide_branch(
        self,
        state: SystemState,
        no_slip: NoSlipResult,
        admissibility: TorqueAdmissibilityResult,
    ) -> SlipMetricsResult:
        """Decide which branch is active."""
        primary_relative_speed, secondary_relative_speed = self._relative_contact_speeds(state)

        primary_admissible = (
            admissibility.primary_tau_p_stick_lower
            <= no_slip.tau_p_ns
            <= admissibility.primary_tau_p_stick_upper
        )
        secondary_admissible = (
            admissibility.secondary_tau_stick_lower
            <= no_slip.tau_s_ns
            <= admissibility.secondary_tau_stick_upper
        )
        primary_slip_direction = self._slip_direction(
            relative_speed=primary_relative_speed,
            tau_ns=no_slip.tau_p_ns,
            lower_bound=admissibility.primary_tau_p_stick_lower,
            upper_bound=admissibility.primary_tau_p_stick_upper,
        )
        secondary_slip_direction = self._slip_direction(
            relative_speed=secondary_relative_speed,
            tau_ns=no_slip.tau_s_ns,
            lower_bound=admissibility.secondary_tau_stick_lower,
            upper_bound=admissibility.secondary_tau_stick_upper,
        )

        return SlipMetricsResult(
            primary_relative_speed=primary_relative_speed,
            secondary_relative_speed=secondary_relative_speed,
            primary_slip_direction=primary_slip_direction,
            secondary_slip_direction=secondary_slip_direction,
            primary_admissible=primary_admissible,
            secondary_admissible=secondary_admissible,
            admissibility=admissibility,
            no_slip=no_slip,
        )

    def _relative_contact_speeds(self, state: SystemState) -> tuple[float, float]:
        """Return the contact relative speeds"""
        s = state.s
        primary_relative_speed = self.cvt.primary_effective_radius(s) * state.ω_p - state.v_b
        secondary_relative_speed = state.v_b - self.cvt.secondary_effective_radius(s) * state.ω_s
        return primary_relative_speed, secondary_relative_speed

    def _slip_direction(
        self,
        relative_speed: float,
        tau_ns: float,
        lower_bound: float,
        upper_bound: float,
    ) -> float:
        # When the contact is moving faster than the stick threshold, direction is set by the
        # sign of the relative speed; otherwise it falls back to the torque bounds.
        if abs(relative_speed) > BELT_STICK_SPEED_THRESHOLD:
            return tm.sgn(relative_speed)

        if tau_ns > upper_bound:
            return 1.0
        if tau_ns < lower_bound:
            return -1.0
        return 0.0

