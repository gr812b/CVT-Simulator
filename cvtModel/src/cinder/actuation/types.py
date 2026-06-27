from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PulleyActuationState:
    """
    Known local state of one movable sheave.

    axial_position is positive in the pulley-local closing direction.
    """

    axial_position: float      # m
    axial_speed: float         # m/s
    shaft_speed: float         # rad/s


@dataclass(frozen=True, slots=True)
class PulleyActuationResult:
    """
    Local actuator force represented as:

        axial_force = bias_force + torque_gain * pulley_torque
    """

    bias_force: float          # N
    torque_gain: float         # 1/m

    def at_torque(self, pulley_torque: float) -> float:
        return self.bias_force + self.torque_gain * pulley_torque


class AxialForceLaw(Protocol):
    def force_relation(
        self,
        state: PulleyActuationState,
    ) -> PulleyActuationResult:
        ...