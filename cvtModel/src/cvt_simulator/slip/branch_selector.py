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

from dataclasses import dataclass
from enum import Enum, auto

from cvt_simulator.components.primary_pulley import PrimaryPulley
from cvt_simulator.components.secondary_pulley import SecondaryPulley
from cvt_simulator.constants.tuning import BELT_STICK_SPEED_THRESHOLD
from cvt_simulator.core.system_state import SystemState
from cvt_simulator.slip.no_slip_candidate import NoSlipResult
from cvt_simulator.slip.torque_admissibility import TorqueAdmissibility, TorqueAdmissibilityResult
from cvt_simulator.utils.theoretical_models import TheoreticalModels as tm


class SlipBranch(Enum):
    NO_SLIP = auto()
    PRIMARY_SLIP = auto()
    SECONDARY_SLIP = auto()
    BOTH_SLIP = auto()
@dataclass
class BranchDeciderResult:
    branch: SlipBranch
    primary_relative_speed: float
    secondary_relative_speed: float
    primary_slip_direction: float
    secondary_slip_direction: float
    primary_can_stick: bool
    secondary_can_stick: bool
    primary_admissible: bool
    secondary_admissible: bool
    admissibility: TorqueAdmissibilityResult
    no_slip: NoSlipResult


class BranchSelector:
    """Select the active torque-transfer branch.

    This is the new branch-selection implementation. The legacy
    `BranchDecider` remains available in `branch_decider.py`.
    """

    def __init__(
        self,
        primary_pulley: PrimaryPulley,
        secondary_pulley: SecondaryPulley,
    ) -> None:
        self.primary_pulley = primary_pulley
        self.secondary_pulley = secondary_pulley
        self.torque_admissibility = TorqueAdmissibility(primary_pulley, secondary_pulley)

    def decide_branch(
        self,
        state: SystemState,
        no_slip: NoSlipResult,
    ) -> BranchDeciderResult:
        """Decide which branch is active."""
        admissibility = self.torque_admissibility.get_breakdown(state, no_slip)
        primary_relative_speed, secondary_relative_speed = self._relative_contact_speeds(state)

        primary_can_stick = self._can_stick(primary_relative_speed)
        secondary_can_stick = self._can_stick(secondary_relative_speed)

        primary_admissible = abs(no_slip.tau_p_ns) <= admissibility.primary.tau_p_stick_limit
        secondary_admissible = (
            admissibility.secondary.tau_stick_lower
            <= no_slip.tau_s_ns
            <= admissibility.secondary.tau_stick_upper
        )

        branch = self._select_branch(
            primary_can_stick=primary_can_stick,
            secondary_can_stick=secondary_can_stick,
            primary_admissible=primary_admissible,
            secondary_admissible=secondary_admissible,
        )

        return BranchDeciderResult(
            branch=branch,
            primary_relative_speed=primary_relative_speed,
            secondary_relative_speed=secondary_relative_speed,
            primary_slip_direction=tm.sgn(primary_relative_speed),
            secondary_slip_direction=tm.sgn(secondary_relative_speed),
            primary_can_stick=primary_can_stick,
            secondary_can_stick=secondary_can_stick,
            primary_admissible=primary_admissible,
            secondary_admissible=secondary_admissible,
            admissibility=admissibility,
            no_slip=no_slip,
        )

    def _relative_contact_speeds(self, state: SystemState) -> tuple[float, float]:
        """Return the contact relative speeds from Eq. 11.1 and 11.2."""
        s = state.s
        primary_relative_speed = tm.primary_effective_radius(s) * state.ω_p - state.v_b
        secondary_relative_speed = state.v_b - tm.secondary_effective_radius(s) * state.ω_s
        return primary_relative_speed, secondary_relative_speed

    def _can_stick(self, relative_speed: float) -> bool:
        """Return whether a contact can remain stuck within the current tolerance."""
        return abs(relative_speed) <= BELT_STICK_SPEED_THRESHOLD

    def _select_branch(
        self,
        primary_can_stick: bool,
        secondary_can_stick: bool,
        primary_admissible: bool,
        secondary_admissible: bool,
    ) -> SlipBranch:
        if primary_can_stick and secondary_can_stick and primary_admissible and secondary_admissible:
            return SlipBranch.NO_SLIP

        if (not primary_can_stick or not primary_admissible) and secondary_can_stick and secondary_admissible:
            return SlipBranch.PRIMARY_SLIP

        if primary_can_stick and primary_admissible and (not secondary_can_stick or not secondary_admissible):
            return SlipBranch.SECONDARY_SLIP

        return SlipBranch.BOTH_SLIP


__all__ = [
    "BranchSelector",
    "BranchDeciderResult",
    "SlipBranch",
]